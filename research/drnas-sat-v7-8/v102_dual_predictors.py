#!/usr/bin/env python3
"""DRNAS V10.2: two separate non-parametric early-signal prediction targets.

Training = frozen V10 12 CNFs. Grouped leave-one-CNF-out report is exploratory.
Evaluation = eight V10.1 archived 2025 CNFs disjoint from V10/V9.8, but
previously used by older V7.2.1 experiments. The four V10.1 repeated 2026
diagnostic CNFs are excluded. Not a prospective or fully blind benchmark.

Task A: predict whether enabling phase hints improves mean capped PAR2 by >=1s
        vs no phase hints, using identical first 256 conflicts.
Task B: predict if NO-phase strategy times out in BOTH 18-second repetitions.
No hidden outcome, ID, benchmark family, SAT label or post-256 measurement
enters either predictor. Neither predictor controls the solver in this study.
"""
import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

PROTOCOL = "DRNAS-V102-locked-two-predictors-20261031"
CAP = 18.0
PHASE_MARGIN = 1.0
PLAIN = "v100_late_plain_force"
PHASE = "v100_late_phase_force"
EARLY_KEYS = (
    "stage1", "v90_learned_256", "v90_lbd2_256", "v90_props_256",
    "v90_conflicts_256", "v90_jumpdepth_256", "v90_jumps_256", "active_256"
)
FEATURE_KEYS = (
    "lbd2_fraction", "log_propagations_per_conflict", "log_mean_jump_depth",
    "log_learned_per_conflict", "active_256", "stage1_finished"
)
TARGETS = ("phase_benefit_ge_1s", "plain_timeout_both")


def require(flag, message):
    if not flag:
        raise ValueError(message)


def load_json(p):
    return json.loads(Path(p).read_text())


def score(r):
    require(r["status"] in ("SAT", "UNSAT", "TIMEOUT"), "bad status")
    return 2 * CAP if r["status"] == "TIMEOUT" else float(r["wall_s"])


def extract(t):
    learned = int(t["v90_learned_256"])
    conflicts = int(t["v90_conflicts_256"])
    lbd2 = int(t["v90_lbd2_256"])
    props = int(t["v90_props_256"])
    jumps = int(t["v90_jumps_256"])
    depth = int(t["v90_jumpdepth_256"])
    require(min(learned, conflicts, lbd2, props, jumps, depth) >= 0,
            "negative telemetry")
    require(lbd2 <= learned, "impossible LBD count")
    return {
        "lbd2_fraction": lbd2 / max(1, learned),
        "log_propagations_per_conflict": math.log1p(props / max(1, conflicts)),
        "log_mean_jump_depth": math.log1p(depth / max(1, jumps)),
        "log_learned_per_conflict": math.log1p(learned / max(1, conflicts)),
        "active_256": float(int(t["active_256"]) > 0),
        "stage1_finished": float(int(t["stage1"]) != 0),
    }


def read_cases(path, version):
    manifest = load_json(Path(path) / ("v100_manifest.json" if version == 100
                                       else "v101_manifest.json"))
    require(len(manifest["cases"]) == 12, "12 CNFs required")
    require(manifest["cap"] == CAP and manifest["repeats"] == 2, "wrong protocol cap")
    cases = manifest["cases"]
    require(len({c["id"] for c in cases}) == 12, "duplicate CNF ID")
    by_id = {c["id"]: c for c in cases}
    runs = defaultdict(dict)
    for shard in range(6):
        folder = Path(path) / f"v{version}-shard-{shard}" / "results"
        metadata = load_json(folder / "meta.json")
        require(metadata["shard"] == shard and metadata["rows"] ==
                (36 if version == 100 else 44), "bad shard metadata")
        expected = [x["id"] for x in cases[shard * 2 : shard * 2 + 2]]
        require(metadata["cases"] == expected, "shard CNF order mismatch")
        raw = load_json(folder / "raw.json")
        require(len(raw) == (36 if version == 100 else 44), "incomplete shard")
        for r in raw:
            require(r["id"] in by_id and r["sha256"] == by_id[r["id"]]["sha256"],
                    "CNF SHA mismatch")
            require(r["group"] == by_id[r["id"]]["group"], "group mismatch")
            require(r["cap"] == CAP, "time cap mismatch")
            require(r["status"] in ("SAT", "UNSAT", "TIMEOUT") and not r["error"],
                    "invalid execution")
            if r["status"] != "TIMEOUT":
                require(r["status"] == by_id[r["id"]]["official_label"],
                        "answer mismatch")
            key = (r["id"], r["rep"])
            require(r["mode"] not in runs[key], "duplicate mode/seed")
            runs[key][r["mode"]] = r
    require(len(runs) == 24, "incomplete CNF repeats")
    expected_arms = set(manifest["arms"])
    require(len(expected_arms) == (9 if version == 100 else 11),
            "arm set mismatch")
    results = []
    for c in cases:
        observed = []
        for rep in range(2):
            rr = runs[(c["id"], rep)]
            require(set(rr) == expected_arms, "missing policy")
            early_p = rr[PLAIN]["early"]
            early_q = rr[PHASE]["early"]
            require(all(k in early_p and k in early_q and early_p[k] == early_q[k]
                        for k in EARLY_KEYS), "unmatched early prefix")
            require(rr[PLAIN]["seed"] == rr[PHASE]["seed"], "unmatched seed")
            observed.append((extract(early_p), rr[PLAIN], rr[PHASE]))
        # Average across two replay seeds; one independent sample per CNF.
        feature = {k: sum(x[0][k] for x in observed) / 2 for k in FEATURE_KEYS}
        advantage = sum(score(x[1]) - score(x[2]) for x in observed) / 2
        timeout_count = sum(x[1]["status"] == "TIMEOUT" for x in observed)
        results.append({
            "case": c["id"], "sha256": c["sha256"], "group": c["group"],
            "features": feature,
            "targets": {
                "phase_benefit_ge_1s": int(advantage >= PHASE_MARGIN),
                "plain_timeout_both": int(timeout_count == 2),
            },
            "actual_phase_benefit_s": round(advantage, 6),
            "plain_timeouts": timeout_count,
        })
    return manifest, results


def distance(a, b, ranges):
    return sum(((a["features"][key] - b["features"][key]) / ranges[key]) ** 2
               for key in FEATURE_KEYS) ** .5


def predict(train, item, target):
    require(len({r["case"] for r in train}) >= 3, "not enough distinct training CNFs")
    # Scales are computed from TRAINING cases only, never from test cases.
    ranges = {
        k: max(max(x["features"][k] for x in train) -
               min(x["features"][k] for x in train), 0.25 if k in
               ("active_256", "stage1_finished") else 1e-3)
        for k in FEATURE_KEYS
    }
    nearest = sorted(train, key=lambda x: (distance(x, item, ranges), x["sha256"]))[:3]
    weights = [1.0 / (0.05 + distance(x, item, ranges)) for x in nearest]
    probability = sum(w * x["targets"][target] for w, x in zip(weights, nearest)) / sum(weights)
    # Abstention is fixed, not selected using holdout outcomes.
    decision = "YES" if probability >= .65 else "NO" if probability <= .35 else "ABSTAIN"
    return {"score": round(probability, 6), "decision": decision,
            "neighbor_cases": [x["case"][:12] for x in nearest]}


def evaluate(train, test, title):
    rows = []
    for item in test:
        record = {"case": item["case"][:12], "group": item["group"],
                  "phase_benefit_s": item["actual_phase_benefit_s"],
                  "plain_timeouts_2": item["plain_timeouts"]}
        for target in TARGETS:
            pred = predict(train, item, target)
            record[target] = {"actual": item["targets"][target], **pred}
        rows.append(record)
    metrics = {}
    for target in TARGETS:
        observed = [r[target] for r in rows]
        covered = [r for r in observed if r["decision"] != "ABSTAIN"]
        correct = sum((r["decision"] == "YES") == bool(r["actual"]) for r in covered)
        majority = int(sum(r["actual"] for r in train) * 2 >= len(train)) if train else 0
        metrics[target] = {
            "n_cases": len(observed), "positive_cases": sum(r["actual"] for r in observed),
            "coverage": len(covered), "correct_when_covered": correct,
            "brier_score": round(sum((r["score"] - r["actual"])**2 for r in observed) /
                                 max(1, len(observed)), 6),
            "majority_baseline_correct": sum(r["actual"] == majority for r in observed),
            "training_majority": majority,
        }
    return {"cohort": title, "metrics": metrics, "predictions": rows}


def markdown(report):
    lines = ["# DRNAS V10.2 — Separate phase-benefit and timeout-risk predictions",
             "", "Method: k=3 nearest *distinct CNFs*, scaled on training cases only;",
             "no regression, no solver modifications, and no outcome-derived input features.",
             "Two replays are merged into ONE independent case-level observation.",
             "Benefit = phase PAR2 advantage >=1s; risk = plain timeout in BOTH 18s trials.",
             "Scores >=0.65 predict YES; <=0.35 predict NO; otherwise ABSTAIN.",
             "All thresholds fixed before examining V10.1 held-out outcomes.",
             "", "This is **retrospective** external evaluation, not a blind or official record.",
             "All eight 2025 evaluation CNFs appeared in older V7.2.1 work.",
             ""]
    for block in ("crossvalidation", "holdout"):
        x = report[block]
        lines += [f"## {x['cohort']}", "",
                  "| Target | Positives | Covered / cases | Correct / covered | Brier ↓ | Majority correct |",
                  "|---|---:|---:|---:|---:|---:|"]
        for name in TARGETS:
            v = x["metrics"][name]
            lines.append(f"| {name} | {v['positive_cases']} | {v['coverage']}/{v['n_cases']} | "
                         f"{v['correct_when_covered']}/{v['coverage']} | "
                         f"{v['brier_score']:.4f} | {v['majority_baseline_correct']}/{v['n_cases']} |")
        lines += ["", "| CNF | Phase actual gain (s) | Phase score / choice | "
                  "Plain timeouts / 2 | Timeout score / choice |",
                  "|---|---:|---|---:|---|"]
        for r in x["predictions"]:
            p = r[TARGETS[0]]
            q = r[TARGETS[1]]
            lines.append(f"| {r['case']} | {r['phase_benefit_s']:+.3f} | "
                         f"{p['score']:.3f} / {p['decision']} | "
                         f"{r['plain_timeouts_2']} | {q['score']:.3f} / {q['decision']} |")
        lines.append("")
    lines += ["Cautions: Only 12 training CNFs and 8 evaluation CNFs; no validated",
              "statistical confidence. Repeated runs of a formula are correlated.",
              "UNSAT uses archived official labels, not independent DRAT/LRAT certificates."]
    return "\n".join(lines) + "\n"


def audit(args):
    m100, train = read_cases(args.v100, 100)
    m101, other = read_cases(args.v101, 101)
    heldout = [x for x in other if x["group"] == "archived_2025_new_to_v101"]
    repeated = [x for x in other if x["group"] == "known_2026_diagnostic"]
    require(len(heldout) == 8 and len(repeated) == 4, "wrong test groups")
    require({x["sha256"] for x in heldout}.isdisjoint({x["sha256"] for x in train}),
            "holdout leakage")
    require({x["case"] for x in heldout}.isdisjoint({x["case"] for x in train}),
            "case overlap")
    require({x["case"] for x in repeated}.issubset({x["case"] for x in train}),
            "diagnostic overlap not properly identified")
    cvpred = []
    for item in train:
        other_train = [x for x in train if x["case"] != item["case"]]
        cvpred += evaluate(other_train, [item], "one-case").get("predictions", [])
    # Aggregate grouped cross-val rows without re-fitting on tested cases.
    cv = {"cohort": "V10 leave-one-CNF-out (exploratory)"}
    cv["predictions"] = cvpred
    cv["metrics"] = {}
    for target in TARGETS:
        obs = [x[target] for x in cvpred]
        covered = [x for x in obs if x["decision"] != "ABSTAIN"]
        correct = sum((x["decision"] == "YES") == bool(x["actual"]) for x in covered)
        most = int(sum(x["targets"][target] for x in train) * 2 >= len(train))
        cv["metrics"][target] = {
            "n_cases": len(obs), "positive_cases": sum(x["actual"] for x in obs),
            "coverage": len(covered), "correct_when_covered": correct,
            "brier_score": round(sum((x["score"] - x["actual"]) ** 2 for x in obs) / len(obs), 6),
            "majority_baseline_correct": sum(x["actual"] == most for x in obs),
        }
    holdout = evaluate(train, heldout, "V10.1 additional archival cases (8)")
    result = {
        "protocol": PROTOCOL, "train_cases": len(train), "holdout_cases": len(heldout),
        "repeated_diagnostics_excluded": len(repeated),
        "train_source": m100["protocol"], "holdout_source": m101["protocol"],
        "features": list(FEATURE_KEYS), "targets": list(TARGETS),
        "crossvalidation": cv, "holdout": holdout,
        "limitations": [
            "Retrospective evaluation; V10.1 had been run before this model was frozen.",
            "V10.1 2025 cases exclude V10/V9.8 but existed in older V7.2.1 research.",
            "Not a deployable classifier without fresh unseen corpus and calibration."
        ],
    }
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    text = markdown(result)
    Path(args.md).write_text(text)
    print(text)


def selftest():
    base = {
        "v90_learned_256": "40", "v90_conflicts_256": "256",
        "v90_lbd2_256": "10", "v90_props_256": "40000",
        "v90_jumps_256": "90", "v90_jumpdepth_256": "400",
        "active_256": "100", "stage1": "0",
    }
    f = extract(base)
    assert len(f) == len(FEATURE_KEYS)
    items = [{
        "case": f"c{i}", "sha256": f"{i:064x}", "group": "training",
        "features": {k: v + (i * .015 if k not in
                            ("active_256", "stage1_finished") else 0) for k, v in f.items()},
        "targets": {TARGETS[0]: int(i % 2 == 0), TARGETS[1]: int(i >= 3)},
        "actual_phase_benefit_s": 2.0 if i % 2 == 0 else -1.0,
        "plain_timeouts": 2 if i >= 3 else 0,
    } for i in range(6)]
    for t in TARGETS:
        assert 0 <= predict(items[:-1], items[-1], t)["score"] <= 1
    outcome = evaluate(items[:-1], [items[-1]], "mock")
    assert outcome["metrics"][TARGETS[0]]["n_cases"] == 1
    assert "ABSTAIN" in markdown({"crossvalidation": outcome, "holdout": outcome})
    print("V10.2 selftest passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    a = sub.add_parser("audit")
    for arg in ("v100", "v101", "out", "md"):
        a.add_argument("--" + arg, required=True)
    args = ap.parse_args()
    (selftest if args.cmd == "selftest" else lambda: audit(args))()
