#!/usr/bin/env python3
"""DECOMP3 — Root-UP-induced CNF separation; no SAT/CDCL performance claims.

Source SHA is frozen before graph/UP analysis, and original CNF is immutable.
A source-only root unit closure is logically sound; condition the CNF using
these forced assignments and compare incidence connectivity/articulation.
Original and reduced candidate separators are verified by independent Python
BFS. No solver backend, no proof of additional UNSAT claims, PAR2 not applicable.
"""
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import subprocess
import tempfile
import time

import dmd1_bench as d1
import decomp2_exact_bench as d2

ROOT=pathlib.Path("mre_decomp3")
BIN=pathlib.Path("mre_decomp1/bin/decomp1_incidence")
P="DRNAS-DECOMP3-ROOT-UP-SHA72-INCIDENCE-SCREEN-v1"
SHARDS=4
LOCAL_LIMIT_S=2.5

def require(value, reason):
    if not value:raise RuntimeError("DECOMP3_FAIL_CLOSED "+str(reason))

def pin():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    return cpu

def source_cases():
    a=json.loads(pathlib.Path("mre_x20/manifest.json").read_text())
    b=json.loads(pathlib.Path("mre_equiv7/manifest.json").read_text())
    require(len(a["cases"])==24 and len(b["cases"])==48,"frozen sources changed")
    out={}
    overlaps=0
    for label,entries,root in [
        ("EQUIV2_original_24",a["cases"],pathlib.Path("mre_x20")),
        ("EQUIV7_original_48",b["cases"],pathlib.Path("mre_equiv7/cases"))]:
        for c in entries:
            f=root/c["filename"];h=c["sha256"]
            require(f.is_file() and d1.sha(f)==h,"original SHA bytes mismatch "+str(f))
            if h in out:
                overlaps+=1;continue
            out[h]=dict(sha256=h,filename=c["filename"],
                        path=str(f),cohort=label,gbd=c.get("gbd"))
    require(len(out)>=48 and len(out)<=72,"unexpected source union")
    return sorted(out.values(),key=lambda x:x["sha256"]),overlaps

def canon(clauses):
    """Drop only tautologies/duplicate literals, both CNF-equivalent."""
    out=[]
    for c in clauses:
        t=tuple(sorted(set(c)))
        if any(-l in t for l in t):continue
        out.append(t)
    return out

def rootup(source,n,seconds=LOCAL_LIMIT_S):
    deadline=time.monotonic()+seconds
    clauses=canon(source)
    occur=collections.defaultdict(list)
    units=[]
    for i,c in enumerate(clauses):
        if (i&1023)==0 and time.monotonic()>deadline:
            return "ABSTAIN",{},[],"budget_occurrence_build"
        if not c:return "CONFLICT",{},[],"source_empty_clause"
        for l in c:occur[l].append(i)
        if len(c)==1:units.append(c[0])
    vals={}
    queue=collections.deque()
    def put(l):
        v=abs(l);value=(l>0)
        if v in vals:return vals[v]==value
        vals[v]=value;queue.append(l)
        return True
    for l in units:
        if not put(l):return "CONFLICT",vals,[],"contradictory_unit"
    scans=0
    while queue:
        assigned=queue.popleft()
        for j in occur.get(-assigned,()):
            scans+=1
            if (scans&255)==0 and time.monotonic()>deadline:
                return "ABSTAIN",{},[],"budget_unit_propagation"
            c=clauses[j]
            satisfied=False;unknown=0;last=0
            for l in c:
                v=vals.get(abs(l))
                if v is None:unknown+=1;last=l
                elif v==(l>0):satisfied=True;break
            if satisfied:continue
            if not unknown:return "CONFLICT",vals,[],"propagation_conflict"
            if unknown==1 and not put(last):
                return "CONFLICT",vals,[],"unit_incompatibility"
    residual=[]
    for j,c in enumerate(clauses):
        if (j&1023)==0 and time.monotonic()>deadline:
            return "ABSTAIN",{},[],"budget_residual"
        if any(vals.get(abs(l))==(l>0) for l in c if abs(l) in vals):
            continue
        z=tuple(l for l in c if abs(l) not in vals)
        require(bool(z),"closure residual unexpectedly empty")
        residual.append(z)
    return "OK",vals,residual,"unit_closure"

def write_cnf(path,n,clauses):
    with pathlib.Path(path).open("w") as f:
        f.write("p cnf "+str(n)+" "+str(len(clauses))+"\n")
        for c in clauses:f.write(" ".join(map(str,c))+" 0\n")

def native_scan(path):
    try:
        proc=subprocess.run([str(BIN),str(path),"2500"],capture_output=True,
            text=True,errors="replace",timeout=3.4)
    except subprocess.TimeoutExpired:
        return {"status":"ABSTAIN","reason":"external_graph_timeout"}
    lines=[x.split(" ",1)[1] for x in proc.stdout.splitlines()
           if x.startswith(("DECOMP1_SCAN ","DECOMP1_ABSTAIN "))]
    require(len(lines)==1 and proc.returncode in (0,75),"native graph protocol failed")
    result=json.loads(lines[0])
    require((proc.returncode==0)==(result.get("status")=="OK"),
            "native graph exit/status mismatch")
    return result

def verify_cpp_separator(n,clauses,stats):
    v=stats.get("best_separator_var",0)
    if v:
        d2.verify_separator(n,clauses,v,stats["best_clause_parts"])
    return v

def freeze():
    pin();ROOT.mkdir(exist_ok=True)
    cases,overlaps=source_cases()
    f=dict(protocol=P,cases=cases,source_count=len(cases),
           duplicate_source_SHA_across_cohorts=overlaps,
           globally_unseen=False,original_sha_frozen=True,
           no_SAT_solver_benchmark=True,no_auto_promotion=True)
    (ROOT/"freeze.json").write_text(json.dumps(f,indent=2,sort_keys=True)+"\n")
    print("DECOMP3_FREEZE_PASS "+json.dumps(dict(source_count=len(cases),duplicates=overlaps,
          source_cohorts=dict(collections.Counter(x["cohort"] for x in cases))),
          sort_keys=True),flush=True)

def loadfreeze():
    f=json.loads((ROOT/"freeze.json").read_text())
    require(f["protocol"]==P,"freeze protocol drift")
    for c in f["cases"]:
        require(d1.sha(pathlib.Path(c["path"]))==c["sha256"],"source drift")
    return f

def trial(case):
    pin();start=time.perf_counter()
    file=pathlib.Path(case["path"])
    require(d1.sha(file)==case["sha256"],"original SHA drift")
    n,source=d1.read_cnf(file)
    raw=native_scan(file)
    up,forced,residual,reason=rootup(source,n)
    reduced={"status":"NOT_APPLICABLE"}
    if up=="OK":
        with tempfile.TemporaryDirectory(prefix="decomp3-") as t:
            temp=pathlib.Path(t)/"residual.cnf"
            write_cnf(temp,n,residual)
            reduced=native_scan(temp)
            if reduced.get("status")=="OK":
                verify_cpp_separator(n,residual,reduced)
    if raw.get("status")=="OK":
        verify_cpp_separator(n,source,raw)
    added=0
    if raw.get("status")=="OK" and reduced.get("status")=="OK":
        added=int(reduced["clause_components"])-int(raw["clause_components"])
    row=dict(protocol=P,original_sha256=case["sha256"],cohort=case["cohort"],
       original_SHA_verified=d1.sha(file)==case["sha256"],
       cpu_affinity=sorted(os.sched_getaffinity(0)),
       variables=n,original_clauses=len(source),
       root_UP_status=up,root_UP_reason=reason,root_assigned=len(forced),
       residual_clauses=len(residual) if up=="OK" else None,
       raw_graph=raw,reduced_graph=reduced,new_component_delta=added,
       new_articulation=(reduced.get("status")=="OK" and
              reduced.get("best_second_largest_part",0)>
              raw.get("best_second_largest_part",0)),
       SAT_solved=False,UNSAT_independent_LRAT=False,
       bounded_CDCL=False,E2E_SAT_benchmark=False,
       wall_s=round(time.perf_counter()-start,6))
    require(row["original_SHA_verified"],"source overwritten")
    return row

def bench(shard):
    require(0<=shard<SHARDS,"shard range")
    c=loadfreeze()["cases"]
    rows=[]
    for i,case in enumerate(c):
        if i%SHARDS!=shard:continue
        row=trial(case);rows.append(row)
        (ROOT/("shard-"+str(shard)+".json")).write_text(
              json.dumps(rows,sort_keys=True,indent=2)+"\n")
        print("DECOMP3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    require(len(rows)==len(c[shard::SHARDS]),"shard partial")
    print("DECOMP3_SHARD_PASS",shard,len(rows),flush=True)

def audit():
    f=loadfreeze();rows=[];shards={}
    for i in range(SHARDS):
        p=ROOT/("shard-"+str(i)+".json")
        require(p.is_file(),"missing shard")
        a=json.loads(p.read_text())
        require(len(a)==len(f["cases"][i::SHARDS]),"shard incomplete")
        rows+=a
        shards[str(i)]=dict(total=len(a),
            graph_ok=sum(x["raw_graph"].get("status")=="OK" for x in a),
            root_up_ok=sum(x["root_UP_status"]=="OK" for x in a),
            new_separators=sum(x["new_articulation"] for x in a),
            new_component_sources=sum(x["new_component_delta"]>0 for x in a),
            elapsed_s=round(sum(x["wall_s"] for x in a),6))
    require(len(rows)==len(f["cases"]) and
            len({x["original_sha256"] for x in rows})==len(rows),
            "source match collision")
    require(set(x["original_sha256"] for x in rows)==
            set(x["sha256"] for x in f["cases"]),"frozen source mismatch")
    require(all(x["protocol"]==P and x["original_SHA_verified"] and
           len(x["cpu_affinity"])==1 and not x["E2E_SAT_benchmark"]
           for x in rows),"provenance mismatch")
    best=sorted([x for x in rows if x["new_articulation"] or
                  x["new_component_delta"]>0],
                key=lambda x: (
                  -x["reduced_graph"].get("best_second_largest_part",0),
                  -x["new_component_delta"],x["original_sha256"]))
    report=dict(protocol=P,source_count=len(rows),
        source_original_SHA_verified=True,
        root_up_pass=sum(x["root_UP_status"]=="OK" for x in rows),
        root_up_conflict=sum(x["root_UP_status"]=="CONFLICT" for x in rows),
        root_up_abstained=sum(x["root_UP_status"]=="ABSTAIN" for x in rows),
        root_units_total=sum(x["root_assigned"] for x in rows),
        raw_graph_analyzed=sum(x["raw_graph"].get("status")=="OK" for x in rows),
        reduced_graph_analyzed=sum(x["reduced_graph"].get("status")=="OK" for x in rows),
        created_new_graph_components=sum(x["new_component_delta"]>0 for x in rows),
        created_new_best_articulations=sum(x["new_articulation"] for x in rows),
        total_wall_s=round(sum(x["wall_s"] for x in rows),6),
        per_shard=shards,
        examples=[dict(sha=x["original_sha256"],cohort=x["cohort"],
            root_assigned=x["root_assigned"],
            old_components=x["raw_graph"].get("clause_components"),
            new_components=x["reduced_graph"].get("clause_components"),
            old_cut=x["raw_graph"].get("best_separator_var"),
            new_cut=x["reduced_graph"].get("best_separator_var"),
            new_cut_parts=x["reduced_graph"].get("best_clause_parts"))
            for x in best[:10]],
        SAT_solved=0,UNSAT_independent_LRAT=False,PAR2_s=None,
        screening_only=True,no_auto_promotion=True,
        not_globally_unseen=True)
    (ROOT/"audit.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("DECOMP3_FINAL "+json.dumps(report,sort_keys=True),flush=True)

def selftest():
    rng=random.Random(19937);count=0
    for i in range(220):
        n=rng.randrange(1,7)
        cs=[tuple((1 if rng.getrandbits(1) else -1)*v
                  for v in rng.sample(range(1,n+1),rng.randrange(1,n+1)))
            for _ in range(rng.randrange(1,15))]
        st,vals,remaining,reason=rootup(cs,n,4.0)
        require(st in ("OK","CONFLICT"),"selftest UP timeout")
        possible=0
        for bits in itertools.product((False,True),repeat=n):
            assign=dict(zip(range(1,n+1),bits))
            sat=d1.holds(cs,assign)
            possible+=int(sat)
            if st=="CONFLICT":
                require(not sat,"unit propagation false UNSAT")
            else:
                predicted=(all(assign.get(v)==b for v,b in vals.items()) and
                           d1.holds(remaining,assign))
                require(predicted==sat,"root UP residual changes full model set")
        if st=="OK":
            parts=d2.components(remaining)
            supports=[{abs(l) for j in p for l in remaining[j]} for p in parts]
            require(all(not(supports[u]&supports[v]) for u in range(len(parts))
                       for v in range(u+1,len(parts))),"components variable overlap")
        count+=1
    print("DECOMP3_SELFTEST_PASS "+json.dumps(dict(
       exhaustive_models_checked=count,original_model_set_equivalence=True,
       source_only_root_units=True,component_sets_disjoint=True)),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("selftest","freeze","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.cmd=="bench":bench(a.shard)
    else:globals()[a.cmd]()
