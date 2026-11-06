#!/usr/bin/env python3
"""Fail-closed independent comparison of R2 original gMISpy and DRNAS minimal KO sets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def verify(reference, original):
    if reference["source_model_sha256"] != original["model_sha256"]:
        raise AssertionError("Different underlying SBML models")
    if reference.get("minimal_cut_sets_match") is not True:
        raise AssertionError("Independent DRNAS-vs-exhaustive reference did not pass")
    if original.get("status") != "PASS":
        raise AssertionError("Upstream gMISpy did not finish successfully")
    selected = reference["selected_one_to_one_gene_reaction_pairs"]
    selected_reactions = {item["reaction"] for item in selected}
    a = {frozenset(sol) for sol in reference["minimal_growth_blocking_KO_sets"]}
    b = set()
    for sol in original["solutions"]:
        if not set(sol["reactions"]).issubset(selected_reactions):
            raise AssertionError("Upstream solution exceeds frozen reaction set")
        if not 0 < len(sol["genes"]) <= 2:
            raise AssertionError("Unexpected solution size")
        if sol["verified_growth"] >= reference["lethal_threshold_absolute"]:
            raise AssertionError("Upstream solution does not block biomass")
        b.add(frozenset(sol["genes"]))
    if a != b:
        raise AssertionError("Solution sets disagree: only_DRNAS=" + str(sorted(map(sorted,a-b))) +
                             " only_original=" + str(sorted(map(sorted,b-a))))
    return {"status": "PASS", "source_model_sha256": reference["source_model_sha256"],
            "exact_matching_intervention_sets": len(a),
            "reference_enumeration_candidates": reference["reference"]["cases"],
            "drnas_tested_candidates": reference["drnas"]["candidate_cases"],
            "gmispy_upstream_solution_sets": len(b),
            "scope": "real E coli GPR/MCS, not regulatory-cyclic gMISpy or cancer"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--drnas", required=True)
    p.add_argument("--gmispy", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    r = verify(json.loads(Path(args.drnas).read_text()),
               json.loads(Path(args.gmispy).read_text()))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r,indent=2,sort_keys=True) + "\n")
    print("DRNAS_GMISPY_R2_EXACT_CROSSCHECK", json.dumps(r), flush=True)
