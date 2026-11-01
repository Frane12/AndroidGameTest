#!/usr/bin/env python3
"""V16.6b preregistered suite. DEV seeds are never scored as holdout.

All prospective new TEST seeds 166600..166607 are generated unchanged and
kept regardless of outcome. No per-seed runtime filtering or selection.
"""
import argparse,hashlib,json,random
from pathlib import Path

def make(path,n,seed,ratio):
    rng=random.Random(seed)
    m=round(n*ratio)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="ascii") as file:
        file.write(f"c V166b preregistered seed={seed} group={path.parent.name}\n")
        file.write(f"p cnf {n} {m}\n")
        for _ in range(m):
            ids=rng.sample(range(1,n+1),3)
            signs=[1 if rng.getrandbits(1) else -1 for _ in range(3)]
            file.write(" ".join(str(v*sgn) for v,sgn in zip(ids,signs))+" 0\n")
    return {"seed":seed,"file":str(path),"nvars":n,"clauses":m,
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def generate(root):
    cases=[]
    # DEV only: these had already been seen when rule was frozen.
    for seed,n in [(165000,640),(165001,640),(165004,480),(165005,480)]:
        cases.append(make(root/"development"/f"random3_n{n}_seed{seed}.cnf",n,seed,4.26))
    # Entire untouched test slate; no drops based on difficulty, answer or time.
    for j in range(8):
        seed=166600+j
        n=320 if j<4 else 420
        cases.append(make(root/"test"/f"random3_n{n}_seed{seed}.cnf",n,seed,4.26))
    for seed,n,ratio in [(166608,320,3.80),(166609,320,4.70)]:
        cases.append(make(root/"control"/f"random3_n{n}_seed{seed}.cnf",n,seed,ratio))
    assert len(cases)==14
    assert {x["seed"] for x in cases if "/test/" in x["file"]}==set(range(166600,166608))
    assert len({x["sha256"] for x in cases})==len(cases)
    manifest={"frozen":"V16.6b preregistered before any test solver runs",
              "cases":cases,"new_test_count":8,"development_count":4}
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2))
    print("V166B_FROZEN_MANIFEST",json.dumps(
        {"test":8,"development":4,"control":2,"hashes":[x["sha256"] for x in cases]},
        sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("root",type=Path);a=p.parse_args()
    generate(a.root)
