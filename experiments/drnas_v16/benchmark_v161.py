#!/usr/bin/env python3
"""DRNAS SAT v16.1: reproducible external Kissat benchmark adapter.
Modes: baseline (no classification), control (classify, never alter solver),
adaptive (gate stays closed until independently validated).
The tool NEVER infers solved status from runtime alone.
"""
import argparse
import csv
import pathlib
import statistics
import subprocess
import time

def probe(path, max_clauses=100000, max_literals=1000000):
    clauses = binary = horn = literals = empty = 0
    positive = negative = 0
    pending = []
    truncated = False
    with open(path, encoding="ascii", errors="replace") as src:
        for line in src:
            s = line.strip()
            if not s or s.startswith("c") or s.startswith("p") or s.startswith("%"):
                continue
            for token in s.split():
                x = int(token)
                if x:
                    pending.append(x)
                else:
                    if clauses >= max_clauses or literals + len(pending) > max_literals:
                        truncated = True
                        break
                    clauses += 1
                    literals += len(pending)
                    binary += len(pending) == 2
                    horn += sum(v > 0 for v in pending) <= 1
                    empty += len(pending) == 0
                    positive += sum(v > 0 for v in pending)
                    negative += sum(v < 0 for v in pending)
                    pending.clear()
            if truncated:
                break
    if pending and not truncated:
        raise ValueError(f"Incomplete DIMACS clause in {path}")
    if truncated or empty or clauses < 32:
        family = "unknown"
    elif binary / clauses >= .75:
        family = "binary-heavy"
    elif horn / clauses >= .90:
        family = "horn-heavy"
    else:
        family = "mixed"
    return dict(family=family, clauses=clauses, literals=literals,
                truncated=truncated, binary_fraction=round(binary/max(1,clauses),5),
                horn_fraction=round(horn/max(1,clauses),5))

def solve(command, cnf, timeout):
    started = time.perf_counter()
    try:
        p = subprocess.run(command + [str(cnf)], capture_output=True,
                           text=True, timeout=timeout, check=False)
        elapsed = time.perf_counter()-started
        # SAT Competition / Kissat exit codes.
        status = {10:"SAT", 20:"UNSAT"}.get(p.returncode, "ERROR")
        return status, elapsed, p.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter()-started, -1

def run(args):
    paths = sorted(pathlib.Path(args.cnf_dir).rglob("*.cnf"))
    if not paths:
        raise SystemExit("No .cnf files found")
    rows = []
    for p in paths:
        for rep in range(args.repeats):
            for mode in ("baseline", "control", "adaptive"):
                start = time.perf_counter()
                features = probe(p) if mode != "baseline" else None
                probe_secs = time.perf_counter()-start if features else 0.0
                # Fail-closed: ALL modes use identical solver arguments.
                status, solve_secs, rc = solve(args.solver, p, args.timeout)
                rows.append(dict(file=str(p), repeat=rep, mode=mode,
                                 family=features["family"] if features else "not-probed",
                                 probe_sec=round(probe_secs,6),
                                 solve_sec=round(solve_secs,6),
                                 total_sec=round(probe_secs+solve_secs,6),
                                 result=status, returncode=rc,
                                 experimental_gate=False))
    keys = list(rows[0])
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)
    print("CSV:",args.out, "rows:", len(rows))
    mismatch = 0
    for p in paths:
        valid = {r["result"] for r in rows if r["file"] == str(p)
                 and r["result"] in ("SAT","UNSAT")}
        if len(valid)>1:
            mismatch += 1
            print("MISMATCH:", p, valid)
    for mode in ("baseline","control","adaptive"):
        selected=[r["total_sec"] for r in rows if r["mode"]==mode]
        print(mode, "median-total-seconds", round(statistics.median(selected),6))
    if mismatch:
        raise SystemExit(f"Detected {mismatch} SAT/UNSAT mismatches")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--cnf-dir",required=True)
    parser.add_argument("--solver",nargs="+",required=True,
                        help="solver executable and arguments; CNF path appended")
    parser.add_argument("--timeout",type=float,default=30.0)
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--out",default="drnas_v161_results.csv")
    opts=parser.parse_args()
    if opts.repeats<1 or opts.timeout<=0:
        parser.error("repeats must be positive and timeout > 0")
    run(opts)
