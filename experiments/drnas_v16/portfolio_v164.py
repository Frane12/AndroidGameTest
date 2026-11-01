#!/usr/bin/env python3
"""DRNAS v16.4 reproducible structural portfolio, experimental only.
All modes use the SAME pinned Kissat binary. The adaptive mode changes
only verified upstream --sat / --unsat configuration flags, never an answer.
The rule below is a PRE-REGISTERED hypothesis, not learned from holdout.
"""
import argparse
import csv
import math
from pathlib import Path
import statistics
import subprocess
import time

MODES=("baseline","sat-profile","unsat-profile","adaptive")

def features(path):
    nvars=None
    clauses=0
    lits=0
    binary=horn=positive=negative=0
    current=[]
    with open(path,encoding="ascii") as source:
        for raw in source:
            line=raw.strip()
            if not line or line.startswith("c") or line.startswith("%"):
                continue
            if line.startswith("p "):
                parts=line.split()
                if len(parts)!=4 or parts[1]!="cnf":
                    raise ValueError(f"Invalid DIMACS header: {path}")
                nvars=int(parts[2])
                declared=int(parts[3])
                continue
            for token in line.split():
                lit=int(token)
                if lit==0:
                    clauses+=1
                    lits+=len(current)
                    binary+=len(current)==2
                    horn+=sum(x>0 for x in current)<=1
                    positive+=sum(x>0 for x in current)
                    negative+=sum(x<0 for x in current)
                    current=[]
                else:
                    if nvars is None or abs(lit)>nvars:
                        raise ValueError(f"Invalid variable in {path}")
                    current.append(lit)
    if nvars is None or current or clauses!=declared or nvars==0:
        raise ValueError(f"Invalid DIMACS clause count in {path}")
    return dict(nvars=nvars,nclauses=clauses,density=clauses/nvars,
                binary_fraction=binary/max(1,clauses),
                horn_fraction=horn/max(1,clauses),
                polarity_balance=1-abs(positive-negative)/max(1,positive+negative))

def choose(f):
    # Explicitly conservative: no unsupervised "SAT guess" in threshold region.
    if f["nclauses"]<32:
        return ()
    if f["binary_fraction"]>0.80 or f["horn_fraction"]>0.95:
        return ()
    if f["density"]<=4.00:
        return ("--sat",)
    if f["density"]>=4.55:
        return ("--unsat",)
    return ()

def args_for(mode,f):
    if mode=="baseline":
        return ()
    if mode=="sat-profile":
        return ("--sat",)
    if mode=="unsat-profile":
        return ("--unsat",)
    if mode=="adaptive":
        return choose(f)
    raise ValueError(mode)

def execute(solver,flags,path,timeout):
    start=time.perf_counter()
    try:
        p=subprocess.run([solver,*flags,str(path)],capture_output=True,
                         text=True,timeout=timeout,check=False)
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
        rc=p.returncode
    except subprocess.TimeoutExpired:
        status="TIMEOUT"
        rc=-1
    return status,time.perf_counter()-start,rc

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--cnf-dir",type=Path,required=True)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--timeout",type=float,default=25)
    p.add_argument("--output",type=Path,default=Path("drnas_v164.csv"))
    a=p.parse_args()
    if a.repeats<1 or a.timeout<=0:
        p.error("repeats and timeout must be positive")
    inputs=sorted(a.cnf_dir.rglob("*.cnf"))
    if not inputs:
        raise SystemExit("No CNFs")
    rows=[]
    for path in inputs:
        f=features(path)
        for rep in range(a.repeats):
            # Rotates invocation order to mitigate, not eliminate, run-order bias.
            order=MODES[rep%len(MODES):]+MODES[:rep%len(MODES)]
            for mode in order:
                start=time.perf_counter()
                flags=args_for(mode,f)
                classify=time.perf_counter()-start if mode=="adaptive" else 0.
                status,elapsed,rc=execute(a.solver,flags,path,a.timeout)
                row=dict(file=path.name,group=path.parent.name,repeat=rep,
                         mode=mode,profile=" ".join(flags) or "default",
                         nvars=f["nvars"],nclauses=f["nclauses"],
                         density=round(f["density"],5),
                         polarity_balance=round(f["polarity_balance"],5),
                         binary_fraction=round(f["binary_fraction"],5),
                         horn_fraction=round(f["horn_fraction"],5),
                         classification_sec=round(classify,6),
                         solve_sec=round(elapsed,6),
                         total_sec=round(classify+elapsed,6),
                         result=status,returncode=rc)
                rows.append(row)
                print("MEASURE",row["group"],row["file"],rep,mode,
                      row["profile"],status,f"{row['total_sec']:.4f}s",flush=True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open("w",newline="",encoding="utf8") as dst:
        writer=csv.DictWriter(dst,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    problems={}
    for row in rows:
        problems.setdefault(row["file"],set()).add(row["result"])
    inconsistent={name:sorted(v & {"SAT","UNSAT"}) for name,v in problems.items()
                  if len(v & {"SAT","UNSAT"})>1}
    if inconsistent:
        raise SystemExit(f"SAT/UNSAT disagreements: {inconsistent}")
    if any(r["result"]=="ERROR" for r in rows):
        raise SystemExit("Solver returned error; check accepted profile flags")
    summary=a.output.with_suffix(".summary.txt")
    with summary.open("w",encoding="utf8") as out:
        for group in sorted({r["group"] for r in rows}):
            out.write(f"GROUP {group}\n")
            for mode in MODES:
                subset=[r for r in rows if r["group"]==group and r["mode"]==mode]
                seconds=[float(r["total_sec"]) for r in subset]
                solved=sum(r["result"] in ("SAT","UNSAT") for r in subset)
                par2=statistics.mean(x if r["result"] in ("SAT","UNSAT")
                                    else 2*a.timeout for x,r in zip(seconds,subset))
                line=(f"{mode}: solved={solved}/{len(subset)}, "
                      f"median={statistics.median(seconds):.5f}s, PAR2={par2:.5f}s")
                print(group,line,flush=True)
                out.write(line+"\n")
        out.write("Experimental policy: density<=4.00 -> --sat; "
                  "density>=4.55 -> --unsat; otherwise upstream default.\n")
        out.write("All comparisons against identical pinned Kissat version; "
                  "not a claim of a new solver or general speedup.\n")
    print("WROTE",a.output,summary,flush=True)

if __name__=="__main__":
    main()
