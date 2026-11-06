#!/usr/bin/env python3
"""Independent R5 audit: exact reference model, completeness, frozen R4 results."""
from __future__ import annotations
import argparse,json,itertools,hashlib
from pathlib import Path

FROZEN="13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f"
OLD18=[
 ["b2926"],["b1779"],["b2779"],["b1136"],["b0720"],["b2415"],
 ["b3919","b0767"],["b3919","b1852"],["b3919","b2029"],
 ["b3919","b4025"],["b3236","b3956"],["b0767","b4025"],
 ["b1852","b4025"],["b2029","b4025"],["b1818","b2417"],
 ["b1817","b2417"],["b3919","b3236","b0474"],
 ["b3919","b3236","b1702"]
]
METHODS={"sat_structural_memo","gurobi_lazy_master","gurobi_gpr_aware_mip"}

def verify(data):
    if data.get("sha256")!=FROZEN:
        raise AssertionError("Source metabolic model changed")
    genes=data["genes"]
    if not len(genes)==48 or len(set(genes))!=48 or len(data["added_genes"])!=16:
        raise AssertionError("Not frozen 48 gene enlargement")
    observed_genesets={frozenset(x) for x in data["exhaustive"]["minimal_sets"]}
    if not {frozenset(x) for x in OLD18}.issubset(observed_genesets):
        raise AssertionError("Known R3/R4 minimal intervention sets missing")
    N=len(genes)
    expected_candidates=sum(__import__("math").comb(N,k) for k in range(1,data["max_KO"]+1))
    exhaustive=data["exhaustive"]
    if expected_candidates!=18472 or exhaustive["cases"]!=expected_candidates:
        raise AssertionError("Incorrect exhaustive knockout coverage")
    if not exhaustive["gene_reaction_equivalence"] or exhaustive["lp_calls"]!=2*expected_candidates:
        raise AssertionError("Independent FBA knockout/reaction check incomplete")
    if exhaustive["monotone_checked"]!=expected_candidates:
        raise AssertionError("GPR rule monotonicity proof missing")
    if len(observed_genesets)!=len(exhaustive["minimal_sets"]):
        raise AssertionError("Duplicate minimal gene sets in reference")
    for a,b in itertools.combinations(observed_genesets,2):
        if a.issubset(b) or b.issubset(a):
            raise AssertionError("Found non-inclusion-minimal gene knockout set")
    if set(data["methods"])!=METHODS:
        raise AssertionError("Missing required external MIP or SAT arm")
    if len(data["trials"])!=len(METHODS)*data["repeats"]:
        raise AssertionError("Missing paired repetitions")
    for method in METHODS:
        runs=[t for t in data["trials"] if t["method"]==method]
        if {t["repeat"] for t in runs}!=set(range(data["repeats"])):
            raise AssertionError("Repeated same seed without matching all repetitions")
        if any(not r["complete"] or r.get("crosscheck")!="PASS" or
               r.get("minimal_sets")!=len(observed_genesets) for r in runs):
            raise AssertionError("Incomplete solver or mismatched reference")
        if not data["methods"][method]["complete"]:
            raise AssertionError("Missing complete method aggregate")
        if any(r["lp_calls"]<=0 or r["lp_calls"]>r["candidates"]
               or r["candidates"]>expected_candidates for r in runs):
            raise AssertionError("Invalid FBA/MIP count")
    return {
        "status":"PASS","frozen_model_sha256":FROZEN,
        "total_genes":N,"exhaustively_verified_KO_sets":expected_candidates,
        "independently_verified_FBA_gene_vs_reaction":2*expected_candidates,
        "minimal_gene_KO_sets":len(observed_genesets),
        "R3_R4_known_minimal_sets_preserved":len(OLD18),
        "repetitions_each":data["repeats"],
        "wall_medians_s":{m:data["methods"][m]["wall_s_median"] for m in sorted(METHODS)},
        "scope":"BiGG E coli GPR KO + shared GLPK oracle; neither native DRNAS nor entire gMISpy"
    }

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--summary",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    data=json.loads(Path(a.summary).read_text())
    result=verify(data)
    dest=Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DRNAS_MEDICAL_R5_CERTIFIED_CROSSCHECK",json.dumps(result,sort_keys=True),flush=True)
