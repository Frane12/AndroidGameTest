#!/usr/bin/env python3
"""DRNAS Medical R26: replay the actual 34 R24D oracle calls without SAT.

Research-only diagnostic on a frozen bacterial metabolic model. The R9, R24
and R25 implementations are not edited; NO clinical, performance, or
biological-correctness certificate is conferred by this script.

The order below is copied from both R24D N384 logs (r9_baseline and
share_12_control), which independently recorded the same 34-call sequence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import pathlib
import time

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r24_regression_guard as r24

PROTOCOL = "DRNAS-MEDICAL-R26-R24D-ORACLE-HISTORY-v1"
SOURCE_SHA = r9.SOURCE_SHA
FAMILY = "unseen_sha_mix"
N = 384
EPS = 1e-6
REPEATS = 3
# Each element causes consecutive gene- and GPR-reaction-route calls.
# Empty string means the wild-type empty KO.
KOS = ("b0003", "", "b0004", "b0074", "b0096", "b0142",
       "b0166", "b0173", "b0182", "b0386", "b0414", "b0417",
       "b0420", "b0421", "b0522", "b0774", "b0777")
TRACE = tuple((tuple([g]) if g else tuple(), route)
              for g in KOS for route in ("gene", "reaction"))
assert len(TRACE) == 34 and TRACE[-2:] == ((("b0777",), "gene"),
                                           (("b0777",), "reaction"))

def load(source):
    model, meta = r8.load_frozen(source)
    if meta["SBML_sha256"] != SOURCE_SHA:
        raise RuntimeError("Wrong R9 SHA-locked iML1515 source")
    return model, r8.all_rules(model), float(meta["wildtype_biomass"])*.01

def state(model):
    """Observe the gene and reaction bounds; do not alter LP optimization."""
    bounds = [[r.id, float(r.lower_bound), float(r.upper_bound)]
              for r in model.reactions]
    genes = sorted(set(KOS)-{""})
    functional = [[g, bool(model.genes.get_by_id(g).functional)]
                  for g in genes]
    digest = lambda x: hashlib.sha256(
        json.dumps(x, separators=(",",":"), sort_keys=True).encode()
    ).hexdigest()
    return {"bounds_sha": digest(bounds), "gene_flags_sha": digest(functional)}

def one(source, mode, genes, rep):
    shared = shared_rules = shared_threshold = None
    if mode == "warm_history":
        shared, shared_rules, shared_threshold = load(source)
    events = []
    for idx, (knocked, route) in enumerate(TRACE):
        if mode == "cold_each_call":
            model, rules, threshold = load(source)
        else:
            model, rules, threshold = shared, shared_rules, shared_threshold
        indices = tuple(genes.index(g) for g in knocked)
        before = state(model)
        start = time.perf_counter()
        # Use precisely the R9/R24 independent-validation growth entrypoint.
        growth = float(r9.growth(model, genes, indices, rules, route))
        elapsed_s = time.perf_counter()-start
        after = state(model)
        if not math.isfinite(growth):
            raise RuntimeError("Nonfinite LP growth in R26 diagnostic")
        events.append({
            "index": idx, "ko": list(knocked), "route": route,
            "growth": growth, "seconds": round(elapsed_s,7),
            "bounds_restored": before["bounds_sha"]==after["bounds_sha"],
            "gene_flags_restored": before["gene_flags_sha"]==after["gene_flags_sha"],
            "before": before, "after": after,
        })
    if len(events) != len(TRACE):
        raise RuntimeError("Incomplete frozen R24D oracle trace")
    last = events[-2:]
    assert last[0]["route"] == "gene" and last[1]["route"] == "reaction"
    g, r = (x["growth"] for x in last)
    pair_mismatch = abs(g-r)>EPS
    threshold_classification_disagree = ((g>=threshold) != (r>=threshold))
    changed = [x["index"] for x in events if not
               (x["bounds_restored"] and x["gene_flags_restored"])]
    result = {"rep":rep, "events":events, "target_gene":g,
              "target_reaction":r, "growth_threshold":threshold,
              "target_difference":g-r, "target_mismatch":pair_mismatch,
              "threshold_disagreement":threshold_classification_disagree,
              "state_restoration_failures":changed,
              "historical_R24D_gene_growth":0.010227963222158323,
              "historical_R24D_reaction_growth":0.0,
              "historical_R24D_reproduced":
                  abs(g-0.010227963222158323)<=EPS and abs(r)<=EPS}
    print("R26_REP "+json.dumps({
        "mode":mode,"rep":rep,"target_gene":g,"target_reaction":r,
        "threshold_disagreement":threshold_classification_disagree,
        "state_restoration_failures":len(changed),
        "historical_R24D_reproduced":result["historical_R24D_reproduced"]
    },sort_keys=True),flush=True)
    return result

def run(args):
    frozen = r24.certified_frozen(args.manifest)
    genes = frozen["cohorts"][FAMILY][str(N)]
    if r9.hgenes(genes) != frozen["cohort_sha"][FAMILY][str(N)]:
        raise RuntimeError("Cohort SHA mismatch")
    if not set(KOS)-{""} <= set(genes):
        raise RuntimeError("Historical oracle KO missing from frozen cohort")
    model, _, threshold = load(args.source)
    if threshold <= 0 or "b0777" not in {g.id for g in model.genes}:
        raise RuntimeError("Wrong model or biomass threshold")
    start = time.perf_counter()
    reps = [one(args.source,args.mode,genes,i) for i in range(REPEATS)]
    result = {
        "protocol":PROTOCOL,"complete":True,"diagnostic_only":True,
        "medical_claim":False,"speedup_validated":False,
        "R24_correctness_validated":False,
        "source_sha":SOURCE_SHA,"frozen_digest":frozen["digest"],
        "cohort_sha":r9.hgenes(genes),"n":N,"family":FAMILY,
        "mode":args.mode,"repetitions":REPEATS,"original_calls":len(TRACE),
        "elapsed_diagnostic_s":round(time.perf_counter()-start,5),
        "runs":reps,
        "historical_trace_reproduced_count":sum(
            r["historical_R24D_reproduced"] for r in reps),
        "any_target_disagreement":any(r["target_mismatch"] for r in reps),
        "any_bounds_or_genes_leaked":any(
            r["state_restoration_failures"] for r in reps),
    }
    path = pathlib.Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("R26_FINAL "+json.dumps({k:result[k] for k in (
        "protocol","n","mode","repetitions","original_calls",
        "historical_trace_reproduced_count","any_target_disagreement",
        "any_bounds_or_genes_leaked","speedup_validated")},
        sort_keys=True),flush=True)

if __name__=="__main__":
    p = argparse.ArgumentParser()
    for name in ("source","manifest","out"):
        p.add_argument("--"+name,required=True)
    p.add_argument("--mode",choices=("warm_history","cold_each_call"),
                   required=True)
    run(p.parse_args())
