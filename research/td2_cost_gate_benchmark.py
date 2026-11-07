#!/usr/bin/env python3
"""TD2 40-source DEVELOPMENT ablation: 8 arms, 2 repeats, 640 attempts.

Uses the exposed R199 manifest unchanged. This is not a new blind holdout.
All arms include process startup, pilot/restart, preparation and SAT verification
inside one 20-second budget. Backend UNSAT has no independent LRAT certificate.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import subprocess
import time

import r199_unseen_mixed40_crossbackend as source_suite
import td2_bounded_gf2 as method

ROOT = pathlib.Path("td2")
CAP = 20.0
REPS = 2
SHARDS = 8
PROTO = "DRNAS-TD2-SPARSE-CERTIFIED-GF2-COST-GATE-DEV40-v1"
VARIANTS = ("plain", "reference_hybrid", "sparse_budget", "pilot_sparse_budget")
MODES = tuple(f"{backend}_{variant}" for backend in ("kissat", "cms")
              for variant in VARIANTS)
certified = method.certified
certified.CAP = CAP
certified.ROOT = ROOT / "reference"


def need(ok, message):
    if not ok:
        raise RuntimeError("TD2_FAIL_CLOSED " + str(message))


def save(path, value):
    certified.save(path, value)


def verify():
    cases, groups = source_suite.cases_and_groups()
    for path, digest in json.loads((ROOT / "pins.json").read_text()).items():
        need(certified.sha(path) == digest, "pin drift " + path)
    return cases, groups


def command(backend, source):
    if backend == "kissat":
        return [str(pathlib.Path("built/bin/kissat_4_0_4").resolve()), str(source.resolve())]
    return ["/usr/bin/cryptominisat5", "--threads=1", str(source.resolve())]


def solve(backend, path, seconds):
    if seconds < 0.001:
        return "TIMEOUT", {}, 124
    try:
        result = subprocess.run(command(backend, path), capture_output=True,
                                text=True, errors="replace", timeout=seconds)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", {}, 124
    status, model, _route = certified.old.inspect(
        result.stdout + "\n" + result.stderr, result.returncode)
    return status, model, result.returncode


def trial(case, mode, rep, shard):
    source = source_suite.SOURCE / (case["id"] + ".cnf")
    need(certified.sha(source) == case["sha256"], "source drift")
    backend, variant = mode.split("_", 1)
    started = time.perf_counter()
    status, model, rc = "TIMEOUT", {}, None
    proof = "CAP_TIMEOUT"
    meta = {"preprocess_s": 0.0, "pilot_s": 0.0, "verification_s": 0.0,
            "pilot_solved": False, "preprocess_budget_exhausted": False,
            "added_total_clauses": 0, "gate_reason": "plain"}
    source_path = source
    decision = None
    if variant == "pilot_sparse_budget":
        phase = time.perf_counter()
        status, model, rc = solve(backend, source, method.PILOT_CAP_S)
        meta["pilot_s"] = round(time.perf_counter() - phase, 6)
        meta["pilot_solved"] = status != "TIMEOUT"
        if meta["pilot_solved"]:
            meta["gate_reason"] = "original_pilot_solved"
    if not meta["pilot_solved"]:
        remaining = CAP - (time.perf_counter() - started) - 0.08
        if variant == "reference_hybrid" and remaining > 0:
            try:
                with method.deadline(remaining):
                    source_path, extra, decision = certified.certified_preprocess(
                        source, "r193_hybrid4", rep, shard, started)
                meta.update(extra)
            except method.PreparationExpired:
                decision = "TIMEOUT"
                meta.update(preprocess_budget_exhausted=True,
                            gate_reason="reference_total_budget_expired",
                            preprocess_s=round(time.perf_counter() - started, 6))
        elif variant in ("sparse_budget", "pilot_sparse_budget") and remaining > 0:
            source_path, extra, decision = method.preprocess(
                source, rep, shard, ROOT / mode, min(method.PREP_CAP_S, remaining))
            meta.update(extra)
        if decision == "UNSAT":
            status = "UNSAT"
            proof = "SOURCE_GF2_CONTRADICTION_REPLAYED"
        elif decision != "TIMEOUT":
            remaining = CAP - (time.perf_counter() - started)
            status, model, rc = solve(backend, source_path, remaining)
    if status == "SAT":
        phase = time.perf_counter()
        _n, original = certified.gf_src.gf.dimacs(source)
        certified.gf_src.gf.sat_check(original, model)
        meta["verification_s"] = round(time.perf_counter() - phase, 6)
        proof = "SAT_WITNESS_ORIGINAL_VERIFIED"
    elif status == "UNSAT" and proof != "SOURCE_GF2_CONTRADICTION_REPLAYED":
        proof = "NO_INDEPENDENT_LRAT"
    elapsed = time.perf_counter() - started
    if elapsed >= CAP or status == "TIMEOUT":
        status, proof = "TIMEOUT", "CAP_TIMEOUT"
    if status != "TIMEOUT":
        need(status == case["expected"], "known source truth mismatch")
    row = {"id": case["id"], "sha256": case["sha256"], "family": case["family"],
           "group": case["group"], "mode": mode, "rep": rep, "shard": shard,
           "status": status, "proof": proof, "returncode": rc,
           "source_original_sha256": case["sha256"],
           "elapsed_s": round(min(CAP, elapsed), 6),
           "par2_s": round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
           **meta}
    print("TD2_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    return row


def shard(index):
    _cases, groups = verify()
    need(0 <= index < SHARDS, "bad shard")
    records = []
    for case in groups[index]:
        for rep in range(REPS):
            modes = list(MODES)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(modes)
            for mode in modes:
                records.append(trial(case, mode, rep, index))
                save(ROOT / f"shard-{index}.json", records)
    need(len(records) == len(groups[index]) * REPS * len(MODES), "partial shard")
    print("TD2_SHARD_PASS", index, len(records), flush=True)


def audit():
    cases, groups = verify()
    all_rows = []
    for shard_index, group in enumerate(groups):
        rows = json.loads((ROOT / f"shard-{shard_index}.json").read_text())
        expected = {(c["sha256"], rep, mode) for c in group
                    for rep in range(REPS) for mode in MODES}
        actual = {(r["sha256"], r["rep"], r["mode"]) for r in rows}
        need(actual == expected and len(rows) == len(expected), "incomplete/duplicate shard")
        for row in rows:
            need(row["shard"] == shard_index, "wrong shard")
            need(row["source_original_sha256"] == row["sha256"], "source drift")
            need(row["status"] in ("SAT", "UNSAT", "TIMEOUT"), "bad status")
            need(row["status"] != "SAT" or row["proof"] == "SAT_WITNESS_ORIGINAL_VERIFIED",
                 "missing original witness verification")
            penalty = 2 * CAP if row["status"] == "TIMEOUT" else row["elapsed_s"]
            need(abs(row["par2_s"] - penalty) < 0.00002, "PAR2 mismatch")
            case = next(c for c in group if c["sha256"] == row["sha256"])
            need(row["status"] == "TIMEOUT" or row["status"] == case["expected"],
                 "truth disagreement")
        all_rows.extend(rows)
    need(len(all_rows) == 640, "not 640 trials")
    reports = {}
    cohorts = {"all": cases}
    cohorts.update({g: [c for c in cases if c["group"] == g]
                    for g in sorted({c["group"] for c in cases})})
    for name, chosen in cohorts.items():
        shas = {c["sha256"] for c in chosen}
        rows = [r for r in all_rows if r["sha256"] in shas]
        metrics = {}
        for mode in MODES:
            selected = [r for r in rows if r["mode"] == mode]
            metrics[mode] = {"attempts": len(selected),
                "solved": sum(r["status"] != "TIMEOUT" for r in selected),
                "PAR2_s": round(sum(r["par2_s"] for r in selected), 6),
                "preprocess_s": round(sum(r["preprocess_s"] for r in selected), 6),
                "pilot_solved": sum(r["pilot_solved"] for r in selected),
                "prep_abstentions": sum(r["preprocess_budget_exhausted"] for r in selected)}
            if not mode.endswith("_plain"):
                baseline = { (r["sha256"], r["rep"]): r for r in rows
                             if r["mode"] == mode.split("_", 1)[0] + "_plain"}
                changes = [r["par2_s"] - baseline[(r["sha256"], r["rep"])]["par2_s"]
                           for r in selected]
                metrics[mode]["paired_vs_plain"] = {
                    "wins": sum(d < -0.001 for d in changes),
                    "losses": sum(d > 0.001 for d in changes),
                    "ties": sum(abs(d) <= 0.001 for d in changes),
                    "par2_gain_s": round(-sum(changes), 6)}
        reports[name] = metrics
    report = {"status": "TD2_AUDIT_PASS", "protocol": PROTO, "attempts": len(all_rows),
              "development_exposed_R199_sources": True, "blind_holdout": False,
              "cap_s_including_verification": CAP, "prep_cap_s": method.PREP_CAP_S,
              "pilot_cap_s": method.PILOT_CAP_S, "independent_backend_UNSAT_LRAT": False,
              "results": reports}
    save(ROOT / "report.json", report)
    save(ROOT / "all-trials.json", all_rows)
    lines = ["# TD2: bounded sparse GF2 development ablation", "",
             "40 exposed R199 original CNFs, 2 repeats, 8 arms, 640 trials. Not blind.",
             "20s wall cap includes pilot/restart, preparation and SAT verification.", "",
             "| Mode | Solved | PAR-2 s | Prep s | Pilot solved | W/L/T vs plain |",
             "|---|---:|---:|---:|---:|---|"]
    for mode, metric in reports["all"].items():
        pairs = metric.get("paired_vs_plain")
        pair_text = (f"{pairs['wins']}/{pairs['losses']}/{pairs['ties']}" if pairs else "baseline")
        lines.append(f"| {mode} | {metric['solved']}/{metric['attempts']} | "
                     f"{metric['PAR2_s']:.3f} | {metric['preprocess_s']:.3f} | "
                     f"{metric['pilot_solved']} | {pair_text} |")
    (ROOT / "summary.md").write_text("\n".join(lines) + "\n")
    print("TD2_AUDIT_PASS", json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    shard(args.shard) if args.action == "shard" else audit()
