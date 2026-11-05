#!/usr/bin/env python3
"""DRNAS SAT v7.1: paired, per-instance summary; no removal of slower cases."""
import argparse
import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

METHODS=("plain","majority","structural","random_phase")
def med(v):return statistics.median(v)

def analyze(csv_file, output_file, seed=20261119):
    rows=list(csv.DictReader(open(csv_file, newline="", encoding="utf8")))
    by_case=defaultdict(lambda:defaultdict(list))
    details={}
    for row in rows:
        key=row["case"];method=row["method"]
        by_case[key][method].append(float(row["elapsed_us"])/1000.)
        details[key]={"family":row["family"],"group":row["group"],"answer":row["answer"]}
    if not by_case:raise ValueError("No benchmark data")
    per_case={}
    for case,groups in by_case.items():
        if set(groups)!=set(METHODS):
            raise ValueError(f"Missing method in {case}: {set(groups)}")
        reps={len(v) for v in groups.values()}
        if len(reps)!=1:raise ValueError(f"Unequal repeat counts in {case}")
        per_case[case]={m:med(groups[m]) for m in METHODS}
    ids=sorted(per_case)
    per_family=defaultdict(list)
    for case in ids:per_family[details[case]["family"]].append(case)

    def aggregate(keys,method):
        p=sum(per_case[k]["plain"] for k in keys)
        h=sum(per_case[k][method] for k in keys)
        ratios=[per_case[k]["plain"]/max(1e-12,per_case[k][method]) for k in keys]
        return {
            "sum_instance_medians_ms":round(h,6),
            "speedup_plain_over_method":round(p/max(h,1e-12),6),
            "median_paired_case_speed_ratio":round(med(ratios),6),
            "faster_cases_than_plain":sum(per_case[k][method]<per_case[k]["plain"] for k in keys),
            "slower_cases_than_plain":sum(per_case[k][method]>per_case[k]["plain"] for k in keys),
        }
    totals={m:aggregate(ids,m) for m in METHODS}
    family={}
    for name,keys in sorted(per_family.items()):
        family[name]={"cases":len(keys)}
        for method in METHODS:family[name][method]=aggregate(keys,method)
    rng=random.Random(20261119)
    ci={}
    for method in METHODS[1:]:
        samples=[]
        for _ in range(2000):
            sample=[rng.choice(ids) for _ in ids]
            numerator=sum(per_case[k]["plain"] for k in sample)
            denominator=sum(per_case[k][method] for k in sample)
            samples.append(numerator/max(denominator,1e-12))
        samples.sort()
        ci[method]=[round(samples[49],6),round(samples[1950],6)]
    phases={}
    for method in METHODS:
        entries=[r for r in rows if r["method"]==method]
        phases[method]={
            "cases_with_nonzero_phase_hints":len({r["case"] for r in entries if int(r["advised"])>0}),
            "cases_with_structural_components":len({r["case"] for r in entries if r["modular"]=="1"}),
            "mean_hints_per_run":round(statistics.mean(int(r["advised"]) for r in entries),3),
            "total_analysis_ms":round(sum(float(r["analysis_us"]) for r in entries)/1000,4),
        }
    report={
        "seed":seed,
        "cases":len(ids),
        "repetitions":len(rows)//(len(ids)*len(METHODS)),
        "verified_agreement":len(ids),
        "methods":totals,
        "per_family":family,
        "phase_activity":phases,
        "paired_instance_bootstrap_95pct_ratio":ci,
        "sat_unsat_counts":dict(Counter(details[i]["answer"] for i in ids)),
        "caveats":[
            "Pre-registered fixed heuristic; seeded synthetic formulas, not an external SAT competition dataset.",
            "Bootstrap intervals measure variation over these synthetic instances only.",
            "All solver constructions, phase computations, graph analysis and solutions are timed; DIMACS reading excluded equally.",
            "Model validation performed for every SAT result; UNSAT agrees with unmodified CaDiCaL but has no independent proof checker.",
            "Microsecond-scale results are sensitive to CPU scheduler/cache. Paired method order is shuffled."
        ],
    }
    Path(output_file).write_text(json.dumps(report,indent=2),encoding="utf8")
    print(json.dumps({k:v for k,v in report.items() if k!="per_family"},indent=2))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--csv",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--seed",type=int,default=20261119)
    a=p.parse_args()
    analyze(a.csv,a.out,a.seed)
