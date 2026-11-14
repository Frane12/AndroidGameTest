#!/usr/bin/env python3
"""Random UNSAT audit for the opt-in clause-Hall guard.

One logical CPU. The solver is never trusted for correctness: every native
UNSAT must carry a source-byte-bound certificate checked independently.
SAT controls have explicit satisfying witnesses. Random 3-CNF and XOR
contradictions are checked by exhaustive assignment enumeration.
"""
import argparse
import collections
import copy
import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_clause_hall import check, InvalidCertificate

SEED=202611142221
def lit_true(lit,model):
    return model.get(abs(lit),False)==(lit>0)
def satisfied(clauses,model):
    return all(any(lit_true(l,model) for l in clause) for clause in clauses)
def exact_sat(clauses,nvars):
    if nvars>8: raise ValueError("exact oracle only for <=8 variables")
    for bits in itertools.product((False,True),repeat=nvars):
        model=dict(zip(range(1,nvars+1),bits))
        if satisfied(clauses,model): return model
    return None
def write_cnf(path,clauses,nvars):
    raw=(f"p cnf {nvars} {len(clauses)}\\n" +
         "".join(" ".join(map(str,c))+" 0\\n" for c in clauses)).encode()
    path.write_bytes(raw)
    return raw
def add_noise(rng,clauses,start):
    newvars=list(range(start,start+7))
    model={v:bool(rng.getrandbits(1)) for v in newvars}
    for _ in range(14):
        vs=rng.sample(newvars,3)
        c=[v if rng.getrandbits(1) else -v for v in vs]
        if not any(lit_true(l,model) for l in c):
            c[0]=vs[0] if model[vs[0]] else -vs[0]
        clauses.append(tuple(c))
    return model,start+6
def hall(rng,k,n,pattern,noise=False):
    groups=[[1+j*k+r for r in range(k)] for j in range(n)]
    if pattern in ("signed_small","signed_wide"):
        for j,g in enumerate(groups):
            groups[j]=[l*(-1 if rng.random()<0.5 else 1) for l in g]
    clauses=[tuple(g) for g in groups]
    for slot in range(k):
        for a in range(n):
            for b in range(a+1,n):
                if pattern=="near_miss" and slot==0 and a==0 and b==1: continue
                clauses.append((-groups[a][slot],-groups[b][slot]))
    # ALO literal order is irrelevant to satisfiability, but native
    # wide-columns discovery currently assumes consistent slot ordering.
    if pattern=="permuted_wide":
        clauses= [tuple(rng.sample(list(g),len(g))) for g in groups] + clauses[n:]
    model=None
    if pattern in ("near_miss","balanced"):
        selected=[(0 if j<2 else j-1) if pattern=="near_miss" else j for j in range(n)]
        model={}
        for j,g in enumerate(groups):
            for lit in g: model[abs(lit)]=lit<0
            lit=g[selected[j]]
            model[abs(lit)]=lit>0
    nvars=n*k
    if noise:
        fmodel,nvars=add_noise(rng,clauses,nvars+1)
        if model is not None:model.update(fmodel)
    # Random variable renaming, then random original-clause order.
    permutation=list(range(1,nvars+1))
    rng.shuffle(permutation)
    ren={v:permutation[v-1] for v in range(1,nvars+1)}
    mapped=[tuple(ren[abs(l)] if l>0 else -ren[abs(l)] for l in c) for c in clauses]
    rng.shuffle(mapped)
    if model is not None:
        model={ren[v]:value for v,value in model.items()}
        assert satisfied(mapped,model),"invalid SAT control witness"
    return mapped,nvars,model

def random_3sat_unsat(rng):
    n=rng.choice([4,5,6])
    clauses=[]
    for _ in range(200):
        vs=rng.sample(range(1,n+1),3)
        clauses.append(tuple(v if rng.getrandbits(1) else -v for v in vs))
        if exact_sat(clauses,n) is None:return clauses,n,None
    raise AssertionError("did not synthesize random UNSAT 3-CNF")
def xor_parity_conflict(rng):
    n=rng.choice([3,4,5])
    # XOR(...)=0 and XOR(...)=1 together exclude all 2**n assignments.
    clauses=[]
    for parity in (0,1):
        for bits in itertools.product((0,1),repeat=n):
            if sum(bits)%2 == parity:
                clauses.append(tuple(-v if b else v for v,b in enumerate(bits,1)))
    rng.shuffle(clauses)
    assert exact_sat(clauses,n) is None
    return clauses,n,None
def unsat_2sat(rng):
    clauses=[(1,2),(-1,2),(1,-2),(-1,-2)]
    rng.shuffle(clauses)
    assert exact_sat(clauses,2) is None
    return clauses,2,None
def planted_sat(rng):
    n=6
    model={i:bool(rng.getrandbits(1)) for i in range(1,n+1)}
    clauses=[]
    for _ in range(45):
        vs=rng.sample(range(1,n+1),3)
        c=[v if rng.getrandbits(1) else -v for v in vs]
        if not any(lit_true(l,model) for l in c):
            c[0]=vs[0] if model[vs[0]] else -vs[0]
        clauses.append(tuple(c))
    assert satisfied(clauses,model)
    return clauses,n,model

def cases(rng):
    out=[]
    def add(family,label,payload):
        clauses,nvars,model=payload
        out.append(dict(name=f"{len(out):03d}_{family}",family=family,
                        expected=label,clauses=clauses,nvars=nvars,model=model))
    for _ in range(22):
        k=rng.randint(2,9)
        add("small_hall","UNSAT",hall(rng,k,k+rng.randint(1,2),"signed_small" if rng.randrange(2) else "aligned",noise=bool(rng.randrange(2))))
    for _ in range(12):
        k=rng.randint(13,34)
        add("wide_aligned","UNSAT",hall(rng,k,k+1,"aligned",noise=bool(rng.randrange(2))))
    for _ in range(12):
        k=rng.randint(13,34)
        add("wide_row_permuted","UNSAT",hall(rng,k,k+1,"permuted_wide",noise=bool(rng.randrange(2))))
    for _ in range(8):
        k=rng.randint(13,22)
        add("wide_signed","UNSAT",hall(rng,k,k+1,"signed_wide",noise=bool(rng.randrange(2))))
    for _ in range(18):add("random_3sat_unsat","UNSAT",random_3sat_unsat(rng))
    for _ in range(8):add("xor_parity_unsat","UNSAT",xor_parity_conflict(rng))
    for _ in range(8):add("unsat_2sat","UNSAT",unsat_2sat(rng))
    for _ in range(12):
        k=rng.randint(2,9)
        add("sat_one_missing_mutex","SAT",hall(rng,k,k+1,"near_miss",noise=bool(rng.randrange(2))))
    for _ in range(8):
        k=rng.randint(2,9)
        add("sat_balanced_hall","SAT",hall(rng,k,k,"balanced",noise=bool(rng.randrange(2))))
    for _ in range(8):add("sat_planted_3sat","SAT",planted_sat(rng))
    rng.shuffle(out)
    return out

def native_run(binary,src,cert,budget):
    cmd=[str(binary.resolve()),str(src.resolve()),"--mode","core","--time","4",
         "--pcmax-clause-guard","--pcmax-only","--pcmax-budget-ms",str(budget),
         "--pcmax-certificate",str(cert.resolve())]
    t=time.perf_counter()
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=8)
    telemetry=[json.loads(s[len("c PCMAX_CAPACITY "):])
              for s in p.stdout.splitlines() if s.startswith("c PCMAX_CAPACITY ")]
    return p.returncode,round(time.perf_counter()-t,6),(telemetry[-1] if telemetry else {}),p.stderr[-200:]
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--binary",type=Path,required=True)
    a.add_argument("--out",type=Path,required=True)
    a.add_argument("--budget-ms",type=int,default=700)
    args=a.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    rng=random.Random(SEED)
    batch=cases(rng)
    records=[]
    with (args.out/"trials.jsonl").open("w") as stream:
        for idx,c in enumerate(batch):
            src=args.out/(c["name"]+".cnf")
            cert=args.out/(c["name"]+".proof.json")
            raw=write_cnf(src,c["clauses"],c["nvars"])
            label=c["expected"]
            if label=="SAT":
                assert c["model"] is not None and satisfied(c["clauses"],c["model"])
            elif c["family"] in ("random_3sat_unsat","xor_parity_unsat","unsat_2sat"):
                assert exact_sat(c["clauses"],c["nvars"]) is None
            rc,seconds,telemetry,stderr=native_run(args.binary,src,cert,args.budget_ms)
            if rc not in (0,20):raise AssertionError((c["name"],rc,stderr,telemetry))
            proof_out=None
            if rc==20:
                assert cert.is_file(),("missing proof",c["name"])
                proof=json.loads(cert.read_text())
                proof_out=check(raw,proof)
                assert proof_out["status"]=="UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED"
                assert label=="UNSAT",("FALSE UNSAT ON SAT",c["name"])
                # One crucial check of independent rejection on every positive.
                forged=copy.deepcopy(proof)
                forged["resource_bound"]+=1
                try:check(raw,forged)
                except (InvalidCertificate,ValueError):pass
                else:raise AssertionError(("forged proof accepted",c["name"]))
            else:
                assert not cert.exists(),("spurious proof",c["name"])
            row={"index":idx,"name":c["name"],"family":c["family"],
                 "expected":label,"status":"CERTIFIED_UNSAT" if rc==20 else "UNKNOWN",
                 "reason":telemetry.get("reason","not_reported"),"seconds":seconds,
                 "native_rc":rc,"variables":c["nvars"],"clauses":len(c["clauses"]),
                 "sha256":hashlib.sha256(raw).hexdigest(),
                 "witness_sat_checked":label=="SAT","certificate":proof_out,
                 "telemetry":telemetry}
            records.append(row)
            stream.write(json.dumps(row,sort_keys=True)+"\\n")
            stream.flush()
            print("RANDOM_UNSAT_TRIAL "+json.dumps({k:row[k] for k in
                  ("index","family","expected","status","reason","seconds",
                   "variables","clauses","certificate")},sort_keys=True),flush=True)
    summary={"seed":SEED,"cpu":cpu,"total":len(records),
             "unsat_certified":sum(r["status"]=="CERTIFIED_UNSAT" for r in records),
             "sat_false_positive":sum(r["expected"]=="SAT" and r["status"]=="CERTIFIED_UNSAT" for r in records),
             "binary_sha256":hashlib.sha256(args.binary.read_bytes()).hexdigest(),
             "checker_sha256":hashlib.sha256((Path(__file__).parent/"check_clause_hall.py").read_bytes()).hexdigest(),
             "families":{}}
    for fam in sorted(set(r["family"] for r in records)):
        rs=[r for r in records if r["family"]==fam]
        summary["families"][fam]={"total":len(rs),
           "certified":sum(r["status"]=="CERTIFIED_UNSAT" for r in rs),
           "unknown":sum(r["status"]=="UNKNOWN" for r in rs),
           "reasons":dict(collections.Counter(r["reason"] for r in rs)),
           "certified_seconds":sorted(r["seconds"] for r in rs if r["status"]=="CERTIFIED_UNSAT")}
    (args.out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\\n")
    print("RANDOM_UNSAT_SUMMARY "+json.dumps(summary,sort_keys=True),flush=True)
    assert summary["sat_false_positive"]==0

if __name__=="__main__":main()
