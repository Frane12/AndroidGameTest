#!/usr/bin/env python3
"""DRNAS Medical R19: fail-closed post-solve instrumentation for the R16 384-gene stall.

Only tracing is added: the R16 algorithms, published iML1515 input, GPR
rules, frozen gene cohorts, and independent FBA oracle remain unchanged.
This is a diagnostic experiment, not a benchmark speedup claim.
"""
from __future__ import annotations

import argparse
import faulthandler
import json
import pathlib
import sys
import time
import traceback
from unittest.mock import patch

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r11_phenotype_cache as r11
import gmispy_r15_stage_boundary as r15
import gmispy_r16_reaction_memo as r16

PROTOCOL = "DRNAS-MEDICAL-R19-POSTSOLVE-TRACE-v1"
ARMS = ("r9_baseline", "share_12_control", "share_12_memo_k3")
BASE_COORDINATOR = r15.BoundaryCoordinator
BASE_SOLVE = r9.solve
BASE_VERIFY = r9.verify_sets
EVENTS = []
OUT = None
BEGIN = time.perf_counter()


def event(phase, **fields):
    entry = {"phase": phase, "elapsed_s": round(time.perf_counter() - BEGIN, 6), **fields}
    EVENTS.append(entry)
    print("R19_PHASE " + json.dumps(entry, sort_keys=True), flush=True)
    if OUT is not None:
        r16.save(OUT, {"protocol": PROTOCOL, "complete": False, "events": EVENTS})


class TracedCoordinator(BASE_COORDINATOR):
    def factory(self, *args, **kwargs):
        event("coordinator_factory_enter", stage_index=self.instantiated)
        result = super().factory(*args, **kwargs)
        event("coordinator_factory_exit", stage_index=self.instantiated)
        return result

    def close(self):
        event("coordinator_close_enter")
        try:
            result = super().close()
            event("coordinator_close_exit")
            return result
        except BaseException as exc:
            event("coordinator_close_exception", error=repr(exc))
            raise

    def audit(self):
        event("coordinator_audit_enter")
        result = super().audit()
        event("coordinator_audit_exit")
        return result


def traced_solve(*args, **kwargs):
    event("r9_solve_enter")
    result = BASE_SOLVE(*args, **kwargs)
    event("r9_solve_exit", wall_s=result.get("wall_s"),
          lp_calls=result.get("lp_calls"), status=result.get("status"))
    return result


def traced_verify(*args, **kwargs):
    event("independent_oracle_enter", n_minimal_sets=len(args[4]))
    result = BASE_VERIFY(*args, **kwargs)
    event("independent_oracle_exit", fba_checks=result.get("FBA_calls"))
    return result


def run(args):
    global OUT
    OUT = pathlib.Path(args.out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    event("source_verify_enter", n=args.n, arm=args.arm)
    genes, expected = r11.frozen_reference(args.source, args.frozen, args.reference, args.n)
    model, manifest = r8.load_frozen(args.source)
    threshold = float(manifest["wildtype_biomass"]) * 0.01
    rules = r8.all_rules(model)
    assert len(genes) == args.n and threshold > 0
    event("source_verify_exit", gene_sha=r9.hgenes(genes),
          minima_expected=len(expected), threshold=threshold)
    del model
    model, manifest = r8.load_frozen(args.source)
    rules = r8.all_rules(model)
    event("trial_enter")
    with patch.object(r9, "solve", traced_solve), \
         patch.object(r9, "verify_sets", traced_verify), \
         patch.object(r15, "BoundaryCoordinator", TracedCoordinator):
        row = r16.trial(model, genes, rules, threshold, expected, args.arm, 0, args.n)
    event("trial_exit", wall_s=row["wall_s"],
          physical_LP_avoided=row["physical_LP_avoided"],
          reference_match=row["reference_match"],
          independent_FBA_sound=row["independent_FBA_sound"])
    r16.save(OUT, {"protocol": PROTOCOL, "complete": True, "n": args.n,
                   "arm": args.arm, "events": EVENTS, "row": row})
    print("R19_DIAG_PASS " + json.dumps({
        "n": args.n, "arm": args.arm, "wall_s": row["wall_s"],
        "physical_LP_avoided": row["physical_LP_avoided"],
        "reference_match": row["reference_match"],
        "independent_FBA_sound": row["independent_FBA_sound"]}, sort_keys=True), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--frozen", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--n", type=int, choices=(96, 384), required=True)
    p.add_argument("--arm", choices=ARMS, required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    faulthandler.enable()
    faulthandler.dump_traceback_later(60, repeat=True, file=sys.stderr)
    try:
        run(args)
    except BaseException as exc:
        event("diagnostic_exception", error=repr(exc))
        traceback.print_exc()
        raise
    finally:
        faulthandler.cancel_dump_traceback_later()
