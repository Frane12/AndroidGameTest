#!/usr/bin/env python3
"""Regenerate prior calibrated cases and independent, untouched v16.4 holdout.
Hard cases remain ~15 seconds only if measured; fixed holdout is not pre-selected.
"""
import argparse
from pathlib import Path
import random

def make(path,n,seed,ratio):
    r=random.Random(seed)
    m=round(n*ratio)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="ascii") as f:
        f.write(f"c DRNAS v16.4 seed={seed} density={ratio}\n")
        f.write(f"p cnf {n} {m}\n")
        for _ in range(m):
            variables=r.sample(range(1,n+1),3)
            lits=[v if r.getrandbits(1) else -v for v in variables]
            f.write(" ".join(map(str,lits))+" 0\n")

def generate(root):
    # Prior v16.3 calibration, not blind. Cross-check only.
    for seed in (163007,163016):
        make(root/"replay"/f"random3_n640_seed{seed}.cnf",640,seed,4.26)
    # New seeds, never used to calibrate the previous 15 s selection.
    for seed in (164000,164001):
        make(root/"holdout"/f"random3_n640_seed{seed}.cnf",640,seed,4.26)
    # Structural control: rule MUST actually route to both alternatives.
    make(root/"structural"/"random3_low_density_seed164002.cnf",220,164002,3.8)
    make(root/"structural"/"random3_high_density_seed164003.cnf",220,164003,4.7)
    assert len(list(root.rglob("*.cnf")))==6
    print("Generated 6 instances: 2 prior-calibrated + 2 blind-seed holdout + 2 structural controls",flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("root",type=Path)
    generate(a.parse_args().root)
