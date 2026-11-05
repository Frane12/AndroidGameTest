#!/usr/bin/env python3
"""DRNAS v16.9 — no-restart in-process SAT -> baseline/restart transition.

Pinned upstream Kissat is patched in search.c; one continuous solve retains
learned clauses and its assignment/search state. Compare against original cold
SAT probe & baseline on replay plus truly unseen 169xxx CNFs. Entire cost
charged to the 25s budget. No training or hyperparameter optimization here.
"""
import argparse
import csv
from collections import defaultdict
import hashlib
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import time

from satprobe_fallback_v168 import make as make_cnf

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CAP=20000
MODES=("baseline","sat-fixed","restart-only",
       "cold-satprobe-baseline","inproc-baseline","inproc-restart-only")
CASES=(("replay",640,165000),("replay",640,165001),
       ("holdout",480,169000),("holdout",640,169001),
       ("holdout",480,169002),("holdout",640,169003),
       ("holdout",480,169004),("holdout",640,169005))
FLAGS={"baseline":(),"sat-fixed":("--sat",),
       "restart-only":("--restartint=50",)}

SWITCH_PATTERN=re.compile(
    r"(?m)^c DRNAS_SWITCH conflicts=(\d+) learned_before=(\d+)"
    r" learned_after=(\d+) restarts=(\d+)"
    r" from_target=(\d+) to_target=(\d+)"
    r" from_restartint=(\d+) to_restartint=(\d+)"
    r" mode=(baseline|restart-only)$")
CONFLICT_PATTERN=re.compile(
    r"(?m)^c\s+conflicts:\s*([0-9][0-9,]*)")

def call(solver,mode,path,timeout,cap=None,switch=None):
    cmd=[str(solver),"-s"]
    if cap is not None:
        cmd.append(f"--conflicts={cap}")
    if switch:
        cmd.append("--sat")
    else:
        cmd.extend(FLAGS[mode])
    cmd.append(str(path))
    env=os.environ.copy()
    env.pop("DRNAS_SWITCH_MODE",None)
    env.pop("DRNAS_SWITCH_CONFLICTS",None)
    if switch:
        env["DRNAS_SWITCH_MODE"]=switch
        env["DRNAS_SWITCH_CONFLICTS"]=str(CAP)
    start=time.perf_counter()
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,
                            timeout=max(.001,timeout),env=env,check=False)
        result={0:"UNKNOWN",10:"SAT",20:"UNSAT"}.get(proc.returncode,"ERROR")
        stdout=proc.stdout
        stderr=proc.stderr
        code=proc.returncode
    except subprocess.TimeoutExpired as ex:
        result="TIMEOUT";code=-1
        stdout=ex.stdout or b""
        stderr=ex.stderr or b""
        if isinstance(stdout,bytes):
            stdout=stdout.decode("utf-8","replace")
        if isinstance(stderr,bytes):
            stderr=stderr.decode("utf-8","replace")
    elapsed=time.perf_counter()-start
    marker=SWITCH_PATTERN.findall(stdout)
    if len(marker)>1:
        raise RuntimeError(f"Multiple in-process switch events for {path}")
    sw=marker[0] if marker else None
    if sw:
        (at,before,after,restarts,target0,target1,restart0,restart1,selected)=sw
        if int(at)<CAP or int(after)!=int(before) or int(target0)!=2 or int(target1)!=1:
            raise RuntimeError(f"Broken state preservation instrumentation: {sw}")
        if int(restart0)!=50 or int(restart1)!=(1 if switch=="baseline" else 50):
            raise RuntimeError(f"Wrong restart option transition: {sw}")
        if selected!=switch:
            raise RuntimeError(f"Wrong switch target mode: {sw}")
    if marker and not switch:
        raise RuntimeError(f"Non-switch mode unexpectedly switched: {mode}")
    mc=CONFLICT_PATTERN.search(stdout)
    conflicts=int(mc.group(1).replace(",","")) if mc else None
    return dict(result=result,elapsed=elapsed,returncode=code,conflicts=conflicts,
                switched=bool(sw),switch_conflicts=(int(sw[0]) if sw else None),
                learned_at_switch=(int(sw[1]) if sw else None),
                restarts_at_switch=(int(sw[3]) if sw else None),
                command=" ".join(cmd),stderr=stderr[-500:],stdout=stdout[-1200:])

def run_mode(solver,path,mode,timeout,probe_timeout):
    if mode in FLAGS:
        r=call(solver,mode,path,timeout)
        if r["result"] not in ("SAT","UNSAT","TIMEOUT"):
            raise RuntimeError(f"Bad fixed run {path} {mode}: {r}")
        return dict(result=r["result"],seconds=r["elapsed"],probe_seconds=0.0,
                    continuation_seconds=r["elapsed"],
                    probe_result="none",conflicts=r["conflicts"],
                    switched=False,switch_conflicts="",learned_at_switch="",
                    restarts_at_switch="",stderr=r["stderr"])
    if mode.startswith("inproc-"):
        switch="baseline" if mode=="inproc-baseline" else "restart-only"
        r=call(solver,mode,path,timeout,switch=switch)
        if r["result"] not in ("SAT","UNSAT","TIMEOUT"):
            raise RuntimeError(f"Bad in-process run {path} {mode}: {r}")
        if r["result"]=="TIMEOUT" and not r["switched"]:
            # A timeout during preprocessing or stalled propagation could be
            # legitimate. Audit reports, never silently claim a switch.
            print("UNSWITCHED_TIMEOUT",path,mode,flush=True)
        return dict(result=r["result"],seconds=r["elapsed"],
                    probe_seconds=0.0,continuation_seconds=r["elapsed"],
                    probe_result="same-process",conflicts=r["conflicts"],
                    switched=r["switched"],
                    switch_conflicts=r["switch_conflicts"] or "",
                    learned_at_switch=r["learned_at_switch"] or "",
                    restarts_at_switch=r["restarts_at_switch"] if r["restarts_at_switch"] is not None else "",
                    stderr=r["stderr"])
    if mode!="cold-satprobe-baseline":
        raise ValueError(mode)
    start=time.perf_counter()
    probe=call(solver,"sat-fixed",path,min(probe_timeout,timeout),cap=CAP)
    if probe["result"]=="ERROR":
        raise RuntimeError(f"Cold probe error: {probe}")
    if probe["result"] in ("SAT","UNSAT"):
        return dict(result=probe["result"],seconds=time.perf_counter()-start,
                    probe_seconds=probe["elapsed"],continuation_seconds=0.0,
                    probe_result=probe["result"],conflicts=probe["conflicts"],
                    switched=False,switch_conflicts="",learned_at_switch="",
                    restarts_at_switch="",stderr=probe["stderr"])
    rest=timeout-(time.perf_counter()-start)
    if rest<=.002:
        return dict(result="TIMEOUT",seconds=time.perf_counter()-start,
                    probe_seconds=probe["elapsed"],continuation_seconds=0.0,
                    probe_result=probe["result"],conflicts="",
                    switched=False,switch_conflicts="",learned_at_switch="",
                    restarts_at_switch="",stderr=probe["stderr"])
    fallback=call(solver,"baseline",path,rest)
    if fallback["result"] not in ("SAT","UNSAT","TIMEOUT"):
        raise RuntimeError(f"Bad cold continuation: {fallback}")
    return dict(result=fallback["result"],seconds=time.perf_counter()-start,
                probe_seconds=probe["elapsed"],continuation_seconds=fallback["elapsed"],
                probe_result=probe["result"],conflicts=fallback["conflicts"],
                switched=False,switch_conflicts="",learned_at_switch="",
                restarts_at_switch="",stderr=fallback["stderr"])

def csvout(path,rows):
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--solver",required=True)
    parser.add_argument("--root",type=Path,default=Path("drnas_v169"))
    parser.add_argument("--timeout",type=float,default=25)
    parser.add_argument("--probe-timeout",type=float,default=3)
    parser.add_argument("--repeats",type=int,default=2)
    parser.add_argument("--group",choices=("replay","holdout","all"),default="all")
    a=parser.parse_args()
    if a.repeats<1 or a.timeout<1 or a.probe_timeout<=0:
        parser.error("Invalid limits")
    a.root.mkdir(parents=True,exist_ok=True)
    selected_cases=tuple(x for x in CASES if a.group=="all" or x[0]==a.group)
    rows=[];identities=[]
    for group,n,seed in selected_cases:
        cnf=a.root/"cnf"/group/f"{seed}.cnf"
        digest=make_cnf(cnf,n,seed)
        identities.append(dict(group=group,seed=seed,nvars=n,sha256=digest))
        print("GENERATED",group,seed,digest,flush=True)
        for rep in range(a.repeats):
            ordered=MODES[rep%len(MODES):]+MODES[:rep%len(MODES)]
            for mode in ordered:
                details=run_mode(a.solver,cnf,mode,a.timeout,a.probe_timeout)
                row=dict(group=group,seed=seed,nvars=n,repeat=rep,
                         mode=mode,**details)
                rows.append(row)
                print("MEASURE",group,seed,rep,mode,details["result"],
                      f'{details["seconds"]:.4f}s',"switched",
                      details["switched"],"conflicts",details["conflicts"],
                      "learned_at_switch",details["learned_at_switch"],flush=True)
                if details["result"] not in ("SAT","UNSAT","TIMEOUT"):
                    raise RuntimeError(f"Unexpected result: {details}")
    csvout(a.root/"identities.csv",identities)
    csvout(a.root/"measurements.csv",rows)
    assert len(rows)==len(selected_cases)*len(MODES)*a.repeats,len(rows)
    groups=defaultdict(dict)
    for r in rows:
        groups[(r["seed"],r["repeat"])][r["mode"]]=r
        if r["mode"] in ("inproc-baseline","inproc-restart-only"):
            if r["switched"] and int(r["learned_at_switch"])<=0:
                raise RuntimeError(f"No learned clauses at switch: {r}")
        if float(r["seconds"]) > a.timeout+.35:
            raise RuntimeError(f"Budget exceeded: {r}")
    for key,ms in groups.items():
        assert set(ms)==set(MODES),key
        answers={r["result"] for r in ms.values()
                 if r["result"] in ("SAT","UNSAT")}
        if len(answers)>1:
            raise RuntimeError(f"SAT/UNSAT mismatch {key}: {answers}")
    txt=["DRNAS SAT v16.9: IN-PROCESS STATE-PRESERVING SWITCH",
         "Kissat upstream SHA "+PINNED,
         f"Conflict trigger {CAP}. One kissat_solve() per in-process run.",
         "NOTE: baseline/restart options changed at trigger; all learned clauses retained.",
         "Cold portfolio stops and reconstructs a NEW solver (for comparison).",
         "No tuning with unseen CNF results. 25s budget applies to full run."]
    for group in ("replay","holdout"):
        if not any(r["group"]==group for r in rows):
            continue
        txt.append(f"GROUP {group}")
        for mode in MODES:
            subset=[r for r in rows if r["group"]==group and r["mode"]==mode]
            solved=sum(r["result"] in ("SAT","UNSAT") for r in subset)
            par2=statistics.mean(float(r["seconds"])
                     if r["result"] in ("SAT","UNSAT") else 2*a.timeout for r in subset)
            median=statistics.median(float(r["seconds"]) for r in subset)
            changes=sum(bool(r["switched"]) for r in subset)
            txt.append(f"{mode}: solved={solved}/{len(subset)} median={median:.5f}s "
                       f"PAR2={par2:.5f}s inprocess_switches={changes}")
        for seed in sorted({r["seed"] for r in rows if r["group"]==group}):
            txt.append(f" SEED {seed}")
            for mode in MODES:
                subset=[r for r in rows if r["seed"]==seed and r["mode"]==mode]
                txt.append(f"  {mode}: median={statistics.median(float(r['seconds']) for r in subset):.5f}s "
                           f"status={'/'.join(r['result'] for r in subset)} "
                           f"switches={sum(bool(r['switched']) for r in subset)}")
    txt.append("No general performance claim from 6 artificial 3SAT seeds.")
    report="\n".join(txt)+"\n"
    (a.root/"summary.txt").write_text(report,encoding="utf8")
    print(report,flush=True)
    print("V169_PARITY_AND_STATE_AUDIT_PASSED",len(rows),flush=True)

if __name__=="__main__":
    main()
