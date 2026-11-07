#!/usr/bin/env python3
"""Diagnostic contrast between known v16.6 winner and loser at conflict caps.

Only replay examples (165000, 165001) used; no data from blind seeds.
A >=25% separation is descriptive, NOT a validated selection rule.
"""
import argparse
import csv
from pathlib import Path

CHECKPOINTS=(1000,5000,10000)
METRICS={
  "decisions_per_conflict":("decisions","conflicts"),
  "propagations_per_conflict":("propagations","conflicts"),
  "restarts_per_conflict":("restarts","conflicts"),
  "learned_per_conflict":("clauses_learned","conflicts"),
  "used_per_learned":("clauses_used","clauses_learned"),
  "redundant_per_learned":("clauses_redundant","clauses_learned"),
}

def metric(row,numerator,denominator):
    if not row.get(numerator) or not row.get(denominator):
        return None
    return float(row[numerator])/max(float(row[denominator]),1.0)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args()
    with args.input.open(newline="",encoding="utf8") as f:
        rows=list(csv.DictReader(f))
    lookup={(int(r["seed"]),int(r["checkpoint"]),r["profile"]):r for r in rows}
    output=[]
    summary=["DRNAS v16.7 replay-only divergence by CONFLICT COUNT",
             "165000: SAT+restart wins; 165001: target=2 harms.",
             "Independent cold runs at 1k, 5k and 10k; no shared solving state.",
             "Ratio is within-instance SAT-both over restart-only; gap is across-seed contrast.",
             "CAUTION: >=25% is diagnostic, not a validated causal or predictive threshold."]
    for label,(num,den) in METRICS.items():
        earliest=None
        for cap in CHECKPOINTS:
            ratios={}
            for seed in (165000,165001):
                a=lookup[(seed,cap,"sat-both")]
                b=lookup[(seed,cap,"restart-only")]
                va=metric(a,num,den)
                vb=metric(b,num,den)
                ratios[seed]=(va/vb if va is not None and vb is not None and vb>0 else None)
            rgood,rbad=ratios[165000],ratios[165001]
            contrast=(max(rgood,rbad)/min(rgood,rbad)
                      if rgood is not None and rbad is not None and min(rgood,rbad)>0
                      else None)
            separated=contrast is not None and contrast>=1.25
            if separated and earliest is None: earliest=cap
            output.append(dict(metric=label,checkpoint=cap,
                good_ratio=rgood,bad_ratio=rbad,
                contrast=contrast,separation_25pct=separated))
        summary.append(f"{label}: first >=25% contrast at "
                       f"{earliest if earliest is not None else 'not observed <=10000 conflicts'}")
    args.out.mkdir(parents=True,exist_ok=True)
    with (args.out/"divergence.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(output[0]))
        w.writeheader();w.writerows(output)
    text="\n".join(summary)+"\n"
    (args.out/"divergence.txt").write_text(text,encoding="utf8")
    print(text,flush=True)

if __name__=="__main__":
    main()
