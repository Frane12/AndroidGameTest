#!/usr/bin/env python3
"""Independent fail-closed R4 gate against frozen R3 biological result."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

EXPECTED_SHA="13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f"
EXPECTED={
    ("b2926",),("b1779",),("b2779",),("b1136",),("b0720",),("b2415",),
    ("b3919","b0767"),("b3919","b1852"),("b3919","b2029"),
    ("b3919","b4025"),("b3236","b3956"),("b0767","b4025"),
    ("b1852","b4025"),("b2029","b4025"),("b1818","b2417"),
    ("b1817","b2417"),("b3919","b3236","b0474"),
    ("b3919","b3236","b1702"),
}

def verify(d):
    if d["model_sha256"]!=EXPECTED_SHA:
        raise AssertionError("Real metabolic model changed from independently confirmed R3")
    oracle=d["independent_oracle"]
    if oracle["combinations"]!=5488 or oracle["minimal"]!=18:
        raise AssertionError("Wrong size / independent biological reference")
    if not oracle["gene_reaction_match"] or oracle["gpr_monotone_checks"]!=5488:
        raise AssertionError("Reference gene/reaction equivalence or monotonicity failed")
    got={frozenset(x) for x in oracle["minimal_ko_sets"]}
    if got!={frozenset(x) for x in EXPECTED}:
        raise AssertionError("18 R3-known minimal interventions changed")
    methods={"drnas_sat_structural_memo","gurobi_mip_lazy_memo"}
    if {t["method"] for t in d["trials"]}!=methods:
        raise AssertionError("MIP or SAT missing")
    if any(not t.get("complete") or t.get("crosscheck")!="PASS" or
           t.get("minimal_sets")!=18 for t in d["trials"]):
        raise AssertionError("Timeout or mismatch; no speedup conclusion permitted")
    if any(d["summaries"][m]["complete"]!=d["repeats"]
           or d["summaries"][m]["median_wall_s"] is None for m in methods):
        raise AssertionError("Missing paired repetitions")
    for t in d["trials"]:
        if t["method"]=="drnas_sat_structural_memo":
            if t["lp_calls"]!=716 or t["candidates"]!=2730:
                raise AssertionError("R3 control not identical")
        if t["method"]=="gurobi_mip_lazy_memo":
            if t["lp_calls"]<=0 or t["candidates"]>5488:
                raise AssertionError("Invalid MIP accounting")
    result=dict(status="PASS",model_sha256=EXPECTED_SHA,
                frozen_R3_minimal_gene_sets=18,
                independent_gene_KO_queries=5488,
                paired_repetitions=d["repeats"],
                mip_median_s=d["summaries"]["gurobi_mip_lazy_memo"]["median_wall_s"],
                sat_median_s=d["summaries"]["drnas_sat_structural_memo"]["median_wall_s"],
                scope="Gurobi vs PySAT CaDiCaL master for identical E coli GPR/FBA tasks, not native DRNAS or full gMISpy")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--summary",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    result=verify(json.loads(Path(a.summary).read_text()))
    target=Path(a.out)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DRNAS_GMISPY_R4_CERTIFIED_CROSSCHECK",json.dumps(result),flush=True)
