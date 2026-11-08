#!/usr/bin/env python3
"""DRNAS YalSAT scout: source-paired live YalSAT -> frozen R193/CDCL or CMS.
No outcomes, family, or benchmark ID used for selection. Existing SHA frozen
R193 original CNFs are REUSED controls, not prospective blind official cases.
SAT models validated on the original CNF. UNSAT is NOT independently certified.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import time

ROOT=pathlib.Path("drnas_yalsat")
FROZEN=ROOT/"frozen"
SOURCE_SHA="9eebc6fc1e8ad3006fc3ecc8b451e1e57d3087932190ba5a91fd60aabf278658"
MODES=("r193","cms","yalsat","drnas_yalsat_r193","drnas_yalsat_cms")
PROTO="DRNAS-YALSAT-SCOUT-48CNF-5ARMS-2REPS-30S-v1"
SHARDS=8
REPS=2
CAP=30.0
SCOUT_CAP=0.65

def need(condition,reason):
    if not condition: raise RuntimeError("DRNAS_YALSAT_FAIL_CLOSED "+str(reason))

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def cases():
    need(sha(FROZEN/"manifest.json")==SOURCE_SHA,"original manifest SHA drift")
    data=json.loads((FROZEN/"manifest.json").read_text())
    need(len(data["cases"])==102,"R193 frozen 102 original sources missing")
    chosen=[]
    for cohort,n in (("new_seed_synthetic",16),("reused_synthetic_control",8),
                     ("reused_external_original",24)):
        subset=sorted((c for c in data["cases"] if c["cohort"]==cohort),
                      key=lambda c:c["sha256"])
        need(len(subset)>=n,"incomplete cohort "+cohort)
        chosen+=subset[:n]
    need(len(chosen)==48 and len({c["sha256"] for c in chosen})==48,"not 48 distinct SHA")
    for c in chosen:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"CNF SHA drift "+c["id"])
    return chosen

def header_features(path):
    nvars=nclauses=None;count_two=0;count_lines=0
    with path.open() as fp:
        for line in fp:
            if line.startswith("p cnf "):
                a=line.split();nvars=int(a[2]);nclauses=int(a[3]);break
    need(nvars is not None and nclauses is not None,"missing DIMACS header")
    # Fully predeclared structural eligibility only (no target status / family).
    return dict(vars=nvars,clauses=nclauses,
                scout_eligible=(nvars<=30000 and nclauses<=100000))

def seed_of(c,rep):
    return int(hashlib.sha256((PROTO+c["sha256"]+str(rep)).encode()).hexdigest()[:12],16)

def invoke(mode,path,cap,order,seed,binary,cms,yals):
    if cap<0.01:return dict(status="TIMEOUT",elapsed=0.0,model={},proof="CAP",raw_status="NONE")
    if mode=="r193":
        command=[binary,str(path),str(max(0.01,cap)),"dual_keep_default",str(order)]
    elif mode=="cms":
        command=[cms,str(path)]
    elif mode=="yalsat":
        command=[yals,str(path),str(seed)]
    else:raise RuntimeError("invalid solver mode")
    t=time.perf_counter()
    try:
        proc=subprocess.run(command,capture_output=True,text=True,errors="replace",
                            timeout=cap+0.015,check=False)
        elapsed=time.perf_counter()-t
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",elapsed=time.perf_counter()-t,
                    model={},proof="CAP",raw_status="OS_TIMEOUT")
    stdout=proc.stdout
    status="TIMEOUT"
    if mode=="r193":
        need(proc.returncode==0,"native R193 crashed "+proc.stderr[-300:])
        m=re.search(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",stdout,re.M)
        need(m is not None,"native R193 missing terminal status")
        status=m.group(1)
    elif mode=="cms":
        need(proc.returncode in (0,10,20),"CMS unexpected exit "+str(proc.returncode))
        m=re.search(r"^s (SATISFIABLE|UNSATISFIABLE|UNKNOWN)\s*$",stdout,re.M)
        if m:status={"SATISFIABLE":"SAT","UNSATISFIABLE":"UNSAT","UNKNOWN":"TIMEOUT"}[m.group(1)]
        if proc.returncode==10:need(status=="SAT","CMS SAT status disagreement")
        if proc.returncode==20:need(status=="UNSAT","CMS UNSAT status disagreement")
    else:
        need(proc.returncode in (0,10,20),"YalSAT unexpected exit "+str(proc.returncode))
        if proc.returncode==10 and re.search(r"^s SATISFIABLE\s*$",stdout,re.M):
            status="SAT"
        # YalSAT is NOT an UNSAT proof method; ignore non-SAT terminal statuses.
    if elapsed>=cap:status="TIMEOUT"
    model={}
    if status=="SAT":
        for line in stdout.splitlines():
            if line.startswith("v "):
                for token in line[2:].split():
                    lit=int(token)
                    if not lit:continue
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "contradictory witness assignments")
                    model[abs(lit)]=lit>0
        need(model,"SAT without witness")
        validate_original_model(path,model)
    return dict(status=status,elapsed=elapsed,model={},raw_status=status,
                proof=("SAT_WITNESS_CHECKED_ORIGINAL" if status=="SAT" else
                       "UNSAT_NO_INDEPENDENT_PROOF" if status=="UNSAT" else "CAP"))

def validate_original_model(path,model):
    # DIMACS supports clauses spanning lines and multiple clauses per line.
    current=[]
    number=0
    with path.open() as f:
        for line in f:
            if not line.strip() or line[0] in ("c","p","%"):
                continue
            for item in line.split():
                lit=int(item)
                if lit:
                    current.append(lit)
                else:
                    need(any(model.get(abs(v))==(v>0) for v in current),
                         "SAT model failed original CNF clause "+str(number))
                    number+=1;current=[]
    need(not current,"unterminated original CNF clause")

def run_case(c,rep,mode,binary,cms,yals):
    path=(FROZEN/(c["id"]+".cnf")).resolve()
    need(sha(path)==c["sha256"],"source SHA mismatch at run")
    order=int(hashlib.sha256((PROTO+c["sha256"]+str(rep)).encode()).hexdigest()[:4],16)%2
    seed=seed_of(c,rep)
    start=time.perf_counter()
    features=header_features(path)
    gates=[]
    results=[]
    if mode in ("drnas_yalsat_r193","drnas_yalsat_cms"):
        selected=("r193" if mode.endswith("r193") else "cms")
        if features["scout_eligible"]:
            scout=invoke("yalsat",path,SCOUT_CAP,order,seed,binary,cms,yals)
            gates.append("SCOUT_FROZEN_STRUCTURE_ELIGIBLE")
            results.append(("yalsat",scout))
            if scout["status"]=="SAT":
                res=scout
            else:
                left=max(0,CAP-(time.perf_counter()-start))
                res=invoke(selected,path,left,order,seed,binary,cms,yals)
                results.append((selected,res))
        else:
            gates.append("SCOUT_SKIPPED_FROZEN_STRUCTURE")
            left=max(0,CAP-(time.perf_counter()-start))
            res=invoke(selected,path,left,order,seed,binary,cms,yals)
            results.append((selected,res))
    else:
        res=invoke(mode,path,max(0,CAP-(time.perf_counter()-start)),
                   order,seed,binary,cms,yals)
        results.append((mode,res))
    elapsed=time.perf_counter()-start
    status=res["status"]
    if elapsed>=CAP:status="TIMEOUT"
    if status!="TIMEOUT" and c.get("expected") not in (None,"UNKNOWN"):
        need(c["expected"]==status,"known class disagreement")
    return dict(protocol=PROTO,id=c["id"],source_sha256=c["sha256"],
        cohort=c["cohort"],family=c["family"],mode=mode,rep=rep,seed=seed,order=order,
        runner=os.environ.get("RUNNER_NAME","unknown"),
        commit=os.environ.get("GITHUB_SHA","local"),
        run_id=os.environ.get("GITHUB_RUN_ID","local"),
        features=features,gate=gates,
        chain=[dict(solver=a,status=b["status"],elapsed_s=round(b["elapsed"],6),
                    proof=b["proof"]) for a,b in results],
        cap_s=CAP,status=status,elapsed_s=round(elapsed,6),
        par2_s=round(2*CAP if status=="TIMEOUT" else elapsed,6),
        proof=(res["proof"] if status!="TIMEOUT" else "CAP_TIMEOUT"))

def shard(idx,binary,cms,yals):
    cs=cases()
    need(0<=idx<SHARDS,"bad shard index")
    data=[]
    for c in cs[idx::SHARDS]:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                row=run_case(c,rep,arm,binary,cms,yals)
                data.append(row)
                save(ROOT/("shard-%d.json"%idx),data)
                print("DRNAS_YALSAT_TRIAL",json.dumps({k:row[k] for k in
                     ("id","cohort","mode","rep","status","elapsed_s","par2_s","gate","chain")},
                     sort_keys=True),flush=True)
    need(len(data)==len(cs[idx::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("DRNAS_YALSAT_SHARD_PASS",idx,len(data),flush=True)

def audit():
    cs=cases();bysha={c["sha256"]:c for c in cs}
    data=[]
    for idx in range(SHARDS):
        part=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        need(len(part)==len(cs[idx::SHARDS])*REPS*len(MODES),"incomplete paired shard")
        data+=part
    need(len(data)==48*REPS*len(MODES)==480,"expected 480 trials")
    groups=collections.defaultdict(dict)
    for row in data:
        need(row["source_sha256"] in bysha and
             row["id"]==bysha[row["source_sha256"]]["id"],"source identity drift")
        key=(row["source_sha256"],row["rep"])
        need(row["mode"] not in groups[key],"duplicate source/repeat/mode")
        groups[key][row["mode"]]=row
        need(abs(row["par2_s"]-
                 (CAP*2 if row["status"]=="TIMEOUT" else row["elapsed_s"]))<1e-5,
             "PAR2 accounting")
        if row["status"]=="SAT":need(row["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL","unwitnessed SAT")
        if row["mode"].startswith("drnas_"):
            need(row["chain"][-1]["solver"] in ("r193","cms","yalsat"),"invalid fallback")
    need(len(groups)==48*REPS,"unpaired")
    for rr in groups.values():
        need(set(rr)==set(MODES),"missing arm")
        need(len({v["status"] for v in rr.values() if v["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT contradiction")
    totals={}
    for cohort in ("all","new_seed_synthetic","reused_synthetic_control",
                   "reused_external_original"):
        sub=[x for x in data if cohort=="all" or x["cohort"]==cohort]
        totals[cohort]={}
        for mode in MODES:
            rows=[x for x in sub if x["mode"]==mode]
            totals[cohort][mode]=dict(attempts=len(rows),
                solved=sum(x["status"]!="TIMEOUT" for x in rows),
                SAT=sum(x["status"]=="SAT" for x in rows),
                UNSAT=sum(x["status"]=="UNSAT" for x in rows),
                par2_s=round(sum(x["par2_s"] for x in rows),6),
                scout_sat=sum(bool(x["chain"]) and x["chain"][0]["solver"]=="yalsat" and
                              x["chain"][0]["status"]=="SAT" for x in rows),
                scout_skipped=sum("SCOUT_SKIPPED_FROZEN_STRUCTURE" in x["gate"] for x in rows))
    output=dict(protocol=PROTO,status="DRNAS_YALSAT_AUDIT_PASS",
        cases=len(cs),attempts=len(data),
        source_manifest_sha256=SOURCE_SHA,source_SHA_validated=True,
        source_cohorts_reused_not_blind=True,
        YalSAT_only_SAT_witness_accepted=True,
        SAT_witness_original_checked=True,
        UNSAT_independent_certificate=False,SCOUT_CAP_S=SCOUT_CAP,
        R193_CaDiCaL_unchanged=True,totals=totals)
    save(ROOT/"report.json",output)
    save(ROOT/"all-trials.json",data)
    print("DRNAS_YALSAT_FINAL",json.dumps(output,sort_keys=True),flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("verify","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--binary",default="drnas_yalsat/r193-driver")
    a.add_argument("--cms",default="cryptominisat5")
    a.add_argument("--yals",default="drnas_yalsat/yalsat")
    ns=a.parse_args()
    if ns.action=="verify":print("DRNAS_YALSAT_SOURCE_PASS",len(cases()),flush=True)
    elif ns.action=="shard":shard(ns.shard,ns.binary,ns.cms,ns.yals)
    else:audit()
