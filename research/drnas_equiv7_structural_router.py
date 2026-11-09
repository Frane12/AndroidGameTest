#!/usr/bin/env python3
"""DRNAS EQUIV7: precommitted structural selection on 16 NEW original CNF SHA.
All original SAT witnesses are independently evaluated against the SOURCE CNF.
The 48 sources are SHA-disjoint from X20/X21 and both previous EQUIV6 runs.
UNSAT requires agreement from unmodified Kissat and original-input CaDiCaL;
cross-solver agreement is NOT an independent LRAT proof.
Selectors depend only on source clause structure, never EQUIV3/4/5 outcomes.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import signal
import subprocess
import tempfile
import time

import drnas_x22_parallel_reducer as x22
import drnas_x20_select2_validation as x20

ROOT=pathlib.Path("mre_equiv7")
SOURCE=ROOT/"cases"
CAD=pathlib.Path("/usr/bin/cadical")
CAD3=ROOT/"bin/cadical_3_0_1"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
NATIVE=pathlib.Path("mre_x4/bin/native")
PROTO="DRNAS-EQUIV7-48FRESH-ROUTER-VS-FIXED-6ARM-2REP-12S-v1"
ARMS=("cadical3_default","cadical3_both","cadical3_route",
      "cadical3_route_placebo","cadical_default","kissat1")
OPTIONS={
    "cadical3_default":(),
    "cadical3_no_congruence":("--no-congruence",),
    "cadical3_no_reluctant":("--no-reluctant",),
    "cadical3_both":("--no-congruence","--no-reluctant"),
    "cadical3_route":(),
    "cadical3_route_placebo":(),
    "cadical_default":(),
}
CAP=12.0
REPS=2
SHARDS=8
TARGET=48
EXPECTED=TARGET*REPS*len(ARMS)
YEARS=("2021","2022","2023")
SALT="DRNAS-EQUIV7-20261109-INDEPENDENT-48-SHA-ROUTER-HOLDOUT-v1"
MAX_SCAN=1200

def need(ok,reason):
    if not ok:raise RuntimeError("EQUIV7_FAIL_CLOSED "+str(reason))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def save(path,value):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def seed(case,rep):
    return x20.seed(case,rep)

def source_signals(n,clauses):
    """Linear-ish source-only pass, no oracle, no CDCL, no solving."""
    total=len(clauses)
    need(total>0,"empty source")
    binary=0;horn=0;edges=set()
    for clause in clauses:
        horn+=sum(lit>0 for lit in clause)<=1
        if len(clause)==2:
            a,b=clause
            binary+=1
            if a!=b and a!=-b:
                edges.add((-a,b))
                edges.add((-b,a))
    reciprocal=sum((b,a) in edges for a,b in edges)//2
    return dict(vars=n,clauses=total,
         binary_ratio=round(binary/total,6),
         horn_ratio=round(horn/total,6),
         reciprocal_binary_edges=reciprocal,
         reciprocal_per_var=round(reciprocal/max(1,n),6))

def route(signals):
    """Policy frozen BEFORE fresh source outcomes; never read outcomes."""
    # Congruence proof search is unlikely to amortize if original binary
    # graph lacks a meaningful reciprocal-implication signal.
    gate=signals["reciprocal_binary_edges"] >= max(4,signals["vars"]//128)
    dense=signals["binary_ratio"]>=.2
    enable_congruence=gate and dense
    # Source-only surrogate for restart susceptibility; this is a testable
    # hypothesis, NOT a learned or outcome-fitted classifier.
    enable_reluctant=(signals["horn_ratio"]<.72 and
                      signals["binary_ratio"]>=.10)
    args=tuple([] if enable_congruence else ["--no-congruence"])+tuple(
         [] if enable_reluctant else ["--no-reluctant"])
    return args,dict(congruence=enable_congruence,
                     reluctant=enable_reluctant,
                     score_binary=signals["binary_ratio"],
                     score_horn=signals["horn_ratio"],
                     score_reciprocal=signals["reciprocal_binary_edges"])
def check_options():
    for exe in (CAD,CAD3):
        need(exe.is_file(),"missing CaDiCaL executable "+str(exe))
    versions={}
    for k,exe in (("old",CAD),("new",CAD3)):
        v=subprocess.run([str(exe),"--version"],check=True,capture_output=True,
                         text=True,timeout=15)
        versions[k]=(v.stdout+" "+v.stderr).strip()
    need("1.7.3" in versions["old"] and "3.0.1" in versions["new"],
         "CaDiCaL version mismatch")
    h=subprocess.run([str(CAD3),"--help"],check=True,capture_output=True,
                     text=True,timeout=15).stdout
    for option in ("--congruence","--reluctant"):
        need(option in h,"missing CaDiCaL3 option "+option)
    return versions

def exclusions():
    old=json.loads(pathlib.Path("mre_x20/manifest.json").read_text())
    x21=json.loads(pathlib.Path("prior_x22/mre_x22/manifest.json").read_text())
    prior_eq6=json.loads(pathlib.Path("prior_equiv6/mre_equiv6/manifest.json").read_text())
    need(len(old["cases"])==24 and len(x21["cases"])==24 and
         len(prior_eq6["cases"])==16,"prior roster incomplete")
    need(prior_eq6["protocol"].startswith("DRNAS-EQUIV6-"),
         "not the frozen EQUIV6 registry")
    cohorts=(old,x21,prior_eq6)
    sha={c["sha256"] for cohort in cohorts for c in cohort["cases"]}
    ids={c["gbd"] for cohort in cohorts for c in cohort["cases"]}
    need(len(sha)>=48,"suspicious prior SHA registry overlap")
    return sha,ids,dict(x20_sha256=digest("mre_x20/manifest.json"),
                        x21_sha256=digest("prior_x22/mre_x22/manifest.json"),
                        equiv6_sha256=digest("prior_equiv6/mre_equiv6/manifest.json"),
                        prior_equiv6_sources=len(prior_eq6["cases"]),
                        prior_cohort_sha_count=len(sha))
def freeze():
    ROOT.mkdir(exist_ok=True); SOURCE.mkdir(exist_ok=True)
    versions=check_options()
    for file in (KISSAT,NATIVE):
        need(file.is_file(),"reference solver missing: "+str(file))
    excluded_sha,excluded_ids,prior=exclusions()
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as fetch
    candidates=[];indexes={}
    for year in YEARS:
        ids,mainsha=pool.getids("track=main_"+year)
        easy,easysha=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(ids)==400 and set(easy)<=set(ids),"official index mismatch "+year)
        indexes[year]=dict(main_sha256=mainsha,easy_sha256=easysha,
                           eligible=len(easy))
        easy_set=set(easy)
        candidates.extend((year,gbd,0) for gbd in easy if gbd not in excluded_ids)
        # Include the full original official competition index after easy metadata.
        # No reference solver timing, SAT outcome or router result influences inclusion.
        candidates.extend((year,gbd,1) for gbd in ids
                          if gbd not in easy_set and gbd not in excluded_ids)
    candidates=sorted(set(candidates),
       key=lambda p:(p[2],hashlib.sha256(
           (SALT+"|"+p[0]+"|"+p[1]).encode()).hexdigest()))
    years=collections.Counter();binary_classes=collections.Counter()
    cases=[];seen=set();trace=[]
    for year,gbd,pool_tier in candidates:
        if len(cases)>=TARGET:break
        if gbd in seen or gbd in excluded_ids:continue
        seen.add(gbd)
        need(len(seen)<=MAX_SCAN,"source-only scan exhausted")
        path=SOURCE/(gbd+".cnf")
        record=dict(year=year,gbd=gbd,
                    source_index_tier="minisat1m_yes" if pool_tier==0 else "full_main")
        try:
            raw=fetch.get("https://benchmark-database.de/file/"+gbd,
                          12*1024*1024,seconds=20)
            plain,_=fetch.prior.r32p.decode(raw)
            need(len(plain)<=12*1024*1024,"source byte cap")
            n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=12000 and 0<k<=85000,"source geometry cap")
            sha=hashlib.sha256(plain).hexdigest()
            need(sha not in excluded_sha,"prior original SHA")
            path.write_bytes(plain)
            features=x20.features(path)
            need(features["vars"]==n and features["clauses"]==k,
                 "source geometry drift")
            binary_class=features["binary_class"]
            # Stratify in the audit; never reject a source merely to fill a
            # hard year/density quota that may be unachievable within caps.
            n2,cl=x22.read_cnf(path)
            need(n2==n,"parser inconsistent")
            sig=source_signals(n,cl)
            opts,decision=route(sig)
            cases.append(dict(filename=path.name,sha256=sha,gbd=gbd,
                        year=year,cohort="equiv7_sourceonly_precommitted",
                        structure=features,source_signals=sig,
                        preregistered_route_args=list(opts),
                        preregistered_route_decision=decision,bytes=len(plain)))
            years[year]+=1;binary_classes[binary_class]+=1
            excluded_sha.add(sha);excluded_ids.add(gbd)
            record.update(action="frozen_source_only",sha256=sha,
                     binary_class=binary_class,gate_args=list(opts))
        except Exception as error:
            path.unlink(missing_ok=True)
            record.update(action="excluded_without_solving",reason=str(error)[:150])
        trace.append(record)
        print("EQUIV7_SOURCE",json.dumps(record,sort_keys=True),flush=True)
        save(ROOT/"selection-progress.json",
             dict(salt=SALT,selected=len(cases),trace=trace))
    need(len(cases)==TARGET,"not forty-eight unseen source SHA")
    # Source-only deterministic SHA-disjoint cohort; actual strata are
    # reported, not forced by an outcome-dependent selection process.
    need(len({c["sha256"] for c in cases})==TARGET,"duplicate SHA")
    manifest=dict(protocol=PROTO,cases=cases,arms=list(ARMS),
        expected_trials=EXPECTED,cap_s=CAP,reps=REPS,shards=SHARDS,
        selection_salt=SALT,source_indexes=indexes,
        selection_trace=trace,year_counts=dict(years),
        binary_counts=dict(binary_classes),
        sample_policy="SHA-salted official 2021/2022/2023 main indexes, minisat1m=yes first then full-main source-only fallback; fixed 48, no solver-outcome screening",
        prior_exclusions=prior,source_only_selection=True,
        globally_blind=False,excluded_X20_and_X21=True,excluded_prior_equiv6=True,
        no_outcome_screening=True,no_auto_promotion=True,
        independent_UNSAT_LRAT=False,UNSAT_reference_agreement_required=True,
        cpu_policy="single Linux logical CPU for each arm",
        versions=versions,code_sha256=digest(__file__),
        binaries=dict(cadical173=digest(CAD),cadical301=digest(CAD3),
                      native=digest(NATIVE),kissat=digest(KISSAT)),
        route_rule="reciprocal >= max(4,n//128) AND binary >= .2 to keep congruence; horn < .72 AND binary>=.1 to keep reluctant")
    save(ROOT/"manifest.json",manifest)
    verify()
    print("EQUIV7_FROZEN",json.dumps(dict(
        sources=len(cases),trials=EXPECTED,years=dict(years),
        binary_classes=dict(binary_classes),
        router_variants={str(k):v for k,v in collections.Counter(
            tuple(c["preregistered_route_args"]) for c in cases).items()})),
        flush=True)
def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         len(m["cases"])==TARGET and m["expected_trials"]==EXPECTED,
         "frozen protocol changed")
    need(m["code_sha256"]==digest(__file__),"code changed after freeze")
    need(m["binaries"]==dict(cadical173=digest(CAD),cadical301=digest(CAD3),
          native=digest(NATIVE),kissat=digest(KISSAT)),"binary drift")
    for c in m["cases"]:
        path=SOURCE/c["filename"]
        need(digest(path)==c["sha256"],"original SHA changed")
        n,cl=x22.read_cnf(path)
        need(source_signals(n,cl)==c["source_signals"],"source signals changed")
        args,dec=route(c["source_signals"])
        need(list(args)==c["preregistered_route_args"] and
             dec==c["preregistered_route_decision"],"router rule drift")
    return m

def trial(c,rep,arm,root=SOURCE,toy=False):
    need(arm in ARMS,"unregistered arm")
    src=root/c["filename"]
    need(digest(src)==c["sha256"],"source SHA")
    cpu=sorted(os.sched_getaffinity(0))[0]
    before=x22.child_cpu()
    start=time.perf_counter()
    status="TIMEOUT";witness=False;decision=None;route_args=()
    if arm in ("kissat1","native1"):
        need(not toy,"no toy on pinned Native/Kissat")
        x20.ROOT=SOURCE
        r=x20.trial(c,rep,arm)
        need(r["original_sha256"]==c["sha256"] and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "baseline SAT original witness failed")
        return dict(protocol=PROTO,arm=arm,rep=rep,gbd=c["gbd"],
            original_sha256=c["sha256"],seed=r["seed"],
            status=r["status"],E2E_s=r["elapsed_s"],
            child_CPU_s=r["child_cpu_s"],
            SAT_original_witness_verified=r["SAT_original_witness_verified"],
            UNSAT_independent_LRAT=False,cap_s=CAP,
            source_signals=c["source_signals"],route_decision=None,
            opts=[],selected_backend=arm)
    n,original=x22.read_cnf(src)
    opts=OPTIONS[arm]
    if arm in ("cadical3_route","cadical3_route_placebo"):
        features=source_signals(n,original)
        need(toy or features==c["source_signals"],"trial signal changed")
        selected,decision=route(features)
        if not toy:
            need(list(selected)==c["preregistered_route_args"],
                 "precommit mismatch")
        opts=selected if arm=="cadical3_route" else ()
        route_args=tuple(opts)
    cmd=[str(CAD3 if arm.startswith("cadical3_") else CAD),
         *opts,str(src)]
    with tempfile.TemporaryDirectory(dir=ROOT if ROOT.exists() else None) as td:
        child=x22.launch("solver",cmd,cpu,td)
        try:
            while child["p"].poll() is None and time.perf_counter()-start < CAP-.02:
                time.sleep(.006)
            if child["p"].poll() is not None:
                stdout,stderr=x22.read_output(child)
                status,witness=x22.solver_result("cadical",child["p"].returncode,
                                                 stdout,original,{})
        finally:
            x22.cleanup([child])
    elapsed=time.perf_counter()-start
    if elapsed>=CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"SAT source-witness not verified")
    return dict(protocol=PROTO,arm=arm,rep=rep,gbd=c["gbd"],
        original_sha256=c["sha256"],seed=seed(c,rep),
        status=status,E2E_s=round(elapsed,6),
        child_CPU_s=round(x22.child_cpu()-before,6),
        SAT_original_witness_verified=witness,
        UNSAT_independent_LRAT=False,cap_s=CAP,
        source_signals=c["source_signals"],route_decision=decision,
        opts=list(opts),selected_backend="cadical3" if arm.startswith("cadical3_") else "cadical173")

def selftest():
    check_options()
    ROOT.mkdir(exist_ok=True)
    src="p cnf 3 4\n-1 2 0\n1 -2 0\n-2 3 0\n2 -3 0\n"
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"toy.cnf";p.write_text(src)
        n,cl=x22.read_cnf(p);features=source_signals(n,cl)
        c=dict(filename=p.name,sha256=digest(p),gbd="toy",source_signals=features)
        for arm in ARMS:
            if arm in ("native1","kissat1"):continue
            r=trial(c,0,arm,root=pathlib.Path(td),toy=True)
            need(r["status"]=="SAT" and
                 r["SAT_original_witness_verified"],"toy model "+arm)
        opt,decision=route(features)
        need(isinstance(decision["congruence"],bool) and isinstance(opt,tuple),
             "toy routing logic invalid")
    print("EQUIV7_SELFTEST_PASS",len(ARMS)-2,flush=True)

def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,"invalid shard")
    selected=m["cases"][idx::SHARDS]
    need(len(selected)==TARGET//SHARDS,"shard imbalance")
    rows=[]
    for c in selected:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(seed(c,rep)).shuffle(arms)
            for arm in arms:
                r=trial(c,rep,arm)
                rows.append(r)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("EQUIV7_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(selected)*REPS*len(ARMS),"incomplete shard")
    print("EQUIV7_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for idx in range(SHARDS):
        p=ROOT/("shard-%d.json"%idx)
        r=json.loads(p.read_text())
        need(len(r)==TARGET//SHARDS*REPS*len(ARMS),"missing shard")
        rows+=r
    need(len(rows)==EXPECTED,"incomplete trials")
    cases={c["sha256"]:c for c in m["cases"]}
    keys={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    expected={(sha,rep,arm) for sha in cases for rep in range(REPS)
              for arm in ARMS}
    need(len(keys)==len(rows)==len(expected) and keys==expected,
         "missing/duplicate or unexpected trial keys")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP,"trial protocol drift")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid outcome")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "unverified SAT")
        need(r["source_signals"]==cases[r["original_sha256"]]["source_signals"],
             "source features mutated")
        bysha[r["original_sha256"]].append(r)
    consensus=set()
    for sha,rs in bysha.items():
        verdicts={r["status"] for r in rs if r["status"]!="TIMEOUT"}
        need(len(verdicts)<=1,"SAT/UNSAT disagreement on original SHA "+sha)
        k=any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rs)
        c=any(r["arm"] in ("cadical_default","cadical3_default") and
              r["status"]=="UNSAT" for r in rs)
        if k and c:consensus.add(sha)
    def ok(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and
                                      r["original_sha256"] in consensus)
    scores={}
    for arm in ARMS:
        group=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(
            n=len(group),solved=sum(ok(r) for r in group),
            SAT_verified=sum(r["status"]=="SAT" for r in group),
            UNSAT_original_backend_agreement_no_LRAT=sum(r["status"]=="UNSAT" and ok(r)
                                                           for r in group),
            UNSAT_unconfirmed=sum(r["status"]=="UNSAT" and not ok(r) for r in group),
            PAR2_s=round(sum(r["E2E_s"] if ok(r) else 2*CAP for r in group),6),
            CPU_PAR2_s=round(sum(r["child_CPU_s"] if ok(r) else 2*CAP
                                 for r in group),6),
            actual_child_CPU_s=round(sum(r["child_CPU_s"] for r in group),6))
    baseline=scores["cadical3_default"]["PAR2_s"]
    for x in scores.values():
        x["delta_PAR2_pct_vs_cadical3_default"]=round(
                100*(x["PAR2_s"]/baseline-1),5)
    # SHA-paired per-source PAR2 comparison; 0.05s tie window
    # guards against over-interpreting tiny scheduling differences.
    paired={}
    for reference in ("cadical3_default","cadical3_both","cadical_default","kissat1"):
        wins=losses=ties=0
        for sha,rs in bysha.items():
            route_s=sum(r["E2E_s"] if ok(r) else 2*CAP for r in rs
                        if r["arm"]=="cadical3_route")
            ref_s=sum(r["E2E_s"] if ok(r) else 2*CAP for r in rs
                      if r["arm"]==reference)
            if route_s+0.05<ref_s:wins+=1
            elif ref_s+0.05<route_s:losses+=1
            else:ties+=1
        need(wins+losses+ties==TARGET,"incomplete paired source audit")
        paired[reference]=dict(route_wins=wins,reference_wins=losses,
                               ties=ties,per_source_tie_s=0.05,
                               PAR2_ratio=round(scores[reference]["PAR2_s"]/
                                                scores["cadical3_route"]["PAR2_s"],5))
    per_sha={sha:dict(gbd=cases[sha]["gbd"],
         signals=cases[sha]["source_signals"],
         route_args=cases[sha]["preregistered_route_args"],
         per_arm={arm:dict(statuses=[r["status"] for r in rs if r["arm"]==arm],
                           E2E_s=[r["E2E_s"] for r in rs if r["arm"]==arm])
                  for arm in ARMS}) for sha,rs in bysha.items()}
    report=dict(protocol=PROTO,source_only_new=True,global_history_exhaustive=False,
        excluded_prior_equiv6=True,
        sources=TARGET,trials=EXPECTED,reps=REPS,cap_s=CAP,
        certified_UNSAT_LRAT=False,consensus_original_SHA=sorted(consensus),
        no_auto_promotion=True,scores=scores,paired_sources=paired,
        source_classes=dict(m["binary_counts"]),year_counts=m["year_counts"],
        routing=collections.Counter(tuple(c["preregistered_route_args"]) for c in m["cases"]),
        per_sha=per_sha)
    report["routing"]={str(k):v for k,v in report["routing"].items()}
    save(ROOT/"report.json",report)
    print("EQUIV7_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="shard":shard(args.shard)
    else:
        globals()[args.action]()
        if args.action=="verify":print("EQUIV7_VERIFY_PASS",flush=True)
