#!/usr/bin/env python3
"""DRNAS EQUIV13: preregistered CNF structural routing, placebo, prospective SHA.

Freeze original 2021-23 official SAT Competition SHA before observing ANY
EQUIV13 solver outcomes. No timing/oracle filter. Original CNF model checked.
UNSAT counts for strict PAR2 only if reference Kissat and CaDiCaL both return
UNSAT on the original SHA; this is NOT independent LRAT proof.

Router probes binary implication SCC, complete 3-XOR motifs, Horn and density.
Placebo ROTATES the source-only routing labels between SHA (exactly preserving
the mix of backends, without consulting any outcomes). Both router and placebo
recompute identical signals and charge all preprocessing to 15s E2E.
One logical CPU per trial, no parallel child portfolio. Frozen experiments only.
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
import drnas_equiv12_cms_native_crossover as e12

ROOT=pathlib.Path("mre_equiv13")
SOURCE=e9.SOURCE
CMS=e12.CMS
PROTO="DRNAS-EQUIV13-SOURCE-STRUCTURAL-ROTATED-PLACEBO-12SHA-6ARM-2REP-15S-v1"
SALT="DRNAS-EQUIV13-20261110-FRESH-SHA-SOURCE-ONLY-NO-OUTCOME-v1"
YEARS=("2021","2022","2023")
TARGET=12
SHARDS=4
REPS=2
CAP=15.0
ARMS=("router","rotated_placebo","kissat1","native_altseed",
      "cms517_default","cadical301_default")
BACKENDS=("kissat1","native_altseed","cms517_default")
MAX_SCAN=1100
MAX_RAW=12*1024*1024
MAX_PLAIN=12*1024*1024
MAX_VARS=12000
MAX_CLAUSES=85000

def need(ok,why):
    if not ok:raise RuntimeError("EQUIV13_FAIL_CLOSED "+str(why))

def digest(p):return e9.digest(p)

def dump(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def signed_node(lit):
    return (abs(lit)-1)*2+(0 if lit>0 else 1)

def source_signals(n,clauses):
    """Deterministic source-only, no CDCL or solver. Exact 2-SAT graph SCC."""
    need(n>0 and len(clauses)>0,"invalid original CNF")
    vertices=2*n
    adj=[[] for _ in range(vertices)]
    rev=[[] for _ in range(vertices)]
    unit=binary=ternary=horn=0
    occ=0
    masks=collections.defaultdict(int)
    for clause in clauses:
        L=len(clause)
        occ+=L
        unit+=(L==1)
        horn+=(sum(x>0 for x in clause)<=1)
        if L==2:
            a,b=clause
            binary+=1
            if a!=b and a!=-b:
                for x,y in ((-a,b),(-b,a)):
                    u=signed_node(x);v=signed_node(y)
                    adj[u].append(v);rev[v].append(u)
        elif L==3:
            ternary+=1
            ab=tuple(sorted(map(abs,clause)))
            if len(set(ab))==3:
                by_var={abs(x):int(x<0) for x in clause}
                mask=by_var[ab[0]] | (by_var[ab[1]]<<1) | (by_var[ab[2]]<<2)
                masks[ab]|=1<<mask
    xor3=0
    for k in masks.values():
        if k & 0b01101001 == 0b01101001: xor3+=1  # even parity masks 0,3,5,6
        if k & 0b10010110 == 0b10010110: xor3+=1  # odd parity masks 1,2,4,7
    seen=bytearray(vertices);post=[]
    for start in range(vertices):
        if seen[start]:continue
        seen[start]=1
        stack=[(start,0)]
        while stack:
            u,i=stack[-1]
            if i<len(adj[u]):
                v=adj[u][i];stack[-1]=(u,i+1)
                if not seen[v]:
                    seen[v]=1;stack.append((v,0))
            else:
                post.append(u);stack.pop()
    comp=[-1]*vertices;sizes=[]
    for start in reversed(post):
        if comp[start]>=0:continue
        cid=len(sizes);size=0;stack=[start];comp[start]=cid
        while stack:
            u=stack.pop();size+=1
            for v in rev[u]:
                if comp[v]<0:comp[v]=cid;stack.append(v)
        sizes.append(size)
    nontriv=sum(k for k in sizes if k>1)
    contradiction=sum(comp[2*i]==comp[2*i+1] for i in range(n))
    k=len(clauses)
    return dict(vars=n,clauses=k,unit=unit,binary=binary,ternary=ternary,
       horn_ratio=round(horn/k,6),binary_ratio=round(binary/k,6),
       avg_clause_len=round(occ/k,6),scc_nontrivial_literal_nodes=nontriv,
       scc_count=len(sizes),binary_scc_opposite_pairs=contradiction,
       xor3_complete_patterns=xor3)

def choose(signals):
    """Precommitted hypothesis based only on mathematical source structure."""
    if signals["xor3_complete_patterns"]>=2:
        return "cms517_default","source_complete_xor3"
    if (signals["vars"]<=1200 and signals["clauses"]<=20000) or (
        signals["binary_ratio"]>=0.42 and
        signals["scc_nontrivial_literal_nodes"]>=max(8,signals["vars"]//50)):
        return "native_altseed","small_or_dense_binary_scc"
    return "kissat1","conservative_kissat_fallback"

def registries():
    # Verify all original historic registries before adding fresh SHA.
    sha,ids,old=e9.registries()
    m=e9.verify()
    for c in m["cases"]:
        sha.add(c["sha256"]);ids.add(c["gbd"])
    known=m5.verify()
    for c in known["cases"]:
        sha.add(c["sha256"]);ids.add(c["gbd"])
    history=dict(old=old,equiv9=digest(e9.ROOT/"manifest.json"),
                 equiv10m5=digest(m5.ROOT/"manifest.json"),
                 equiv12=digest(e12.ROOT/"manifest.json"))
    return sha,ids,history

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    SOURCE.mkdir(parents=True,exist_ok=True)
    e12.verify()
    prior_sha,prior_ids,historical=registries()
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as fetch
    indexes={};candidates=[]
    for year in YEARS:
        allids,mainsha=pool.getids("track=main_"+year)
        easy,easysha=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(allids)==400 and set(easy)<=set(allids),
             "official index unexpected "+year)
        indexes[year]=dict(main_sha256=mainsha,easy_sha256=easysha,
                           source_easy_index_count=len(easy))
        easyset=set(easy)
        candidates.extend((year,id,0) for id in easy if id not in prior_ids)
        candidates.extend((year,id,1) for id in allids
                          if id not in easyset and id not in prior_ids)
    candidates=sorted(set(candidates),key=lambda a:(
        a[2],hashlib.sha256((SALT+"|"+a[0]+"|"+a[1]).encode()).hexdigest()))
    seen=set();cases=[];trace=[]
    for year,gbd,tier in candidates:
        if len(cases)>=TARGET:break
        if gbd in seen or gbd in prior_ids:continue
        seen.add(gbd)
        need(len(seen)<=MAX_SCAN,"source-only candidate scan cap")
        p=SOURCE/(gbd+".cnf")
        record=dict(year=year,gbd=gbd,
            index_tier="minisat1m_yes" if tier==0 else "full_main")
        try:
            raw=fetch.get("https://benchmark-database.de/file/"+gbd,MAX_RAW,seconds=20)
            plain,_=fetch.prior.r32p.decode(raw)
            need(len(plain)<=MAX_PLAIN,"source byte cap")
            n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=MAX_VARS and 0<k<=MAX_CLAUSES,"source geometry cap")
            sha=hashlib.sha256(plain).hexdigest()
            need(sha not in prior_sha,"historic SHA collision")
            p.write_bytes(plain)
            n2,clauses=e9.x22.read_cnf(p)
            need(n2==n and len(clauses)==k,"original DIMACS size mismatch")
            signals=source_signals(n,clauses)
            selected,reason=choose(signals)
            cases.append(dict(gbd=gbd,year=year,sha256=sha,
                  filename=p.name,index_tier=record["index_tier"],
                  bytes=len(plain),signals=signals,
                  route_backend=selected,route_reason=reason))
            prior_sha.add(sha);prior_ids.add(gbd)
            record.update(action="frozen",sha256=sha,
                          selected_backend=selected,reason=reason)
        except Exception as error:
            p.unlink(missing_ok=True)
            record.update(action="excluded_without_solving",
                          reason=str(error)[:180])
        trace.append(record)
        dump(ROOT/"selection-progress.json",
             dict(salt=SALT,selected=len(cases),trace=trace))
        print("EQUIV13_SOURCE",json.dumps(record,sort_keys=True),flush=True)
    need(len(cases)==TARGET and len({c["sha256"] for c in cases})==TARGET,
         "not twelve SHA-disjoint original sources")
    # Placebo is a deterministic rotation of ROUTING LABELS across distinct
    # SHA. This preserves exact backend prevalence and destroys feature pairing.
    ordering=sorted(cases,key=lambda c:c["sha256"])
    rotated={ordering[i]["sha256"]:ordering[(i+1)%TARGET]["route_backend"]
             for i in range(TARGET)}
    for c in cases:c["placebo_backend"]=rotated[c["sha256"]]
    need(collections.Counter(c["route_backend"] for c in cases)==
         collections.Counter(c["placebo_backend"] for c in cases),
         "placebo changes backend population")
    m=dict(protocol=PROTO, selection_salt=SALT,selection_indexes=indexes,
       historical_registry_sha256=historical,
       selection_trace=trace,cases=cases,source_count=TARGET,
       arms=list(ARMS),reps=REPS,shards=SHARDS,cap_s=CAP,
       expected_trials=TARGET*REPS*len(ARMS),
       new_sha_relative_to_registered_history=True,
       globally_blind=False,history_registry_not_globally_exhaustive=True,
       source_only_selection=True,no_outcome_based_source_filter=True,
       router_only_source_features=True,
       placebo_exact_backend_count_preserving_rotation=True,
       router_rule="xor3_patterns>=2 -> CMS; small<=1200vars/20kclauses OR binary>=.42 & multi_SCC_nodes>=max(8,n//50) -> Native altseed; else Kissat",
       one_logical_cpu_per_arm=True,no_parallel_children=True,
       SAT_original_model_required=True,UNSAT_reference_agreement_no_LRAT=True,
       no_auto_promotion=True,code_sha256=digest(__file__),
       binaries=dict(native=digest(e9.NATIVE),kissat=digest(e9.KISSAT),
           cadical=digest(e9.CAD),cms=digest(CMS)))
    dump(ROOT/"manifest.json",m)
    verify()
    print("EQUIV13_FROZEN",json.dumps(dict(sources=TARGET,
         trials=m["expected_trials"],features=list(cases[0]["signals"]),
         routing=dict(collections.Counter(c["route_backend"] for c in cases)),
         years=dict(collections.Counter(c["year"] for c in cases)),
         placebo_preserves_backend_population=True),sort_keys=True),flush=True)

def verify():
    e12.verify()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["source_count"]==TARGET and len(m["cases"])==TARGET and
         m["shards"]==SHARDS and m["reps"]==REPS and m["cap_s"]==CAP and
         m["expected_trials"]==TARGET*REPS*len(ARMS),"manifest protocol drift")
    need(m["code_sha256"]==digest(__file__) and
         m["binaries"]==dict(native=digest(e9.NATIVE),
              kissat=digest(e9.KISSAT),cadical=digest(e9.CAD),
              cms=digest(CMS)),"frozen binaries/script drift")
    hist_sha,hist_ids,hist=registries()
    need(m["historical_registry_sha256"]==hist,"historic exclusion changed")
    need(len({c["sha256"] for c in m["cases"]})==TARGET,
         "duplicate source hash")
    for c in m["cases"]:
        need(c["sha256"] not in hist_sha and c["gbd"] not in hist_ids,
             "prior source overlap")
        need(digest(SOURCE/c["filename"])==c["sha256"],"source SHA changed")
        need(choose(c["signals"])[0]==c["route_backend"],
             "router decision changed")
    ordering=sorted(m["cases"],key=lambda c:c["sha256"])
    for idx,c in enumerate(ordering):
        need(c["placebo_backend"]==ordering[(idx+1)%TARGET]["route_backend"],
             "placebo rotation changed")
    return m

def cms_trial(c,rep,limit):
    src=SOURCE/c["filename"]
    n,clauses=e9.x22.read_cnf(src)
    need(n>0 and len(clauses)>0,"CMS source missing")
    cpu=min(os.sched_getaffinity(0))
    before=e9.x22.child_cpu(); start=time.perf_counter()
    status="TIMEOUT"; witness=False
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        ch=e9.x22.launch("cms",[str(CMS),"--verb","0","-t","1",str(src)],
                         cpu,folder)
        try:
            while ch["p"].poll() is None and time.perf_counter()-start<limit-.018:
                time.sleep(.004)
            if ch["p"].poll() is not None:
                stdout,stderr=e9.x22.read_output(ch)
                status,witness=e9.x22.solver_result("cms",
                     ch["p"].returncode,stdout,clauses,{})
        finally:
            e9.x22.cleanup([ch])
    elapsed=time.perf_counter()-start
    if elapsed>=limit or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"CMS original SAT witness invalid")
    return dict(status=status,SAT_original_witness_verified=bool(
            status=="SAT" and witness),UNSAT_independent_LRAT=False,
        child_CPU_s=round(e9.x22.child_cpu()-before,6),
        wall_E2E_s=round(elapsed,6),pinned_cpu=cpu,child_starts=1)

def trial(c,rep,arm):
    need(0<=rep<REPS and arm in ARMS,"bad trial key")
    src=SOURCE/c["filename"]
    need(digest(src)==c["sha256"],"original SHA changed")
    started=time.perf_counter(); selected=arm
    signals=None;route_reason="fixed_reference_arm"
    prep=0.0
    if arm in ("router","rotated_placebo"):
        n,clauses=e9.x22.read_cnf(src)
        signals=source_signals(n,clauses)
        need(signals==c["signals"],"preprocessing signals not reproducible")
        if arm=="router":
            selected,route_reason=choose(signals)
            need(selected==c["route_backend"],"router changed from freeze")
        else:
            selected=c["placebo_backend"]
            route_reason="same_preprocessing_rotated_population_placebo"
        prep=time.perf_counter()-started
    need(selected in BACKENDS+("cadical301_default",),"unknown selected backend")
    remaining=CAP-(time.perf_counter()-started)
    need(remaining>0.1,"preprocess exhausted E2E budget")
    if selected=="cms517_default":
        inner=cms_trial(c,rep,remaining)
    else:
        inner=e9.trial(c,rep,selected,remaining)
    elapsed=time.perf_counter()-started
    status=inner["status"];witness=inner["SAT_original_witness_verified"]
    if elapsed>=CAP:
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"source SAT witness rejected")
    return dict(protocol=PROTO,arm=arm,selected_backend=selected,
       route_reason=route_reason,gbd=c["gbd"],sha256=c["sha256"],
       year=c["year"],rep=rep,cap_s=CAP,
       status=status,SAT_original_witness_verified=witness,
       UNSAT_independent_LRAT=False,wall_E2E_s=round(elapsed,6),
       child_CPU_s=inner["child_CPU_s"],pinned_cpu=inner["pinned_cpu"],
       child_starts=inner["child_starts"],
       source_signals_checked=(signals is not None),
       preparation_E2E_s=round(prep,6))

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    # Complete parity-3 encoding on one set of variables, one XOR motif.
    clauses=[(1,2,3),(1,-2,-3),(-1,2,-3),(-1,-2,3)]
    s=source_signals(3,clauses)
    need(s["xor3_complete_patterns"]==1,
         "source exact XOR3 detector false negative")
    dense=source_signals(2,[(1,2),(-1,2),(1,-2),(-1,-2)])
    need(dense["binary_scc_opposite_pairs"]==2,
         "signed binary SCC contradiction selftest failed")
    need(choose(s)[0] in BACKENDS,"route invalid")
    e12.selftest()
    print("EQUIV13_SELFTEST_PASS",json.dumps(dict(
        xor3_checked=True,scc_opposite_checked=True,
        cms_original_SAT_checked=True),sort_keys=True),flush=True)

def shard(idx):
    m=verify();need(0<=idx<SHARDS,"invalid shard")
    subset=m["cases"][idx::SHARDS]
    need(len(subset)==TARGET//SHARDS,"shard imbalance")
    rows=[]
    for c in subset:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+"|E13|"+str(rep)).shuffle(arms)
            for arm in arms:
                r=trial(c,rep,arm)
                rows.append(r)
                dump(ROOT/("shard-%d.json"%idx),rows)
                print("EQUIV13_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==TARGET//SHARDS*REPS*len(ARMS),"shard incomplete")
    print("EQUIV13_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    cases={c["sha256"]:c for c in m["cases"]}
    rows=[]
    for idx in range(SHARDS):
        rr=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
        need(len(rr)==TARGET//SHARDS*REPS*len(ARMS),
             "shard size incomplete")
        rows+=rr
    expected={(sha,rep,arm) for sha in cases for rep in range(REPS)
              for arm in ARMS}
    actual={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(actual)==len(expected) and actual==expected,
         "missing or duplicate paired source trials")
    bysha=collections.defaultdict(list)
    for r in rows:
        c=cases[r["sha256"]]
        need(r["protocol"]==PROTO and r["gbd"]==c["gbd"] and
             r["cap_s"]==CAP and r["wall_E2E_s"]<=CAP+.08 and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]) and
             r["selected_backend"]==(c["route_backend"] if r["arm"]=="router"
               else c["placebo_backend"] if r["arm"]=="rotated_placebo"
               else r["arm"]),"trial original SHA/route/proof/budget mismatch")
        bysha[r["sha256"]].append(r)
    agreed=set()
    for sha,rr in bysha.items():
        verdicts={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(verdicts)<=1,"SAT/UNSAT source mismatch "+sha)
        if (any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr)
            and any(r["arm"]=="cadical301_default" and r["status"]=="UNSAT"
                    for r in rr)):
            agreed.add(sha)
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT"
                                       and r["sha256"] in agreed)
    scores={}
    for arm in ARMS:
        g=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(attempts=len(g),solved=sum(accepted(r) for r in g),
            SAT_verified=sum(r["status"]=="SAT" for r in g),
            UNSAT_reference_agreement_no_LRAT=sum(r["status"]=="UNSAT"
                                                and accepted(r) for r in g),
            UNSAT_unconfirmed=sum(r["status"]=="UNSAT" and
                                  not accepted(r) for r in g),
            timeouts=sum(r["status"]=="TIMEOUT" for r in g),
            PAR2_s=round(sum(r["wall_E2E_s"] if accepted(r)
                           else 2*CAP for r in g),6),
            actual_child_CPU_s=round(sum(r["child_CPU_s"] for r in g),6),
            preprocessing_wall_s=round(sum(r["preparation_E2E_s"] for r in g),6),
            selected_counts=dict(collections.Counter(r["selected_backend"]
                                                       for r in g)))
    for a in ARMS:
        scores[a]["speedup_vs_kissat_PAR2_x"]=round(
            scores["kissat1"]["PAR2_s"]/scores[a]["PAR2_s"],6)
        scores[a]["speedup_vs_placebo_PAR2_x"]=round(
            scores["rotated_placebo"]["PAR2_s"]/scores[a]["PAR2_s"],6)
    paired={}
    for arm in ("router","rotated_placebo"):
        diffs=[]
        for sha,rr in bysha.items():
            for rep in range(REPS):
                r=next(x for x in rr if x["arm"]==arm and x["rep"]==rep)
                ref=next(x for x in rr if x["arm"]=="kissat1" and x["rep"]==rep)
                diffs.append((r["wall_E2E_s"] if accepted(r) else 2*CAP)-
                             (ref["wall_E2E_s"] if accepted(ref) else 2*CAP))
        paired[arm]=dict(wins=sum(z<-.02 for z in diffs),
                         losses=sum(z>.02 for z in diffs),
                         ties=sum(abs(z)<=.02 for z in diffs))
    report=dict(protocol=PROTO,source_count=TARGET,trials=len(rows),
       frozen_before_E2E=True,source_only_selection=True,
       not_globally_blind=True, no_independent_UNSAT_LRAT=True,
       original_SAT_models_verified=True, one_logical_CPU=True,
       routed_preprocess_included_in_E2E=True,
       placebo_same_preprocess_and_exact_backend_distribution=True,
       source_history_register_not_exhaustive=True,
       no_auto_promotion=True, UNSAT_reference_agreement_SHA=sorted(agreed),
       routing=dict(collections.Counter(c["route_backend"] for c in cases.values())),
       scores=scores,paired_vs_kissat=paired,
       per_sha={sha:dict(gbd=cases[sha]["gbd"],year=cases[sha]["year"],
           signals=cases[sha]["signals"],route=cases[sha]["route_backend"],
           placebo=cases[sha]["placebo_backend"],
           per_arm={arm:dict(statuses=[r["status"] for r in rr if r["arm"]==arm],
                 E2E_s=[r["wall_E2E_s"] for r in rr if r["arm"]==arm])
                 for arm in ARMS}) for sha,rr in bysha.items()})
    dump(ROOT/"report.json",report)
    print("EQUIV13_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="shard":shard(args.shard)
    else:
        globals()[args.action]()
        if args.action=="verify":print("EQUIV13_VERIFY_PASS",flush=True)
