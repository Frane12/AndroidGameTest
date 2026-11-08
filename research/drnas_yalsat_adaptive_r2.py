#!/usr/bin/env python3
"""DRNAS YalSAT R2: frozen structure gate and four YalSAT scouting budgets.

Causal evaluation on the SAME 48 pinned, REUSED source CNFs as R1.
The gate may inspect original CNF structure only. It NEVER reads expected SAT/UNSAT
or benchmark IDs. All parsing, YalSAT, fallback, witness checking, and startup
overhead are charged to the same 30-second wall clock as baseline.
Frozen R193 and frozen V15.3.1 remain unmodified. UNSAT has no independent proof.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import sys
import time

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import drnas_yalsat_scout as base

ROOT=pathlib.Path("drnas_yalsat_r2")
CAP=30.0
SHARDS=8
REPS=2
PROTO="DRNAS-YALSAT-R2-48SHA-12ARMS-2REPS-30S-v1"
PINNED_R1_RUN="42435569125"
# Branch-independent, frozen before looking at R2 outcomes.
BUDGETS=(0.05,0.10,0.25,0.65)
MODES=("r193","cms",
       "y05_r193","y10_r193","y25_r193","y65_r193",
       "y05_cms","y10_cms","y25_cms","y65_cms",
       "adaptive_r193","adaptive_cms")

def need(cond,reason):
    if not cond: raise RuntimeError("DRNAS_YALSAT_R2_FAIL_CLOSED "+str(reason))

def save(path,obj):
    p=pathlib.Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def structural_profile(path, limit=2048):
    """Bounded, causal DIMACS feature scan. No labels or dataset identifiers."""
    nv=nc=None
    sampled=units=binary=ternary=positive_horn=longer=0
    current=[]
    with pathlib.Path(path).open() as fp:
        stop=False
        for raw in fp:
            s=raw.strip()
            if not s or s.startswith("c") or s.startswith("%"):continue
            if s.startswith("p cnf "):
                parts=s.split()
                need(len(parts)==4,"bad DIMACS header")
                nv,nc=int(parts[2]),int(parts[3])
                continue
            need(nv is not None,"clause before DIMACS header")
            for tok in s.split():
                lit=int(tok)
                if lit:
                    current.append(lit)
                    continue
                length=len(current)
                sampled+=1
                units+=(length==1)
                binary+=(length==2)
                ternary+=(length==3)
                longer+=(length>=4)
                positive_horn+=(sum(l>0 for l in current)<=1)
                current=[]
                if sampled>=limit:
                    stop=True
                    break
            if stop:break
    need(nv is not None and nc is not None,"missing DIMACS header")
    need(nv>0 and nc>0,"unexpected empty formula")
    return dict(vars=nv,clauses=nc,sampled=sampled,
                unit_fraction=round(units/max(1,sampled),5),
                binary_fraction=round(binary/max(1,sampled),5),
                ternary_fraction=round(ternary/max(1,sampled),5),
                longer_fraction=round(longer/max(1,sampled),5),
                horn_fraction=round(positive_horn/max(1,sampled),5),
                clause_var_ratio=round(nc/max(1,nv),5))

def static_adaptive_cap(f):
    """Pre-registered zero/short/medium/long policy, not a learned classifier."""
    if f["vars"]>10000 or f["clauses"]>65000:
        return 0.0,"SKIP_SIZE"
    if f["vars"]<48 or f["clauses"]<150:
        return 0.0,"SKIP_TRIVIAL"
    if f["unit_fraction"]>0.05 or f["horn_fraction"]>=0.94:
        return 0.0,"SKIP_UNIT_OR_HORN"
    if f["binary_fraction"]>0.70:
        return 0.0,"SKIP_BINARY_DOMINANT"
    if f["ternary_fraction"]>=0.60 and f["clause_var_ratio"]>=3.0:
        return 0.25,"SCOUT_3SAT_DENSE"
    if f["ternary_fraction"]>=0.25:
        return 0.10,"SCOUT_3SAT_MIX"
    return 0.05,"SCOUT_OTHER"

def decode(mode):
    if mode in ("r193","cms"):return mode,0.0,"BASELINE"
    if mode.startswith("adaptive_"):return mode.split("_",1)[1],None,"ADAPTIVE"
    prefix,backend=mode.split("_",1)
    cap={"y05":0.05,"y10":0.10,"y25":0.25,"y65":0.65}[prefix]
    return backend,cap,"FIXED"

def trial(c,rep,mode,binary,cms,yals):
    path=(base.FROZEN/(c["id"]+".cnf")).resolve()
    start=time.perf_counter()
    need(base.sha(path)==c["sha256"],"original SHA mismatch")
    backend,pilot_cap,policy=decode(mode)
    order=int(hashlib.sha256((PROTO+c["sha256"]+str(rep)).encode()).hexdigest()[:4],16)%2
    seed=int(hashlib.sha256(("YALSAT-R2"+c["sha256"]+str(rep)).encode()).hexdigest()[:12],16)
    f=None
    reason=policy
    if policy=="ADAPTIVE":
        f=structural_profile(path)
        pilot_cap,reason=static_adaptive_cap(f)
    chain=[]
    if pilot_cap:
        left=CAP-(time.perf_counter()-start)
        scout=base.invoke("yalsat",path,min(pilot_cap,max(0,left)),order,seed,binary,cms,yals)
        chain.append(dict(solver="yalsat",status=scout["status"],elapsed_s=round(scout["elapsed"],6),
                          proof=scout["proof"]))
        if scout["status"]=="SAT":
            result=scout
        else:
            left=CAP-(time.perf_counter()-start)
            result=base.invoke(backend,path,max(0,left),order,seed,binary,cms,yals)
            chain.append(dict(solver=backend,status=result["status"],
                              elapsed_s=round(result["elapsed"],6),proof=result["proof"]))
    else:
        left=CAP-(time.perf_counter()-start)
        result=base.invoke(backend,path,max(0,left),order,seed,binary,cms,yals)
        chain.append(dict(solver=backend,status=result["status"],
                          elapsed_s=round(result["elapsed"],6),proof=result["proof"]))
    elapsed=time.perf_counter()-start
    status=result["status"] if elapsed<CAP else "TIMEOUT"
    if status!="TIMEOUT" and c.get("expected") not in (None,"UNKNOWN"):
        need(status==c["expected"],"expected SAT/UNSAT mismatch")
    return dict(protocol=PROTO,source_sha256=c["sha256"],id=c["id"],
                family=c["family"],cohort=c["cohort"],mode=mode,rep=rep,seed=seed,order=order,
                status=status,elapsed_s=round(elapsed,6),
                par2_s=round(2*CAP if status=="TIMEOUT" else elapsed,6),
                policy=policy,reason=reason,pilot_cap_s=pilot_cap,
                profile=f,chain=chain,
                proof=result["proof"] if status!="TIMEOUT" else "CAP_TIMEOUT",
                commit=os.environ.get("GITHUB_SHA","local"),
                runner=os.environ.get("RUNNER_NAME","local"),
                run_id=os.environ.get("GITHUB_RUN_ID","local"))

def shard(i,binary,cms,yals):
    cs=base.cases()
    need(0<=i<SHARDS,"invalid shard number")
    rows=[]
    for c in cs[i::SHARDS]:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                row=trial(c,rep,mode,binary,cms,yals)
                rows.append(row)
                save(ROOT/("shard-%d.json"%i),rows)
                print("YALS_R2_TRIAL",json.dumps({key:row[key] for key in (
                    "id","cohort","mode","rep","status","elapsed_s","par2_s",
                    "pilot_cap_s","reason","chain")},sort_keys=True),flush=True)
    need(len(rows)==len(cs[i::SHARDS])*REPS*len(MODES),"incomplete paired shard")
    print("YALS_R2_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cs=base.cases()
    mapping={c["sha256"]:c for c in cs}
    rows=[]
    for i in range(SHARDS):
        part=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(part)==len(cs[i::SHARDS])*REPS*len(MODES),"incomplete shard "+str(i))
        rows.extend(part)
    need(len(rows)==48*REPS*len(MODES)==1152,"1152 measurements required")
    pairs=collections.defaultdict(dict)
    for r in rows:
        need(r["source_sha256"] in mapping and r["id"]==mapping[r["source_sha256"]]["id"],
             "source identity mismatch")
        key=(r["source_sha256"],r["rep"])
        need(r["mode"] not in pairs[key],"duplicate pair/mode")
        pairs[key][r["mode"]]=r
        need(abs(r["par2_s"]-(60 if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-5,
             "PAR2 accounting drift")
        if r["status"]=="SAT":
            need(r["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL","unwitnessed SAT")
        if r["policy"]=="ADAPTIVE":
            cap,reason=static_adaptive_cap(r["profile"])
            need(r["pilot_cap_s"]==cap and r["reason"]==reason,"adaptive gate drift")
    need(len(pairs)==48*REPS,"missing pairs")
    for p in pairs.values():
        need(set(p)==set(MODES),"missing modes in pair")
        need(len({x["status"] for x in p.values() if x["status"]!="TIMEOUT"})<=1,
             "contradictory terminal results")
    totals={}
    for cohort in ("all","new_seed_synthetic","reused_synthetic_control","reused_external_original"):
        a=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
        totals[cohort]={}
        for mode in MODES:
            part=[r for r in a if r["mode"]==mode]
            totals[cohort][mode]=dict(attempts=len(part),
                solved=sum(r["status"]!="TIMEOUT" for r in part),
                SAT=sum(r["status"]=="SAT" for r in part),
                UNSAT=sum(r["status"]=="UNSAT" for r in part),
                par2_s=round(sum(r["par2_s"] for r in part),6),
                scout_sat=sum(len(r["chain"])>0 and
                              r["chain"][0]["solver"]=="yalsat" and
                              r["chain"][0]["status"]=="SAT" for r in part),
                scout_skipped=sum(r["pilot_cap_s"]==0.0 for r in part))
    report=dict(protocol=PROTO,status="YALS_R2_AUDIT_PASS",
        trials=len(rows),cases=48,reps=REPS,modes=list(MODES),
        source_manifest_sha256=base.SOURCE_SHA,
        original_R1_run=PINNED_R1_RUN,
        original_sources_reused_not_blind=True,
        frozen_gates_no_outcome_labels=True,
        SAT_witness_checked_on_original=True,
        UNSAT_independent_proof=False,
        full_wall_clock_budget_s=CAP,
        totals=totals)
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("YALS_R2_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    assert static_adaptive_cap(dict(vars=100,clauses=1000,
               unit_fraction=0.,horn_fraction=.2,binary_fraction=.0,
               ternary_fraction=1.,clause_var_ratio=10.))[0]==.25
    assert static_adaptive_cap(dict(vars=100,clauses=1000,
               unit_fraction=.1,horn_fraction=.2,binary_fraction=.0,
               ternary_fraction=1.,clause_var_ratio=10.))[0]==0.
    assert static_adaptive_cap(dict(vars=20,clauses=1000,
               unit_fraction=0.,horn_fraction=.2,binary_fraction=.0,
               ternary_fraction=1.,clause_var_ratio=10.))[0]==0.
    for mode in MODES:
        b,c,p=decode(mode)
        need(b in ("r193","cms") and p in ("BASELINE","ADAPTIVE","FIXED"),"invalid mode")
    print("YALS_R2_SELFTEST_PASS",len(MODES),flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("verify","selftest","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--binary",default="drnas_yalsat/r193-driver")
    a.add_argument("--cms",default="cryptominisat5")
    a.add_argument("--yals",default="drnas_yalsat/yalsat")
    args=a.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="verify":print("YALS_R2_SOURCE_PASS",len(base.cases()),flush=True)
    elif args.action=="shard":shard(args.shard,args.binary,args.cms,args.yals)
    else:audit()
