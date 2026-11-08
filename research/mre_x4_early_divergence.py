#!/usr/bin/env python3
"""DRNAS MRE X4 — source-exact, SHA-paired CDCL early divergence localization.

No modification of CMS branching/BCP or reference SAT source; only cumulative
10..10000 conflict caps, original SAT witness replay, and clause order variants.
Counters do NOT expose watched-literal events, learnt-clause LBD, restarts, or
full trail. Do not infer those events directly from aggregate counters.
All four source SHAs are KNOWN development formulas, NOT blind holdout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import tempfile
import time
import statistics
import mre_x_benchmark as base
import mre_x2_clause_order_causal as x2
import mre_x3_spread_mechanism as x3

PROTO="DRNAS-MRE-X4-4SHA-5ORDERS-4SEED-10CHECKPOINTS-12SPAR2-v1"
OUT=pathlib.Path("mre_x4")
CASES=(x3.TARGETS[0],x3.TARGETS[1],x3.TARGETS[2],x3.TARGETS[4])
MODES=("original","spread100","spread_reverse_copies","spread_shifted","front100")
BUDGETS=(10,25,50,100,250,500,1000,2000,5000,10000)
REPS=4
SHARDS=4
CAP=12.0
REAL_TRIALS=len(CASES)*REPS*len(MODES)
BOUNDED_TRIALS=REAL_TRIALS*len(BUDGETS)
TRAIL_EVENTS_AVAILABLE=False
LBD_AVAILABLE=False
WATCH_EVENTS_AVAILABLE=False
RESTART_EVENTS_AVAILABLE=False

def need(v,why):
    if not v:raise RuntimeError("MRE_X4_FAIL_CLOSED "+why)

def sha(v):return hashlib.sha256(v).hexdigest()
def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def sources():
    data={c["sha256"]:c for c in x3.source_cases()}
    need(all(s in data for s in CASES),"original X3 sources disappeared")
    return [data[s] for s in CASES]

def path(case,mode):return OUT/(case["gbd"]+"."+mode+".cnf")

def interleave(unique,duplicates,gaps):
    need(len(gaps)==len(duplicates),"gap cardinality mismatch")
    buckets=[[] for _ in range(len(unique)+1)]
    for i,(clause,gap) in enumerate(zip(duplicates,gaps)):
        need(0<=gap<=len(unique),"gap index out of bounds")
        buckets[gap].append(clause)
    out=[]
    for gap in range(len(unique)+1):
        out.extend(buckets[gap])
        if gap<len(unique):out.append(unique[gap])
    return out

def transform(clauses,mode):
    need(mode in MODES,"unknown clause order")
    if mode in ("original","spread100","front100"):
        return x3.transform(clauses,mode)[0]
    duplicate_positions=set(x3.duplicates(clauses))
    if not duplicate_positions:return list(clauses)
    unique=[c for i,c in enumerate(clauses) if i not in duplicate_positions]
    duplicate=[c for i,c in enumerate(clauses) if i in duplicate_positions]
    gaps=[((i+1)*(len(unique)+1))//(len(duplicate)+1)
          for i in range(len(duplicate))]
    if mode=="spread_reverse_copies":
        return interleave(unique,list(reversed(duplicate)),gaps)
    need(mode=="spread_shifted","unknown experimental interleave")
    offset=max(1,len(unique)//(2*(len(duplicate)+1)))
    shifted=[min(len(unique),p+offset) for p in gaps]
    return interleave(unique,duplicate,shifted)

def selftest():
    tiny=[(4,[(1,-2),(1,-2),(-1,2),(1,3),(1,3),(4,)]),
          (3,[(1,),(-1,),(1,),(-2,3),(-2,3)]),
          (5,[(1,2),(3,4),(1,2),(2,5),(1,2),(3,4),(-5,)])]
    with tempfile.TemporaryDirectory() as tmp:
        td=pathlib.Path(tmp)
        for i,(nv,cs) in enumerate(tiny):
            original=td/("original-%d.cnf"%i);x2.write(original,nv,cs)
            truth=base.brute(original)
            for mode in MODES:
                changed=transform(cs,mode)
                dest=td/(str(i)+"-"+mode+".cnf")
                x2.write(dest,nv,changed)
                need(collections.Counter(cs)==collections.Counter(changed),
                     "raw clause MULTISET changed in "+mode)
                need(base.brute(dest)==truth,"Boolean truth changed in "+mode)
                if mode=="spread100":
                    need(changed==x3.transform(cs,"spread100")[0],
                         "X3 exact spread100 parity absent")
    print("MRE_X4_SELFTEST_PASS 3 5",flush=True)

def freeze():
    OUT.mkdir(exist_ok=True);rows=[]
    for c in sources():
        src=x3.source(c)
        need(sha(src.read_bytes())==c["sha256"],"original source SHA drift")
        nv,original=x2.parse(src)
        variants={}
        for mode in MODES:
            changed=transform(original,mode)
            need(collections.Counter(original)==collections.Counter(changed),
                 "original exact raw clause multiset violated")
            dest=path(c,mode)
            x2.write(dest,nv,changed)
            variants[mode]=sha(dest.read_bytes())
            if mode in ("original","spread100","front100"):
                need(x2.parse(dest)==x2.parse(x3.path(c,mode)),
                     "MRE X3 frozen original/spread/front mismatch")
        duplicate_count=len(x3.duplicates(original))
        rows.append(dict(gbd=c["gbd"],sha256=c["sha256"],status=c["reference_status"],
          variables=nv,clauses=len(original),duplicates=duplicate_count,variants=variants))
        print("MRE_X4_SOURCE",json.dumps({k:v for k,v in rows[-1].items() if k!="variants"},
              sort_keys=True),flush=True)
    need([r["duplicates"]>0 for r in rows]==[True,True,True,False],
         "not three duplication positives and one clean control")
    save(OUT/"manifest.json",dict(protocol=PROTO,source_count=4,seeds=REPS,
         modes=list(MODES),budgets=list(BUDGETS),real_trials=REAL_TRIALS,
         bounded_trials=BOUNDED_TRIALS,cap_s=CAP,known_development_not_blind=True,
         original_clause_multiset_exact=True,backend="CMS 5.11 frozen X3 native, checkpoint guard extended",
         measured=["conflicts","decisions","propagations","init_s","add_s","solve_s"],
         unavailable=["watch-events","trail","learnt LBD","restarts"],
         UNSAT_independent_LRAT=False,no_auto_promotion=True,cases=rows))
    print("MRE_X4_FREEZE_PASS 4 5",flush=True)

def verify():
    info=json.loads((OUT/"manifest.json").read_text())
    need(info["protocol"]==PROTO and info["source_count"]==4 and
         info["real_trials"]==REAL_TRIALS and
         info["bounded_trials"]==BOUNDED_TRIALS and
         info["budgets"]==list(BUDGETS),"manifest protocol changed")
    records={x["sha256"]:x for x in info["cases"]}
    need(len(records)==4,"not four frozen originals")
    for c in sources():
        row=records[c["sha256"]]
        src=x3.source(c);need(sha(src.read_bytes())==c["sha256"],"SHA source changed")
        nv,clauses=x2.parse(src)
        for mode in MODES:
            p=path(c,mode)
            need(sha(p.read_bytes())==row["variants"][mode],"variant SHA drift")
            n,got=x2.parse(p)
            need(n==nv and got==transform(clauses,mode) and
                 collections.Counter(got)==collections.Counter(clauses),
                 "not exact original permutation")
    print("MRE_X4_VERIFY_PASS 4 5",flush=True)

MARKER=re.compile(r"^R195_RESULT status=(SAT|UNSAT|BUDGET|UNKNOWN) conflicts=(\d+) decisions=(\d+) propagations=(\d+) source_rows=(\d+) derived_rows=(\d+)$",re.M)

def run(c,rep,mode,binary,budget=None):
    need(rep in range(REPS) and mode in MODES,"unknown source/seed/arm")
    src=x3.source(c);trial=path(c,mode)
    seed=base.seed(c,rep)
    env=os.environ.copy()
    env.pop("DRNAS_MAX_CONFLICTS",None)
    if budget is not None:
        need(budget in BUDGETS,"not a frozen bounded checkpoint")
        env["DRNAS_MAX_CONFLICTS"]=str(budget)
    started=time.perf_counter()
    p=None
    try:
        p=subprocess.run([str(pathlib.Path(binary).resolve()),
          str(trial.resolve()),"x_native",str(seed)],env=env,
          capture_output=True,text=True,errors="replace",timeout=(CAP if budget is None else 20),
          check=False)
    except subprocess.TimeoutExpired:
        need(budget is None,"a bounded diagnostic exceeded 20s")
    wall=time.perf_counter()-started
    status="TIMEOUT";stats=None;stages=None;witness=False
    if p is not None:
        need(p.returncode==0,"native crash "+mode+" stderr="+p.stderr[-600:])
        gate=base.parse_gate(p.stdout,"x_native")
        need(not gate["applied"] and gate["clauses_removed"]==0,"native altered original")
        steps=[s.split(" ",1)[1] for s in p.stdout.splitlines()
               if s.startswith("MRE_X3_STAGE ")]
        need(len(steps)==1,"missing stage telemetry")
        stages=json.loads(steps[0])
        need(stages["working_clauses"]==x2.parse(src)[1].__len__() and
             stages["clauses_loaded"]<=stages["working_clauses"],
             "incorrect number of clauses loaded")
        match=MARKER.search(p.stdout)
        need(match is not None,"missing native conflict/propagation statistics")
        status=match.group(1)
        stats=dict(conflicts=int(match.group(2)),decisions=int(match.group(3)),
                   propagations=int(match.group(4)))
        if status=="SAT":
            v,model,_=base.cms.parsed_native(p.stdout)
            need(v=="SAT","wrong model parser status")
            base.cms.verify_model(src,model)
            witness=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference_status"],"original source reference disagrees")
    if budget is None and (status not in ("SAT","UNSAT") or wall>CAP):
        status="TIMEOUT";witness=False
    if budget is not None:
        need(status in ("SAT","UNSAT","BUDGET"),"invalid bounded CDCL state")
    row=dict(protocol=PROTO,gbd=c["gbd"],sha256=c["sha256"],rep=rep,
       seed=seed,mode=mode,budget=budget,status=status,
       wall_s=round(wall,6),native_stats=stats,stages=stages,
       original_SAT_witness_verified=witness,
       UNSAT_reference_agreement_no_independent_LRAT=(status=="UNSAT"),
       bounded_not_PAR2=(budget is not None))
    if budget is None:
        row["PAR2_s"]=round(wall if status in ("SAT","UNSAT") else CAP*2,6)
    return row

def shard(idx,binary):
    need(idx in range(SHARDS),"invalid shard")
    c=sources()[idx]
    bounded=[];real=[];repeat=[]
    for rep in range(REPS):
        modes=list(MODES)
        random.Random(int(sha((PROTO+"|ORDER|"+c["sha256"]+"|"+str(rep)).encode())[:16],16)).shuffle(modes)
        for mode in modes:
            r=run(c,rep,mode,binary)
            real.append(r)
            save(OUT/("real-%d.json"%idx),real)
            print("MRE_X4_REAL",json.dumps(r,sort_keys=True),flush=True)
        for cap in BUDGETS:
            order=list(MODES)
            random.Random(int(sha((PROTO+"|CAPORDER|"+c["sha256"]+"|"+str(rep)+"|"+str(cap)).encode())[:16],16)).shuffle(order)
            for mode in order:
                r=run(c,rep,mode,binary,budget=cap)
                bounded.append(r)
                save(OUT/("bounded-%d.json"%idx),bounded)
                print("MRE_X4_BOUNDED",json.dumps(r,sort_keys=True),flush=True)
        if idx==0 and rep==0:
            for cap in (100,1000,5000):
                for mode in ("original","spread100"):
                    a=next(x for x in bounded if x["rep"]==rep and x["mode"]==mode and x["budget"]==cap)
                    b=run(c,rep,mode,binary,budget=cap)
                    stable=(a["status"]==b["status"] and a["native_stats"]==b["native_stats"])
                    repeat.append(dict(cap=cap,mode=mode,repeated_aggregate_stats_equal=stable))
    need(len(real)==REPS*len(MODES),"incomplete 20 real trials")
    need(len(bounded)==REPS*len(MODES)*len(BUDGETS),
         "incomplete 200 bounded checkpoints")
    save(OUT/("repeat-%d.json"%idx),repeat)
    print("MRE_X4_SHARD_PASS",idx,len(real),len(bounded),flush=True)

def audit():
    cs=sources();bysha={c["sha256"]:c for c in cs}
    real=[];bounded=[];repeats=[]
    for i in range(SHARDS):
        real+=json.loads((OUT/("real-%d.json"%i)).read_text())
        bounded+=json.loads((OUT/("bounded-%d.json"%i)).read_text())
        repeats+=json.loads((OUT/("repeat-%d.json"%i)).read_text())
    need(len(real)==REAL_TRIALS and len(bounded)==BOUNDED_TRIALS,
         "audit missing full pairing")
    for dataset,is_bounded in ((real,False),(bounded,True)):
        seen=set()
        for r in dataset:
            c=bysha.get(r["sha256"])
            need(c and c["gbd"]==r["gbd"] and
                 r["seed"]==base.seed(c,r["rep"]) and r["mode"] in MODES and
                 r["protocol"]==PROTO,"source/seed/mode drift")
            key=(r["sha256"],r["rep"],r["mode"],r["budget"])
            need(key not in seen,"duplicated trial")
            seen.add(key)
            need(r["bounded_not_PAR2"]==is_bounded,"mixed bounded with end-to-end")
            if is_bounded:
                need(r["budget"] in BUDGETS and r["status"] in ("SAT","UNSAT","BUDGET"),
                     "bounded invalid")
            else:
                need(r["budget"] is None and r["status"] in ("SAT","UNSAT","TIMEOUT"),
                     "real SAT invalid")
                if r["status"]=="TIMEOUT":
                    need(r["PAR2_s"]==CAP*2,"invalid 12s PAR2 penalty")
            if r["status"]=="SAT":
                need(r["original_SAT_witness_verified"],"no source SAT replay")
            if r["status"]=="UNSAT":
                need(r["UNSAT_reference_agreement_no_independent_LRAT"],
                     "no reference UNSAT agreement")
        need(len(seen)==(BOUNDED_TRIALS if is_bounded else REAL_TRIALS),
             "not every required paired run")
    score={}
    for mode in MODES:
        a=[x for x in real if x["mode"]==mode]
        score[mode]=dict(n=len(a),solved=sum(x["status"]!="TIMEOUT" for x in a),
          timeouts=sum(x["status"]=="TIMEOUT" for x in a),
          PAR2_s=round(sum(x["PAR2_s"] for x in a),6))
    baseline=score["original"]["PAR2_s"]
    for m in MODES:
        score[m]["speedup_vs_original"]=round(baseline/score[m]["PAR2_s"],6)
    per_source=[]
    for c in cs:
        subset=[r for r in real if r["sha256"]==c["sha256"]]
        per_source.append(dict(gbd=c["gbd"],sha256=c["sha256"],
          reference_status=c["reference_status"],
          PAR2_s={m:round(sum(r["PAR2_s"] for r in subset if r["mode"]==m),6)
              for m in MODES},solved={m:sum(r["status"]!="TIMEOUT" for r in subset
              if r["mode"]==m) for m in MODES}))
    divergences=[]
    for c in cs:
        for rep in range(REPS):
            a=[r for r in bounded if r["sha256"]==c["sha256"] and r["rep"]==rep]
            for mode in MODES:
                if mode=="original":continue
                first=None;kind=None
                for budget in BUDGETS:
                    ref=next(r for r in a if r["mode"]=="original" and r["budget"]==budget)
                    exp=next(r for r in a if r["mode"]==mode and r["budget"]==budget)
                    fields=("status","conflicts","decisions","propagations")
                    rkeys=(ref["status"],)+tuple(ref["native_stats"][k] for k in fields[1:])
                    ekeys=(exp["status"],)+tuple(exp["native_stats"][k] for k in fields[1:])
                    if rkeys!=ekeys:
                        first=budget
                        kind=[k for k,rv,ev in zip(fields,rkeys,ekeys) if rv!=ev]
                        break
                divergences.append(dict(gbd=c["gbd"],rep=rep,mode=mode,
                  first_aggregate_divergence_cap=first,
                  differing_metrics_at_first_cap=kind))
    result=dict(protocol=PROTO,source_count=len(cs),seed_count=REPS,
      real_trials=len(real),bounded_diagnostics=len(bounded),cap_s=CAP,
      budgets=list(BUDGETS),development_not_blind=True,no_auto_promotion=True,
      independent_UNSAT_LRAT=False,original_SAT_witness_checked=True,
      same_backend_and_original_multiset=True,
      watch_trail_LBD_restart_trace_available=False,
      observed_metrics_only=["conflicts","decisions","propagations","stages"],
      score=score,per_source=per_source,divergences=divergences,repeats=repeats)
    save(OUT/"report.json",result)
    print("MRE_X4_FINAL",json.dumps({k:v for k,v in result.items()
        if k not in ("per_source","divergences")},sort_keys=True),flush=True)
    print("MRE_X4_DIVERGENCE",json.dumps(divergences,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="mre_x4/bin/native")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":verify()
    elif a.action=="shard":shard(a.shard,a.native)
    else:audit()
