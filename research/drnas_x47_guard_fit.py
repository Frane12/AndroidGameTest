#!/usr/bin/env python3
"""X4.7: fit a conservative tail-regret and pre-probe gate on TRAIN/VAL only.

Uses X4.6's already fitted source-disjoint logistic P(flip cheaper).
The risk amplitudes come from source-weighted, independently verified
completed counterfactuals in TRAIN ONLY. The only selection data are the
21 previously separated VALIDATION source CNFs. No new holdout outcomes enter.
"""
from __future__ import annotations
from collections import defaultdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

import drnas_x45_matched_branches as X45
import drnas_x46_cost_train as X46

def source_indexed_samples(path):
    entries,_=X46.extract(path)
    raw=[json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]
    table=defaultdict(dict)
    for r in raw:
        if r["arm"] in ("CORE","FLIP","X46_8"):
            table[(r["sha256"],r["checkpoint"],r["rep"])][r["arm"]]=r
    result=[]
    info={}
    for e in entries:
        key=(e["source"],e["checkpoint"],e["rep"])
        x=table[key]
        if len(x)!=3:raise AssertionError("unbalanced matched pair")
        if e["source"] not in info:
            case=X45.make_case(e["family"],e["source_id"])
            assert case["sha256"]==e["source"],"source generator changed"
            info[e["source"]]=(case["n"],len(case["clauses"]))
        n,nclauses=info[e["source"]]
        result.append({**e,
            "nvars":n,"nclauses":nclauses,
            "base_e2e_PAR2":x["CORE"]["PAR2"],
            "flip_e2e_PAR2":x["FLIP"]["PAR2"],
            "probe_ms":x["X46_8"]["probe_wall_ms"]})
    return result

def source_mean(items,key):
    grouped=defaultdict(list)
    for r in items:grouped[r["source"]].append(r[key])
    return statistics.mean(statistics.mean(v) for v in grouped.values())

def estimate_magnitude(train):
    bysource=defaultdict(list)
    for r in train:bysource[r["source"]].append(r["flip_saving"])
    wins=[];regrets=[]
    for records in bysource.values():
        wins.extend(max(0,x)/len(records) for x in records)
        regrets.extend(max(0,-x)/len(records) for x in records)
    # Across all training sources, the source-weighted magnitudes are nonzero
    # only if some completed matched continuations differ.
    pos_total=sum(wins);neg_total=sum(regrets)
    n=len(bysource)
    if not pos_total or not neg_total or n<15:
        raise AssertionError("need >=15 independent sources with both cost directions")
    positive=[x["flip_saving"] for x in train if x["flip_saving"]>0]
    negative=[-x["flip_saving"] for x in train if x["flip_saving"]<0]
    positive.sort();negative.sort()
    return {
        "avg_win":statistics.mean(positive),
        "avg_regret":statistics.mean(negative),
        "p90_regret":negative[int(.90*(len(negative)-1))],
        "source_weighted_unconditional_win":pos_total/n,
        "source_weighted_unconditional_regret":neg_total/n,
        "source_count":n,
    }

def candidates():
    # Modest, preregistered menu; default "skip" competes with all probes.
    return [
        {"name":"NO_PROBE","min_vars":100000,"min_clauses":0,"max_k":1,"floor":1.,"minimum":100000.,"risk":2.},
        {"name":"VERY_HIGH_CONF","min_vars":0,"min_clauses":0,"max_k":8,"floor":.95,"minimum":20.,"risk":2.},
        {"name":"HIGH_CONF","min_vars":0,"min_clauses":0,"max_k":8,"floor":.85,"minimum":10.,"risk":1.5},
        {"name":"MEDIUM_CONF","min_vars":0,"min_clauses":0,"max_k":4,"floor":.75,"minimum":10.,"risk":1.5},
        {"name":"LONG_DENSE","min_vars":38,"min_clauses":230,"max_k":4,"floor":.85,"minimum":12.,"risk":1.},
        {"name":"LONG_VERY_DENSE","min_vars":42,"min_clauses":300,"max_k":2,"floor":.90,"minimum":20.,"risk":2.},
        {"name":"LATE_DENSE","min_vars":38,"min_clauses":230,"max_k":8,"floor":.90,"minimum":20.,"risk":1.5},
    ]

def simulate(row,model,mag,choice):
    eligible=(row["nvars"]>=choice["min_vars"]
              and row["nclauses"]>=choice["min_clauses"]
              and row["checkpoint"]<=choice["max_k"])
    if not eligible:return 0.0,False,False
    p=X46.predict(model,row["features"])
    expected=(p*mag["avg_win"]-(1-p)*(mag["avg_regret"]+
                 choice["risk"]*mag["p90_regret"]))
    flip=(p>model["threshold"] and p>choice["floor"] and
          expected>=choice["minimum"])
    # Actual flipped end-to-end time is known only in offline VALIDATION,
    # never in the native X47 decision. Probe time is a separate cost.
    # Avoid double charging probe overhead: CORE/FLIP arms have no probes.
    saving=row["base_e2e_PAR2"]-(row["flip_e2e_PAR2"] if flip
                                else row["base_e2e_PAR2"])
    return saving-row["probe_ms"]/1000,True,flip

def select_validation(val,model,mag):
    bysource=defaultdict(list)
    for r in val:bysource[r["source"]].append(r)
    summaries=[]
    for choice in candidates():
        per_source=[]
        prompted=flip_count=0
        for items in bysource.values():
            net=[]
            for row in items:
                delta,probe,flip=simulate(row,model,mag,choice)
                net.append(delta)
                prompted+=int(probe);flip_count+=int(flip)
            per_source.append(statistics.mean(net))
        mean=statistics.mean(per_source)
        std=statistics.stdev(per_source) if len(per_source)>1 else 0.
        lb=mean-1.64*std/math.sqrt(len(per_source))
        summaries.append({**choice,"validation_source_mean_net_s":round(mean,9),
             "validation_one_sided_conservative_bound_s":round(lb,9),
             "probe_count":prompted,"flip_count":flip_count})
    # For measured positive gain, require a conservative positive lower bound
    # on a separate 21-source validation set. Otherwise keep standard CORE.
    positive=[x for x in summaries if x["validation_one_sided_conservative_bound_s"]>0]
    if positive:
        selected=max(positive,key=lambda x:(x["validation_one_sided_conservative_bound_s"],
                                             -x["probe_count"]))
    else:selected=summaries[0]
    return selected,summaries

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trials",type=Path,required=True)
    p.add_argument("--frozen-cost-model",type=Path,required=True)
    p.add_argument("--guard-output",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    samples=source_indexed_samples(a.trials)
    frozen=json.loads(a.frozen_cost_model.read_text())
    if frozen["version"]!="X46COST1":raise ValueError("X46 frozen cost model invalid")
    train=[r for r in samples if r["source_id"]%4!=0]
    validation=[r for r in samples if r["source_id"]%4==0]
    if len({x["source"] for x in train if x["label"]!="equal_conflicts"})!=frozen["train_distinct_sources"]:
        raise AssertionError("frozen model trained against different non-tied training sources")
    if not validation:raise AssertionError("validation absent")
    magnitude=estimate_magnitude(train)
    selected,menu=select_validation(validation,frozen,magnitude)
    a.guard_output.parent.mkdir(parents=True,exist_ok=True)
    with a.guard_output.open("w") as fd:
        fd.write("X47GUARD1 1\n")
        fd.write(f"{selected['min_vars']} {selected['min_clauses']} {selected['max_k']} "
                 f"{selected['floor']:.17g} {selected['minimum']:.17g} "
                 f"{magnitude['avg_win']:.17g} {magnitude['avg_regret']:.17g} "
                 f"{magnitude['p90_regret']:.17g} {selected['risk']:.17g}\n")
    digest=hashlib.sha256(a.guard_output.read_bytes()).hexdigest()
    report={
        "source_selection":"source_id % 4: train!=0 validation==0",
        "training_original_sources":len({r["source"] for r in train}),
        "validation_original_sources":len({r["source"] for r in validation}),
        "training_only_regret_distribution":magnitude,
        "validation_candidate_menu":menu,
        "selected_guard":selected,
        "cost_model_sha256":hashlib.sha256(a.frozen_cost_model.read_bytes()).hexdigest(),
        "risk_guard_sha256":digest,
        "frozen_before_fresh_holdout":True,
        "holdout_outcomes_not_seen":True,
        "regret_tail_uses_training_full_paths_only":True,
        "preprobe_gate_uses_nvars_clauses_and_checkpoint_only":True,
        "important_limit":"Time-based gate selection on 21-source validation is noisy. Predefined no-probe option is preferred if no conservative gain."
    }
    a.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("X47_GUARD_FROZEN "+json.dumps({
        "train_sources":report["training_original_sources"],
        "validation_sources":report["validation_original_sources"],
        "guard_choice":selected["name"],
        "validation_net_s":selected["validation_source_mean_net_s"],
        "validation_bound_s":selected["validation_one_sided_conservative_bound_s"],
        "guard_sha256":digest,
        "train_avg_win":magnitude["avg_win"],
        "train_p90_regret":magnitude["p90_regret"]},sort_keys=True),flush=True)

if __name__=="__main__":main()
