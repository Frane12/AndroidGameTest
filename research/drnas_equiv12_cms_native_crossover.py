#!/usr/bin/env python3
"""EQUIV12: CMS 5.17 vs DRNAS on all five *already frozen* EQUIV10M5 CNF SHA.
Mechanistic matched cohort, NOT a new/unseen holdout. Six solver arms, two
repetitions, one logical CPU, original-input SAT witness checked, strict PAR2;
UNSAT only accepted on unmodified Kissat+CaDiCaL original agreement, NOT LRAT.
No automatic promotion and no modification of historical manifests or CNFs.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import tempfile
import time

import drnas_equiv9_prospective_seed_holdout as e9
import drnas_equiv10m5_frozen_rescue as m5

ROOT=pathlib.Path("mre_equiv12")
CMS=ROOT/"bin/cryptominisat5"
PROTO="DRNAS-EQUIV12-5FROZEN-SHA-CMS-NATIVE-CROSSOVER-6ARM-2REP-15S-v1"
ARMS=("native1","native_altseed","native_split4","kissat1",
      "cadical301_default","cms517_default")
CAP=15.0
REPS=2
COUNT=5
SHARDS=5
EXPECTED=COUNT*REPS*len(ARMS)
CMS_COMMIT="03954f7f7815ea3984774c95a66e7c224cd25952"

def need(ok,reason):
    if not ok:raise RuntimeError("EQUIV12_FAIL_CLOSED "+str(reason))

def digest(p):
    return e9.digest(p)

def dump(p,x):
    p=pathlib.Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")

def validate_originals():
    old=m5.verify()
    need(len(old["cases"])==COUNT and old["trial_count"]==50,
         "unexpected old frozen cohort")
    need(CMS.is_file(),"CMS binary absent")
    return old

def freeze():
    original=validate_originals()
    ROOT.mkdir(parents=True,exist_ok=True)
    man=dict(protocol=PROTO, source="EQUIV10M5 five frozen reference-selected original CNFs",
       NOT_NEW_HOLDOUT=True,reference_conditioned_selection=True,
       independent_UNSAT_LRAT=False,no_auto_promotion=True,
       cap_s=CAP,reps=REPS,shards=SHARDS,source_count=COUNT,arms=list(ARMS),
       expected_trials=EXPECTED,cases=original["cases"],
       original_manifest_sha256=digest(m5.ROOT/"manifest.json"),
       script_sha256=digest(__file__),native_bin_sha256=digest(e9.NATIVE),
       kissat_bin_sha256=digest(e9.KISSAT),cadical_bin_sha256=digest(e9.CAD),
       cms_bin_sha256=digest(CMS),cms_source_commit=CMS_COMMIT,
       pinned_single_logical_CPU=True,no_parallel_children=True,
       original_sat_witness_required=True)
    dump(ROOT/"manifest.json",man)
    verify()
    print("EQUIV12_FROZEN",json.dumps(dict(sources=COUNT,arms=len(ARMS),
          reps=REPS,paired=EXPECTED,cms_sha=man["cms_bin_sha256"],
          not_blind=True),sort_keys=True),flush=True)

def verify():
    orig=validate_originals()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["cases"]==orig["cases"] and
         m["arms"]==list(ARMS) and m["expected_trials"]==EXPECTED and
         m["reps"]==REPS and m["shards"]==SHARDS and m["cap_s"]==CAP,
         "registered protocol/roster changed")
    need(m["script_sha256"]==digest(__file__) and
         m["original_manifest_sha256"]==digest(m5.ROOT/"manifest.json") and
         m["native_bin_sha256"]==digest(e9.NATIVE) and
         m["kissat_bin_sha256"]==digest(e9.KISSAT) and
         m["cadical_bin_sha256"]==digest(e9.CAD) and
         m["cms_bin_sha256"]==digest(CMS),"code or frozen binaries drift")
    for c in orig["cases"]:
        need(digest(e9.SOURCE/c["filename"])==c["sha256"],
             "original CNF SHA drift")
    return m

def cms_trial(case,rep):
    src=e9.SOURCE/case["filename"]
    need(digest(src)==case["sha256"],"original SHA changed")
    n, clauses=e9.x22.read_cnf(src)
    need(n>0 and len(clauses)>0,"source parser failed")
    seed=e9.seedpair(case["sha256"],rep)[0]
    cpu=min(os.sched_getaffinity(0))
    begin=time.perf_counter(); prev=e9.x22.child_cpu()
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        child=e9.x22.launch("cms", [str(CMS),"--verb","0","-t","1",str(src)],
                            cpu,folder)
        status="TIMEOUT";witness=False
        try:
            while child["p"].poll() is None and time.perf_counter()-begin < CAP-.018:
                time.sleep(.004)
            if child["p"].poll() is not None:
                stdout,stderr=e9.x22.read_output(child)
                status,witness=e9.x22.solver_result("cms",
                    child["p"].returncode,stdout,clauses,{})
        finally:
            e9.x22.cleanup([child])
    elapsed=time.perf_counter()-begin
    if elapsed>=CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"CMS SAT original model invalid")
    return dict(protocol=PROTO, arm="cms517_default",sha256=case["sha256"],
        gbd=case["gbd"],cohort="historical_reference_conditioned",rep=rep,
        status=status,SAT_original_witness_verified=(status=="SAT" and witness),
        UNSAT_independent_LRAT=False,cap_s=CAP,wall_E2E_s=round(elapsed,6),
        child_CPU_s=round(e9.x22.child_cpu()-prev,6),
        seed_base=seed, pinned_cpu=cpu,child_starts=1,
        original_sha256_verified=True)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(CMS.is_file(),"CMS missing")
    with tempfile.TemporaryDirectory() as folder:
        src=pathlib.Path(folder)/"sat.cnf"
        src.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n")
        case=dict(filename=str(src),sha256=digest(src),gbd="toy")
        # The CMS helper normally draws from the historical source directory;
        # the toy executes the same parser/model-verifier directly.
        clauses=e9.x22.read_cnf(src)[1]
        c=e9.x22.launch("cms",[str(CMS),"--verb","0","-t","1",str(src)],
                         min(os.sched_getaffinity(0)),folder)
        try:
            c["p"].wait(timeout=20)
            out,_=e9.x22.read_output(c)
            status,w=e9.x22.solver_result("cms",c["p"].returncode,out,clauses,{})
            need(status=="SAT" and w,"toy SAT witness invalid")
        finally:
            e9.x22.cleanup([c])
    print("EQUIV12_SELFTEST_PASS CMS_SAT_original=True",flush=True)

def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,"invalid shard")
    c=m["cases"][idx]
    rows=[]
    for rep in range(REPS):
        arr=list(ARMS)
        random.Random(c["sha256"]+"|E12|"+str(rep)).shuffle(arr)
        for arm in arr:
            if arm=="cms517_default":
                row=cms_trial(c,rep)
            else:
                row=e9.trial(c,rep,arm,CAP)
                row["source_protocol"]=row["protocol"]
                row["protocol"]=PROTO
            row["shard"]=idx
            need(row["sha256"]==c["sha256"] and row["wall_E2E_s"]<=CAP+0.08
                 and (row["status"]!="SAT" or row["SAT_original_witness_verified"]),
                 "original SAT, SHA or cap violation")
            rows.append(row)
            dump(ROOT/("shard-%d.json"%idx),rows)
            print("EQUIV12_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(ARMS),"incomplete shard")
    print("EQUIV12_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for idx,c in enumerate(m["cases"]):
        shard_rows=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        need(len(shard_rows)==REPS*len(ARMS) and
             {r["sha256"] for r in shard_rows}=={c["sha256"]},
             "shard source/count mismatch")
        rows+=shard_rows
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    actual={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(actual)==len(expected) and actual==expected,
         "missing or duplicate SHA paired trial")
    by_sha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             r["wall_E2E_s"]<=CAP+.08 and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "invalid source SHA/witness/status/budget")
        by_sha[r["sha256"]].append(r)
    consensus=set()
    for sha, rr in by_sha.items():
        statuses={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT/UNSAT disagreement on original "+sha)
        if (any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr)
            and any(r["arm"]=="cadical301_default" and r["status"]=="UNSAT"
                    for r in rr)):
            consensus.add(sha)
    def ok(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in consensus)
    def score(rr):
        return dict(attempts=len(rr),solved=sum(ok(r) for r in rr),
            SAT_verified=sum(r["status"]=="SAT" for r in rr),
            UNSAT_ref_agreed_no_LRAT=sum(r["status"]=="UNSAT" and ok(r) for r in rr),
            UNSAT_not_confirmed=sum(r["status"]=="UNSAT" and not ok(r) for r in rr),
            timeouts=sum(r["status"]=="TIMEOUT" for r in rr),
            PAR2_s=round(sum(r["wall_E2E_s"] if ok(r) else 2*CAP for r in rr),6),
            actual_CPU_s=round(sum(r["child_CPU_s"] for r in rr),6),
            actual_wall_s=round(sum(r["wall_E2E_s"] for r in rr),6))
    scores={arm:score([r for r in rows if r["arm"]==arm]) for arm in ARMS}
    for arm in ARMS:
        scores[arm]["speedup_vs_kissat_PAR2_x"]=round(
           scores["kissat1"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
        scores[arm]["speedup_vs_cms_PAR2_x"]=round(
           scores["cms517_default"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
    report=dict(protocol=PROTO, source_count=COUNT,trials=EXPECTED,
       not_blind=True,reference_conditioned_frozen_cohort=True,
       original_SHA_verified=True, SAT_original_model_verified=True,
       independent_UNSAT_LRAT=False,
       UNSAT_original_backend_agreement=list(sorted(consensus)),
       cpu_policy="one logical CPU per solver, no parallel child portfolios",
       no_auto_promotion=True,scores=scores,
       per_sha={sha:dict(gbd=next(c["gbd"] for c in m["cases"] if c["sha256"]==sha),
                    per_arm={arm:[dict(rep=r["rep"],status=r["status"],
                                 wall_s=r["wall_E2E_s"],CPU_s=r["child_CPU_s"])
                       for r in rr if r["arm"]==arm] for arm in ARMS})
               for sha,rr in by_sha.items()})
    dump(ROOT/"report.json",report)
    print("EQUIV12_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    x=p.parse_args()
    if x.action=="shard":shard(x.shard)
    else:
        globals()[x.action]()
        if x.action=="verify":
            print("EQUIV12_VERIFY_PASS",flush=True)
