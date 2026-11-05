#!/usr/bin/env python3
"""R151 fast paired rerun on 10 original public crypto CNFs frozen before R150.

Sources are previously used in R150; this is a development replication, not a
fresh blind holdout or an official SAT competition result.
5 modes x 2 repeats x 10 original crypto formulas = 100 trials.
Per-trial cap: 6 seconds incl native detector; PAR2 timeout: 12 seconds.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import r150_quality_benchmark as r150

PROTO="DRNAS-R151-CRYPTO-SAME-SOURCE-QUICK-6S-20261105-v1"
CAP=6.0
REPS=2
SHARDS=4
MODES=("kissat","cadical","r148","r150_02","r150_07")
OUT=Path("r151")
SOURCE_RUN=42088721067

def need(ok,why):
    if not ok:raise RuntimeError("R151_AUDIT_FAIL_CLOSED "+why)

def save(path,val):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(val,indent=2,sort_keys=True)+"\n")

def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda:fp.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def crypto_sources():
    # Reuse the R150 source file hashes, not its outcomes.
    allcases=r150.cases()
    cases=[c for c in allcases if c["cohort"]=="cryptography"]
    need(len(cases)==10,"source manifest must contain all 10 crypto CNFs")
    need(len({x["sha256"] for x in cases})==10,"duplicate source")
    return sorted(cases,key=lambda c:c["sha256"])

def initialize():
    need(r150.MODEL.is_file() and r150.FEATURE.is_file() and
         r150.R148.is_file() and r150.KISSAT.is_file() and
         r150.CADICAL.is_file(),"missing model or pinned native binaries")
    r150.CAP=CAP
    if hasattr(os,"sched_getaffinity"):
        cores=os.sched_getaffinity(0)
        if cores:os.sched_setaffinity(0,{min(cores)})
    return dict(model_sha256=hash_file(r150.MODEL),
                features_sha256=hash_file(r150.FEATURE),
                selector_sha256=hash_file(r150.R148),
                kissat_sha256=hash_file(r150.KISSAT),
                cadical_sha256=hash_file(r150.CADICAL))

def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    pins=initialize()
    cases=crypto_sources()
    manifest=hash_file(r150.SOURCES/"manifest.json")
    ours=cases[shard::SHARDS]
    need(len(ours) in (2,3),"unexpected shard assignment")
    rows=[]
    cpu=next((x for x in Path("/proc/cpuinfo").read_text().splitlines()
              if x.startswith("model name")),"unknown")
    for c in ours:
        src=(r150.SOURCES/c["id"]).resolve()
        need(hash_file(src)==c["sha256"],"original CNF SHA changed")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            answers=set()
            for mode in modes:
                val=r150.solve(src,mode,rep)
                # R150 hard-codes PAR2=30 for 15 s, so override on the
                # new 6 s budget; measured solved times remain unchanged.
                if val["status"]=="TIMEOUT":
                    val["seconds"]=CAP
                    val["par2"]=2*CAP
                need(0<=val["seconds"]<=CAP+0.00001,"elapsed outside cap")
                need(abs(val["par2"]-(2*CAP if val["status"]=="TIMEOUT"
                            else val["seconds"]))<=0.000001,"bad PAR2")
                if val["status"]=="SAT":
                    need(val["proof"]=="source_SAT_witness_verified","SAT witness unverified")
                elif val["status"]=="UNSAT":
                    need(val["proof"]=="UNSAT_without_independent_LRAT",
                         "missing honest UNSAT proof tier")
                elif val["status"]!="TIMEOUT":need(False,"bad status")
                if val["status"]!="TIMEOUT":
                    answers.add(val["status"])
                    need(len(answers)==1,"inconsistent SAT/UNSAT outputs")
                result=dict(source_sha256=c["sha256"],id=c["id"],
                            cohort="cryptography",source_manifest_sha256=manifest,
                            protocol=PROTO,shard=shard,**val)
                rows.append(result)
                save(OUT/f"shard-{shard}.json",dict(protocol=PROTO,pins=pins,
                        manifest_sha256=manifest,cpu=cpu,shard=shard,rows=rows))
                print("R151_PAIRED",json.dumps(result,sort_keys=True),flush=True)
        print("R151_ORIGINAL_CASE_DONE",c["id"],c["sha256"],flush=True)
    need(len(rows)==len(ours)*REPS*len(MODES),"missing paired rows")
    print("R151_SHARD_PASS",shard,len(rows),flush=True)

def audit():
    cases=crypto_sources()
    manifest=hash_file(r150.SOURCES/"manifest.json")
    shards=[json.loads((OUT/f"shard-{k}.json").read_text()) for k in range(SHARDS)]
    need(all(s["protocol"]==PROTO and s["manifest_sha256"]==manifest for s in shards),
         "protocol or manifest mismatch")
    need(len({json.dumps(s["pins"],sort_keys=True) for s in shards})==1,
         "mixed binary/model versions across shards")
    records=[r for s in shards for r in s["rows"]]
    need(len(records)==len(cases)*REPS*len(MODES)==100,
         "wrong number of trials")
    expected={(c["sha256"],rep,mode) for c in cases
              for rep in range(REPS) for mode in MODES}
    observed=set()
    pairs={}
    for row in records:
        key=(row["source_sha256"],row["repeat"],row["mode"])
        need(key in expected and key not in observed,"missing or duplicate pair")
        observed.add(key)
        need(row["source_manifest_sha256"]==manifest,"source drift")
        need(row["status"] in ("SAT","UNSAT","TIMEOUT"),"unexpected solver status")
        need(abs(row["par2"]-(12.0 if row["status"]=="TIMEOUT"
                 else row["seconds"]))<1e-5,"PAR2 inconsistent")
        if row["status"]=="SAT":
            need(row["proof"]=="source_SAT_witness_verified",
                 "SAT witness verification missing")
        if row["status"]=="UNSAT":
            need(row["proof"]=="UNSAT_without_independent_LRAT",
                 "cannot claim verified UNSAT")
        pairs.setdefault((row["source_sha256"],row["repeat"]),{})[row["mode"]]=row
    need(observed==expected,"incomplete full paired comparison")
    for key,by in pairs.items():
        need(len(by)==len(MODES),"incomplete formula pair")
        statuses={x["status"] for x in by.values()}-{"TIMEOUT"}
        need(len(statuses)<=1,"SAT/UNSAT conflict "+str(key))
    summary={}
    for mode in MODES:
        arr=[r for r in records if r["mode"]==mode]
        summary[mode]=dict(trials=len(arr),
                           par2_s=round(sum(r["par2"] for r in arr),6),
                           solved=sum(r["status"]!="TIMEOUT" for r in arr),
                           SAT=sum(r["status"]=="SAT" for r in arr),
                           UNSAT_without_independent_proof=sum(r["status"]=="UNSAT" for r in arr),
                           timeouts=sum(r["status"]=="TIMEOUT" for r in arr),
                           detector_time_s=round(sum(r["detector_s"] for r in arr),6),
                           route_overrides=sum(bool(r["override"]) for r in arr))
    kissat=summary["kissat"]["par2_s"]
    better=[]
    for mode in ("r148","r150_02","r150_07","cadical"):
        vals=[]
        for c in cases:
            k=c["sha256"]
            z=sum(pairs[(k,r)][mode]["par2"] for r in range(REPS))
            ref=sum(pairs[(k,r)]["kissat"]["par2"] for r in range(REPS))
            vals.append(ref-z)
        better.append(dict(mode=mode,improved_formula_pairs=sum(v>0 for v in vals),
                           worse_formula_pairs=sum(v<0 for v in vals),
                           equal_formula_pairs=sum(v==0 for v in vals),
                           par2_gain_vs_kissat_pct=round(100*(kissat-summary[mode]["par2_s"])/kissat,5)))
    report=dict(protocol=PROTO,scope="10 REUSED R150 ORIGINAL CRYPTOGRAPHY CNFs",
                blinded=False,new_crypto_sources=False,
                previous_source_run=SOURCE_RUN,formula_count=10,
                repetitions=REPS,measurements=len(records),
                cap_s=CAP,parallel_shards=SHARDS,
                original_source_sha256_verified=True,
                original_CNF_unchanged=True,sat_witness_checked=True,
                independent_unsat_proofs=False,
                same_formula_and_seed_across_modes=True,
                selector_and_detector_cost_included=True,
                source_manifest_sha256=manifest,
                pins=shards[0]["pins"],summary=summary,comparisons=better,
                verdict="DEVELOPMENT_REPLICATION_ONLY_NO_PROMOTION")
    save(OUT/"report.json",report)
    print("R151_FINAL",json.dumps(report,sort_keys=True),flush=True)

def main():
    a=argparse.ArgumentParser()
    a.add_argument("command",choices=("run","audit"))
    a.add_argument("--shard",type=int,default=0)
    args=a.parse_args()
    OUT.mkdir(exist_ok=True)
    if args.command=="run":run(args.shard)
    else:audit()

if __name__=="__main__":main()
