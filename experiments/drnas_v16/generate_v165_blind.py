#!/usr/bin/env python3
"""DRNAS v16.5 fixed, unfiltered 3-SAT suite.

REPLAY: previously calibrated v16.3 seeds (not used as evidence of generalization).
HOLDOUT: new seeds 165000..165005, never selected on runtime or SAT outcome.
CONTROL: density alternatives to verify that the selector abstains.
"""
from pathlib import Path
import argparse
import hashlib
import random

def make_cnf(file, n, ratio, seed):
    rng=random.Random(seed)
    m=round(n*ratio)
    file.parent.mkdir(parents=True,exist_ok=True)
    with file.open("w",encoding="ascii") as out:
        out.write(f"c DRNAS-v165 group={file.parent.name} seed={seed} ratio={ratio}\n")
        out.write(f"p cnf {n} {m}\n")
        for _ in range(m):
            vars_=rng.sample(range(1,n+1),3)
            signs=[1 if rng.getrandbits(1) else -1 for _ in range(3)]
            out.write(" ".join(str(v*s) for v,s in zip(vars_,signs))+" 0\n")
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    print("GENERATED",file,"sha256",digest,flush=True)

def generate(root):
    # Mirrors v16.3 random3 generation byte-for-byte in the clauses.
    for seed in (163007,163016):
        make_cnf(root/"replay"/f"random3_n640_seed{seed}.cnf",640,4.26,seed)
    # ALL new seeds must be kept regardless of measured difficulty or SAT result.
    for seed in (165000,165001,165002,165003):
        make_cnf(root/"holdout"/f"random3_n640_seed{seed}.cnf",640,4.26,seed)
    for seed in (165004,165005):
        make_cnf(root/"holdout"/f"random3_n480_seed{seed}.cnf",480,4.26,seed)
    make_cnf(root/"control"/"random3_n320_low_seed165006.cnf",320,3.80,165006)
    make_cnf(root/"control"/"random3_n320_high_seed165007.cnf",320,4.70,165007)
    counts={name:len(list((root/name).glob("*.cnf"))) for name in
            ("replay","holdout","control")}
    assert counts=={"replay":2,"holdout":6,"control":2},counts
    print("SUITE:",counts,"10 fixed CNFs, no runtime-based selection",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("root",type=Path)
    generate(parser.parse_args().root)
