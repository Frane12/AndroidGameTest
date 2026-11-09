#!/usr/bin/env python3
"""DRNAS EQUIV8: reproducible single-core native multi-seed cold PROCESS restarts.
SAT certificates are checked on the EXACT original CNF by the frozen existing
reference verifier. A fresh solver process discards learnt clauses: unlike
an in-core CDCL restart this is a stronger cold reset with measurable overhead.
Previously observed SAT source (NOT blind). New disjoint deterministic seeds.
No parallel solver portfolio. Not independent UNSAT LRAT.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import random
import statistics
import subprocess
import tempfile
import time

import drnas_x16_singlecore_dual as x16
import drnas_x14_adaptive_portfolio as x14
import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_equiv8")
SOURCE=pathlib.Path("mre_equiv6/cases")
PRIOR=pathlib.Path("mre_equiv7/manifest.json")
NATIVE=pathlib.Path("mre_x4/bin/native")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CAD3=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
TARGET_GBD="5ea9d54e4eb8eeab1ff058471b9c83ca"
TARGET_SHA="c28e829957911baee4a9218f952f87f2c3d776669d3ac176a09dc47ee5729371"
PROTO="DRNAS-EQUIV8-SINGLECORE-SEED-HEDGE-8ARM-12REP-30S-v1"
CAP=30.0
REPS=12
SHARDS=6
ARMS=("native1","native_altseed","native_split4","native_split8",
      "native_split12","native_split16","cadical301_both","kissat1")
SPLITS={"native_split4":4.0,"native_split8":8.0,
        "native_split12":12.0,"native_split16":16.0}

def need(ok,reason):
    if not ok:raise RuntimeError("EQUIV8_FAIL_CLOSED "+str(reason))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def seeds(rep):
    need(0<=rep<REPS,"invalid rep")
    a=int(hashlib.sha256((TARGET_SHA+"|DRNAS_EQ8_BASE|"+str(rep)).encode()).hexdigest()[:7],16)
    b=int(hashlib.sha256((TARGET_SHA+"|DRNAS_EQ8_ALT|"+str(rep)).encode()).hexdigest()[:7],16)
    need(a!=b,"identical first/second seeds")
    return a,b
def command(arm,source,seed):
    if arm.startswith("native"):
        return x16.command("native",source,seed)
    if arm=="kissat1":
        return x16.command("kissat",source,seed)
    if arm=="cadical301_both":
        return [str(CAD3), "--no-congruence", "--no-reluctant", str(source)]
    need(False,"unregistered command")

def verify_model(arm,entry,src,clauses):
    stdout,stderr=x22.read_output(entry)
    rc=entry["p"].returncode
    if arm.startswith("native"):
        status=x14.outcome_of("native",rc,stdout,stderr,src)
        return status,status=="SAT"
    if arm=="kissat1":
        status=x14.outcome_of("kissat",rc,stdout,stderr,src)
        return status,status=="SAT"
    status,witness=x22.solver_result("cadical",rc,stdout,clauses,{})
    return status,witness

def freeze():
    ROOT.mkdir(exist_ok=True)
    prior=json.loads(PRIOR.read_text())
    need(prior["protocol"].startswith("DRNAS-EQUIV7-") and
         prior["target"]["sha256"]==TARGET_SHA,"EQUIV7 prior audit/source drift")
    src=SOURCE/prior["target"]["filename"]
    need(src.is_file() and digest(src)==TARGET_SHA,
         "original frozen SHA drift")
    bins={str(p):digest(p) for p in (NATIVE,KISSAT,CAD3)}
    prior_new=[]
    for rep in range(6):
        old=int(hashlib.sha256((TARGET_SHA+"|equiv7|"+str(rep)).encode()).hexdigest()[:7],16)
        prior_new.append(old)
    schedule=[dict(rep=i,base_seed=seeds(i)[0],alt_seed=seeds(i)[1])
              for i in range(REPS)]
    used={p["base_seed"] for p in schedule}|{p["alt_seed"] for p in schedule}
    need(len(used)==2*REPS and not used.intersection(prior_new),
         "new seeds overlap EQUIV7 or each other")
    m=dict(protocol=PROTO,source_filename=prior["target"]["filename"],
           sha256=TARGET_SHA,gbd=TARGET_GBD,cap_s=CAP,
           source_original_verified=True,
           earlier_trials_on_same_formula=True,blind_holdout=False,
           no_independent_UNSAT_LRAT=True,
           cold_process_restart_drops_all_learned_clauses=True,
           one_logical_CPU_per_arm=True,
           no_parallel_children=True,no_auto_promotion=True,
           previous_manifest_sha256=digest(PRIOR),
           code_sha256=digest(__file__),binary_sha256=bins,
           reps=REPS,shards=SHARDS,arms=ARMS,split_s=SPLITS,
           expected_trials=REPS*len(ARMS),schedule=schedule)
    save(ROOT/"manifest.json",m)
    verify()
    print("EQUIV8_FROZEN",json.dumps(dict(
        sources=1,reps=REPS,trials=REPS*len(ARMS),caps=CAP,
        schedule_first=schedule[0],no_prior_seed_reuse=True),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["reps"]==REPS and m["shards"]==SHARDS
         and m["expected_trials"]==REPS*len(ARMS),
         "manifest protocol drift")
    need(m["code_sha256"]==digest(__file__) and
         m["previous_manifest_sha256"]==digest(PRIOR),
         "code/prior SHA drift")
    need(m["binary_sha256"]=={str(p):digest(p)
                                for p in (NATIVE,KISSAT,CAD3)},
         "backend binary SHA drift")
    need(digest(SOURCE/m["source_filename"])==TARGET_SHA
         and m["sha256"]==TARGET_SHA,
         "original source SHA changed")
    need(m["schedule"]==[dict(rep=i,base_seed=seeds(i)[0],
                              alt_seed=seeds(i)[1]) for i in range(REPS)],
         "random schedule drift")
    return m

def one_stage(arm,src,clauses,seed,cpu,limit,folder,stage):
    """One child on one pinned CPU, no overlapping background solver."""
    started=time.perf_counter()
    prev_cpu=x22.child_cpu()
    status="TIMEOUT";verified=False
    child=x22.launch("s"+str(stage),command(arm,src,seed),cpu,folder)
    try:
        while child["p"].poll() is None and time.perf_counter()-started < limit-.018:
            time.sleep(.004)
        if child["p"].poll() is not None:
            status,verified=verify_model(arm,child,src,clauses)
    finally:
        x22.cleanup([child])
    elapsed=time.perf_counter()-started
    if elapsed>=limit or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"SAT witness invalid")
    return dict(stage=stage,seed=seed,budget_s=round(limit,5),
         status=status,SAT_original_witness_verified=verified,
         E2E_stage_s=round(elapsed,6),
         child_CPU_stage_s=round(x22.child_cpu()-prev_cpu,6))

def trial(rep,arm,toy=None):
    need(0<=rep<REPS and arm in ARMS,"invalid trial")
    m=verify() if toy is None else None
    src=SOURCE/m["source_filename"] if toy is None else toy
    need(toy is not None or digest(src)==TARGET_SHA,"source mismatch")
    base,alt=seeds(rep)
    allowed=sorted(os.sched_getaffinity(0))
    need(bool(allowed),"no CPU affinity set")
    cpu=allowed[0]
    started=time.perf_counter()
    before=x22.child_cpu()
    n,clauses=x22.read_cnf(src)
    need(n>0,"bad CNF")
    status="TIMEOUT";verified=False
    plan=[(base,CAP)]
    if arm in SPLITS:plan=[(base,SPLITS[arm]),(alt,CAP)]
    if arm=="native_altseed":plan=[(alt,CAP)]
    stages=[]
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        for i,(seed,target) in enumerate(plan):
            remaining=CAP-(time.perf_counter()-started)
            if remaining<.07:break
            budget=min(remaining,target)
            attempt=one_stage(arm,src,clauses,seed,cpu,budget,td,i)
            stages.append(attempt)
            if attempt["status"] in ("SAT","UNSAT"):
                status=attempt["status"]
                verified=attempt["SAT_original_witness_verified"]
                break
    elapsed=time.perf_counter()-started
    if elapsed>=CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"original SAT not verified")
    return dict(protocol=PROTO,sha256=TARGET_SHA if toy is None else digest(src),
        rep=rep,arm=arm,seed_base=base,seed_alt=alt,cap_s=CAP,
        status=status,SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,elapsed_E2E_s=round(elapsed,6),
        child_CPU_s=round(x22.child_cpu()-before,6),
        stages=stages,child_starts=len(stages),pinned_cpu=cpu)

def selftest():
    ROOT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        src=pathlib.Path(td)/"sat.cnf"
        src.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n")
        for arm in ARMS:
            for rep in (0,1):
                r=trial(rep,arm,toy=src)
                need(r["status"]=="SAT" and r["SAT_original_witness_verified"],
                     "original SAT selftest "+arm)
    print("EQUIV8_SELFTEST_PASS",len(ARMS)*2,flush=True)

def shard(idx):
    verify()
    need(0<=idx<SHARDS,"invalid shard")
    reps=list(range(idx,REPS,SHARDS))
    need(len(reps)==2,"two paired reps per shard")
    rows=[]
    for rep in reps:
        arms=list(ARMS)
        random.Random(seeds(rep)[0]).shuffle(arms)
        for arm in arms:
            row=trial(rep,arm)
            rows.append(row)
            save(ROOT/("shard-%d.json"%idx),rows)
            print("EQUIV8_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(reps)*len(ARMS),"incomplete shard")
    print("EQUIV8_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for i in range(SHARDS):
        a=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(a)==(REPS//SHARDS)*len(ARMS),"incomplete shard "+str(i))
        rows+=a
    keys={(r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(keys)==m["expected_trials"] and
         keys=={(rep,arm) for rep in range(REPS) for arm in ARMS},
         "missing/duplicate trial")
    statuses={r["status"] for r in rows if r["status"]!="TIMEOUT"}
    need(len(statuses)<=1,"original SAT UNSAT conflict")
    reference_unsat=(any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rows)
        and any(r["arm"]=="cadical301_both" and r["status"]=="UNSAT" for r in rows))
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and reference_unsat)
    scores={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        for r in a:
            need(r["protocol"]==PROTO and r["sha256"]==TARGET_SHA
                 and r["cap_s"]==CAP and
                 r["seed_base"]==seeds(r["rep"])[0] and
                 r["seed_alt"]==seeds(r["rep"])[1],
                 "trial source/seed drift")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "invalid model")
            need(r["child_starts"]==len(r["stages"]) and
                 r["child_starts"]<=2 and
                 r["elapsed_E2E_s"]<=CAP+.05,
                 "CPU/child budget drift")
        scores[arm]=dict(attempts=len(a),solved=sum(accepted(r) for r in a),
             SAT_verified=sum(r["status"]=="SAT" for r in a),
             unverified_UNSAT=sum(r["status"]=="UNSAT" and not accepted(r) for r in a),
             timeouts=sum(r["status"]=="TIMEOUT" for r in a),
             PAR2_s=round(sum(r["elapsed_E2E_s"] if accepted(r)
                              else 2*CAP for r in a),6),
             actual_child_CPU_s=round(sum(r["child_CPU_s"] for r in a),6),
             solver_child_starts=sum(r["child_starts"] for r in a),
             second_seed_solves=sum(r["status"]=="SAT" and len(r["stages"])==2
                                     and r["stages"][-1]["status"]=="SAT" for r in a),
             individual=[dict(rep=r["rep"],seed=r["seed_base"],
                              alt_seed=r["seed_alt"],
                              status=r["status"],
                              time_s=r["elapsed_E2E_s"],
                              stages=r["stages"])
                         for r in sorted(a,key=lambda q:q["rep"])])
    baseline=scores["native1"]["PAR2_s"]
    for v in scores.values():
        v["delta_PAR2_pct_vs_native1"]=round(100*(v["PAR2_s"]/baseline-1),4)
    report=dict(protocol=PROTO,gbd=TARGET_GBD,source_SHA=TARGET_SHA,
        not_blind=True,previously_observed_SAT_source=True,
        source_count=1,attempts=len(rows),caps_s=CAP,
        proof_status="SAT original model verified; UNSAT cross-backend only, no LRAT",
        no_parallel_portfolio=True,cold_restart_new_process_discards_all_learnts=True,
        source_hash_locked=True,scores=scores)
    save(ROOT/"report.json",report)
    print("EQUIV8_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="shard":shard(args.shard)
    else:
        globals()[args.action]()
        if args.action=="verify":print("EQUIV8_VERIFY_PASS",flush=True)
