#!/usr/bin/env python3
"""MG7 proof-first residual SCC pilot; strict independent DRAT and SAT model audit.

Two independently compiled C++ arms, same original DIMACS per pair, serial
single logical CPU. All generated original inputs and claimed proof logs are
preserved in CI artifacts. No result classified verified from solver text alone.
"""
import hashlib
import itertools
import json
import os
import pathlib
import resource
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/mg7_residual"
BINARY={"BASE":ROOT/"build/drnas-mg7-base", "RESIDUAL":ROOT/"build/drnas-mg7-scc"}
VERIFIER=ROOT/"drat-trim/drat-trim"
MAX_PROOF=36*1024*1024

def make_cnf(path,n,clauses):
    path.write_text("p cnf "+str(n)+" "+str(len(clauses))+"\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))

def read_cnf(path):
    raw=path.read_bytes()
    parts=raw.decode("ascii").splitlines()
    nvar=ncl=None
    clauses=[];partial=[]
    for line in parts:
        tok=line.split()
        if not tok or tok[0]=="c": continue
        if tok[0]=="p":
            if nvar is not None or tok[1]!="cnf":raise ValueError("bad header")
            nvar,ncl=int(tok[2]),int(tok[3])
            continue
        for t in tok:
            v=int(t)
            if v:partial.append(v)
            else:clauses.append(partial);partial=[]
    if nvar is None or ncl!=len(clauses) or partial:raise ValueError("bad source")
    return nvar,clauses

def model_valid(stdout, cnf):
    n,clauses=read_cnf(cnf)
    values={}
    for line in stdout.splitlines():
        tok=line.split()
        if tok and tok[0]=="v":
            for item in tok[1:]:
                v=int(item)
                if v:values[abs(v)]=(v>0)
    if len(values)!=n:
        return False
    return all(any(values[abs(v)]==(v>0) for v in c) for c in clauses)

def file_limit():
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_PROOF,MAX_PROOF))

def execute(args,timeout,proof_limit=False):
    start=time.perf_counter()
    try:
        r=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=timeout,
                         preexec_fn=file_limit if proof_limit else None)
        return (r.returncode,round(time.perf_counter()-start,6),r.stdout or "",r.stderr or "")
    except subprocess.TimeoutExpired:
        return (124,round(time.perf_counter()-start,6),"","TIMEOUT")

def generate_cases():
    OUT.mkdir(parents=True,exist_ok=True)
    names=[]
    # Pure binary contradiction, without initial unit propagation.
    make_cnf(OUT/"binary_unsat.cnf",2,[(1,2),(-1,2),(1,-2),(-1,-2)])
    names.append(("binary_unsat", "UNSAT",OUT/"binary_unsat.cnf"))
    # Four 3-clauses become an inconsistent 2-CNF after unit g=TRUE;
    # unrelated long clause stays open. This must work *without* all clauses
    # reducing to residual width <=2.
    base=[(1,),(-1,2,3),(-1,-2,3),(-1,2,-3),(-1,-2,-3),(4,5,6)]
    make_cnf(OUT/"residual_unsat_long.cnf",6,base)
    names.append(("residual_unsat_long","UNSAT",OUT/"residual_unsat_long.cnf"))
    def php(n,m):
        c=[tuple(i*m+j+1 for j in range(m)) for i in range(n)]
        for j in range(m):
            for i,k in itertools.combinations(range(n),2):
                c.append((-(i*m+j+1),-(k*m+j+1)))
        return c
    for n,m in [(3,2),(4,3),(5,4),(3,3),(4,4)]:
        dest=OUT/f"php_{n}_{m}.cnf"
        make_cnf(dest,n*m,php(n,m))
        names.append((dest.stem,"UNSAT" if n>m else "SAT",dest))
    # Known SAT 3-CNF with irreducible long clauses.
    make_cnf(OUT/"simple_sat.cnf",4,[(1,2,3),(-1,2,4),(1,-2,-4)])
    names.append(("simple_sat","SAT",OUT/"simple_sat.cnf"))
    # Deterministic SAT by construction; never create false UNSAT.
    import random
    rng=random.Random(711162026)
    for i in range(12):
        n=16
        model={j:rng.choice((False,True)) for j in range(1,n+1)}
        clauses=[]
        for _ in range(80):
            vars_=rng.sample(range(1,n+1),rng.randint(2,5))
            lits=[v if rng.randrange(2) else -v for v in vars_]
            if not any(model[abs(v)]==(v>0) for v in lits):lits[0]=-lits[0]
            clauses.append(tuple(lits))
        path=OUT/f"planted_sat_{i:02d}.cnf"
        make_cnf(path,n,clauses)
        names.append((path.stem,"SAT",path))
    return names

def originals():
    sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
    from benchmark import materialize
    entries=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
    orig=OUT/"originals"
    orig.mkdir(exist_ok=True)
    result=[]
    for i in [0,2,1,6]:
        e=entries[i]
        path=materialize(e,orig,True)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==e["sha256"],"frozen SHA mismatch"
        result.append((f"original_{i:02d}",e["expected_status"],path))
    return result

def run_case(label,expected,path,arm,orig):
    proof=OUT/(label+"_"+arm+".drat")
    args=[BINARY[arm],path,"--mode","core","--time","4" if orig else "7",
          "--stats","--proof",proof]
    if arm=="RESIDUAL":args.append("--residual-scc")
    rc,wall,out,err=execute(args,9 if orig else 11,True)
    (OUT/(label+"_"+arm+".log")).write_text((out+"\n"+err)[-24000:])
    row={"name":label,"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
         "expected":expected,"arm":arm,"solver_rc":rc,"solver_wall_s":wall,
         "status":"UNKNOWN","residual_telemetry":None}
    for line in err.splitlines():
        if line.startswith("MG7_RESIDUAL "):
            row["residual_telemetry"]=json.loads(line.partition(" ")[2])
        if line.startswith("X41_STATS "):
            info=json.loads(line.partition(" ")[2])
            row.update({k:info.get(k) for k in ("decisions","conflicts","propagations")})
    if rc==20 and "s UNSATISFIABLE" in out:
        if not proof.exists() or proof.stat().st_size==0:
            row["status"]="UNVERIFIED_NO_PROOF"
        else:
            vr,vsec,vout,verr=execute([VERIFIER,path,proof],80)
            row.update(checker_rc=vr,checker_s=vsec,proof_bytes=proof.stat().st_size)
            (OUT/(label+"_"+arm+".checker.log")).write_text((vout+"\n"+verr)[-18000:])
            if vr==0 and "s VERIFIED" in (vout+"\n"+verr):
                row["status"]="DRAT_UNSAT_VERIFIED"
            else:
                row["status"]="UNVERIFIED_REJECTED"
    elif rc==10 and "s SATISFIABLE" in out:
        row["status"]="SAT_MODEL_VERIFIED" if model_valid(out,path) else "SAT_MODEL_INVALID"
    elif rc in (0,124):
        row["status"]="UNKNOWN" if rc==0 else "TIMEOUT"
    else:
        row["status"]="RUN_ERROR"
    return row

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    items=generate_cases()+originals()
    rows=[];failures=[]
    for name,expected,path in items:
        is_original=name.startswith("original_")
        for arm in ("BASE","RESIDUAL"):
            row=run_case(name,expected,path,arm,is_original)
            rows.append(row)
            print("MG7_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
            if row["status"] in ("UNVERIFIED_NO_PROOF","UNVERIFIED_REJECTED","RUN_ERROR","SAT_MODEL_INVALID"):
                failures.append(name+" "+arm+" "+row["status"])
            if expected=="SAT" and row["status"]=="DRAT_UNSAT_VERIFIED":
                failures.append(name+" "+arm+" falsely UNSAT")
            if not is_original and expected=="UNSAT" and row["status"]!="DRAT_UNSAT_VERIFIED":
                failures.append(name+" "+arm+" expected formal UNSAT")
        (OUT/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    summary={
        "cases":len(items),"trials":len(rows),
        "baseline_verified_unsat":sum(r["arm"]=="BASE" and r["status"]=="DRAT_UNSAT_VERIFIED" for r in rows),
        "residual_verified_unsat":sum(r["arm"]=="RESIDUAL" and r["status"]=="DRAT_UNSAT_VERIFIED" for r in rows),
        "residual_scc_hits":sum((r.get("residual_telemetry") or {}).get("scc_conflicts",0) for r in rows),
        "residual_nogoods":sum((r.get("residual_telemetry") or {}).get("nogoods",0) for r in rows),
        "verified_models":sum(r["status"]=="SAT_MODEL_VERIFIED" for r in rows),
        "failures":failures,
        "note":"First-pass synthetic + 4 known original PCMAX CNFs, NOT blind PAR2."
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("MG7_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 1 if failures else 0

if __name__=="__main__":
    sys.exit(main())
