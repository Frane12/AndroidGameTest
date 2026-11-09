#!/usr/bin/env python3
"""DRNAS MRE X6 — exact clause-order offset-dose causal test.

Reuses the frozen four X4 original SHA sources, native CryptoMiniSat binary,
paired source seeds, original witness replay, strict PAR2 and bounded checkpoints.
Only the placement of second-and-later exact-canonical duplicate clauses changes.
This is DEVELOPMENT mechanism localization, NOT globally blind validation.
"""
import argparse
import collections
import json
import pathlib

import mre_x4_early_divergence as x4
import mre_x3_spread_mechanism as x3

BASE_TRANSFORM = x4.transform
PROTO = "DRNAS-MRE-X6-SHIFT-OFFSET-8ARM-4SHA-4SEED-12S-v1"
MODES = (
    "original", "spread100", "shift1", "shift_half",
    "spread_shifted", "shift_double", "front100", "spread_reverse_copies"
)
BUDGETS = (10, 25, 100, 250, 1000, 5000)

def transform(clauses, mode):
    if mode in ("original", "spread100", "spread_shifted",
                "front100", "spread_reverse_copies"):
        return BASE_TRANSFORM(clauses, mode)
    x4.need(mode in ("shift1", "shift_half", "shift_double"),
            "unexpected X6 mode")
    duplicate_indices = set(x3.duplicates(clauses))
    if not duplicate_indices:
        return list(clauses)
    unique = [c for i, c in enumerate(clauses) if i not in duplicate_indices]
    duplicate = [c for i, c in enumerate(clauses) if i in duplicate_indices]
    gaps = [((i + 1) * (len(unique) + 1)) // (len(duplicate) + 1)
            for i in range(len(duplicate))]
    base_offset = max(1, len(unique) // (2 * (len(duplicate) + 1)))
    offset = {
        "shift1": 1,
        "shift_half": max(1, base_offset // 2),
        "shift_double": base_offset * 2,
    }[mode]
    changed = x4.interleave(
        unique, duplicate, [min(len(unique), p + offset) for p in gaps]
    )
    x4.need(collections.Counter(clauses) == collections.Counter(changed),
            "X6 clause multiset changed")
    return changed

def install():
    x4.PROTO = PROTO
    x4.OUT = pathlib.Path("mre_x6")
    x4.MODES = MODES
    x4.BUDGETS = BUDGETS
    x4.REAL_TRIALS = len(x4.CASES) * x4.REPS * len(MODES)
    x4.BOUNDED_TRIALS = x4.REAL_TRIALS * len(BUDGETS)
    x4.transform = transform

def print_x6_summary():
    path = x4.OUT / "report.json"
    r = json.loads(path.read_text())
    x4.need(r["protocol"] == PROTO and r["real_trials"] == 128
            and r["bounded_diagnostics"] == 768, "X6 final count invalid")
    source_dose = {}
    for c in x4.sources():
        _, clauses = x4.x2.parse(x3.source(c))
        duplicates = len(x3.duplicates(clauses))
        unique_count = len(clauses) - duplicates
        base_offset = max(1, unique_count // (2 * (duplicates + 1)))
        source_dose[c["gbd"]] = {
            "duplicates": duplicates,
            "shifted_base_offset": base_offset if duplicates else 0,
            "shift_half_offset": max(1, base_offset // 2) if duplicates else 0,
            "shift_double_offset": base_offset * 2 if duplicates else 0,
        }
    print("MRE_X6_FINAL", json.dumps({
        "protocol": PROTO,
        "source_count": r["source_count"],
        "real_trials": r["real_trials"],
        "bounded_not_PAR2": r["bounded_diagnostics"],
        "scores": r["score"],
        "per_source": r["per_source"],
        "first_aggregate_divergence": r["divergences"],
        "source_offset_doses": source_dose,
        "development_not_blind": True,
        "independent_UNSAT_LRAT": False,
        "no_auto_promotion": True
    }, sort_keys=True), flush=True)

def main():
    install()
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "freeze", "verify", "shard", "audit"))
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--native", default="mre_x6/bin/native")
    args = p.parse_args()
    if args.action == "selftest":
        x4.selftest()
        print("MRE_X6_SELFTEST_PASS", flush=True)
    elif args.action == "freeze":
        x4.freeze()
        print("MRE_X6_FREEZE_PASS", flush=True)
    elif args.action == "verify":
        x4.verify()
        print("MRE_X6_VERIFY_PASS", flush=True)
    elif args.action == "shard":
        x4.shard(args.shard, args.native)
        print("MRE_X6_SHARD_PASS", args.shard, flush=True)
    else:
        x4.audit()
        print_x6_summary()

if __name__ == "__main__":
    main()
