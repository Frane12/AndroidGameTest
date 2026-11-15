#!/usr/bin/env python3
"""Generated PCMAX capacity scaling, not a general blind benchmark.

Serial one-CPU runs; original-CNF certificate checked independently.
Horn padding measures input-size scalability, NOT CDCL difficulty.
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "tests"))
from make_fixtures import build_scheduling

# Preregistered before examining solver outcomes. A time cap is not evidence of
# expected baseline timeout: all solved results and failures are retained.
CASES = [
    ("U005_m2_k2", 5, 2, 2, 0, 17),
    ("U013_m2_k6", 13, 2, 6, 0, 17),
    ("U025_m2_k12", 25, 2, 12, 0, 17),
    ("U049_m2_k24", 49, 2, 24, 0, 17),
    ("U097_m2_k48", 97, 2, 48, 0, 17),
    ("U097_m2_k48_r29", 97, 2, 48, 0, 29),
    ("U121_m3_k40", 121, 3, 40, 0, 17),
    ("U121_m3_k40_r29", 121, 3, 40, 0, 29),
    ("U061_m3_k20_pad50k", 61, 3, 20, 50000, 17),
    ("U061_m3_k20_pad195k", 61, 3, 20, 195000, 17),
    ("S012_m2_k6", 12, 2, 6, 0, 17),
]

def make_case(spec, destination):
    name, jobs, machines, cap, pad, seed = spec
    assert 3 <= jobs <= 128 and 2 <= machines <= 3
    assert jobs in (machines * cap, machines * cap + 1)
    core_vars, clauses, groups, _ = build_scheduling([1] * jobs, machines, cap)
    assert len(groups) == jobs
    declared = max(core_vars, pad)
    # Independent Horn chain is satisfiable with every auxiliary variable false.
    if declared > core_vars:
        clauses.extend((-a, -(a+1), a+2) for a in range(core_vars+1, declared-1))
    assert len(clauses) <= 1000000 and declared <= 200000
    assert max(map(len, clauses)) <= 128
    rng = random.Random(seed)
    rename = [0] + list(range(1, declared+1))
    shuffled = list(range(1, declared + 1))
    rng.shuffle(shuffled)
    rename[1:] = shuffled
    mapped = [tuple(rename[abs(v)] * (1 if v > 0 else -1) for v in c)
              for c in clauses]
    rng.shuffle(mapped)
    destination.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with destination.open("wb") as fd:
        def emit(b):
            h.update(b)
            fd.write(b)
        emit(f"p cnf {declared} {len(mapped)}\n".encode())
        for c in mapped:
            emit((" ".join(map(str, c)) + " 0\n").encode())
    return dict(name=name, sha256=h.hexdigest(), variables=declared,
                core_variables=core_vars, clauses=len(mapped), jobs=jobs,
                machines=machines, capacity_per_machine=cap, seed=seed,
                expected="SAT" if jobs == machines*cap else "UNSAT",
                padding_horn=(declared > core_vars))

def run_one(command, cpu, timeout):
    start = time.perf_counter()
    def pin():
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, {cpu})
    try:
        p = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout, preexec_fn=pin)
        return dict(rc=p.returncode, wall_s=round(time.perf_counter()-start, 6),
                    timeout=False, stdout=p.stdout[-500:], stderr=p.stderr[-500:])
    except subprocess.TimeoutExpired:
        return dict(rc=None, wall_s=round(time.perf_counter()-start, 6),
                    timeout=True, stdout="", stderr="TIMEOUT")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("results/pcmax_scale_20261115"))
    p.add_argument("--native", type=Path, default=Path("build/drnas-pcmax"))
    p.add_argument("--base", type=Path, default=Path("build/drnas-pcmax-base"))
    p.add_argument("--cap", type=float, default=12.0)
    p.add_argument("--generate-only", action="store_true")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cpu = min(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else 0
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {cpu})
    entries = []
    arms = ["structural", "x5_cdcl"]
    for executable in ("kissat", "cadical"):
        if shutil.which(executable):
            arms.append(executable)
    checker = Path("research/pcmax_capacity/check_capacity.py").resolve()
    log_path = args.out / "trials.jsonl"
    with log_path.open("w") as log:
        for index, spec in enumerate(CASES):
            path = args.out / "cnf" / (spec[0] + ".cnf")
            info = make_case(spec, path)
            entries.append(info)
            print("SCALE_INPUT " + json.dumps(info, sort_keys=True), flush=True)
            if args.generate_only:
                continue
            ordered = arms[index % len(arms):] + arms[:index % len(arms)]
            for arm in ordered:
                cert = args.out / (info["name"] + ".capacity.json")
                if arm == "structural":
                    cert.unlink(missing_ok=True)
                    command = [str(args.native.resolve()), str(path.resolve()),
                               "--mode", "core", "--time", str(args.cap + 2),
                               "--pcmax-only", "--pcmax-capacity",
                               "--pcmax-budget-ms", str(round(args.cap * 1000)),
                               "--pcmax-certificate", str(cert.resolve())]
                elif arm == "x5_cdcl":
                    command = [str(args.base.resolve()), str(path.resolve()),
                               "--mode", "core", "--time", str(args.cap)]
                elif arm == "cadical":
                    command = [shutil.which(arm), "-q", str(path.resolve())]
                else:
                    command = [shutil.which(arm), "--quiet", str(path.resolve())]
                result = run_one(command, cpu,
                                 args.cap + 4 if arm == "structural" else args.cap + 1)
                row = dict(name=info["name"], sha256=info["sha256"],
                           expected=info["expected"], arm=arm, **result)
                row.pop("stdout", None)
                row.pop("stderr", None)
                row["status"] = "TIMEOUT" if result["timeout"] else (
                    "UNSAT_REPORTED" if result["rc"] == 20 else
                    "SAT_REPORTED" if result["rc"] == 10 else "UNKNOWN")
                row["verified"] = False
                row["checker_s"] = None
                if arm == "structural" and result["rc"] == 20 and cert.is_file():
                    checked = run_one([sys.executable, str(checker),
                                       str(path.resolve()), str(cert.resolve())],
                                      cpu, 60)
                    row["checker_s"] = checked["wall_s"]
                    row["verified"] = (checked["rc"] == 0 and not checked["timeout"]
                                       and "UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED"
                                       in checked["stdout"])
                    row["status"] = ("UNSAT_STRUCTURAL_VERIFIED" if row["verified"]
                                     else "UNSAT_UNVERIFIED")
                if info["expected"] == "SAT" and result["rc"] == 20:
                    raise AssertionError("FALSE UNSAT ON SAT CONTROL: " + repr(row))
                log.write(json.dumps(row, sort_keys=True) + "\n")
                log.flush()
                print("SCALE_TRIAL " + json.dumps({k: row[k] for k in
                      ("name", "arm", "status", "verified", "wall_s", "checker_s")},
                      sort_keys=True), flush=True)
    summary = dict(protocol="GENERATED_SCHEDULING_NOT_BLIND",
                   source="make_fixtures.build_scheduling", cap=args.cap,
                   one_logical_cpu=cpu, arms=arms, cases=entries,
                   structural_certificate="pcmax-capacity-v1, not DRAT/LRAT",
                   padding_is_only_input_size_stress=True)
    if log_path.stat().st_size:
        rows = [json.loads(l) for l in log_path.read_text().splitlines()]
        summary["trials"] = len(rows)
        summary["structural_verified"] = sum(r["verified"] for r in rows)
        summary["statuses"] = {
            arm: {s: sum(r["arm"] == arm and r["status"] == s for r in rows)
                  for s in sorted({r["status"] for r in rows if r["arm"] == arm})}
            for arm in arms}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("SCALE_SUMMARY " + json.dumps({k: summary.get(k) for k in
          ("protocol", "trials", "structural_verified", "statuses")},
          sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
