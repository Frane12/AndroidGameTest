#!/usr/bin/env python3
"""DRNAS X1 MEMORY2: predeclared larger, family-disjoint synthetic test.

The purpose is statistical *estimation*, not manufacturing significance.
All SAT/UNSAT credit requires an independent original-CNF/proof check.
No hidden holdout data enter the persistent learned policy.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
from collections import Counter
import check
import memory2_significance as significance

TRAIN_FAMILIES=("rand3","planted3","xor_sparse","horn","graph3","pigeonhole")
TEST_FAMILIES=("rand4","planted4","xor_chain","binary2","graph4","cardinality")
ARMS=significance.ARMS

def add_xor(clauses,vs,rhs):
    for bits in itertools.product((0,1),repeat=len(vs)):
        if (sum(bits)%2)!=rhs:
            clauses.append([v if bit==0 else -v for v,bit in zip(vs,bits)])

def make_formula(family,i):
    rng=random.Random(0x71D7A5 + 30971*i + 1000003*(
        TRAIN_FAMILIES+TEST_FAMILIES).index(family))
    clauses=[]
    if family in ("rand3","planted3","rand4","planted4","binary2"):
        k=2 if family=="binary2" else 4 if "4" in family else 3
        n=rng.randrange(16,51) if k!=2 else rng.randrange(20,66)
        density={2:1.08,3:4.2,4:8.4}[k]
        planted=family.startswith("planted")
        witness=[False]+[bool(rng.randrange(2)) for _ in range(n)]
        for _ in range(round(density*n)):
            vs=rng.sample(range(1,n+1),k)
            c=[v*rng.choice((-1,1)) for v in vs]
            if planted and not any(witness[abs(v)]==(v>0) for v in c):
                c[rng.randrange(k)]*=-1
            clauses.append(c)
    elif family=="xor_sparse":
        n=rng.randrange(9,25)
        for _ in range(n+rng.randrange(-3,5)):
            vs=rng.sample(range(1,n+1),3)
            add_xor(clauses,vs,rng.randrange(2))
    elif family=="xor_chain":
        n=rng.randrange(15,38)
        assign=[False]+[bool(rng.randrange(2)) for _ in range(n)]
        for v in range(3,n+1):
            a,b=rng.sample(range(1,v),2)
            add_xor(clauses,[a,b,v],int(assign[a])^int(assign[b])^int(assign[v]))
        for _ in range(rng.randrange(1,6)):
            vs=rng.sample(range(1,n+1),3)
            rhs=0
            for v in vs:rhs ^= int(assign[v])
            # A contradiction in one of the added equations gives an UNSAT subset.
            if rng.random()<0.25:rhs ^= 1
            add_xor(clauses,vs,rhs)
    elif family=="horn":
        n=rng.randrange(17,55)
        for _ in range(3*n):
            vs=rng.sample(range(1,n+1),rng.randrange(2,5))
            if rng.random()<0.25:clauses.append([-v for v in vs])
            else:clauses.append([-v for v in vs[:-1]]+[vs[-1]])
        for _ in range(rng.randrange(1,7)):
            v=rng.randrange(1,n+1)
            clauses.append([v*rng.choice((-1,1))])
    elif family in ("graph3","graph4"):
        colors=3 if family=="graph3" else 4
        vertices=rng.randrange(8,15) if colors==3 else rng.randrange(9,16)
        n=vertices*colors
        v=lambda node,color:node*colors+color+1
        for node in range(vertices):
            clauses.append([v(node,c) for c in range(colors)])
            for a in range(colors):
                for b in range(a+1,colors):
                    clauses.append([-v(node,a),-v(node,b)])
        probability=rng.uniform(.16,.57) if colors==3 else rng.uniform(.27,.70)
        for a in range(vertices):
            for b in range(a+1,vertices):
                if b==a+1 or rng.random()<probability:
                    for color in range(colors):
                        clauses.append([-v(a,color),-v(b,color)])
    elif family=="pigeonhole":
        holes=rng.randrange(4,11)
        pigeons=holes+(1 if rng.random()<0.58 else 0)
        n=pigeons*holes
        v=lambda p,h:p*holes+h+1
        for p in range(pigeons):
            clauses.append([v(p,h) for h in range(holes)])
        for h in range(holes):
            for a in range(pigeons):
                for b in range(a+1,pigeons):
                    clauses.append([-v(a,h),-v(b,h)])
        # Distinct additional implied clauses; cannot create an invalid SAT answer.
        for _ in range(rng.randrange(2,12)):
            a,b=rng.sample(range(1,n+1),2)
            clauses.append([a*rng.choice((-1,1)),b*rng.choice((-1,1))])
    elif family=="cardinality":
        groups=rng.randrange(5,12)
        sizes=[rng.randrange(3,7) for _ in range(groups)]
        n=sum(sizes)
        variables=[];off=0
        for size in sizes:
            group=list(range(off+1,off+size+1));variables.append(group);off+=size
            clauses.append(group)
            for a,b in itertools.combinations(group,2):
                clauses.append([-a,-b])
        # Random cross-group disallowances lead to distinctive constraint graphs.
        for _ in range(n*2):
            a,b=rng.sample(range(groups),2)
            clauses.append([-rng.choice(variables[a]),-rng.choice(variables[b])])
        if rng.random()<0.20:
            group=rng.choice(variables)
            clauses.extend([[group[0]],[-group[0]]])
    else:
        raise ValueError(f"unsupported generator {family}")
    # Canonical normalization; not a label-specific CNF rewriting of holdout data.
    normalized=sorted({tuple(sorted(set(cl),key=lambda x:(abs(x),x<0))) for cl in clauses})
    text=f"p cnf {n} {len(normalized)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in normalized)
    return {"source":text,"family":family,"id":i,
            "sha256":hashlib.sha256(text.encode()).hexdigest(),"nvars":n,
            "clauses":len(normalized)}

def dataset(families,total):
    if total%len(families):raise ValueError("source count must be divisible by family count")
    each=total//len(families)
    data=[]
    for f in families:
        for i in range(each):
            data.append(make_formula(f,i))
    rng=random.Random(2026111309);rng.shuffle(data)
    return data

def emit(tag,row):
    print(tag+" "+json.dumps(row,sort_keys=True,separators=(",",":")),flush=True)

def run_trial(binary,cnf,cap,seed,flags,root,trace=None):
    proof=root/"proof.txt"
    args=[str(binary),"--mode","core","--seconds",str(cap),
          "--seed",str(seed),"--proof",str(proof)]
    if trace is not None:args+=["--memory2-log",str(trace)]
    args+=flags+[str(cnf)]
    t=time.monotonic()
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=cap+0.7)
        elapsed=time.monotonic()-t
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","verified":False,"PAR2":2*cap,
                "solve_s":cap,"check_s":0,"decisions":None,"conflicts":None}
    if p.returncode not in (0,10,20):
        raise RuntimeError(f"solver returned {p.returncode}: {p.stderr[-1200:]}")
    stats={}
    for line in p.stdout.splitlines():
        if line.startswith("c X1_STATS "):
            stats=json.loads(line[len("c X1_STATS "):]);break
    if stats.get("external_solver_calls")!=0:
        raise AssertionError("X1 must not invoke external SAT solver")
    status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
    check_t=0.;verified=False;kind="NOT_SOLVED"
    if status!="UNKNOWN":
        u=time.monotonic()
        try:
            c=check.verify(cnf,p.stdout,proof,0.9)
            verified=bool(c["verified"]);kind=c["kind"]
        except (ValueError,TimeoutError) as exc:
            kind=type(exc).__name__
        check_t=time.monotonic()-u
        if status=="SAT" and not verified:raise AssertionError("invalid SAT witness")
    e2e=elapsed+check_t
    return {"status":status,"verified":verified,"verification":kind,
        "solve_s":round(elapsed,6),"check_s":round(check_t,6),
        "PAR2":round(e2e if verified and e2e<=cap else 2*cap,6),
        "decisions":stats.get("decisions"),"conflicts":stats.get("conflicts"),
        "memory2_episodes":stats.get("memory2_episodes",0),
        "memory2_observations":stats.get("memory2_horizon_observations",0),
        "memory2_flipped":stats.get("memory2_flip_blocks",0)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,default=Path("build/drnas-x1"))
    p.add_argument("--out",type=Path,default=Path("memory2_statpower"))
    p.add_argument("--train",type=int,default=240)
    p.add_argument("--holdout",type=int,default=360)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--cap",type=float,default=0.5)
    args=p.parse_args()
    if args.repeats<3 or args.train<60 or args.holdout<200 or args.cap<0.2:
        raise ValueError("insufficient predeclared statistical sample")
    binary=args.binary.resolve()
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    train=dataset(TRAIN_FAMILIES,args.train)
    holdout=dataset(TEST_FAMILIES,args.holdout)
    all_cases=train+holdout
    if len({c["sha256"] for c in all_cases})!=len(all_cases):
        raise RuntimeError("duplicate generated CNF SHA; no independent-sample claim")
    if {c["family"] for c in train}&{c["family"] for c in holdout}:
        raise RuntimeError("train/holdout structural family leakage")
    manifest={"data":"controlled synthetic generated CNF","globally_blind":False,
       "family_disjoint_by_generator":True,
       "train_families":TRAIN_FAMILIES,"holdout_families":TEST_FAMILIES,
       "train_unique":len(train),"holdout_unique":len(holdout),
       "repeats":args.repeats,"cap_s":args.cap,
       "primary_comparison":"X1_M2_FROZEN vs X1_CORE",
       "target_relative_PAR2_improvement":0.05,
       "independence_unit":"distinct SHA of original CNF; seeds repeated within formula",
       "proofs":"independent SAT witness / UNSAT DRUP checker",
       "synthetic_not_general_SAT2024_claim":True,
       "sources":[{"split":"train" if index<len(train) else "holdout",
                    "id":x["id"],"family":x["family"],"sha256":x["sha256"],
                    "nvars":x["nvars"],"clauses":x["clauses"]}
                  for index,x in enumerate(all_cases)]}
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    policy=args.out/"verified-memory2-policy.txt"
    accepted=0;trials=[]
    with tempfile.TemporaryDirectory(prefix="memory2-statpower-") as tmp:
        root=Path(tmp);cnf=root/"case.cnf"
        for i,case in enumerate(train):
            cnf.write_text(case["source"])
            staged=root/"candidate-policy.txt"
            if staged.exists():staged.unlink()
            flags=["--memory2","--memory2-interval","8",
                    "--memory2-save",str(staged)]
            if policy.exists():flags+=["--memory2-load",str(policy)]
            row=run_trial(binary,cnf,args.cap,17,flags,root)
            if row["verified"] and staged.exists():
                os.replace(staged,policy);accepted+=1
            elif staged.exists():staged.unlink()
            if (i+1)%40==0:
                emit("M2_POWER_TRAIN",{"completed":i+1,"total":len(train),
                    "trusted_promotions":accepted})
        if not policy.exists():raise RuntimeError("no independently verified training result")
        policy_sha=hashlib.sha256(policy.read_bytes()).hexdigest()
        for i,case in enumerate(holdout):
            cnf.write_text(case["source"])
            for rep in range(args.repeats):
                seed=17+13*rep
                specs=[
                    ("X1_CORE",[]),
                    ("X1_M2_SHADOW",["--memory2-load",str(policy),
                        "--memory2-frozen","--memory2-shadow","--memory2-interval","8"]),
                    ("X1_M2_FROZEN",["--memory2-load",str(policy),
                        "--memory2-frozen","--memory2-interval","8"]),
                    ("X1_M2_ONLINE",["--memory2-load",str(policy),
                        "--memory2-interval","8"])
                ]
                offset=(i+rep)%len(specs);specs=specs[offset:]+specs[:offset]
                batch=[]
                for arm,flags in specs:
                    trace=(args.out/f"trace_{i}_{rep}.jsonl") if (
                        i in (0,1,len(holdout)-1) and rep==0 and arm=="X1_M2_ONLINE") else None
                    row=run_trial(binary,cnf,args.cap,seed,flags,root,trace)
                    row.update({"sha256":case["sha256"],"family":case["family"],
                        "id":i,"rep":rep,"seed":seed,"arm":arm,"nvars":case["nvars"]})
                    trials.append(row);batch.append(row)
                statuses={x["status"] for x in batch if x["verified"]}
                if len(statuses)>1:raise RuntimeError("certified SAT/UNSAT disagreement")
                core=next(x for x in batch if x["arm"]=="X1_CORE")
                shadow=next(x for x in batch if x["arm"]=="X1_M2_SHADOW")
                if core["verified"] and shadow["verified"]:
                    if (core["status"],core["decisions"],core["conflicts"])!=(
                            shadow["status"],shadow["decisions"],shadow["conflicts"]):
                        raise AssertionError("shadow altered the exact CDCL search")
            if (i+1)%20==0:
                with (args.out/"trials.jsonl").open("w") as o:
                    for row in trials:o.write(json.dumps(row,sort_keys=True)+"\n")
                emit("M2_POWER_PROGRESS",{"completed":i+1,"total":len(holdout),
                    "trials":len(trials)})
        if policy_sha!=hashlib.sha256(policy.read_bytes()).hexdigest():
            raise RuntimeError("holdout contaminated persistent learned state")
    with (args.out/"trials.jsonl").open("w") as o:
        for row in trials:o.write(json.dumps(row,sort_keys=True)+"\n")
    report=significance.compute(trials,"X1_M2_FROZEN",target=.05)
    report["train_unique"]=len(train)
    report["training_promoted_verified"]=accepted
    report["holdout_unique"]=len(holdout)
    report["holdout_model_sha_unchanged"]=True
    report["one_logical_cpu"]=True
    (args.out/"statistical-report.json").write_text(
        json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("M2_POWER_FINAL",{"train":len(train),"holdout":len(holdout),
         "primary_passed":report["primary_passed"],
         "stats":report["comparisons"]["X1_M2_FROZEN"],
         "by_arm":report["arms"],
         "caveat":report["limits"]})

if __name__=="__main__":main()
