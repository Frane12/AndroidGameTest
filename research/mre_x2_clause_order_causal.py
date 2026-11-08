#!/usr/bin/env python3
"""MRE X2 — exact-clause-order causal intervention, DEVELOPMENT replay only.

Seven orderings, same original clause multiset, same native C++/CMS backend,
same solver seed per paired (original SHA, rep), and equal 12s end-to-end cap.
No formulas are claimed to be new or blind. SAT witnesses checked against
the ORIGINAL source CNF; UNSAT agrees only with prior reference, no LRAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import pathlib
import random
import subprocess
import sys
import tempfile
import time

import mre_x_benchmark as base

OUT=pathlib.Path("mre_x2")
PROTO="DRNAS-MRE-X2-13SHA-7ORDERS-4SEED-12S-CAUSAL-DEV-v1"
MODES=("original","duplicate_tail","duplicate_front","duplicate_middle",
       "duplicate_spread","duplicate_random","reverse_unique_tail")
SHARDS=4
REPS=4
CAP=12.0
SOURCE_COUNT=13
TOTAL=SOURCE_COUNT*REPS*len(MODES)

def need(ok,msg):
    if not ok: raise RuntimeError("MRE_X2_FAIL_CLOSED "+str(msg))

def sha(b): return hashlib.sha256(b).hexdigest()

def save(path,obj):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def parse(path):
    path=pathlib.Path(path)
    nv=decl=None
    clauses=[]
    cur=[]
    for line in path.read_text().splitlines():
        t=line.strip()
        if not t or t[0] in "c%": continue
        if t.startswith("p "):
            parts=t.split()
            need(len(parts)==4 and parts[1]=="cnf" and nv is None,"invalid header")
            nv=int(parts[2]);decl=int(parts[3])
            need(0<nv<=1000000 and 0<decl<=5000000,"invalid DIMACS dimensions")
            continue
        need(nv is not None,"no header")
        for tok in t.split():
            l=int(tok)
            if l==0:
                clauses.append(tuple(cur));cur=[]
            else:
                need(0<abs(l)<=nv,"bad literal")
                cur.append(l)
    need(nv is not None and not cur and len(clauses)==decl,"DIMACS incomplete")
    return nv,clauses

def write(path,nv,clauses):
    path=pathlib.Path(path)
    with path.open("w") as f:
        f.write("p cnf %d %d\n"%(nv,len(clauses)))
        for clause in clauses:
            f.write(" ".join(map(str,clause))+" 0\n")

def split_duplicates(clauses):
    seen=set();unique=[];duplicate=[]
    for c in clauses:
        key=tuple(sorted(set(c)))
        if key in seen:duplicate.append(c)
        else:seen.add(key);unique.append(c)
    return unique,duplicate

def permutation(clauses,mode,source_sha):
    need(mode in MODES,"unknown ordering")
    if mode=="original":return list(clauses)
    uniq,dup=split_duplicates(clauses)
    if mode=="duplicate_tail":result=uniq+dup
    elif mode=="duplicate_front":result=dup+uniq
    elif mode=="duplicate_middle":
        m=len(uniq)//2;result=uniq[:m]+dup+uniq[m:]
    elif mode in ("duplicate_spread","duplicate_random"):
        if mode=="duplicate_spread":
            gaps=[((i+1)*(len(uniq)+1))//(len(dup)+1) for i in range(len(dup))]
        else:
            rng=random.Random(int(sha((PROTO+"|GAPS|"+source_sha).encode())[:16],16))
            gaps=sorted(rng.randrange(len(uniq)+1) for _ in dup)
        buckets=[[] for _ in range(len(uniq)+1)]
        for g,c in zip(gaps,dup):buckets[g].append(c)
        result=[]
        for i in range(len(uniq)+1):
            result.extend(buckets[i])
            if i<len(uniq):result.append(uniq[i])
    elif mode=="reverse_unique_tail":result=list(reversed(uniq))+dup
    else:raise AssertionError(mode)
    need(collections.Counter(result)==collections.Counter(clauses),
         "exact raw original clause MULTISET changed")
    if mode!="reverse_unique_tail":
        u2,_=split_duplicates(result)
        # In the front arm duplicate instances are canonically indistinguishable;
        # 'first occurrence' after reordering is an exact duplicate, so the
        # first-occurrence distinct-clause sequence is unchanged.
        need(u2==uniq,"relative first-unique clause order changed")
    return result

def cases():return base.cases()

def variant_path(c,mode):
    return OUT/(c["gbd"]+"."+mode+".cnf")

def selftest(emit_binary):
    need(REPS==4 and CAP==12.0 and len(MODES)==7,"protocol drift")
    tests=[
        (4,[(1,-2),(1,-2),(-1,2),(1,3),(1,3),(4,)]),
        (3,[(1,),(-1,),(1,),(-2,3),(-2,3)]),
        (4,[(1,2),(-1,3),(2,3),(1,2),(4,-4)]),
    ]
    with tempfile.TemporaryDirectory(prefix="mre-x2-selftest-") as tmp:
        td=pathlib.Path(tmp)
        for i,(nv,clauses) in enumerate(tests):
            src=td/("source-%d.cnf"%i)
            write(src,nv,clauses)
            original_sat=base.brute(src)
            for m in MODES:
                transformed=permutation(clauses,m,sha(src.read_bytes()))
                dest=td/("source-%d-%s.cnf"%(i,m))
                write(dest,nv,transformed)
                need(base.brute(dest)==original_sat,"SAT truth changed: "+m)
                need(collections.Counter(transformed)==collections.Counter(clauses),
                     "source multiplicity drift in selftest")
                if m=="duplicate_tail":
                    emitted=td/("source-%d-cpp-tail.cnf"%i)
                    g=base.emit(emit_binary,src,"x_tail",emitted)
                    need(parse(emitted)==parse(dest),"tail diverges from certified MRE X C++")
                    need(g["clauses_removed"]==0 and g["duplicate_clauses_removed"]==0,
                         "C++ tail changed clause count")
    print("MRE_X2_SELFTEST_PASS 3 7 exact-multiset C++-tail-parity",flush=True)

def freeze(emit_binary):
    OUT.mkdir(exist_ok=True)
    cs=cases();need(len(cs)==SOURCE_COUNT,"old source manifest no longer 13")
    rows=[]
    with tempfile.TemporaryDirectory(prefix="mre-x2-tail-") as tmp:
        tail_path=pathlib.Path(tmp)/"cpp-tail.cnf"
        for c in cs:
            source=base.ROOT/c["filename"]
            nv,original=parse(source)
            row=dict(gbd=c["gbd"],original_sha256=c["sha256"],
                     family=c["family"],reference_status=c["reference_status"],
                     duplicates=len(split_duplicates(original)[1]),variables=nv,
                     clauses=len(original),modes={})
            for m in MODES:
                dst=variant_path(c,m)
                order=permutation(original,m,c["sha256"])
                write(dst,nv,order)
                need(collections.Counter(order)==collections.Counter(original),
                     "loss or addition of exact clause")
                row["modes"][m]=sha(dst.read_bytes())
                if m=="duplicate_tail":
                    gate=base.emit(emit_binary,source,"x_tail",tail_path)
                    need(parse(tail_path)==parse(dst),"x_tail byte-token parity failed")
                    need(gate["duplicate_clauses_moved"]==row["duplicates"],
                         "C++ duplicate count disagreement")
            rows.append(row)
            print("MRE_X2_SOURCE",json.dumps({k:v for k,v in row.items() if k!="modes"},
                  sort_keys=True),flush=True)
    save(OUT/"manifest.json",dict(protocol=PROTO,source_count=SOURCE_COUNT,
         expected_trials=TOTAL,cap_s=CAP,seed_count=REPS,modes=list(MODES),
         source="MRE X old 13 SHA DEVELOPMENT cohort, not blind or new",
         comparison="exact raw clause multiset; only order changes",
         native="frozen MRE X x_native unchanged for every permutation",
         independent_unsat_lrat=False,no_auto_promotion=True,cases=rows))
    print("MRE_X2_FREEZE_PASS",len(rows),"modes",len(MODES),flush=True)

def verify():
    cs=cases();data=json.loads((OUT/"manifest.json").read_text())
    need(data["protocol"]==PROTO and data["source_count"]==SOURCE_COUNT and
         data["expected_trials"]==TOTAL and data["modes"]==list(MODES),
         "freeze manifest drift")
    old={c["sha256"]:c for c in cs}
    need(len(data["cases"])==SOURCE_COUNT,"missing frozen source")
    for row in data["cases"]:
        c=old.get(row["original_sha256"])
        need(c is not None and c["gbd"]==row["gbd"],"wrong source SHA")
        n,clauses=parse(base.ROOT/c["filename"])
        for m in MODES:
            p=variant_path(c,m)
            need(sha(p.read_bytes())==row["modes"][m],"order file SHA changed")
            a,b=parse(p)
            need(a==n and collections.Counter(b)==collections.Counter(clauses),
                 "original CNF exact multiset difference")
            need(b==permutation(clauses,m,c["sha256"]),"ordering deterministic drift")
    print("MRE_X2_VERIFY_PASS",len(cs),len(MODES),flush=True)

def trial(c,rep,mode,binary):
    need(rep in range(REPS) and mode in MODES,"unfrozen trial")
    src=base.ROOT/c["filename"]
    transformed=variant_path(c,mode)
    seed=base.seed(c,rep)
    start=time.perf_counter()
    p=None
    try:
        p=subprocess.run([str(pathlib.Path(binary).resolve()),str(transformed.resolve()),
                          "x_native",str(seed)],capture_output=True,text=True,
                         errors="replace",check=False,timeout=CAP)
    except subprocess.TimeoutExpired: pass
    wall=time.perf_counter()-start
    status="TIMEOUT";stats=None;gate=None;verified=False
    if p is not None:
        need(p.returncode==0,"native crashed "+mode+" "+p.stderr[-750:])
        gate=base.parse_gate(p.stdout,"x_native")
        need(not gate["applied"] and gate["clauses_removed"]==0,
             "native performed a non-order transformation")
        status,model,stats=base.cms.parsed_native(p.stdout)
        need(status in ("SAT","UNSAT","UNKNOWN","BUDGET"),"unexpected verdict")
        if status=="SAT":
            base.cms.verify_model(src,model)
            verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference_status"],
                 "verdict differs from independent original reference")
    if status not in ("SAT","UNSAT") or wall>CAP:
        status="TIMEOUT";verified=False
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],family=c["family"],
      reference_status=c["reference_status"],mode=mode,rep=rep,seed=seed,
      elapsed_s=round(wall,6),PAR2_s=round(wall if status in ("SAT","UNSAT")
      else 2*CAP,6),status=status,SAT_original_witness_verified=verified,
      UNSAT_prior_reference_no_LRAT=(status=="UNSAT"),gate=gate,native=stats)

def shard(idx,binary):
    need(idx in range(SHARDS),"wrong shard")
    cc=[c for i,c in enumerate(cases()) if i%SHARDS==idx]
    rows=[]
    for c in cc:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(sha((PROTO+"|SCHEDULE|"+c["sha256"]+
                        "|"+str(rep)).encode())[:16],16)).shuffle(order)
            for mode in order:
                r=trial(c,rep,mode,binary)
                rows.append(r)
                save(OUT/("shard-%d.json"%idx),rows)
                print("MRE_X2_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(cc)*REPS*len(MODES),"missing shard trials")
    print("MRE_X2_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cs=cases();source={x["sha256"]:x for x in cs}
    trials=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i)
        need(p.exists(),"missing shard")
        trials.extend(json.loads(p.read_text()))
    need(len(trials)==TOTAL,"not all 364 trials")
    seen=set();score={}
    for r in trials:
        c=source.get(r["sha256"])
        need(c is not None and r["gbd"]==c["gbd"] and r["protocol"]==PROTO,
             "source mismatch")
        need(r["mode"] in MODES and r["rep"] in range(REPS) and
             r["seed"]==base.seed(c,r["rep"]),"seed not paired")
        need(r["reference_status"]==c["reference_status"] and
             r["status"] in ("SAT","UNSAT","TIMEOUT"),"verdict mismatch")
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],"SAT original witness not verified")
        if r["status"]=="UNSAT":
            need(r["UNSAT_prior_reference_no_LRAT"],"UNSAT missing reference")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==2*CAP,"bad timeout penalty")
        key=(r["sha256"],r["rep"],r["mode"])
        need(key not in seen,"duplicate paired trial")
        seen.add(key)
    need(len(seen)==TOTAL,"not 364 unique paired trials")
    per_source=[]
    for c in cs:
        rows=[r for r in trials if r["sha256"]==c["sha256"]]
        per_source.append(dict(sha256=c["sha256"],gbd=c["gbd"],
            family=c["family"],status=c["reference_status"],
            PAR2_s={m:round(sum(r["PAR2_s"] for r in rows if r["mode"]==m),6)
                    for m in MODES},
            solved={m:sum(r["status"] in ("SAT","UNSAT") for r in rows
                          if r["mode"]==m) for m in MODES}))
    for m in MODES:
        rows=[r for r in trials if r["mode"]==m]
        score[m]=dict(n=len(rows),solved=sum(r["status"]!="TIMEOUT" for r in rows),
          SAT=sum(r["status"]=="SAT" for r in rows),
          UNSAT_prior_reference_no_LRAT=sum(r["status"]=="UNSAT" for r in rows),
          timeouts=sum(r["status"]=="TIMEOUT" for r in rows),
          PAR2_s=round(sum(r["PAR2_s"] for r in rows),6))
    for v in score.values():
        v["speedup_vs_original_x"]=round(score["original"]["PAR2_s"]/v["PAR2_s"],6)
    out=dict(protocol=PROTO,source_count=SOURCE_COUNT,cap_s=CAP,
       total_trials=TOTAL,seed_count=REPS,source_disposition="development NOT blind",
       same_frozen_native_binary_all_arms=True,exact_raw_clause_multisets=True,
       SAT_original_model_verified=True,UNSAT_prior_reference_no_LRAT=True,
       no_auto_promotion=True,score=score,per_source=per_source)
    save(OUT/"report.json",out)
    print("MRE_X2_FINAL",json.dumps({k:v for k,v in out.items()
         if k!="per_source"},sort_keys=True),flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=["selftest","freeze","verify","shard","audit"])
    a.add_argument("--emit",default="mre_x/bin/emit")
    a.add_argument("--native",default="mre_x/bin/native")
    a.add_argument("--shard",type=int,default=0)
    args=a.parse_args()
    if args.action=="selftest":selftest(args.emit)
    elif args.action=="freeze":freeze(args.emit)
    elif args.action=="verify":verify()
    elif args.action=="shard":shard(args.shard,args.native)
    else:audit()
