#!/usr/bin/env python3
"""DRNAS TA6: frozen, source-only structural router (experimental).

Two precommitted hypotheses, NOT established speedups:
- guarded: protect against small-source XOR and high-density partial XOR samples
  being sent to CMS when source-certified R28+Kissat may do better.
- r28_explore: broaden the R28 candidate region, with a risk of regressions.

Input features are produced by the unchanged TA3 bounded DIMACS scanner.
No SAT answer, prior-case identity, source URL, runtime, or benchmark label is
read during selection. All four downstream solvers are frozen original-CNF
executors; R28 is source-certified. The SHA-disjoint benchmark tests claims.
"""
from __future__ import annotations

import argparse
import json
import drnas_ta3_adaptive_selector as ta3

VALID = frozenset(("ta6_guarded", "ta6_r28_explore", "ta6_shadow"))
EXECUTORS = frozenset(("cms_plain", "cms_r28", "kissat_plain", "kissat_r28"))

def route(features: dict, mode: str):
    if mode not in VALID:
        raise ValueError("unknown TA6 mode " + str(mode))
    legacy, reason = ta3.decision(features, "ta2_portfolio")
    if legacy not in EXECUTORS:
        raise AssertionError("unsafe TA3 host")
    if mode == "ta6_shadow":
        return legacy, "shadow_same_as_TA3:" + reason

    xor3 = int(features["complete_xor3_templates_sample"])
    size = int(features["declared_clauses"])
    coverage = float(features["sample_fraction_clauses"])
    binary = float(features["binary_fraction"])
    long_clauses = float(features["long_clause_fraction"])
    horn = float(features["horn_clause_fraction"])
    skew = float(features["variable_occurrence_p90_over_median"])

    # Fully scanned, pure XOR: compare the exact same certified R28 wrapper
    # against both host backends (CMS and Kissat), rather than assuming CMS wins.
    pure_source = (size <= 2500 and coverage >= .95 and xor3 >= 6
                   and binary < .12 and long_clauses < .16)
    if pure_source:
        return "kissat_r28", "TA6_pure_source_XOR_Kissat_R28"

    # TA3's "any 2 XOR templates implies CMS" rule can misroute a large
    # source if only 512 leading clauses are sampled. Require strong, repeated
    # XOR evidence before risking a new R28 preprocessing route.
    if (size >= 2500 and xor3 >= 16 and coverage <= .10
            and binary < .40 and long_clauses < .40
            and horn < .95 and skew < 12):
        return "kissat_r28", "TA6_sparse_sample_strong_XOR_R28"

    if mode == "ta6_r28_explore":
        # Separate, explicitly exploratory hypothesis, never used by guarded.
        if (size >= 2500 and xor3 >= 4 and coverage <= .25
                and binary < .60 and long_clauses < .60):
            return "kissat_r28", "TA6_explore_partial_XOR_R28"
        if legacy == "kissat_plain" and xor3 >= 2 and coverage <= .25:
            return "kissat_r28", "TA6_explore_Kissat_R28"

    # Critical fallback: preserve previously audited TA3 decisions when there
    # is insufficient structural evidence, instead of always adding GF2.
    return legacy, "TA6_fallback_TA3:" + reason


def selftest():
    base = dict(declared_clauses=150000,
                sample_fraction_clauses=512/150000,
                complete_xor3_templates_sample=0,
                binary_fraction=.01,
                horn_clause_fraction=.45,
                long_clause_fraction=.02,
                variable_occurrence_p90_over_median=2)
    def case(**kw):
        return dict(base, **kw)

    tests = [
        (case(declared_clauses=1000, sample_fraction_clauses=1.0,
              complete_xor3_templates_sample=10), "ta6_guarded",
         "kissat_r28"),
        (case(complete_xor3_templates_sample=28,
              sample_fraction_clauses=.02), "ta6_guarded", "kissat_r28"),
        (case(complete_xor3_templates_sample=3,
              sample_fraction_clauses=.08), "ta6_guarded", "cms_plain"),
        (case(complete_xor3_templates_sample=3,
              sample_fraction_clauses=.08), "ta6_r28_explore", "cms_plain"),
        (case(complete_xor3_templates_sample=4,
              sample_fraction_clauses=.08), "ta6_r28_explore", "kissat_r28"),
        (case(binary_fraction=.80,
              complete_xor3_templates_sample=0), "ta6_guarded",
         "kissat_plain"),
        (case(declared_clauses=1000, sample_fraction_clauses=1.0,
              complete_xor3_templates_sample=10), "ta6_shadow", "cms_r28"),
    ]
    for features, mode, expected in tests:
        selected, _why = route(features, mode)
        assert selected == expected, (mode, expected, selected)
        assert selected in EXECUTORS
    try:
        route(base, "invalid")
        raise AssertionError("unknown mode accepted")
    except ValueError:
        pass
    print("TA6_SELECTOR_SELFTEST_PASS", json.dumps({
        "cases": len(tests), "modes": sorted(VALID),
        "source_features_only": True, "frozen_before_holdout": True}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("selftest",))
    args = ap.parse_args()
    selftest()
