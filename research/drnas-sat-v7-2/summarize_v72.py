#!/usr/bin/env python3
"""V7.2 statistics: paired independent cases, selection precision and cost.
All cases count, including regressions and rejected instances. No filters.
"""
import argparse
import csv
import json
import math
import random
import statistics
from collections import defaultdict,Counter
from pathlib import Path

METHODS=("plain","majority","selective","gated_random")

def summarize(path, outfile):
    rows=list(csv.DictReader(open(path,newline="",encoding="utf8")))
    if not rows:raise RuntimeError("Empty measurements")
    times=defaultdict(lambda:defaultdict(list))
    props={}
    families=defaultdict(list)
    answers=defaultdict(set)
    for row in rows:
        case=row["case"]
        times[case][row["method"]].append(float(row["elapsed_us"])/1000)
        answers[case].add(row["answer"])
        props[(case,row["method"])]=row
    ids=sorted(times)
    for case in ids:
        if set(times[case])!=set(METHODS) or len(set(map(len,times[case].values())))!=1:
            raise AssertionError(f"Missing/repeat mismatch in {case}")
        if len(answers[case])!=1:raise AssertionError("SAT/UNSAT mismatch "+case)
        families[props[(case,"plain")]["family"]].append(case)
    med={case:{m:statistics.median(times[case][m]) for m in METHODS} for case in ids}
    selected={k for k in ids if props[(k,"selective")]["selected"]=="1"}
    def aggregate(subset,method):
        if not subset:return None
        plain=sum(med[k]["plain"] for k in subset)
        vals=sum(med[k][method] for k in subset)
        ratios=[med[k]["plain"]/max(med[k][method],1e-12) for k in subset]
        return {
            "cases":len(subset),
            "sum_medians_ms":round(vals,6),
            "speedup_plain_over_method":round(plain/max(vals,1e-12),6),
            "median_paired_ratio":round(statistics.median(ratios),6),
            "faster_cases":sum(med[k][method]<med[k]["plain"] for k in subset),
            "slower_cases":sum(med[k][method]>med[k]["plain"] for k in subset),
        }
    totals={m:aggregate(ids,m) for m in METHODS}
    inselected={m:aggregate(sorted(selected),m) for m in METHODS}
    rejected={m:aggregate([k for k in ids if k not in selected],m) for m in METHODS}
    fam={name:{"selected":sum(k in selected for k in keys),
               "methods":{m:aggregate(keys,m) for m in METHODS}}
         for name,keys in sorted(families.items())}
    # Any gain >=5% is called beneficial. Using baseline vs fully evaluated
    # majority serves only as a post-hoc *diagnostic label*, never used by gate.
    worthwhile={k for k in ids if med[k]["majority"] <= 0.95*med[k]["plain"]}
    TP=len(selected & worthwhile)
    FP=len(selected - worthwhile)
    FN=len(worthwhile - selected)
    TN=len(set(ids) - selected - worthwhile)
    rng=random.Random(20261122)
    bootstrap={}
    for method in METHODS[1:]:
        sampled_ratios=[]
        for _ in range(2000):
            batch=[rng.choice(ids) for __ in ids]
            a=sum(med[k]["plain"] for k in batch)
            b=sum(med[k][method] for k in batch)
            sampled_ratios.append(a/max(b,1e-12))
        sampled_ratios.sort()
        bootstrap[method]=[round(sampled_ratios[49],6),round(sampled_ratios[1950],6)]
    gate_rows=[r for r in rows if r["method"]=="selective"]
    summary={
        "instances":len(ids),
        "repetitions":len(rows)//(len(ids)*len(METHODS)),
        "verified_sat_unsat":len(ids),
        "answer_count":dict(Counter(next(iter(answers[k])) for k in ids)),
        "selected_cases":len(selected),
        "rejected_cases":len(ids)-len(selected),
        "timings":totals,
        "when_selected":inselected,
        "when_rejected":rejected,
        "by_family":fam,
        "gate_accuracy_5pct_gain_target":{
            "definition":"positive iff unconditional majority median wall time <=0.95 * plain median, diagnostic only",
            "TP":TP,"FP":FP,"FN":FN,"TN":TN,
            "precision":round(TP/max(1,TP+FP),4),
            "recall":round(TP/max(1,TP+FN),4),
            "false_positive_rate":round(FP/max(1,FP+TN),4),
        },
        "selectivity_cost":{
            "mean_gate_and_hint_us":round(statistics.mean(float(r["analysis_us"]) for r in gate_rows),5),
            "mean_gate_only_us_for_rejected":round(statistics.mean([float(r["analysis_us"]) for r in gate_rows if r["selected"]=="0"] or [0.0]),5),
            "median_gate_and_hint_us":round(statistics.median(float(r["analysis_us"]) for r in gate_rows),5),
            "mean_hints_on_selected":round(statistics.mean([int(r["hint_count"]) for r in gate_rows if r["selected"]=="1"] or [0]),2),
        },
        "paired_instance_bootstrap_95pct_speedup":bootstrap,
        "caveats":[
            "Synthetic seeded cases, not an external SAT Competition dataset.",
            "Gate thresholds fixed using v7.1 development family observations, not these cases.",
            "3 repeats yield noisy per-case benefit labels; precision/recall are exploratory.",
            "SAT models checked; UNSAT determined by agreement of unchanged CaDiCaL across methods.",
            "All hint computation and solver setup timed; DIMACS reading excluded for all methods.",
            "Aggregation is sum of per-case median wall times, not total CI execution time.",
            "Do not infer broad generalization or novel SAT complexity results from this run."
        ],
    }
    Path(outfile).write_text(json.dumps(summary,indent=2),encoding="utf8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("by_family","when_selected","when_rejected")},indent=2))
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    summarize(a.csv,a.out)
