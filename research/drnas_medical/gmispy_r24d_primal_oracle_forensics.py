#!/usr/bin/env python3
"""DRNAS Medical R24D: numerical/biological forensic audit of R24 failures.

Does NOT weaken any certificate: run the exact R24 arm and record which
strict validation aborts, candidate KO IDs, and GLPK state diagnostics.
All original validity checks remain mandatory for solver acceptance.
No time from this instrumented experiment is a performance comparison.
"""
from __future__ import annotations
import argparse, collections, json, math, pathlib, sys, time, traceback
from unittest.mock import patch

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r24_regression_guard as r24

ORIGINAL_FLUX = r9.certified_flux
ORIGINAL_GROWTH = r9.growth
EVENTS=collections.deque(maxlen=120)
OUT=None
SOURCE=None
FAILURE=None
TRIAL_START=time.perf_counter()
EXPECTED={192:"primal stoichiometric balance invalid",
          384:"candidate not lethally valid"}

def log_event(kind, **payload):
    d={"kind":kind, "elapsed_s":round(time.perf_counter()-TRIAL_START,6),
       **payload}
    EVENTS.append(d)
    if kind in ("failure","fresh_raw_lp","oracle_growth","diagnostic"):
        print("R24D_EVENT "+json.dumps(d,sort_keys=True,default=str),flush=True)
    if OUT is not None:
        r24.save(OUT,{"protocol":"R24D-FORENSIC-STRICT-v1",
                      "complete":False,"events":list(EVENTS),
                      "failure":FAILURE})


def independent_raw_check(genes,ko,expected_threshold):
    """Forensic observation only, not an acceptance oracle or a replacement
    for the strict R9 certificate. Does not alter the search solver instance."""
    import numpy as np
    from cobra.util.array import create_stoichiometric_matrix
    model,meta=r8.load_frozen(SOURCE)
    r24.need(meta["SBML_sha256"]==r9.SOURCE_SHA,"wrong forensic SBML source")
    with model:
        for ix in ko:
            model.genes.get_by_id(genes[ix]).knock_out()
        sol=model.optimize()
        result={"status":sol.status,"threshold":expected_threshold,
                "source_sha":meta["SBML_sha256"]}
        if sol.status=="optimal":
            val=float(sol.objective_value)
            result["objective"]=val
            result["above_threshold"]=val>=expected_threshold
            rxns=list(model.reactions)
            vals=np.array([float(sol.fluxes.get(r.id,0.0)) for r in rxns])
            residual=np.abs(create_stoichiometric_matrix(model,array_type="lil")@vals)
            result["primal_max_abs_residual"]=float(np.max(residual))
            result["worst_metabolite"]=list(model.metabolites)[int(np.argmax(residual))].id
            result["finite_flux"]=bool(np.isfinite(vals).all())
            result["bound_violation_max"]=float(max(
                (max(r.lower_bound-v, v-r.upper_bound,0.0)
                 for r,v in zip(rxns,vals)),default=0.0))
        return result


def traced_flux(model,genes,ko,rules,matrix,rxns,threshold):
    global FAILURE
    labels=[genes[i] for i in ko]
    log_event("flux_enter", ko=labels,ko_indices=list(ko))
    try:
        result=ORIGINAL_FLUX(model,genes,ko,rules,matrix,rxns,threshold)
        log_event("flux_exit", ko=labels,viable=bool(result[2]),
                  objective=round(float(result[0]),10))
        return result
    except BaseException as exc:
        FAILURE={"stage":"certified_flux",
                 "error":str(exc),"ko":labels,"ko_indices":list(ko)}
        log_event("failure",**FAILURE)
        try:
            extra=independent_raw_check(genes,ko,threshold)
            log_event("fresh_raw_lp",ko=labels,**extra)
        except BaseException as extra_error:
            log_event("diagnostic",diagnostic_error=repr(extra_error))
        raise


def traced_growth(model,genes,combo,rules,how):
    labels=[genes[i] for i in combo]
    tick=time.perf_counter()
    result=ORIGINAL_GROWTH(model,genes,combo,rules,how)
    log_event("oracle_growth",ko=labels,how=how,growth=float(result),
              duration_s=round(time.perf_counter()-tick,7))
    return result


def run(args):
    global OUT,SOURCE,FAILURE
    OUT=pathlib.Path(args.out)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    SOURCE=args.source
    frozen=r24.certified_frozen(args.manifest)
    family="unseen_sha_mix"
    genes=frozen["cohorts"][family][str(args.n)]
    manifest_digest=frozen["digest"]
    log_event("diagnostic",family=family,n=args.n,arm=args.arm,
              gene_sha=r9.hgenes(genes),frozen_digest=manifest_digest)
    try:
        with patch.object(r9,"certified_flux",traced_flux), \
             patch.object(r9,"growth",traced_growth):
            row=r24.run_arm(SOURCE,genes,args.arm,0,family,args.n,frozen)
    except BaseException as exc:
        text=str(exc)
        if FAILURE is None:
            FAILURE={"stage":"independent_fba_or_other",
                     "error":text}
        log_event("failure",**FAILURE)
        matched=EXPECTED[args.n] in text
        r24.save(OUT,{"protocol":"R24D-FORENSIC-STRICT-v1",
                      "complete":True,"outcome":"STRICT_FAILURE_REPRODUCED" if matched
                      else "UNEXPECTED_FAILURE",
                      "arm":args.arm,"n":args.n,"failure":FAILURE,
                      "expected_signature":EXPECTED[args.n],
                      "events":list(EVENTS),
                      "source_sha":r9.SOURCE_SHA,
                      "frozen_digest":manifest_digest})
        print("R24D_FINAL "+json.dumps({
              "arm":args.arm,"n":args.n,"failure":FAILURE,
              "expected_signature_reproduced":matched,
              "source_sha":r9.SOURCE_SHA,
              "result":"NOT_CERTIFIED"},sort_keys=True),flush=True)
        if not matched:
            raise
        return
    r24.save(OUT,{"protocol":"R24D-FORENSIC-STRICT-v1",
                  "complete":True,"outcome":"NO_FAILURE_REPRODUCED",
                  "arm":args.arm,"n":args.n,"source_sha":r9.SOURCE_SHA,
                  "frozen_digest":manifest_digest,
                  "events":list(EVENTS),
                  "wall_s_IGNORED_FOR_PERFORMANCE":row["wall_s"],
                  "independent_sound":row["independent_sound"]})
    print("R24D_FINAL "+json.dumps({
          "arm":args.arm,"n":args.n,"expected_signature_reproduced":False,
          "result":"ORIGINAL_ARM_COMPLETED_WITH_STRICT_VALIDATION",
          "not_a_performance_trial":True},sort_keys=True),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    for field in ("source","manifest","out"):
        parser.add_argument("--"+field,required=True)
    parser.add_argument("--n",type=int,choices=(192,384),required=True)
    parser.add_argument("--arm",choices=("r9_baseline","share_12_control"),required=True)
    args=parser.parse_args()
    try:
        run(args)
    except BaseException:
        traceback.print_exc()
        raise
