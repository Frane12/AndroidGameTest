#!/usr/bin/env python3
"""WorldSim W2: longer, resource-bounded exploration of W1's 17 unsolved CNFs.

Stages: all six W1 configurations at 180s, then four diverse configurations
at 600s only on formulas not solved in stage 180. One repetition per stage.
No performance-informed selection within a stage. UNSAT reports are not
independently certificate-verified. W1 source/binary pins remain mandatory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import threading
from pathlib import Path
import random
import statistics
import sys
import time

sys.path.insert(0, str(Path("research").resolve()))
import drnas_worldsim_w1 as w1

ROOT = Path("worldsim_w2")
W1_RUN = 42397824391
S180 = tuple(w1.MODES)
S600 = ("r28_kissat", "satsuma_iter_kissat_2026", "kissat_404", "cadical_301")
SHARDS = 8
PROTOCOL = "DRNAS-WORLDSIM-W2-W1UNSOLVED17-180-600-20261107-v1"

def require(condition, message):
    if not condition:
        raise RuntimeError("W2_FAIL_CLOSED " + message)

def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def original():
    manifest = w1.verify_pins()
    require(manifest["protocol"] == w1.PROTO, "W1 protocol changed")
    return manifest

def check_w1_report(path, manifest):
    data = json.loads(Path(path).read_text())
    cases = {c["sha256"]: c for c in manifest["cases"]}
    require(len(cases) == 24 and len(data) == 432, "W1 24x6x3 results missing")
    bykey = {}
    for r in data:
        key = (r["sha256"], r["rep"], r["mode"])
        require(r["sha256"] in cases and r["id"] == cases[r["sha256"]]["id"], "W1 identity")
        require(r["rep"] in (0, 1, 2) and r["mode"] in S180, "W1 key")
        require(r["status"] in ("TIMEOUT", "SAT", "UNSAT"), "W1 status")
        require(key not in bykey, "W1 duplicate")
        bykey[key] = r
    require(len(bykey) == 432, "W1 incomplete")
    selected = []
    for c in manifest["cases"]:
        if all(bykey[(c["sha256"], rep, mode)]["status"] == "TIMEOUT"
               for rep in range(3) for mode in S180):
            selected.append({"id": c["id"], "sha256": c["sha256"],
                             "expected": c.get("expected", "UNKNOWN")})
    require(len(selected) == 17, "W1 unsolved cohort is not 17")
    return sorted(selected, key=lambda x: x["sha256"])

def cohort(path):
    obj = json.loads(Path(path).read_text())
    require(obj["protocol"] == PROTOCOL and obj["w1_run_id"] == W1_RUN, "wrong cohort")
    manifest = original()
    known = {c["sha256"]: c for c in manifest["cases"]}
    for c in obj["cases"]:
        require(c["sha256"] in known and c["id"] == known[c["sha256"]]["id"], "unknown formula")
        require(sha(Path("ta3_2026/sources") / (c["id"] + ".cnf")) == c["sha256"],
                "source SHA drift")
    return obj

def prep(directory):
    manifest = original()
    matches = list(Path(directory).rglob("all_trials.json"))
    require(len(matches) == 1, "expected W1 final all_trials.json")
    cases = check_w1_report(matches[0], manifest)
    obj = {"protocol": PROTOCOL, "w1_run_id": W1_RUN,
           "w1_report_sha256": sha(matches[0]), "w1_manifest_sha256": sha("worldsim_w1/manifest.json"),
           "stage180_cap_s": 180, "stage600_cap_s": 600,
           "stage180_modes": S180, "stage600_modes": S600,
           "cases": cases, "exploratory_single_rep": True,
           "proof_output": "discarded_or_bounded_no_independent_UNSAT_verification"}
    save(ROOT / "freeze.json", obj)
    print("W2_FREEZE_PASS", json.dumps({"unresolved":len(cases),
          "w1_report_sha256":obj["w1_report_sha256"]}), flush=True)

def run_one(c, mode, cap, stage, shard):
    source = Path("ta3_2026/sources") / (c["id"] + ".cnf")
    require(sha(source) == c["sha256"], "source hash changed")
    # Generating long DRAT files can exhaust the runner disk. /dev/null
    # preserves proof-writing codepaths but deliberately does not certify UNSAT.
    scratch = None
    if mode == "satsuma_iter_kissat_2026":
        # Submitted run.sh creates temp.cnf beside its proof destination.
        # /dev/null as an argument would wrongly place temp.cnf under /dev.
        scratch = ROOT / stage / "scratch" / str(shard) / c["id"] / mode
        scratch.mkdir(parents=True, exist_ok=True)
        proof = scratch / "solver.proof"
    else:
        proof = Path("/dev/null")
    started = time.perf_counter()
    selected, reason, profile = mode, "fixed", 0.0
    if mode == "ta3_portfolio":
        features = w1.selector().fast_features(source)
        selected, reason = w1.selector().decision(features, "ta2_portfolio")
        profile = time.perf_counter() - started
        command = w1.selected_command(selected, source, proof)
        cwd = None
    else:
        command, cwd = w1.command_for(mode, source, proof)
    stopping = threading.Event()
    def prune_proofs():
        # Keep a regular proof file for the submitted run.sh's file checks,
        # but bound disk use; no independently verifiable proof is retained.
        while not stopping.wait(0.5):
            if scratch is None:
                return
            for p in (scratch / "proof.out", scratch / "solver.proof"):
                try:
                    if p.is_file() and p.stat().st_size > 128*1024*1024:
                        with p.open("r+b") as handle:
                            handle.truncate(0)
                except FileNotFoundError:
                    pass
    janitor = None
    if scratch is not None:
        janitor = threading.Thread(target=prune_proofs, daemon=True)
        janitor.start()
    try:
        rc, output, timed_out = w1.timed_process(
            command, started, cwd=cwd, env={"W1_PROOF_FILE": str(proof)}, cap=cap)
    finally:
        stopping.set()
        if janitor is not None:
            janitor.join(timeout=2)
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
    elapsed = min(cap, time.perf_counter() - started)
    status, evidence = "TIMEOUT", "CAP_TIMEOUT"
    if stage == "smoke":
        print("W2_SMOKE_DETAIL", json.dumps({"mode":mode, "selected":selected, "rc":rc, "timeout":timed_out, "stdout_tail":output[-3500:], "command":list(map(str,command))}), flush=True)
    if not timed_out and elapsed < cap:
        status, model = w1.parse_answer(output, rc)
        if status == "SAT":
            w1.verify_model(source, model)
            evidence = "SAT_MODEL_VERIFIED_ON_ORIGINAL"
        else:
            evidence = "UNSAT_REPORTED_NOT_CERTIFICATE_VERIFIED"
        expected = c.get("expected", "UNKNOWN")
        if expected != "UNKNOWN":
            require(status == expected, "incorrect SAT/UNSAT answer")
    root = ROOT / stage / "stdout" / str(shard) / c["id"]
    root.mkdir(parents=True, exist_ok=True)
    (root / (mode + ".log")).write_text(output)
    return {"id":c["id"], "sha256":c["sha256"], "mode":mode, "stage":stage,
            "cap_s":cap, "shard":shard, "rep":0, "status":status,
            "elapsed_s":round(elapsed, 6),
            "par2_s":round(2*cap if status=="TIMEOUT" else elapsed, 6),
            "selected":selected, "reason":reason, "profile_s":round(profile,6),
            "evidence":evidence, "stdout_sha256":hashlib.sha256(output.encode()).hexdigest(),
            "proof_file":str(proof), "command":list(map(str, command))}

def smoke():
    original()
    w1.selector()
    file = Path("ta3_2026/sources/w2-temporary-smoke.cnf")
    file.write_text("p cnf 2 2\n1 0\n2 0\n")
    case = {"id":"w2-temporary-smoke", "sha256":sha(file), "expected":"SAT"}
    try:
        for mode in S180:
            row = run_one(case, mode, 15, "smoke", -1)
            require(row["status"] == "SAT", "smoke failed " + mode)
    finally:
        file.unlink(missing_ok=True)
    print("W2_SMOKE_PASS", flush=True)

def run_shard(stage, index):
    require(index in range(SHARDS), "invalid shard")
    conf = cohort(ROOT / ("freeze.json" if stage=="stage180" else "stage600/cohort.json"))
    require(stage != "stage180" or len(conf["cases"]) == 17, "wrong 180 set")
    cap, modes = (180, S180) if stage=="stage180" else (600, S600)
    w1.selector()
    cpus = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpus[0]})
    assigned = conf["cases"][index::SHARDS]
    rows = []
    for c in assigned:
        modes_here = list(modes)
        random.Random(PROTOCOL+c["sha256"]+stage).shuffle(modes_here)
        for mode in modes_here:
            row = run_one(c, mode, cap, stage, index)
            rows.append(row)
            print("W2_TRIAL",json.dumps({k:row[k] for k in
                ("stage","id","mode","cap_s","status","elapsed_s","par2_s","evidence")}),flush=True)
            save(ROOT / stage / ("shard-%d.json" % index),
                 {"protocol":PROTOCOL, "stage":stage, "shard":index, "cap_s":cap,
                  "rows":rows, "affinity":sorted(os.sched_getaffinity(0)),
                  "freeze_sha256":sha(ROOT / ("freeze.json" if stage=="stage180" else "stage600/cohort.json"))})
    require(len(rows) == len(assigned)*len(modes), "incomplete shard")
    print("W2_SHARD_PASS",stage,index,len(rows),flush=True)

def collected(stage, cases):
    cap,modes = (180,S180) if stage=="stage180" else (600,S600)
    freeze_file = ROOT / ("freeze.json" if stage=="stage180" else "stage600/cohort.json")
    expected = {(c["sha256"],m) for c in cases for m in modes}
    seen, rows = set(),[]
    for shard in range(SHARDS):
        p = ROOT / stage / ("shard-%d.json" % shard)
        d = json.loads(p.read_text())
        require(d["protocol"]==PROTOCOL and d["stage"]==stage
                and d["shard"]==shard and d["cap_s"]==cap, "bad shard metadata")
        require(d["freeze_sha256"]==sha(freeze_file) and len(d["affinity"])==1,
                "bad source or CPU pin")
        for r in d["rows"]:
            key = (r["sha256"],r["mode"])
            require(key in expected and key not in seen, "duplicate or alien trial")
            require(r["status"] in ("SAT","UNSAT","TIMEOUT"), "invalid answer")
            require(r["cap_s"]==cap and r["shard"]==shard, "wrong trial cap/shard")
            require(abs(r["par2_s"]-(2*cap if r["status"]=="TIMEOUT" else r["elapsed_s"]))<.0001,
                    "PAR2 mismatch")
            seen.add(key);rows.append(r)
    require(seen == expected, "incomplete stage pairs")
    for c in cases:
        st = {r["status"] for r in rows if r["sha256"]==c["sha256"]}
        st.discard("TIMEOUT")
        require(len(st)<=1, "SAT-UNSAT disagreement")
    return rows

def summaries(rows, modes):
    return {m:{"solved":sum(r["status"]!="TIMEOUT" for r in rows if r["mode"]==m),
               "PAR2_s":round(sum(r["par2_s"] for r in rows if r["mode"]==m), 6)}
            for m in modes}

def audit180():
    obj = cohort(ROOT/"freeze.json")
    rows = collected("stage180",obj["cases"])
    solved={r["sha256"] for r in rows if r["status"]!="TIMEOUT"}
    remaining=[c for c in obj["cases"] if c["sha256"] not in solved]
    config = {"protocol":PROTOCOL,"w1_run_id":W1_RUN,"cases":remaining,
              "stage180_cohort_sha256":sha(ROOT/"freeze.json"),
              "unsolved180":len(remaining)}
    save(ROOT/"stage600/cohort.json",config)
    summary={"status":"W2_180_AUDIT_PASS","W1_unsolved":17,
             "newly_solved":len(solved),"still_unsolved":len(remaining),
             "potential_total_solved":7+len(solved),"by_solver":summaries(rows,S180)}
    save(ROOT/"stage180/report.json",summary)
    print("W2_180_FINAL",json.dumps(summary,sort_keys=True),flush=True)

def audit600():
    orig=cohort(ROOT/"freeze.json")
    stage2=cohort(ROOT/"stage600/cohort.json")
    require(stage2["stage180_cohort_sha256"]==sha(ROOT/"freeze.json"),"stage link drift")
    rows180=collected("stage180",orig["cases"])
    known={r["sha256"] for r in rows180 if r["status"]!="TIMEOUT"}
    require({c["sha256"] for c in stage2["cases"]}==
            {c["sha256"] for c in orig["cases"]}-known,"600 source mismatch")
    rows600=collected("stage600",stage2["cases"])
    solved600={r["sha256"] for r in rows600 if r["status"]!="TIMEOUT"}
    report={"status":"W2_FINAL_AUDIT_PASS","w1_run_id":W1_RUN,
            "initial_unsolved":17,"solved_by_180":len(known),
            "new_solved_by_600":len(solved600),"remaining":17-len(known|solved600),
            "total_known_solved_of_24":7+len(known|solved600),
            "stage180":summaries(rows180,S180),"stage600":summaries(rows600,S600),
            "UNSAT_independently_verified":False,
            "limitations":["One exploration repetition per stage","No preserved proof certificates",
                           "60/180/600 second comparisons must not be conflated",
                           "Retested W1 failures; not a new blind holdout"]}
    save(ROOT/"report.json",report)
    print("W2_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","smoke","stage180","audit180","stage600","audit600"))
    parser.add_argument("--w1dir",default="worldsim_w2/w1_final")
    parser.add_argument("--shard",type=int,default=0)
    opts=parser.parse_args()
    if opts.action=="prepare":prep(opts.w1dir)
    elif opts.action=="smoke":smoke()
    elif opts.action=="stage180":run_shard("stage180",opts.shard)
    elif opts.action=="audit180":audit180()
    elif opts.action=="stage600":run_shard("stage600",opts.shard)
    elif opts.action=="audit600":audit600()
