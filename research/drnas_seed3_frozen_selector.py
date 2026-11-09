#!/usr/bin/env python3
"""SEED3: truly frozen SEED2 byte-size stump on NEW source-only official SHA.

There is NO training on SEED2 outcomes and no modification of the 253335.5
byte threshold. All candidates chosen by precommitted source-only size bounds.
The benchmark runner/auditor is the reviewed SEED2 one-logical-core
implementation; this wrapper extends only cohort freeze and exact audit.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import random
import sys

import drnas_seed2_structural_selector as base
import drnas_x22_parallel_reducer as x22
import drnas_seed1_dual_seed_holdout as seed1

ROOT=pathlib.Path("mre_seed3")
SOURCE=ROOT/"cases"
PRIOR=pathlib.Path("prior_seed2/mre_seed2/manifest.json")
PROTO="DRNAS-SEED3-48NEW-FROZEN-STUMP-6ARM-2REP-20S-SHA-E2E-v1"
SALT="DRNAS-SEED3-20261109-FROZEN-SEED2-MODEL-48-SOURCEONLY-v1"
TARGET=48
REPS=2
SHARDS=8
CAP=20.0
ARMS=base.ARMS
EXPECTED=TARGET*REPS*len(ARMS)
SCAN_LIMIT=1060
MAX_VARIABLES=9000
MAX_CLAUSES=65000
MAX_BYTES=8*1024*1024
# Exact model as reported in independent, previously COMPLETED SEED2 run.
FROZEN=dict(type="stump",feature="bytes",threshold=253335.5,
            left_seed="A",right_seed="B")

def need(ok,why):
    if not ok:raise RuntimeError("SEED3_FAIL_CLOSED "+str(why))
def digest(path):
    return base.digest(path)
def save(path,value):
    return base.save(path,value)
def configure():
    base.ROOT=ROOT
    base.SOURCE=SOURCE
    base.CAD3=ROOT/"bin/cadical_3_0_1"
    base.PROTO=PROTO
    base.SALT=SALT
    base.TARGET=TARGET
    base.REPS=REPS
    base.SHARDS=SHARDS
    base.CAP=CAP
    base.EXPECTED=EXPECTED

def prior_data():
    m=json.loads(PRIOR.read_text())
    need(m["protocol"].startswith("DRNAS-SEED2-") and
         len(m["source_cases"])==24 and m["training"]["model"]==FROZEN,
         "unexpected prior model or source count")
    need(m["training"]["training_n"]==24 and
         m["training"]["source_only_classifier"] is True,
         "prior was not trained on frozen SEED1 only")
    need(m["source_count"]==24 and m["expected_trials"]==288,
         "wrong prior SEED2 manifest")
    need(m["no_outcome_conditioning_in_holdout"] is True,
         "prior not source frozen")
    return m

def excluded():
    ids,sha,old=seed1.exclude()
    old_seed1=json.loads(pathlib.Path("prior_seed1/mre_seed1/manifest.json").read_text())
    need(len(old_seed1["cases"])==24,"prior SEED1 registry")
    for c in old_seed1["cases"]:
        ids.add(c["gbd"]);sha.add(c["sha256"])
    old_seed2=prior_data()
    for c in old_seed2["source_cases"]:
        ids.add(c["gbd"]);sha.add(c["sha256"])
    need(len(sha)>=100,"historical SHA collision or incomplete exclusions")
    return ids,sha,old

def selftest():
    configure()
    base.binaries()
    m=prior_data()
    need(base.pick(FROZEN,dict(bytes=253335))=="A" and
         base.pick(FROZEN,dict(bytes=253336))=="B",
         "frozen threshold changed")
    for k in ("native_a","native_b","native_selected",
              "native_inverse_placebo","kissat_a","cadical3_both"):
        need(k in ARMS,"comparison missing: "+k)
    need(EXPECTED==576 and SHARDS==8 and CAP==20.0,
         "protocol matrix drift")
    print("SEED3_SELFTEST_PASS",json.dumps(dict(
        model=FROZEN,old_protocol=m["protocol"],
        seed_algorithm="SEED1 SHA two seeds unchanged",
        expected=EXPECTED,source_policy="fixed geometry, no source solve")),
        flush=True)

def freeze():
    configure()
    ROOT.mkdir(parents=True,exist_ok=True);SOURCE.mkdir(parents=True,exist_ok=True)
    prior=prior_data()
    binaries=base.binaries()
    excluded_ids,excluded_sha,registries=excluded()
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as downloader
    candidates=[];indexes={}
    for year in ("2021","2022","2023"):
        all_ids,main_sha=pool.getids("track=main_"+year)
        easy,easy_sha=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(all_ids)==400 and set(easy)<=set(all_ids),
             "official source index drift "+year)
        indexes[year]=dict(main_sha256=main_sha,easy_sha256=easy_sha,
                           minisat1m_index_n=len(easy))
        easy_set=set(easy)
        candidates.extend((0,year,gbd) for gbd in easy if gbd not in excluded_ids)
        candidates.extend((1,year,gbd) for gbd in all_ids
                          if gbd not in easy_set and gbd not in excluded_ids)
    candidates.sort(key=lambda t:(t[0],hashlib.sha256(
        (SALT+"|"+t[1]+"|"+t[2]).encode()).hexdigest()))
    selected=[];trace=[];seen=set()
    for tier,year,gbd in candidates:
        if len(selected)>=TARGET:break
        if gbd in seen:continue
        seen.add(gbd)
        need(len(seen)<=SCAN_LIMIT,"source-only bounded scan exhausted")
        path=SOURCE/(gbd+".cnf")
        rec=dict(year=year,gbd=gbd,source_index_tier=
                 "minisat1m_yes" if tier==0 else "full_main")
        try:
            raw=downloader.get("https://benchmark-database.de/file/"+gbd,
                               12*1024*1024,seconds=20)
            plain,_=downloader.prior.r32p.decode(raw)
            need(len(plain)<=MAX_BYTES,"smaller original byte cap")
            n,k=downloader.prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=MAX_VARIABLES and 0<k<=MAX_CLAUSES,
                 "smaller source geometry cap")
            sha=hashlib.sha256(plain).hexdigest()
            need(sha not in excluded_sha,"historical source SHA")
            path.write_bytes(plain)
            nn,clauses=x22.read_cnf(path)
            need(n==nn and k==len(clauses),"original CNF parse mismatch")
            feature=base.features(path,nn,clauses)
            need(feature["bytes"]==len(plain),"source bytes changed")
            choice=base.pick(FROZEN,feature)
            selected.append(dict(year=year,gbd=gbd,filename=path.name,
                sha256=sha,feature=feature,index_tier=tier,
                precommitted_selection=choice))
            excluded_sha.add(sha)
            rec.update(action="source_only_frozen",sha256=sha,
                       selected_seed=choice,vars=n,clauses=k,bytes=len(plain))
        except Exception as e:
            path.unlink(missing_ok=True)
            rec.update(action="source_only_skipped",reason=str(e)[:150])
        trace.append(rec)
        print("SEED3_SOURCE",json.dumps(rec,sort_keys=True),flush=True)
        save(ROOT/"selection-progress.json",dict(
             selection_salt=SALT,selected_n=len(selected),trace=trace))
    need(len(selected)==TARGET,"less than 48 disjoint smaller original CNFs")
    need(len({c["sha256"] for c in selected})==TARGET,"duplicate original SHA")
    manifest=dict(protocol=PROTO,source_cases=selected,source_count=TARGET,
        expected_trials=EXPECTED,arms=list(ARMS),reps=REPS,shards=SHARDS,
        cap_s=CAP,salt=SALT,training=dict(prior["training"]),
        source_indexes=indexes,selection_trace=trace,
        prior_exclusions=registries,excluded_prior_seed1=True,
        excluded_prior_seed2=True,excluded_X20_X21_EQ6_EQ7=True,
        prior_seed2_manifest_sha256=digest(PRIOR),
        frozen_model_exact=FROZEN,wrapper_code_sha256=digest(__file__),
        code_sha256=digest(base.__file__),binary_sha256=binaries,
        source_policy=dict(max_vars=MAX_VARIABLES,max_clauses=MAX_CLAUSES,
                           max_original_bytes=MAX_BYTES,scan_limit=SCAN_LIMIT,
                           metadata_priority="minisat1m=yes, then full main",
                           no_solver_outcome_based_screening=True),
        source_only_preselection=True,
        no_outcome_conditioning_in_holdout=True,independent_UNSAT_LRAT=False,
        global_history_exhaustive=False,not_globally_blind=True,
        no_auto_promotion=True,
        cpu_policy="each arm one pinned logical CPU, 0 portfolios")
    save(ROOT/"manifest.json",manifest)
    verify()
    print("SEED3_FROZEN",json.dumps(dict(sources=TARGET,trials=EXPECTED,
       source_years=dict(collections.Counter(c["year"] for c in selected)),
       predicted_seeds=dict(collections.Counter(c["precommitted_selection"]
                                               for c in selected)),
       source_index_tiers=dict(collections.Counter(rec["source_index_tier"]
                                                 for rec in selected)),
       max_vars=MAX_VARIABLES,max_clauses=MAX_CLAUSES,max_bytes=MAX_BYTES),
       sort_keys=True),flush=True)

def verify():
    configure()
    m=base.verify()
    need(m["protocol"]==PROTO and m["source_count"]==TARGET,
         "not SEED3 manifest")
    need(m["frozen_model_exact"]==FROZEN and
         m["training"]["model"]==FROZEN,
         "frozen SEED2 selector changed")
    need(m["wrapper_code_sha256"]==digest(__file__),
         "wrapper source changed after freeze")
    need(m["source_policy"]["max_vars"]==MAX_VARIABLES and
         m["source_policy"]["max_clauses"]==MAX_CLAUSES and
         m["source_policy"]["max_original_bytes"]==MAX_BYTES,
         "source policy changed")
    for c in m["source_cases"]:
        need(c["feature"]["vars"]<=MAX_VARIABLES and
             c["feature"]["clauses"]<=MAX_CLAUSES and
             c["feature"]["bytes"]<=MAX_BYTES,"out-of-policy CNF")
    return m

def shard(idx):
    verify()
    base.shard(idx)
    print("SEED3_SHARD_PASS",idx,TARGET//SHARDS*REPS*len(ARMS),flush=True)

def audit():
    verify()
    base.audit()
    report=json.loads((ROOT/"report.json").read_text())
    need(report["protocol"]==PROTO and report["trials"]==EXPECTED and
         report["sources"]==TARGET and report["frozen_model"]==FROZEN,
         "base audit mismatch")
    report.update(prior_selector_frozen_without_retraining=True,
       source_only_smaller_geometry=True,
       SEED3_without_global_historical_exhaustive_exclusion=True)
    save(ROOT/"report.json",report)
    print("SEED3_FINAL",json.dumps({k:v for k,v in report.items() if k!="rows"},
                                   sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":verify();print("SEED3_VERIFY_PASS",flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()
