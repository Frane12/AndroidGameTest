#!/usr/bin/env python3
"""DRNAS-SAT v7.2 frozen diversity benchmark (synthetic CNF).
Pilot and holdout use disjoint seeds. Families are enumerated before solving.
"""
import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "drnas-sat-v4"))
from benchmark_sat import (random_3sat, modular_3sat, xor_chain,
                           pigeonhole, normalize, write_dimacs)

FAMILIES = (
    "global_planted_ratio_355",
    "global_planted_ratio_380",
    "global_planted_ratio_405",
    "global_random_ratio_380",
    "global_random_ratio_400",
    "global_random_ratio_425",
    "global_random_ratio_475",
    "modular_planted_ratio_380",
    "modular_planted_ratio_425",
    "modular_random_ratio_400",
    "xor_sat_unsat",
    "pigeonhole_unsat",
)

def make_case(rng, family, index):
    if family.startswith("global_"):
        planted = "planted" in family
        ratio = float(family.rsplit("_",1)[1]) / 100
        n = rng.choice([160, 180, 200, 220])
        return normalize(random_3sat(rng, n, ratio, planted))
    if family.startswith("modular_"):
        planted = "planted" in family
        ratio = float(family.rsplit("_",1)[1]) / 100
        blocks = rng.choice([8,9,10])
        width = rng.choice([18,20,22])
        return normalize(modular_3sat(rng, blocks, width, ratio, 1, planted))
    if family == "xor_sat_unsat":
        return normalize(xor_chain(rng, rng.choice([80,120,160]), index%2==1))
    if family == "pigeonhole_unsat":
        holes = rng.choice([5,6,7])
        return normalize(pigeonhole(holes+1,holes))
    raise ValueError(family)

def generate(outdir,seed,each):
    out = Path(outdir).resolve()
    cnfdir = out/"cnf"
    cnfdir.mkdir(parents=True,exist_ok=True)
    rng=random.Random(seed)
    result=[]
    for family in FAMILIES:
        for index in range(each):
            cnf=make_case(rng,family,index)
            case=f"{family}_{index:03d}"
            path=cnfdir/(case+".cnf")
            write_dimacs(path,cnf)
            result.append(dict(case=case,family=family,path=str(path),
                               vars=max((abs(l) for c in cnf for l in c),default=0),
                               clauses=len(cnf)))
    with (out/"manifest.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=["case","family","path","vars","clauses"])
        writer.writeheader();writer.writerows(result)
    print(f"Frozen {len(result)} CNFs, seed={seed}; {each} instances x {len(FAMILIES)} families",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--outdir",required=True)
    p.add_argument("--seed",type=int,required=True)
    p.add_argument("--each",type=int,required=True)
    a=p.parse_args()
    generate(a.outdir,a.seed,a.each)
