#!/usr/bin/env python3
"""NMR R2: train-only persistent experience, SHA-disjoint paired evaluation."""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import math
import pathlib
import random
import statistics
import sys

import new_horizon_sat as nh
import nmr_online as nmr

ROOT=pathlib.Path("new_horizon")
OUT=pathlib.Path("nmr_r2")
SPLIT=OUT/"split.json"
FROZEN=ROOT/"frozen"
PROTOCOL="DRNAS-NMR-R2-MIXING-RESOLUTION-20261107"
MODES=("clean","shadow","frozen","live","no_period")
REPS=2
SHARDS=4


def need(condition,message):
    if not condition:
        raise RuntimeError("NMR_R2_AUDIT_FAIL_CLOSED "+str(message))


def load(path):
    return json.loads(pathlib.Path(path).read_text())


def save(path, obj):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def prepare():
    manifest=load(FROZEN/"manifest.json")
    need(len(manifest["cases"])==74, "R1 74-source contract changed")
    grouped=collections.defaultdict(list)
    for c in manifest["cases"]:
        p=FROZEN/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"source changed: "+c["id"])
        group=c["origin"]+"/"+c["family"]
        grouped[group].append(c)
    training=[]
    testing=[]
    for group,items in sorted(grouped.items()):
        items.sort(key=lambda item:item["sha256"])
        # Deterministic within-cohort split keeps all test instances unseen by
        # *training*; no family labels enter the controller.
        ntrain=max(1,round(len(items)*0.45))
        training.extend(items[:ntrain])
        testing.extend(items[ntrain:])
    need(training and testing, "empty holdout split")
    need({x["sha256"] for x in training}.isdisjoint(
         {x["sha256"] for x in testing}),"train/test leak")
    random.Random(PROTOCOL).shuffle(training)
    random.Random(PROTOCOL+"TEST").shuffle(testing)
    data=dict(protocol=PROTOCOL,training=training,testing=testing,
              modes=MODES,repetitions=REPS,shards=SHARDS,
              original_manifest_sha256=sha(FROZEN/"manifest.json"),
              labels_withheld_from_controller=True,
              train_test_source_disjoint=True,
              blind_external=False,
              curriculum_note="Train/test SHA-disjoint, shared generator families. Not a blind-family generalization test.")
    save(SPLIT,data)
    print("NMR_R2_PREPARED",json.dumps(dict(training=len(training),
          testing=len(testing),runs=len(testing)*REPS*len(MODES),
          split_sha256=sha(SPLIT))),flush=True)


def verify():
    d=load(SPLIT)
    need(d["protocol"]==PROTOCOL and tuple(d["modes"])==MODES,
         "split protocol mismatch")
    need(d["original_manifest_sha256"]==sha(FROZEN/"manifest.json"),
         "frozen source manifest altered")
    source=load(FROZEN/"manifest.json")
    allsha={c["sha256"] for c in source["cases"]}
    trainsha={c["sha256"] for c in d["training"]}
    testsha={c["sha256"] for c in d["testing"]}
    need(trainsha.isdisjoint(testsha), "train/test reuse")
    need(trainsha|testsha==allsha and len(trainsha)+len(testsha)==74,
         "unaccounted frozen sources")
    for c in d["training"]+d["testing"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],"SHA drift")
    return d


def train(binary, clean, memory_file):
    cases=verify()["training"]
    mem=nmr.PersistentMemory(memory_file,True)
    history=[]
    try:
        for i,c in enumerate(cases):
            result=nmr.run_case(FROZEN/(c["id"]+".cnf"),
                                binary,clean,float(c["cap_s"]),"train",mem)
            if c.get("expected") in ("SAT","UNSAT") and result["status"]!="TIMEOUT":
                need(result["status"]==c["expected"],"wrong train outcome")
            history.append(dict(index=i, source_sha=c["sha256"],
                                origin=c["origin"], result=result))
            save(OUT/"train-trials.json",history)
            print("NMR_R2_TRAIN",json.dumps(dict(i=i,status=result["status"],
                  pairs=result["pairs"],updates=result["updates"],
                  periods=result["recurrence_hits"])),flush=True)
        stats=mem.db.execute("SELECT count(*),sum(updates) FROM episodes").fetchone()
        summary=dict(protocol=PROTOCOL,training_instances=len(cases),
                     lifetime_episodes=int(stats[0] or 0),
                     lifetime_proxy_updates=mem.policy.updates,
                     learned_labels="paired_proxies_not_optimality",
                     memory_path=str(memory_file))
        save(OUT/"training.json",summary)
        print("NMR_R2_TRAIN_PASS",json.dumps(summary),flush=True)
    finally:
        mem.close()


def trial(c,mode,rep,binary,clean,mem):
    source=FROZEN/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"changed original")
    out=nmr.run_case(source,binary,clean,float(c["cap_s"]),mode,mem)
    need(out["source_sha"]==c["sha256"],"controller source mismatch")
    if out["status"]!="TIMEOUT" and c.get("expected") in ("SAT","UNSAT"):
        need(out["status"]==c["expected"],"wrong benchmark result")
    elapsed=min(float(c["cap_s"]),float(out["elapsed_s"]))
    need(elapsed>=0.,"negative duration")
    return dict(id=c["id"],sha256=c["sha256"],origin=c["origin"],
                family=c["family"],mode=mode,rep=rep,status=out["status"],
                cap_s=c["cap_s"],wall_s=round(elapsed,7),
                par2_s=round(2*c["cap_s"] if out["status"]=="TIMEOUT" else elapsed,7),
                profile=out["profile"],windows=out["windows"],pairs=out["pairs"],
                online_updates=out["updates"],recurrence_hits=out["recurrence_hits"],
                recurrence_misses=out["recurrence_misses"],
                recurrence_lag=out["recurrence_lag"],
                scan_s=round(out["structural_scan_s"],8),proof=out["proof"])


def shard(index,binary,clean,memory_file):
    d=verify()
    need(0<=index<SHARDS, "bad shard number")
    mem=nmr.PersistentMemory(memory_file,False)
    history=[]
    try:
        for c in d["testing"][index::SHARDS]:
            for rep in range(REPS):
                modes=list(MODES)
                random.Random(PROTOCOL+c["sha256"]+str(rep)).shuffle(modes)
                for mode in modes:
                    r=trial(c,mode,rep,binary,clean,mem)
                    history.append(r)
                    save(OUT/f"shard-{index}.json",history)
                    print("NMR_R2_TRIAL",json.dumps({
                        k:r[k] for k in ("id","mode","status","wall_s",
                                        "profile","online_updates",
                                        "recurrence_hits")}),flush=True)
        expected=len(d["testing"][index::SHARDS])*REPS*len(MODES)
        need(len(history)==expected,"incomplete paired shard")
        print("NMR_R2_SHARD_PASS",index,len(history),flush=True)
    finally:
        mem.close()


def audit():
    d=verify()
    results=[]
    for index in range(SHARDS):
        rows=load(OUT/f"shard-{index}.json")
        need(len(rows)==len(d["testing"][index::SHARDS])*REPS*len(MODES),
             "incomplete shard")
        results+=rows
    need(len(results)==len(d["testing"])*REPS*len(MODES),
         "incomplete total paired benchmark")
    bykey=collections.defaultdict(dict)
    tested={c["sha256"]:c for c in d["testing"]}
    for row in results:
        need(row["sha256"] in tested, "unknown trial source")
        need(row["id"]==tested[row["sha256"]]["id"], "source id drift")
        key=(row["sha256"],row["rep"])
        need(row["mode"] not in bykey[key],"duplicated arm")
        bykey[key][row["mode"]]=row
        expected_par=(2*row["cap_s"] if row["status"]=="TIMEOUT"
                      else row["wall_s"])
        need(abs(row["par2_s"]-expected_par)<0.00001, "PAR2 mismatch")
        need(row["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
        if row["status"]=="SAT":
            need(row["proof"] in ("SAT_WITNESS_VERIFIED_ORIGINAL_CNF",
                                   "SAT_WITNESS_CHECKED_ORIGINAL_SHA"),"unverified SAT")
    for key,arms in bykey.items():
        need(set(arms)==set(MODES),"missing paired arm")
        resolved={v["status"] for v in arms.values() if v["status"]!="TIMEOUT"}
        need(len(resolved)<=1,"SAT/UNSAT contradiction")
    summary={}
    for cohort in ("all","reused_external_original",
                   "new_seed_known_family","synthetic_controlled"):
        chosen={c["sha256"] for c in d["testing"]
                if cohort=="all" or c["origin"]==cohort}
        summary[cohort]={}
        for mode in MODES:
            subset=[r for r in results if r["mode"]==mode and r["sha256"] in chosen]
            summary[cohort][mode]=dict(
                trials=len(subset),
                solved=sum(r["status"]!="TIMEOUT" for r in subset),
                par2_s=round(sum(r["par2_s"] for r in subset),5),
                wall_s=round(sum(r["wall_s"] for r in subset),5),
                neural_updates=sum(r["online_updates"] for r in subset),
                recurrence_hits=sum(r["recurrence_hits"] for r in subset),
                recurrence_misses=sum(r["recurrence_misses"] for r in subset),
                used_sat_profile=sum(r["profile"]=="sat" for r in subset))
    comparisons={}
    for mode in MODES[1:]:
        ratios=[];wins=losses=ties=0
        for arms in bykey.values():
            a=arms["clean"]
            b=arms[mode]
            if a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT":
                ratios.append(a["wall_s"]/max(b["wall_s"],0.0000001))
            if b["par2_s"]<a["par2_s"]*0.995:wins+=1
            elif b["par2_s"]>a["par2_s"]*1.005:losses+=1
            else:ties+=1
        comparisons[mode]=dict(paired_wins=wins,paired_losses=losses,
                 paired_ties=ties,
                 geometric_speedup_both_solved=round(
                   math.exp(statistics.mean(math.log(x) for x in ratios)),5)
                   if ratios else None,comparable_solved_pairs=len(ratios))
    report=dict(protocol=PROTOCOL,status="AUDIT_PASS_NONBLIND",
                sources=len(d["testing"]),train_sources=len(d["training"]),
                attempts=len(results),repetitions=REPS,
                control="same frozen original, cap, paired/reversed order",
                source_sha=sha(SPLIT),
                caveat="Not blind-family; short-clause proxy is not optimality; recurrence in telemetry is not proof of mathematical formula periodicity; native UNSAT lacks independently checked LRAT.",
                summary=summary,comparisons=comparisons)
    save(OUT/"report.json",report)
    save(OUT/"trials.json",results)
    with (OUT/"trials.csv").open("w",newline="") as f:
        fieldnames=list(results[0])
        writer=csv.DictWriter(f,fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    lines=["# DRNAS New Horizon NMR R2 — audited paired experiment","",
           f"{len(d['training'])} training formulas, {len(d['testing'])} disjoint evaluation formulas, {len(results)} paired attempts.",
           "","| Cohort | Arm | Solved | PAR2 s | Neural updates |",
           "|---|---|---:|---:|---:|"]
    for cohort,data in summary.items():
        for mode,r in data.items():
            lines.append(f"| {cohort} | {mode} | {r['solved']}/{r['trials']} | {r['par2_s']} | {r['neural_updates']} |")
    lines+=["","## Paired comparisons vs clean","",
            "| Arm | Wins | Losses | Ties | Geomean speedup on both-solved |",
            "|---|---:|---:|---:|---:|"]
    for mode,v in comparisons.items():
        lines.append(f"| {mode} | {v['paired_wins']} | {v['paired_losses']} | {v['paired_ties']} | {v['geometric_speedup_both_solved']} |")
    lines+=["","## Important limitations",
            "- Source-disjoint training/evaluation, but generator families are reused; this is not a blind external holdout.",
            "- Telemetry events and predictive recurrence are sampled, not measured at every CPU instruction or solver cycle.",
            "- Neural labels optimize a heuristic short-clause/time proxy, not final SAT runtime directly.",
            "- A detected recurrence is a measured sequence pattern, not proof that the source formula is periodic.",
            "- SAT witnesses checked against unchanged source; native UNSAT lacks independently verified LRAT.",
            "- Wall time includes scanning, inference, dual-solver work, Python controller, and database overhead.",
            "- No claim of universal speedup, or polynomial SAT solving."]
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NMR_R2_FINAL",json.dumps(dict(cases=len(d["testing"]),
          attempts=len(results),comparisons=comparisons)),flush=True)


def selftest():
    nmr.selftest()
    print("NMR_R2_BENCH_SELFTEST_PASS",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("selftest","prepare","verify","train","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="nmr_r2/nmr-driver")
    p.add_argument("--clean",default="new_horizon/r190-driver")
    p.add_argument("--memory",default="nmr_r2/model.sqlite")
    a=p.parse_args()
    if a.command=="selftest":selftest()
    elif a.command=="prepare":prepare()
    elif a.command=="verify":print("NMR_R2_VERIFY_PASS",len(verify()["testing"]))
    elif a.command=="train":train(a.binary,a.clean,a.memory)
    elif a.command=="shard":shard(a.shard,a.binary,a.clean,a.memory)
    else:audit()
