#!/usr/bin/env python3
"""Independent audit of true gMCSpy vs SAT same gene KO problem, no fake wins."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

EXPECTED_SHA="13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f"
R5_SET=[["b2926"],["b1779"],["b2779"],["b1136"],["b0720"],["b2415"],
["b3919","b0767"],["b3919","b1852"],["b3919","b2029"],["b3919","b4025"],
["b3236","b3956"],["b0767","b4025"],["b1852","b4025"],["b2029","b4025"],
["b1818","b2417"],["b1817","b2417"],["b3919","b3236","b0474"],
["b3919","b3236","b1702"],
["b2417","b1819"],["b0115","b0904","b2492"],["b0114","b0904","b2492"],
["b0116","b0904","b2492"],["b0118","b1276"],["b2416"],["b2465","b2935"]]

def audit(cohort):
    if cohort["source_model_sha256"]!=EXPECTED_SHA:
        raise AssertionError("Source model changed")
    n=cohort["cohort"]
    genes=cohort["genes"]
    if n not in (48,64) or len(genes)!=n or len(set(genes))!=n:
        raise AssertionError("Wrong gene cohort")
    if not all(g.startswith("b") and len(g)==5 and g[1:].isdigit() for g in genes):
        raise AssertionError("Non-genetic KO target")
    oracle=cohort["exhaustive"]
    count=18472 if n==48 else 43744
    if oracle["candidate_KO_sets"]!=count or oracle["monotone_checked"]!=count or oracle["gene_and_reaction_FBA_calls"]!=2*count:
        raise AssertionError("Independent gene-reaction FBA benchmark incomplete")
    expected={frozenset(s) for s in oracle["minimal_solutions"]}
    if not {frozenset(s) for s in R5_SET}.issubset(expected):
        raise AssertionError("Earlier R5 certified minimal gene sets disappeared")
    trials=cohort["repetitions"]
    if len(trials)!=6:
        raise AssertionError("Missing 3 repeats of 2 solver arms")
    sat=[x for x in trials if x["method"]=="drnas_architecture_sat_glpk"]
    original=[x for x in trials if x["method"]=="published_gMCSpy_staged_lazy"]
    if len(sat)!=3 or len(original)!=3 or set(t["repeat"] for t in sat)!=set(range(3)):
        raise AssertionError("Missing paired runs")
    if any(not t["all_solutions_verified"] or t["minimal_sets"]!=len(expected) for t in sat):
        raise AssertionError("SAT failed frozen independent oracle")
    for t in original:
        if t.get("status")=="returned":
            actual={frozenset(s) for s in t["solutions"]}
            for item in actual:
                if not item.issubset(set(genes)):
                    raise AssertionError("Published solver returned KO outside cohort")
                if len(item)>3:
                    raise AssertionError("Published solver violated size cap")
            if actual-expected:
                raise AssertionError("Original gMCSpy produced KO not viable in our independent oracle")
    can_compare=(all(t["all_solutions_verified"] for t in original) and
                 cohort["complete_comparable"] and
                 all(cohort["median_wall_s"].get(m) is not None
                     for m in ("drnas_architecture_sat_glpk","published_gMCSpy_staged_lazy")))
    return dict(cohort=n,source_hash=EXPECTED_SHA,reference_combinations=count,
                independent_FBA_pairs=count,correct_minimal_sets=len(expected),
                SAT_correct=True,gMCSpy_correct_and_complete=can_compare,
                published_gMCSpy_status=[t.get("status") for t in original],
                median_s=cohort["median_wall_s"] if can_compare else None,
                certified_speed_comparison=can_compare,
                caution=None if can_compare else
                    "No gMCSpy versus SAT speed claim: solver not complete/semantically equivalent.",
                scientific_scope="real E coli gene MCS / GPR; no clinical data or native DRNAS")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--cohort48",required=True)
    p.add_argument("--cohort64",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    info=[audit(json.loads(Path(f).read_text()))
          for f in (a.cohort48,a.cohort64)]
    result=dict(status="PASS_REFERENCE_AND_SAT",cohorts=info,
                paired_gMCSpy_speed_claim_allowed=all(x["certified_speed_comparison"] for x in info))
    path=Path(a.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DRNAS_MEDICAL_R6_AUDIT",json.dumps(result,sort_keys=True),flush=True)
