#!/usr/bin/env python3
"""DRNAS Medical R21: independently reload the frozen metabolic model for FBA oracle.

R20 established a reproducible GLPK simplex stall in share_12_control,
during verification of KO gene b0180 after 16 earlier successful LP checks.
R21 changes ONLY the oracle's in-memory model instance; candidate SAT/LP
search, original frozen cohort, original GPR definitions, and biological
gene/reaction verification remain identical to R16.
"""
from __future__ import annotations
import argparse
import faulthandler
import json
import pathlib
import sys
import time
from unittest.mock import patch

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r11_phenotype_cache as r11
import gmispy_r16_reaction_memo as r16

PROTOCOL = "DRNAS-MEDICAL-R21-INDEPENDENT-FRESH-GLPK-ORACLE-v1"
ORIGINAL_VERIFY = r9.verify_sets
ORIGINAL_GROWTH = r9.growth
START = time.perf_counter()
PATH = None
EVENTS = []
COUNTS = {"oracle_calls":0,"growth_checks":0}
SOURCE = None

def event(phase, **data):
    record = {"phase":phase, "elapsed_s":round(time.perf_counter()-START,6), **data}
    EVENTS.append(record)
    print("R21_PHASE " + json.dumps(record,sort_keys=True),flush=True)
    if PATH is not None:
        r16.save(PATH,{"protocol":PROTOCOL,"complete":False,"events":EVENTS})

def traced_growth(model,genes,combo,rules,how):
    COUNTS["growth_checks"] += 1
    chosen = tuple(genes[i] for i in combo)
    k = COUNTS["growth_checks"]
    event("oracle_lp_enter",seq=k,how=how,ko=chosen)
    start = time.perf_counter()
    value = ORIGINAL_GROWTH(model,genes,combo,rules,how)
    event("oracle_lp_exit",seq=k,how=how,ko=chosen,
          duration_s=round(time.perf_counter()-start,6),
          growth=round(float(value),10))
    return value

def independent_fresh_oracle(original_model, genes, rules, threshold, sols):
    COUNTS["oracle_calls"] += 1
    if COUNTS["oracle_calls"] != 1:
        raise RuntimeError("R21 requires one independent oracle per trial")
    event("fresh_oracle_load_enter",n_minimal_sets=len(sols))
    fresh_model, manifest = r8.load_frozen(SOURCE)
    fresh_rules = r8.all_rules(fresh_model)
    # The exact same published SBML model and GPR logic, different live GLPK
    # solver instance. Never use a model copied from the search solver state.
    if r8.dims(fresh_model) != r8.dims(original_model):
        raise RuntimeError("fresh model dimensions differ")
    a = sorted((rid, rule[0]) for rid,rule in fresh_rules.items())
    b = sorted((rid, rule[0]) for rid,rule in rules.items())
    if a != b:
        raise RuntimeError("independent GPR source differs")
    if abs(float(manifest["wildtype_biomass"])*.01-float(threshold)) > 1e-12:
        raise RuntimeError("frozen biomass threshold differs")
    event("fresh_oracle_load_exit",n_genes=len(genes),gpr_rules=len(a))
    with patch.object(r9,"growth",traced_growth):
        result = ORIGINAL_VERIFY(fresh_model,genes,fresh_rules,threshold,sols)
    if result.get("FBA_calls") != COUNTS["growth_checks"]:
        raise RuntimeError("oracle LP accounting mismatch")
    event("fresh_oracle_verified",independent_checks=result["independent_checks"],
          independent_LP=result["FBA_calls"],sound_minimal=result["sound_minimal"])
    return result

def main(args):
    global PATH,SOURCE
    PATH=pathlib.Path(args.out)
    PATH.parent.mkdir(parents=True,exist_ok=True)
    SOURCE=args.source
    event("frozen_source_load_enter",arm=args.arm)
    genes, expected = r11.frozen_reference(args.source,args.frozen,args.reference,args.n)
    model, manifest = r8.load_frozen(args.source)
    rules = r8.all_rules(model)
    threshold=float(manifest["wildtype_biomass"])*.01
    if len(genes) != args.n or args.n!=384:
        raise RuntimeError("wrong 384-gene cohort")
    event("frozen_source_load_exit",gene_sha=r9.hgenes(genes),
          reference_minima=len(expected),threshold=threshold)
    event("r16_original_trial_enter",arm=args.arm)
    with patch.object(r9,"verify_sets",independent_fresh_oracle):
        row=r16.trial(model,genes,rules,threshold,expected,args.arm,0,args.n)
    if not row["reference_match"] or not row["independent_FBA_sound"]:
        raise RuntimeError("R21 original biological reference failed")
    if COUNTS["oracle_calls"]!=1 or COUNTS["growth_checks"]!=170:
        raise RuntimeError("R21 original 170-query independent oracle incomplete")
    event("r21_trial_complete",arm=args.arm,
          wall_s=row["wall_s"],lp_requests=row["LP_requests"],
          physical_LP_calls=row["physical_LP_calls"],
          avoided=row["physical_LP_avoided"],
          fba_checks=COUNTS["growth_checks"])
    r16.save(PATH,{"protocol":PROTOCOL,"complete":True,"n":args.n,
                   "arm":args.arm,"events":EVENTS,"result":row})
    print("R21_PASS " + json.dumps({
        "arm":args.arm,"n":args.n,"wall_s":row["wall_s"],
        "LP_requests":row["LP_requests"],
        "physical_LP_calls":row["physical_LP_calls"],
        "physical_LP_avoided":row["physical_LP_avoided"],
        "independent_oracle_LP":COUNTS["growth_checks"],
        "reference_match":row["reference_match"]},sort_keys=True),flush=True)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True)
    p.add_argument("--frozen",required=True)
    p.add_argument("--reference",required=True)
    p.add_argument("--n",type=int,choices=(384,),required=True)
    p.add_argument("--arm",choices=("r9_baseline","share_12_control","share_12_memo_k3"),required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    faulthandler.enable()
    faulthandler.dump_traceback_later(45,repeat=True,file=sys.stderr)
    try:
        main(args)
    finally:
        faulthandler.cancel_dump_traceback_later()
