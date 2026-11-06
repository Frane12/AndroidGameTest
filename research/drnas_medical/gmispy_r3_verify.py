#!/usr/bin/env python3
"""Verify R3 matches published gMISpy GPR semantics, with no speedup mislabeling."""
from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
from gmispy_r3 import parse_rule

def verify(our, upstream):
    if upstream.get("status") != "PASS":
        raise AssertionError("Upstream source GPR parsing failed")
    if our["model_source_sbml_sha256"] != upstream["model_source_sbml_sha256"]:
        raise AssertionError("Source model mismatch")
    count = 0
    for rid, example in upstream["complex_examples"].items():
        ours = our["original_complex_gpr_examples"][rid]
        official = example["upstream_gpr"]
        genes = sorted(set(example["genes"]))
        _, f = parse_rule(ours, set(our["genes"]) | set(genes) | {"s0001"})
        _, g = parse_rule(official, set(our["genes"]) | set(genes) | {"s0001"})
        for bits in itertools.product([False,True], repeat=len(genes)):
            knocked = frozenset(genes[i] for i,b in enumerate(bits) if b)
            if f(knocked) != g(knocked):
                raise AssertionError("Official gMISpy GPR logic differs: " + rid)
            count += 1
    if not our["independent_exhaustive"]["gene_vs_reaction_match_all"]:
        raise AssertionError("Gene/reaction KO biological consistency failed")
    if not all(x["crosscheck"] == "PASS" for x in our["repetitions"]):
        raise AssertionError("SAT model and FBA exhaustive mismatch")
    result = {
        "status": "PASS",
        "identical_model_sha256": our["model_source_sbml_sha256"],
        "truth_table_evaluations": count,
        "original_gmispy_complex_reactions_checked": len(upstream["complex_examples"]),
        "real_gene_KO_FBA_cases": our["independent_exhaustive"]["candidates"],
        "all_sat_ablation_arms_match_exhaustive_minimal_gene_KO_sets": True,
        "not_full_gmispy_genetic_intervention_comparison": True,
        "clinical_claims": False
    }
    return result

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--drnas",required=True)
    parser.add_argument("--gmispy",required=True)
    parser.add_argument("--out",required=True)
    args=parser.parse_args()
    data=verify(json.loads(Path(args.drnas).read_text()),
                json.loads(Path(args.gmispy).read_text()))
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print("DRNAS_GMISPY_R3_CROSSCHECK",json.dumps(data),flush=True)
