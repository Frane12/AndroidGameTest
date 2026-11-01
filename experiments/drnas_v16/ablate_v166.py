#!/usr/bin/env python3
"""DRNAS v16.6: factor-isolation experiment on Kissat SAT configuration.
FROZEN IN ADVANCE: baseline, target-only, restart-only, both (--sat).
No profiling, labels or outcomes of blind seeds used for selection.
All modes use exactly the same upstream Kissat executable.
"""
import argparse
import collections
import csv
import hashlib
import math
from pathlib import Path
import random
import re
import statistics
import subprocess
import time

PINNED_KISSAT = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CONFIGS = {
    "baseline": (),
    "target-only": ("--target=2",),
    "restart-only": ("--restartint=50",),
    "sat-both": ("--sat",),
}
CASES = (
    ("replay", 640, 165000), # 4.61x faster with --sat in v16.5
    ("replay", 640, 165001), # 5.21x slower with --sat in v16.5
    ("holdout", 480, 166000),
    ("holdout", 480, 166001),
    ("holdout", 640, 166002),
    ("holdout", 640, 166003),
)

def make_cnf(path, n, seed):
    rng=random.Random(seed)
    m=round(n*4.26)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="ascii") as f:
        f.write(f"c DRNAS-v166 seed={seed} ratio=4.26 group={path.parent.name}\n")
        f.write(f"p cnf {n} {m}\n")
        for _ in range(m):
            variables=rng.sample(range(1,n+1),3)
            signs=[1 if rng.getrandbits(1) else -1 for _ in range(3)]
            f.write(" ".join(str(v*s) for v,s in zip(variables,signs))+" 0\n")
    return m

def structural_features(path, n):
    degree=[0]*n
    pos=[0]*n
    neg=[0]*n
    pairs=collections.Counter()
    clauses=0
    with path.open(encoding="ascii") as f:
        for line in f:
            if not line or line[0] in ("c","p"):
                continue
            vals=[int(t) for t in line.split()]
            if not vals or vals[-1]!=0 or len(vals)!=4:
                raise ValueError(f"Expected 3CNF: {path}")
            clauses+=1
            vars_=[]
            for literal in vals[:-1]:
                idx=abs(literal)-1
                if idx<0 or idx>=n:
                    raise ValueError(f"Invalid literal in {path}")
                degree[idx]+=1
                (pos if literal>0 else neg)[idx]+=1
                vars_.append(idx)
            vars_.sort()
            pairs[(vars_[0],vars_[1])]+=1
            pairs[(vars_[0],vars_[2])]+=1
            pairs[(vars_[1],vars_[2])]+=1
    mean=sum(degree)/n
    variance=sum((d-mean)**2 for d in degree)/n
    signed_imbalance=sum(abs(a-b)/max(1,a+b) for a,b in zip(pos,neg))/n
    repeating=sum(count-1 for count in pairs.values() if count>1)
    return dict(nvars=n,nclauses=clauses, density=clauses/n,
        degree_cv=math.sqrt(variance)/mean,
        mean_variable_imbalance=signed_imbalance,
        repeated_variable_pairs=repeating,
        pair_repetition_fraction=repeating/(3*clauses),
        max_occurrence=max(degree),
        missing_polarity=sum(a==0 or b==0 for a,b in zip(pos,neg)))

def run_one(solver, mode, path, timeout, logfile):
    args=[solver, "-s", *CONFIGS[mode], str(path)]
    start=time.perf_counter()
    try:
        run=subprocess.run(args,capture_output=True,text=True,
                           timeout=timeout,check=False)
        elapsed=time.perf_counter()-start
        status={10:"SAT",20:"UNSAT"}.get(run.returncode,"ERROR")
        text=run.stdout + "\n" + run.stderr
        rc=run.returncode
    except subprocess.TimeoutExpired as e:
        elapsed=time.perf_counter()-start
        status="TIMEOUT"
        rc=-1
        out=e.stdout if isinstance(e.stdout,bytes) else (e.stdout or "")
        err=e.stderr if isinstance(e.stderr,bytes) else (e.stderr or "")
        text=(out.decode("utf-8","replace") if isinstance(out,bytes) else out)
        text+="\n"+(err.decode("utf-8","replace") if isinstance(err,bytes) else err)
    logfile.parent.mkdir(parents=True,exist_ok=True)
    logfile.write_text("COMMAND: "+" ".join(args)+"\nSTATUS: "+status+
                       "\nTIME_SECONDS: "+f"{elapsed:.6f}"+"\n"+text,
                       encoding="utf-8")
    # Stats names depend on compile options; retain all raw -s output for audit.
    # Recognize 'c conflicts: 1234' and 'c conflicts 1234 ...' variants.
    counters={}
    for name in ("conflicts","restarts","decisions","propagations","learned"):
        pattern=r"(?m)^c\s+"+name+r"\s*:?\s+([0-9][0-9,]*)\b"
        found=re.search(pattern,text)
        counters[name]=int(found.group(1).replace(",","")) if found else ""
    return dict(status=status,elapsed=elapsed,rc=rc,**counters)

def summarize(rows,output,timeout):
    lines=[
        "DRNAS SAT v16.6 target/restart factorial ablation",
        "Kissat source: "+PINNED_KISSAT,
        "Baseline=target1/restart1; target-only=target2/restart1; "
        "restart-only=target1/restart50; sat-both=target2/restart50.",
        "Holdout seeds were fixed in source before measurements.  "
        "All results exploratory, no record claims.",
    ]
    for group in ("replay","holdout"):
        lines.append(f"GROUP {group}")
        subset=[r for r in rows if r["group"]==group]
        for mode in CONFIGS:
            values=[r for r in subset if r["mode"]==mode]
            times=[float(x["elapsed_sec"]) for x in values]
            solved=sum(x["status"] in ("SAT","UNSAT") for x in values)
            par2=statistics.mean(
                t if v["status"] in ("SAT","UNSAT") else 2*timeout
                for t,v in zip(times,values))
            lines.append(f"  {mode}: solved={solved}/{len(values)} "
                         f"median={statistics.median(times):.5f}s PAR2={par2:.5f}s")
        for seed in sorted({r["seed"] for r in subset}):
            lines.append("  INSTANCE "+str(seed))
            for mode in CONFIGS:
                values=[r for r in subset if r["seed"]==seed and r["mode"]==mode]
                times=[float(x["elapsed_sec"]) for x in values]
                statuses="/".join(x["status"] for x in values)
                conflicts="/".join(str(x["conflicts"] or "?") for x in values)
                restarts="/".join(str(x["restarts"] or "?") for x in values)
                lines.append(f"    {mode}: {statistics.median(times):.4f}s "
                             f"status={statuses} conflicts={conflicts} "
                             f"restarts={restarts}")
    summary="\n".join(lines)+"\n"
    output.write_text(summary,encoding="utf-8")
    print(summary,flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--root",type=Path,default=Path("drnas_v166"))
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--timeout",type=float,default=25)
    a=p.parse_args()
    if a.repeats<=0 or a.timeout<=0:
        p.error("positive repeats and timeout required")
    a.root.mkdir(parents=True,exist_ok=True)
    records=[]
    structural=[]
    for group,n,seed in CASES:
        path=a.root/"cnf"/group/f"random3_n{n}_seed{seed}.cnf"
        m=make_cnf(path,n,seed)
        features=structural_features(path,n)
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        structural.append(dict(group=group,seed=seed,sha256=sha,**features))
        print("STATIC",group,seed,features,"sha256",sha,flush=True)
        assert m==round(n*4.26)
        for rep in range(a.repeats):
            order=list(CONFIGS)
            order=order[rep%len(order):]+order[:rep%len(order)]
            for mode in order:
                log=a.root/"stats"/f"{group}_{seed}_{rep}_{mode}.txt"
                value=run_one(a.solver,mode,path,a.timeout,log)
                records.append(dict(group=group,nvars=n,seed=seed,
                    repeat=rep,mode=mode,profile=" ".join(CONFIGS[mode]) or "default",
                    status=value["status"],elapsed_sec=round(value["elapsed"],6),
                    returncode=value["rc"],conflicts=value["conflicts"],
                    restarts=value["restarts"],decisions=value["decisions"],
                    propagations=value["propagations"],learned=value["learned"],
                    stats_path=str(log)))
                print("MEASURE",group,seed,rep,mode,value["status"],
                      f"{value['elapsed']:.4f}s",
                      "conflicts",value["conflicts"],
                      "restarts",value["restarts"],flush=True)
    for name,records_,fieldnames in (
        ("measurements.csv",records,list(records[0])),
        ("features.csv",structural,list(structural[0]))):
        with (a.root/name).open("w",newline="",encoding="utf-8") as out:
            writer=csv.DictWriter(out,fieldnames=fieldnames)
            writer.writeheader();writer.writerows(records_)
    bykey=collections.defaultdict(dict)
    for r in records:
        if r["status"]=="ERROR":
            raise RuntimeError(f"Kissat ERROR on {r['seed']} {r['mode']}")
        bykey[(r["seed"],r["repeat"])][r["mode"]]=r
    assert len(bykey)==len(CASES)*a.repeats
    for key,variants in bykey.items():
        assert set(variants)==set(CONFIGS),key
        known={r["status"] for r in variants.values()
               if r["status"] in ("SAT","UNSAT")}
        if len(known)>1:
            raise RuntimeError(f"SAT/UNSAT mismatch at {key}: {known}")
    summarize(records,a.root/"summary.txt",a.timeout)
    print("VALIDATION_OK",len(records),"measurements",len(CASES),
          "instances including 4 untouched seeds",flush=True)

if __name__=="__main__":
    main()
