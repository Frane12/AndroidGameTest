#!/usr/bin/env python3
"""Generate frozen, deterministic DIMACS instances for DRNAS SAT v6.
New large cases: shared cutset variables connecting independently generated
3-CNF modules. Controls: globally mixed 3-SAT. No solver feedback is used.
"""
import argparse
import csv
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "drnas-sat-v4"))
from benchmark_sat import cases as v4_cases, normalize, write_dimacs, random_3sat

def shared_modular(rng, blocks, width, hubs, ratio, planted):
    n=blocks*width+hubs
    model={v:rng.choice((-1,1)) for v in range(1,n+1)}
    cnf=[]
    def push(ls):
        if planted and not any((lit>0)==(model[abs(lit)]>0) for lit in ls):
            ls[0]=-ls[0]
        cnf.append(ls)
    for b in range(blocks):
        vs=list(range(hubs+b*width+1, hubs+(b+1)*width+1))
        for _ in range(round(ratio*width)):
            push([v*rng.choice((-1,1)) for v in rng.sample(vs,3)])
        for hub in range(1,hubs+1):
            # Each hub touches every module; no clause couples private variables
            # from distinct modules, so removing all hubs separates them exactly.
            for _ in range(3):
                local=rng.sample(vs,2)
                push([hub*rng.choice((-1,1))]+
                     [v*rng.choice((-1,1)) for v in local])
    return normalize(cnf)

def generate(outdir, seed=20261117, small=16, each=7):
    outdir=Path(outdir).resolve()
    cnfdir=outdir/"cnfs"
    cnfdir.mkdir(parents=True,exist_ok=True)
    rows=[]
    rng=random.Random(seed)
    for i,(case,family,formula) in enumerate(v4_cases(seed+9,small)):
        name=f"legacy_{i:03d}"
        path=cnfdir/f"{name}.cnf"
        write_dimacs(path,formula)
        rows.append(dict(case=name,family="legacy_"+family,path=str(path),
                         variables=max((abs(l) for c in formula for l in c),default=0),
                         clauses=len(formula),group="old-size-control"))
    scenarios=[
        ("mod1_161_planted",dict(blocks=8,width=20,hubs=1,ratio=4.10,planted=True)),
        ("mod2_202_planted",dict(blocks=10,width=20,hubs=2,ratio=4.10,planted=True)),
        ("mod2_322_random",dict(blocks=10,width=32,hubs=2,ratio=4.10,planted=False)),
        ("mod1_301_random",dict(blocks=12,width=25,hubs=1,ratio=4.00,planted=False)),
        ("global_180_planted",None),
        ("global_260_unsatlike",None),
    ]
    for family,params in scenarios:
        for i in range(each):
            if params is not None:
                ratio=params['ratio']+rng.uniform(-0.15,0.15)
                cnf=shared_modular(rng,params['blocks'],params['width'],
                                   params['hubs'],ratio,params['planted'])
            elif family.endswith("planted"):
                cnf=normalize(random_3sat(rng,180,3.8,True))
            else:
                cnf=normalize(random_3sat(rng,260,4.75,False))
            name=f"{family}_{i:03d}"
            path=cnfdir/f"{name}.cnf"
            write_dimacs(path,cnf)
            rows.append(dict(case=name,family=family,path=str(path),
                             variables=max((abs(l) for c in cnf for l in c),default=0),
                             clauses=len(cnf),group="new-large"))
    with (outdir/"manifest.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(f"Frozen {len(rows)} formulas: {small} original-sized + {each*len(scenarios)} larger, seed={seed}")
    return rows

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--outdir",default="bench_native_v6")
    p.add_argument("--seed",type=int,default=20261117)
    p.add_argument("--small",type=int,default=16)
    p.add_argument("--each",type=int,default=7)
    a=p.parse_args()
    generate(a.outdir,a.seed,a.small,a.each)
