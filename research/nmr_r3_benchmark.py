#!/usr/bin/env python3
"""DRNAS R3 utility-feedback benchmark: training-only calibration and held-out arms."""
from __future__ import annotations
import argparse
import collections
import csv
import json
import math
import pathlib
import random
import statistics

import nmr_r2_benchmark as r2
import nmr_r3_policy as r3

OUT=pathlib.Path("nmr_r3")
SOURCE=pathlib.Path("new_horizon/frozen")
PROTOCOL="DRNAS-NMR-R3-COST-UTILITY-FEEDBACK-v1"
MODES=r3.MODES
REPS=2
SHARDS=4


def need(v,msg):
    if not v:
        raise RuntimeError("NMR3_AUDIT_FAIL_CLOSED "+str(msg))


def save(path,obj):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")


def read(path):
    return json.loads(pathlib.Path(path).read_text())


def verify():
    data=r2.verify()   # previously frozen source-disjoint 34/40 split
    need(data["train_test_source_disjoint"] is True,"train/test must be disjoint")
    need(len(data["training"])==34 and len(data["testing"])==40,
         "unexpected R2 split drift")
    return data


def cap_par(status,elapsed,cap):
    return 2*cap if status=="TIMEOUT" else elapsed


def output_trial(c,mode,rep,driver,clean,mem):
    src=SOURCE/(c["id"]+".cnf")
    result=r3.run_case(src,driver,clean,float(c["cap_s"]),mode,mem)
    need(result["source_sha"]==c["sha256"],"input integrity failure")
    status=result["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"unknown status")
    expected=c.get("expected")
    if status!="TIMEOUT" and expected in ("SAT","UNSAT"):
        need(status==expected,"incorrect answer")
    elapsed=float(result["elapsed_s"])
    need(0.<=elapsed<=float(c["cap_s"])+1e-8,"cap or timing violated")
    return dict(id=c["id"],sha256=c["sha256"],origin=c["origin"],
                family=c["family"],mode=mode,rep=rep,status=status,
                cap_s=float(c["cap_s"]),wall_s=round(elapsed,7),
                par2_s=round(cap_par(status,elapsed,float(c["cap_s"])),7),
                reason=result["reason"],windows=result["windows"],
                activation_s=round(result["activation_s"],8),
                scan_s=round(result["scan_s"],8),
                recurrence_hits=result["recurrence_hits"],
                recurrence_misses=result["recurrence_misses"],
                callback_wakeups=result["callback_wakeups"],
                observations=result["observations"],
                net_probability=result.get("probability"),
                utility_estimate_s=result.get("expected_gain_s"),
                proof=result["proof"])


def train(driver,clean,path):
    data=verify()
    memory=r3.UtilityMemory(path,True)
    records=[]
    try:
        for i,c in enumerate(data["training"]):
            original=SOURCE/(c["id"]+".cnf")
            baseline=r3.run_case(original,driver,clean,float(c["cap_s"]),"clean",memory)
            forced=r3.run_case(original,driver,clean,float(c["cap_s"]),"forced_probe",memory)
            expected=c.get("expected")
            for a in (baseline,forced):
                if a["status"]!="TIMEOUT" and expected in ("SAT","UNSAT"):
                    need(a["status"]==expected,"bad training SAT result")
            benefit=(cap_par(baseline["status"],baseline["elapsed_s"],float(c["cap_s"]))-
                     cap_par(forced["status"],forced["elapsed_s"],float(c["cap_s"])))
            features=forced["decision_feature"]
            if features is not None:
                memory.add_training(features,benefit,forced["activation_s"],c["sha256"])
            row=dict(i=i,source_sha=c["sha256"],
                     baseline_status=baseline["status"],forced_status=forced["status"],
                     baseline_wall_s=round(baseline["elapsed_s"],6),
                     forced_wall_s=round(forced["elapsed_s"],6),
                     paired_benefit_s=round(benefit,6),
                     activation_s=round(forced["activation_s"],6),
                     trained=features is not None)
            records.append(row)
            save(OUT/"training-trials.json",records)
            print("NMR3_TRAIN",json.dumps(row),flush=True)
        n,w,pos,neg,act=memory.read_stats()
        report=dict(protocol=PROTOCOL,
                    training_sources=len(data["training"]),
                    persistent_training_episodes=n,
                    positive_exploration_results=w,
                    total_positive_benefit_s=pos,
                    total_negative_benefit_s=neg,
                    total_activation_overhead_s=act,
                    lifetime_neural_updates=memory.model.policy.updates,
                    utility_gate_requires_evidence=True,
                    labels="paired baseline-vs-forced outcomes, training only")
        save(OUT/"training.json",report)
        print("NMR3_TRAIN_PASS",json.dumps(report),flush=True)
    finally:
        memory.close()


def shard(index,driver,clean,path):
    data=verify()
    need(0<=index<SHARDS,"bad shard index")
    mem=r3.UtilityMemory(path,False)
    rows=[]
    try:
        for c in data["testing"][index::SHARDS]:
            for rep in range(REPS):
                arms=list(MODES)
                random.Random(PROTOCOL+c["sha256"]+str(rep)).shuffle(arms)
                for mode in arms:
                    row=output_trial(c,mode,rep,driver,clean,mem)
                    rows.append(row)
                    save(OUT/f"shard-{index}.json",rows)
                    print("NMR3_TRIAL",json.dumps({k:row[k] for k in
                        ("id","mode","status","wall_s","windows",
                         "reason","activation_s","callback_wakeups")}),flush=True)
        target=len(data["testing"][index::SHARDS])*REPS*len(MODES)
        need(len(rows)==target,"incomplete shard")
        print("NMR3_SHARD_PASS",index,target,flush=True)
    finally:
        mem.close()


def audit():
    data=verify()
    trials=[]
    for i in range(SHARDS):
        part=read(OUT/f"shard-{i}.json")
        need(len(part)==len(data["testing"][i::SHARDS])*REPS*len(MODES),
             "incomplete shard")
        trials.extend(part)
    need(len(trials)==len(data["testing"])*REPS*len(MODES),
         "wrong number of trial records")
    expected={c["sha256"]:c for c in data["testing"]}
    pairs=collections.defaultdict(dict)
    for a in trials:
        need(a["sha256"] in expected and a["id"]==expected[a["sha256"]]["id"],
             "source identity error")
        key=(a["sha256"],a["rep"])
        need(a["mode"] not in pairs[key],"duplicate mode")
        pairs[key][a["mode"]]=a
        need(abs(a["par2_s"]-cap_par(a["status"],a["wall_s"],a["cap_s"]))<.00002,
             "PAR2 inconsistent")
        if a["status"]=="SAT":
            need(a["proof"] in ("ORIGINAL_CNF_SAT_WITNESS_CHECKED",
                                 "SAT_WITNESS_CHECKED_ORIGINAL_SHA"),
                 "unverified SAT witness")
    for key,arms in pairs.items():
        need(set(arms)==set(MODES),"paired arm missing")
        statuses={r["status"] for r in arms.values() if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT and UNSAT disagree")
    by_mode={}
    for mode in MODES:
        rows=[r for r in trials if r["mode"]==mode]
        by_mode[mode]=dict(
            trials=len(rows),solved=sum(r["status"]!="TIMEOUT" for r in rows),
            par2_s=round(sum(r["par2_s"] for r in rows),6),
            wall_s=round(sum(r["wall_s"] for r in rows),6),
            sample_windows=sum(r["windows"] for r in rows),
            activation_count=sum(r["activation_s"]>0 for r in rows),
            cost_abstention_count=sum("abstention" in r["reason"] or
              "no_positive_training_calibration"==r["reason"] for r in rows),
            recurrence_hits=sum(r["recurrence_hits"] for r in rows),
            callback_wakeups=sum(r["callback_wakeups"] for r in rows))
    comparisons={}
    for mode in MODES[1:]:
        wins=losses=ties=0
        speed=[]
        for arms in pairs.values():
            baseline=arms["clean"]
            current=arms[mode]
            if current["par2_s"]<baseline["par2_s"]*.995:wins+=1
            elif current["par2_s"]>baseline["par2_s"]*1.005:losses+=1
            else:ties+=1
            if baseline["status"]!="TIMEOUT" and current["status"]!="TIMEOUT":
                speed.append(baseline["wall_s"]/max(current["wall_s"],1e-8))
        comparisons[mode]=dict(wins=wins,losses=losses,ties=ties,
          geometric_speedup_both_solved=round(
            math.exp(statistics.mean(math.log(s) for s in speed)),5)
            if speed else None,pairs_both_solved=len(speed))
    report=dict(protocol=PROTOCOL,status="AUDIT_PASS_NONBLIND",
                sources=len(data["testing"]),training_sources=len(data["training"]),
                runs=len(trials),baseline="SHA-pinned CaDiCaL 2.1 31f9aae",
                confidence_note="Known families, source-disjoint but not external-family blind.",
                caveat="Neural decisions do not prove periodicity or completeness; native UNSAT not independently LRAT verified; paired runtime is wall-clock including all overhead.",
                summary=by_mode,comparisons=comparisons)
    save(OUT/"report.json",report)
    save(OUT/"trials.json",trials)
    with (OUT/"trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(trials[0]))
        w.writeheader();w.writerows(trials)
    lines=["# NMR R3 — Adaptive Utility Feedback (held-out sources)","",
           f"{len(data['testing'])} evaluation formulas, 2 repetitions, {len(trials)} trials.",
           "","| Arm | Solved | PAR2 s | Wall s | Observation windows | Activations |",
           "|---|---:|---:|---:|---:|---:|"]
    for mode,s in by_mode.items():
        lines.append(f"| {mode} | {s['solved']}/{s['trials']} | {s['par2_s']} | {s['wall_s']} | {s['sample_windows']} | {s['activation_count']} |")
    lines+=["","## Comparison with clean CDCL","",
            "| Method | Paired wins | Paired losses | Ties | Both-solved geometric speedup |",
            "|---|---:|---:|---:|---:|"]
    for mode,s in comparisons.items():
        lines.append(f"| {mode} | {s['wins']} | {s['losses']} | {s['ties']} | {s['geometric_speedup_both_solved']} |")
    lines+=["","## Limitations",
            "- R3 parameters selected after examining R2 evidence, not blind development.",
            "- SHA-disjoint evaluation uses known families; real external formulas are previously used.",
            "- Only observations after bounded CDCL conflict batches, not every instruction.",
            "- Periodic telemetry candidate is not a proof of periodic formula structure.",
            "- Model training uses clean-vs-forced outcomes on training sources only.",
            "- Proof correctness: SAT witnesses checked against original CNFs, native UNSAT not independently LRAT certified.",
            "- Even a no-AI path has Python launcher and stat overhead, measured in walltime."]
    (OUT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NMR3_FINAL",json.dumps(dict(sources=len(data["testing"]),
            attempts=len(trials),summary=by_mode,comparisons=comparisons)),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("selftest","verify","train","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--driver",default="nmr_r3/nmr3-driver")
    p.add_argument("--clean",default="new_horizon/r190-driver")
    p.add_argument("--memory",default="nmr_r3/model.sqlite")
    a=p.parse_args()
    if a.command=="selftest":
        r3.selftest()
        print("NMR3_BENCH_SELFTEST_PASS",flush=True)
    elif a.command=="verify":
        print("NMR3_VERIFY_PASS",len(verify()["testing"]),flush=True)
    elif a.command=="train":train(a.driver,a.clean,a.memory)
    elif a.command=="shard":shard(a.shard,a.driver,a.clean,a.memory)
    else:audit()
