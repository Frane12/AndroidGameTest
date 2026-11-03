#!/usr/bin/env python3
"""DRNAS R23: pre-solve structural-link risk selector in SHADOW mode.

Frozen historical training: R21 development formulas only. R21 test formulas
are untouched holdout. Uses same-binary native monitor versus forced restart
from archived R21 measured outcomes, NEVER re-runs solvers or changes Kissat.
Produces a candidate model and an audit; deployment requires prospective trials.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import tempfile
from collections import Counter, defaultdict, deque
from itertools import combinations
from pathlib import Path

ROOT = Path("experiments/drnas_v16")
CATALOG = ROOT / "r21-results/current/formula_features.csv"
OUT = Path("drnas-r23-results")
FEATURES = (
    "degree_cv", "polarity_bias", "hub_top10", "pair_reuse",
    "pair_sign_diversity", "cross_quartile_edges", "mean_twohop",
    "twohop_variance", "clause_repeated_varpair", "positive_negative_neighbor_overlap",
)
SEED_BASE = 2121210000
DENSITY = 4.23
MIN_NEIGHBORS = 7
K = 7
GAIN_FLOOR = .05
SAFE_WIN_FRACTION = 6 / 7
MIN_MEAN_GAIN = .10
MAX_SIMILARITY_DISTANCE = 3.5
# All gates above are fixed prior to inspecting R21 test outcomes.


def git_blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\\0" + data).hexdigest()


def read_dimacs(path: Path):
    n = 0
    clauses = []
    for raw in path.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("c"):
            continue
        if s.startswith("p "):
            words = s.split()
            assert words[1] == "cnf"
            n = int(words[2])
            continue
        ints = [int(z) for z in s.split()]
        assert ints and ints[-1] == 0
        clauses.append(ints[:-1])
    assert n > 0 and clauses
    return n, clauses


def binary_implication_graph(clauses):
    result = defaultdict(set)
    for clause in clauses:
        if len(clause) == 2:
            a, b = clause
            result[-a].add(b)
            result[-b].add(a)
    return result


def max_distance(graph, start):
    seen = {start: 0}
    pending = deque([start])
    while pending:
        node = pending.popleft()
        for nxt in graph.get(node, ()):
            if nxt not in seen:
                seen[nxt] = seen[node] + 1
                pending.append(nxt)
    return max(seen.values())


def self_test():
    # Exactly four binary implications: linear versus branching.
    chain = [[-1, 2], [-2, 3], [-3, 4], [-4, 5]]
    star = [[-1, 2], [-1, 3], [-1, 4], [-1, 5]]
    assert len(chain) == len(star) == 4
    assert max_distance(binary_implication_graph(chain), 1) == 4
    assert max_distance(binary_implication_graph(star), 1) == 1
    n = 5
    fa = features(n, chain)
    fb = features(n, star)
    assert fa["mean_twohop"] != fb["mean_twohop"]
    print("R23_TOY_CHAIN_STAR_IMPLICATION_TOPOLOGY_DIFFERENCE_OK")


def features(n: int, clauses):
    degree = [0] * (n + 1)
    pos = [0] * (n + 1)
    neg = [0] * (n + 1)
    neighbors = [set() for _ in range(n + 1)]
    pair_signs = defaultdict(set)
    pair_counts = Counter()
    same_literal_neighbors = [set() for _ in range(n + 1)]
    opposite_literal_neighbors = [set() for _ in range(n + 1)]
    repeated_per_clause = 0
    for clause in clauses:
        for lit in clause:
            v = abs(lit)
            assert 1 <= v <= n
            degree[v] += 1
            if lit > 0:
                pos[v] += 1
            else:
                neg[v] += 1
        for a, b in combinations(clause, 2):
            va, vb = abs(a), abs(b)
            if va == vb:
                continue
            k = (min(va, vb), max(va, vb))
            old = pair_counts[k]
            pair_counts[k] += 1
            if old:
                repeated_per_clause += 1
            orient = (a > 0, b > 0) if va < vb else (b > 0, a > 0)
            pair_signs[k].add(orient)
            neighbors[va].add(vb)
            neighbors[vb].add(va)
            for v, sign, other in ((va, a > 0, vb), (vb, b > 0, va)):
                (same_literal_neighbors if sign else opposite_literal_neighbors)[v].add(other)
    d = degree[1:]
    avg = statistics.mean(d)
    cv = statistics.pstdev(d) / max(avg, 1e-8)
    polarity = sum(abs(pos[v] - neg[v]) for v in range(1, n + 1)) / max(sum(d), 1)
    top = max(1, math.ceil(n / 10))
    hub = sum(sorted(d, reverse=True)[:top]) / max(sum(d), 1)
    ratio_pair_reuse = sum(max(0, cnt - 1) for cnt in pair_counts.values()) / max(sum(pair_counts.values()), 1)
    sign_diversity = sum(len(pair_signs[p]) > 1 for p in pair_signs) / max(len(pair_signs), 1)
    # Quartiles are feature-extraction partitions, not a claim of true communities.
    span = max(1, n // 4)
    cross = sum((a - 1) // span != (b - 1) // span for a, b in pair_counts) / max(len(pair_counts), 1)
    twohop = []
    for v in range(1, n + 1):
        reach = set()
        for u in neighbors[v]:
            reach.update(neighbors[u])
        reach.discard(v)
        twohop.append(len(reach) / max(n - 1, 1))
    lit_overlap = sum(
        len(same_literal_neighbors[v] & opposite_literal_neighbors[v]) /
        max(1, len(same_literal_neighbors[v] | opposite_literal_neighbors[v]))
        for v in range(1, n + 1)
    ) / n
    return {
        "degree_cv": cv, "polarity_bias": polarity, "hub_top10": hub,
        "pair_reuse": ratio_pair_reuse,
        "pair_sign_diversity": sign_diversity,
        "cross_quartile_edges": cross, "mean_twohop": statistics.mean(twohop),
        "twohop_variance": statistics.pvariance(twohop),
        "clause_repeated_varpair": repeated_per_clause / max(len(clauses), 1),
        "positive_negative_neighbor_overlap": lit_overlap,
    }


def outcomes():
    assert git_blob(CATALOG) == "a8fa4b316b0ea8863f623f0e41a9d654c2da4e62", "R21_CATALOG_BLOB_DRIFT"
    with CATALOG.open(newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 160 and len({x["formula_sha256"] for x in rows}) == 160
    # Replay the FROZEN R21 generator and verify exact content SHA per formula.
    import sys
    sys.path.insert(0, str(ROOT))
    import r21_native_benchmark as r21
    indexed = {x["formula"]: x for x in rows}
    output = []
    with tempfile.TemporaryDirectory() as folder:
        categories = sorted({
            ("community_" if x["family"] == "community3" else "") +
            "n" + x["n"] + "_" + x["fold"][-11:] if False else ""
            for x in []
        })
        # Category belongs to (family,n,fold,part); reconstruct from filename.
        categories = set()
        for x in rows:
            parts = x["formula"].removesuffix(".cnf").split("_")
            # r21_community3_220_development_0_00.cnf
            assert len(parts) == 6 and parts[0] == "r21"
            categories.add(("community_" if parts[1] == "community3" else "") +
                           "n" + parts[2] + "_" + parts[3] + parts[4])
        assert len(categories) == 16, sorted(categories)
        seen = set()
        for category in sorted(categories):
            for case in r21.make_cases(category, Path(folder), set()):
                old = indexed[case["formula"]]
                name = case["formula"]
                assert case["formula_sha256"] == old["formula_sha256"], name
                path = Path(folder) / name
                assert hashlib.sha256(path.read_bytes()).hexdigest() == case["formula_sha256"], name
                n, clauses = read_dimacs(path)
                assert n == int(old["n"])
                base = float(old["monitor"])
                forced = float(old["r11_2048_50"])
                assert 0 < base <= 24 and 0 < forced <= 24
                gain = (base - forced) / base
                result = {
                    "formula": name, "sha": case["formula_sha256"],
                    "fold": old["fold"], "family": old["family"], "n": n,
                    "monitor": base, "forced": forced, "gain": gain,
                    "catastrophic": forced > 2 * base,
                    "features": features(n, clauses),
                }
                output.append(result)
                seen.add(name)
        assert len(output) == len(seen) == 160
    return output


def fit(train):
    mu = {f: statistics.mean(x["features"][f] for x in train) for f in FEATURES}
    sig = {f: max(statistics.pstdev(x["features"][f] for x in train), 1e-6) for f in FEATURES}
    return {"protocol": "R23-shadow-structural-links-v1", "trained_on": "R21 development only",
            "features": list(FEATURES), "mu": mu, "sigma": sig, "training": train,
            "policy": {"k": K, "min_neighbors": MIN_NEIGHBORS,
                       "min_win_fraction": SAFE_WIN_FRACTION,
                       "min_mean_gain": MIN_MEAN_GAIN,
                       "max_similarity_distance": MAX_SIMILARITY_DISTANCE}}


def predict(model, target):
    eligible = [x for x in model["training"]
                if x["n"] == target["n"] and x["family"] == target["family"]
                and x["sha"] != target.get("sha")]
    if len(eligible) < MIN_NEIGHBORS:
        return {"allow": False, "reason": "insufficient_stratum_examples"}
    def distance(x):
        # 10 normalized structural dimensions, deterministic.
        return math.sqrt(sum(
            ((x["features"][f] - target["features"][f]) / model["sigma"][f]) ** 2
            for f in FEATURES
        ) / len(FEATURES))
    nearby = sorted(eligible, key=lambda x: (distance(x), x["sha"]))[:K]
    wins = sum(x["gain"] >= GAIN_FLOOR for x in nearby)
    dangerous = sum(x["catastrophic"] for x in nearby)
    mean_gain = statistics.mean(x["gain"] for x in nearby)
    local_distance = distance(nearby[0])
    allow = (
        len(nearby) >= MIN_NEIGHBORS and
        wins / len(nearby) >= SAFE_WIN_FRACTION and
        dangerous == 0 and mean_gain >= MIN_MEAN_GAIN and
        local_distance <= MAX_SIMILARITY_DISTANCE
    )
    return {"allow": bool(allow), "reason": "eligible" if allow else "abstain_risk",
            "neighbors": len(nearby), "wins": wins, "catastrophic": dangerous,
            "expected_gain": mean_gain, "nearest_distance": local_distance}


def evaluate(model, records):
    table = []
    for x in records:
        choice = predict(model, x)
        time = x["forced"] if choice["allow"] else x["monitor"]
        table.append({
            "formula": x["formula"], "family": x["family"], "n": x["n"],
            "monitor": x["monitor"], "forced": x["forced"], "shadow": time,
            "chosen_forced": int(choice["allow"]),
            "forced_regression_gt2x": int(x["catastrophic"]),
            "guard_regression_gt2x": int(time > 2 * x["monitor"]),
            "gain": x["gain"], "reason": choice["reason"],
            "neighbors": choice.get("neighbors", 0),
            "expected_gain": choice.get("expected_gain", 0),
        })
    s0 = sum(r["monitor"] for r in table)
    s1 = sum(r["forced"] for r in table)
    s2 = sum(r["shadow"] for r in table)
    return {
        "formulas": len(table), "interventions": sum(r["chosen_forced"] for r in table),
        "monitor_seconds": s0, "always_forced_seconds": s1, "shadow_seconds": s2,
        "forced_gain_pct": 100 * (s0 - s1) / s0,
        "shadow_gain_pct": 100 * (s0 - s2) / s0,
        "forced_catastrophic": sum(r["forced_regression_gt2x"] for r in table),
        "shadow_catastrophic": sum(r["guard_regression_gt2x" ] for r in table),
    }, table


def matched_pairs(dev):
    # Match similar coarse statistics and opposing intervention outcomes.
    results = []
    for i, a in enumerate(dev):
        for b in dev[i + 1:]:
            if a["n"] != b["n"] or a["family"] != b["family"]:
                continue
            if not ((a["gain"] > .10 and b["gain"] < -.10) or
                    (b["gain"] > .10 and a["gain"] < -.10)):
                continue
            coarse = abs(a["features"]["degree_cv"] - b["features"]["degree_cv"]) + (
                2 * abs(a["features"]["polarity_bias"] - b["features"]["polarity_bias"])
            )
            diffs = sorted(
                ((abs(a["features"][f] - b["features"][f]), f) for f in FEATURES
                 if f not in ("degree_cv", "polarity_bias")), reverse=True
            )
            results.append({"a": a["formula"], "b": b["formula"], "coarse_gap": coarse,
                            "a_gain": a["gain"], "b_gain": b["gain"],
                            "top_structural_differences": [f for _, f in diffs[:3]]})
    return sorted(results, key=lambda x: x["coarse_gap"])[:12]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--decide", action="store_true")
    ap.add_argument("--model", type=Path)
    ap.add_argument("--cnf", type=Path)
    ap.add_argument("--family", choices=["random3", "community3"])
    a = ap.parse_args()
    if a.self_test:
        self_test()
        return
    if a.decide:
        assert a.model and a.cnf and a.family
        model = json.loads(a.model.read_text())
        assert model["protocol"] == "R23-shadow-structural-links-v1"
        n, clauses = read_dimacs(a.cnf)
        target = {"n": n, "family": a.family,
                  "sha": hashlib.sha256(a.cnf.read_bytes()).hexdigest(),
                  "features": features(n, clauses)}
        print(json.dumps(predict(model, target), sort_keys=True))
        return
    assert a.evaluate
    self_test()
    items = outcomes()
    dev = [x for x in items if x["fold"].endswith("development")]
    holdout = [x for x in items if x["fold"].endswith("test")]
    assert len(dev) == len(holdout) == 80
    model = fit(dev)
    # Leave-one-out train-only diagnostic. The test fold never influences model.
    dev_summary, dev_rows = evaluate(model, dev)
    test_summary, test_rows = evaluate(model, holdout)
    pairs = matched_pairs(dev)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "model.json").write_text(json.dumps(model, indent=2, sort_keys=True) + "\\n")
    (OUT / "report.json").write_text(json.dumps({
        "scope": "offline historical counterfactual replay: NOT a live solver speedup",
        "caveat": "Pre-solve graph extraction overhead and prospective action decisions not measured",
        "development_loo": dev_summary, "holdout": test_summary,
        "matched_development_pairs": pairs,
        "model_sha256": hashlib.sha256((OUT / "model.json").read_bytes()).hexdigest(),
    }, indent=2, sort_keys=True) + "\\n")
    with (OUT / "holdout_decisions.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(test_rows[0]))
        w.writeheader()
        w.writerows(test_rows)
    print("R23_DEV", json.dumps(dev_summary, sort_keys=True))
    print("R23_BLIND_HOLDOUT", json.dumps(test_summary, sort_keys=True))
    print("R23_MATCHED_PAIRS", json.dumps(pairs[:5], sort_keys=True))
    print("R23_SHADOW_ONLY_NO_NATIVE_STRATEGY_CHANGED")


if __name__ == "__main__":
    main()
