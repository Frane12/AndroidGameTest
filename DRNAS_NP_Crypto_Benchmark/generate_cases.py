#!/usr/bin/env python3
"""Deterministic, blind DIMACS test suite for DRNAS and CryptoMiniSat."""
from pathlib import Path
import random,csv,argparse
from drnas_np_lab import write_dimacs,normalize,random_3sat
from experiment_v02 import sample_instance
from experiment_masked import mask
def generate(root,seeds=2,sizes=(41,81,121)):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);records=[]
    def add(family,n,clauses,seed,expected,detail=""):
        idx=len(records)+1
        name=f"case_{idx:04}.cnf"
        clauses=normalize(n,clauses)
        write_dimacs(root/name,n,clauses)
        records.append(dict(case_id=f"case_{idx:04}",family=family,n=n,m=len(clauses),seed=seed,expected=expected,description=detail))
    for size in sizes:
        for j in range(seeds):
            seed=930001+size*101+j
            for sat in (False,True):
                expected="SAT" if sat else "UNSAT"
                n,clauses=sample_instance(size,seed,satisfiable=sat)
                add("parity_"+expected.lower(),n,clauses,seed,expected,f"V={size}")
                new_n,masked,count=mask(n,clauses)
                add("masked_"+expected.lower(),new_n,masked,seed,expected,f"V={size}; split={count}")
    for n,m in ((24,100),(36,150),(48,206)):
        for j in range(seeds):
            seed=960007+100*n+j;rng=random.Random(seed)
            add("random_3sat",n,random_3sat(n,m,rng),seed,"UNKNOWN","no planted structure")
    for j in range(seeds):
        rng=random.Random(80000+j);n=60;clauses=[]
        for _ in range(200):
            a,b=rng.sample(range(1,n+1),2)
            clauses.append((a if rng.randrange(2) else -a,b if rng.randrange(2) else -b))
        add("random_2sat",n,clauses,80000+j,"UNKNOWN","2-CNF control")
        horn=[]
        for _ in range(180):
            k=rng.choice((1,2,3));vs=rng.sample(range(1,n+1),k)
            pos=rng.choice(vs+[None])
            horn.append(tuple(v if v==pos else -v for v in vs))
        add("random_horn",n,horn,80000+j,"UNKNOWN","Horn control")
    with (root/"manifest.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    return records
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--dir",default="cases");p.add_argument("--seeds",type=int,default=2)
    a=p.parse_args();print(f"Generated {len(generate(a.dir,a.seeds))} fixed cases.")
