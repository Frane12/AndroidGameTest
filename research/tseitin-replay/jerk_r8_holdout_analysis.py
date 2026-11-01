#!/usr/bin/env python3
"""Validate the frozen R8 paired holdout and test formula-level jerk association."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

CATEGORIES = ("random3", "graphcolor", "xor", "external_satlib")
MODES = ("stable_v1531", "monitor", "forced_restart25", "r5_frozen_gate")
TREATMENTS = ("stable_v1531", "forced_restart25", "r5_frozen_gate")
PER_CATEGORY = 25
REPEATS = 3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def median(values):
    values = sorted(values)
    if not values:
        return None
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def finite(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def interpolate(times, conflicts, target):
    if target <= times[0]:
        return conflicts[0]
    if target >= times[-1]:
        return conflicts[-1]
    for i in range(1, len(times)):
        if times[i] >= target:
            span = times[i] - times[i - 1]
            return conflicts[i - 1] + (conflicts[i] - conflicts[i - 1]) * (target - times[i - 1]) / span
    raise AssertionError("interpolation range failure")


def timed_jerk(points):
    usable = []
    for point in points:
        try:
            conflicts = int(point["conflict"])
            wall_ns = int(point["wall_ns"])
        except (KeyError, TypeError, ValueError):
            continue
        if conflicts <= 2048:
            usable.append((wall_ns, conflicts))
    usable = sorted(set(usable))
    if len(usable) < 7:
        return None, "insufficient_prefix_checkpoints"
    times = [p[0] for p in usable]
    conflicts = [p[1] for p in usable]
    if any(times[i] <= times[i - 1] or conflicts[i] <= conflicts[i - 1]
           for i in range(1, len(usable))):
        return None, "non_monotonic_time_or_conflicts"
    duration = (times[-1] - times[0]) * 1e-9
    if duration <= 0:
        return None, "zero_duration"
    samples = [interpolate(times, conflicts,
                           times[0] + (times[-1] - times[0]) * i / 10)
               for i in range(11)]
    third = [samples[i] - 3 * samples[i - 1] + 3 * samples[i - 2] - samples[i - 3]
             for i in range(3, len(samples))]
    denom = max(1.0, samples[-1] - samples[0])
    return {
        "jerk_abs_norm": statistics.mean(abs(v) for v in third) / denom,
        "jerk_signed_norm": statistics.mean(third) / denom,
        "prefix_duration_s": duration,
        "prefix_checkpoints": len(usable),
        "prefix_first_conflict": conflicts[0],
        "prefix_last_conflict": conflicts[-1],
    }, None


def rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        r = (i + j - 1) / 2
        for k in range(i, j):
            result[order[k]] = r
        i = j
    return result


def spearman(x, y):
    if len(x) < 8 or len(x) != len(y):
        return None
    rx, ry = rank(x), rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    xx = sum((v - mx) ** 2 for v in rx)
    yy = sum((v - my) ** 2 for v in ry)
    if not xx or not yy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / math.sqrt(xx * yy)


def association(x, y, seed):
    observed = spearman(x, y)
    n = len(x)
    if observed is None:
        return {"formulas": n, "spearman": None, "bootstrap_95": None,
                "permutation_p_two_sided": None}
    rng = random.Random(seed)
    boot = []
    for _ in range(3000):
        indices = [rng.randrange(n) for _ in range(n)]
        value = spearman([x[i] for i in indices], [y[i] for i in indices])
        if value is not None:
            boot.append(value)
    boot.sort()
    ci = [boot[int(0.025 * (len(boot) - 1))], boot[int(0.975 * (len(boot) - 1))]] if boot else None
    extreme = 0
    for _ in range(5000):
        shuffled = y[:]
        rng.shuffle(shuffled)
        value = spearman(x, shuffled)
        if value is not None and abs(value) >= abs(observed):
            extreme += 1
    return {"formulas": n, "spearman": observed, "bootstrap_95": ci,
            "permutation_p_two_sided": (extreme + 1) / 5001}


def read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        path.write_text("\n")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    measurements = []
    traces = {}
    sources = []
    all_hashes = set()
    skips = Counter()
    for category in CATEGORIES:
        folder = args.input / category
        csv_path, trace_path, manifest_path = (
            folder / "measurements.csv", folder / "traces.jsonl", folder / "manifest.json")
        if not all(p.is_file() for p in (csv_path, trace_path, manifest_path)):
            raise SystemExit(f"Missing complete holdout shard: {category}")
        rows = read_csv(csv_path)
        trace_rows = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
        manifest = json.loads(manifest_path.read_text())
        expected_rows = PER_CATEGORY * REPEATS * len(MODES)
        if len(rows) != expected_rows or len(trace_rows) != expected_rows:
            raise SystemExit(f"Incorrect measurement coverage for {category}: {len(rows)} / {len(trace_rows)}")
        if manifest.get("category") != category or manifest.get("stable_blob") != "d280a2ffa28d72aec183323bbea40544d676112d":
            raise SystemExit(f"Frozen source mismatch for {category}")
        if manifest.get("kissat_pin") != "8af8e56f174b778aef3aa45af9f739b2a5f492c2":
            raise SystemExit(f"Kissat pin mismatch for {category}")
        if len(manifest.get("cases", [])) != PER_CATEGORY:
            raise SystemExit(f"Expected {PER_CATEGORY} frozen formulas in {category}")
        formula_hashes = {case["formula_sha256"] for case in manifest["cases"]}
        if len(formula_hashes) != PER_CATEGORY or all_hashes.intersection(formula_hashes):
            raise SystemExit(f"Formula hash overlap or duplicate in {category}")
        all_hashes.update(formula_hashes)
        if any(row.get("error") for row in rows):
            raise SystemExit(f"Solver error present in {category}")
        measurements.extend(rows)
        for trace in trace_rows:
            key = (trace["category"], trace["formula"], str(trace["repeat"]), trace["mode"])
            if key in traces:
                raise SystemExit(f"Duplicate trace {key}")
            traces[key] = trace
        sources.append({
            "category": category,
            "measurements_sha256": sha(csv_path),
            "traces_sha256": sha(trace_path),
            "manifest_sha256": sha(manifest_path),
            "runner": manifest.get("runner"),
            "source_commit": manifest.get("source_commit"),
            "executables": manifest.get("executables"),
            "formula_hashes": sorted(formula_hashes),
        })

    expected_total = PER_CATEGORY * len(CATEGORIES) * REPEATS * len(MODES)
    if len(measurements) != expected_total or len(traces) != expected_total:
        raise SystemExit("Holdout does not contain exactly 1,200 distinct measurements and traces")
    index = {}
    for row in measurements:
        key = (row["category"], row["formula"], str(row["repeat"]), row["mode"])
        if key in index:
            raise SystemExit(f"Duplicate measurement {key}")
        index[key] = row

    paired = []
    features = []
    grouped = []
    formula_effects = []
    for category in CATEGORIES:
        formulas = sorted({r["formula"] for r in measurements if r["category"] == category})
        if len(formulas) != PER_CATEGORY:
            raise SystemExit(f"Expected {PER_CATEGORY} formulas for {category}")
        for formula in formulas:
            for rep in range(REPEATS):
                modes = {mode: index.get((category, formula, str(rep), mode)) for mode in MODES}
                if any(row is None for row in modes.values()):
                    raise SystemExit(f"Missing matched attempt: {category}/{formula}/{rep}")
                if len({row["runner"] for row in modes.values()}) != 1:
                    raise SystemExit("Paired attempts ran on different runners")
                if len({row["formula_sha256"] for row in modes.values()}) != 1:
                    raise SystemExit("Paired formula SHA mismatch")
                statuses = {row["status"] for row in modes.values() if row["status"] in ("SAT", "UNSAT")}
                if len(statuses) > 1:
                    raise SystemExit(f"Solver answer disagreement: {category}/{formula}/{rep}")
                monitor = modes["monitor"]
                signal, reason = timed_jerk(traces[(category, formula, str(rep), "monitor")].get("points", []))
                if reason:
                    skips[reason] += 1
                if signal:
                    features.append({"category": category, "formula": formula, "repeat": rep, **signal})
                for treatment in TREATMENTS:
                    target = modes[treatment]
                    base_par2 = float(monitor["par2_s"])
                    treatment_par2 = float(target["par2_s"])
                    paired.append({
                        "category": category,
                        "formula": formula,
                        "formula_sha256": monitor["formula_sha256"],
                        "repeat": rep,
                        "treatment": treatment,
                        "monitor_par2": base_par2,
                        "treatment_par2": treatment_par2,
                        "gain_pct": 100 * (base_par2 - treatment_par2) / base_par2 if base_par2 else None,
                        "monitor_status": monitor["status"],
                        "treatment_status": target["status"],
                        "usable_jerk": int(signal is not None),
                        "jerk_abs_norm": signal["jerk_abs_norm"] if signal else "",
                        "jerk_signed_norm": signal["jerk_signed_norm"] if signal else "",
                        "prefix_duration_s": signal["prefix_duration_s"] if signal else "",
                        "prefix_checkpoints": signal["prefix_checkpoints"] if signal else "",
                    })

    # Aggregate repeats within formula so the inferential unit remains the formula.
    by_formula_treatment = defaultdict(list)
    for row in paired:
        by_formula_treatment[(row["category"], row["formula"], row["treatment"])].append(row)
    by_formula_features = defaultdict(list)
    for row in features:
        by_formula_features[(row["category"], row["formula"])].append(row)
    aggregated = {}
    for key, rows in by_formula_treatment.items():
        usable = [r for r in rows if r["usable_jerk"]]
        aggregated[key] = {
            "monitor_par2": median([r["monitor_par2"] for r in rows]),
            "treatment_par2": median([r["treatment_par2"] for r in rows]),
            "gain_pct": median([r["gain_pct"] for r in rows if r["gain_pct"] is not None]),
            "jerk_abs_norm": median([float(r["jerk_abs_norm"]) for r in usable]) if len(usable) == REPEATS else None,
            "jerk_signed_norm": median([float(r["jerk_signed_norm"]) for r in usable]) if len(usable) == REPEATS else None,
            "prefix_duration_s": median([float(r["prefix_duration_s"]) for r in usable]) if len(usable) == REPEATS else None,
            "usable_repeats": len(usable),
        }
    formula_keys = sorted({(c, f) for c, f, _ in by_formula_treatment})
    formula_by_signal = {}
    for category, formula in formula_keys:
        for treatment in TREATMENTS:
            entry = aggregated[(category, formula, treatment)]
            formula_effects.append({"category": category, "formula": formula, "treatment": treatment, **entry})
        feature_entry = by_formula_features.get((category, formula), [])
        formula_by_signal[(category, formula)] = {
            "jerk_abs_norm": median([r["jerk_abs_norm"] for r in feature_entry]) if len(feature_entry) == REPEATS else None,
            "jerk_signed_norm": median([r["jerk_signed_norm"] for r in feature_entry]) if len(feature_entry) == REPEATS else None,
            "prefix_duration_s": median([r["prefix_duration_s"] for r in feature_entry]) if len(feature_entry) == REPEATS else None,
            "usable_repeats": len(feature_entry),
        }

    associations = {}
    category_directions = {}
    for treatment in ("forced_restart25", "r5_frozen_gate"):
        for category in ("all",) + CATEGORIES:
            rows = []
            for cat, formula in formula_keys:
                if category != "all" and cat != category:
                    continue
                signal = formula_by_signal[(cat, formula)]
                effect = aggregated[(cat, formula, treatment)]
                if signal["usable_repeats"] == REPEATS:
                    rows.append((cat, formula, signal, effect))
            seed = sum(ord(ch) for ch in (treatment + category)) + 20261101
            associations[treatment + "/" + category] = {
                "jerk_abs_vs_gain": association([r[2]["jerk_abs_norm"] for r in rows],
                                                 [r[3]["gain_pct"] for r in rows], seed),
                "jerk_signed_vs_gain": association([r[2]["jerk_signed_norm"] for r in rows],
                                                    [r[3]["gain_pct"] for r in rows], seed + 1),
                "prefix_duration_vs_gain": association([r[2]["prefix_duration_s"] for r in rows],
                                                       [r[3]["gain_pct"] for r in rows], seed + 2),
            }
            if treatment == "forced_restart25" and category != "all":
                val = associations[treatment + "/" + category]["jerk_abs_vs_gain"]["spearman"]
                if val is not None:
                    category_directions[category] = val

    primary = associations["forced_restart25/all"]["jerk_abs_vs_gain"]
    duration = associations["forced_restart25/all"]["prefix_duration_vs_gain"]
    same_direction = sum(1 for v in category_directions.values() if v > 0)
    supported = bool(
        primary["formulas"] >= 40 and primary["bootstrap_95"] and
        primary["bootstrap_95"][0] > 0 and
        primary["permutation_p_two_sided"] < 0.05 and
        same_direction >= 3 and
        primary["spearman"] is not None and duration["spearman"] is not None and
        abs(primary["spearman"]) > abs(duration["spearman"]))

    for category in CATEGORIES:
        for mode in MODES:
            subset = [r for r in measurements if r["category"] == category and r["mode"] == mode]
            grouped.append({
                "category": category, "mode": mode, "attempts": len(subset),
                "solved": sum(r["status"] in ("SAT", "UNSAT") for r in subset),
                "timeouts": sum(r["status"] == "TIMEOUT" for r in subset),
                "errors": sum(r["status"] == "ERROR" for r in subset),
                "par2_sum": round(sum(float(r["par2_s"]) for r in subset), 8),
            })

    report = {
        "protocol": "DRNAS Jerk R8 hash-new paired holdout",
        "measurements": len(measurements),
        "unique_formulas": len(formula_keys),
        "paired_comparisons": len(paired),
        "monitor_trials_with_usable_jerk": len(features),
        "monitor_trials_total": len(CATEGORIES) * PER_CATEGORY * REPEATS,
        "formulas_with_jerk_in_all_repeats": sum(
            formula_by_signal[k]["usable_repeats"] == REPEATS for k in formula_keys),
        "skipped": dict(skips),
        "groups": grouped,
        "associations": associations,
        "signal_predictive_rule_supported": supported,
        "predeclared_support_criteria": {
            "at_least_40_formula_level_complete_signals": True,
            "overall_jerk_gain_bootstrap_95_lower_bound_above_zero": True,
            "two_sided_formula_permutation_p_below_0.05": True,
            "same_positive_direction_in_at_least_3_of_4_categories": True,
            "absolute_jerk_rho_exceeds_prefix_duration_rho": True,
        },
        "sources": sources,
        "caution": "Association between a passive signal and a paired intervention effect is predictive evidence, not proof that the signal itself causes the effect. No active Jerk gate was tested; no official competition result is claimed.",
    }

    write_csv(args.out / "jerk_pairs.csv", paired)
    write_csv(args.out / "jerk_features.csv", features)
    write_csv(args.out / "formula_effects.csv", formula_effects)
    (args.out / "jerk_holdout_report.json").write_text(json.dumps(report, indent=2) + "\n")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for signal_name, label in (("jerk_abs_norm", "Timed conflict jerk"),
                                   ("prefix_duration_s", "Prefix duration")):
            fig, ax = plt.subplots(figsize=(8, 5))
            for category in CATEGORIES:
                xs, ys = [], []
                for cat, formula in formula_keys:
                    if cat != category:
                        continue
                    feature = formula_by_signal[(cat, formula)]
                    effect = aggregated[(cat, formula, "forced_restart25")]
                    if feature["usable_repeats"] == REPEATS:
                        xs.append(feature[signal_name])
                        ys.append(effect["gain_pct"])
                if xs:
                    ax.scatter(xs, ys, label=category, alpha=.7)
            ax.axhline(0, color="black", linestyle="--", linewidth=.8)
            ax.set(xlabel=label, ylabel="Paired PAR-2 gain vs monitor (%)",
                   title="R8 frozen holdout: signal vs restart intervention effect")
            if ax.has_data():
                ax.legend()
            fig.tight_layout()
            fig.savefig(args.out / ("scatter_" + signal_name + "_forced_restart25.png"), dpi=160)
            plt.close(fig)
    except ImportError:
        pass

    print(json.dumps({
        "measurements": report["measurements"],
        "unique_formulas": report["unique_formulas"],
        "usable_jerk_runs": report["monitor_trials_with_usable_jerk"],
        "formula_level_complete_signals": report["formulas_with_jerk_in_all_repeats"],
        "forced_restart25_jerk_association": primary,
        "forced_restart25_duration_control": duration,
        "signal_predictive_rule_supported": supported,
        "skipped": report["skipped"],
    }, indent=2))


if __name__ == "__main__":
    main()
