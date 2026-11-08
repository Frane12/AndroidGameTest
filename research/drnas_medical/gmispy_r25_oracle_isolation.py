#!/usr/bin/env python3
"""DRNAS Medical R25: independent fresh-vs-reused GLPK / GPR forensics.

Research-only diagnostics. NEVER silently accept a conflicting KO, modify the
frozen R9/R24 science backend, or count these probes as solving benchmarks.
N192 and N384 share b0777, implicated in the strict R24D failures.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import time

import numpy as np
from cobra.util.array import create_stoichiometric_matrix

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r24_regression_guard as r24
from gmispy_r3 import disabled_reactions

PROTOCOL = "DRNAS-MEDICAL-R25-STRICT-ORACLE-ISOLATION-v1"
GENE = "b0777"
EPS = 1e-6
REPS = 3


def evaluate(model, rules, gene, route, threshold):
    """Measure gene KO or source-GPR reaction KO, with primal and bound checks.

    The 'with model' context is deliberately preserved in warm mode: solver
    basis/state is reused, while reaction bounds should be restored.
    """
    assert route in ("gene", "reaction")
    rxns = list(model.reactions)
    before = {r.id: tuple(r.bounds) for r in rxns}
    expected = set(disabled_reactions(rules, (gene,)))
    effective_expected = {rid for rid in expected if before[rid] != (0, 0)}
    with model:
        if route == "gene":
            model.genes.get_by_id(gene).knock_out()
        else:
            for rid in expected:
                model.reactions.get_by_id(rid).knock_out()
        after = {r.id: tuple(r.bounds) for r in rxns}
        actually_zeroed = {rid for rid in before
                           if before[rid] != (0, 0)
                           and after[rid] == (0, 0)}
        t0 = time.perf_counter()
        solution = model.optimize()
        elapsed = time.perf_counter() - t0
        optimal = solution.status == "optimal"
        result = {
            "route": route, "gene": gene, "solver_status": solution.status,
            "LP_seconds": round(elapsed, 7),
            "source_GPR_disabled": len(expected),
            "effective_source_GPR_disabled": len(effective_expected),
            "actually_zeroed_count": len(actually_zeroed),
            "missing_disabled": sorted(effective_expected - actually_zeroed),
            "unexpected_disabled": sorted(actually_zeroed - effective_expected),
            "threshold": threshold,
            "primal_accepted": False,
            "classification": "UNKNOWN",
        }
        if optimal:
            objective = float(solution.objective_value)
            vals = np.array([float(solution.fluxes.get(r.id, 0.0)) for r in rxns])
            matrix = create_stoichiometric_matrix(model, array_type="lil")
            bal = np.abs(matrix @ vals)
            residual = float(bal.max()) if bal.size else 0.0
            bounds = max((max(r.lower_bound - v, v - r.upper_bound, 0.0)
                          for r, v in zip(rxns, vals)), default=0.0)
            inactive_flux = max((abs(float(solution.fluxes.get(rid, 0.0)))
                                 for rid in expected), default=0.0)
            is_finite = (math.isfinite(objective) and np.isfinite(vals).all()
                         and all(math.isfinite(x) for x in
                                 (residual, bounds, inactive_flux)))
            primal = bool(is_finite and residual <= EPS
                          and bounds <= EPS and inactive_flux <= EPS)
            result.update({
                "growth": objective,
                "primal_max_abs_residual": residual,
                "bound_violation_max": float(bounds),
                "source_GPR_disabled_flux_max": inactive_flux,
                "flux_finite": bool(is_finite),
                "primal_accepted": primal,
            })
            if primal and abs(objective - threshold) <= EPS:
                result["classification"] = "THRESHOLD_AMBIGUOUS"
            elif primal:
                result["classification"] = (
                    "VIABLE" if objective > threshold else "LETHAL")
    # Check restoration of all reaction bounds after exiting the context.
    result["bounds_restored"] = all(
        tuple(r.bounds) == before[r.id] for r in rxns)
    return result


def pair(source, gene, order, threshold):
    """Cold: fresh SBML for EACH route. Warm: a SHARED model, two passes."""
    routes = ("gene", "reaction") if order == "gene_first" else ("reaction", "gene")
    cold = {}
    for route in routes:
        model, meta = r8.load_frozen(source)
        assert meta["SBML_sha256"] == r9.SOURCE_SHA
        cold[route] = evaluate(model, r8.all_rules(model), gene, route, threshold)
    model, meta = r8.load_frozen(source)
    assert meta["SBML_sha256"] == r9.SOURCE_SHA
    rules = r8.all_rules(model)
    warm = []
    for route in routes + routes:
        warm.append(evaluate(model, rules, gene, route, threshold))
    return {"order": order, "cold": cold, "warm": warm}


def sound_pair(a, b):
    return bool(
        a["solver_status"] == b["solver_status"] == "optimal"
        and a["primal_accepted"] and b["primal_accepted"]
        and a["classification"] == b["classification"]
        and a["classification"] in ("LETHAL", "VIABLE")
        and abs(a["growth"] - b["growth"]) <= EPS
        and a["bounds_restored"] and b["bounds_restored"]
        and not a["missing_disabled"] and not a["unexpected_disabled"]
        and not b["missing_disabled"] and not b["unexpected_disabled"]
    )


def run(args):
    source = pathlib.Path(args.source)
    manifest = r24.certified_frozen(args.manifest)
    assert args.n in (192, 384)
    genes = manifest["cohorts"]["unseen_sha_mix"][str(args.n)]
    assert GENE in genes and r9.hgenes(genes) == (
        manifest["cohort_sha"]["unseen_sha_mix"][str(args.n)])
    base, meta = r8.load_frozen(source)
    assert meta["SBML_sha256"] == r9.SOURCE_SHA
    assert GENE in {g.id for g in base.genes}
    threshold = float(meta["wildtype_biomass"]) * .01
    assert math.isfinite(threshold) and threshold > 0
    rows = []
    for rep in range(REPS):
        row = pair(source, GENE, args.order, threshold)
        row["rep"] = rep
        rows.append(row)
        print("R25_REP " + json.dumps({
            "n": args.n, "rep": rep, "order": args.order,
            "cold_gene": row["cold"]["gene"].get("growth"),
            "cold_reaction": row["cold"]["reaction"].get("growth"),
            "warm_growths": [x.get("growth") for x in row["warm"]],
        }, sort_keys=True), flush=True)

    comparisons = []
    invalid = []
    for row in rows:
        g, r = row["cold"]["gene"], row["cold"]["reaction"]
        comparisons.append(sound_pair(g, r))
        if not comparisons[-1]:
            invalid.append({"rep": row["rep"], "comparison": "fresh_gene_vs_reaction"})
        warm = row["warm"]
        for i in range(0, len(warm), 2):
            if not sound_pair(warm[i], warm[i + 1]):
                invalid.append({"rep": row["rep"], "comparison": "warm_gene_vs_reaction",
                                "pair": i // 2})
        # Cold/warm values for each path also must agree.
        for w in warm:
            if not sound_pair(row["cold"][w["route"]], w):
                invalid.append({"rep": row["rep"], "comparison": "cold_vs_warm",
                                "route": w["route"]})
    report = {
        "protocol": PROTOCOL,
        "complete": True,
        "research_only": True, "not_a_speedup_test": True,
        "not_an_independent_LP_backend_proof": True,
        "source_sha": r9.SOURCE_SHA,
        "frozen_digest": manifest["digest"],
        "family": "unseen_sha_mix", "n": args.n,
        "cohort_sha": r9.hgenes(genes),
        "gene": GENE, "order": args.order, "repetitions": REPS,
        "primal_tolerance": EPS, "growth_difference_tolerance": EPS,
        "threshold": threshold,
        "rows": rows,
        "failures": invalid,
        "outcome": ("CONSISTENT_FRESH_AND_WARM_GPR_ORACLE"
                    if not invalid else "BIOLOGICAL_OR_NUMERICAL_DISAGREEMENT"),
        "no_claim_of_R24_correctness": True,
    }
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print("R25_FINAL " + json.dumps({
        "n": args.n, "order": args.order, "outcome": report["outcome"],
        "failed_comparisons": len(invalid), "frozen_digest": report["frozen_digest"],
        "source_sha": report["source_sha"],
        "certified_R24_speedup": False
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--n", required=True, type=int, choices=(192, 384))
    parser.add_argument("--order", required=True, choices=("gene_first", "reaction_first"))
    parser.add_argument("--out", required=True)
    run(parser.parse_args())
