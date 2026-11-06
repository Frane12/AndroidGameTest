#!/usr/bin/env python3
"""R160 paired confirmation of frozen R153 exact GF(2) + R135 structural fallback.
This is a REPLAY on R154's original 25 SHA-frozen formulas, NOT a fresh holdout.
The same frozen R153 binary is used as both standalone and R160's GF(2) kernel.
R160 only changes fallback selection (Kissat vs CaDiCaL). No CNF rewriting.
Every original SAT witness and every GF(2) UNSAT proof is independently checked.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import pathlib
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
sys.path.insert(0, "research")
import r153_repeat25_benchmark as r153audit

ROOT = pathlib.Path("r160")
SOURCE = ROOT / "source" / "frozen"
PROTO = "DRNAS-R160-R153-GF2-R135-STRUCTURAL-PAR2-REPLAY-20261106-v1"
CAP = 20.0
REPS = 2
SHARDS = 5
MODES = ("r153", "r160", "kissat", "cadical")
R153 = ROOT / "source" / "r153"
SELECTOR = ROOT / "r160_dispatch"
KISSAT = pathlib.Path("built/bin/kissat_4_0_4")
CADICAL = pathlib.Path("built/bin/cadical_3_0_1")


def need(condition, message):
    if not condition:
        raise RuntimeError("R160_AUDIT_FAIL " + str(message))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def write(path, obj):
    pathlib.Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def manifest():
    data = json.loads((SOURCE / "manifest.json").read_text())
    need(data["protocol"] == "DRNAS-R154-UNSEEN-LIGHTSOUT-XOR-UNIT-TRANSFER-20261105-v1", "source protocol mismatch")
    cases = data["cases"]
    need(len(cases) == 25, "expected exactly frozen original 25 formulas")
    need(len({x["sha256"] for x in cases}) == 25, "duplicate original SHA")
    for case in cases:
        need(sha(SOURCE / (case["id"] + ".cnf")) == case["sha256"], "original source modified " + case["id"])
    return data


def command(mode, cnf):
    if mode == "r153":
        return [str(R153.resolve()), str(cnf), str(KISSAT.resolve())]
    if mode == "r160":
        return [str(R153.resolve()), str(cnf), str(SELECTOR.resolve())]
    if mode == "kissat":
        return [str(KISSAT.resolve()), str(cnf)]
    if mode == "cadical":
        return [str(CADICAL.resolve()), str(cnf)]
    raise ValueError(mode)


def result_mode(mode, data):
    if mode not in ("r153", "r160"):
        return mode, None
    if b"R28_ROUTE certified_pure_xor_sat" in data:
        route = "gf2_sat"
    elif b"R28_ROUTE certified_xor_contradiction" in data:
        route = "gf2_unsat"
    else:
        need(b"R28_ROUTE fallback" in data, "no R153 kernel decision")
        route = "fallback"
    selector = re.search(rb"^c R160_SELECTOR route=(CADICAL|KISSAT) ", data, re.M)
    if mode == "r160":
        need(bool(selector) == (route == "fallback"), "R160 selected a solver on certified GF2 or missed fallback")
    else:
        need(not selector, "R153 baseline used R160 selector")
    return route, selector.group(1).decode() if selector else None


def trial(case, mode, rep):
    cnf = SOURCE / (case["id"] + ".cnf")
    need(sha(cnf) == case["sha256"], "source SHA drift")
    status = "TIMEOUT"
    seconds = CAP
    route = "timeout"
    selected = None
    proof = "timeout"
    start = time.perf_counter()
    try:
        proc = subprocess.run(command(mode, cnf), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=CAP)
        seconds = min(CAP, time.perf_counter() - start)
        need(proc.returncode in (10, 20), mode + " exit=" + str(proc.returncode) +
             " stderr=" + proc.stderr[-400:].decode(errors="replace"))
        status = "SAT" if proc.returncode == 10 else "UNSAT"
        route, selected = result_mode(mode, proc.stdout)
        if status == "SAT":
            r153audit.orig.sat_model_check(cnf, proc.stdout)
            proof = "original_CNF_SAT_witness_checked"
        elif route == "gf2_unsat":
            r153audit.replay_xor_unsat(cnf, proc.stdout)
            proof = "independent_original_CNF_GF2_UNSAT_replay"
        else:
            proof = "UNSAT_without_independent_LRAT"
        official = (case.get("official") or {}).get("best_verified")
        if official:
            need(official["status"].startswith(status.lower()), "official status conflict")
    except subprocess.TimeoutExpired:
        seconds = CAP
    return dict(id=case["id"], source_sha256=case["sha256"], cohort=case["cohort"],
                family=case["family"], mode=mode, repeat=rep, status=status,
                seconds=round(seconds, 6), par2=round(2 * CAP if status == "TIMEOUT" else seconds, 6),
                route=route, selected=selected, proof=proof)


def selftest():
    ROOT.mkdir(exist_ok=True)
    cases = [
        ("xor_sat", b"p cnf 2 2\n1 -2 0\n-1 2 0\n", "SAT", "gf2_sat", None),
        ("xor_unit_unsat", b"p cnf 2 4\n1 -2 0\n-1 2 0\n1 0\n-2 0\n", "UNSAT", "gf2_unsat", None),
        ("nonxor_horn", b"p cnf 3 120\n" + b"1 0\n" * 120, "SAT", "fallback", "KISSAT"),
        ("nonxor_cadical", b"p cnf 3 120\n" + b"1 2 3 0\n" * 120, "SAT", "fallback", "CADICAL"),
        ("mixed", b"p cnf 4 4\n1 -2 0\n-1 2 0\n3 4 0\n1 3 0\n", "SAT", "fallback", "KISSAT"),
    ]
    for name, raw, expected, expected_route, selected in cases:
        cnf = ROOT / ("smoke_" + name + ".cnf")
        cnf.write_bytes(raw)
        for mode in ("r153", "r160"):
            proc = subprocess.run(command(mode, cnf), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            need(proc.returncode == (10 if expected == "SAT" else 20),
                 name + " " + mode + " wrong solver return " + proc.stderr.decode(errors="replace")[-300:])
            route, actual = result_mode(mode, proc.stdout)
            need(route == expected_route, name + " wrong route " + route)
            if mode == "r160":
                need(actual == selected, name + " wrong R135 selector route " + str(actual))
            if expected == "SAT":
                r153audit.orig.sat_model_check(cnf, proc.stdout)
            elif route == "gf2_unsat":
                r153audit.replay_xor_unsat(cnf, proc.stdout)
            print("R160_SMOKE_PASS", name, mode, route, actual, flush=True)


def shard(index):
    need(0 <= index < SHARDS, "shard range")
    m = manifest()
    for p in (R153, SELECTOR, KISSAT, CADICAL):
        need(p.is_file(), "binary missing: " + str(p))
    selftest()
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    rows = []
    for j, case in enumerate(m["cases"]):
        if j % SHARDS != index:
            continue
        for rep in range(REPS):
            order = list(MODES)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(order)
            for mode in order:
                x = trial(case, mode, rep)
                rows.append(x)
                write(ROOT / ("shard-" + str(index) + ".json"), rows)
                print("R160_PAIRED", json.dumps(x, sort_keys=True), flush=True)
    need(len(rows) == len(m["cases"][index::SHARDS]) * REPS * len(MODES),
         "incomplete shard")
    print("R160_SHARD_PASS", index, len(rows), flush=True)


def audit():
    m = manifest()
    rows = []
    seen = set()
    pins = []
    for index in range(SHARDS):
        f = ROOT / ("shard-" + str(index) + ".json")
        need(f.is_file(), "missing shard: " + str(index))
        sample = json.loads(f.read_text())
        need(len(sample) == len(m["cases"][index::SHARDS]) * REPS * len(MODES),
             "incomplete shard: " + str(index))
        rows.extend(sample)
        pin = json.loads((ROOT / ("pin-" + str(index) + ".json")).read_text())
        pins.append(pin)
    need(len(rows) == 25 * 2 * 4, "incorrect row count")
    need(len({json.dumps(p["binaries"], sort_keys=True) for p in pins}) == 1, "binary hash drift")
    need(len({p["cpu"] for p in pins}) == 1, "CPU type drift")
    groups = defaultdict(list)
    known = {c["id"]: c for c in m["cases"]}
    for row in rows:
        need(row["id"] in known and row["source_sha256"] == known[row["id"]]["sha256"],
             "SHA mismatch")
        key = (row["id"], row["repeat"], row["mode"])
        need(key not in seen, "duplicate trial")
        seen.add(key)
        need(row["repeat"] in range(REPS) and row["mode"] in MODES, "invalid trial")
        need(row["status"] in ("SAT", "UNSAT", "TIMEOUT"), "invalid status")
        need(abs(row["par2"] - (40.0 if row["status"] == "TIMEOUT" else row["seconds"])) < 0.00001, "PAR2 invalid")
        if row["status"] == "SAT":
            need(row["proof"] == "original_CNF_SAT_witness_checked", "missing checked SAT model")
        if row["route"] == "gf2_unsat":
            need(row["proof"] == "independent_original_CNF_GF2_UNSAT_replay", "missing certified XOR proof")
        groups[row["id"]].append(row)
    for case in m["cases"]:
        rr = groups[case["id"]]
        need(len(rr) == REPS * len(MODES), "incomplete formula pairs")
        need(len({r["status"] for r in rr if r["status"] != "TIMEOUT"}) <= 1,
             "SAT UNSAT mismatch: " + case["id"])
        for rep in range(REPS):
            by = {r["mode"]: r for r in rr if r["repeat"] == rep}
            if by["r153"]["route"] in ("gf2_sat", "gf2_unsat") and by["r160"]["status"] != "TIMEOUT":
                need(by["r160"]["route"] == by["r153"]["route"],
                     "GF2 kernel route changed: " + case["id"])
    cohorts = {}
    for group in ("all", "complete_xor", "xor_plus_units", "mixed_residual", "nonxor_control"):
        selected = [r for r in rows if group == "all" or r["cohort"] == group]
        cohorts[group] = {}
        for mode in MODES:
            r = [x for x in selected if x["mode"] == mode]
            cohorts[group][mode] = dict(trials=len(r),
                                        solved=sum(x["status"] != "TIMEOUT" for x in r),
                                        par2_s=round(sum(x["par2"] for x in r), 6),
                                        routes=dict(Counter(x["route"] for x in r)),
                                        fallback_choices=dict(Counter(x["selected"] for x in r if x["selected"])))
        a = cohorts[group]["r153"]["par2_s"]
        b = cohorts[group]["r160"]["par2_s"]
        cohorts[group]["r160"]["par2_delta_vs_r153_s"] = round(b-a, 6)
        cohorts[group]["r160"]["gain_vs_r153_pct"] = round(100*(a-b)/a, 4) if a else None
    pairs = []
    for case in m["cases"]:
        for rep in range(REPS):
            z = {x["mode"]: x for x in groups[case["id"]] if x["repeat"] == rep}
            pairs.append(dict(id=case["id"], cohort=case["cohort"], rep=rep,
                              r153_par2=z["r153"]["par2"], r160_par2=z["r160"]["par2"],
                              gain_s=round(z["r153"]["par2"]-z["r160"]["par2"], 6),
                              route=z["r160"]["route"], selected=z["r160"]["selected"]))
    report = dict(protocol=PROTO, status="AUDIT_PASS", formula_count=25, repetitions=REPS,
                  attempts=len(rows), cap_s=CAP, par2_timeout_penalty_s=40,
                  reused_source_run_id=42128549081,
                  corpus="SAME 25 R154 frozen originals as R153 confirmation; replay NOT independent holdout",
                  unchanged_gf2_binary_sha256=sha(R153),
                  source_manifest_sha256=sha(SOURCE / "manifest.json"),
                  binary_pins=pins[0]["binaries"], cpu=pins[0]["cpu"],
                  methodological_note="R160 reuses bit-identical R153 executable and changes only certified fallback dispatch via frozen R135 rule; all times include both prepasses",
                  proof_note="SAT witnesses checked against original CNF; source-implied GF(2) UNSAT proofs replayed independently. Fallback UNSAT lacks independent LRAT.",
                  cohorts=cohorts, paired_gains=pairs,
                  pair_counts=dict(improved=sum(p["gain_s"] > 0.001 for p in pairs),
                                   regressed=sum(p["gain_s"] < -0.001 for p in pairs),
                                   near_equal=sum(abs(p["gain_s"]) <= 0.001 for p in pairs)))
    write(ROOT / "report.json", report)
    with (ROOT / "paired.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("R160_AUDIT_PASS", json.dumps({"all": cohorts["all"], "pair_counts": report["pair_counts"],
                                         "attempts": len(rows)}, sort_keys=True), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "shard", "audit"))
    p.add_argument("--shard", type=int, default=0)
    args = p.parse_args()
    {"selftest": selftest, "shard": lambda: shard(args.shard), "audit": audit}[args.action]()
