#!/usr/bin/env python3
"""Inspect MEMORY2 statistical coverage and concrete future-horizon trajectories.

Descriptive diagnostic, NOT causal inference or a probability of SAT.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

HORIZONS=(16,64,256)
ARMS=("saved_phase","inverted_phase")

def load_policy(path):
    lines=path.read_text().splitlines()
    assert lines and lines[0]=="X1MEMORY2 64 2 3","unexpected MEMORY2 model version"
    by_context={}
    totals={name:{str(h):0 for h in HORIZONS} for name in ARMS}
    for line in lines[1:]:
        c,a,h,n,rsq,sumsq=line.split()
        c,a,h,n=int(c),int(a),int(h),int(n)
        val=float(rsq)
        assert 0<=c<64 and a in (0,1) and 0<=h<3
        row=by_context.setdefault(c,{name:{} for name in ARMS})
        row[ARMS[a]][str(HORIZONS[h])]={"samples":n,"mean_proxy":round(val/n,5) if n else None}
        totals[ARMS[a]][str(HORIZONS[h])]+=n
    contexts=[]
    for c,arms in by_context.items():
        count=sum(x["samples"] for data in arms.values() for x in data.values())
        if not count:continue
        contexts.append({"context":c,"samples_total":count,
            "features":{"dense_formula":bool(c&2),"binary_heavy_formula":bool(c&1),
                "high_degree_selected_var":bool(c&4),
                "high_binary_incidence":bool(c&8),"conflict_pressure":bool(c&16),
                "previous_step_had_strong_immediate_proxy":bool(c&32)},
            "by_action":arms})
    contexts.sort(key=lambda x:x["samples_total"],reverse=True)
    confidence={
        "h16_arms_with_data":all(totals[a]["16"]>0 for a in ARMS),
        "h64_arms_with_data":all(totals[a]["64"]>0 for a in ARMS),
        "h256_arms_with_data":all(totals[a]["256"]>0 for a in ARMS),
        "contexts_with_any_data":len(contexts),
        "contexts_with_both_actions_h16":sum(
            bool(c["by_action"]["saved_phase"]["16"]["samples"] and
                 c["by_action"]["inverted_phase"]["16"]["samples"]) for c in contexts)
    }
    return {"total_observations_by_arm_horizon":totals,
            "coverage":confidence,"most_observed_contexts":contexts[:12]}

def trace_summary(path):
    events=[json.loads(x) for x in path.read_text().splitlines()]
    assert events and events[-1]["event"]=="outcome"
    contexts={}
    horizons={str(h):{"observed":0,"censored":0} for h in HORIZONS}
    start={}
    examples=[]
    for event in events:
        t=event["event"]
        if t=="before_action":
            start[event["id"]]=event
        elif t=="after_action":
            contexts[event["context"]]=contexts.get(event["context"],0)+1
        elif t=="horizon":
            h=str(event["horizon"])
            horizons[h]["observed" if event["observed"] else "censored"]+=1
            if event["observed"] and len(examples)<12:
                begin=start.get(event["id"])
                if begin:
                    examples.append({"episode":event["id"],"horizon":event["horizon"],
                        "context":begin["context"],"action":begin["action"],
                        "start_decisions":begin["state"]["decisions"],
                        "future_observed_decisions":event["decisions"],
                        "reward_proxy":event["reward_proxy"],
                        "predicted_weighted_proxy":begin["expected_utility"][
                            1 if begin["action"]=="inverted_phase" else 0]})
    return {"path":str(path),"outcome":events[-1],
        "horizon_events":horizons,"contexts":contexts,"examples":examples}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--policy",type=Path,required=True)
    parser.add_argument("--trace",type=Path)
    parser.add_argument("--out",type=Path)
    args=parser.parse_args()
    result={"version":"MEMORY2_INSPECT_V1","model":load_policy(args.policy),
            "statistics_not_causal":True,
            "cannot_infer_proven_SAT_probability":True,
            "unobserved_horizons_are_censored_not_training_data":True}
    if args.trace:
        result["sample_trace"]=trace_summary(args.trace)
    if args.out:
        args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("X1_M2_INSPECT "+json.dumps(result,sort_keys=True,separators=(",",":")),flush=True)

if __name__=="__main__":
    main()
