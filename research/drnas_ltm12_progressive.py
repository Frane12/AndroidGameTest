#!/usr/bin/env python3
"""LTM12 Progressive: small-first official SAT2024 source-disjoint router study.

The native solver is unchanged. Learned policies only select one serial solver,
using CNF-only structural features. Report verified E2E PAR2 separately from
unverified UNSAT, with an exploratory (NOT globally blind) holdout.
"""
import collections
import hashlib
import json
import os
import pathlib
import random
import shutil
import sys
import time

import drnas_ltm11_real2 as B
import drnas_ltm11_policy as F

ROOT = pathlib.Path("ltm12_progressive")
SEED = 17
HOLDOUT_SEEDS = (17, 29)
CAPS = {"train": 3.0, "validation": 6.0, "holdout": 12.0}
SCREEN_ARMS = ("LTM9_FAST", "LTM8_FAST", "Kissat", "CaDiCaL", "CryptoMiniSat")
TEST_ARMS = ("LTM12_NATIVE", "LTM12_HYBRID", "LTM9_FAST",
             "LTM8_FAST", "Kissat", "CaDiCaL")
SCHEMA = "ltm12-progressive-verified-v1"

def emit(name, value):
    print(name + " " + json.dumps(value, sort_keys=True, separators=(",", ":")), flush=True)

def select_small_entries(entries):
    """Size curriculum, not outcome-directed filtering. 100 filename families."""
    eligible = sorted(
        (e for e in entries if not e.is_dir()
         and e.filename.lower().endswith((".cnf", ".cnf.xz", ".cnf.gz", ".cnf.bz2"))
         and 4000 <= e.file_size <= 900000
         and pathlib.PurePosixPath(e.filename).name not in B.OLD_OFFICIAL),
        key=lambda e: (e.file_size, e.filename))
    by_family = {}
    for entry in eligible:
        by_family.setdefault(B.family_key(entry.filename), entry)
    pool = sorted(by_family.values(), key=lambda e: (e.file_size, e.filename))
    if len(pool) < 100:
        raise RuntimeError(f"need >=100 filename families, got {len(pool)}")
    chosen = pool[:100]
    random.Random(1212).shuffle(chosen)
    assert len({B.family_key(e.filename) for e in chosen}) == 100
    return chosen, len(eligible), len(pool)

def setup_source():
    B.ROOT = ROOT
    B.SCREEN_CAP = CAPS["train"]
    B.TEST_CAP = CAPS["holdout"]
    B.TRAIN_COUNT = 60
    B.VALID_COUNT = 20
    B.TEST_COUNT = 20
    B.SAMPLE_COUNT = 100
    B.choose_archive_entries = select_small_entries
    B.emit = lambda name, obj: emit(name.replace("LTM11", "LTM12"), obj)
    original = B.command
    def command(arm, path, seed, cap):
        cmd = original(arm, path, seed, cap)
        if arm in F.NATIVE_ARMS and "--time" in cmd:
            cmd[cmd.index("--time") + 1] = str(max(0.1, cap - 0.30))
        return cmd
    B.command = command

def run_checked(arm, source, seed, cap):
    """Full E2E clock includes source SHA, subprocess and verification."""
    start = time.monotonic()
    out = B.run_solver(arm, source, seed, max(0.50, cap - 0.20))
    elapsed = time.monotonic() - start
    out["e2e_s"] = round(elapsed, 6)
    out["cap_s"] = cap
    out["original_cnf_sha256"] = source["sha256"]
    if elapsed > cap:
        out["status"] = "UNKNOWN"
        out["verified"] = False
        out["php_math_certified"] = False
    return B.with_metrics(out, cap)

def fallback(mode):
    return "LTM9_FAST" if mode == "NATIVE" else "Kissat"

def blank(mode):
    return dict(schema=SCHEMA, mode=mode, default=fallback(mode),
                enabled=False, alternate=None, feature=None, threshold=None,
                less_equal=True, status="not-validated")

def pick(model, feature):
    if model["schema"] != SCHEMA:
        raise ValueError("policy schema mismatch")
    if not model["enabled"]:
        return model["default"]
    if model["feature"] not in F.FEATURES:
        raise ValueError("unknown source feature")
    match = float(feature[model["feature"]]) <= float(model["threshold"])
    if not model["less_equal"]:
        match = not match
    return model["alternate"] if match else model["default"]

def score(rows, arm, feature):
    """PAR2 verified; a routed solve pays its extraction overhead."""
    trial = rows[arm]
    cap = trial["cap_s"]
    base = trial["PAR2_verified_s"]
    if base >= 2 * cap:
        return 2 * cap
    routed = base + feature.get("feature_extract_s", 0)
    return routed if routed <= cap else 2 * cap

def gain(model, cases, win_margin=0.03):
    default = model["default"]
    improvement = 0.0
    wins = regressions = switches = 0
    for feature, rows in cases:
        chosen = pick(model, feature)
        selected_cost = score(rows, chosen, feature)
        baseline_cost = rows[default]["PAR2_verified_s"]
        delta = baseline_cost - selected_cost
        improvement += delta
        if chosen != default:
            switches += 1
            if delta > win_margin:
                wins += 1
            elif delta < -win_margin:
                regressions += 1
    return dict(gain_s=round(improvement, 6), wins=wins,
                regressions=regressions, switches=switches)

def fit(train, validation, mode, win_margin=0.03, min_gain=0.5):
    """Thresholds and candidate selected using TRAIN only; one validation gate."""
    if len(train) < 20 or len(validation) < 10:
        raise ValueError("insufficient train/validation split")
    base = blank(mode)
    alternates = (("LTM8_FAST",) if mode == "NATIVE" else
                  ("CaDiCaL", "CryptoMiniSat", "LTM9_FAST", "LTM8_FAST"))
    candidates = []
    for name in F.FEATURES:
        values = sorted({float(f[name]) for f, _ in train})
        if len(values) < 5:
            continue
        thresholds = sorted({values[min(len(values) - 2, int((len(values)-1)*q))]
                             for q in (0.15, 0.30, 0.50, 0.70, 0.85)})
        for threshold in thresholds:
            for sense in (True, False):
                for alternate in alternates:
                    model = dict(base, enabled=True, alternate=alternate,
                                 feature=name, threshold=threshold,
                                 less_equal=sense, status="train-candidate")
                    t = gain(model, train, win_margin)
                    if t["wins"] < 2 or t["switches"] < 4:
                        continue
                    if t["gain_s"] <= min_gain:
                        continue
                    candidates.append((t["gain_s"], model, t))
    candidates.sort(key=lambda x: (-x[0], x[1]["feature"],
                                    x[1]["threshold"], x[1]["alternate"]))
    if not candidates:
        base["status"] = "no-verified-train-benefit"
        base["candidate_count"] = 0
        return base
    train_gain, candidate, training = candidates[0]
    checked = gain(candidate, validation, win_margin)
    accepted = (checked["wins"] >= 2 and checked["switches"] >= 2
                and checked["gain_s"] > min_gain
                and checked["wins"] >= checked["regressions"])
    model = candidate if accepted else base
    model["status"] = "validated" if accepted else "validation-rejected"
    model["candidate_count"] = len(candidates)
    model["training_evidence"] = training
    model["validation_evidence"] = checked
    return model

def curriculum(source):
    return CAPS[source["split"]]

def run_training(sources):
    pairs = []
    rows = []
    with (ROOT / "screen.jsonl").open("w") as handle:
        for source in sources:
            if source["split"] == "holdout":
                continue
            start = time.monotonic()
            feature = F.extract(source["path"])
            feature["feature_extract_s"] = time.monotonic() - start
            paired = {}
            for arm in SCREEN_ARMS:
                result = run_checked(arm, source, SEED, curriculum(source))
                paired[arm] = result
                rows.append(result)
                handle.write(json.dumps(result, sort_keys=True) + "\n")
                handle.flush()
                emit("LTM12_SCREEN_TRIAL", result)
            pairs.append((source, feature, paired))
    B.check_contradictions(rows)
    train = [(f, r) for s, f, r in pairs if s["split"] == "train"]
    val = [(f, r) for s, f, r in pairs if s["split"] == "validation"]
    if len(train) != 60 or len(val) != 20:
        raise ValueError("invalid source partition")
    models = {mode: fit(train, val, mode) for mode in ("NATIVE", "HYBRID")}
    evidence = dict(
        verified_train=sum(any(r["verified"] for r in rows.values()) for _, rows in train),
        verified_validation=sum(any(r["verified"] for r in rows.values()) for _, rows in val),
        progress_observed=sum(x["conflicts"] is not None or x["decisions"] is not None for x in rows),
        training_rows=len(rows),
        train_oracle_verified_PAR2_s=round(sum(min(x["PAR2_verified_s"] for x in armrows.values())
                        for _, armrows in train), 6),
        note="Oracle is a retrospective lower bound, not a usable predictor")
    memory = dict(schema=SCHEMA, models=models,
                  provenance=dict(train_sha256=sorted(s["sha256"] for s, _, _ in pairs
                                                     if s["split"] == "train"),
                                  validation_sha256=sorted(s["sha256"] for s, _, _ in pairs
                                                          if s["split"] == "validation"),
                                  holdout_used_for_fit=False),
                  evidence=evidence)
    (ROOT / "ltm12_memory.json").write_text(json.dumps(memory, indent=2, sort_keys=True) + "\n")
    emit("LTM12_TRAIN_FINAL", dict(models=models, evidence=evidence,
                                screening_metrics=B.metrics(rows, CAPS["train"], SCREEN_ARMS),
                                note="screening metrics mix 3s train and 6s validation caps; per-row verified PAR2 is authoritative"))
    return memory

def run_routed(source, seed, mode, memory):
    t = time.monotonic()
    feature = F.extract(source["path"])
    chosen = pick(memory["models"][mode], feature)
    overhead = time.monotonic() - t
    remaining = CAPS["holdout"] - overhead
    if remaining < 0.55:
        out = dict(arm=chosen, id=source["id"], seed=seed, split="holdout",
                   status="UNKNOWN", e2e_s=CAPS["holdout"],
                   verified=False, php_math_certified=False,
                   decisions=None, conflicts=None)
    else:
        out = run_checked(chosen, source, seed, remaining)
    out["arm"] = "LTM12_" + mode
    out["chosen_solver"] = chosen
    out["feature_extract_s"] = round(overhead, 6)
    out["e2e_s"] = round(out["e2e_s"] + overhead, 6)
    return B.with_metrics(out, CAPS["holdout"])

def run_holdout(sources):
    memory = json.loads((ROOT / "ltm12_memory.json").read_text())
    if memory["schema"] != SCHEMA or memory["provenance"]["holdout_used_for_fit"]:
        raise RuntimeError("incompatible or leaky memory")
    rows = []
    with (ROOT / "holdout.jsonl").open("w") as handle:
        for source in sources:
            if source["split"] != "holdout":
                continue
            for rep, seed in enumerate(HOLDOUT_SEEDS):
                rotated = list(TEST_ARMS)
                shift = (source["id"] + rep) % len(rotated)
                rotated = rotated[shift:] + rotated[:shift]
                for arm in rotated:
                    row = (run_routed(source, seed, arm.split("_", 1)[1], memory)
                           if arm.startswith("LTM12_")
                           else run_checked(arm, source, seed, CAPS["holdout"]))
                    row["rep"] = rep
                    row["shard"] = (source["id"] - 80) // 5
                    rows.append(row)
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                    handle.flush()
                    emit("LTM12_HOLDOUT_TRIAL", row)
    if len(rows) != 20 * len(HOLDOUT_SEEDS) * len(TEST_ARMS):
        raise RuntimeError("holdout trial count mismatch")
    B.check_contradictions(rows)
    totals = B.metrics(rows, CAPS["holdout"], TEST_ARMS)
    shards = {str(i): B.metrics([x for x in rows if x["shard"] == i],
                                CAPS["holdout"], TEST_ARMS) for i in range(4)}
    baseline_native = totals["LTM9_FAST"]["PAR2_verified_s"]
    baseline_ref = totals["Kissat"]["PAR2_verified_s"]
    report = dict(official_original_CNF=True, source_count=100,
                  train_sources=60, validation_sources=20, holdout_sources=20,
                  holdout_trials=len(rows), one_logical_CPU=True,
                  retrospective_not_globally_blind=True,
                  independently_verified_unsat="PHP mathematical only, not LRAT",
                  policy=memory["models"], training_evidence=memory["evidence"],
                  totals=totals, shards=shards,
                  relative_PAR2={
                      "native_vs_LTM9_x": round(baseline_native / max(0.000001, totals["LTM12_NATIVE"]["PAR2_verified_s"]), 5),
                      "hybrid_vs_Kissat_x": round(baseline_ref / max(0.000001, totals["LTM12_HYBRID"]["PAR2_verified_s"]), 5)},
                  selections=dict(collections.Counter(x["chosen_solver"] for x in rows
                         if x["arm"].startswith("LTM12_"))))
    (ROOT / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    emit("LTM12_REAL_FINAL", report)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as handle:
            handle.write("### DRNAS LTM12 Progressive — SAT2024 exploratory\n\n")
            handle.write("60 train @3s / 20 validation @6s / 20 holdout @12s x2; serial one CPU. Prior SAT2024 experiments exist: **NOT globally blind**.\n\n")
            handle.write("| Arm | Verified SAT | Math-certified UNSAT | Unverified UNSAT | Verified PAR2 s |\n")
            handle.write("|---|---:|---:|---:|---:|\n")
            for arm, item in totals.items():
                handle.write(f"| {arm} | {item['SAT_verified']} | {item['UNSAT_math_certified']} | {item['UNSAT_unverified']} | {item['PAR2_verified_s']:.3f} |\n")
            handle.write("\nNative and reference-assisted routers are separate comparisons. Unverified UNSAT earns no verified PAR2 reward.\n")
    emit("LTM12_PASS", dict(holdout_trials=len(rows)))

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "tiny.cnf"
        p.write_text("p cnf 3 3\n1 2 0\n-2 3 0\n-3 0\n")
        feat = F.extract(p)
        assert feat["binary"] > 0
        for mode in ("NATIVE", "HYBRID"):
            m = blank(mode)
            assert pick(m, feat) == fallback(mode)
            m.update(enabled=True, feature="binary", threshold=0.5,
                     alternate="CaDiCaL" if mode == "HYBRID" else "LTM8_FAST")
            assert pick(m, dict(feat, binary=0.1)) == m["alternate"]
        assert B.sat_witness_valid(p, 3, "v 1 -2 -3 0\n")
        assert not B.sat_witness_valid(p, 3, "v -1 -2 -3 0\n")
    emit("LTM12_SELFTEST_PASS", dict(source_features=True, verified_witness=True,
                                     two_separate_policies=True))

def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    setup_source()
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    for exe in ("kissat", "cadical", "cryptominisat5"):
        if not shutil.which(exe):
            raise RuntimeError("missing reference solver " + exe)
    if ROOT.exists():
        raise RuntimeError("fresh-run directory required")
    ROOT.mkdir(parents=True)
    sources = B.collect()
    manifest = ROOT / "manifest.json"
    info = json.loads(manifest.read_text())
    info.update(source_selection="100 smallest compressed-size filename-family representatives",
                curriculum={"train_s": 3, "validation_s": 6, "holdout_s": 12},
                exploratory_reused_prior_2024_holdout=True,
                blind_generalization_claim=False,
                compared_native_and_reference_routers_separately=True)
    manifest.write_text(json.dumps(info, indent=2) + "\n")
    run_training(sources)
    run_holdout(sources)

if __name__ == "__main__":
    main()

