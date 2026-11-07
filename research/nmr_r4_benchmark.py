#!/usr/bin/env python3
"""R4: pre-registered bounded exploration and 480 source-paired evaluation arms.

R2/R3 holdout was already inspected in development => NOT BLIND.
Training uses original training partition only. No test result updates memory.
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
import nmr_r4_policy as r4

ROOT=pathlib.Path("nmr_r4")
SOURCE=pathlib.Path("new_horizon/frozen")
PLAN=ROOT/"exploration-plan.json"
PROTOCOL="DRNAS-NMR-R4-PERSISTENT-BOUNDED-EXPLORATION-v1"
MODES=r4.MODES
REPS=2
SHARDS=4

def need(ok,msg):
    if not ok:raise RuntimeError("NMR4_AUDIT_FAIL_CLOSED: "+str(msg))

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def write(path,obj):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def read(path):
    return json.loads(pathlib.Path(path).read_text())

def source_split():
    d=r2.verify()
    need(len(d["training"])==34 and len(d["testing"])==40,
         "R2 source pool changed")
    return d

def prepare():
    d=source_split()
    assignments=[]
    # Deterministic randomization from an index list fixed before outcomes.
    # Model sees only the selected arm, never the SHA or family ID.
    rng=random.Random(PROTOCOL)
    slots=[(i,rep) for i in range(40) for rep in range(REPS)]
    rng.shuffle(slots)
    assigned={}
    for k,item in enumerate(slots):
        assigned[item]=(1+(k//8)%2) if k%8==0 else None
    for i,c in enumerate(d["testing"]):
        for rep in range(REPS):
            assignments.append(dict(source_sha=c["sha256"],index=i,rep=rep,
                                    explore_arm=assigned[(i,rep)]))
    need(sum(x["explore_arm"] is not None for x in assignments)==10,
         "expected ten preplanned exploration attempts")
    write(PLAN,dict(protocol=PROTOCOL,source_split_sha=sha("nmr_r2/split.json"),
                    assignments=assignments,planned_exploration_count=10,
                    attempt_count=40*REPS,
                    independent_of_formula_identity=True,
                    model_sees_only_arm_not_assignment_keys=True,
                    source_disjoint_not_blind=True))
    print("NMR4_PLAN_PASS",json.dumps(dict(test_sources=40,attempts=480,
          explore_slots=10,plan_sha256=sha(PLAN))),flush=True)

def verify():
    d=source_split()
    p=read(PLAN)
    need(p["protocol"]==PROTOCOL and
         p["source_split_sha"]==sha("nmr_r2/split.json"),
         "exploration plan source mismatch")
    need(len(p["assignments"])==80,"plan count")
    lookup={}
    for a in p["assignments"]:
        index=a["index"];rep=a["rep"]
        need(0<=index<40 and rep in (0,1) and
             a["source_sha"]==d["testing"][index]["sha256"],"plan identity drift")
        key=(index,rep)
        need(key not in lookup,"duplicate plan entry")
        need(a["explore_arm"] in (None,1,2),"unknown expert")
        lookup[key]=a["explore_arm"]
    need(len(lookup)==80 and
         sum(v is not None for v in lookup.values())==10,"exploration budget drift")
    return d,lookup

def par2(result,cap):
    return 2*cap if result["status"]=="TIMEOUT" else result["elapsed_s"]

def validate(c,result):
    need(result["source_sha"]==c["sha256"],"SHA mismatch")
    need(result["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
    if result["status"]!="TIMEOUT" and c.get("expected") in ("SAT","UNSAT"):
        need(result["status"]==c["expected"],"wrong known result")
    if result["status"]=="SAT":
        need(result["proof"] in ("SAT_WITNESS_VERIFIED_SOURCE",
              "ORIGINAL_CNF_SAT_WITNESS_CHECKED",
              "SAT_WITNESS_CHECKED_ORIGINAL_SHA"),
             "SAT witness not checked against original source")

def train(driver,clean,r3_driver,path):
    d,_=verify()
    m=r4.UtilityBandit(path,True)
    records=[]
    try:
        for i,c in enumerate(d["training"]):
            src=SOURCE/(c["id"]+".cnf")
            # Counterbalanced order across source hashes, not target labels.
            choices=["clean","forced_sat","forced_unsat"]
            random.Random(PROTOCOL+c["sha256"]).shuffle(choices)
            outcomes={}
            for mode in choices:
                z=r4.run_case(src,driver,clean,r3_driver,float(c["cap_s"]),mode,m)
                validate(c,z)
                outcomes[mode]=z
            baseline=outcomes["clean"]
            for arm,mode in ((1,"forced_sat"),(2,"forced_unsat")):
                z=outcomes[mode]
                # If no second solver was actually activated, record that
                # as a non-informative attempt, NOT positive evidence.
                activated=z["activation_s"]>0
                if activated and z["feature"] is not None:
                    m.update_reward(z["bucket"],arm,c["sha256"],
                        par2(baseline,c["cap_s"]),par2(z,c["cap_s"]),
                        z["activation_s"],z["windows"],z["feature"])
                row=dict(i=i,sha256=c["sha256"],arm=arm,activated=activated,
                         status_baseline=baseline["status"],
                         status_candidate=z["status"],
                         baseline_par2_s=par2(baseline,c["cap_s"]),
                         candidate_par2_s=par2(z,c["cap_s"]),
                         benefit_s=par2(baseline,c["cap_s"])-par2(z,c["cap_s"]),
                         bucket=z["bucket"],callback_wakeups=z["callback_wakeups"],
                         useful_training_sample=activated and z["feature"] is not None)
                records.append(row)
                write(ROOT/"training-trials.json",records)
                print("NMR4_TRAIN",json.dumps(row,sort_keys=True),flush=True)
        summary={}
        for arm in (1,2):
            rows=m.global_stats(arm)
            summary[str(arm)]=dict(samples=len(rows),
                positive=sum(x[0]>.02 for x in rows),
                negative=sum(x[0]<-.02 for x in rows),
                net_par2_gain_s=sum(x[0] for x in rows))
        report=dict(protocol=PROTOCOL,training_sources=34,
                    informative_attempts=sum(x["useful_training_sample"] for x in records),
                    trained=summary,model_updates=m.base.model.policy.updates,
                    migration="prior R3 persistent model, training-only update",
                    holdout_contamination=False,
                    limitation="previously inspected R2/R3 holdout reused")
        write(ROOT/"training.json",report)
        print("NMR4_TRAIN_PASS",json.dumps(report,sort_keys=True),flush=True)
    finally:m.close()

def trial(c,rep,mode,override,driver,clean,r3driver,memory):
    source=SOURCE/(c["id"]+".cnf")
    z=r4.run_case(source,driver,clean,r3driver,float(c["cap_s"]),
                  mode,memory,arm_override=override if mode=="r4_explore" else None)
    validate(c,z)
    return dict(id=c["id"],sha256=c["sha256"],origin=c["origin"],
                family=c["family"],rep=rep,mode=mode,status=z["status"],
                cap_s=float(c["cap_s"]),wall_s=round(z["elapsed_s"],7),
                par2_s=round(par2(z,c["cap_s"]),7),reason=z["reason"],
                windows=z["windows"],callback_wakeups=z["callback_wakeups"],
                activation_s=round(z["activation_s"],8),
                selected_arm=z["selected_arm"],
                exploration_assignment=override if mode=="r4_explore" else None,
                proof=z["proof"])

def shard(index,driver,clean,r3driver,path):
    d,assign=verify()
    need(0<=index<SHARDS,"bad shard")
    mem=r4.UtilityBandit(path,False)
    rows=[]
    try:
        for i in range(index,len(d["testing"]),SHARDS):
            c=d["testing"][i]
            for rep in range(REPS):
                order=list(MODES)
                random.Random(PROTOCOL+c["sha256"]+str(rep)).shuffle(order)
                for mode in order:
                    row=trial(c,rep,mode,assign[(i,rep)],driver,clean,
                              r3driver,mem)
                    rows.append(row)
                    write(ROOT/f"shard-{index}.json",rows)
                    print("NMR4_TRIAL",json.dumps({
                        k:row[k] for k in ("id","mode","status","wall_s",
                                "reason","windows","callback_wakeups",
                                "activation_s")}),flush=True)
        expected=len(d["testing"][index::SHARDS])*REPS*len(MODES)
        need(len(rows)==expected,"incomplete paired block")
        print("NMR4_SHARD_PASS",index,len(rows),flush=True)
    finally:mem.close()

def audit():
    d,assignment=verify()
    cases={c["sha256"]:c for c in d["testing"]}
    rows=[]
    for i in range(SHARDS):
        part=read(ROOT/f"shard-{i}.json")
        need(len(part)==len(d["testing"][i::SHARDS])*REPS*len(MODES),
             "missing shard")
        rows.extend(part)
    need(len(rows)==len(d["testing"])*REPS*len(MODES),"wrong total")
    grouped=collections.defaultdict(dict)
    idx={c["sha256"]:j for j,c in enumerate(d["testing"])}
    for row in rows:
        need(row["sha256"] in cases and row["id"]==cases[row["sha256"]]["id"],
             "source identity drift")
        key=(row["sha256"],row["rep"])
        need(row["mode"] not in grouped[key],"duplicate mode")
        grouped[key][row["mode"]]=row
        expected=2*row["cap_s"] if row["status"]=="TIMEOUT" else row["wall_s"]
        need(abs(row["par2_s"]-expected)<1e-5,"PAR2 mismatch")
        if row["mode"]=="r4_explore":
            need(row["exploration_assignment"]==
                 assignment[(idx[row["sha256"]],row["rep"])],
                 "exploration plan leak/drift")
        if row["status"]=="SAT":
            need(row["proof"] in ("SAT_WITNESS_VERIFIED_SOURCE",
                  "ORIGINAL_CNF_SAT_WITNESS_CHECKED",
                  "SAT_WITNESS_CHECKED_ORIGINAL_SHA"),"unchecked SAT witness")
    for key,arms in grouped.items():
        need(set(arms)==set(MODES),"missing comparison arm")
        consistent={a["status"] for a in arms.values() if a["status"]!="TIMEOUT"}
        need(len(consistent)<=1,"contradictory SAT/UNSAT result")
    summary={}
    for mode in MODES:
        part=[x for x in rows if x["mode"]==mode]
        summary[mode]=dict(
            trials=len(part),
            solved=sum(x["status"]!="TIMEOUT" for x in part),
            par2_s=round(sum(x["par2_s"] for x in part),6),
            wall_s=round(sum(x["wall_s"] for x in part),6),
            activated=sum(x["activation_s"]>0 for x in part),
            windows=sum(x["windows"] for x in part),
            callbacks=sum(x["callback_wakeups"] for x in part),
            abstentions=sum("abstain" in x["reason"] or
                            "no_positive_calibration"==x["reason"] or
                            "no_contextual_gain"==x["reason"] for x in part))
    comparisons={}
    for mode in MODES[1:]:
        wins=losses=ties=0
        paired=[]
        for group in grouped.values():
            a=group["clean"];b=group[mode]
            if b["par2_s"]<a["par2_s"]*.995:wins+=1
            elif b["par2_s"]>a["par2_s"]*1.005:losses+=1
            else:ties+=1
            if a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT":
                paired.append(a["wall_s"]/max(.0000001,b["wall_s"]))
        comparisons[mode]=dict(wins=wins,losses=losses,ties=ties,
            geometric_speedup_both_solved=round(math.exp(
                statistics.mean(math.log(x) for x in paired)),5) if paired else None,
            compared_solved_pairs=len(paired))
    report=dict(protocol=PROTOCOL,status="AUDIT_PASS_NOT_BLIND",
       sources=40,attempts=len(rows),repetitions=REPS,
       precommitted_exploration_plan=sha(PLAN),
       known_prior_holdout=True,
       correctness="SAT witness checked on unchanged source; native UNSAT lacks LRAT",
       primary="solved count and PAR2 including source scan and controller overhead",
       summary=summary,comparisons=comparisons)
    write(ROOT/"report.json",report)
    write(ROOT/"trials.json",rows)
    with (ROOT/"trials.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    lines=["# NMR R4 — bounded exploration versus R3 and clean CaDiCaL","",
        "40 sources, two repeats, six modes, 480 attempts. NOT a blind holdout.",
        "", "| Mode | Solved | PAR2 (s) | Probes | Callback wakeups |",
        "|---|---:|---:|---:|---:|"]
    for mode,x in summary.items():
        lines.append(f"| {mode} | {x['solved']}/{x['trials']} | {x['par2_s']} | {x['activated']} | {x['callbacks']} |")
    lines+=["","## Paired speed (both solved)","",
      "| Mode | Wins | Losses | Ties | Geomean speedup |",
      "|---|---:|---:|---:|---:|"]
    for mode,x in comparisons.items():
        lines.append(f"| {mode} | {x['wins']} | {x['losses']} | {x['ties']} | {x['geometric_speedup_both_solved']} |")
    lines+=["","Training-only utility memory. Source SHA used for audit identity, never model input.",
       "Random exploration allocated by fixed shuffled index list before test results.",
       "Unsolved timeouts receive PAR2. No claim of general SAT advantage or mathematical periodicity.",
       "No independently verified LRAT for native UNSAT."]
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("NMR4_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    r4.selftest()
    print("NMR4_BENCH_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("selftest","prepare","verify","train","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--driver",default="nmr_r4/nmr4-driver")
    p.add_argument("--clean",default="new_horizon/r190-driver")
    p.add_argument("--r3driver",default="nmr_r3/nmr3-driver")
    p.add_argument("--memory",default="nmr_r4/model.sqlite")
    args=p.parse_args()
    if args.command=="selftest":selftest()
    elif args.command=="prepare":prepare()
    elif args.command=="verify":
        print("NMR4_VERIFY_PASS",len(verify()[0]["testing"]),flush=True)
    elif args.command=="train":
        train(args.driver,args.clean,args.r3driver,args.memory)
    elif args.command=="shard":
        shard(args.shard,args.driver,args.clean,args.r3driver,args.memory)
    else:audit()
