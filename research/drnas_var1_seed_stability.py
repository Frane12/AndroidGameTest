#!/usr/bin/env python3
"""VAR1: repeat FIXED seeds from EQUIV7 on separate runners.
Development replay on ONE previously seen original SHA, not a blind holdout.
This diagnoses seed sensitivity versus runtime/runner variability.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import platform
import random
import statistics
import tempfile
import time

import drnas_x22_parallel_reducer as x22
import drnas_x14_adaptive_portfolio as x14
import drnas_equiv7_scc_native_repro as prior

ROOT=pathlib.Path("mre_var1")
PROTO="DRNAS-VAR1-FIXED-SEED-X-RUNNER-6SEEDS-2BLOCKS-3REPS-2ARMS-30S-v1"
ARMS=("native1","kissat1")
CAP=30.0
SEEDS=6
BLOCKS=2
REPS=3
TOTAL=SEEDS*BLOCKS*REPS*len(ARMS)

def need(ok,why):
    if not ok: raise RuntimeError("VAR1_FAIL_CLOSED "+str(why))
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def stable_seed(slot):
    return int(hashlib.sha256((prior.TARGET_SHA+"|equiv7|"+str(slot)).encode()).hexdigest()[:7],16)
def check():
    m=prior.verify()
    need(m["target"]["sha256"]==prior.TARGET_SHA and
         m["target"]["gbd"]==prior.TARGET_GBD,"wrong original SHA")
    need(len({stable_seed(i) for i in range(SEEDS)})==SEEDS,"duplicate seed")
    need(prior.NATIVE.is_file() and prior.KISSAT.is_file(),"missing pinned binaries")
    return m
def selftest():
    check()
    src=prior.SOURCE/check()["target"]["filename"]
    n,clauses=x22.read_cnf(src)
    need(n>0 and len(clauses)>0,"original CNF not parsed")
    need(x22.digest(src)==prior.TARGET_SHA,"source changed")
    need(prior.command("native1",src,stable_seed(0))[2]=="x_native","native mode drift")
    need(prior.command("native1",src,stable_seed(0))[3]==str(stable_seed(0)),"seed not passed")
    need("--seed="+str(stable_seed(0)) in prior.command("kissat1",src,stable_seed(0)),"Kissat seed drift")
    print("VAR1_SELFTEST_PASS",json.dumps(dict(source_sha=prior.TARGET_SHA,
          seeds=[stable_seed(i) for i in range(SEEDS)],arms=ARMS,trials=TOTAL)),flush=True)
def run(slot,block):
    m=check()
    need(0<=slot<SEEDS and 0<=block<BLOCKS,"matrix index")
    source=prior.SOURCE/m["target"]["filename"]
    need(x22.digest(source)==prior.TARGET_SHA,"source byte drift")
    seed=stable_seed(slot)
    cpu=sorted(os.sched_getaffinity(0))[0]
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for k in range(REPS):
        order=list(ARMS)
        random.Random(seed ^ (block<<12) ^ (k<<20)).shuffle(order)
        for arm in order:
            before=x22.child_cpu()
            start=time.perf_counter()
            status="TIMEOUT";witness=False
            cmd=prior.command(arm,source,seed)
            with tempfile.TemporaryDirectory(dir=ROOT) as td:
                child=x22.launch(arm,cmd,cpu,td)
                try:
                    while child["p"].poll() is None and time.perf_counter()-start<CAP-.02:
                        time.sleep(.005)
                    if child["p"].poll() is not None:
                        stdout,stderr=x22.read_output(child)
                        backend="native" if arm=="native1" else "kissat"
                        status=x14.outcome_of(backend,child["p"].returncode,
                                               stdout,stderr,source)
                        witness=status=="SAT"
                finally:
                    x22.cleanup([child])
            elapsed=time.perf_counter()-start
            if elapsed>=CAP or status not in ("SAT","UNSAT"):
                status="TIMEOUT";witness=False
            need(status!="SAT" or witness,"original SAT witness invalid")
            # The original SHA has previously verified SAT: any UNSAT here is a hard failure.
            need(status!="UNSAT","solver contradicted already-verified original SAT")
            row=dict(protocol=PROTO,source_sha256=prior.TARGET_SHA,gbd=prior.TARGET_GBD,
                arm=arm,seed_slot=slot,seed=seed,block=block,repeat=k,
                cpu=cpu,allowed_cpu_count=len(os.sched_getaffinity(0)),
                runner_name=os.environ.get("RUNNER_NAME","unknown"),
                github_run_id=os.environ.get("GITHUB_RUN_ID","unknown"),
                platform=platform.platform(),status=status,
                SAT_original_witness_verified=witness,
                E2E_s=round(elapsed,6),
                child_CPU_s=round(x22.child_cpu()-before,6),cap_s=CAP,
                PAR2_s=round(elapsed if status=="SAT" else 2*CAP,6),
                native_original_gate_unapplied=(arm=="native1" and status=="SAT"))
            rows.append(row)
            save(ROOT/("seed-%d-block-%d.json"%(slot,block)),rows)
            print("VAR1_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(ARMS),"missing trials")
    print("VAR1_SHARD_PASS",slot,block,len(rows),flush=True)
def audit():
    check()
    rows=[]
    for slot in range(SEEDS):
        for block in range(BLOCKS):
            p=ROOT/("seed-%d-block-%d.json"%(slot,block))
            part=json.loads(p.read_text())
            need(len(part)==REPS*len(ARMS),"missing shard "+str(p))
            rows+=part
    observed={(r["seed_slot"],r["block"],r["repeat"],r["arm"]) for r in rows}
    expected={(i,b,k,a) for i in range(SEEDS) for b in range(BLOCKS)
              for k in range(REPS) for a in ARMS}
    need(len(rows)==len(observed)==TOTAL and observed==expected,"bad coverage")
    for r in rows:
        need(r["protocol"]==PROTO and r["source_sha256"]==prior.TARGET_SHA and
             r["seed"]==stable_seed(r["seed_slot"]) and r["cap_s"]==CAP,
             "trial identity mismatch")
        need(r["status"] in ("SAT","TIMEOUT"),"invalid status")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],"bad witness")
    scores={}
    byseed={}
    for arm in ARMS:
        rr=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(solved=sum(r["status"]=="SAT" for r in rr),
            attempts=len(rr),timeouts=sum(r["status"]=="TIMEOUT" for r in rr),
            PAR2_s=round(sum(r["PAR2_s"] for r in rr),6),
            child_CPU_s=round(sum(r["child_CPU_s"] for r in rr),6))
        byseed[arm]={}
        for slot in range(SEEDS):
            g=[r for r in rr if r["seed_slot"]==slot]
            sat=[r["E2E_s"] for r in g if r["status"]=="SAT"]
            byseed[arm][str(slot)]=dict(seed=stable_seed(slot),solved=len(sat),
                timeouts=len(g)-len(sat),attempts=len(g),
                PAR2_s=round(sum(r["PAR2_s"] for r in g),6),
                median_solved_E2E_s=(round(statistics.median(sat),6) if sat else None),
                # Fixed-seed per-block variation helps separate CPU/runner noise.
                blocks={str(b):dict(solved=sum(r["status"]=="SAT" for r in g
                                              if r["block"]==b),
                                   runtimes=[r["E2E_s"] if r["status"]=="SAT" else None
                                             for r in sorted(g,key=lambda x:x["repeat"])
                                             if r["block"]==b])
                        for b in range(BLOCKS)})
    report=dict(protocol=PROTO,source_sha256=prior.TARGET_SHA,
        previously_seen_not_blind=True,controls_distinct_seed_and_repeat=True,
        seed_changes_between_slots_only=True,seed_replayed_across_independent_jobs=True,
        solver_source_verified=True,not_auto_promoted=True,
        calls_mre_x4_native_crypto_minisat=True,expected_trials=TOTAL,
        scores=scores,by_seed=byseed,
        native_vs_kissat_PAR2_ratio=round(scores["kissat1"]["PAR2_s"]/
                                         scores["native1"]["PAR2_s"],6),
        rows=rows)
    save(ROOT/"report.json",report)
    compact={k:v for k,v in report.items() if k!="rows"}
    print("VAR1_FINAL",json.dumps(compact,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","run","audit"))
    p.add_argument("--seed-slot",type=int,default=0)
    p.add_argument("--block",type=int,default=0)
    a=p.parse_args()
    if a.action=="run":run(a.seed_slot,a.block)
    elif a.action=="selftest":selftest()
    else:audit()
