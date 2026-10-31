#!/usr/bin/env python3
"""DRNAS-SAT V7.2.1 independent matched benchmark analysis.
Selection precision defined in advance as counterfactual >=5% time gain of
unconditional majority vs unmodified CaDiCaL on each same CNF. This is noisy
for short formulas and is reported only as a diagnostic (not a proof).
"""
import argparse
import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

METHODS=("plain","majority","selective","confidence","confidence_random")

def summarize(input_file, output_file):
    records=list(csv.DictReader(open(input_file,newline="",encoding="utf8")))
    by=defaultdict(lambda:defaultdict(list))
    meta={}
    for row in records:
        id=row["case"]
        by[id][row["method"]].append(float(row["elapsed_us"])/1000)
        key=(id,row["method"])
        if key in meta and row["selected"]!=meta[key]["selected"]:
            raise AssertionError("Nondeterministic gate on "+id)
        meta[key]=row
    ids=sorted(by)
    if not ids:raise ValueError("Empty benchmark")
    stats={}
    for id in ids:
        methods=by[id]
        if set(methods)!=set(METHODS):
            raise AssertionError("Missing method: "+id)
        counts={len(v) for v in methods.values()}
        if len(counts)!=1 or min(counts)==0:
            raise AssertionError("Repetition mismatch: "+id)
        answers={meta[(id,m)]["answer"] for m in METHODS}
        if len(answers)!=1:
            raise AssertionError("SAT/UNSAT mismatch: "+id)
        stats[id]={m:statistics.median(methods[m]) for m in METHODS}
    def metrics(ids,method):
        if not ids:return None
        base=sum(stats[id]["plain"] for id in ids)
        total=sum(stats[id][method] for id in ids)
        ratios=[stats[id]["plain"]/max(stats[id][method],1e-12) for id in ids]
        return {
            "cases":len(ids),
            "sum_of_case_medians_ms":round(total,6),
            "speedup_plain_over_method":round(base/max(total,1e-12),6),
            "faster_cases":sum(stats[id][method]<stats[id]["plain"] for id in ids),
            "slower_cases":sum(stats[id][method]>stats[id]["plain"] for id in ids),
            "median_paired_speedup":round(statistics.median(ratios),6)
        }
    labels={id: stats[id]["majority"]<=0.95*stats[id]["plain"] for id in ids}
    def classify(method):
        chosen={id for id in ids if meta[(id,method)]["selected"]=="1"}
        positive={id for id in ids if labels[id]}
        TP=len(chosen & positive);FP=len(chosen-positive);FN=len(positive-chosen)
        TN=len(set(ids)-chosen-positive)
        return {
            "selected":len(chosen),"rejected":len(ids)-len(chosen),
            "true_positive":TP,"false_positive":FP,
            "false_negative":FN,"true_negative":TN,
            "precision":round(TP/max(1,TP+FP),5),
            "recall":round(TP/max(1,TP+FN),5),
            "false_positive_rate":round(FP/max(1,FP+TN),5),
            "when_selected":metrics(sorted(chosen),method),
            "when_rejected":metrics([id for id in ids if id not in chosen],method)
        }
    cost={}
    for method in METHODS:
        entries=[row for row in records if row["method"]==method]
        cost[method]={
            "mean_analysis_us":round(statistics.mean(float(r["analysis_us"]) for r in entries),5),
            "median_analysis_us":round(statistics.median(float(r["analysis_us"]) for r in entries),5),
            "rejected_mean_analysis_us":round(statistics.mean(
                [float(r["analysis_us"]) for r in entries if r["selected"]=="0"] or [0.0]),5),
            "selected_mean_analysis_us":round(statistics.mean(
                [float(r["analysis_us"]) for r in entries if r["selected"]=="1"] or [0.0]),5),
        }
    families=defaultdict(list)
    for id in ids:families[meta[(id,"plain")]["family"]].append(id)
    fam_stats={name:{
        "cases":len(its),
        "confidence_selected":sum(meta[(id,"confidence")]["selected"]=="1" for id in its),
        "old_selected":sum(meta[(id,"selective")]["selected"]=="1" for id in its),
        "methods":{m:metrics(its,m) for m in METHODS}}
        for name,its in sorted(families.items())}
    rng=random.Random(20261202)
    boot={}
    for method in METHODS[1:]:
        estimate=[]
        for _ in range(1200):
            sampled=[rng.choice(ids) for __ in ids]
            estimate.append(sum(stats[id]["plain"] for id in sampled)/
                            sum(stats[id][method] for id in sampled))
        estimate.sort()
        boot[method]=[round(estimate[29],6),round(estimate[1170],6)]
    report={
        "cases":len(ids),"repetitions":len(records)//(len(ids)*len(METHODS)),
        "verified_sat_unsat":len(ids),
        "answers":dict(Counter(meta[(id,"plain")]["answer"] for id in ids)),
        "methods":{m:metrics(ids,m) for m in METHODS},
        "selector":{m:classify(m) for m in ("selective","confidence","confidence_random")},
        "selection_rule":"V7.2: 3.20<=clauses/vars<=4.02; V7.2.1: 3.65<=clauses/vars<=4.10 AND 128-sample pair reuse<=0.030; n>=120, >=90% ternary in 64 sample",
        "precision_definition":"Counterfactual >=5% speed of unconditional majority-phase over plain. Due to noisy wall times, precision is exploratory.",
        "analysis_overhead_us":cost,
        "per_family":fam_stats,
        "paired_case_bootstrap_speedup_interval":boot,
        "caveats":[
            "Two historical V7.2 datasets informed V7.2.1 thresholds. Only new seeds are independent of threshold selection.",
            "Synthetic formulas with limited families; real SAT Competition benchmarks required.",
            "Microsecond timings on tiny cases can be dominated by scheduling noise.",
            "Costs include selection + hint generation + CaDiCaL setup and solve, excluding DIMACS read equally.",
            "SAT models independently checked. UNSAT determined by identical unmodified CaDiCaL answers, no proof certificates."
        ]
    }
    Path(output_file).write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps({k:v for k,v in report.items() if k!="per_family"},indent=2))
    return report
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    summarize(a.csv,a.out)
