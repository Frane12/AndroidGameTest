#!/usr/bin/env python3
"""DRNAS v16.8: cold SAT-first probing then deterministic fallbacks.

The profile and 20k conflict limit are PRE-REGISTERED from replay-only
v16.6/v16.7 observations. New seeds are generated without inspecting outcomes.
This is a sequential portfolio, not a modified Kissat core; all subprocess
wall time is counted toward the same 25s budget.

A completed SAT/UNSAT answer from the short trial is accepted directly.
If it returns UNKNOWN/TIMEOUT, launch fallback from scratch.
"""
import argparse
import csv
from collections import defaultdict
import hashlib
from pathlib import Path
import random
import re
import statistics
import subprocess
import time

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CAP=20000
MODES=("baseline","restart-only","sat-fixed","satprobe-baseline","satprobe-restart")
CASES=(("replay",640,165000),("replay",640,165001),
       ("holdout",480,168000),("holdout",640,168001),
       ("holdout",480,168002),("holdout",640,168003),
       ("holdout",480,168004),("holdout",640,168005))
ARGS={"baseline":(), "restart-only":("--restartint=50",), "sat-fixed":("--sat",)}

def make(path,n,seed):
    rng=random.Random(seed)
    m=round(n*4.26)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="ascii") as f:
        f.write(f"c DRNAS v16.8 seed={seed}\n")
        f.write(f"p cnf {n} {m}\n")
        for _ in range(m):
            variables=rng.sample(range(1,n+1),3)
            signs=[1 if rng.getrandbits(1) else -1 for _ in range(3)]
            f.write(" ".join(str(v*s) for v,s in zip(variables,signs))+" 0\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def kissat(solver,flags,path,limit,cap=None):
    cmd=[str(solver),"-s"]
    if cap is not None:
        cmd.append(f"--conflicts={cap}")
    cmd.extend(flags)
    cmd.append(str(path))
    begin=time.perf_counter()
    try:
        p=subprocess.run(cmd, capture_output=True,text=True,
                         check=False,timeout=limit)
        status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
        stdout=p.stdout
        stderr=p.stderr
        rc=p.returncode
    except subprocess.TimeoutExpired as exc:
        status="TIMEOUT";rc=-1
        stdout=exc.stdout or b"";stderr=exc.stderr or b""
        if isinstance(stdout,bytes):stdout=stdout.decode("utf-8","replace")
        if isinstance(stderr,bytes):stderr=stderr.decode("utf-8","replace")
    elapsed=time.perf_counter()-begin
    m=re.search(r"(?m)^c\s+conflicts:\s*([0-9][0-9,]*)",stdout)
    conflicts=int(m.group(1).replace(",","")) if m else ""
    return dict(status=status,seconds=elapsed,returncode=rc,conflicts=conflicts,
                command=" ".join(cmd),stdout=stdout[-1200:],stderr=stderr[-1200:])

def attempt(solver,path,mode,timeout,probe_timeout):
    if mode in ARGS:
        r=kissat(solver,ARGS[mode],path,timeout)
        return dict(result=r["status"],total_seconds=r["seconds"],
                    probe_seconds=0.0,solve_seconds=r["seconds"],
                    probe_outcome="none",solve_profile=mode,
                    probe_conflicts="",solve_conflicts=r["conflicts"],
                    error=r["stderr"] if r["status"]=="ERROR" else "")
    fallback="baseline" if mode=="satprobe-baseline" else "restart-only"
    start=time.perf_counter()
    first=kissat(solver,("--sat",),path,min(probe_timeout,timeout),cap=CAP)
    if first["status"]=="ERROR":
        raise RuntimeError(f"Probe ERROR: {path} {first['stderr']}")
    if first["status"] in ("SAT","UNSAT"):
        return dict(result=first["status"],
                    total_seconds=time.perf_counter()-start,
                    probe_seconds=first["seconds"],solve_seconds=0.0,
                    probe_outcome=first["status"],solve_profile="sat-probe-solved",
                    probe_conflicts=first["conflicts"],solve_conflicts="",
                    error="")
    remaining=timeout-(time.perf_counter()-start)
    if remaining<=0.002:
        return dict(result="TIMEOUT",total_seconds=time.perf_counter()-start,
                    probe_seconds=first["seconds"],solve_seconds=0.0,
                    probe_outcome=first["status"],solve_profile=fallback,
                    probe_conflicts=first["conflicts"],solve_conflicts="",
                    error="")
    final=kissat(solver,ARGS[fallback],path,remaining)
    if final["status"]=="ERROR":
        raise RuntimeError(f"Fallback ERROR: {path} {final['stderr']}")
    return dict(result=final["status"],
                total_seconds=time.perf_counter()-start,
                probe_seconds=first["seconds"],solve_seconds=final["seconds"],
                probe_outcome=first["status"],solve_profile=fallback,
                probe_conflicts=first["conflicts"],
                solve_conflicts=final["conflicts"],error="")

def write_csv(file,rows):
    with file.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def report(rows,timeout):
    lines=["DRNAS v16.8 sequential SAT-first portfolio",
           "Pinned Kissat "+PINNED,
           f"SAT cold-probe conflict cap={CAP}; timeout={timeout}s inclusive of probe.",
           "Fixed holdout seeds and policy before any measurements; no tuning on holdout.",
           "WARNING: probes RESTART state and may regress easy problems."]
    for group in ("replay","holdout"):
        lines.append(f"GROUP {group}")
        for mode in MODES:
            rs=[r for r in rows if r["group"]==group and r["mode"]==mode]
            solved=sum(r["result"] in ("SAT","UNSAT") for r in rs)
            par2=statistics.mean(float(r["total_seconds"])
                 if r["result"] in ("SAT","UNSAT") else 2*timeout for r in rs)
            median=statistics.median(float(r["total_seconds"]) for r in rs)
            lines.append(f" {mode}: solved={solved}/{len(rs)} median={median:.5f}s PAR2={par2:.5f}s")
        for seed in sorted({r["seed"] for r in rows if r["group"]==group}):
            lines.append(" SEED "+str(seed))
            for mode in MODES:
                rs=[r for r in rows if r["seed"]==seed and r["mode"]==mode]
                times=[float(r["total_seconds"]) for r in rs]
                lines.append(f"  {mode}: median={statistics.median(times):.4f}s "
                    f"statuses={'/'.join(r['result'] for r in rs)}")
    lines.append("No general performance claims unless independently replicated.")
    return "\n".join(lines)+"\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",required=True)
    p.add_argument("--root",type=Path,default=Path("drnas_v168"))
    p.add_argument("--timeout",type=float,default=25)
    p.add_argument("--probe-timeout",type=float,default=3)
    p.add_argument("--repeats",type=int,default=2)
    a=p.parse_args()
    if a.timeout<1 or a.probe_timeout<=0 or a.repeats<1:
        p.error("positive limits required")
    a.root.mkdir(parents=True,exist_ok=True)
    rows=[];identities=[]
    for group,n,seed in CASES:
        cnf=a.root/"cnf"/group/f"random3_n{n}_seed{seed}.cnf"
        digest=make(cnf,n,seed)
        identities.append(dict(group=group,nvars=n,seed=seed,sha256=digest))
        print("GENERATED",group,seed,digest,flush=True)
        for rep in range(a.repeats):
            order=MODES[rep%len(MODES):]+MODES[:rep%len(MODES)]
            for mode in order:
                result=attempt(a.solver,cnf,mode,a.timeout,a.probe_timeout)
                row=dict(group=group,nvars=n,seed=seed,repeat=rep,mode=mode,**result)
                rows.append(row)
                print("MEASURE",group,seed,rep,mode,row["result"],
                    f'{row["total_seconds"]:.4f}s',
                    "probe",row["probe_outcome"],
                    "fallback",row["solve_profile"],flush=True)
                if result["result"] in ("ERROR","UNKNOWN"):
                    raise RuntimeError(f"Unacceptable full-run result: {row}")
    write_csv(a.root/"measurements.csv",rows)
    write_csv(a.root/"identity.csv",identities)
    pairs=defaultdict(dict)
    for r in rows:
        key=(r["seed"],r["repeat"])
        pairs[key][r["mode"]]=r
    assert len(rows)==len(CASES)*len(MODES)*a.repeats
    for key,ms in pairs.items():
        assert set(ms)==set(MODES),key
        statuses={r["result"] for r in ms.values() if r["result"] in ("SAT","UNSAT")}
        if len(statuses)>1:
            raise RuntimeError(f"SAT/UNSAT mismatch at {key}: {statuses}")
        for mode in ("satprobe-baseline","satprobe-restart"):
            r=ms[mode]
            assert r["probe_outcome"] in ("SAT","UNSAT","UNKNOWN","TIMEOUT")
            assert float(r["total_seconds"]) <= a.timeout+0.25
            assert float(r["probe_seconds"])>0
    output=report(rows,a.timeout)
    (a.root/"summary.txt").write_text(output,encoding="utf8")
    print(output,flush=True)
    print("V168_HOLDOUT_VALIDATED",len(rows),"runs",flush=True)

if __name__=="__main__":
    main()
