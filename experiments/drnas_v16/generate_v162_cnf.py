#!/usr/bin/env python3
"""Deterministic v16.2 benchmark inputs: 36 CNFs, 12 per class.
Planted SAT instances include a known all-true witness. UNSAT cases
contain contradictory units. Random cases have no assumed answer.
"""
from pathlib import Path
import argparse
import random

def write(path, n, clauses, extra=()):
    with path.open("w", encoding="ascii") as f:
        f.write("c DRNAS v16.2 deterministic benchmark\n")
        f.write(f"p cnf {n} {len(clauses)+len(extra)}\n")
        for c in list(clauses)+list(extra):
            f.write(" ".join(map(str,c))+" 0\n")

def generate(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for idx in range(12):
        r=random.Random(160200+idx)
        n=75+idx*4
        # all-true witness: at least one positive literal per clause
        planted=[]
        for _ in range(300+idx*12):
            vs=r.sample(range(1,n+1),3)
            signs=[r.choice((-1,1)) for _ in range(3)]
            if all(s<0 for s in signs):
                signs[r.randrange(3)]=1
            planted.append([v*s for v,s in zip(vs,signs)])
        write(folder/f"sat_planted_{idx:02d}.cnf",n,planted)
        # Known UNSAT (contradictory units) with nontrivial padding
        padding=[[(v if r.getrandbits(1) else -v) for v in r.sample(range(1,n+1),3)]
                 for _ in range(280+idx*10)]
        write(folder/f"unsat_units_{idx:02d}.cnf",n,padding,([1],[-1]))
        # Random 3-SAT around phase transition. Result deliberately unknown.
        random3=[[(v if r.getrandbits(1) else -v) for v in r.sample(range(1,n+1),3)]
                 for _ in range(round(n*4.26))]
        write(folder/f"random3_{idx:02d}.cnf",n,random3)
    assert len(list(folder.glob("*.cnf")))==36

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("folder",type=Path)
    args=p.parse_args()
    generate(args.folder)
    print("Generated 36 deterministic CNFs in",args.folder)
