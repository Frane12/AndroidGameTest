#!/usr/bin/env python3
"""Summarize actual paired native C++ SAT timings without excluding failures."""
import argparse
import csv
import json
import random
import statistics
from collections import defaultdict,Counter
from pathlib import Path

def median(x):
    return statistics.median(x)

def main(csv_path, out):
    rows=list(csv.DictReader(open(csv_path,newline="")))
    by_case=defaultdict(lambda:defaultdict(list))
    metadata={}
    for r in rows:
        by_case[r["case"]][r["method"]].append(float(r["elapsed_us"]))
        metadata[r["case"]]=(r["family"],r["result"])
    methods=("cadical_plain","native_hybrid","cut_assumptions")
    pair={}
    for k,d in by_case.items():
        if set(d)!=set(methods):
            raise ValueError(f"Missing method on {k}: {list(d)}")
        if len(set(map(len,d.values())))!=1:
            raise ValueError(f"Unequal repetitions: {k}")
        pair[k]={m:median(d[m])/1000 for m in methods}
    summaries={}
    for m in methods:
        times=[pair[k][m] for k in pair]
        baseline=[pair[k]["cadical_plain"] for k in pair]
        summaries[m]={
            "sum_of_case_medians_ms":round(sum(times),6),
            "median_case_ms":round(median(times),6),
            "cases_faster_than_plain":sum(t<b for t,b in zip(times,baseline)) if m!="cadical_plain" else None,
            "median_case_speed_ratio_plain_over_method":round(median(b/t for b,t in zip(baseline,times)),5),
            "aggregate_speed_ratio_plain_over_method":round(sum(baseline)/sum(times),6)
        }
    groups=defaultdict(list)
    for k,(fam,result) in metadata.items():
        groups[fam].append(k)
    family={}
    for fam,ids in sorted(groups.items()):
        item={"cases":len(ids),"SAT":sum(metadata[k][1]=="SAT" for k in ids),"UNSAT":sum(metadata[k][1]=="UNSAT" for k in ids)}
        for m in methods:
            t=sum(pair[k][m] for k in ids)
            baseline=sum(pair[k]["cadical_plain"] for k in ids)
            item[m+"_sum_medians_ms"]=round(t,6)
            if m!="cadical_plain":
                item[m+"_speed_ratio"]=round(baseline/t,5)
                item[m+"_faster_cases"]=sum(pair[k][m]<pair[k]["cadical_plain"] for k in ids)
        family[fam]=item
    # Bootstrap resamples complete paired instances, not individual time readings.
    rng=random.Random(20261117)
    ids=list(pair)
    ci={}
    for m in methods[1:]:
        estimates=[]
        for _ in range(2000):
            sampled=[rng.choice(ids) for __ in ids]
            estimates.append(sum(pair[k]["cadical_plain"] for k in sampled)/
                             sum(pair[k][m] for k in sampled))
        estimates.sort()
        ci[m]=[round(estimates[50],5),round(estimates[1949],5)]
    selected=Counter()
    for r in rows:
        if r["method"]=="native_hybrid" and r["selected"]=="1":
            selected[r["case"]]+=1
    selected_calls=[int(r["calls"]) for r in rows if r["method"]=="native_hybrid" and r["selected"]=="1"]
    result={
        "cases":len(pair),"repetitions":len(rows)//(len(pair)*3),
        "all_methods_agreed":True,
        "selected_cases":len(selected),
        "selected_calls_avg":round(statistics.mean(selected_calls),3) if selected_calls else 0,
        "method_stats":summaries,
        "per_family":family,
        "bootstrap_95pct_paired_case_speed_ratio":ci,
        "caveats":[
            "Synthetic seeded instances, not an external benchmark corpus.",
            "This benchmark compares matched native in-process CaDiCaL 3.0.1 calls.",
            "Loading DIMACS files is excluded for all methods, but graph analysis and solver creation are included.",
            "Microsecond-scale cases are sensitive to runner noise and cache order.",
            "Bootstrap interval only measures sampled-instance variability, not generalization to SAT Competition."
        ]
    }
    out=Path(out)
    out.write_text(json.dumps(result,indent=2),encoding="utf8")
    print(json.dumps(result,indent=2))
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    main(args.csv,args.out)
