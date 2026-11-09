#!/usr/bin/env python3
"""DRNAS SEED1: source-frozen independent cohort and deterministic native seed diversification.

Original SAT witness is checked against complete original CNF.
UNSAT is counted only on original-input cross-solver agreement (Kissat + CaDiCaL 3).
No adaptive fitting, no result-conditioned source selection, no auto promotion.
24 official original SHA, disjoint from recorded X20/X21/EQUIV6/EQUIV7.
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

import drnas_x22_parallel_reducer as x22
import drnas_x16_singlecore_dual as x16
import drnas_x14_adaptive_portfolio as x14

ROOT=pathlib.Path("mre_seed1")
CASES=ROOT/"cases"
NATIVE=pathlib.Path("mre_x4/bin/native")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CAD=ROOT/"bin/cadical_3_0_1"
PROTO="DRNAS-SEED1-24NEW-7ARMS-2REPS-20S-SHA-E2E-PAR2-v1"
SALT="DRNAS-SEED1-20261109-FRESH-SOURCEONLY-FREEZE-v1"
ARMS=("native_a","native_b","native_restart_b3","native_ab_2cpu",
      "native_aa_2cpu_placebo","kissat_a","cadical3_both")
N=24
REPS=2
SHARDS=8
CAP=20.0
SWITCH=3.0
EXPECTED=N*REPS*len(ARMS)

def need(ok,reason):
    if not ok:raise RuntimeError("SEED1_FAIL_CLOSED "+str(reason))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):h.update(part)
    return h.hexdigest()
def save(path,value):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def seeds(case,rep):
    sha=case["sha256"]
    a=int(hashlib.sha256(("SEED1|A|"+sha+"|"+str(rep)).encode()).hexdigest()[:7],16)
    b=int(hashlib.sha256(("SEED1|B|"+sha+"|"+str(rep)).encode()).hexdigest()[:7],16)
    need(a!=b and 0<=a<=268435455 and 0<=b<=268435455,"seed collision or range")
    return a,b
def options():
    for p in (NATIVE,KISSAT,CAD):
        need(p.is_file(),"missing pinned binary "+str(p))
    return {"native":digest(NATIVE),"kissat":digest(KISSAT),"cadical301":digest(CAD)}
def exclude():
    sources={
       "X20":pathlib.Path("mre_x20/manifest.json"),
       "X21":pathlib.Path("prior_x22/mre_x22/manifest.json"),
       "EQUIV6":pathlib.Path("prior_equiv6/mre_equiv6/manifest.json"),
       "EQUIV7":pathlib.Path("mre_equiv7/manifest.json")}
    ids=set();sha=set();checks={}
    for name,path in sources.items():
        m=json.loads(path.read_text())
        expected={"X20":24,"X21":24,"EQUIV6":16,"EQUIV7":48}[name]
        need(len(m["cases"])==expected,"prior source count drift "+name)
        checks[name]=dict(manifest_sha256=digest(path),count=expected)
        for c in m["cases"]:
            ids.add(c["gbd"]);sha.add(c["sha256"])
    need(len(sha)>=48,"prior SHA registry implausible")
    return ids,sha,checks
def freeze():
    ROOT.mkdir(exist_ok=True);CASES.mkdir(exist_ok=True)
    binaries=options()
    exclude_ids,exclude_sha,prior=exclude()
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as downloader
    indexes={};candidates=[]
    for year in ("2021","2022","2023"):
        all_ids,all_sha=pool.getids("track=main_"+year)
        easy,easy_sha=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(all_ids)==400 and set(easy)<=set(all_ids),"official index changed "+year)
        indexes[year]=dict(main_sha256=all_sha,easy_sha256=easy_sha,
                           easy_sources=len(easy))
        e=set(easy)
        candidates.extend((0,year,g) for g in easy if g not in exclude_ids)
        candidates.extend((1,year,g) for g in all_ids
                          if g not in e and g not in exclude_ids)
    candidates.sort(key=lambda t:(t[0],hashlib.sha256(
        (SALT+"|"+t[1]+"|"+t[2]).encode()).hexdigest()))
    selected=[];records=[];seen=set()
    for tier,year,gbd in candidates:
        if len(selected)>=N:break
        if gbd in seen:continue
        seen.add(gbd)
        need(len(seen)<=1100,"source-only scan budget exhausted")
        p=CASES/(gbd+".cnf")
        record=dict(gbd=gbd,year=year,tier="minisat1m_yes" if tier==0 else "full_main")
        try:
            raw=downloader.get("https://benchmark-database.de/file/"+gbd,
                               12*1024*1024,seconds=20)
            data,_=downloader.prior.r32p.decode(raw)
            need(len(data)<=12*1024*1024,"source byte cap")
            n,k=downloader.prior.r32p.parse_dimacs_metadata(data)
            need(0<n<=12000 and 0<k<=85000,"source geometry cap")
            sha=hashlib.sha256(data).hexdigest()
            need(sha not in exclude_sha,"historical original SHA")
            p.write_bytes(data)
            var,clauses=x22.read_cnf(p)
            need(var==n and len(clauses)==k,"DIMACS parsed geometry drift")
            binary=sum(len(c)==2 for c in clauses)
            horn=sum(sum(lit>0 for lit in c)<=1 for c in clauses)
            obj=dict(gbd=gbd,filename=p.name,sha256=sha,year=year,
                     source_index_tier=record["tier"],vars=n,clauses=k,
                     binary_ratio=round(binary/k,6),horn_ratio=round(horn/k,6),
                     bytes=len(data))
            selected.append(obj)
            exclude_sha.add(sha)
            record.update(action="frozen_source_only",sha256=sha)
        except Exception as e:
            p.unlink(missing_ok=True)
            record.update(action="skipped_without_solving",reason=str(e)[:170])
        records.append(record)
        print("SEED1_SOURCE",json.dumps(record,sort_keys=True),flush=True)
        save(ROOT/"selection-progress.json",
             dict(salt=SALT,selected=len(selected),trace=records))
    need(len(selected)==N,"fewer than 24 disjoint original SHA")
    need(len({c["sha256"] for c in selected})==N,"SHA collision")
    manifest=dict(protocol=PROTO,cases=selected,arms=ARMS,cap_s=CAP,
        switch_s=SWITCH,reps=REPS,shards=SHARDS,expected_trials=EXPECTED,
        no_outcome_selection=True,source_only_selection=True,
        historical_disjoint_cohorts=list(prior),prior_manifests=prior,
        source_indexes=indexes,selection_salt=SALT,selection_trace=records,
        global_history_exhaustive=False,not_globally_blind=True,
        no_auto_promotion=True,original_SHA_verified=True,
        UNSAT_independent_LRAT=False,
        UNSAT_requires_Kissat_CaDiCaL_original_agreement=True,
        one_cpu_arms=[a for a in ARMS if "_2cpu" not in a],
        two_cpu_arms=[a for a in ARMS if "_2cpu" in a],
        seeds="SHA salted two independent 28-bit nonnegative seeds per source/rep; no outcome tuning",
        seed_policy_frozen_before_any_trial=True,
        cpu_affinity="one pinned logical CPU per child, two for simultaneous arms",
        code_sha256=digest(__file__),binary_sha256=binaries)
    save(ROOT/"manifest.json",manifest)
    verify()
    print("SEED1_FROZEN",json.dumps(dict(sources=N,trials=EXPECTED,
            years=dict(collections.Counter(c["year"] for c in selected)),
            source_tiers=dict(collections.Counter(c["source_index_tier"] for c in selected))),sort_keys=True),flush=True)
def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["cases"])==N and
         m["expected_trials"]==EXPECTED and m["arms"]==list(ARMS),
         "frozen protocol mismatch")
    need(m["code_sha256"]==digest(__file__),"code modified after freeze")
    need(m["binary_sha256"]==options(),"binary modified after freeze")
    for c in m["cases"]:
        p=CASES/c["filename"]
        need(digest(p)==c["sha256"],"original SHA changed")
        need(seeds(c,0)!=seeds(c,1),"rep seed pairs identical")
    return m
def selftest():
    options()
    test=dict(sha256="f"*64)
    need(len(set(seeds(test,0)+seeds(test,1)))==4,"seed generator collision")
    need(CAP>SWITCH and N%SHARDS==0,"bad experimental matrix")
    print("SEED1_SELFTEST_PASS",json.dumps(dict(arms=ARMS,
         trials=EXPECTED,cap_s=CAP,switch_s=SWITCH)),flush=True)
def _execute(case,rep,arm):
    original_path=CASES/case["filename"]
    need(digest(original_path)==case["sha256"],"source SHA")
    available=sorted(os.sched_getaffinity(0))
    need(len(available)>=2,"two logical CPUs unavailable")
    cpus=available[:2]
    a,b=seeds(case,rep)
    begin=time.perf_counter();before_cpu=x22.child_cpu()
    _,original_clauses=x22.read_cnf(original_path)
    status="TIMEOUT";verified=False;winner=None
    entries=[];phase2=False
    def launch(label,backend,seed,cpu,td):
        if backend=="native":
            cmd=x16.command("native",original_path,seed)
        elif backend=="kissat":
            cmd=x16.command("kissat",original_path,seed)
        else:
            cmd=[str(CAD),"--no-congruence","--no-reluctant",str(original_path)]
        z=x22.launch(label,cmd,cpu,td)
        z["backend"]=backend;z["seed"]=seed;z["consumed"]=False
        return z
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        try:
            if arm=="native_a":
                entries=[launch("na","native",a,cpus[0],td)]
            elif arm=="native_b":
                entries=[launch("nb","native",b,cpus[0],td)]
            elif arm=="native_restart_b3":
                entries=[launch("probe","native",a,cpus[0],td)]
            elif arm=="native_ab_2cpu":
                entries=[launch("pa","native",a,cpus[0],td),
                         launch("pb","native",b,cpus[1],td)]
            elif arm=="native_aa_2cpu_placebo":
                entries=[launch("xa","native",a,cpus[0],td),
                         launch("xb","native",a,cpus[1],td)]
            elif arm=="kissat_a":
                entries=[launch("k","kissat",a,cpus[0],td)]
            elif arm=="cadical3_both":
                entries=[launch("c","cadical",a,cpus[0],td)]
            else:need(False,"unknown arm")
            while time.perf_counter()-begin<CAP-.02:
                for child in entries:
                    if child["consumed"] or child["p"].poll() is None:continue
                    child["consumed"]=True
                    stdout,stderr=x22.read_output(child)
                    backend=child["backend"]
                    if backend in ("native","kissat"):
                        st=x14.outcome_of(backend,child["p"].returncode,
                                         stdout,stderr,original_path)
                        wit=(st=="SAT")
                    else:
                        st,wit=x22.solver_result("cadical",child["p"].returncode,
                                                stdout,original_clauses,{})
                    if st in ("SAT","UNSAT"):
                        status=st;verified=wit;winner=child["seed"]
                        break
                if status in ("SAT","UNSAT"):break
                if arm=="native_restart_b3" and not phase2 and (
                    time.perf_counter()-begin>=SWITCH or all(x["consumed"] for x in entries)):
                    x22.cleanup(entries)
                    entries=[];phase2=True
                    if time.perf_counter()-begin<CAP-.1:
                        entries=[launch("restart","native",b,cpus[0],td)]
                if all(x["consumed"] for x in entries):break
                time.sleep(.005)
        finally:
            x22.cleanup(entries)
    elapsed=time.perf_counter()-begin
    if elapsed>=CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False;winner=None
    need(status!="SAT" or verified,"unverified original-SHA SAT witness")
    return dict(protocol=PROTO,arm=arm,rep=rep,gbd=case["gbd"],
        original_sha256=case["sha256"],status=status,
        SAT_original_witness_verified=verified,UNSAT_independent_LRAT=False,
        E2E_s=round(elapsed,6),child_CPU_s=round(x22.child_cpu()-before_cpu,6),
        seed_a=a,seed_b=b,winning_seed=winner,cap_s=CAP,
        logical_cpu_budget=(2 if "_2cpu" in arm else 1),
        pinned_cpus=cpus[:(2 if "_2cpu" in arm else 1)],
        switched_to_b=phase2,
        original_CNF_not_transformed=True)
def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,"invalid shard")
    subset=m["cases"][idx::SHARDS]
    need(len(subset)==N//SHARDS,"uneven shard")
    rows=[]
    for c in subset:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(seeds(c,rep)[0]).shuffle(arms)
            for arm in arms:
                r=_execute(c,rep,arm)
                rows.append(r)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("SEED1_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==N//SHARDS*REPS*len(ARMS),"incomplete shard")
    print("SEED1_SHARD_PASS",idx,len(rows),flush=True)
def audit():
    m=verify();rows=[]
    for idx in range(SHARDS):
        p=ROOT/("shard-%d.json"%idx)
        a=json.loads(p.read_text())
        need(len(a)==N//SHARDS*REPS*len(ARMS),"missing shard rows")
        rows.extend(a)
    bysha={c["sha256"]:c for c in m["cases"]}
    observed={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    need(len(rows)==EXPECTED and len(observed)==EXPECTED and observed==expected,
         "missing/duplicated/mismatched source-rep-arm")
    groups=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP,"trial protocol mismatch")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "SAT original witness not verified")
        need(r["original_sha256"] in bysha,"unknown source")
        need((r["seed_a"],r["seed_b"])==seeds(
             bysha[r["original_sha256"]],r["rep"]),"seed mutation")
        need(r["logical_cpu_budget"]==(2 if "_2cpu" in r["arm"] else 1),
             "CPU accounting drift")
        groups[r["original_sha256"]].append(r)
    consensus=set()
    for sha,rr in groups.items():
        values={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(values)<=1,"SAT/UNSAT contradiction on original SHA "+sha)
        kissat=any(r["arm"]=="kissat_a" and r["status"]=="UNSAT" for r in rr)
        cadical=any(r["arm"]=="cadical3_both" and r["status"]=="UNSAT" for r in rr)
        if kissat and cadical:consensus.add(sha)
    def good(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and
                                      r["original_sha256"] in consensus)
    scores={}
    for arm in ARMS:
        group=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(attempts=len(group),solved=sum(good(r) for r in group),
          SAT_verified=sum(r["status"]=="SAT" for r in group),
          UNSAT_backend_agreement_no_LRAT=sum(r["status"]=="UNSAT" and good(r) for r in group),
          UNSAT_unconfirmed=sum(r["status"]=="UNSAT" and not good(r) for r in group),
          PAR2_s=round(sum(r["E2E_s"] if good(r) else 2*CAP for r in group),6),
          CPU_PAR2_s=round(sum(r["child_CPU_s"] if good(r) else
                               2*CAP*r["logical_cpu_budget"] for r in group),6),
          actual_child_CPU_s=round(sum(r["child_CPU_s"] for r in group),6),
          logical_cpu_budget=(2 if "_2cpu" in arm else 1))
    baseline=scores["native_a"]
    for v in scores.values():
        v["PAR2_pct_lower_vs_native_a"]=round(100*(1-v["PAR2_s"]/baseline["PAR2_s"]),4)
        v["CPU_PAR2_pct_lower_vs_native_a"]=round(
            100*(1-v["CPU_PAR2_s"]/baseline["CPU_PAR2_s"]),4)
    paired={}
    for arm in ARMS:
        if arm=="native_a":continue
        wins=losses=ties=0
        for sha,group in groups.items():
            a=sum(r["E2E_s"] if good(r) else 2*CAP for r in group if r["arm"]=="native_a")
            b=sum(r["E2E_s"] if good(r) else 2*CAP for r in group if r["arm"]==arm)
            if b<a-.1:wins+=1
            elif a<b-.1:losses+=1
            else:ties+=1
        paired[arm]=dict(wins_vs_native_a=wins,losses_vs_native_a=losses,ties=ties)
    report=dict(protocol=PROTO,sources=N,trials=EXPECTED,reps=REPS,cap_s=CAP,
        original_SHA_disjoint_recorded_cohorts=True,not_globally_blind=True,
        SAT_original_witness_verified_required=True,independent_UNSAT_LRAT=False,
        UNSAT_consensus_source_count=len(consensus),no_auto_promotion=True,
        scores=scores,paired=paired,
        source_years=dict(collections.Counter(c["year"] for c in m["cases"])),
        source_tiers=dict(collections.Counter(c["source_index_tier"] for c in m["cases"])),
        rows=rows)
    save(ROOT/"report.json",report)
    print("SEED1_FINAL",json.dumps({k:v for k,v in report.items() if k!="rows"},
                                   sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="shard":shard(args.shard)
    else:
        globals()[args.action]()
        if args.action=="verify":print("SEED1_VERIFY_PASS",flush=True)
