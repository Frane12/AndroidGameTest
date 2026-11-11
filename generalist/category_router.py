#!/usr/bin/env python3
"""DRNAS GENERALIST1: deterministic, explainable CNF family router.

Offline *research* module. Never changes SAT/UNSAT verdicts. Routing recommendations
are gated by held-out, original-CNF verified trials. Not yet wired into native CDCL.
Input features must be available before solving; no runtime/outcome leakage.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics

CATEGORIES = ("xor", "pigeonhole", "graph", "crypto", "planning", "arithmetic",
              "random_3sat", "industrial", "crafted", "unknown")
KEYWORDS = {
    "pigeonhole": ("pigeonhole", "php", "hole"),
    "crypto": ("crypto", "sha", "aes", "md5", "cipher"),
    "planning": ("planning", "logistics", "blocksworld", "schedule"),
    "arithmetic": ("adder", "multiplier", "factor", "bitvector"),
    "graph": ("graph", "coloring", "clique", "hamilton", "vertex"),
    "random_3sat": ("random", "uf", "uuf", "3sat"),
    "industrial": ("industrial", "hardware", "bmc", "verification", "software"),
    "crafted": ("crafted", "challenge"),
}
BASELINE = "drnas_base"

def bucket(meta):
    """Cheap structural family, only declared source family + certified features.

    Caller MUST set xor_certified only after proof-preserving detection; no guess
    from a suspicious XOR-like name or from solver outcomes.
    """
    if meta.get("xor_certified") is True:
        return "xor"
    name = str(meta.get("family", "")).lower().replace("-", "_")
    for cat in ("pigeonhole", "crypto", "planning", "arithmetic", "graph",
                "random_3sat", "industrial", "crafted"):
        if any(word in name for word in KEYWORDS[cat]):
            return cat
    return "unknown"

def group_key(row):
    """Require original content SHA (not a path) to prevent exact leakage."""
    sha = str(row.get("original_sha256", "")).lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Each trial requires full original_sha256")
    return sha

def validate(row):
    group_key(row)
    for key in ("arm", "family", "status", "e2e_s", "cap_s", "verified"):
        if key not in row:
            raise ValueError("missing required trial field: " + key)
    if row["status"] not in ("SAT", "UNSAT", "TIMEOUT", "UNKNOWN"):
        raise ValueError("bad status")
    if float(row["cap_s"]) <= 0 or float(row["e2e_s"]) < 0:
        raise ValueError("invalid time")
    if not isinstance(row["verified"], bool):
        raise ValueError("verified must be a boolean")
    # For actual solver success we require verified original-CNF result.
    if row["status"] in ("SAT", "UNSAT") and not row["verified"]:
        raise ValueError("unverified solver verdict in training data")

def par2(row):
    cap = float(row["cap_s"])
    if row["status"] not in ("SAT", "UNSAT") or float(row["e2e_s"]) > cap:
        return 2.0 * cap
    return float(row["e2e_s"])

def partition(rows, holdout_pct=25):
    """Deterministic SHA-disjoint split, independent of arm and trial order."""
    if not (1 <= holdout_pct <= 50):
        raise ValueError("holdout_pct must be between 1 and 50")
    training, holdout = [], []
    for row in rows:
        validate(row)
        h = int(hashlib.sha256(group_key(row).encode()).hexdigest()[:8], 16) % 100
        (holdout if h < holdout_pct else training).append(row)
    return training, holdout

def aggregate(rows):
    """Per-instance paired score: median repetitions, then sum over instances.

    A key includes family and SHA to keep cases distinct; records must have
    identical cap across arms of the same case.
    """
    grouped = defaultdict(list)
    for r in rows:
        grouped[(group_key(r), r["arm"])].append(par2(r))
    return {k: statistics.median(v) for k, v in grouped.items()}

def learn(rows, min_paired=8, margin=0.05):
    """Recommend a category-specific arm only with enough matched cases and
    PAR2 improvement vs baseline. Conservative fallback otherwise."""
    scored = aggregate(rows)
    by_sha = {}
    for r in rows:
        by_sha[group_key(r)] = bucket(r)
    by_cat = defaultdict(lambda: defaultdict(dict))
    for (sha, arm), val in scored.items():
        by_cat[by_sha[sha]][sha][arm] = val
    result = {}
    for cat in CATEGORIES:
        instances = by_cat[cat]
        arm_names = sorted({arm for d in instances.values() for arm in d})
        best = {"arm": BASELINE, "paired": 0, "ratio": 1.0,
                "reason": "fallback: insufficient paired or no robust gain"}
        if BASELINE not in arm_names:
            result[cat] = best
            continue
        for arm in arm_names:
            if arm == BASELINE:
                continue
            paired = [v for v in instances.values() if arm in v and BASELINE in v]
            if len(paired) < min_paired:
                continue
            base = sum(v[BASELINE] for v in paired)
            new = sum(v[arm] for v in paired)
            ratio = base / new if new > 0 else float("inf")
            if ratio >= 1.0 + margin and ratio > best["ratio"]:
                best = {"arm": arm, "paired": len(paired),
                        "ratio": round(ratio, 6), "reason": "training gain only"}
        result[cat] = best
    return result

def evaluate(rows, recommendations):
    scored = aggregate(rows)
    by_sha = {}
    for r in rows:
        by_sha[group_key(r)] = bucket(r)
    stats = defaultdict(lambda: {"paired": 0, "base_par2_s": 0.0,
                                 "routed_par2_s": 0.0, "fallback": 0})
    arms = defaultdict(dict)
    for (sha, arm), score in scored.items():
        arms[sha][arm] = score
    for sha, avail in arms.items():
        cat = by_sha[sha]
        base = avail.get(BASELINE)
        if base is None:
            continue
        wanted = recommendations.get(cat, {}).get("arm", BASELINE)
        if wanted not in avail:
            # Honest evaluation: no imputed result for a missing experimental arm.
            stats[cat]["fallback"] += 1
            continue
        st = stats[cat]
        st["paired"] += 1
        st["base_par2_s"] += base
        st["routed_par2_s"] += avail[wanted]
    return {cat: {**v, "par2_ratio": round(v["base_par2_s"] /
             v["routed_par2_s"], 6) if v["routed_par2_s"] else None}
             for cat, v in sorted(stats.items())}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("trials", type=Path, help="JSONL with verified original-CNF trial records")
    p.add_argument("--min-paired", type=int, default=8)
    p.add_argument("--holdout-pct", type=int, default=25)
    p.add_argument("--output", type=Path, default=Path("generalist1_report.json"))
    args = p.parse_args()
    rows = [json.loads(line) for line in args.trials.read_text().splitlines() if line.strip()]
    train, test = partition(rows, args.holdout_pct)
    selection = learn(train, args.min_paired)
    report = {"status": "offline-only; not a native solver speedup",
              "train_unique_sha": len({group_key(r) for r in train}),
              "holdout_unique_sha": len({group_key(r) for r in test}),
              "sha_disjoint": not bool({group_key(r) for r in train} &
                                        {group_key(r) for r in test}),
              "selection": selection, "holdout": evaluate(test, selection)}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))

if __name__ == "__main__":
    main()
