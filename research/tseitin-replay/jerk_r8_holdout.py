#!/usr/bin/env python3
"""Run a frozen 100-formula R8 holdout for timed conflict-trajectory signals.

This is a paired measurement experiment. It does not change solver policy.
The R7 signal is evaluated on a new formula set; forced restart and the frozen
R5 gate remain pre-existing comparators. Repeats are clustered by formula.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
from pathlib import Path

CATEGORIES = ("random3", "graphcolor", "xor", "external_satlib")
COUNT = 25
REPEATS = 3
MODES = ("stable_v1531", "monitor", "forced_restart25", "r5_frozen_gate")
SEED_REPLACEMENTS = {
    "seed=610000+i": "seed=710000+i",
    "seed=620000+i": "seed=720000+i",
    "seed=630000+i": "seed=730000+i",
}


def replace_once(source: str, old: str, new: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f"Frozen runner anchor mismatch ({n}): {old}")
    return source.replace(old, new, 1)


def replace_expected(source: str, old: str, new: str, expected: int) -> str:
    n = source.count(old)
    if n != expected:
        raise RuntimeError(f"Frozen runner anchor mismatch ({n}, expected {expected}): {old}")
    return source.replace(old, new)


def canonical_sha(runner, n: int, clauses) -> str:
    raw = (f"p cnf {n} {len(clauses)}\n" +
           "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)).encode()
    return runner.sha(raw)


def known_formula_hashes(path: Path) -> set[str]:
    if not path.is_file():
        raise FileNotFoundError(f"Required cumulative formula registry missing: {path}")
    with path.open(newline="") as f:
        rows = csv.DictReader(f)
        if "formula_sha256" not in (rows.fieldnames or []):
            raise RuntimeError("Formula registry lacks formula_sha256 column")
        result = {r["formula_sha256"].strip() for r in rows
                  if r.get("formula_sha256", "").strip()}
    if not result:
        raise RuntimeError("Formula registry contains no existing formula hashes")
    return result


def fresh_satlib_cases(runner, out: Path, seen: set[str]):
    root = Path("/tmp/satlib-r6/testdata/satlib")
    families = (
        ("sat-flat125-301", "SAT", 7),
        ("sat-uniform-20-91", "SAT", 6),
        ("unsat-uniform-50-218", "UNSAT", 12),
    )
    selected = []
    for family, expected, wanted in families:
        folder = root / family
        if not folder.is_dir():
            raise FileNotFoundError(f"Pinned SATLIB family missing: {folder}")
        candidates = []
        for source_path in sorted(folder.glob("*.cnf")):
            raw, n, clauses = runner.normalize_satlib(source_path)
            digest = canonical_sha(runner, n, clauses)
            if digest in seen:
                continue
            relative = source_path.relative_to(root).as_posix()
            order_key = hashlib.sha256(relative.encode()).hexdigest()
            candidates.append((order_key, relative, raw, n, clauses, digest))
        candidates.sort()
        if len(candidates) < wanted:
            raise RuntimeError(
                f"Not enough hash-new SATLIB formulas in {family}: "
                f"need {wanted}, found {len(candidates)}")
        for _, relative, raw, n, clauses, digest in candidates[:wanted]:
            selected.append((family, expected, relative, raw, n, clauses, digest))

    cases = []
    for i, (family, expected, relative, raw, n, clauses, digest) in enumerate(selected):
        case = runner.emit_cnf(
            out, f"satlib_holdout_{i:02d}.cnf", n, clauses, expected,
            "external_hash_new_public", "mitchellh/go-sat SATLIB",
            runner.PIN_SATLIB,
            {"upstream_relative_path": relative,
             "upstream_family": family,
             "raw_source_sha256": runner.sha(raw),
             "canonical_formula_sha256": digest,
             "excluded_from_existing_registry": True,
             "global_unseen_claim": False})
        if case["formula_sha256"] != digest or digest in seen:
            raise RuntimeError("SATLIB holdout hash audit failed")
        cases.append(case)
    if len(cases) != COUNT or len({c["formula_sha256"] for c in cases}) != COUNT:
        raise RuntimeError("SATLIB holdout is not 25 unique formulas")
    return cases


def load_runner(path: Path):
    source = path.read_text()
    for old, new in SEED_REPLACEMENTS.items():
        source = replace_once(source, old, new)
    source = replace_expected(source, "for i in range(10):", "for i in range(25):", 3)
    source = replace_once(
        source,
        'if len(cases)!=10 or len({c["formula_sha256"] for c in cases})!=10:',
        'if len(cases)!=25 or len({c["formula_sha256"] for c in cases})!=25:')
    source = replace_once(
        source,
        'if len(rows)!=120:',
        'if len(rows)!=len(cases)*REPEATS*len(MODES):')
    spec = importlib.util.spec_from_loader("r6_holdout_runner", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    module.__name__ = "r6_holdout_runner"
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", type=Path, required=True)
    ap.add_argument("--category", choices=CATEGORIES, required=True)
    ap.add_argument("--seen-hashes", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    runner = load_runner(args.runner)
    seen = known_formula_hashes(args.seen_hashes)
    runner.REPEATS = REPEATS
    runner.CAP = 8
    runner.OUT = args.out
    runner.MODES = MODES
    runner.CATEGORIES = CATEGORIES
    runner.ORIGINAL = Path("/tmp/kissat-r8-original/build/kissat")
    runner.PATCHED = Path("/tmp/kissat-r8-patched/build/kissat")
    runner.STABLE = Path("/tmp/drnas-r8-v1531")
    if args.category == "external_satlib":
        runner.external_cases = lambda out: fresh_satlib_cases(runner, out, seen)

    args.out.mkdir(parents=True, exist_ok=True)
    protocol = {
        "name": "DRNAS Jerk R8 hash-new paired holdout",
        "role": "confirmatory predictive-association test; no active Jerk gate",
        "categories": list(CATEGORIES),
        "formulas_per_category": COUNT,
        "formula_total": COUNT * len(CATEGORIES),
        "repeats_per_formula": REPEATS,
        "strategies": list(MODES),
        "timeout_seconds": runner.CAP,
        "generated_seed_bases": {"random3": 710000, "graphcolor": 720000,
                                  "xor": 730000},
        "external_formula_source": runner.PIN_SATLIB,
        "external_selection": "25 SATLIB formulas with canonical hashes absent from the cumulative formula registry",
        "registry_sha256": runner.sha(args.seen_hashes.read_bytes()),
        "primary_signal": "R7 timed conflict-count jerk absolute normalized magnitude through 2048 conflicts",
        "primary_effect": "paired formula-level PAR-2 gain of forced_restart25 versus monitor",
        "analysis_unit": "formula; three repeats are summarized within formula",
        "threshold_tuning": "none on holdout",
        "official_competition_claim": False,
        "global_unseen_claim_for_public_satlib": False,
    }
    (args.out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    runner.run_shard(args.category)


if __name__ == "__main__":
    main()
