#!/usr/bin/env python3
"""BINARY-SCC1: SHA-locked source-only native signed-implication SCC audit.

No SAT/CDCL solve, no mutation of original CNF, no LRAT. Independent Python
Tarjan checks ALL C++ SCC equivalence aliases from original clauses. Explicit
two-path witness for contradictory literal verified edge-for-edge on original.
No UNSAT claims unless the exact original graph contains a replayed
contradiction (or an explicit empty clause). Reference solvers not run.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import resource
import statistics
import subprocess
import tempfile
import time

import drnas_equiv9_prospective_seed_holdout as e9
import drnas_equiv10m5_frozen_rescue as m5

ROOT=pathlib.Path("mre_binary_scc1")
BIN=ROOT/"bin/scc_scout"
PROTO="DRNAS-BINARY-SCC1-SOURCE-ONLY-17SHA-3REPS-PROOF-20261110-v1"
REPS=3
SHARDS=4
EXPECTED=17
TIMEOUT=15.0
BIN_RATIO_HIGHLIGHT=0.9

def need(ok,why):
    if not ok:raise RuntimeError("BINARY_SCC1_FAIL_CLOSED "+str(why))
def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def cases():
    e=e9.verify()
    m=m5.verify()
    old=[dict(source="EQUIV9_holdout_seen",**x) for x in e["cases"] if x["cohort"]=="holdout"]
    new=[dict(source="EQUIV10M5_reference_selected_seen",**x) for x in m["cases"]]
    c=old+new
    need(len(old)==12 and len(new)==5 and len(c)==EXPECTED,
         "unexpected source count")
    need(len({x["sha256"] for x in c})==EXPECTED,"overlap/duplicate source SHA")
    for x in c:
        src=e9.SOURCE/x["filename"]
        need(src.is_file() and e9.digest(src)==x["sha256"],
             "original CNF SHA drift "+str(x["gbd"]))
    return c

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(BIN.is_file(),"native binary missing")
    c=cases()
    m=dict(protocol=PROTO,script_sha256=e9.digest(__file__),
        binary_sha256=e9.digest(BIN),equiv9_manifest_sha256=e9.digest(e9.ROOT/"manifest.json"),
        equiv10m5_manifest_sha256=e9.digest(m5.ROOT/"manifest.json"),
        cohort="previously seen EQUIV9 12 SHA and EQUIV10M5 5 SHA (NOT BLIND)",
        original_SHA_locked=True,not_blind=True,no_reselection=True,
        original_input_unchanged=True,no_solver_runs=True,
        only_original_2clauses_and_units=True,
        all_native_aliases_independently_Tarjan_verified=True,
        contradiction_requires_checked_two_way_implication_paths=True,
        claim_no_independent_LRAT=True,
        do_not_count_as_PAR2_SAT_benchmark=True,
        one_logical_CPU=True,
        proof_policy="check every alias by independently constructed graph SCC; "
                     "check contradictory source paths edge-by-edge; no LRAT",
        emphasis_binary_ratio=BIN_RATIO_HIGHLIGHT,
        candidates=c,n_cases=EXPECTED,n_reps=REPS,n_shards=SHARDS,
        total_scans=EXPECTED*REPS,timeout_s=TIMEOUT,no_auto_promotion=True)
    save(ROOT/"manifest.json",m)
    verify()
    print("BINARY_SCC1_FROZEN "+json.dumps(dict(sources=EXPECTED,reps=REPS,
        expected_scans=EXPECTED*REPS,shards=SHARDS,
        original_SHA_verified=True,no_CDCL=True,
        all_aliases_need_independent_verification=True,
        no_LRAT=True),sort_keys=True),flush=True)

def verify():
    c=cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["candidates"]==c and
         m["n_cases"]==EXPECTED and m["n_reps"]==REPS and
         m["n_shards"]==SHARDS and m["total_scans"]==EXPECTED*REPS and
         m["timeout_s"]==TIMEOUT and
         m["script_sha256"]==e9.digest(__file__) and
         m["binary_sha256"]==e9.digest(BIN) and
         m["equiv9_manifest_sha256"]==e9.digest(e9.ROOT/"manifest.json") and
         m["equiv10m5_manifest_sha256"]==e9.digest(m5.ROOT/"manifest.json"),
         "protocol/source/C++ binary/Python SHA drift")
    return m

def node(lit):
    return 2*(abs(lit)-1)+(lit<0)

def signed(i):
    return (i//2+1)*(-1 if i%2 else 1)

def independent_graph(n,clauses):
    """Independent original clauses parser and Tarjan graph verifier."""
    g=[[] for _ in range(2*n)]
    edges=set()
    binary=unit=empty=taut=0
    lits=0
    for c in clauses:
        lits+=len(c)
        if not c:
            empty+=1
        elif len(c)==1:
            unit+=1
            u,v=node(-c[0]),node(c[0])
            g[u].append(v);edges.add((u,v))
        elif len(c)==2:
            binary+=1;a,b=c
            if a==-b:
                taut+=1
                continue
            if a==b:
                u,v=node(-a),node(a)
                g[u].append(v);edges.add((u,v))
            else:
                for u,v in ((node(-a),node(b)),(node(-b),node(a))):
                    g[u].append(v);edges.add((u,v))
    return g,edges,dict(variables=n,clauses=len(clauses),
        literal_occurrences=lits, binary_clauses=binary,
        unit_clauses=unit,empty_clauses=empty,
        tautological_binary=taut,implication_edges=sum(len(a) for a in g))

def independent_tarjan(g):
    """Tarjan iterative SCC, deliberately different from C++ Kosaraju."""
    n=len(g)
    discovery=[-1]*n;low=[0]*n;inside=[False]*n;pool=[]
    comp=[-1]*n;comps=0;nextid=0
    for start in range(n):
        if discovery[start]>=0:continue
        dfs=[(start,0,-1)]
        while dfs:
            v,at,parent=dfs[-1]
            if discovery[v]<0:
                discovery[v]=low[v]=nextid;nextid+=1
                pool.append(v);inside[v]=True
            if at<len(g[v]):
                w=g[v][at]
                dfs[-1]=(v,at+1,parent)
                if discovery[w]<0:
                    dfs.append((w,0,v))
                elif inside[w]:
                    low[v]=min(low[v],discovery[w])
            else:
                if low[v]==discovery[v]:
                    while True:
                        w=pool.pop();inside[w]=False;comp[w]=comps
                        if w==v:break
                    comps+=1
                dfs.pop()
                if parent>=0:
                    low[parent]=min(low[parent],low[v])
    need(all(x>=0 for x in comp),"Tarjan missing literal component")
    return comp,comps

def verified_alias_map(comp,n):
    canon={}
    sizes=collections.Counter(comp)
    for i,cid in enumerate(comp):
        l=signed(i)
        if cid not in canon or (abs(l),-l)<(abs(canon[cid]),-canon[cid]):
            canon[cid]=l
    mapping=[]
    conflicts=[]
    for v in range(1,n+1):
        if comp[node(v)]==comp[node(-v)]:
            conflicts.append(v)
        else:
            target=canon[comp[node(v)]]
            if abs(target)<v:
                need(comp[node(-v)]==comp[node(-target)] and
                     comp[node(v)]==comp[node(target)],
                     "positive and negative signed equivalence mismatch")
                mapping.append([v,target])
    return mapping,conflicts,dict(
        scc_components=len(sizes),
        nontrivial_scc=sum(sz>1 for sz in sizes.values()),
        largest_scc=max(sizes.values(),default=0))

def verify_path(original_edges,seq,src,dst,n):
    need(isinstance(seq,list) and 2<=len(seq)<=2*n+1 and
         seq[0]==src and seq[-1]==dst,"invalid contradiction path endpoints")
    for a,b in zip(seq,seq[1:]):
        need(1<=abs(a)<=n and 1<=abs(b)<=n and
             (node(a),node(b)) in original_edges,
             "contradiction proof step not in original input binary/unit graph")

def independent_check(source,out):
    n,clauses=e9.x22.read_cnf(source)
    graph,edges,expected=independent_graph(n,clauses)
    comp,num=independent_tarjan(graph)
    aliases,conflicts,metrics=verified_alias_map(comp,n)
    for key,value in {**expected,**metrics}.items():
        need(out.get(key)==value,
             "C++/independent Python disagreement in "+key)
    need(out.get("alias_map")==aliases,"native aliases not implied by original CNF")
    need(out.get("certifiable_alias_candidates")==len(aliases),
         "C++ alias total is not verified")
    need(out.get("contradictory_vars")==len(conflicts),
         "original signed SCC contradiction count mismatch")
    need(abs(out.get("binary_ratio",0)-expected["binary_clauses"]/max(1,len(clauses)))<1e-5,
         "original binary ratio wrong")
    if conflicts:
        need(out.get("contradiction_witness_var")==conflicts[0],
             "native contradiction witness source variable drift")
        v=conflicts[0]
        verify_path(edges,out.get("path_positive_to_negative"),v,-v,n)
        verify_path(edges,out.get("path_negative_to_positive"),-v,v,n)
    else:
        need("path_positive_to_negative" not in out and
             "path_negative_to_positive" not in out,
             "nonexistent contradiction witness")
    return dict(all_aliases_original_source_verified=len(aliases),
                contradiction_binary_subformula_path_verified=bool(conflicts),
                contradiction_count=len(conflicts),
                independent_algorithm="iterative Tarjan, native C++ Kosaraju",
                no_LRAT=True)

def native_run(src):
    cpu=min(os.sched_getaffinity(0))
    def setup():
        os.sched_setaffinity(0,{cpu})
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    p=subprocess.run([str(BIN.resolve()),str(src.resolve())],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        timeout=TIMEOUT,preexec_fn=setup,text=True)
    need(p.returncode==0,"C++ scanner failed "+
         p.stderr[-500:])
    need(p.stdout.count("\n")==1 and len(p.stdout)<2*1024*1024,
         "unexpected native JSON/oversized proof")
    out=json.loads(p.stdout)
    return out,cpu

def scan_one(c,rep):
    src=e9.SOURCE/c["filename"]
    begin=time.perf_counter()
    main_cpu=time.process_time()
    child_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    need(e9.digest(src)==c["sha256"],"original SHA mismatch")
    output,cpu=native_run(src)
    # Each counted result independently verifies source, all aliases, and
    # contradiction paths; no output counted as proof without this step.
    sound=independent_check(src,output)
    main_elapsed=time.process_time()-main_cpu
    ch=resource.getrusage(resource.RUSAGE_CHILDREN)
    child_cpu=(ch.ru_utime+ch.ru_stime)-(child_before.ru_utime+child_before.ru_stime)
    wall=time.perf_counter()-begin
    row=dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
        cohort=c["source"],rep=rep,status="SOURCE_SCREEN_COMPLETE",
        original_CNF_SHA_verified=True,one_CPU=cpu,
        scan_and_verify_E2E_wall_s=round(wall,6),
        python_verification_cpu_s=round(main_elapsed,6),
        native_child_CPU_s=round(child_cpu,6),
        binary_fraction=round(output["binary_ratio"],6),
        variables=output["variables"],clauses=output["clauses"],
        binary_clauses=output["binary_clauses"],
        unit_clauses=output["unit_clauses"],
        implication_edges=output["implication_edges"],
        scc_components=output["scc_components"],
        nontrivial_scc=output["nontrivial_scc"],
        largest_scc=output["largest_scc"],
        alias_candidates_verified=sound["all_aliases_original_source_verified"],
        contradictory_vars=sound["contradiction_count"],
        original_binary_unsat_path_verified=sound["contradiction_binary_subformula_path_verified"],
        explicit_empty_clause=output["empty_clauses"]>0,
        native_cpp_parse_ms=round(output["cnf_parse_ms"],5),
        native_cpp_scout_ms=round(output["total_scout_ms"],5),
        SAT_original_witness_verified=False,
        UNSAT_independent_LRAT=False,
        no_CDCL_solver_run=True)
    return row,output

def toy_tests():
    need(BIN.is_file(),"missing native C++ scanner")
    ROOT.mkdir(parents=True,exist_ok=True)
    rng=random.Random(8212026)
    total=0
    with tempfile.TemporaryDirectory() as td:
        src=pathlib.Path(td)/"toy.cnf"
        for i in range(150):
            n=2+rng.randrange(5)
            cl=[]
            for _ in range(rng.randrange(1,24)):
                size=rng.choice((1,2,2,2))
                cl.append([rng.choice((-1,1))*rng.randint(1,n)
                           for _ in range(size)])
            if i==0:cl=[[1],[-1]]
            if i==1:cl=[[-1,2],[1,-2]]
            if i==2:cl=[[1,-1]]
            if i==3:cl=[[]]
            src.write_text("p cnf %d %d\n"%(n,len(cl))+
                "".join(" ".join(map(str,c))+" 0\n" for c in cl))
            o,_=native_run(src)
            chk=independent_check(src,o)
            if all(len(c)<=2 for c in cl):
                sat=any(all(any((v>0)==bool(mask&(1<<(abs(v)-1))) for v in c)
                            for c in cl) for mask in range(1<<n))
                detected=(o["contradictory_vars"]>0 or o["empty_clauses"]>0)
                need(detected==not sat,"2-SAT brute force inconsistency")
            total+=1
    print("BINARY_SCC1_SELFTEST_PASS "+json.dumps(dict(
        random_and_adversarial_cases=total,
        independent_Tarjan_replay=True,
        brute_force_twoSAT_consistency=True,
        synthetic_contradiction_and_alias_cases=True),sort_keys=True),flush=True)

def shard(idx):
    need(0<=idx<SHARDS,"bad shard")
    m=verify()
    subset=[c for i,c in enumerate(m["candidates"]) if i%SHARDS==idx]
    rows=[];evidence={}
    for c in subset:
        rep_outputs=[]
        for rep in range(REPS):
            row,raw=scan_one(c,rep)
            row["shard"]=idx
            rows.append(row)
            rep_outputs.append(raw)
            if rep==0:
                # Keep bounded actual witnesses, no big generated proof files.
                evidence[c["sha256"]]=dict(gbd=c["gbd"],raw=raw)
            save(ROOT/("shard-%d.json"%idx),rows)
            print("BINARY_SCC1_SCAN "+json.dumps(row,sort_keys=True),flush=True)
        need(all(raw["alias_map"]==rep_outputs[0]["alias_map"] and
                 raw["contradictory_vars"]==rep_outputs[0]["contradictory_vars"]
                 for raw in rep_outputs),"nondeterministic source implication graph")
    save(ROOT/("shard-%d-evidence.json"%idx),evidence)
    need(len(rows)==len(subset)*REPS,"shard missing source")
    print("BINARY_SCC1_SHARD_PASS "+json.dumps(dict(shard=idx,
        originals=len(subset),scans=len(rows)),sort_keys=True),flush=True)

def audit():
    m=verify()
    rows=[];evidence={}
    for idx in range(SHARDS):
        rr=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        need(len(rr)==len([c for i,c in enumerate(m["candidates"]) if i%SHARDS==idx])*REPS,
             "shard count drift")
        rows.extend(rr)
        x=json.loads((ROOT/("shard-%d-evidence.json"%idx)).read_text())
        need(not set(x)&set(evidence),"duplicate source evidence")
        evidence.update(x)
    expected={(c["sha256"],rep) for c in m["candidates"] for rep in range(REPS)}
    have={(r["sha256"],r["rep"]) for r in rows}
    need(len(rows)==len(have)==len(expected)==m["total_scans"] and
         have==expected and len(evidence)==EXPECTED,
         "missing or duplicate original source scans")
    out={}
    for c in m["candidates"]:
        rr=[r for r in rows if r["sha256"]==c["sha256"]]
        need(len(rr)==REPS and all(r["status"]=="SOURCE_SCREEN_COMPLETE" and
            r["original_CNF_SHA_verified"] and r["no_CDCL_solver_run"] and
            not r["UNSAT_independent_LRAT"] for r in rr),
            "incomplete source-only proof verification")
        need(len({(r["alias_candidates_verified"],r["contradictory_vars"],
                    r["binary_clauses"],r["scc_components"]) for r in rr})==1,
             "source-only nondeterminism")
        output=evidence[c["sha256"]]["raw"]
        sound=independent_check(e9.SOURCE/c["filename"],output)
        need(sound["all_aliases_original_source_verified"]==rr[0]["alias_candidates_verified"],
             "audit independent replay mismatch")
        out[c["sha256"]]=dict(gbd=c["gbd"],source=c["source"],
            vars=rr[0]["variables"],clauses=rr[0]["clauses"],
            binary_fraction=rr[0]["binary_fraction"],
            certified_scc_aliases=rr[0]["alias_candidates_verified"],
            contradiction_binary_subformula_path_verified=rr[0]["original_binary_unsat_path_verified"],
            contradictory_vars=rr[0]["contradictory_vars"],
            native_cpp_scout_ms_median=round(statistics.median(r["native_cpp_scout_ms"] for r in rr),5),
            full_SHA_plus_independent_verify_E2E_s_median=round(
                statistics.median(r["scan_and_verify_E2E_wall_s"] for r in rr),6),
            CPU_child_s_total=round(sum(r["native_child_CPU_s"] for r in rr),6))
    saved=list(out.values())
    report=dict(protocol=PROTO,source_count=len(saved),scans=len(rows),
        original_SHA_locked=True,source_only_not_blind=True,
        no_CDCL_runs=True,no_PAR2_solution_claims=True,
        verified_total_source_SCC_aliases=sum(x["certified_scc_aliases"] for x in saved),
        SHA_with_at_least_one_verified_alias=sum(x["certified_scc_aliases"]>0 for x in saved),
        SHA_with_binary_subformula_contradiction_path=sum(
            x["contradiction_binary_subformula_path_verified"] for x in saved),
        SHA_binary_fraction_ge_90pct=sum(x["binary_fraction"]>=BIN_RATIO_HIGHLIGHT for x in saved),
        average_native_cpp_scout_ms=round(statistics.mean(r["native_cpp_scout_ms"] for r in rows),5),
        median_native_cpp_scout_ms=round(statistics.median(r["native_cpp_scout_ms"] for r in rows),5),
        total_native_child_CPU_s=round(sum(r["native_child_CPU_s"] for r in rows),6),
        total_SHA_and_verifier_E2E_wall_s=sum(round(r["scan_and_verify_E2E_wall_s"],6) for r in rows),
        original_path_replay_independent_Tarjan=True,
        no_independent_UNSAT_LRAT=True,no_auto_promotion=True,
        per_original=out,
        per_shard={str(i):dict(originals=len({r["sha256"] for r in rows if r["shard"]==i}),
                               scans=sum(r["shard"]==i for r in rows),
                               native_child_CPU_s=round(sum(r["native_child_CPU_s"] for r in rows if r["shard"]==i),6))
                         for i in range(SHARDS)})
    report["total_SHA_and_verifier_E2E_wall_s"]=round(report["total_SHA_and_verifier_E2E_wall_s"],6)
    save(ROOT/"report.json",report)
    print("BINARY_SCC1_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    elif a.action=="selftest":toy_tests()
    else:
        globals()[a.action]()
        if a.action=="verify":print("BINARY_SCC1_VERIFY_PASS",flush=True)
