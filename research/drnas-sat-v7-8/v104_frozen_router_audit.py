#!/usr/bin/env python3
"""V10.4 retrospective structural-routing replay.

Training: 120 already measured V10.3 2026 SAT CNFs (15s cap).
Cross-validation: deterministic formula-disjoint 5 folds, two repeats kept together.
External check: only V11 formulas absent by BOTH ID and SHA (30s cap).
This program replays solver outcomes; it is NOT an integrated SAT solver,
not early-conflict telemetry, not a prospective blind test or a world ranking.
"""
import argparse
import csv
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

FEATURES = ("log_vars", "log_clauses", "clause_var", "avg_width", "binary_frac",
            "ternary_frac", "four_frac", "polarity_imbalance", "majority_coverage")
MODES = ("Kissat404", "DRNAS_Legacy", "DRNAS_NoLate", "CaDiCaL301")
K, SUPPORT, MARGIN = 7, 2, 2.0

def check(cond, reason):
    if not cond:
        raise ValueError(reason)

def read(path):
    return json.loads(Path(path).read_text())

def dataset(root, manifest_filename, prefix, shards, timeout, expected):
    root = Path(root)
    manifest = read(root / "frozen" / manifest_filename)
    cases = manifest["cases"]
    check(len(cases) == expected and manifest["cap_seconds"] == timeout, "Wrong manifest")
    byid = {case["id"]: case for case in cases}
    check(len(byid) == len(cases), "Duplicate CNF id")
    check(len({case["sha256"] for case in cases}) == len(cases), "Duplicate CNF SHA")
    attempts = {}
    for shard in range(shards):
        folder = root / "combined" / f"{prefix}-{shard}" / "results"
        meta, rows = read(folder / "meta.json"), read(folder / "rows.json")
        check(meta["shard"] == shard, "Wrong shard")
        check(len(rows) == len(cases[shard::shards]) * 8, "Incomplete shard")
        for row in rows:
            cid = row.get("id", row.get("cnf_id"))
            digest = row.get("sha256", row.get("cnf_sha256"))
            check(cid in byid and digest == byid[cid]["sha256"], "Unmatched CNF hash")
            key = (cid, row["repetition"], row["mode"])
            check(key not in attempts, "Duplicate trial")
            check(row["repetition"] in (0, 1) and row["mode"] in MODES, "Wrong solver/rep")
            check(row["status"] in ("SAT", "UNSAT", "TIMEOUT") and not row["error"],
                  "Invalid solver result")
            check(row["status"] == "TIMEOUT" or row["status"] == byid[cid]["official_label"],
                  "Wrong SAT/UNSAT answer")
            cost = timeout * 2 if row["status"] == "TIMEOUT" else row["seconds"]
            check(0 <= cost <= 2 * timeout, "Bad walltime")
            attempts[key] = float(cost)
    check(len(attempts) == expected * 8, "Missing solver trials")
    data = {}
    for case in cases:
        cid = case["id"]
        check(all(k in case["features"] for k in FEATURES), "Incomplete static features")
        data[cid] = {
            "sha256": case["sha256"],
            "features": case["features"],
            "costs": {mode: statistics.mean(attempts[(cid, rep, mode)]
                                          for rep in (0, 1)) for mode in MODES},
        }
    return data

def route(train, feature):
    # Per-fold scale computed from training only.
    scales = {k: max(max(d["features"][k] for d in train)
                      - min(d["features"][k] for d in train), 0.01) for k in FEATURES}
    def dist(point):
        return math.sqrt(sum(((feature[k] - point["features"][k]) / scales[k]) ** 2
                             for k in FEATURES))
    near = sorted(train, key=lambda point: (dist(point), point["sha256"]))[:K]
    weights = [1 / (0.05 + dist(point)) for point in near]
    expected = {mode: sum(w * point["costs"][mode] for point, w in zip(near, weights))
                         / sum(weights)
                for mode in ("Kissat404", "DRNAS_Legacy", "DRNAS_NoLate")}
    challenger = min(("DRNAS_Legacy", "DRNAS_NoLate"),
                     key=lambda mode: (expected[mode], mode))
    support = sum(point["costs"][challenger] + 1e-8 < point["costs"]["Kissat404"]
                  for point in near)
    switch = (support >= SUPPORT
              and expected["Kissat404"] - expected[challenger] >= MARGIN)
    return (challenger if switch else "Kissat404", support)

def summary(data, choices):
    check(len(choices) == len(data), "Missing decisions")
    par2 = {mode: round(statistics.mean(d["costs"][mode] for d in data.values()), 6)
            for mode in MODES}
    par2["V104_Router"] = round(statistics.mean(data[cid]["costs"][choice]
                                              for cid, (choice, _) in choices.items()), 6)
    return {"formulas": len(data), "PAR2": par2,
            "choices": dict(Counter(choice for choice, _ in choices.values()))}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--v103", required=True)
    parser.add_argument("--v11", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    train = dataset(args.v103, "v103_manifest.json", "v103-shard", 6, 15.0, 120)
    v11 = dataset(args.v11, "v11_manifest.json", "v11-shard", 10, 30.0, 50)

    overlap = set(train) & set(v11)
    overlap_sha = {v["sha256"] for v in train.values()} & {v["sha256"] for v in v11.values()}
    check(len(overlap) == 38 and len(overlap_sha) == 38, "Unexpected overlap")
    test = {cid:case for cid,case in v11.items() if cid not in train}
    check(len(test) == 12 and not ({d["sha256"] for d in test.values()} & 
                                   {d["sha256"] for d in train.values()}),
          "Test data are not truly disjoint")
    cv = {}
    for fold in range(5):
        hold = [cid for cid in train if int(hashlib.sha256(
            ("DRNAS-v104-static-cv-locked/" + cid).encode()).hexdigest(), 16) % 5 == fold]
        fitting = [case for cid, case in train.items() if cid not in hold]
        for cid in hold:
            cv[cid] = route(fitting, train[cid]["features"])
    check(len(cv) == 120, "CV coverage failure")
    external = {cid: route(list(train.values()), case["features"])
                for cid, case in test.items()}
    cv_result, external_result = summary(train, cv), summary(test, external)
    result = {
        "protocol": "DRNAS-V104-STATIC-ROUTER-RETROSPECTIVE-20261101-v1",
        "training_run_id": 41249978820, "external_run_id": 41250184539,
        "training_formulas": 120, "v11_formulas": 50,
        "overlapping_formulas_excluded": 38, "external_disjoint_formulas": 12,
        "k": K, "support_threshold": SUPPORT, "predicted_gain_seconds": MARGIN,
        "features": FEATURES, "cross_validation": cv_result, "external": external_result,
        "limits": [
            "Retrospective replay; both V10.3 and V11 results had been inspected.",
            "No input SHA leaks between training and disjoint V11 cases.",
            "V10.3 uses a 15s timeout; V11 uses 30s and a different CPU model.",
            "Formula-level grouped CV, both repetitions always in one fold.",
            "Static structural features only, not first-256-conflict telemetry.",
            "Replay of matched solver results, not a working unified adaptive solver.",
            "Not an official SAT 2026 competition score or world ranking.",
            "SAT/UNSAT labels checked, independent proof certificates not verified."
        ],
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "v104_report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    with (out / "v104_predictions.csv").open("w", newline="") as h:
        w = csv.writer(h)
        w.writerow(["cohort","cnf_id","sha256","choice","support",
                    "Kissat_PAR2","DRNAS_Legacy_PAR2","DRNAS_NoLate_PAR2"])
        for label, data, picks in (("cross_validated_v103", train, cv),
                                   ("sha_disjoint_v11", test, external)):
            for cid in sorted(data):
                case=data[cid]
                choice,support=picks[cid]
                w.writerow([label,cid,case["sha256"],choice,support,
                            case["costs"]["Kissat404"],case["costs"]["DRNAS_Legacy"],
                            case["costs"]["DRNAS_NoLate"]])
    lines=[
        "# DRNAS V10.4 — retrospective structural routing audit", "",
        "**NOT an official 2026 SAT Competition result or prospective model test.**", "",
        "120 V10.3 cases for 5-fold grouped cross-validation (15s cap).",
        "Only 12 of V11's 50 cases are SHA-disjoint from V10.3 (30s cap).",
        "K=7, at least two supporting neighbors, and >=2s predicted gain required",
        "to switch from fixed Kissat to a DRNAS strategy.", "",
        "| Cohort | Solver | PAR2 s (lower better) |", "|---|---|---:|"
    ]
    for label,s in (("V10.3 five-fold CV",cv_result),("V11 disjoint-12",external_result)):
        for mode,seconds in sorted(s["PAR2"].items(),key=lambda row:row[1]):
            lines.append(f"| {label} | {mode} | {seconds:.5f} |")
    lines.extend(["", "## Routing choices",
                  f"Cross-validation: {cv_result['choices']}",
                  f"Disjoint V11: {external_result['choices']}", "",
                  "This tests static routing ONLY; early-conflict dynamics remain untested.",
                  "Next: new SHA-disjoint CNFs with predeclared solver telemetry."])
    (out / "v104_report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print("V104_AUDIT_PASS",len(train),len(test),flush=True)

if __name__ == "__main__":
    main()
