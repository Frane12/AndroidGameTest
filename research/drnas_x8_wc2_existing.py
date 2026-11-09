#!/usr/bin/env python3
"""WC2: existing C13 official SAT Competition 2026 originals vs frozen X8.

This is an explicitly HISTORICAL comparison, NOT blind, NOT official World Cup,
and NOT guaranteed medium-runtime on the GH runner. Reuses 12 C13 SHA-frozen
original CNFs without downloading any new SAT instance. Same hardware and 25s
E2E cap per arm, 2 repeats, 5 modes, 120 full E2E trials.
"""
import argparse
import collections
import json
import pathlib
import shutil

import drnas_x8_worldcup_mid16 as w

w.PROTO="DRNAS-X8-WC2-HISTORICAL-C13-12SHA-6SAT-6UNSAT-5ARMS-2REP-25S-v1"
w.OUT=pathlib.Path("wc2_out")
w.SRC=pathlib.Path("wc2_sources")
w.X8_BINARY=pathlib.Path("wc2_bin/mre_x8/bin/native")
w.TARGET=12
w.MIN_READY=12
w.REPS=2
w.SHARDS=4
w.CAP=25.0

ORIGINAL=pathlib.Path("c13_sources")
C13_PROTO="DRNAS-C13-2026-NEW12-6ARMS-3REPS-30S-E2E-v1"
C13_MANIFEST_SHA="e1563f7acb67bbbca4a8ff7d982e9c7e25c59e3a8b1941e6d660ae6cf1be45f3"

def freeze():
    original_manifest=ORIGINAL/"manifest.json"
    w.need(original_manifest.is_file(),"original C13 manifest missing")
    w.need(w.digest(original_manifest)==C13_MANIFEST_SHA,
           "C13 source manifest SHA not original audited manifest")
    raw=json.loads(original_manifest.read_text())
    w.need(raw["protocol"]==C13_PROTO and raw["source_count"]==12,
           "wrong frozen C13 cohort")
    cs=raw["cases"]
    w.need(len(cs)==12 and len({c["sha256"] for c in cs})==12,
           "wrong C13 source set or duplicate")
    w.need(collections.Counter(c["status"] for c in cs)=={"SAT":6,"UNSAT":6},
           "C13 published SAT/UNSAT cohort changed")
    w.SRC.mkdir(parents=True,exist_ok=True)
    items=[]
    for c in cs:
        source=ORIGINAL/c["filename"]
        w.need(source.is_file() and source.stat().st_size==c["bytes"] and
               w.digest(source)==c["sha256"],
               "C13 original binary SHA mismatch")
        target=w.SRC/c["filename"]
        shutil.copyfile(source,target)
        w.need(w.digest(target)==c["sha256"],
               "WC2 original source copy mismatch")
        items.append({
            "gbd":c["gbd"],"reference":c["status"],
            "sha256":c["sha256"],"filename":c["filename"],
            "bytes":c["bytes"],"nvars":c["nvars"],
            "nclauses":c["nclauses"],"official_ca3_s":None,
            "selection":"previously_evaluated_C13_original_not_blind",
        })
    manifest={
        "protocol":w.PROTO,"source_count":len(items),"target":12,
        "cap_s":w.CAP,"seed_repeats":w.REPS,"arms":list(w.ARMS),
        "source_frozen_before_local_solver":True,
        "cases":items,"C13_original_source_manifest_sha256":C13_MANIFEST_SHA,
        "C13_original_run":"https://github.com/Frane12/AndroidGameTest/actions/runs/42537515529",
        "C13_prior_30s_results_existed_before_selection":True,
        "not_new_not_blind":True,
        "not_medium_runtime_controlled":True,
        "not_official_SAT_Competition_ranking":True,
        "UNSAT_independent_LRAT":False,"no_auto_promotion":True
    }
    w.save(w.SRC/"manifest.json",manifest)
    (w.SRC/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in items))
    print("X8_WC2_FROZEN",json.dumps({"n":len(items),"SAT":6,"UNSAT":6,
        "manifest_sha":w.digest(w.SRC/"manifest.json"),
        "historical":True}),flush=True)

def audit():
    w.audit()
    path=w.OUT/"report.json"
    v=json.loads(path.read_text())
    w.need(v["source_count"]==12 and v["total_trials"]==120,
           "WC2 incomplete full E2E")
    v["WC2_existing_C13_historical_not_blind"]=True
    v["prior_reference_timings_unknown_medium"]=True
    v["not_official_competition_ranking"]=True
    w.save(path,v)
    print("X8_WC2_HISTORICAL_AUDIT_PASS 12 120",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="freeze":freeze()
    elif args.action=="selftest":w.selftest()
    elif args.action=="verify":
        cs=w.cases()
        w.need(len(cs)==12,"expected 12 C13 originals")
        print("X8_WC2_VERIFY_PASS",len(cs),flush=True)
    elif args.action=="shard":w.shard(args.shard)
    else:audit()

if __name__=="__main__":
    main()
