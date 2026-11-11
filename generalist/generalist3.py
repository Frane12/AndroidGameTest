#!/usr/bin/env python3
"""GENERALIST3 offline-trained, source-blind native mode selector.

Safety: policy is trained on independently frozen SHA-disjoint original
formulas and only enabled if >= min_distinct_sha for a structural cell.
Classification uses CNF contents, never known source family or solver outcome.
Commands invoke ONE native process, not a portfolio.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ARMS=("A36_75","A39_PROTECT","A40_TREE")
BASE="A36_75"

def fingerprint(path):
    path=Path(path)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    n=0; declared=None; lengths=Counter(); freq=Counter()
    clauses=0; unit=0; binary=0
    pending=[]
    with path.open("rt", encoding="ascii", errors="strict") as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("c") or line.startswith("%"): continue
            if line.startswith("p "):
                parts=line.split()
                if len(parts)!=4 or parts[1]!="cnf": raise ValueError("bad DIMACS header")
                n=int(parts[2]); declared=int(parts[3])
                continue
            if declared is None: raise ValueError("missing DIMACS header")
            for token in line.split():
                val=int(token)
                if val:
                    if abs(val)>n: raise ValueError("variable out of declared range")
                    pending.append(val)
                else:
                    lengths[len(pending)]+=1
                    clauses+=1
                    for lit in set(map(abs,pending)): freq[lit]+=1
                    pending=[]
    if pending or declared is None or clauses!=declared: raise ValueError("incomplete CNF")
    if n<=0 or clauses<=0: raise ValueError("empty CNF not supported by classifier")
    avglen=sum(k*v for k,v in lengths.items())/clauses
    used=len(freq)
    maxdeg=max(freq.values(),default=0)
    # Coarse bins keep learning cells reusable across different formulas.
    density=clauses/n
    key="d%s_l%s_b%s_u%s_h%s" % (
        0 if density<2 else 1 if density<4 else 2 if density<8 else 3,
        0 if avglen<2.5 else 1 if avglen<3.5 else 2 if avglen<5 else 3,
        0 if binary/clauses<0.1 else 1 if binary/clauses<0.5 else 2,
        int(unit>0),
        int(maxdeg/clauses>0.2))
    return {"sha256":sha,"key":key,"vars":n,"clauses":clauses,
            "mean_clause_length":round(avglen,4),"used_variables":used}

def learn(rows,min_distinct=8,min_ratio=1.05):
    """Per SHA/arm median repetitions; verified PAR2 supplied by audit."""
    from statistics import median
    grouped=defaultdict(list); features={}
    for r in rows:
        sha=r["sha256"]; arm=r["arm"]
        if arm not in ARMS or len(sha)!=64: raise ValueError("invalid arm or SHA")
        if r.get("original_verified") is not True: raise ValueError("unverified record")
        if not (0<=float(r["verified_par2_s"]) and float(r["cap_s"])>0): raise ValueError("invalid PAR2")
        k=r["feature_key"]
        if sha in features and features[sha]!=k: raise ValueError("unstable features")
        features[sha]=k
        grouped[(sha,arm)].append(float(r["verified_par2_s"]))
    paired=defaultdict(dict)
    for (sha,arm),times in grouped.items(): paired[(features[sha],sha)][arm]=median(times)
    cells=defaultdict(list)
    for (key,sha),arms in paired.items():
        if BASE in arms: cells[key].append(arms)
    model={}
    for key,instances in cells.items():
        best={"arm":BASE,"paired":len(instances),"ratio":1.0}
        for arm in ARMS[1:]:
            overlap=[v for v in instances if arm in v]
            if len(overlap)<min_distinct:continue
            b=sum(v[BASE] for v in overlap)
            a=sum(v[arm] for v in overlap)
            ratio=b/a if a>0 else 0
            if ratio>=min_ratio and ratio>best["ratio"]:
                best={"arm":arm,"paired":len(overlap),"ratio":round(ratio,6)}
        model[key]=best
    return model

def choose(feature,policy):
    decision=policy.get(feature["key"],{})
    arm=decision.get("arm",BASE)
    if arm not in ARMS:raise ValueError("unsafe policy mode")
    return arm

def load_policy(path):
    data=json.loads(Path(path).read_text())
    if data.get("version")!=3 or data.get("baseline")!=BASE:raise ValueError("policy mismatch")
    return data

def solve(args):
    feat=fingerprint(args.cnf)
    policy=load_policy(args.policy)
    if feat["sha256"] in policy.get("training_sha",[]):
        raise ValueError("evaluation CNF overlaps training set")
    selected=choose(feat,policy["cells"])
    cmd=[args.binary,str(args.cnf),"--mode",selected,"--time",str(args.cap),"--seed",str(args.seed),
         "--policy","1.0,0.85"]
    print("GENERALIST3_DECISION "+json.dumps({"sha256":feat["sha256"],"feature_key":feat["key"],
          "selected_arm":selected,"fallback":selected==BASE},sort_keys=True),flush=True)
    p=subprocess.run(cmd,timeout=args.cap+5,check=False)
    return p.returncode

def main():
    a=argparse.ArgumentParser()
    sp=a.add_subparsers(dest="command",required=True)
    train=sp.add_parser("train")
    train.add_argument("jsonl",type=Path)
    train.add_argument("--out",type=Path,required=True)
    train.add_argument("--min-distinct",type=int,default=8)
    run=sp.add_parser("solve")
    run.add_argument("cnf",type=Path)
    run.add_argument("--policy",type=Path,required=True)
    run.add_argument("--binary",required=True)
    run.add_argument("--cap",type=float,default=60)
    run.add_argument("--seed",type=int,default=1)
    args=a.parse_args()
    if args.command=="train":
        if args.min_distinct<8:raise ValueError("min distinct must be >=8")
        rows=[json.loads(l) for l in args.jsonl.read_text().splitlines() if l.strip()]
        cells=learn(rows,args.min_distinct)
        out={"version":3,"baseline":BASE,"cells":cells,
             "training_sha":sorted({r["sha256"] for r in rows}),
             "status":"offline policy; must be prospectively validated"}
        args.out.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
        print("GENERALIST3_TRAIN "+json.dumps({"training_sha":len(out["training_sha"]),
            "cells":len(cells),"nondefault_cells":sum(x["arm"]!=BASE for x in cells.values())}),flush=True)
    else:
        sys.exit(solve(args))
if __name__=="__main__":main()
