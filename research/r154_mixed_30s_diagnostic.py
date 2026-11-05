#!/usr/bin/env python3
"""R154 MIX diagnostic: SAME frozen 12 real mixed XOR/CNF sources as 6s trial.

30s paired wall clock and a derived 15s horizon; no claim this is a new holdout.
Capture R153's flushed decision/fallback trace even if the subprocess times out.
The solver binaries and their behavior are unchanged.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import pathlib
import random
import re
import statistics
import subprocess
import time

ROOT = pathlib.Path("r154mix30")
SOURCE_PROTOCOL = "DRNAS-R154-MIX-SHORT-NEW-SHA-20261105-v1"
PROTOCOL = "DRNAS-R154-MIX-30S-SAME-12-DIAGNOSTIC-20261105-v1"
SOURCE_RUN = 42112341909
CAP = 30.0
SHORT_CAP = 15.0
SHARDS = 4
MODES = ("r28", "r153", "kissat", "cadical")


def load_bench():
    spec = importlib.util.spec_from_file_location("r154_mix_30_core", "research/r154_unseen_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.PROTO = SOURCE_PROTOCOL  # Only for verifying previously frozen original CNFs
    module.CAP = CAP
    module.SHARDS = SHARDS
    module.BINARIES = {
        "r28": ROOT / "r28",
        "r153": ROOT / "r153",
        "kissat": pathlib.Path("built/bin/kissat_4_0_4"),
        "cadical": pathlib.Path("built/bin/cadical_3_0_1"),
    }
    return module


def verify_source(m):
    frozen = m.manifest()
    m.need(len(frozen["cases"]) == 12, "must reuse exactly the original R154 MIX 12")
    m.need(frozen["cohort_counts"] == {"mixed_residual": 12}, "unexpected source cohorts")
    m.need(all(c["structural"]["original_xor_covered_clauses"] > 0
               and c["structural"]["uncovered_nonunit_clauses"] > 0
               for c in frozen["cases"]), "not mixed original XOR/CNF")
    m.need(frozen["phase"] == "FROZEN_BEFORE_FIRST_R154_SOLVER_TIMING", "source freeze missing")
    return frozen


def extract_r153_trace(stdout):
    match = re.search(
        rb"c R153_DECISION_US (\d+) outcome=([a-z_]+) clauses=(\d+) covered=(\d+) units=(\d+)",
        stdout,
    )
    if not match:
        return dict(detector_us=None, detector_outcome="not_observed", clauses_seen=None,
                    clauses_covered=None, units_seen=None)
    return dict(
        detector_us=int(match[1]), detector_outcome=match[2].decode(),
        clauses_seen=int(match[3]), clauses_covered=int(match[4]),
        units_seen=int(match[5]),
    )


def trial(m, case, mode, repeat):
    cnf = ROOT / "frozen" / (case["id"] + ".cnf")
    m.need(m.sha(cnf) == case["sha256"], "frozen original SHA changed " + case["id"])
    argv = [str(m.BINARIES[mode]), str(cnf)]
    if mode in ("r153", "r28"):
        argv.append(str(m.BINARIES["kissat"]))
    started = time.perf_counter()
    output = b""
    status = "TIMEOUT"
    elapsed = CAP
    proof = "timeout"
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=CAP)
        elapsed = min(CAP, time.perf_counter() - started)
        output = proc.stdout or b""
        m.need(proc.returncode in (10, 20),
               f"{mode} abnormal exit {proc.returncode}: " + proc.stderr[-250:].decode(errors="replace"))
        status = "SAT" if proc.returncode == 10 else "UNSAT"
    except subprocess.TimeoutExpired as exc:
        # Unlike the 6s pilot, retain already-flushed R153 telemetry on timeouts.
        output = exc.stdout or exc.output or b""
        elapsed = CAP

    if mode in ("r153", "r28"):
        if b"R28_ROUTE certified_pure_xor_sat" in output:
            route = "gf2_sat"
        elif b"R28_ROUTE certified_xor_contradiction" in output:
            route = "gf2_unsat"
        elif b"R28_ROUTE fallback" in output:
            route = "fallback"
        else:
            route = "decision_not_observed"
    else:
        route = mode

    trace = extract_r153_trace(output) if mode == "r153" else dict(
        detector_us=None, detector_outcome=None, clauses_seen=None,
        clauses_covered=None, units_seen=None,
    )
    if mode == "r153" and status != "TIMEOUT":
        m.need(trace["detector_us"] is not None, "completed R153 without decision trace")
    reason = re.search(rb"c R28_ROUTE fallback reason=([a-z_]+)", output)
    fallback_reason = reason[1].decode() if reason else None

    if status == "SAT":
        m.orig.sat_model_check(cnf, output)
        proof = "original_CNF_SAT_model_checked"
    elif status == "UNSAT":
        if route == "gf2_unsat":
            m.replay_xor_unsat(cnf, output)
            proof = "independently_replayed_original_XOR_unit_UNSAT"
        else:
            proof = "UNSAT_without_independent_LRAT"
    published = (case.get("official") or {}).get("best_verified")
    if published and status != "TIMEOUT":
        m.need(published["status"].startswith(status.lower()), "verified original status mismatch")

    decision_s = None if trace["detector_us"] is None else trace["detector_us"] / 1_000_000.0
    fallback_s = None
    if mode == "r153" and route == "fallback" and decision_s is not None:
        fallback_s = round(max(0.0, elapsed - decision_s), 6)
    return dict(
        id=case["id"], cohort=case["cohort"], family=case["family"], sha256=case["sha256"],
        mode=mode, repeat=repeat, status=status, seconds=round(elapsed, 6),
        par2=round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
        route=route, proof=proof, detector_us=trace["detector_us"],
        detector_outcome=trace["detector_outcome"],
        fallback_reason=fallback_reason, clauses_seen=trace["clauses_seen"],
        clauses_covered=trace["clauses_covered"], units_seen=trace["units_seen"],
        fallback_wall_s_approx=fallback_s,
        fallback_time_censored=(mode == "r153" and route == "fallback" and status == "TIMEOUT"),
    )


def run_shard(m, number):
    m.need(0 <= number < SHARDS, "invalid shard")
    m.manifest()
    if hasattr(m.os, "sched_getaffinity"):
        m.os.sched_setaffinity(0, {min(m.os.sched_getaffinity(0))})
    m.selftest()
    rows = []
    for index, case in enumerate(verify_source(m)["cases"]):
        if index % SHARDS != number:
            continue
        for repeat in range(2):
            order = list(MODES)
            random.Random(PROTOCOL + case["sha256"] + str(repeat)).shuffle(order)
            for mode in order:
                row = trial(m, case, mode, repeat)
                rows.append(row)
                m.write(ROOT / f"shard-{number}.json", rows)
                print("R154_MIX30_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    m.need(len(rows) == 24, "shard must contain 3 CNFs x 2 repetitions x 4 solvers")
    print("R154_MIX30_SHARD_PASS", number, len(rows), flush=True)


def diagnostic_audit(m):
    frozen = verify_source(m)
    # Reuses core audit for source SHA, original models/proofs, four-way pairing,
    # immutable binary pins, PAR2, regressions and final CSV generation.
    m.audit()
    report = m.read(ROOT / "report.json")
    rows = [row for i in range(SHARDS) for row in m.read(ROOT / f"shard-{i}.json")]
    m.need(len(rows) == 96, "expected exactly 96 trials")
    m.need(report["status"] == "AUDIT_PASS", "core audit did not pass")
    by_mode = {}
    for mode in MODES:
        subset = [r for r in rows if r["mode"] == mode]
        horizon15 = [r for r in subset if r["status"] != "TIMEOUT" and r["seconds"] <= SHORT_CAP]
        decision_us = [r["detector_us"] for r in subset if r["detector_us"] is not None]
        fallback = [r for r in subset if r["route"] == "fallback"]
        by_mode[mode] = dict(
            trials=len(subset),
            solved_by_15s=len(horizon15),
            solved_by_30s=sum(r["status"] != "TIMEOUT" for r in subset),
            par2_15_s=round(sum(r["seconds"] if r in horizon15 else 2 * SHORT_CAP for r in subset), 6),
            par2_30_s=round(sum(r["par2"] for r in subset), 6),
            detector_us_p50=round(statistics.median(decision_us), 3) if decision_us else None,
            detector_trace_observed=len(decision_us),
            fallback_cases=len(fallback),
            fallback_reasons={reason: sum(r["fallback_reason"] == reason for r in fallback)
                              for reason in sorted({r["fallback_reason"] for r in fallback if r["fallback_reason"]})},
            fallback_wall_estimates_s=[
                {"id": r["id"], "repeat": r["repeat"], "approx_s": r["fallback_wall_s_approx"],
                 "right_censored": r["fallback_time_censored"]}
                for r in fallback
            ],
            unresolved_detector_timeouts=sum(r["status"] == "TIMEOUT"
                                            and r["route"] == "decision_not_observed" for r in subset),
        )
    report.update(
        protocol=PROTOCOL,
        source_run_id=SOURCE_RUN,
        source_protocol=SOURCE_PROTOCOL,
        source_is_reused_6s_holdout=True,
        not_independent_holdout=True,
        benchmark_reuses_R154_MIX_seen_12_originals=True,
        cap_s=CAP,
        diagnostics=dict(
            comparison_horizons_seconds=[SHORT_CAP, CAP],
            by_mode=by_mode,
            source_cohort="mixed_residual",
            frozen_source_count=len(frozen["cases"]),
            fallback_measurement_note="approx wall minus R153 reported decision time; on timeouts the fallback elapsed time is right-censored at 30s",
            no_new_holdout_claim=True,
        ),
    )
    m.write(ROOT / "report.json", report)
    for mode in MODES:
        print("R154_MIX30_MODE", mode, json.dumps(by_mode[mode], sort_keys=True), flush=True)
    print("R154_MIX30_FINAL", json.dumps({
        "formulas": len(frozen["cases"]), "attempts": len(rows),
        "by_mode": {k: {x: v[x] for x in (
            "solved_by_15s", "solved_by_30s", "par2_15_s", "par2_30_s",
            "detector_us_p50", "fallback_cases", "unresolved_detector_timeouts")}
            for k, v in by_mode.items()},
    }, sort_keys=True), flush=True)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("shard", "audit"))
    cli.add_argument("--shard", type=int, default=0)
    args = cli.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    core = load_bench()
    if args.action == "shard":
        run_shard(core, args.shard)
    else:
        diagnostic_audit(core)


if __name__ == "__main__":
    main()
