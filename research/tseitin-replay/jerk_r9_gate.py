#!/usr/bin/env python3
"""Run the frozen R9 opt-in Jerk-gate holdout."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from jerk_r8_holdout import fresh_satlib_cases, known_formula_hashes, replace_once

CATEGORIES = ("random3", "graphcolor", "xor", "external_satlib")
COUNT = 25
REPEATS = 3
MODES = ("stable_v1531", "monitor", "forced_restart25",
         "r5_frozen_gate", "jerk_gate")
THRESHOLD = 0.0105088239760238
SEEDS = {
    "seed=610000+i": "seed=810000+i",
    "seed=620000+i": "seed=820000+i",
    "seed=630000+i": "seed=830000+i",
}


def replace_expected(source: str, old: str, new: str, expected: int) -> str:
    n = source.count(old)
    if n != expected:
        raise RuntimeError(f"R9 frozen runner anchor mismatch ({n}/{expected}): {old}")
    return source.replace(old, new)


def load_runner(path: Path):
    source = path.read_text()
    for old, new in SEEDS.items():
        source = replace_once(source, old, new)
    source = replace_expected(source, "for i in range(10):",
                              "for i in range(25):", 3)
    source = replace_once(
        source,
        'if len(cases)!=10 or len({c["formula_sha256"] for c in cases})!=10:',
        'if len(cases)!=25 or len({c["formula_sha256"] for c in cases})!=25:')
    source = replace_once(
        source,
        'if len(rows)!=120:',
        'if len(rows)!=len(cases)*REPEATS*len(MODES):')
    source = replace_once(
        source,
        '"R5_EARLY","DRNAS_V177_SWITCH","DRNAS_V177_FINAL"',
        '"R5_EARLY","DRNAS_JERK_GATE","DRNAS_V177_SWITCH","DRNAS_V177_FINAL"')
    source = replace_once(
        source,
        'gate=labels.get("R5_EARLY",{})',
        'gate=labels.get("DRNAS_JERK_GATE",labels.get("R5_EARLY",{}))')
    old_mode_block = '''        env["DRNAS_V177_MODE"]={
            "monitor":"r5_monitor",
            "forced_restart25":"switch2048",
            "r5_frozen_gate":"r5_gate"}[mode]
        command=[str(PATCHED),"-s",str(case["path"].resolve())]'''
    new_mode_block = '''        env["DRNAS_V177_MODE"]={
            "monitor":"r5_monitor",
            "forced_restart25":"switch2048",
            "r5_frozen_gate":"r5_gate",
            "jerk_gate":"r5_monitor"}[mode]
        if mode=="jerk_gate":
            env["DRNAS_JERK_GATE"]="1"
        command=[str(PATCHED),"-s",str(case["path"].resolve())]'''
    source = replace_once(source, old_mode_block, new_mode_block)
    source = replace_once(
        source,
        'freeze="4 strategies fixed before R6; D uses prior R5 frozen gate, never fitted on R6",',
        'freeze="R9 Jerk median gate frozen from R7 calibration; R9 formulas never used to fit threshold",')
    spec = importlib.util.spec_from_loader("r6_r9_gate_runner", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    module.__name__ = "r6_r9_gate_runner"
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--seen-hashes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    runner = load_runner(args.runner)
    seen = known_formula_hashes(args.seen_hashes)
    runner.REPEATS = REPEATS
    runner.CAP = 8
    runner.OUT = args.out
    runner.MODES = MODES
    runner.CATEGORIES = CATEGORIES
    runner.ORIGINAL = Path("/tmp/kissat-r9-original/build/kissat")
    runner.PATCHED = Path("/tmp/kissat-r9-patched/build/kissat")
    runner.STABLE = Path("/tmp/drnas-r9-v1531")
    if args.category == "external_satlib":
        runner.external_cases = lambda out: fresh_satlib_cases(runner, out, seen)

    args.out.mkdir(parents=True, exist_ok=True)
    protocol = {
        "name": "DRNAS Jerk R9 opt-in median gate holdout",
        "role": "experimental policy validation; default solver policy unchanged",
        "categories": list(CATEGORIES),
        "formulas_per_category": COUNT,
        "formula_total": COUNT * len(CATEGORIES),
        "repeats_per_formula": REPEATS,
        "strategies": list(MODES),
        "timeout_seconds": runner.CAP,
        "generated_seed_bases": {"random3": 810000, "graphcolor": 820000,
                                  "xor": 830000},
        "external_formula_source": runner.PIN_SATLIB,
        "external_selection": "25 SATLIB formulas with canonical hashes absent from the cumulative registry",
        "registry_sha256": runner.sha(args.seen_hashes.read_bytes()),
        "jerk_gate": {
            "enabled_only_for_mode": "jerk_gate",
            "input": "wall-time trajectory at pinned conflicts 32 through 2048; runtime checkpoints above 2048 are excluded even when the loop reports the 2048 mark at 2049",
            "metric": "mean absolute third finite difference of 11 equal-time interpolates, normalized by conflict growth",
            "threshold": THRESHOLD,
            "threshold_source": "median of formula medians among 13 complete R7 calibration formulas",
            "decision": "if metric >= frozen threshold, request restart interval 25 at the 2048 checkpoint; due to loop ordering the first applicable check may report conflict 2049",
            "decision_direction_from": "R7 development pilot only; R8 holdout not used in threshold fitting",
            "default_behavior": "unchanged unless DRNAS_JERK_GATE=1 is explicitly set for the jerk_gate strategy",
        },
        "analysis_unit": "formula; three repeats summarized within formula",
        "official_competition_claim": False,
    }
    (args.out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    runner.run_shard(args.category)


if __name__ == "__main__":
    main()
