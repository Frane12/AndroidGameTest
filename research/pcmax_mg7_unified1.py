#!/usr/bin/env python3
"""One-process DRNAS PCMAX+MG7 C++ proof-kind union, source-bound short audit.

Certificate rule:
* CAPACITY_JSON_NEEDS_VERIPB -> structural check + separate weighted VeriPB3;
* DRAT_PROOF -> DRAT-TRIM on exact source CNF;
* SAT -> direct model validation against every source clause;
* UNKNOWN -> never accepted as solved.
Serial paired run, one logical CPU, no portfolio / no second solver process.
Originals: retrospective frozen source family, NOT blind, NOT verified PAR2.
"""
import hashlib
import itertools
import json
import os
import pathlib
import random
import resource
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/unified1"
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark import materialize
from check_capacity import check as structural_check

MANIFEST=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
BINARIES={
    "BDD_ONLY":ROOT/"build/drnas-pcmax",
    "MG7_ONLY":ROOT/"build/drnas-mg7-scc",
    "UNIFIED":ROOT/"build/drnas-pcmax-mg7-unified",
}
EMIT=ROOT/"research/pcmax_capacity/emit_veripb_capacity_weighted2.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
DRAT=ROOT/"drat-trim/drat-trim"
MAXPROOF=75*1024*1024

def limitfiles():
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAXPROOF,MAXPROOF))

def command(argv,limit,limited=False):
    start=time.monotonic()
    try:
        r=subprocess.run([str(a) for a in argv], capture_output=True,text=True,
                         timeout=limit,preexec_fn=limitfiles if limited else None)
        return r.returncode,round(time.monotonic()-start,6),r.stdout or "",r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124,round(time.monotonic()-start,6),"","TIMEOUT"

def parse_cnf(path):
    lines=path.read_text(encoding="ascii").splitlines()
    nvars=nc=None
    clauses=[];p=[]
    for line in lines:
        t=line.split()
        if not t or t[0]=="c":continue
        if t[0]=="p":
            if nvars is not None or t[1]!="cnf":raise ValueError("invalid header")
            nvars,nc=int(t[2]),int(t[3])
            continue
        for lit in t:
            v=int(lit)
            if v:p.append(v)
            else:clauses.append(p);p=[]
    if nvars is None or len(clauses)!=nc or p:raise ValueError("invalid DIMACS")
    return nvars,clauses

def model_checked(path,out):
    n,clauses=parse_cnf(path)
    model={}
    for line in out.splitlines():
        t=line.split()
        if t and t[0]=="v":
            for s in t[1:]:
                v=int(s)
                if v:model[abs(v)]=v>0
    return len(model)==n and all(any(model[abs(v)]==(v>0) for v in c) for c in clauses)

def synthetic():
    root=OUT/"synth";root.mkdir(parents=True,exist_ok=True)
    cases=[]
    for n,m in [(3,2),(4,3),(5,4),(3,3)]:
        cs=[tuple(i*m+j+1 for j in range(m)) for i in range(n)]
        for j in range(m):
            for i,k in itertools.combinations(range(n),2):
                cs.append((-(i*m+j+1),-(k*m+j+1)))
        path=root/f"php_{n}_{m}.cnf"
        path.write_text(f"p cnf {n*m} {len(cs)}\n"+
                        "".join(" ".join(map(str,c))+" 0\n" for c in cs))
        cases.append((f"php_{n}_{m}","UNSAT" if n>m else "SAT",path))
    rng=random.Random(20261116)
    cs=[];model={i:rng.choice([False,True]) for i in range(1,17)}
    for _ in range(100):
        vs=rng.sample(range(1,17),3)
        lits=[v if rng.choice([True,False]) else -v for v in vs]
        if not any(model[abs(v)]==(v>0) for v in lits):lits[0]=-lits[0]
        cs.append(tuple(lits))
    path=root/"planted_sat.cnf"
    path.write_text(f"p cnf 16 {len(cs)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in cs))
    cases.append(("planted_sat","SAT",path))
    return cases

def originals():
    originaldir=OUT/"originals";originaldir.mkdir(parents=True,exist_ok=True)
    rows=[]
    # Four source-frozen original UNSAT plus three catalog SAT controls.
    for i in [0,2,5,10,1,6,11]:
        entry=MANIFEST[i]
        cnf=materialize(entry,originaldir,True)
        if hashlib.sha256(cnf.read_bytes()).hexdigest()!=entry["sha256"]:
            raise AssertionError("original CNF byte identity mismatch")
        rows.append((f"pcmax_{i:02d}",entry["expected_status"],cnf))
    return rows

def verify_capacity(path,cert,case):
    outcome=structural_check(path.read_bytes(),json.loads(cert.read_text()))
    if outcome["status"]!="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
        return "CAPACITY_STRUCT_REJECTED",{}
    pb=case/"capacity.pbp"
    rc,sec,out,err=command([sys.executable,EMIT,"--cnf",path,
                             "--certificate",cert,"--output",pb],55,True)
    if rc!=0 or not pb.exists():
        return "CAPACITY_VERIPB_PRODUCER_ERROR",{"generator_rc":rc,"generator_s":sec}
    vc,vs,vout,verr=command([VERIPB,"--cnf",path,pb],110)
    (case/"capacity_veripb.log").write_text((vout+"\n"+verr)[-9000:])
    details={"generator_s":sec,"veripb_s":vs,"veripb_rc":vc,
             "proof_bytes":pb.stat().st_size,
             "demand":outcome["required"],"capacity":outcome["capacity_sum"]}
    return ("CAPACITY_VERIPB_VERIFIED" if vc==0 and
        "s VERIFIED UNSATISFIABLE" in vout+"\n"+verr else "CAPACITY_VERIPB_REJECTED"),details

def verify_drat(path,proof,case):
    if not proof.exists() or not proof.stat().st_size:
        return "DRAT_MISSING",{}
    vc,vs,out,err=command([DRAT,path,proof],100)
    (case/"checker.log").write_text((out+"\n"+err)[-12000:])
    return ("DRAT_UNSAT_VERIFIED" if vc==0 and "s VERIFIED" in out+"\n"+err
            else "DRAT_REJECTED"),{
                "checker_s":vs,"checker_rc":vc,"proof_bytes":proof.stat().st_size}

def run_case(name,label,cnf,arm):
    case=OUT/name/arm;case.mkdir(parents=True,exist_ok=True)
    cert=(case/"capacity.json").resolve()
    drat=case/"trace.drat"
    original=name.startswith("pcmax_")
    argv=[BINARIES[arm],cnf.resolve(),"--mode","core","--time",
          "5" if original else "4","--stats"]
    if arm in ("BDD_ONLY","UNIFIED"):
        argv += ["--pcmax-capacity","--pcmax-budget-ms","1000",
                 "--pcmax-certificate",cert]
    if arm=="BDD_ONLY":
        argv.append("--pcmax-only")
    if arm in ("MG7_ONLY","UNIFIED"):
        argv += ["--residual-scc","--proof",drat]
    rc,seconds,out,err=command(argv,9,True)
    (case/"native.log").write_text((out+"\n"+err)[-17000:])
    row={"name":name,"expected":label,"arm":arm,
         "source_sha256":hashlib.sha256(cnf.read_bytes()).hexdigest(),
         "solver_rc":rc,"wall_s":seconds,"status":"UNKNOWN"}
    kinds=[line.split()[-1] for line in out.splitlines()
           if line.startswith("c PCMAX_UNIFIED_PROOF_KIND ")]
    if arm=="UNIFIED":
        row["proof_kind"]=kinds
    for line in err.splitlines():
        if line.startswith("MG7_RESIDUAL "):
            row["scc_stats"]=json.loads(line.partition(" ")[2])
        if line.startswith("X41_STATS "):
            record=json.loads(line.partition(" ")[2])
            row.update({k:record.get(k) for k in ("decisions","conflicts","propagations")})
    if rc==20 and "s UNSATISFIABLE" in out:
        if cert.is_file():
            if arm=="MG7_ONLY" or (arm=="UNIFIED" and kinds!=["CAPACITY_JSON_NEEDS_VERIPB"]):
                row["status"]="ERROR_PROOF_KIND_MISMATCH"
            elif drat.exists() and drat.stat().st_size:
                row["status"]="ERROR_MIXED_PROOF"
            else:
                row["status"],detail=verify_capacity(cnf,cert,case)
                row.update(detail)
        else:
            if arm=="BDD_ONLY" or (arm=="UNIFIED" and kinds!=["DRAT_PROOF"]):
                row["status"]="ERROR_PROOF_KIND_MISMATCH"
            else:
                row["status"],detail=verify_drat(cnf,drat,case)
                row.update(detail)
    elif rc==10 and "s SATISFIABLE" in out:
        if arm=="UNIFIED" and kinds!=["DRAT_PROOF"]:
            row["status"]="ERROR_MISSING_FALLBACK_MARKER"
        else:
            row["status"]="SAT_MODEL_VERIFIED" if model_checked(cnf,out) else "INVALID_SAT_MODEL"
    elif rc==0 and "s UNKNOWN" in out:
        row["status"]="UNKNOWN"
    elif rc==124:
        row["status"]="TIMEOUT"
    else:
        row["status"]="RUN_ERROR"
    return row

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    entries=synthetic()+originals()
    rows=[];failures=[]
    valid={"CAPACITY_VERIPB_VERIFIED","DRAT_UNSAT_VERIFIED","SAT_MODEL_VERIFIED","UNKNOWN","TIMEOUT"}
    for name,label,cnf in entries:
        for arm in ("BDD_ONLY","MG7_ONLY","UNIFIED"):
            row=run_case(name,label,cnf,arm)
            rows.append(row)
            print("UNIFIED1_CASE "+json.dumps(row,sort_keys=True),flush=True)
            if row["status"] not in valid:failures.append(name+" "+arm+": "+row["status"])
            if label=="SAT" and row["status"] in ("DRAT_UNSAT_VERIFIED","CAPACITY_VERIPB_VERIFIED"):
                failures.append(name+" "+arm+" false UNSAT")
            if arm!="BDD_ONLY" and not name.startswith("pcmax_") and label=="UNSAT" and row["status"]!="DRAT_UNSAT_VERIFIED":
                failures.append(name+" "+arm+" expected synthetic DRAT proof")
        (OUT/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    summary={
        "cases":len(entries),"trials":len(rows),"errors":failures,
        "original_cases":sum(name.startswith("pcmax_") for name,_,_ in entries),
        "synthetic_cases":sum(not name.startswith("pcmax_") for name,_,_ in entries),
        "verified_capacity":sum(r["arm"]=="UNIFIED" and r["status"]=="CAPACITY_VERIPB_VERIFIED" for r in rows),
        "verified_drat":sum(r["arm"]=="UNIFIED" and r["status"]=="DRAT_UNSAT_VERIFIED" for r in rows),
        "verified_models":sum(r["arm"]=="UNIFIED" and r["status"]=="SAT_MODEL_VERIFIED" for r in rows),
        "unknown":sum(r["arm"]=="UNIFIED" and r["status"] in ("UNKNOWN","TIMEOUT") for r in rows),
        "scc_hits":sum((r.get("scc_stats") or {}).get("scc_conflicts",0)
                       for r in rows if r["arm"]=="UNIFIED"),
        "note":"Retrospective original PCMAX plus synthetic controls. No blind PAR2 or universal PCMAX claim."
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("UNIFIED1_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 1 if failures else 0

if __name__=="__main__":sys.exit(main())
