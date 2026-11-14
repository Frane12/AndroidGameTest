#!/usr/bin/env python3
"""Regression: native single-process clause-only Hall detector and independent proof.

All CNFs and witnesses are locally constructed; signed and shuffled cases
are included to ensure no accidental BDD or variable-order dependence.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import time
from itertools import combinations

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from check_clause_hall import check,InvalidCertificate

def php(n,k,signed=False):
    groups=[[1+j*k+r for r in range(k)] for j in range(n)]
    if signed:
        for i in range(n):
            if i%2:groups[i]=[-x for x in groups[i]]
    clauses=[tuple(g) for g in groups]
    for r in range(k):
        for j,i in combinations(range(n),2):
            clauses.append((-groups[j][r],-groups[i][r]))
    return groups,clauses

def write(path,clauses,nvars=None):
    if nvars is None:nvars=max(abs(v) for c in clauses for v in c)
    raw=(f"p cnf {nvars} {len(clauses)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in clauses)).encode("ascii")
    path.write_bytes(raw)
    return raw

def run(binary,cnf,cert,budget=500):
    args=[str(binary.resolve()),str(cnf.resolve()),"--mode","core","--time","4",
          "--pcmax-clause-guard","--pcmax-only","--pcmax-budget-ms",str(budget),
          "--pcmax-certificate",str(cert.resolve())]
    t=time.perf_counter()
    p=subprocess.run(args,capture_output=True,text=True,timeout=10)
    tele=[json.loads(s[len("c PCMAX_CAPACITY "):])
          for s in p.stdout.splitlines() if s.startswith("c PCMAX_CAPACITY ")]
    return dict(rc=p.returncode,stdout=p.stdout,stderr=p.stderr,
                seconds=round(time.perf_counter()-t,6),
                telemetry=tele[-1] if tele else {})

def negative_checks(raw,proof):
    mutated=json.loads(json.dumps(proof))
    mutated["resource_bound"]+=1
    try:check(raw,mutated);raise AssertionError("accepted forged bound")
    except (InvalidCertificate,ValueError):pass
    mutated=json.loads(json.dumps(proof))
    mutated["source_sha256"]="0"*64
    try:check(raw,mutated);raise AssertionError("accepted wrong source hash")
    except (InvalidCertificate,ValueError):pass
    mutated=json.loads(json.dumps(proof))
    mutated["alo_groups"][0][0] *= -1
    try:check(raw,mutated);raise AssertionError("accepted fake source ALO")
    except (InvalidCertificate,ValueError):pass
    mutated=json.loads(json.dumps(proof))
    mutated["resource_cliques"][0].append(987654)
    try:check(raw,mutated);raise AssertionError("accepted invented conflict")
    except (InvalidCertificate,ValueError):pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    args.output.mkdir(parents=True,exist_ok=False)
    rng=random.Random(202611142137)
    configs=[("php3x2",3,2,False,True),("php5x4",5,4,False,True),
             ("php7x6",7,6,False,True),("signed_php3x2",3,2,True,True),
             ("sat_2x2",2,2,False,False),("sat_4x4",4,4,False,False),
             ("sat_gap3x2",3,2,False,False)]
    results=[]
    for name,n,k,signed,unsat in configs:
        groups,clauses=php(n,k,signed=signed)
        if name=="sat_gap3x2":
            # Remove a blocking clause to permit two groups to share one slot.
            pair=(-groups[0][0],-groups[1][0])
            clauses.remove(pair)
            chosen={groups[0][0],groups[1][0],groups[2][1]}
            assert all(any(l in chosen or -l not in chosen for l in c) for c in clauses)
        raw=write(args.output/(name+".cnf"),clauses)
        cert=args.output/(name+".json")
        native=run(args.binary,args.output/(name+".cnf"),cert)
        if unsat:
            assert native["rc"]==20 and cert.is_file(),(name,native)
            proof=json.loads(cert.read_text())
            outcome=check(raw,proof)
            assert outcome["status"]=="UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED"
            negative_checks(raw,proof)
            status="UNSAT_CERTIFIED"
        else:
            assert native["rc"]==0 and not cert.exists(),(name,native)
            status="UNKNOWN_CORRECT"
        results.append(dict(name=name,status=status,native_s=native["seconds"],
                            telemetry=native["telemetry"],
                            source_sha256=hashlib.sha256(raw).hexdigest()))
        print("CLAUSE_HALL_SMOKE "+json.dumps({k:results[-1][k] for k in
                ("name","status","native_s","telemetry")}),flush=True)
    # Fuzz-safe-source control: different clause order and renamed variables,
    # no correctness assumptions on completeness, but every UNSAT must verify.
    for trial in range(8):
        n,k=4+rng.randrange(2),3+rng.randrange(2)
        groups,clauses=php(n,k,signed=bool(trial%2))
        nv=n*k
        order=list(range(1,nv+1))
        rng.shuffle(order)
        rename={i+1:order[i] for i in range(nv)}
        mapped=[tuple(rename[abs(l)] if l>0 else -rename[abs(l)] for l in c)
                for c in clauses]
        rng.shuffle(mapped)
        raw=write(args.output/(f"shuffled{trial}.cnf"),mapped,nv)
        cnf=args.output/(f"shuffled{trial}.cnf")
        cert=args.output/(f"shuffled{trial}.json")
        run_data=run(args.binary,cnf,cert,budget=700)
        if run_data["rc"]==20:
            assert cert.is_file() and check(raw,json.loads(cert.read_text()))["status"]=="UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED"
            status="UNSAT_CERTIFIED"
        else:
            assert run_data["rc"]==0 and not cert.exists(),run_data
            status="UNKNOWN_SAFELY"
        print("CLAUSE_HALL_FUZZ "+json.dumps(dict(index=trial,status=status,
                          native_s=run_data["seconds"])),flush=True)
    report=dict(binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                checker_sha256=hashlib.sha256((HERE/"check_clause_hall.py").read_bytes()).hexdigest(),
                single_cpu=cpu,cases=results,pass_count=len(results),fuzz_trials=8)
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("CLAUSE_HALL_SMOKE_SUMMARY "+json.dumps(dict(
          pass_count=len(results),fuzz_trials=8)),flush=True)

if __name__=="__main__":main()
