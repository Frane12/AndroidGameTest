#!/usr/bin/env python3
"""TURN2H: one change only, certified R28 GF(2) gate before TURN2 Signed Kissat.

Development replication on the *already seen* TURN2 original12 cohort. Neither
the source set nor the transform uses outcomes. This is NOT a blind holdout.
Only verified SAT models or independently replayed R28 XOR contradictions
count as solved; native UNSAT without independent proof is scored as timeout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time

import drnas_turn2_structural as turn

ROOT = Path("turn2h")
CAP, REPS, SHARDS = 60., 3, 12
MODES = ("kissat_plain", "kissat_struct_signed", "r28_optimized", "turn2_signed_r28")
PROTO = "DRNAS-TURN2H-ORIGINAL12-4ARMS-3REPS-60S-v1"
R28 = Path("optimized/r28").resolve()
KISSAT = Path(turn.KISSAT).resolve()


def need(ok, msg):
    if not ok:
        raise RuntimeError("TURN2H_FAIL_CLOSED " + str(msg))


def save(path, data):
    turn.save(path, data)


def replay_xor_unsat(clauses, stdout):
    """Replay R28's trace independently against COMPLETE exact CNF XOR blocks."""
    if "c R28_ROUTE certified_xor_contradiction" not in stdout:
        return False
    equations = {}
    for m in re.finditer(r"^c R28_EQ id=(\d+) rhs=([01]) vars=([0-9,]+)\s*$", stdout, re.M):
        idx = int(m.group(1))
        vars_ = tuple(int(s) for s in m.group(3).split(","))
        need(idx not in equations and 2 <= len(vars_) <= 6 and
             vars_ == tuple(sorted(set(vars_))), "invalid R28 equation")
        equations[idx] = (vars_, int(m.group(2)))
    cert = re.search(r"^c R28_UNSAT_CERT ids=([0-9,]+)\s*$", stdout, re.M)
    need(cert is not None and equations, "missing R28 proof rows")
    selected = [int(x) for x in cert.group(1).split(",")]
    need(selected and len(set(selected)) == len(selected) and
         all(i in equations for i in selected), "bad XOR combination")
    chosen = {equations[i][0] for i in selected}
    masks = {v: set() for v in chosen}
    for clause in clauses:
        v = tuple(sorted(abs(x) for x in clause))
        if v not in masks or len(clause) != len(v) or len(set(map(abs, clause))) != len(v):
            continue
        signs = {abs(x): x < 0 for x in clause}
        masks[v].add(sum(int(signs[x]) << k for k, x in enumerate(v)))
    xor_vars = set()
    rhs = 0
    for i in selected:
        v, bit = equations[i]
        required_parity = 0 if bit == 1 else 1
        need(all(m in masks[v] for m in range(1 << len(v))
                 if m.bit_count() % 2 == required_parity),
             "XOR premise missing exact CNF masks")
        xor_vars.symmetric_difference_update(v)
        rhs ^= bit
    return not xor_vars and rhs == 1


def worker(source, mode, directory):
    start = time.perf_counter()
    n, original = turn.t1.parse(source)
    signed = mode in ("kissat_struct_signed", "turn2_signed_r28")
    if signed:
        clauses, mapping = turn.transformation(n, original, "kissat_struct_signed")
    else:
        clauses, mapping = original, list(range(n + 1))
    path = Path(source)
    if signed:
        path = Path(directory) / "signed.cnf"
        turn.t1.write_cnf(path, n, clauses)
    prep = time.perf_counter() - start
    command = ([str(R28), str(path.resolve()), str(KISSAT)]
               if mode in ("r28_optimized", "turn2_signed_r28")
               else [str(KISSAT), str(path.resolve())])
    print(json.dumps(dict(event="start", command=command, prep_s=prep,
                          transformed_sha256=turn.sha(path))), flush=True)
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    Path(directory, "solver.log").write_text(result.stdout)
    answers = re.findall(r"^s (SATISFIABLE|UNSATISFIABLE)\s*$", result.stdout, re.M)
    need(len(answers) == 1 and result.returncode == (10 if answers[0] == "SATISFIABLE" else 20),
         "solver did not deliver an unambiguous result")
    verdict = "SAT" if answers[0] == "SATISFIABLE" else "UNSAT"
    proof = "UNSAT_REPORTED_NO_INDEPENDENT_CERTIFICATE"
    if verdict == "SAT":
        model = {}
        for line in result.stdout.splitlines():
            if line.startswith("v "):
                for token in line[2:].split():
                    lit = int(token)
                    if lit:
                        need(abs(lit) not in model or model[abs(lit)] == (lit > 0),
                             "conflicting model literal")
                        model[abs(lit)] = lit > 0
        model = turn.t1.inverse_model(model, mapping)
        need(turn.t1.satisfies(original, model), "SAT model fails original CNF")
        save(Path(directory) / "model.json", model)
        proof = "SAT_ORIGINAL_MODEL_VERIFIED"
    elif mode in ("r28_optimized", "turn2_signed_r28"):
        if replay_xor_unsat(clauses, result.stdout):
            proof = "R28_EXACT_XOR_UNSAT_REPLAYED_ORIGINAL_EQUIVALENT"
    route = re.search(r"^c R28_ROUTE (.+)$", result.stdout, re.M)
    rprep = re.search(r"^c R28_PREP_S ([0-9.eE+-]+)$", result.stdout, re.M)
    print(json.dumps(dict(event="result", verdict=verdict, proof=proof,
        prep_s=prep, r28_route=route.group(1) if route else None,
        r28_prep_s=float(rprep.group(1)) if rprep else None,
        transformed_sha256=turn.sha(path),
        cpu_user_s=round(after.ru_utime - before.ru_utime, 6),
        cpu_system_s=round(after.ru_stime - before.ru_stime, 6))), flush=True)


def verify():
    cases = turn.verify()
    data = json.loads((ROOT / "manifest.json").read_text())
    need(data["protocol"] == PROTO and data["modes"] == list(MODES)
         and data["cap_s"] == CAP and data["repetitions"] == REPS,
         "protocol manifest drift")
    need(data["original_turn2_manifest_sha256"] == turn.sha("turn2/manifest.json"),
         "source manifest drift")
    for p, digest in json.loads((ROOT / "pins.json").read_text()).items():
        need(turn.sha(p) == digest, "pin drift " + p)
    return cases


def trial(c, mode, rep, shard):
    source = turn.SOURCE / (c["id"] + ".cnf")
    need(turn.sha(source) == c["sha256"], "original source SHA drift")
    directory = ROOT / "raw" / str(shard) / (str(rep) + "-" + mode)
    directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    p = subprocess.Popen([sys.executable, __file__, "worker",
                          "--source", str(source), "--mode", mode,
                          "--directory", str(directory)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True)
    timed_out = False
    try:
        output, _ = p.communicate(timeout=max(.001, CAP - (time.perf_counter() - started)))
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = p.communicate()
    elapsed = min(CAP, time.perf_counter() - started)
    (directory / "worker.log").write_text(output)
    events = []
    for line in output.splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
        except ValueError:
            pass
    starts = [e for e in events if e.get("event") == "start"]
    ends = [e for e in events if e.get("event") == "result"]
    status, reported, proof = "TIMEOUT", None, "WALL_CAP_TIMEOUT"
    prep = rprep = transformed = route = None
    cpu_user = cpu_system = None
    if not timed_out and elapsed < CAP:
        need(p.returncode == 0 and len(starts) == len(ends) == 1,
             "worker failure: " + output[-2000:])
        event = ends[0]
        reported, proof = event["verdict"], event["proof"]
        status = reported if (reported == "SAT" or
                 proof == "R28_EXACT_XOR_UNSAT_REPLAYED_ORIGINAL_EQUIVALENT") else "TIMEOUT"
        prep, rprep = event["prep_s"], event["r28_prep_s"]
        transformed, route = event["transformed_sha256"], event["r28_route"]
        cpu_user, cpu_system = event["cpu_user_s"], event["cpu_system_s"]
        if status == "TIMEOUT":
            proof = "UNSAT_UNCERTIFIED_NOT_SCORED"
    if status == "SAT":
        model = {int(k): v for k, v in json.loads((directory / "model.json").read_text()).items()}
        need(turn.t1.satisfies(turn.t1.parse(source)[1], model),
             "independent original SAT model recheck")
    if (directory / "signed.cnf").exists():
        (directory / "signed.cnf").unlink()
    row = dict(protocol=PROTO, id=c["id"], sha256=c["sha256"],
        mode=mode, rep=rep, shard=shard, status=status,
        reported_status=reported, proof=proof, elapsed_s=round(elapsed, 6),
        par2_s=round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
        prep_s=prep, r28_prep_s=rprep, r28_route=route,
        transformed_sha256=transformed,
        cpu_user_s=cpu_user, cpu_system_s=cpu_system, one_cpu=True)
    print("TURN2H_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    return row


def prepare():
    turn.verify()
    turn.selftest()
    need(KISSAT.is_file() and R28.is_file(), "pinned native solvers absent")
    ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for expected, clauses in (("SAT", [[1], [-1, 2]]),
                                  ("UNSAT", [[1], [-1]])):
            source = Path(tmp) / (expected + ".cnf")
            turn.t1.write_cnf(source, 3, clauses)
            for mode in MODES:
                directory = Path(tmp) / (mode + "-" + expected)
                directory.mkdir()
                result = subprocess.run([sys.executable, __file__, "worker",
                    "--source", str(source), "--mode", mode,
                    "--directory", str(directory)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, timeout=15)
                need(result.returncode == 0, "smoke crash " + mode + " " + (result.stdout or "")[-1600:] + (result.stderr or "")[-1600:])
                event = json.loads(result.stdout.splitlines()[-1])
                need(event["verdict"] == expected, "smoke wrong result " + mode)
                if expected == "SAT":
                    need(event["proof"] == "SAT_ORIGINAL_MODEL_VERIFIED",
                         "smoke invalid SAT")
    save(ROOT / "manifest.json", dict(protocol=PROTO,
        modes=MODES, cap_s=CAP, repetitions=REPS, shards=SHARDS,
        cohort="same 12 frozen TURN2 original SHA, developmental known-outcome cohort",
        original_turn2_run=42420269832,
        original_turn2_manifest_sha256=turn.sha("turn2/manifest.json"),
        development_not_blind=True, source_sha_locked=True,
        primary="turn2_signed_r28 vs kissat_struct_signed",
        matched_ablations=["kissat_plain", "r28_optimized", "kissat_struct_signed"],
        scoring="SAT original model verified or R28 exact XOR contradiction independently replayed; unproven UNSAT is timeout",
        seeds="deterministic by protocol + frozen source SHA + repeat; no outcome used by solver",
        do_not_promote_without_new_holdout=True))
    pins = ["research/drnas_turn2_hybrid.py", "research/drnas_turn2_structural.py",
            "research/drnas_turn1_representation.py", "research/r28_w4_optimized.cpp",
            ".github/workflows/drnas-turn2-hybrid.yml", "optimized/r28",
            "built/bin/kissat_4_0_4", "turn2/manifest.json",
            "turn2/pins.json", str(ROOT / "manifest.json")]
    save(ROOT / "pins.json", {p: turn.sha(p) for p in pins})
    verify()
    print("TURN2H_PREPARE_PASS", turn.sha(ROOT / "manifest.json"), flush=True)


def shard(index):
    cases = verify()
    need(0 <= index < SHARDS, "invalid shard")
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    c = cases[index]
    rows = []
    for rep in range(REPS):
        order = list(MODES)
        random.Random(PROTO + c["sha256"] + str(rep)).shuffle(order)
        for mode in order:
            rows.append(trial(c, mode, rep, index))
            save(ROOT / ("shard-%d.json" % index), rows)
    need(len(rows) == len(MODES) * REPS, "partial shard")
    print("TURN2H_SHARD_PASS", index, len(rows), flush=True)


def audit():
    cases = verify()
    allrows, keys = [], set()
    for index, c in enumerate(cases):
        rows = json.loads((ROOT / ("shard-%d.json" % index)).read_text())
        need(len(rows) == REPS * len(MODES), "partial shard " + str(index))
        for row in rows:
            key = row["sha256"], row["rep"], row["mode"]
            need(key not in keys and row["sha256"] == c["sha256"] and
                 row["id"] == c["id"] and row["shard"] == index and
                 row["protocol"] == PROTO and row["mode"] in MODES and
                 row["rep"] in range(REPS), "trial provenance mismatch")
            keys.add(key)
            need(row["status"] in ("SAT", "UNSAT", "TIMEOUT"), "bad verdict")
            need(0 <= row["elapsed_s"] <= CAP, "wall cap")
            need(abs(row["par2_s"] - (2 * CAP if row["status"] == "TIMEOUT"
                                     else row["elapsed_s"])) < .00002, "PAR2")
            need(row["status"] != "SAT" or
                 row["proof"] == "SAT_ORIGINAL_MODEL_VERIFIED", "unverified SAT")
            need(row["status"] != "UNSAT" or
                 row["proof"] == "R28_EXACT_XOR_UNSAT_REPLAYED_ORIGINAL_EQUIVALENT",
                 "unverified UNSAT")
            allrows.append(row)
        need(len({r["status"] for r in rows if r["status"] != "TIMEOUT"}) <= 1,
             "contradictory verdict")
    expected = {(c["sha256"], rep, mode) for c in cases
                for rep in range(REPS) for mode in MODES}
    need(keys == expected and len(allrows) == 144, "missing trials")
    totals = {}
    bykey = {(r["sha256"], r["rep"], r["mode"]): r for r in allrows}
    for mode in MODES:
        rr = [r for r in allrows if r["mode"] == mode]
        totals[mode] = dict(attempts=len(rr),
            solved=sum(r["status"] != "TIMEOUT" for r in rr),
            SAT=sum(r["status"] == "SAT" for r in rr),
            UNSAT_verified=sum(r["status"] == "UNSAT" for r in rr),
            UNSAT_unverified=sum(r["reported_status"] == "UNSAT" and
                                 r["status"] == "TIMEOUT" for r in rr),
            PAR2_s=round(sum(r["par2_s"] for r in rr), 6),
            prep_s_total=round(sum(r["prep_s"] or 0 for r in rr), 6),
            r28_prep_s_total=round(sum(r["r28_prep_s"] or 0 for r in rr), 6))
    gains = []
    for c in cases:
        a = sum(bykey[c["sha256"], rep, "kissat_struct_signed"]["par2_s"]
                for rep in range(REPS))
        b = sum(bykey[c["sha256"], rep, "turn2_signed_r28"]["par2_s"]
                for rep in range(REPS))
        gains.append(dict(id=c["id"], source_sha256=c["sha256"],
                          signed_PAR2_s=round(a,6), hybrid_PAR2_s=round(b,6),
                          signed_minus_hybrid_s=round(a-b,6)))
    report = dict(status="TURN2H_AUDIT_PASS", protocol=PROTO, attempts=len(allrows),
        sources=len(cases), original_turn2_manifest_sha256=turn.sha("turn2/manifest.json"),
        results=totals, primary_source_deltas=gains,
        primary_gain_PAR2_s=round(totals["kissat_struct_signed"]["PAR2_s"] -
                                  totals["turn2_signed_r28"]["PAR2_s"], 6),
        primary_ratio=(totals["kissat_struct_signed"]["PAR2_s"] /
                       totals["turn2_signed_r28"]["PAR2_s"]),
        global_blind=False, independent_native_UNSAT_proof=False,
        R28_exact_XOR_UNSAT_replay=True, promotion_allowed=False)
    save(ROOT / "report.json", report)
    save(ROOT / "all-trials.json", allrows)
    text = ["# TURN2H — Signed + R28 certified hybrid", "",
      "12 seen, SHA-frozen TURN2 originals; 4 arms, 3 reps, 60s cap. Not blind.",
      "Uncertified native UNSAT is not scored as solved. All SAT verified on original.",
      "", "| Mode | Solved / 36 | SAT | Certified UNSAT | Unproven UNSAT | PAR2 s |",
      "|---|---:|---:|---:|---:|---:|"]
    for mode, m in totals.items():
        text.append(f"| {mode} | {m['solved']} | {m['SAT']} | {m['UNSAT_verified']} | {m['UNSAT_unverified']} | {m['PAR2_s']:.6f} |")
    text.extend(["", f"Signed-only minus hybrid PAR2: {report['primary_gain_PAR2_s']:.6f} s",
                 "Promotion prohibited pending fresh source-disjoint holdout."])
    (ROOT / "report.md").write_text("\n".join(text) + "\n")
    print("TURN2H_FINAL", json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("worker", "prepare", "shard", "audit"))
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--source")
    p.add_argument("--mode", choices=MODES)
    p.add_argument("--directory")
    args = p.parse_args()
    if args.action == "worker":
        worker(args.source, args.mode, args.directory)
    elif args.action == "shard":
        shard(args.shard)
    else:
        globals()[args.action]()
