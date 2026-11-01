#!/usr/bin/env python3
"""V18.0: train a *preemptive* single-split SAT regression gate.

All labels are derived from a complete paired run of BASELINE, SWITCH1024
and SWITCH2048 on previously explored development formulas only. Features
come from baseline's original 512-conflict checkpoint BEFORE intervention.
The new 180xxx prospective holdout is never accessed by this script.
"""
from __future__ import annotations
import argparse,json,statistics
from pathlib import Path
from preemptive_common_v180 import (PINNED,CAP,BASE_MODES,FIELDS,
    fresh_case,execute,write_csv,write_json,is_bad,is_good,rank,sha_file)

SEEDS=tuple(range(177100,177120))+tuple(range(178100,178110))+tuple(range(179100,179112))
assert len(SEEDS)==42
ACTIONS=(0,1024,2048)
OPTIONS=((0,1024),(1024,0),(0,2048),(2048,0))

def choose(c,rule):
    if rule is None or c["features"] is None:return 0
    feature,op,thr,yes,no=rule
    cond=(c["features"][feature]<thr) if op=="lt" else (c["features"][feature]>=thr)
    return yes if cond else no

def evaluate(cases,rule):
    m={"gain":0.0,"good":0,"bad":0,"switched":0,"skipped":0,"rescues":0,
       "changed_solved_to_timeout":0}
    for c in cases:
        act=choose(c,rule)
        b=c["baseline"]
        r=c["switch"+str(act)] if act else b
        m["gain"]+=b["par2"]-r["par2"]
        if act:
            m["switched"]+=1
            m["good"]+=int(is_good(b,r))
            m["bad"]+=int(is_bad(b,r))
            m["rescues"]+=int(b["status"]=="TIMEOUT" and r["status"] in ("SAT","UNSAT"))
            m["changed_solved_to_timeout"]+=int(
                b["status"] in ("SAT","UNSAT") and r["status"]=="TIMEOUT")
        else:m["skipped"]+=1
    m["net_score"]=round(m["gain"]-2.5*m["bad"]-0.05*m["switched"],8)
    m["gain"]=round(m["gain"],8)
    return m

def fit(cases):
    best=None
    fit_metrics=None
    for feature in FIELDS:
        distinct=sorted({c["features"][feature] for c in cases if c["features"] is not None})
        for left,right in zip(distinct,distinct[1:]):
            t=(left+right)/2
            for op in ("lt","ge"):
                for a,b in OPTIONS:
                    r=(feature,op,t,a,b)
                    m=evaluate(cases,r)
                    if m["switched"]<4 or m["skipped"]<4:continue
                    if m["good"]<2 or m["changed_solved_to_timeout"]>0:continue
                    if m["bad"]>1 or m["net_score"]<=0:continue
                    merit=(m["net_score"],m["good"],-m["bad"],
                           -m["switched"])
                    if best is None or merit>best[0]:
                        best=(merit,r)
                        fit_metrics=m
    return (best[1],fit_metrics) if best is not None else (None,None)

def leave_one_out(cases):
    predictions=[]
    for i,held in enumerate(cases):
        model,_=fit(cases[:i]+cases[i+1:])
        act=choose(held,model)
        r=held["switch"+str(act)] if act else held["baseline"]
        b=held["baseline"]
        predictions.append({"seed":held["seed"],"action":act,
            "bad":int(is_bad(b,r)),"good":int(is_good(b,r)),
            "baseline_par2":b["par2"],"policy_par2":r["par2"]})
    return {
      "n":len(predictions),
      "PAR2_baseline":round(statistics.mean(x["baseline_par2"] for x in predictions),6),
      "PAR2_predicted":round(statistics.mean(x["policy_par2"] for x in predictions),6),
      "bad_actions":sum(x["bad"] for x in predictions),
      "good_actions":sum(x["good"] for x in predictions),
      "switches":sum(x["action"]!=0 for x in predictions),
      "predictions":predictions}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--solver",type=Path,required=True)
    p.add_argument("--root",type=Path,required=True)
    a=p.parse_args()
    a.root.mkdir(parents=True,exist_ok=True)
    cases=[fresh_case(a.root,seed,seed-seed%100) for seed in SEEDS]
    write_json(a.root/"manifest.json",{
        "version":"V18.0","stage":"train","source":"only previously explored 177xxx/178xxx/179xxx formulas",
        "seeds":SEEDS,"modes":BASE_MODES,
        "pin":PINNED,"cap":CAP,
        "labels":{"BAD":"solved->timeout OR >=1.5x AND >=0.15s slower",
                  "GOOD":"timeout->solved OR >=25pct AND >=0.1s faster"},
        "feature_source":"baseline, conflict 512, before interventions",
        "candidate":"single split on one of r/d/p/g/l, with SKIP vs SWITCH1024 or SWITCH2048",
        "no_holdout_training":True,"cases":cases})
    attempts=[]
    examples=[]
    print("V180_TRAIN_START",len(cases)*len(BASE_MODES),"paired trials",flush=True)
    for c in cases:
        paired={}
        for mode in BASE_MODES:
            row=execute(a.solver,c,mode,0,a.root)
            paired[mode]=row
            attempts.append({k:v for k,v in row.items() if k!="features"})
            print("V180_TRAIN_MEASURE",c["seed"],mode,row["status"],
                  f'{row["wall"]:.5f}s',"conflicts",row["final_conflicts"],flush=True)
        assert len(paired)==3
        ans={r["status"] for r in paired.values() if r["status"] in ("SAT","UNSAT")}
        assert len(ans)<=1,"SAT/UNSAT outcome disagreement"
        if paired["baseline"]["features"] is not None:
            for m in ("switch1024","switch2048"):
                other=paired[m]["features"]
                if other is not None:
                    # If readings differ, fail rather than use non-equivalent pre-state.
                    for f in FIELDS:
                        if abs(paired["baseline"]["features"][f]-other[f])>1e-4:
                            raise RuntimeError(f"Pre-intervention trajectory difference {c['seed']}/{m}/{f}")
        example={"seed":c["seed"],"features":paired["baseline"]["features"],
                 **{m:paired[m] for m in BASE_MODES}}
        examples.append(example)
        print("V180_TRAIN_PAIR",c["seed"],
          "bad1024",int(is_bad(paired["baseline"],paired["switch1024"])),
          "bad2048",int(is_bad(paired["baseline"],paired["switch2048"])),
          "good1024",int(is_good(paired["baseline"],paired["switch1024"])),
          "good2048",int(is_good(paired["baseline"],paired["switch2048"])),flush=True)
        write_csv(a.root/"attempts.partial.csv",attempts)
    assert len(attempts)==126
    frozen,metrics=fit(examples)
    loo=leave_one_out(examples)
    # Retain the stronger safety rule: no unchecked deployment when LOO
    # produces no measurable benefit or more than one harmful selected case.
    acceptable=(frozen is not None and loo["PAR2_predicted"]<loo["PAR2_baseline"]
                and loo["bad_actions"]<=1 and loo["good_actions"]>=1)
    if not acceptable:
        frozen=None
        metrics=None
    if frozen is None:
        # Explicit abstention: unknown risk -> do not modify solver.
        rule=("g","lt",0.0,0,0)
    else:rule=frozen
    (a.root/"rule.txt").write_text(
        f"{rule[0]} {rule[1]} {rule[2]:.17g} {rule[3]} {rule[4]}\n")
    model={"version":"V18.0","rule":{
        "feature":rule[0],"op":rule[1],"threshold":rule[2],
        "pass_action":rule[3],"fail_action":rule[4]},
       "deployable_in_holdout":bool(acceptable),
       "abstain_reason":None if acceptable else "Insufficient conservative leave-one-formula-out evidence",
       "in_sample":metrics,"loo":loo,
       "baseline_PAR2":statistics.mean(c["baseline"]["par2"] for c in examples),
       "training_sha256":sha_file(a.root/"attempts.partial.csv"),
       "pin":PINNED,
       "frozen_before_holdout":True,
       "n_development_formulas":len(examples),
       "limitations":["Trained on prior synthetic 3SAT only",
          "One run/formula and a small candidate model family",
          "No proof that pre-conflict indicators identify the physical cause of a slowdown",
          "All 'regression' labels are relative to baseline and 2.5s timeout"]}
    write_json(a.root/"model.json",model)
    write_csv(a.root/"training.csv",[{
      "seed":c["seed"],**(c["features"] or {f:"" for f in FIELDS}),
      **{f"bad_{mode}":int(is_bad(c["baseline"],c[mode])) for mode in ("switch1024","switch2048")},
      **{f"good_{mode}":int(is_good(c["baseline"],c[mode])) for mode in ("switch1024","switch2048")},
      **{f"par2_{mode}":c[mode]["par2"] for mode in BASE_MODES}}
      for c in examples])
    write_csv(a.root/"attempts.csv",attempts)
    print("V180_FROZEN_RISK_RULE",json.dumps(
        {k:v for k,v in model.items() if k!="loo"},sort_keys=True),flush=True)
    print("V180_LOO_AUDIT",json.dumps({k:v for k,v in loo.items() if k!="predictions"},sort_keys=True),flush=True)

if __name__=="__main__":main()
