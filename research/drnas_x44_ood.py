#!/usr/bin/env python3
"""X4.4: train-only novelty detection, abstaining router, and fresh-family trial.

The classifier sees only initial CNF structure. It never uses a filename, SHA,
generator-family label, planted witness, solver result, or previous-run memo
at inference. This is an OUTER solver router, not decision-level RL.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import math
import pathlib
import random
import statistics
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drnas_x42_1000 as G
import drnas_x43_two_cycle as X

SEED_NAMESPACE = "x44-independent-family-prospective-20261113-v1"
FAMILIES = (
    "planted_uniform", "planted_local40",
    "novel_hub16", "novel_widthmix", "novel_xor_duplicate",
)
KNOWN = {"planted_uniform", "planted_local40"}
N_EACH = 240
N_SHARDS = 12
CAP = 3.0
CORE = X.ARM_CORE
ADAPT = X.ARM_ADAPT


def emit(tag, obj):
    print(tag + " " + json.dumps(obj, sort_keys=True, separators=(",", ":")), flush=True)


def quantile(data, fraction):
    ordered = sorted(data)
    return ordered[min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))]


def detector_fit(train_rows):
    """12 source-only features; family labels restricted to training phase."""
    xs = [r["features"] for r in train_rows]
    names = sorted({r["family"] for r in train_rows})
    centers, scales = [], []
    for j in range(len(X.FEATURES)):
        col = [v[j] for v in xs]
        centers.append(quantile(col, 0.5))
        scales.append(max(0.015, quantile(col, 0.75) - quantile(col, 0.25)))
    z = [[max(-30.0, min(30.0, (a - c) / s))
          for a, c, s in zip(row, centers, scales)] for row in xs]
    low = [quantile([v[j] for v in z], 0.002) for j in range(len(X.FEATURES))]
    high = [quantile([v[j] for v in z], 0.998) for j in range(len(X.FEATURES))]
    prototypes = []
    for family in names:
        subset = [v for r, v in zip(train_rows, z) if r["family"] == family]
        prototypes.append([quantile([v[j] for v in subset], 0.5)
                           for j in range(len(X.FEATURES))])
    return dict(centers=centers, scales=scales, low=low, high=high,
                prototypes=prototypes, feature_names=X.FEATURES)


def novelty_score(detector, features):
    if len(features) != len(detector["centers"]):
        raise ValueError("Source feature dimension mismatch")
    z = [max(-30.0, min(30.0, (a - c) / s))
         for a, c, s in zip(features, detector["centers"], detector["scales"])]
    envelope = max(max(0.0, lo - x, x - hi)
                   for x, lo, hi in zip(z, detector["low"], detector["high"]))
    proximity = min(math.sqrt(sum((v - w) ** 2 for v, w in zip(z, p)) / len(z))
                    for p in detector["prototypes"])
    return envelope + 0.30 * proximity


def prepare_model(rows):
    """No holdout labels can affect fitting, threshold, or fallback."""
    seen = [r for r in rows if r["split"] in ("train", "validation")]
    training = [r for r in seen if r["split"] == "train"]
    validation = [r for r in seen if r["split"] == "validation"]
    if len(training) != 1800 or len(validation) != 600:
        raise RuntimeError("X4.3 train/validation partition changed")
    if len({r["sha256"] for r in seen}) != 2400:
        raise RuntimeError("Duplicate training source")
    router = X.train_model(seen, "X4.3-original-inputs-train-validation-only")
    fit_part = [r for r in training if r["id"] % 5 != 0]
    calibrate = [r for r in training if r["id"] % 5 == 0]
    if len(calibrate) != 360 or len(fit_part) != 1440:
        raise RuntimeError("Unexpected train calibration sizes")
    temporary = detector_fit(fit_part)
    threshold = quantile([novelty_score(temporary, r["features"])
                          for r in calibrate], 0.95)
    detector = detector_fit(training)
    family_cost = {}
    for family in sorted({r["family"] for r in training}):
        family_rows = [r for r in training if r["family"] == family]
        family_cost[family] = {
            arm: sum(r["arms"][arm]["PAR2_s"] for r in family_rows)
            for arm in (CORE, ADAPT)
        }
    worst_regret = {
        arm: max(family_cost[family][arm] / min(family_cost[family].values()) - 1
                 for family in family_cost)
        for arm in (CORE, ADAPT)
    }
    fallback = min((CORE, ADAPT), key=lambda arm: (worst_regret[arm], arm != CORE))
    return {
        "schema": 1, "mode": "source_only_novelty_abstain",
        "router": router, "detector": detector, "ood_threshold": threshold,
        "fallback": fallback, "worst_train_family_regret": worst_regret,
        "train_count": 1800, "calibration_count": 360, "validation_count": 600,
        "no_holdout_outcomes_used": True,
        "no_per_sha_memory": True,
        "notes": "Calibration 95th percentile is approximate, not a proven OOD guarantee."
    }


def route(model, features):
    old_arm = X.choose_arm(model["router"], features)
    score = novelty_score(model["detector"], features)
    abstain = score > model["ood_threshold"]
    guarded = model["fallback"] if abstain else old_arm
    return old_arm, guarded, score, abstain


def new_source(family, rep, root):
    if family in KNOWN:
        G.SAMPLE_HASH = SEED_NAMESPACE
        old = G.gen_source(family, rep, root)
        old["split"] = "eval_known"
        old["source_kind"] = "GENERATED_NEW_SEED_KNOWN_FAMILY"
        return old
    seed = int.from_bytes(hashlib.sha256(
        f"{SEED_NAMESPACE}:{family}:{rep}".encode()).digest()[:8], "big")
    rng = random.Random(seed)
    n = 220 + 7 * (rep % 10)
    density = 4.20 + (rep % 4) * 0.10
    secret = [bool(rng.getrandbits(1)) for _ in range(n)]
    clauses = []

    def sat(clause):
        return any(secret[abs(v) - 1] == (v > 0) for v in clause)

    def planted(vars_):
        c = [v if rng.getrandbits(1) else -v for v in vars_]
        if not sat(c):
            c[rng.randrange(len(c))] *= -1
        assert sat(c)
        return c

    for i in range(int(n * density)):
        width = 3
        if family == "novel_widthmix":
            if i % 9 == 0:
                width = 2
            elif i % 6 == 0:
                width = 4
        if family == "novel_hub16" and rng.random() < 0.55:
            hub = rng.randrange(1, 17)
            others = rng.sample([v for v in range(1, n + 1) if v != hub], width - 1)
            vs = [hub] + others
        else:
            vs = rng.sample(range(1, n + 1), width)
        clauses.append(planted(vs))
    if family == "novel_xor_duplicate":
        for _ in range(n // 20):
            vs = rng.sample(range(1, n + 1), 3)
            parity = sum(secret[v - 1] for v in vs) % 2
            for bits in itertools.product((0, 1), repeat=3):
                if sum(bits) % 2 != parity:
                    clauses.append([-v if b else v for v, b in zip(vs, bits)])
        clauses.extend([list(c) for c in clauses[: n // 5]])
    if family not in ("novel_hub16", "novel_widthmix", "novel_xor_duplicate"):
        raise ValueError("Unknown prospective family")
    if not all(sat(c) for c in clauses):
        raise AssertionError("Generated SAT witness not satisfied")
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{family}_{rep:03d}.cnf"
    content = f"p cnf {n} {len(clauses)}\n" + "".join(
        " ".join(map(str, c)) + " 0\n" for c in clauses)
    path.write_text(content)
    return {
        "global_id": -1, "formula_id": f"{family}:{rep:03d}",
        "family": f"GENERATED:{family}", "split": "eval_ood",
        "seed": seed, "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "path": str(path), "nvars": n, "nclauses": len(clauses),
        "oracle": "SAT_PLANTED_WITNESS", "source_kind": "GENERATED_NOT_OFFICIAL",
    }


def frozen_sources(root):
    sources = [new_source(family, rep, root)
               for family in FAMILIES for rep in range(N_EACH)]
    for idx, src in enumerate(sources):
        src["global_id"] = idx
    if len(sources) != 1200 or len({s["sha256"] for s in sources}) != 1200:
        raise RuntimeError("Must freeze 1200 distinct CNF SHA")
    manifest = [{k: v for k, v in src.items() if k != "path"} for src in sources]
    data = json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    return sources, data, hashlib.sha256(data.encode()).hexdigest()


def prepare(args):
    rows = X.read_one_cycle(args.cycle1_dir, "x43-cycle1", 12, 3000)
    model = prepare_model(rows)
    sources, data, sha = frozen_sources(pathlib.Path("x44_generated"))
    training_sha = {r["sha256"] for r in rows}
    if any(s["sha256"] in training_sha for s in sources):
        raise RuntimeError("Prospective formula overlaps historical input")
    output = pathlib.Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    model["prospective_manifest_sha256"] = sha
    (output / "model.json").write_text(json.dumps(model, sort_keys=True, indent=2) + "\n")
    (output / "frozen_manifest.json").write_text(data)
    val = [r for r in rows if r["split"] == "validation"]
    flagged = sum(route(model, r["features"])[3] for r in val)
    emit("X44_FROZEN", {
        "prospective_sources": len(sources), "manifest_sha256": sha,
        "train": model["train_count"], "validation": model["validation_count"],
        "fallback": model["fallback"], "ood_threshold": model["ood_threshold"],
        "validation_ood_flag_count": flagged,
        "validation_ood_flag_denominator": len(val),
        "worst_train_family_regret": model["worst_train_family_regret"]
    })


def charged_policy_run(src, arm, overhead):
    record, _ = X.checked_run(src, arm, CAP)
    full = record["e2e_s"] + overhead
    verified = record["status"] == "SAT_VERIFIED" and full <= CAP
    return {
        "status": "SAT_VERIFIED" if verified else "UNKNOWN",
        "e2e_s": round(full, 6),
        "PAR2_s": round(full if verified else 2 * CAP, 6),
    }


def shard_run(args):
    outdir = pathlib.Path(args.model_dir)
    model = json.loads((outdir / "model.json").read_text())
    sources, data, sha = frozen_sources(pathlib.Path("x44_generated"))
    if sha != model["prospective_manifest_sha256"]:
        raise RuntimeError("Model/manifest SHA mismatch")
    if hashlib.sha256((outdir / "frozen_manifest.json").read_bytes()).hexdigest() != sha:
        raise RuntimeError("Frozen manifest changed")
    mine = [s for s in sources if s["global_id"] % N_SHARDS == args.shard]
    dest = pathlib.Path(f"x44_stage/shard_{args.shard}")
    dest.mkdir(parents=True, exist_ok=True)
    counts = collections.Counter()
    with (dest / "trials.jsonl").open("w") as f:
        for idx, src in enumerate(mine, 1):
            start = time.perf_counter()
            features = X.extract_features(src["path"], src["nvars"], src["nclauses"])
            old_arm = X.choose_arm(model["router"], features)
            cost_old = time.perf_counter() - start
            score = novelty_score(model["detector"], features)
            abstain = score > model["ood_threshold"]
            new_arm = model["fallback"] if abstain else old_arm
            cost_guard = time.perf_counter() - start
            arms = {"CORE": CORE, "ADAPT": ADAPT, "X43": old_arm, "X44": new_arm}
            overhead = {"CORE": 0.0, "ADAPT": 0.0,
                        "X43": cost_old, "X44": cost_guard}
            order = list(arms)
            shift = src["global_id"] % len(order)
            order = order[shift:] + order[:shift]
            results = {key: charged_policy_run(src, arms[key], overhead[key]) for key in order}
            rec = {
                "sha256": src["sha256"], "id": src["global_id"],
                "family": src["family"], "split": src["split"],
                "ood_score": round(score, 7), "ood_flag": abstain,
                "old_choice": old_arm, "new_choice": new_arm,
                "policy_cost_s": round(cost_guard, 6), "arms": results,
            }
            f.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
            f.flush()
            counts["done"] += 1
            counts["ood_flagged"] += int(abstain)
            for k, r in results.items():
                counts[k + "_solved"] += r["status"] == "SAT_VERIFIED"
            if idx % 25 == 0:
                emit("X44_PROGRESS", {"shard": args.shard, "total": len(mine), **counts})
    report = {
        "shard": args.shard, "sources": len(mine), "manifest_sha256": sha,
        "counts": dict(counts), "cap_s": CAP,
    }
    (dest / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    emit("X44_SHARD_FINAL", report)


def finish(args):
    model_dir = pathlib.Path(args.model_dir)
    model = json.loads((model_dir / "model.json").read_text())
    expected = json.loads((model_dir / "frozen_manifest.json").read_text())
    expected_sha = {r["sha256"] for r in expected}
    gathered = []
    for shard in range(N_SHARDS):
        folder = pathlib.Path(args.shards_dir) / f"x44-eval-{shard}"
        report = json.loads((folder / "report.json").read_text())
        if report["manifest_sha256"] != model["prospective_manifest_sha256"]:
            raise RuntimeError("Inconsistent shard manifest")
        rows = [json.loads(line) for line in (folder / "trials.jsonl").read_text().splitlines()]
        if len(rows) != N_EACH * len(FAMILIES) // N_SHARDS:
            raise RuntimeError("Missing shard data")
        gathered.extend(rows)
    if len(gathered) != 1200 or len({r["sha256"] for r in gathered}) != 1200:
        raise RuntimeError("Duplicate/missing prospective trials")
    if {r["sha256"] for r in gathered} != expected_sha:
        raise RuntimeError("Evaluation SHA differ from frozen pre-run manifest")
    by_sha = {r["sha256"]: r for r in expected}
    for r in gathered:
        meta = by_sha[r["sha256"]]
        if r["family"] != meta["family"] or r["split"] != meta["split"]:
            raise RuntimeError("Split or family mismatch")
    def group_report(rr):
        out = {"sources": len(rr), "ood_flagged": sum(r["ood_flag"] for r in rr),
               "changed_routes": sum(r["old_choice"] != r["new_choice"] for r in rr),
               "mean_ood_score": round(statistics.mean(r["ood_score"] for r in rr), 5)}
        for k in ("CORE", "ADAPT", "X43", "X44"):
            arm = [r["arms"][k] for r in rr]
            out[k] = {
                "SAT_verified": sum(r["status"] == "SAT_VERIFIED" for r in arm),
                "PAR2_s": round(sum(r["PAR2_s"] for r in arm), 5),
                "E2E_s": round(sum(r["e2e_s"] for r in arm), 5),
            }
        out["x44_vs_x43"] = {
            "faster": sum(r["arms"]["X44"]["PAR2_s"] < r["arms"]["X43"]["PAR2_s"] - 0.002 for r in rr),
            "slower": sum(r["arms"]["X44"]["PAR2_s"] > r["arms"]["X43"]["PAR2_s"] + 0.002 for r in rr),
        }
        return out
    summary = {
        "status": "COMPLETE", "design": "FROZEN_PROSPECTIVE_NEW_SHA",
        "generated_not_official": True, "sources": len(gathered),
        "manifest_sha256": model["prospective_manifest_sha256"],
        "train_original_1800": model["train_count"],
        "train_calibration_360": model["calibration_count"],
        "validation_original_600": model["validation_count"],
        "new_known_seed_families": sorted(KNOWN),
        "new_ood_families": sorted(set(FAMILIES) - KNOWN),
        "ood_threshold": model["ood_threshold"], "fallback": model["fallback"],
        "splits": {
            k: group_report([r for r in gathered if r["split"] == k])
            for k in ("eval_known", "eval_ood")
        },
        "families": {
            k: group_report([r for r in gathered if r["family"] == "GENERATED:" + k])
            for k in FAMILIES
        },
        "overall": group_report(gathered),
        "limits": "Generated planted SAT only; initial-source OOD detection is not distance-to-solution; a low OOD false-positive rate within known families does not certify unseen-family correctness or faster solving. Training used historical X4.3 TRAIN and VALIDATION; held-out prospective sources were frozen before results and never tuned.",
    }
    dest = pathlib.Path(args.out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "report.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    with (dest / "paired_trials.jsonl").open("w") as f:
        for r in sorted(gathered, key=lambda x: x["id"]):
            f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")
    emit("X44_FINAL", summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "shard", "finish"))
    parser.add_argument("--cycle1-dir", default="x44_x43_training")
    parser.add_argument("--model-dir", default="x44_frozen")
    parser.add_argument("--shards-dir", default="x44_eval_downloads")
    parser.add_argument("--out-dir", default="x44_frozen")
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args)
    elif args.command == "shard":
        if args.shard not in range(N_SHARDS):
            parser.error("Invalid shard")
        if not X.X41.is_file() or not X.X3.is_file():
            parser.error("Compile both DRNAS native solvers first")
        shard_run(args)
    else:
        finish(args)


if __name__ == "__main__":
    main()
