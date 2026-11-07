#!/usr/bin/env python3
"""DRNAS Neural R5 paired evaluation: clean, R4, shadow, reward, neural.

Known R2/R4 40-source holdout is NOT BLIND. Results are hypothesis-generating.
All decisions use only 34 training CNFs and training reward observations.
"""
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
import nmr_r2_benchmark as r2
import nmr_r4_benchmark as r4b
import nmr_r4_policy as r4
import nmr_r5_utility as r5

ROOT=pathlib.Path("nmr_r5")
SOURCES=pathlib.Path("new_horizon/frozen")
PROTOCOL="DRNAS-NEURAL-R5-PAIRED-UTILITY-v1"
MODES=r5.MODES
SHARDS=4
REPS=2
N_SOURCES=40
N_ATTEMPTS=N_SOURCES*REPS*len(MODES)

def need(ok,msg):
    if not ok:
        raise RuntimeError("R5_AUDIT_FAIL_CLOSED: "+str(msg))

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path,item):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(item,indent=2,sort_keys=True)+"\n")

def read(path):
    return json.loads(pathlib.Path(path).read_text())

def verify_sources():
    d=r2.verify()
    need(len(d["training"])==34 and len(d["testing"])==N_SOURCES,
         "wrong source counts")
    train={x["sha256"] for x in d["training"]}
    test={x["sha256"] for x in d["testing"]}
    need(not train.intersection(test),"train-test SHA overlap")
    for c in d["training"]+d["testing"]:
        p=SOURCES/(c["id"]+".cnf")
        need(sha(p)==c["sha256"],"source digest changed")
    return d

def train():
    split=verify_sources()
    training_path=pathlib.Path("nmr_r4/training-trials.json")
    need(training_path.exists(),"R4 training artifact missing")
    trials=read(training_path)
    need(len(trials)==68,"R4 paired reward count drift")
    model=r5.train(trials,split,SOURCES,ROOT/"model.json")
    report=dict(protocol=PROTOCOL,status="TRAIN_PASS",
        model_sha256=sha(ROOT/"model.json"),
        frozen_split_sha256=sha("nmr_r2/split.json"),
        source_manifest_sha256=sha(SOURCES/"manifest.json"),
        reward_sha256=sha(training_path),
        known_holdout_not_blind=True,
        train_sources=34,
        samples=model["trained_samples"],
        sample_counts=model["samples_by_arm"],
        epochs=80,checkpoint_training_mse=model["history"][-1]["training_mse"],
        no_test_update=True,primary="paired PAR2 / solved / safety")
    save(ROOT/"train-report.json",report)
    print("R5_TRAIN_PASS",json.dumps(report,sort_keys=True),flush=True)

def load_model():
    report=read(ROOT/"train-report.json")
    need(report["protocol"]==PROTOCOL,"protocol drift")
    need(sha(ROOT/"model.json")==report["model_sha256"],"model drift")
    need(sha("nmr_r2/split.json")==report["frozen_split_sha256"],
         "source split drift")
    need(sha(SOURCES/"manifest.json")==report["source_manifest_sha256"],
         "manifest drift")
    return r5.RewardMLP(read(ROOT/"model.json"))

def one(c,rep,mode,driver,clean,r3driver,memory,net):
    src=SOURCES/(c["id"]+".cnf")
    need(sha(src)==c["sha256"],"source drift")
    cap=float(c["cap_s"])
    z=r5.run_case(src,driver,clean,r3driver,cap,mode,memory,net)
    r4b.validate(c,z)
    par2=2*cap if z["status"]=="TIMEOUT" else z["elapsed_s"]
    return dict(source_sha256=c["sha256"],id=c["id"],
        origin=c["origin"],family=c["family"],
        mode=mode,rep=rep,status=z["status"],proof=z["proof"],
        cap_s=cap,wall_s=round(z["elapsed_s"],7),
        par2_s=round(par2,7),
        reason=z["reason"],requested_arm=z["requested_arm"],
        selected_arm=z["selected_arm"],bucket=z["bucket"],
        predicted_gain_s=z["predicted_gain_s"],
        lower_gain_s=z["lower_gain_s"],
        activation_s=round(z["activation_s"],8),
        callback_wakeups=z["callback_wakeups"],
        windows=z["windows"])

def shard(index,driver,clean,r3driver,memory_path):
    d=verify_sources()
    need(0<=index<SHARDS,"invalid shard")
    net=load_model()
    model_before=sha(ROOT/"model.json")
    memory_before=sha(memory_path)
    mem=r4.UtilityBandit(memory_path,False)
    rows=[]
    try:
        for i in range(index,len(d["testing"]),SHARDS):
            c=d["testing"][i]
            for rep in range(REPS):
                modes=list(MODES)
                random.Random(PROTOCOL+c["sha256"]+str(rep)).shuffle(modes)
                for mode in modes:
                    row=one(c,rep,mode,driver,clean,r3driver,mem,net)
                    rows.append(row)
                    save(ROOT/f"shard-{index}.json",rows)
                    print("R5_TRIAL",json.dumps({k:row[k] for k in
                        ("id","rep","mode","status","wall_s","requested_arm",
                         "selected_arm","reason")},sort_keys=True),flush=True)
        expected=len(d["testing"][index::SHARDS])*REPS*len(MODES)
        need(len(rows)==expected,"missing attempts")
    finally:
        mem.close()
    need(sha(ROOT/"model.json")==model_before,"test mutated neural model")
    need(sha(memory_path)==memory_before,"test mutated utility memory")
    print("R5_SHARD_PASS",index,len(rows),flush=True)

def audit():
    d=verify_sources()
    rows=[]
    for i in range(SHARDS):
        p=ROOT/f"shard-{i}.json"
        part=read(p)
        need(len(part)==len(d["testing"][i::SHARDS])*REPS*len(MODES),
             "incomplete shard "+str(i))
        rows.extend(part)
    need(len(rows)==N_ATTEMPTS,"attempt count mismatch")
    cases={c["sha256"]:c for c in d["testing"]}
    grouped=collections.defaultdict(dict)
    for r in rows:
        c=cases.get(r["source_sha256"])
        need(c is not None and c["id"]==r["id"],"not known holdout source")
        key=(r["source_sha256"],r["rep"])
        need(r["rep"] in (0,1) and r["mode"] in MODES
             and r["mode"] not in grouped[key],"duplicate mode")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad solve status")
        expected=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["wall_s"]
        need(abs(expected-r["par2_s"])<1e-5,"PAR2 error")
        if r["status"]=="SAT":
            need(r["proof"] in ("SAT_WITNESS_VERIFIED_SOURCE",
                              "ORIGINAL_CNF_SAT_WITNESS_CHECKED",
                              "SAT_WITNESS_CHECKED_ORIGINAL_SHA"),
                 "unverified SAT witness")
        if r["mode"] in ("clean","r4_safe","r5_shadow"):
            need(r["requested_arm"]==0,"shadow action leak")
        grouped[key][r["mode"]]=r
    need(len(grouped)==N_SOURCES*REPS,"paired key count")
    for pair,arms in grouped.items():
        need(set(arms)==set(MODES),"missing paired arm")
        statuses={x["status"] for x in arms.values() if x["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"contradictory SAT/UNSAT outcomes")
    results,comparisons={},{}
    for mode in MODES:
        part=[r for r in rows if r["mode"]==mode]
        results[mode]=dict(trials=len(part),
            solved=sum(r["status"]!="TIMEOUT" for r in part),
            par2_s=round(sum(r["par2_s"] for r in part),6),
            wall_s=round(sum(r["wall_s"] for r in part),6),
            attempted_activations=sum(r["requested_arm"]!=0 for r in part),
            actual_activations=sum(r["activation_s"]>0 for r in part),
            selected_alternate=sum(r["selected_arm"] in (1,2) for r in part),
            abstentions=sum("abstain" in r["reason"] for r in part))
    for mode in MODES[1:]:
        wins=losses=ties=0
        ratios=[]
        paired_deltas=[]
        for arms in grouped.values():
            a,b=arms["clean"],arms[mode]
            delta=a["par2_s"]-b["par2_s"]
            paired_deltas.append(delta)
            if b["par2_s"]<a["par2_s"]*.995:wins+=1
            elif b["par2_s"]>a["par2_s"]*1.005:losses+=1
            else:ties+=1
            if a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT":
                ratios.append(a["wall_s"]/max(1e-9,b["wall_s"]))
        comparisons[mode]=dict(wins=wins,losses=losses,ties=ties,
             par2_gain_s=round(sum(paired_deltas),6),
             both_solved=len(ratios),
             geomean_speedup=(round(math.exp(statistics.mean(
                 math.log(x) for x in ratios)),6) if ratios else None))
    report=dict(protocol=PROTOCOL,status="AUDIT_PASS_NOT_BLIND",
        attempts=N_ATTEMPTS,source_count=N_SOURCES,
        repetitions=REPS,modes=list(MODES),
        training_checkpoint_sha256=read(ROOT/"train-report.json")["model_sha256"],
        primary="solved count and PAR2 including controller, scan and startup overhead",
        known_holdout_not_blind=True,
        sat_witness_check=True,independent_unsat_lrat=False,
        results=results,comparisons=comparisons,
        caveat="R2/R4 reused holdout; needs independent prospective CNF validation")
    save(ROOT/"report.json",report)
    save(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as fd:
        w=csv.DictWriter(fd,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    lines=["# DRNAS Neural R5 — actual utility reward versus clean CaDiCaL","",
      "40 reused heldout CNFs × 2 reps × 5 arms = 400 paired attempts.",
      "NOT BLIND: previous R2/R4 development has already inspected this holdout.",
      "Training-only utility rewards, model frozen and read-only in tests.","",
      "| Mode | Solved | PAR2 seconds | Requested interventions |",
      "|---|---:|---:|---:|"]
    for k,v in results.items():
        lines.append(f"| {k} | {v['solved']}/{v['trials']} | {v['par2_s']} | {v['attempted_activations']} |")
    lines.extend(["","| Mode | Wins | Losses | Ties | PAR2 gain (s) | Geomean |",
                  "|---|---:|---:|---:|---:|---:|"])
    for k,v in comparisons.items():
        lines.append(f"| {k} | {v['wins']} | {v['losses']} | {v['ties']} | {v['par2_gain_s']} | {v['geomean_speedup']} |")
    lines.extend(["","No independent LRAT for native UNSAT; SAT models verified.",
                  "Never claim a general SAT advantage without prospective tests."])
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("R5_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    r5.selftest()
    need(N_ATTEMPTS==400 and len(MODES)==5,"bad experiment matrix")
    print("R5_BENCH_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("selftest","train","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--driver",default="nmr_r4/nmr4-driver")
    p.add_argument("--clean",default="new_horizon/r190-driver")
    p.add_argument("--r3driver",default="nmr_r3/nmr3-driver")
    p.add_argument("--memory",default="nmr_r4/model.sqlite")
    a=p.parse_args()
    if a.command=="selftest":selftest()
    elif a.command=="train":train()
    elif a.command=="shard":shard(a.shard,a.driver,a.clean,
                                  a.r3driver,a.memory)
    else:audit()
