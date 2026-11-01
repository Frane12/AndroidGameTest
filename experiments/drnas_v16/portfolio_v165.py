#!/usr/bin/env python3
"""DRNAS SAT v16.5 structural profile-selector experiment.

The selection rule is frozen before any v16.5 holdout measurements.
It is a hypothesis prompted by v16.4 observations, not a trained model.
Only upstream Kissat --sat is selected, so logical SAT semantics remain
the responsibility of Kissat. No reuse of holdout data for calibration.
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
import math
import statistics
import subprocess
import time

MODES = ("baseline", "sat-fixed", "adaptive")
SOURCE_COMMIT = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def describe(path):
    n = declared = None
    clauses = three = binary = horn = positive = negative = 0
    degree = []
    pending = []
    with open(path, encoding="ascii") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("c") or line.startswith("%"):
                continue
            if line.startswith("p "):
                parts = line.split()
                if len(parts) != 4 or parts[1] != "cnf" or n is not None:
                    raise ValueError(f"invalid DIMACS header in {path}")
                n, declared = int(parts[2]), int(parts[3])
                if n < 1 or declared < 0:
                    raise ValueError("invalid DIMACS dimensions")
                degree = [0]*n
                continue
            if n is None:
                raise ValueError(f"clause before DIMACS header in {path}")
            for rawlit in line.split():
                lit = int(rawlit)
                if lit:
                    if abs(lit) > n:
                        raise ValueError(f"literal {lit} exceeds declared variables")
                    pending.append(lit)
                else:
                    clauses += 1
                    three += len(pending) == 3
                    binary += len(pending) == 2
                    horn += sum(x > 0 for x in pending) <= 1
                    for x in pending:
                        degree[abs(x)-1] += 1
                        positive += x > 0
                        negative += x < 0
                    pending.clear()
    if n is None or pending or clauses != declared:
        raise ValueError(f"invalid number of DIMACS clauses in {path}")
    mean = sum(degree)/n
    sd = math.sqrt(sum((x-mean)**2 for x in degree)/n) if mean else 0.0
    total=positive+negative
    return {
        "nvars": n, "nclauses": clauses,
        "density": clauses/n, "three_fraction": three/max(1, clauses),
        "binary_fraction": binary/max(1, clauses),
        "horn_fraction": horn/max(1, clauses),
        "degree_cv": sd/mean if mean else 0.0,
        "polarity_balance": 1.0-abs(positive-negative)/max(1,total)
    }

def select_profile(f):
    # PRE-REGISTERED v16.5 hypothesis:
    # near-threshold, regular random-3SAT-like formulas may benefit from
    # Kissat's satisfiability-oriented search configuration.
    # Abstain on unrecognized / clearly nonmatching structures.
    if (f["nvars"] >= 350
        and f["nclauses"] >= 1000
        and 4.10 <= f["density"] <= 4.42
        and f["three_fraction"] >= .995
        and f["degree_cv"] <= .50
        and f["polarity_balance"] >= .90):
        return ("--sat",)
    return ()

def measure(solver, flags, path, timeout):
    start = time.perf_counter()
    try:
        p = subprocess.run([solver, *flags, str(path)],
                           capture_output=True, text=True, timeout=timeout,
                           check=False)
        result = {10: "SAT", 20: "UNSAT"}.get(p.returncode, "ERROR")
        if result == "ERROR":
            print("SOLVER_ERROR", path.name, flags, p.returncode,
                  p.stdout[-800:], p.stderr[-800:], flush=True)
        return result, time.perf_counter()-start, p.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", time.perf_counter()-start, -1

def summary(rows, timeout, output):
    by_pair = defaultdict(dict)
    for r in rows:
        key=(r["group"], r["file"], int(r["repeat"]))
        if r["mode"] in by_pair[key]:
            raise ValueError(f"duplicate mode {key}")
        by_pair[key][r["mode"]]=r
    for key, modes in by_pair.items():
        if set(modes)!=set(MODES):
            raise ValueError(f"incomplete mode set at {key}")
        answers={v["result"] for v in modes.values()
                 if v["result"] in ("SAT","UNSAT")}
        if len(answers)>1:
            raise ValueError(f"SAT/UNSAT disagreement: {key}: {answers}")
    if any(x["result"] == "ERROR" for x in rows):
        raise ValueError("solver failed one or more runs")

    lines=["DRNAS SAT v16.5 / frozen structural hypothesis / upstream Kissat",
           f"pinned-kissat-commit: {SOURCE_COMMIT}",
           "Interpretation: adaptation selects upstream --sat; it does not alter Kissat internals."]
    for group in ("replay","holdout","control"):
        subset=[r for r in rows if r["group"]==group]
        if not subset:
            continue
        lines.append(f"GROUP {group} ({len(subset)//len(MODES)} problem-repetitions)")
        for mode in MODES:
            data=[r for r in subset if r["mode"]==mode]
            seconds=[float(r["total_sec"]) for r in data]
            solved=sum(r["result"] in ("SAT","UNSAT") for r in data)
            par2=sum(float(r["total_sec"]) if r["result"] in ("SAT","UNSAT")
                     else 2*timeout for r in data)/len(data)
            lines.append(f"  {mode}: solved={solved}/{len(data)}, "
                         f"median={statistics.median(seconds):.5f}s, PAR2={par2:.5f}s")
        ratios=[]
        for (g,_,_), m in by_pair.items():
            if g!=group:
                continue
            base, adaptive=m["baseline"],m["adaptive"]
            if base["result"] in ("SAT","UNSAT") and adaptive["result"] in ("SAT","UNSAT"):
                ratios.append(float(base["total_sec"])/float(adaptive["total_sec"]))
        if ratios:
            gm=math.exp(statistics.mean(math.log(x) for x in ratios))
            lines.append(f"  paired solved-only geo-speedup baseline/adaptive={gm:.4f}x "
                         f"(n={len(ratios)}, excludes censored timeouts)")
        else:
            lines.append("  paired solved-only geo-speedup unavailable")
        if group=="holdout":
            lines.append("  HOLDOUT is the only independent exploratory generalization estimate.")
    lines.append("Do not extrapolate to arbitrary SAT instances or world records.")
    text="\n".join(lines)+"\n"
    output.write_text(text,encoding="utf-8")
    print(text,flush=True)

def run(args):
    inputs=sorted(args.cnf_dir.rglob("*.cnf"))
    if not inputs:
        raise SystemExit("No .cnf inputs found")
    rows=[]
    for path in inputs:
        f=describe(path)
        selected=select_profile(f)
        print("CLASSIFY",path.parent.name,path.name,"selected=",
              " ".join(selected) or "default",
              "density=",round(f["density"],5),
              "degree_cv=",round(f["degree_cv"],5),
              "polarity_balance=",round(f["polarity_balance"],5),flush=True)
        for rep in range(args.repeats):
            # Rotate execution order, retaining identical files and hardware.
            order=MODES[rep%len(MODES):]+MODES[:rep%len(MODES)]
            for mode in order:
                started=time.perf_counter()
                flags=() if mode=="baseline" else ("--sat",) if mode=="sat-fixed" else select_profile(f)
                gate_sec=time.perf_counter()-started if mode=="adaptive" else 0.0
                result,solve_sec,rc=measure(args.solver,flags,path,args.timeout)
                row={
                    "group":path.parent.name,"file":path.name,"repeat":rep,
                    "mode":mode,"profile":" ".join(flags) or "default",
                    "nvars":f["nvars"],"nclauses":f["nclauses"],
                    "density":round(f["density"],6),
                    "three_fraction":round(f["three_fraction"],6),
                    "degree_cv":round(f["degree_cv"],6),
                    "polarity_balance":round(f["polarity_balance"],6),
                    "gate_sec":round(gate_sec,6),
                    "solve_sec":round(solve_sec,6),
                    "total_sec":round(solve_sec+gate_sec,6),
                    "result":result,"returncode":rc
                }
                rows.append(row)
                print("MEASURE",row["group"],row["file"],rep,mode,
                      row["profile"],result,f"{row['total_sec']:.6f}s",flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",newline="",encoding="utf-8") as out:
        w=csv.DictWriter(out,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summary(rows,args.timeout,args.output.with_suffix(".summary.txt"))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--cnf-dir",required=True,type=Path)
    p.add_argument("--solver",required=True)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--timeout",type=float,default=25.0)
    p.add_argument("--output",type=Path,default=Path("drnas_v165.csv"))
    opts=p.parse_args()
    if opts.repeats < 1 or opts.timeout <= 0:
        p.error("repeats and timeout must be positive")
    run(opts)
