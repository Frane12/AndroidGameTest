#!/usr/bin/env python3
"""DRNAS MRE9: five-arm MRE6f reference vs in-process C++ equality gate.

Seven frozen SAT2026 originals (bounded 1k/5k conflicts) and six already-used
MRE7 easy SAT2024/25 originals (8s real solver verdict) with paired SHA, seed,
original-model verification. No promotion; bounded UNKNOWN is not SAT solved.
"""
from __future__ import annotations
import argparse
import collections
import json
import itertools
import os
import pathlib
import random
import re
import subprocess
import tempfile
import time

import mre8f_6f_reference_gate as old
import mre6d_paired as d
import mre6d_all_equalities as eq
import mre6b_blind_freeze as freeze
import mre6e_conflict_diagnostic as diagnostic
import mre1_cross_representation as mre1
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195

PROTO="DRNAS-MRE9-NATIVE-CPP-MRE6F-REFERENCE-5ARMS-20261108-v1"
ROOT=pathlib.Path("mre9")
MODES=("cms_native","mre6f_all","mre8f_gate","cpp_native","cpp_gate")
SHARDS={"bounded":4,"verdict":3}
REPS={"bounded":3,"verdict":2}
LIMITS={"bounded":(1000,5000),"verdict":(None,)}
CAP={"bounded":6.0,"verdict":8.0}
STAT=re.compile(r"^MRE9_GATE (\{.*\})$",re.M)

def need(ok,msg):
    if not ok:raise RuntimeError("MRE9_BENCH_FAIL_CLOSED "+str(msg))

def test_native(cpp):
    with tempfile.TemporaryDirectory(prefix="drnas-mre9-selftest-") as tmp:
        root=pathlib.Path(tmp)
        def score(cnf,assignment):
            return all(any(assignment[abs(l)] == (l>0) for l in c) for c in cnf)
        rng=random.Random(20261108)
        for sample in range(48):
            n=6
            original=[tuple(rng.choice((-1,1))*rng.randint(1,n)
                            for _ in range(rng.randrange(1,4))) for _ in range(10)]
            if sample%2==0: original.extend([(-1,2),(1,-2)])
            if sample%3==0: original.extend([(-2,3),(2,-3)])
            if sample%5==0: original.extend([(-4,5),(4,-5)])
            original.append((6,))
            src=root/"test.cnf"; out=root/"rewritten.cnf"
            mre1.write_cnf(src,n,original,[])
            p=subprocess.run([str(pathlib.Path(cpp).resolve()),"--emit",
                              str(src),"cpp_all",str(out)],
                             capture_output=True,text=True,check=True)
            line=STAT.search(p.stdout); need(line,"missing standalone C++ gate")
            stat=json.loads(line[1])
            reduced,_,mapping,_=eq.quotient(original)
            _,actual=exact.parse_dimacs(out)
            need(len(actual)==len(reduced),"C++ quotient clause count differs")
            def canon(seq):
                return {tuple(sorted(set(c))) for c in seq}
            need(canon(actual)==canon(reduced),"C++ quotient clauses disagree with MRE6f")
            need(stat["variables_eliminated"]==len(mapping),"C++ merge count differs")
            for bits in itertools.product((False,True),repeat=n):
                assignment=dict(enumerate(bits,1))
                lifted=eq.reconstruct(assignment,mapping)
                need(score(original,lifted)==score(actual,assignment),
                     "exhaustive original CNF equivalence violated")
        # 260-variable positive signal requires actual gate, small controls must abstain.
        for n,with_eq in [(260,True),(8,True),(260,False)]:
            clauses=[]
            for i in range(2,n+1):
                if with_eq:clauses.extend([(-1,i),(1,-i)])
                clauses.append((1,i))
            clauses.extend([(1,2)]*300)
            src=root/"large.cnf"; out=root/"gate.cnf"
            mre1.write_cnf(src,n,clauses,[])
            p=subprocess.run([str(pathlib.Path(cpp).resolve()),"--emit",
                              str(src),"cpp_gate",str(out)],
                             capture_output=True,text=True,check=True)
            cppstat=json.loads(STAT.search(p.stdout)[1])
            _,_,pystat=old.gate_prepare(src,root)
            need(bool(cppstat["applied"])==bool(pystat["applied"]),
                 "C++ vs frozen Python gate disagreement")
            if with_eq and n==260:
                need(cppstat["variables_eliminated"]==259 and
                     cppstat["clauses_removed"]>=256,
                     "large synthetic equivalence missed")
            else:need(not cppstat["applied"],"negative control wrongly activated")
    print("MRE9_STANDALONE_EXHAUSTIVE_SELFTEST_PASS 48 formulas x 64 models",flush=True)

def make_trial(case,source,rep,mode,dataset,limit,refbin,cppbin):
    need(mode in MODES and dataset in SHARDS,"invalid case")
    need(freeze.sha256(source.read_bytes())==case["sha256"],"SHA changed")
    if mode in ("cms_native","mre6f_all","mre8f_gate"):
        r=old.run_one(case,source,rep,mode,dataset,limit,refbin)
        # The same reference implementation used in the completed MRE8f audit.
        need(r["protocol"]==old.PROTO,"MRE8f reference has drifted")
        r["reference_protocol"]=r["protocol"]
        r["protocol"]=PROTO
        r["backend"]="MRE8F_PINNED_PYTHON_REFERENCE"
        r["native_gate_s"]=None
        r["native_parse_s"]=None
        return r
    start=time.perf_counter()
    env=os.environ.copy()
    env["DRNAS_TRACE_ENABLED"]="0"
    if limit is None:env.pop("DRNAS_MAX_CONFLICTS",None)
    else:env["DRNAS_MAX_CONFLICTS"]=str(limit)
    status="TIMEOUT";counters=None;checked=False;gate=None;proc_s=None
    remaining=CAP[dataset]-(time.perf_counter()-start)
    if remaining>0.05:
        t=time.perf_counter()
        try:
            p=subprocess.run(
                [str(pathlib.Path(cppbin).resolve()),
                 str(pathlib.Path(source).resolve()),mode,
                 str(d.seed_of(case["sha256"],rep))],
                text=True,capture_output=True,errors="replace",
                env=env,timeout=remaining,check=False)
        except subprocess.TimeoutExpired:
            p=None
        proc_s=time.perf_counter()-t
        if p is not None:
            need(p.returncode==0,"native C++ bridge failed "+p.stderr[-1200:])
            m=STAT.search(p.stdout)
            need(m,"native C++ certificate telemetry missing")
            gate=json.loads(m[1])
            status,counters,model=diagnostic.parse(p.stdout)
            need(bool(gate["applied"])==(mode=="cpp_gate" and
                    gate["reason"]=="APPLY_CERTIFIED_SOURCE_EQUIVALENCES"),
                 "C++ certificate gate contradiction")
            if status=="SAT":
                r195.verify_model(source,model)
                checked=True
            if status in ("SAT","UNSAT"):
                need(status==old.expected_status(case),"wrong original SAT verdict")
            if status=="BUDGET":
                need(limit is not None and counters["conflicts"]>0,
                     "unbounded UNKNOWN mistaken as completed verdict")
    wall=time.perf_counter()-start
    if wall>=CAP[dataset]:
        status="TIMEOUT";checked=False
    if status=="SAT":need(checked,"model not verified")
    return dict(protocol=PROTO,dataset=dataset,
                study_source_sha256=case["sha256"],official_gbd=case["gbd"],
                original_reference_status=old.expected_status(case),
                source_year=case.get("year",2026),
                mode=mode,rep=rep,seed=d.seed_of(case["sha256"],rep),
                conflict_cap=limit,status=status,
                total_wall_s=round(wall,6),
                preprocessing_s=0.0,
                cms_subprocess_wall_s=round(proc_s,6) if proc_s is not None else None,
                par2_s=round(wall if status in ("SAT","UNSAT")
                             else 2*CAP[dataset],6),
                counters=counters,
                gate=(gate if gate is not None else
                      dict(applied=False,reason="PREP_OR_RUN_TIMEOUT")),
                quotient_applied=bool(gate and gate["applied"]),
                native_gate_s=gate.get("native_gate_s") if gate else None,
                native_parse_s=gate.get("native_parse_s") if gate else None,
                sat_original_model_verified=checked,
                unsat_independent_LRAT=False,originally_sha_verified=True,
                same_CMS_source_commit=d.SOURCE_CMS_SHA,
                original_clauses=case["clauses"],original_vars=case["vars"],
                reference_MRE6f_run=42499854392,
                pilot_not_new_blind_holdout=True,
                backend="MRE9_IN_PROCESS_NATIVE_CPP")

def shard(dataset,idx,refbin,cppbin):
    need(0<=idx<SHARDS[dataset],"invalid shard")
    allcases=old.source_set(dataset)
    cases=[x for i,x in enumerate(allcases) if i%SHARDS[dataset]==idx]
    need(bool(cases),"empty shard")
    folder=ROOT/dataset;folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case,source in cases:
        for rep in range(REPS[dataset]):
            for lim in LIMITS[dataset]:
                order=list(MODES)
                random.Random(PROTO+case["sha256"]+str(rep)+str(lim)).shuffle(order)
                for mode in order:
                    row=make_trial(case,source,rep,mode,dataset,lim,refbin,cppbin)
                    rows.append(row)
                    (folder/("shard-%d.json"%idx)).write_text(
                        json.dumps(rows,sort_keys=True)+"\n")
                    print("MRE9_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cases)*REPS[dataset]*len(LIMITS[dataset])*len(MODES),
         "incomplete source shard")
    print("MRE9_SHARD_PASS",dataset,idx,len(rows),flush=True)

def audit(dataset):
    source=old.source_set(dataset)
    expected={c["sha256"]:c for c,p in source}
    rows=[];pairs=collections.defaultdict(dict)
    for idx in range(SHARDS[dataset]):
        f=ROOT/dataset/("shard-%d.json"%idx)
        need(f.exists(),"missing shard")
        rows+=json.loads(f.read_text())
    n=len(source)*REPS[dataset]*len(LIMITS[dataset])*len(MODES)
    need(len(rows)==n,"benchmark missing attempts")
    for r in rows:
        c=expected.get(r["study_source_sha256"])
        need(c and r["official_gbd"]==c["gbd"],"wrong frozen source")
        need(r["protocol"]==PROTO and r["dataset"]==dataset,"wrong protocol")
        need(r["rep"] in range(REPS[dataset]) and
             r["conflict_cap"] in LIMITS[dataset],"wrong repetition/cap")
        need(r["same_CMS_source_commit"]==d.SOURCE_CMS_SHA and
             r["originally_sha_verified"],"binary or SHA drift")
        if r["status"]=="SAT":
            need(r["sat_original_model_verified"],"unverified SAT model")
        if r["status"]=="UNSAT":
            need(old.expected_status(c)=="UNSAT","unverified UNSAT against reference")
        if r["status"]=="BUDGET":
            need(dataset=="bounded" and r["counters"] and
                 r["counters"]["conflicts"]>0,"BUDGET not a real CDCL count")
        key=(r["study_source_sha256"],r["rep"],r["conflict_cap"])
        need(r["mode"] not in pairs[key],"duplicate arm")
        pairs[key][r["mode"]]=r
    need(len(pairs)==len(source)*REPS[dataset]*len(LIMITS[dataset]),
         "missing a source or seed")
    for key,arms in pairs.items():
        need(set(arms)==set(MODES),"incomplete paired arm group")
        need(len({x["seed"] for x in arms.values()})==1,
             "paired seeds are unequal")
        need(arms["cpp_gate"]["quotient_applied"] ==
             arms["mre8f_gate"]["quotient_applied"],
             "C++ certified gate disagreed with Python reference")
        if arms["cpp_gate"]["quotient_applied"]:
            gp=arms["cpp_gate"]["gate"]
            py=arms["mre8f_gate"]["gate"]
            need(gp["variables_eliminated"]==py["variables_eliminated"] and
                 gp["clauses_removed"]==py["removed_clauses"],
                 "C++ mathematical quotient changed original proof outcome")
    modes={}
    for mode in MODES:
        arr=[r for r in rows if r["mode"]==mode]
        modes[mode]=dict(
            trials=len(arr),
            solved=sum(r["status"] in ("SAT","UNSAT") for r in arr),
            sat=sum(r["status"]=="SAT" for r in arr),
            unsat_no_independent_LRAT=sum(r["status"]=="UNSAT" for r in arr),
            timeout=sum(r["status"]=="TIMEOUT" for r in arr),
            bounded_unknown=sum(r["status"]=="BUDGET" for r in arr),
            total_wall_s=round(sum(r["total_wall_s"] for r in arr),6),
            par2_s=round(sum(r["par2_s"] for r in arr),6),
            external_prep_s=round(sum(r["preprocessing_s"] for r in arr),6),
            native_gate_s=round(sum(r["native_gate_s"] or 0 for r in arr),6),
            native_parse_s=round(sum(r["native_parse_s"] or 0 for r in arr),6),
            gate_activations=sum(r["quotient_applied"] for r in arr),
            propagations=sum((r["counters"] or {}).get("propagations",0)
                             for r in arr))
    report=dict(protocol=PROTO,dataset=dataset,source_count=len(source),
                trials=len(rows),modes=modes,source_selection_not_new_blind=True,
                reference_MRE6f_run=42499854392,
                bounded_budget_not_solved=(dataset=="bounded"),
                full_wall_includes_cpp_preflight=True,
                source_sha_and_paired_seed_verified=True,
                original_sat_models_verified=True,
                independent_UNSAT_LRAT=False,
                gate_matches_python_reference_on_every_paired_input=True,
                promotion_allowed=False)
    folder=ROOT/dataset
    (folder/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE9_FINAL_"+dataset.upper(),json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","shard","audit"))
    ap.add_argument("--dataset",choices=("bounded","verdict"),default="bounded")
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--cpp",default="mre9/native")
    ap.add_argument("--standalone",default="mre9/standalone")
    ap.add_argument("--refbin",default="mre6e/native")
    args=ap.parse_args()
    if args.action=="selftest":test_native(args.standalone)
    elif args.action=="shard":shard(args.dataset,args.shard,args.refbin,args.cpp)
    else:audit(args.dataset)
