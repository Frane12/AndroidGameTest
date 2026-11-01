#!/usr/bin/env python3
"""Audit the frozen R9 Jerk-gate experiment and compute paired effects."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from jerk_r8_holdout_analysis import timed_jerk

CATEGORIES = ("random3", "graphcolor", "xor", "external_satlib")
MODES = ("stable_v1531", "monitor", "forced_restart25",
         "r5_frozen_gate", "jerk_gate")
PER_CATEGORY = 25
REPEATS = 3
THRESHOLD = 0.0105088239760238


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows):
    if not rows:
        path.write_text("\n")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def median(values):
    vals = sorted(float(v) for v in values)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2


def paired_stats(gains, seed):
    n = len(gains)
    if not n:
        return {"formulas": 0, "mean_gain_pct": None, "median_gain_pct": None,
                "bootstrap_95_mean_gain": None, "paired_permutation_p": None}
    observed = sum(gains) / n
    rng = random.Random(seed)
    boot = []
    for _ in range(10000):
        boot.append(sum(gains[rng.randrange(n)] for _ in range(n)) / n)
    boot.sort()
    ci = [boot[int(0.025 * (len(boot) - 1))],
          boot[int(0.975 * (len(boot) - 1))]]
    extreme = 0
    for _ in range(20000):
        permuted = sum(v if rng.getrandbits(1) else -v for v in gains) / n
        if abs(permuted) >= abs(observed):
            extreme += 1
    return {
        "formulas": n,
        "mean_gain_pct": observed,
        "median_gain_pct": median(gains),
        "bootstrap_95_mean_gain": ci,
        "paired_permutation_p_two_sided": (extreme + 1) / 20001,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    measurements = []
    trace_index = {}
    sources = []
    all_hashes = set()
    for category in CATEGORIES:
        folder = args.input / category
        csv_path, trace_path, manifest_path = (
            folder / "measurements.csv",
            folder / "traces.jsonl",
            folder / "manifest.json",
        )
        if not all(p.is_file() for p in (csv_path, trace_path, manifest_path)):
            raise SystemExit(f"Missing complete R9 shard: {category}")
        rows = read_csv(csv_path)
        traces = [json.loads(line) for line in trace_path.read_text().splitlines()
                  if line.strip()]
        manifest = json.loads(manifest_path.read_text())
        expected = PER_CATEGORY * REPEATS * len(MODES)
        if len(rows) != expected or len(traces) != expected:
            raise SystemExit(
                f"Coverage mismatch in {category}: {len(rows)} rows, {len(traces)} traces")
        if manifest.get("category") != category:
            raise SystemExit(f"Category manifest mismatch: {category}")
        if manifest.get("stable_blob") != "d280a2ffa28d72aec183323bbea40544d676112d":
            raise SystemExit(f"Frozen V15.3.1 source mismatch: {category}")
        if manifest.get("kissat_pin") != "8af8e56f174b778aef3aa45af9f739b2a5f492c2":
            raise SystemExit(f"Pinned Kissat mismatch: {category}")
        cases = manifest.get("cases", [])
        hashes = {case["formula_sha256"] for case in cases}
        if len(cases) != PER_CATEGORY or len(hashes) != PER_CATEGORY:
            raise SystemExit(f"Formula freeze mismatch: {category}")
        if all_hashes.intersection(hashes):
            raise SystemExit(f"Formula hash overlap across categories: {category}")
        all_hashes.update(hashes)
        if any(row.get("error") for row in rows):
            raise SystemExit(f"Solver validation error present: {category}")
        measurements.extend(rows)
        for trace in traces:
            key = (trace["category"], trace["formula"], str(trace["repeat"]), trace["mode"])
            if key in trace_index:
                raise SystemExit(f"Duplicate trace: {key}")
            trace_index[key] = trace
        sources.append({
            "category": category,
            "measurements_sha256": file_sha(csv_path),
            "traces_sha256": file_sha(trace_path),
            "manifest_sha256": file_sha(manifest_path),
            "runner": manifest.get("runner"),
            "source_commit": manifest.get("source_commit"),
            "executables": manifest.get("executables"),
            "formula_hashes": sorted(hashes),
        })

    expected_total = PER_CATEGORY * len(CATEGORIES) * REPEATS * len(MODES)
    if len(measurements) != expected_total or len(trace_index) != expected_total:
        raise SystemExit("R9 does not contain exactly 1,500 unique paired attempts")
    index = {}
    for row in measurements:
        key = (row["category"], row["formula"], str(row["repeat"]), row["mode"])
        if key in index:
            raise SystemExit(f"Duplicate measurement: {key}")
        index[key] = row

    formula_rows = []
    gate_rows = [r for r in measurements if r["mode"] == "jerk_gate"]
    gate_evaluated = [r for r in gate_rows if r.get("gate_eligible", "") != ""]
    gate_triggered = [r for r in gate_rows if r.get("gate_action") == "2048"]
    gate_switched = [r for r in gate_rows if r.get("switch_at") == "2048"]
    gate_metric_audits = 0
    gate_metric_max_abs_diff = 0.0
    for row in gate_rows:
        trace = trace_index[(row["category"], row["formula"], str(row["repeat"]), "jerk_gate")]
        gate = trace.get("gate", {})
        if gate.get("valid") == "1":
            computed, reason = timed_jerk(trace.get("points", []))
            if reason or not computed:
                raise SystemExit("Jerk gate marked valid but analysis could not reproduce its metric")
            diff = abs(float(gate["jerk_abs"]) - computed["jerk_abs_norm"])
            gate_metric_max_abs_diff = max(gate_metric_max_abs_diff, diff)
            if diff > 1e-6:
                raise SystemExit(f"C/Python Jerk metric mismatch: {diff}")
            gate_metric_audits += 1
            eligible = int(float(gate["jerk_abs"]) >= THRESHOLD)
            if eligible != int(gate.get("eligible", "-1")):
                raise SystemExit("Frozen Jerk threshold decision mismatch")
        elif gate.get("valid") == "0" and gate.get("eligible") != "0":
            raise SystemExit("Invalid Jerk prefix incorrectly marked eligible")

    by_formula = defaultdict(lambda: defaultdict(list))
    for row in measurements:
        by_formula[(row["category"], row["formula"])][row["mode"]].append(row)
    formula_gains = defaultdict(list)
    category_gains = defaultdict(lambda: defaultdict(list))
    for (category, formula), modes in sorted(by_formula.items()):
        if set(modes) != set(MODES) or any(len(modes[m]) != REPEATS for m in MODES):
            raise SystemExit(f"Unpaired repeats: {category}/{formula}")
        hashes = {r["formula_sha256"] for rs in modes.values() for r in rs}
        if len(hashes) != 1:
            raise SystemExit(f"Formula hash mismatch: {category}/{formula}")
        medians = {mode: median([float(r["par2_s"]) for r in modes[mode]])
                   for mode in MODES}
        base = medians["monitor"]
        row = {"category": category, "formula": formula,
               "formula_sha256": next(iter(hashes))}
        for mode, value in medians.items():
            row[mode + "_median_par2_s"] = value
        for treatment in ("jerk_gate", "forced_restart25", "r5_frozen_gate",
                          "stable_v1531"):
            gain = 100.0 * (base - medians[treatment]) / base if base else None
            row[treatment + "_gain_pct_vs_monitor"] = gain
            if gain is not None:
                formula_gains[treatment].append(gain)
                category_gains[treatment][category].append(gain)
        formula_rows.append(row)

    effects = {}
    for treatment in ("jerk_gate", "forced_restart25", "r5_frozen_gate",
                      "stable_v1531"):
        effects[treatment + "_vs_monitor"] = paired_stats(
            formula_gains[treatment], sum(ord(c) for c in treatment) + 20261102)
    category_effects = {
        treatment: {
            category: {
                "formulas": len(vals),
                "mean_gain_pct": sum(vals) / len(vals) if vals else None,
            }
            for category, vals in category_gains[treatment].items()
        }
        for treatment in ("jerk_gate", "forced_restart25", "r5_frozen_gate",
                          "stable_v1531")
    }

    groups = []
    for category in CATEGORIES:
        for mode in MODES:
            subset = [r for r in measurements
                      if r["category"] == category and r["mode"] == mode]
            groups.append({
                "category": category,
                "mode": mode,
                "attempts": len(subset),
                "solved": sum(r["status"] in ("SAT", "UNSAT") for r in subset),
                "timeouts": sum(r["status"] == "TIMEOUT" for r in subset),
                "errors": sum(r["status"] == "ERROR" for r in subset),
                "par2_sum": round(sum(float(r["par2_s"]) for r in subset), 8),
            })

    monitor_usable = 0
    for category in CATEGORIES:
        for formula in sorted({r["formula"] for r in measurements
                               if r["category"] == category}):
            all_usable = True
            for repeat in range(REPEATS):
                trace = trace_index[(category, formula, str(repeat), "monitor")]
                signal, reason = timed_jerk(trace.get("points", []))
                if reason or not signal:
                    all_usable = False
                else:
                    monitor_usable += 1
            if all_usable:
                pass

    primary = effects["jerk_gate_vs_monitor"]
    positive_categories = sum(
        1 for category in CATEGORIES
        if category_effects["jerk_gate"].get(category, {}).get("mean_gain_pct", 0) > 0)
    signal_supported = bool(
        primary["formulas"] >= 40 and
        primary["bootstrap_95_mean_gain"] and
        primary["bootstrap_95_mean_gain"][0] > 0 and
        primary["paired_permutation_p_two_sided"] < 0.05 and
        positive_categories >= 3 and
        len({r["formula"] for r in gate_triggered}) >= 10)

    report = {
        "protocol": "DRNAS Jerk R9 opt-in median gate holdout",
        "measurements": len(measurements),
        "unique_formulas": len(by_formula),
        "monitor_trials_with_reproducible_jerk": monitor_usable,
        "gate_attempts": len(gate_rows),
        "gate_evaluated_attempts": len(gate_evaluated),
        "gate_triggered_attempts": len(gate_triggered),
        "gate_restarted_at_2048_attempts": len(gate_switched),
        "gate_triggered_formula_count": len({r["formula"] for r in gate_triggered}),
        "gate_metric_python_reproductions": gate_metric_audits,
        "gate_metric_max_absolute_difference": gate_metric_max_abs_diff,
        "frozen_threshold": THRESHOLD,
        "effects": effects,
        "category_effects": category_effects,
        "groups": groups,
        "signal_gate_supported": signal_supported,
        "predeclared_gate_support_criteria": {
            "at_least_40_formula_level_paired_effects": True,
            "bootstrap_95_lower_bound_above_zero": True,
            "paired_permutation_p_below_0.05": True,
            "positive_mean_gain_in_at_least_3_of_4_categories": True,
            "gate_triggered_on_at_least_10_formulae": True,
        },
        "sources": sources,
        "caution": "The Jerk policy is experimental and opt-in. A successful build is not evidence of a solver speedup; only the frozen paired holdout can support that claim.",
    }
    write_csv(args.out / "formula_effects.csv", formula_rows)
    write_csv(args.out / "measurements.csv", measurements)
    (args.out / "jerk_gate_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "measurements": report["measurements"],
        "unique_formulas": report["unique_formulas"],
        "gate_evaluated_attempts": report["gate_evaluated_attempts"],
        "gate_triggered_attempts": report["gate_triggered_attempts"],
        "gate_metric_python_reproductions": report["gate_metric_python_reproductions"],
        "jerk_gate_vs_monitor": effects["jerk_gate_vs_monitor"],
        "signal_gate_supported": signal_supported,
    }, indent=2))


if __name__ == "__main__":
    main()
