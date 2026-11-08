#!/usr/bin/env python3
"""DRNAS C5: early bounded CDCL dynamics on EXACT frozen C2/C4 native binaries.

Each (source, seed, mode, conflict budget) is a NEW fresh solver process.
Budgets (100,1000,5000) are NOT incremental checkpoints from one uninterrupted
run and NOT comparable to wall time of an end-to-end SAT proof.
Predeclared C4 development cases: 4 positive-duplicate original SHA, plus
2 no-duplicate source controls from the existing C3 development registry.
Read historical C4 full-solve outcomes ONLY at the final analysis stage.
Do not use this as a blind holdout or auto-promote a predictive gate.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import math
import os
import pathlib
import random
import re
import subprocess
import time

import c4_duplicate_order_causal as c4
import c3_dedup_sha12_validation as c3
import c2_cnf_clean_ablation as c2
import r195_native_cms_benchmark as cms

PROTO="DRNAS-C5-EARLY-CDCL-6SHA-3ARM-3SEED-100-1000-5000-CONFLICT-v1"
OUT=pathlib.Path("c5_out")
BUDGETS=(100,1000,5000)
MODES=("cpp_native","cpp_dedup","cpp_tail")
REPS=3
N_CASES=6
WALL_CAP_S=18.0
CONTROL_GBD=(
    "0d81711a3d73c828e8c6e12607eda82d",
    "17039a3ed02ea12653ec5389e56dab50",
)
CONTROL_SHA=(
    "6582502357d5960da9e8059fc1211e82d821944cae07d22ebef91509af7909ba",
    "ae9ec25d79e840a6794724857b894bf47e595a17c5893170f38526a41380f472",
)
RESULT_RE=re.compile(
    r"^R195_RESULT status=(SAT|UNSAT|BUDGET|UNKNOWN)"
    r" conflicts=(\d+) decisions=(\d+) propagations=(\d+)"
    r" source_rows=(\d+) derived_rows=(\d+)$",re.M
)

def need(b,msg):
    if not b:
        raise RuntimeError("C5_FAIL_CLOSED "+str(msg))

def source_cases():
    cc=c4.sources()
    need(len(cc)==4,"frozen C4 source cases changed")
    prior={x["gbd"]:x for x in c3.original_cases()}
    for gbd,sha in zip(CONTROL_GBD,CONTROL_SHA):
        c=prior.get(gbd)
        need(c is not None and c["sha256"]==sha,"control source GBD/SHA changed")
        p=c3.SRC/c["filename"]
        need(hashlib.sha256(p.read_bytes()).hexdigest()==sha,
             "original control CNF SHA changed")
        cc.append(dict(gbd=gbd,sha256=sha,path=p,control=True,
                       expected_status=c["reference_screen_status"]))
    for i,x in enumerate(cc):
        x["control"]=i>=4
        if i<4:x["expected_status"]="SAT"
    need(len(cc)==N_CASES and len({x["sha256"] for x in cc})==N_CASES,
         "non-distinct frozen source SHA")
    # Two additional zero-duplicate controls chosen BEFORE runtime signals.
    for x in cc[4:]:
        n,clauses=c2.read_clauses(x["path"])
        unique={tuple(sorted(set(c))) for c in clauses}
        need(len(unique)==len(clauses) and n>0,"control contains duplicate CNF clauses")
    return cc

def c5_seed(c,rep):
    # Exactly the original C4 seed function on all six source hashes.
    return c4.seed(c,rep)

def binary_for(mode):
    return "c4/bin/native" if mode=="cpp_tail" else "c2/bin/native"

def parse_result(stdout):
    matches=RESULT_RE.findall(stdout)
    need(len(matches)==1,"bounded native result or numeric counter missing")
    status,conf,dec,prop,source_rows,derived_rows=matches[0]
    counts=dict(conflicts=int(conf),decisions=int(dec),propagations=int(prop),
                source_rows=int(source_rows),derived_rows=int(derived_rows))
    need(counts["source_rows"]==0 and counts["derived_rows"]==0,
         "unexpected live XOR intervention")
    return status,counts

def one_probe(c,rep,mode,budget):
    need(mode in MODES and rep in range(REPS) and budget in BUDGETS,
         "arm / rep / window outside frozen protocol")
    src=c["path"]
    need(hashlib.sha256(src.read_bytes()).hexdigest()==c["sha256"],
         "CNF SHA changed just before bounded solve")
    env=os.environ.copy()
    env["DRNAS_MAX_CONFLICTS"]=str(budget)
    start=time.perf_counter()
    p=None
    try:
        p=subprocess.run(
            [str(pathlib.Path(binary_for(mode)).resolve()),
             str(src.resolve()),mode,str(c5_seed(c,rep))],
            capture_output=True,text=True,errors="replace",check=False,
            timeout=WALL_CAP_S,env=env
        )
    except subprocess.TimeoutExpired:
        pass
    wall=time.perf_counter()-start
    status="DIAGNOSTIC_TIMEOUT";stats=None;gate=None;verified=False
    if p is not None:
        need(p.returncode==0,
             "native bounded CDCL crashed: "+p.stderr[-900:])
        gate=c4.gate_native(p.stdout,mode)
        status,stats=parse_result(p.stdout)
        if status=="SAT":
            # Original SHA CNF witness, not rewritten CNF only.
            _,model,model_stats=cms.parsed_native(p.stdout)
            need(model_stats["conflicts"]==stats["conflicts"],
                 "bounded SAT witness stats drift")
            cms.verify_model(src,model)
            verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["expected_status"],
                 "bounded verdict contradicts original source")
        if status=="BUDGET":
            need(not verified,"bounded diagnostic wrongly treated as SAT")
        need(status!="UNKNOWN","unexplained native unknown outside conflict cap")
    if wall>WALL_CAP_S:
        status="DIAGNOSTIC_TIMEOUT"
        verified=False
        stats=None
        gate=None
    return dict(protocol=PROTO,gbd=c["gbd"],sha256=c["sha256"],
        source_type="no_duplicate_control" if c["control"] else "C4_positive_duplicate_development",
        expected_status=c["expected_status"],
        rep=rep,seed=c5_seed(c,rep),mode=mode,budget_conflicts=budget,
        bounded_status=status,full_end_to_end_SAT=False,
        original_SAT_witness_verified=verified,
        UNSAT_independent_LRAT=False,
        runtime_s=round(wall,6),wall_cap_s=WALL_CAP_S,
        native_stats=stats,gate=gate,
        build_sha=os.environ.get("GITHUB_SHA","LOCAL"))

def smoke():
    # A check of actual budgeted CMS behavior, no performance conclusion.
    cc=source_cases()
    c=cc[0]
    rows=[]
    for mode in MODES:
        x=one_probe(c,0,mode,100)
        need(x["bounded_status"]!="DIAGNOSTIC_TIMEOUT",
             "100-conflict bounded smoke failed")
        need(x["native_stats"] is not None and
             x["native_stats"]["conflicts"]>=1,
             "CMS get_last_conflicts unavailable in bounded mode")
        rows.append(dict(mode=mode,status=x["bounded_status"],
                         stats=x["native_stats"],gate=x["gate"]))
    print("C5_BOUNDED_100_CONFLICT_SMOKE_PASS",
          json.dumps(rows,sort_keys=True),flush=True)

def shard(i):
    cc=source_cases()
    need(i in range(N_CASES),"unsupported shard id")
    OUT.mkdir(exist_ok=True)
    c=cc[i]
    rows=[]
    for rep in range(REPS):
        combos=[(mode,b) for mode in MODES for b in BUDGETS]
        random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(combos)
        for mode,budget in combos:
            x=one_probe(c,rep,mode,budget)
            rows.append(x)
            (OUT/("shard-%d.json"%i)).write_text(
                json.dumps(rows,indent=2,sort_keys=True)+"\n"
            )
            print("C5_PROBE",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES)*len(BUDGETS),
         "incomplete bounded source shard")
    print("C5_SHARD_PASS",i,len(rows),flush=True)

def previous_c4():
    root=pathlib.Path("c5_prior_c4")
    files=list(root.rglob("shard-*.json"))
    need(len(files)==4,
         "missing four complete original C4 full-solve shard artifacts")
    rows=[]
    for f in files:
        x=json.loads(f.read_text())
        need(len(x)==9,"C4 full source shard incomplete")
        rows+=x
    source={c["sha256"]:c for c in source_cases()[:4]}
    keyed={}
    for x in rows:
        need(x["sha256"] in source,"C4 prior source SHA changed")
        need(x["protocol"]==c4.PROTO and
             x["seed"]==c5_seed(source[x["sha256"]],x["rep"]),
             "C4 prior full-end-to-end seed changed")
        need(x["mode"] in MODES and x["rep"] in range(REPS),
             "prior C4 mode/rep differs")
        key=(x["sha256"],x["rep"],x["mode"])
        need(key not in keyed,"duplicate C4 historical pair")
        need(x["status"] in ("SAT","TIMEOUT"),"C4 prior unexpected terminal")
        need(x["status"]!="SAT" or x["SAT_original_witness_verified"],
             "prior C4 SAT witness missing")
        need((x["status"]!="TIMEOUT") or x["par2_s"]==70,
             "prior C4 35-second PAR2 penalty mismatch")
        keyed[key]=x
    need(len(keyed)==4*REPS*len(MODES),
         "missing C4 full-end-to-end source x seed x arm outcomes")
    return keyed

def audit():
    cc=source_cases()
    by_sha={x["sha256"]:x for x in cc}
    rows=[]
    for i in range(N_CASES):
        f=OUT/("shard-%d.json"%i)
        need(f.is_file(),"source shard missing "+str(i))
        sl=json.loads(f.read_text())
        need(len(sl)==REPS*len(MODES)*len(BUDGETS),
             "incomplete source-window run")
        rows+=sl
    need(len(rows)==N_CASES*REPS*len(MODES)*len(BUDGETS),
         "missing pilot attempts")
    observed={}
    stats=collections.defaultdict(lambda:dict(n=0,budget=0,solved=0,timeout=0,
        decisions=0,propagations=0,conflicts=0,wall=0.0))
    early=collections.defaultdict(dict)
    for x in rows:
        c=by_sha.get(x["sha256"])
        need(c is not None and c["gbd"]==x["gbd"] and
             c5_seed(c,x["rep"])==x["seed"],
             "source / seed mismatch")
        need(x["protocol"]==PROTO and x["mode"] in MODES and
             x["budget_conflicts"] in BUDGETS and
             x["wall_cap_s"]==WALL_CAP_S,
             "unfrozen bounded protocol")
        key=(x["sha256"],x["rep"],x["mode"],x["budget_conflicts"])
        need(key not in observed,"duplicate source rep arm window")
        observed[key]=x
        status=x["bounded_status"]
        need(status in ("SAT","UNSAT","BUDGET","DIAGNOSTIC_TIMEOUT"),
             "unknown bounded terminal")
        if status=="DIAGNOSTIC_TIMEOUT":
            need(x["native_stats"] is None and x["gate"] is None,
                 "timeout fabricated native counters")
        else:
            need(x["native_stats"] is not None and x["gate"] is not None,
                 "missing native statistics on completed bounded probe")
            n=x["native_stats"]
            need(all(isinstance(n[k],int) and n[k]>=0 for k in
                     ("conflicts","decisions","propagations")),
                 "invalid native CDCL counters")
            if status=="BUDGET":
                need(not x["original_SAT_witness_verified"],
                     "budget not a verified SAT answer")
            if status=="SAT":
                need(x["original_SAT_witness_verified"] and c["expected_status"]=="SAT",
                     "invalid bounded SAT original witness")
            if status=="UNSAT":
                need(c["expected_status"]=="UNSAT",
                     "UNSAT contradicts frozen original")
            if x["mode"]=="cpp_native":
                need(not x["gate"]["applied"],"native source unexpectedly modified")
            if x["mode"]=="cpp_dedup":
                need(x["gate"]["variables_eliminated"]==0 and
                     x["gate"]["taut_clauses_removed"]==0 and
                     x["gate"]["duplicate_literals_removed"]==0,
                     "dedup altered another mechanism")
            if x["mode"]=="cpp_tail":
                need(x["gate"]["clauses_removed"]==0 and
                     x["gate"]["variables_eliminated"]==0,
                     "tail was not an exact clause permutation")
            if c["control"]:
                need(not x["gate"]["applied"],"no-duplicate control was changed")
            early[key]=dict(status=status,counts=n,wall_s=x["runtime_s"])
        d=stats[(x["mode"],x["budget_conflicts"])]
        d["n"]+=1
        d["budget"]+=status=="BUDGET"
        d["solved"]+=status in ("SAT","UNSAT")
        d["timeout"]+=status=="DIAGNOSTIC_TIMEOUT"
        d["wall"]+=x["runtime_s"]
        if x["native_stats"] is not None:
            d["conflicts"]+=x["native_stats"]["conflicts"]
            d["decisions"]+=x["native_stats"]["decisions"]
            d["propagations"]+=x["native_stats"]["propagations"]
    need(len(observed)==N_CASES*REPS*len(MODES)*len(BUDGETS),
         "source-window matrix incomplete")
    prior=previous_c4()
    joined=[]
    for sha in [x["sha256"] for x in cc[:4]]:
        for rep in range(REPS):
            full={mode:prior[(sha,rep,mode)] for mode in MODES}
            pilot={}
            for mode in MODES:
                pilot[mode]={}
                for budget in BUDGETS:
                    e=observed[(sha,rep,mode,budget)]
                    n=e["native_stats"] or {}
                    conf=n.get("conflicts")
                    pilot[mode][str(budget)]=dict(
                        status=e["bounded_status"],wall_s=e["runtime_s"],
                        conflicts=conf,decisions=n.get("decisions"),
                        propagations=n.get("propagations"),
                        decisions_per_conflict=(round(n["decisions"]/conf,6)
                                                if conf else None),
                        propagations_per_conflict=(round(n["propagations"]/conf,6)
                                                   if conf else None))
            joined.append(dict(sha256=sha,gbd=by_sha[sha]["gbd"],rep=rep,
                full_PAR2_s={mode:full[mode]["par2_s"] for mode in MODES},
                full_status={mode:full[mode]["status"] for mode in MODES},
                full_dedup_vs_native_speedup_x=round(
                    full["cpp_native"]["par2_s"]/full["cpp_dedup"]["par2_s"],6),
                bounded_pilot=pilot))
    need(len(joined)==4*REPS,"missing historical complete C4 matched full outcome")
    sumstats={}
    for (mode,budget),v in sorted(stats.items()):
        k=mode+"@"+str(budget)
        sumstats[k]=dict(n=v["n"],reached_conflict_budget=v["budget"],
            solved_before_budget=v["solved"],diagnostic_timeouts=v["timeout"],
            conflicts_total=v["conflicts"],decisions_total=v["decisions"],
            propagations_total=v["propagations"],probe_wall_s=round(v["wall"],6),
            decisions_per_conflict=(round(v["decisions"]/v["conflicts"],6)
                                    if v["conflicts"] else None),
            propagations_per_conflict=(round(v["propagations"]/v["conflicts"],6)
                                       if v["conflicts"] else None))
    result=dict(protocol=PROTO,source_cohort="4 C4 development positives + 2 C3 pre-screened no-duplicate controls",
        no_blind_holdout=True,results_are_bounded_diagnostics_not_full_SAT=True,
        each_budget_starts_fresh_solver=True,source_count=N_CASES,
        paired_source_seed_arms=N_CASES*REPS*len(MODES),
        diagnostic_trials=len(rows),budgets_conflicts=list(BUDGETS),
        modes=list(MODES),reps=REPS,window_time_cap_s=WALL_CAP_S,
        original_SHA=[x["sha256"] for x in cc],
        linked_C4_full_outcome_run=42519684428,
        independent_UNSAT_LRAT=False,
        no_auto_promotion=True,
        by_mode_budget=sumstats,
        matched_C4_full_and_early=joined)
    (OUT/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("C5_FINAL",json.dumps({k:v for k,v in result.items()
          if k!="matched_C4_full_and_early"},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="verify":
        print("C5_SOURCE_SHA6_VERIFIED",len(source_cases()),flush=True)
    elif args.action=="smoke":
        smoke()
    elif args.action=="shard":
        shard(args.shard)
    else:
        audit()
