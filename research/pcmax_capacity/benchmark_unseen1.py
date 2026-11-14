#!/usr/bin/env python3
"""Fresh, reproducible PCMAX P||Cmax CNFs outside original20.

The task lists are generated before evaluating the native module. Ground-truth
UNSAT uses the independent counting argument n > m*k and every job duration >=
w while each machine has capacity (k+1)*w-1. For SAT controls, a balanced
explicit assignment is checked. The module sees only DIMACS, not the labels.
Certificates are checked by a fresh independent checker process.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/pcmax_capacity/tests"))
from make_fixtures import build_scheduling

SEED = 202611142105
UNSAT = [(2,3,11,0),(3,3,10,1),(3,4,9,0),(4,3,12,1),
         (4,5,10,1),(5,3,10,0),(5,4,8,1),(6,4,9,0),
         (6,5,9,1),(7,3,10,1),(8,3,9,1),(9,4,9,0)]
SAT = [(2,3,11,1),(3,3,10,0),(3,4,9,1),(4,3,12,0),
       (5,4,8,1),(6,4,9,0),(7,3,10,1),(8,3,9,0)]

def generate(root):
    rng = random.Random(SEED)
    root.mkdir(parents=True, exist_ok=False)
    previous = {e["sha256"] for e in
        json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]}
    cases = []
    for label, rows in [("UNSAT", UNSAT), ("SAT", SAT)]:
        for i, (m,k,w,jitter) in enumerate(rows):
            n = m*k + (label == "UNSAT")
            durations = [w + rng.randint(0, jitter) for _ in range(n)]
            capacity = (k+1)*w-1
            assert min(durations) == w or min(durations) == w+1
            assert all(d <= capacity for d in durations)
            if label == "UNSAT":
                assert n > m*(capacity//min(durations))
                assert sum(durations) <= m*capacity, "Ensure volume bound alone does not prove UNSAT"
            else:
                # Explicit round-robin witness, not just a claimed label.
                loads = [sum(durations[j] for j in range(q,n,m))
                         for q in range(m)]
                assert max(loads) <= capacity
            variables, clauses, groups, _ = build_scheduling(durations, m, capacity)
            raw = (f"c New PCMAX schedule, held-out seed {SEED}, case {label}{i:02d}\n"
                   f"p cnf {variables} {len(clauses)}\n" +
                   "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode("ascii")
            sha = hashlib.sha256(raw).hexdigest()
            assert sha not in previous
            previous.add(sha)
            name = f"fresh-{label.lower()}-{i:02d}-m{m}-n{n}.cnf"
            (root/name).write_bytes(raw)
            cases.append(dict(name=name, label=label, sha256=sha, machine_count=m,
                              jobs=n, min_duration=min(durations), max_duration=max(durations),
                              capacity=capacity, total_duration=sum(durations),
                              variables=variables, clauses=len(clauses),
                              proof_basis=("COUNT_CAPACITY" if label=="UNSAT" else "ROUND_ROBIN_WITNESS")))
    return cases

def exec_cmd(cmd, timeout):
    t = time.perf_counter()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return dict(rc=p.returncode, wall_s=time.perf_counter()-t,
                    out=p.stdout, err=p.stderr, timeout=False)
    except subprocess.TimeoutExpired:
        return dict(rc=None, wall_s=time.perf_counter()-t,
                    out="", err="hard timeout", timeout=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--budget-ms", type=int, default=5000)
    p.add_argument("--repetitions", type=int, default=2)
    args = p.parse_args()
    assert args.repetitions >= 1 and 100 <= args.budget_ms <= 10000
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    args.output.mkdir(parents=True, exist_ok=False)
    cnfs = args.output/"cnfs"
    cases = generate(cnfs)
    checker = ROOT/"research/pcmax_capacity/check_capacity.py"
    rows = []
    with (args.output/"trials.jsonl").open("w") as log:
        for rep in range(args.repetitions):
            for case in (cases if rep%2 == 0 else list(reversed(cases))):
                cnf = cnfs/case["name"]
                assert hashlib.sha256(cnf.read_bytes()).hexdigest() == case["sha256"]
                cert = args.output / f"cert-{case['sha256'][:14]}-r{rep}.json"
                native = exec_cmd([str(args.binary.resolve()),str(cnf.resolve()),
                    "--mode","core","--time",str(args.budget_ms/1000+1),
                    "--pcmax-only","--pcmax-budget-ms",str(args.budget_ms),
                    "--pcmax-certificate",str(cert.resolve())],timeout=args.budget_ms/1000+5)
                recs = [json.loads(s.removeprefix("c PCMAX_CAPACITY "))
                        for s in native["out"].splitlines()
                        if s.startswith("c PCMAX_CAPACITY ")]
                row = dict(name=case["name"], sha256=case["sha256"], expected=case["label"],
                           rep=rep, native_s=round(native["wall_s"],6),
                           native_rc=native["rc"], telemetry=recs[-1] if recs else None,
                           status="UNKNOWN", checked=False)
                if native["rc"] == 20 and "s UNSATISFIABLE" in native["out"]:
                    assert cert.is_file(), (row,native)
                    check = exec_cmd([sys.executable,str(checker.resolve()),
                                      str(cnf.resolve()),str(cert.resolve())],timeout=45)
                    assert check["rc"] == 0, (row,check)
                    proof = json.loads(check["out"])
                    assert proof["status"] == "UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED", proof
                    assert case["label"] == "UNSAT", "UNSOUND: SAT control structurally refuted"
                    row.update(status="UNSAT_VERIFIED",checked=True,
                               demand=proof["required"],capacity_sum=proof["capacity_sum"],
                               check_s=round(check["wall_s"],6),
                               total_s=round(native["wall_s"]+check["wall_s"],6))
                else:
                    assert native["rc"] == 0 and "s UNKNOWN" in native["out"], (row,native)
                    assert not cert.exists(), row
                    row["total_s"] = round(native["wall_s"],6)
                rows.append(row)
                log.write(json.dumps(row,sort_keys=True)+"\n")
                log.flush()
                print("PCMAX_UNSEEN_TRIAL "+json.dumps({
                    k:row[k] for k in ("name","rep","status","native_s","total_s")}),flush=True)
    meta = dict(kind="FRESH_SYNTHETIC_PCMAX_NOT_OFFICIAL", seed=SEED, frozen_cases=cases,
        independent_ground_truth="COUNT_CAPACITY or explicit round-robin SAT witness",
        source_count=len(cases), repetitions=args.repetitions,
        single_logical_cpu=cpu, budget_ms=args.budget_ms,
        binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
        checker_sha256=hashlib.sha256(checker.read_bytes()).hexdigest(),
        verified_unsat_trials=sum(r["checked"] for r in rows),
        unsat_cases=sum(c["label"]=="UNSAT" for c in cases),
        sat_controls=sum(c["label"]=="SAT" for c in cases),rows=rows)
    (args.output/"summary.json").write_text(json.dumps(meta,indent=2)+"\n")
    print("PCMAX_UNSEEN_SUMMARY "+json.dumps({
        k:meta[k] for k in ("source_count","repetitions","verified_unsat_trials","unsat_cases","sat_controls")
    }),flush=True)

if __name__ == "__main__":
    main()
