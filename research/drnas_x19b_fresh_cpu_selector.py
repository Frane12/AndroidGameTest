#!/usr/bin/env python3
"""DRNAS X19B — source-only prospective SAT checks for X18 versus X16A CPU sharing.

Eight new source-only official SAT 2021-23 GBD original CNFs, disjoint from
X18's 24 originals, X6 fresh8, and prior XX2R 10 GBD IDs.  No solver run
or timing is used to select cases. Historical global exclusions incomplete.
All arms receive identical original SHA and source-paired seeds.
8 original CNFs x 2 seeds x 8 arms = 128 *real E2E* trials (12s cap).
Bounded-CDCL 5000-conflict probes are separate and never counted as solves.
No stable-code modifications, no auto-promotion, no independent UNSAT LRAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random

import drnas_x18_selective as x18
import drnas_x16a_asymmetric_timeshare as x16a
import mre7_extended_easy_freeze as pool
import mre7_reference_easy_freeze as fetch
import mre_x2_clause_order_causal as x2

ROOT=pathlib.Path("mre_x19b")
X18F=pathlib.Path("mre_x18")
X6F=pathlib.Path("x19b_x6_exclusion/manifest.json")
PROTO="DRNAS-X19B-FRESH-SOURCE-SELECTIVE-SHARE80-SHARE50-8SHA-2REP-8ARM-12S-PAR2-v1"
ARMS=("native1","kissat1","cadical1","placebo2","asym2","select2",
      "share80_1","share50_1")
TWO_CPU=("placebo2","asym2","select2")
CAP=12.0
REPS=2
SOURCES=8
SHARDS=8
EXPECTED=SOURCES*REPS*len(ARMS)
SALT="DRNAS-X19B-SOURCE-ONLY-PROTOCOL-20261109-v1"
# These 10 GBD source IDs were already used in XX2R:
XX2R_OLD_GBD={
 "587150fb7b12a6b5dd7e4a9446b9713b",
 "70af2c3bfd44bcf9baa2a9605f4a17fe",
 "44b249f51321a2bf38f730534b781bec",
 "92387c29e87aa857e84feb301f3d6aff",
 "909f704d5f4127c1197a086705468624",
 "3fb297f59ad2dc32fd3f79d61951d8cb",
 "911cbc796d15eb316d36c82c90fd7d11",
 "e9b4369f9a98e397ac69eb7740ffef49",
 "037c423f56548082b1935e88c48ffdda",
 "44092fcc83a5cba81419e82cfd18602c",
}

def need(v,why):
    if not v:
        raise RuntimeError("DRNAS_X19B_FAIL_CLOSED "+str(why))

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for data in iter(lambda:f.read(1<<20),b""):
            h.update(data)
    return h.hexdigest()

def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def configure():
    # Preserve exact source-only CNF; re-point ONLY the frozen experimental drivers.
    x18.ROOT=ROOT
    x18.DRIVER=ROOT/"bin"/"selective"
    x18.configure()
    x16a.ROOT=ROOT
    x16a.SOURCE=ROOT

def old_cases():
    x18manifest=json.loads((X18F/"manifest.json").read_text())
    need(len(x18manifest["cases"])==24 and
         x18manifest["protocol"].startswith("DRNAS-X18-"),
         "X18 source baseline missing")
    x6=json.loads(X6F.read_text())
    need(len(x6["cases"])==8,"X6 fresh exclusion missing")
    excluded_gbd={c["gbd"] for c in x18manifest["cases"]}|{
        c["gbd"] for c in x6["cases"]}|XX2R_OLD_GBD
    excluded_sha={c["sha256"] for c in x18manifest["cases"]}|{
        c["sha256"] for c in x6["cases"]}
    return x18manifest,excluded_gbd,excluded_sha

def freeze():
    configure()
    ROOT.mkdir(exist_ok=True)
    old,used_ids,used_sha=old_cases()
    need(x18.DRIVER.is_file() and sha(x18.DRIVER)==old["driver_sha256"],
         "X18 selective driver not pinned")
    need(x18.x16.binaries()==old["backend_sha256"],
         "native/Kissat backend binary SHA drift")
    # GitHub Actions job contains 2 CPUs and the same original-CNF runtime.
    need(len(x18.x16.topology()["allowed"])>=2,"runner CPU topology inadequate")
    candidates=[]
    indexes={}
    for year in ("2021","2022","2023"):
        ids,all_digest=pool.getids("track=main_"+year)
        easy,easy_digest=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(ids)==400 and set(easy).issubset(set(ids)),
             "official SAT source registry not valid "+year)
        candidates.extend((year,gbd) for gbd in easy if gbd not in used_ids)
        indexes[year]=dict(main_sha256=all_digest,metadata_sha256=easy_digest)
    candidates=sorted(set(candidates),
        key=lambda x:hashlib.sha256((SALT+"|"+x[0]+"|"+x[1]).encode()).hexdigest())
    selected=[]
    trace=[]
    for year,gbd in candidates:
        if len(selected)==SOURCES:break
        need(len(trace)<110,"source-only fetch budget exceeded; fail closed")
        row=dict(gbd=gbd,year=year,selected=False)
        dst=ROOT/(gbd+".cnf")
        try:
            packed=fetch.get("https://benchmark-database.de/file/"+gbd,
                             12*1024*1024,seconds=23)
            plain,compression=fetch.prior.r32p.decode(packed)
            need(len(plain)<=12*1024*1024,"decompressed source too large")
            nv,nc=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0<nv<=12000 and 0<nc<=85000,"source geometry cap")
            checksum=hashlib.sha256(plain).hexdigest()
            need(checksum not in used_sha,"source SHA reused in previous cohort")
            dst.write_bytes(plain)
            n,clauses=x2.parse(dst)
            need(n==nv and len(clauses)==nc,"CNF geometry parse mismatch")
            entry=dict(gbd=gbd,sha256=checksum,filename=dst.name,
                       cohort="x19b_new_sourceonly_official_not_global_blind",
                       year=year,vars=n,clauses=nc,bytes=len(plain),
                       previous_X15_tier="new_sourceonly")
            selected.append(entry)
            used_ids.add(gbd)
            used_sha.add(checksum)
            row.update(selected=True,sha256=checksum,vars=n,clauses=nc)
        except Exception as e:
            dst.unlink(missing_ok=True)
            row["reason"]=(type(e).__name__+": "+str(e))[:180]
        trace.append(row)
        print("X19B_SOURCE",json.dumps(row,sort_keys=True),flush=True)
        save(ROOT/"source-selection-progress.json",dict(
             selected_count=len(selected),trace=trace,indexes=indexes))
    need(len(selected)==SOURCES and
         len({r["gbd"] for r in selected})==SOURCES and
         len({r["sha256"] for r in selected})==SOURCES,
         "not eight unique original SHA from source-only official registry")
    m=dict(protocol=PROTO,source_count=SOURCES,expected_trials=EXPECTED,
       arms=list(ARMS),source_years=["2021","2022","2023"],
       source_only_precommitted_salt=SALT,sources_selected_by_solver_outcomes=False,
       source_only_metadata="minisat1m=yes, no outcome runtime screen",
       source_reused_prior_X18_X6_XX2R=False,global_historical_exclusions_incomplete=True,
       not_globally_blind=True,
       source_exclusion_X18_manifest_sha256=sha(X18F/"manifest.json"),
       source_exclusion_X6_manifest_sha256=sha(X6F),
       source_selection_trace=trace,official_source_index_hashes=indexes,
       cap_s=CAP,reps=REPS,shards=SHARDS,
       driver_sha256=sha(x18.DRIVER),backend_sha256=x18.x16.binaries(),
       identical_original_sha_seed_pairing=True,
       single_cpu_share_native_pct=80,control_share_pct=50,
       two_logical_cpu_arms=list(TWO_CPU),
       native_bounded_probes_diagnostic_only=True,
       UNSAT_independent_LRAT=False,
       accepted_unsat_requires_cross_solver_agreement=True,
       no_auto_promotion=True,cases=selected)
    save(ROOT/"manifest.json",m)
    verify()
    print("X19B_FROZEN",json.dumps(dict(sources=SOURCES,trials=EXPECTED,
          driver_sha256=m["driver_sha256"],manifest_sha256=sha(ROOT/"manifest.json")),
          sort_keys=True),flush=True)

def verify():
    configure()
    m=json.loads((ROOT/"manifest.json").read_text())
    old,old_ids,old_sha=old_cases()
    need(m["protocol"]==PROTO and m["expected_trials"]==EXPECTED and
         m["source_count"]==SOURCES and m["arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["reps"]==REPS,
         "precommitted prospective protocol changed")
    need(sha(x18.DRIVER)==m["driver_sha256"]==old["driver_sha256"],
         "experimental driver SHA mismatch")
    need(x18.x16.binaries()==m["backend_sha256"]==old["backend_sha256"],
         "pinned backend SHA mismatch")
    need(sha(X18F/"manifest.json")==m["source_exclusion_X18_manifest_sha256"] and
         sha(X6F)==m["source_exclusion_X6_manifest_sha256"],
         "historical exclusion registry drift")
    need(len(m["cases"])==SOURCES,"source count changed")
    for c in m["cases"]:
        p=ROOT/c["filename"]
        need(p.is_file() and sha(p)==c["sha256"] and
             c["gbd"] not in old_ids and c["sha256"] not in old_sha and
             p.stat().st_size==c["bytes"],"source SHA overlapping or missing")
    return m

def trial(c,rep,arm):
    need(arm in ARMS and rep in range(REPS),"not a precommitted strategy")
    configure()
    if arm in ("share80_1","share50_1"):
        native_arm="asym" if arm=="share80_1" else "balanced50"
        row=x16a.run_trial(c,rep,native_arm,80)
        row["arm"]=arm
        row["share_original_arm"]=native_arm
        row["original_sha256"]=c["sha256"]
    elif arm in ("native1","kissat1"):
        row=x18.baseline(c,rep,arm)
    else:
        row=x18.run_driver(c,rep,arm)
    need(row["original_sha256"]==c["sha256"] and
         row["seed"]==x18.seed(c,rep) and
         row["status"] in ("SAT","UNSAT","TIMEOUT"),
         "paired original SHA/seed/status mismatch")
    need(row["status"]!="SAT" or row["SAT_original_witness_verified"],
         "SAT original witness not checked")
    need(row["PAR2_s"]==2*CAP if row["status"]=="TIMEOUT"
         else 0<=row["PAR2_s"]<=CAP,
         "bad end to end PAR2 cap")
    row.update(protocol=PROTO,cohort=c["cohort"],rep=rep,arm=arm,
         experimental_not_globally_blind=True)
    return row

def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,"shard outside frozen grid")
    c=m["cases"][idx]
    rows=[]
    probes=[]
    probe=x18.native_probe(c)
    need(probe["diagnostic_only"] and probe["conflict_cap"]==5000,
         "bounded native probe accidentally scored as E2E")
    probes.append(probe)
    print("X19B_DIAGNOSTIC_ONLY",json.dumps(probe,sort_keys=True),flush=True)
    for rep in range(REPS):
        order=list(ARMS)
        random.Random(x18.seed(c,rep)).shuffle(order)
        for arm in order:
            row=trial(c,rep,arm)
            rows.append(row)
            save(ROOT/f"shard-{idx}.json",dict(trials=rows,probes=probes))
            print("X19B_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(ARMS),"incomplete fixed source shard")
    print("X19B_SHARD_PASS",idx,len(rows),len(probes),flush=True)

def audit():
    m=verify()
    rows=[]
    probes=[]
    cases={c["sha256"]:c for c in m["cases"]}
    for i in range(SHARDS):
        data=json.loads((ROOT/f"shard-{i}.json").read_text())
        rows+=data["trials"]
        probes+=data["probes"]
    need(len(rows)==EXPECTED and len(probes)==SOURCES,"lost trials or diagnostics")
    seen=set()
    for r in rows:
        key=(r["original_sha256"],r["rep"],r["arm"])
        need(key not in seen and key[0] in cases and
             r["seed"]==x18.seed(cases[key[0]],r["rep"]) and
             r["arm"] in ARMS and r["protocol"]==PROTO,
             "source arm seed duplicate or drift")
        seen.add(key)
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "original SAT model not validated")
        need(r["PAR2_s"]==2*CAP if r["status"]=="TIMEOUT"
             else 0<=r["PAR2_s"]<=CAP,
             "PAR2 elapsed outside capped run")
    need(all(p["diagnostic_only"] for p in probes),
         "bounded probes cannot count as solves")
    # Only cross-solver confirmed UNSAT can enter research score. No LRAT.
    accepted=[]
    for c in m["cases"]:
        rr=[r for r in rows if r["original_sha256"]==c["sha256"]]
        statuses={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT UNSAT contradiction across matched original CNF")
        ref_k=any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr)
        ref_c=any(r["arm"]=="cadical1" and r["status"]=="UNSAT" for r in rr)
        for r in rr:
            r["accepted_solved"]=(r["status"]=="SAT" or
                r["status"]=="UNSAT" and ref_k and ref_c)
            r["audited_PAR2_s"]=(
                r["PAR2_s"] if r["accepted_solved"] else 2*CAP)
            accepted.append(r)
    scores={}
    for arm in ARMS:
        rr=[r for r in accepted if r["arm"]==arm]
        budget=2 if arm in TWO_CPU else 1
        scores[arm]=dict(n=len(rr),solved=sum(r["accepted_solved"] for r in rr),
            SAT_original_verified=sum(r["accepted_solved"] and r["status"]=="SAT"
                                       for r in rr),
            UNSAT_cross_solver_agreement_no_LRAT=sum(
                r["accepted_solved"] and r["status"]=="UNSAT" for r in rr),
            timeouts=sum(r["status"]=="TIMEOUT" for r in rr),
            PAR2_s=round(sum(r["audited_PAR2_s"] for r in rr),6),
            raw_PAR2_s=round(sum(r["PAR2_s"] for r in rr),6),
            child_cpu_s=round(sum(r["child_cpu_s"] for r in rr),6),
            CPU_budget_PAR2_s=round(sum(
                r["child_cpu_s"] if r["accepted_solved"] else
                2*CAP*budget for r in rr),6),
            allocated_logical_CPU_budget=budget,
            driver_penalty_included=True)
    for arm in ARMS:
        scores[arm]["speedup_vs_native1"]=round(
             scores["native1"]["PAR2_s"]/max(scores[arm]["PAR2_s"],1e-9),6)
        scores[arm]["speedup_vs_kissat1"]=round(
             scores["kissat1"]["PAR2_s"]/max(scores[arm]["PAR2_s"],1e-9),6)
    report=dict(protocol=PROTO,sources=SOURCES,trials=EXPECTED,cap_s=CAP,
       score=scores,not_globally_blind=True,registry_disjoint_only=True,
       true_fresh_source_only_without_solver_time_screen=True,
       original_SHA_and_seed_paired=True,
       UNSAT_independent_LRAT=False, no_auto_promotion=True,
       native_bounded_probes_not_PAR2=True,
       CPU_budget_PAR2_separate_from_wall=True,
       limited_to_declared_exclusion_registries=True,
       per_source=[dict(gbd=c["gbd"],sha256=c["sha256"],
            year=c["year"],outcomes=[
                dict(arm=r["arm"],rep=r["rep"],status=r["status"],
                     PAR2_s=r["audited_PAR2_s"],
                     child_cpu_s=r["child_cpu_s"])
                for r in accepted if r["original_sha256"]==c["sha256"]])
                for c in m["cases"]])
    save(ROOT/"report.json",report)
    print("X19B_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
          sort_keys=True),flush=True)

def selftest():
    need(SOURCES==8 and EXPECTED==128 and len(ARMS)==8
         and len(TWO_CPU)==3,"X19B grid changed")
    configure()
    need(x18.DRIVER.is_file() and
         len(x18.x16.topology()["allowed"])>=2,
         "X19B native selective binary or runner CPU missing")
    x18.selftest()
    print("X19B_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="freeze":freeze()
    elif args.action=="verify":verify();print("X19B_VERIFY_PASS",flush=True)
    elif args.action=="shard":shard(args.shard)
    else:audit()

if __name__=="__main__":
    main()
