#!/usr/bin/env python3
"""IPG1 first source-bound C++ union audit with independent proof check.

Only VERIFIED results enter the table. This does not demonstrate polynomial
time, new mathematics or a competitive advantage on a blind benchmark.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg1"
UNIFIED=ROOT/"build/drnas-pcmax-mg7-ipg1"
OLD=ROOT/"build/drnas-pcmax-mg7-unified"
DRAT=ROOT/"drat-trim/drat-trim"
VERIPB=ROOT/"veripb-tool/bin/veripb"
STRUCT=ROOT/"research/pcmax_capacity/check_capacity.py"
WEIGHTED=ROOT/"research/pcmax_capacity/emit_veripb_capacity_weighted2.py"
IPGCHECK=ROOT/"research/ipg1_check.py"

def execute(argv,timeout=30):
    begin=time.monotonic()
    try:
        p=subprocess.run([str(x) for x in argv],capture_output=True,text=True,timeout=timeout)
        return (p.returncode,round(time.monotonic()-begin,6),p.stdout or "",p.stderr or "")
    except subprocess.TimeoutExpired:
        return (124,round(time.monotonic()-begin,6),"","TIMEOUT")

def model_check(cnf,out):
    from ipg1_check import read_dimacs
    n,clauses=read_dimacs(cnf.read_bytes())
    assignment={}
    for line in out.splitlines():
        bits=line.split()
        if bits and bits[0]=="v":
            for literal in bits[1:]:
                v=int(literal)
                if v:assignment[abs(v)]=v>0
    return len(assignment)==n and all(any(assignment[abs(lit)]==(lit>0)
                                            for lit in clause) for clause in clauses)

def original44():
    sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
    from benchmark import materialize
    entries=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
    expected="c55ab8fe2c9e10f0579f806802bc32d04913f12cd6ce28e6662b8d59d114c174"
    matched=[e for e in entries if e["sha256"]==expected]
    if len(matched)!=1:raise ValueError("original44 source manifest mismatch")
    folder=OUT/"originals"
    folder.mkdir(exist_ok=True)
    f=materialize(matched[0],folder,True)
    if hashlib.sha256(f.read_bytes()).hexdigest()!=expected:
        raise ValueError("original44 original CNF SHA mismatch")
    return f

def one(cnf,arm,expect):
    name=cnf.stem;case=OUT/(name+"_"+arm)
    case.mkdir(exist_ok=True)
    cap=(case/"capacity.json").resolve()
    ipg=(case/"ipg.json").resolve()
    proof=(case/"fallback.drat").resolve()
    binary=UNIFIED if arm=="IPG1" else OLD
    cmd=[binary,cnf.resolve(),"--mode","core","--time","6",
         "--pcmax-capacity","--pcmax-budget-ms","500",
         "--pcmax-certificate",cap,"--residual-scc",
         "--proof",proof,"--stats"]
    if arm=="IPG1":
        cmd += ["--ipg1","--ipg1-certificate",ipg,"--ipg1-budget-ms","2000"]
    rc,wall,out,err=execute(cmd,10)
    (case/"native.log").write_text(out+"\n"+err)
    kinds=[line.rsplit(" ",1)[-1] for line in out.splitlines()
           if line.startswith("c PCMAX_UNIFIED_PROOF_KIND ")]
    row={"case":name,"arm":arm,"expected":expect,
         "sha256":hashlib.sha256(cnf.read_bytes()).hexdigest(),
         "solver_rc":rc,"native_s":wall,"kinds":kinds,
         "status":"UNKNOWN"}
    if rc==20 and "s UNSATISFIABLE" in out:
        if ipg.is_file():
            if kinds!=["IPG1_JSON_NEEDS_EXHAUSTIVE_CHECKER"] or cap.exists():
                row["status"]="BAD_PROOF_ROUTING"
            else:
                chk,secs,stdout,stderr=execute([sys.executable,IPGCHECK,cnf,ipg],30)
                (case/"independent_ipg.log").write_text(stdout+"\n"+stderr)
                row.update(checker_rc=chk,checker_s=secs)
                row["status"]="IPG1_SOURCE_VERIFIED" if chk==0 and "IPG1_SOURCE_VERIFIED " in stdout else "IPG1_REJECTED"
                if proof.exists() and proof.stat().st_size:
                    row["status"]="BAD_MIXED_PROOF"
        elif cap.is_file():
            if kinds!=["CAPACITY_JSON_NEEDS_VERIPB"]:
                row["status"]="BAD_PROOF_ROUTING"
            else:
                from check_capacity import check
                structural=check(cnf.read_bytes(),json.loads(cap.read_text()))
                if structural.get("status")!="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
                    row["status"]="CAPACITY_REJECTED"
                else:
                    pb=case/"capacity.pbp"
                    rc0,t0,pout,perr=execute([sys.executable,WEIGHTED,"--cnf",cnf,
                                               "--certificate",cap,"--output",pb],50)
                    if rc0!=0:row["status"]="PBP_PRODUCER_FAILURE"
                    else:
                        vc,sec,stdout,stderr=execute([VERIPB,"--cnf",cnf,pb],100)
                        (case/"independent_veripb.log").write_text(stdout+"\n"+stderr)
                        row.update(checker_rc=vc,checker_s=sec,pbp_producer_s=t0)
                        row["status"]="VERIPB_UNSAT_VERIFIED" if vc==0 and "s VERIFIED UNSATISFIABLE" in stdout+"\n"+stderr else "PBP_REJECTED"
        else:
            if kinds!=["DRAT_PROOF"]:
                row["status"]="BAD_PROOF_ROUTING"
            elif not proof.exists() or proof.stat().st_size==0:
                row["status"]="MISSING_DRAT"
            else:
                vc,sec,stdout,stderr=execute([DRAT,cnf,proof],100)
                (case/"independent_drat.log").write_text(stdout+"\n"+stderr)
                row.update(checker_rc=vc,checker_s=sec)
                row["status"]="DRAT_UNSAT_VERIFIED" if vc==0 and "s VERIFIED" in stdout+"\n"+stderr else "DRAT_REJECTED"
    elif rc==10 and "s SATISFIABLE" in out:
        row["status"]="SAT_MODEL_VERIFIED" if model_check(cnf,out) else "SAT_MODEL_INVALID"
    elif rc==0 and "s UNKNOWN" in out:
        row["status"]="UNKNOWN"
    else:
        row["status"]="RUN_FAILURE"
    for line in out.splitlines():
        if line.startswith("c IPG1_COVER "):
            row["ipg_telemetry"]=json.loads(line.partition(" ")[2])
    for line in err.splitlines():
        if line.startswith("MG7_RESIDUAL "):
            row["scc_telemetry"]=json.loads(line.partition(" ")[2])
    return row

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    from ipg1_fixtures import main as make_fixtures
    make_fixtures()
    original=original44()
    cases=[(OUT/"petersen3.cnf","UNSAT"),
           (OUT/"pack_7_3_capacity_2.cnf","UNSAT"),
           (OUT/"pack_5_3_capacity_2.cnf","SAT"),
           (OUT/"pack_6_3_capacity_2.cnf","SAT"),
           (original,"UNSAT")]
    # PHP 4/3 proves the inherited MG7 DRAT route is still functional.
    php=OUT/"php_4_3.cnf"
    clauses=[[i*3+j+1 for j in range(3)] for i in range(4)]
    for j in range(3):
        for i in range(4):
            for k in range(i+1,4):
                clauses.append([-(i*3+j+1),-(k*3+j+1)])
    php.write_text(f"p cnf 12 {len(clauses)}\n"+
                   "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    cases.append((php,"UNSAT"))

    errors=[];rows=[]
    for cnf,expected in cases:
        for arm in ("UNIFIED_PREVIOUS","IPG1"):
            r=one(cnf,arm,expected)
            print("IPG1_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
            rows.append(r)
            valid={"IPG1_SOURCE_VERIFIED","VERIPB_UNSAT_VERIFIED","DRAT_UNSAT_VERIFIED","SAT_MODEL_VERIFIED","UNKNOWN"}
            if r["status"] not in valid:errors.append(f"{r['case']} {arm} {r['status']}")
            if expected=="SAT" and r["status"] in ("IPG1_SOURCE_VERIFIED","VERIPB_UNSAT_VERIFIED","DRAT_UNSAT_VERIFIED"):
                errors.append(f"{r['case']} false UNSAT")
        (OUT/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")

    for name in ("petersen3","pack_7_3_capacity_2"):
        hit=[r for r in rows if r["case"]==name and r["arm"]=="IPG1"]
        if len(hit)!=1 or hit[0]["status"]!="IPG1_SOURCE_VERIFIED":
            errors.append(name+" failed IPG1 independent structural proof")

    # Mandatory corruption tests against the INDEPENDENT checker.
    cert=OUT/"petersen3_IPG1"/"ipg.json"
    if cert.is_file():
        bad=json.loads(cert.read_text())
        bad["checked_partitions"]+=1
        forged=OUT/"forged_ipg.json"
        forged.write_text(json.dumps(bad))
        rc,_,_,_=execute([sys.executable,IPGCHECK,OUT/"petersen3.cnf",forged],30)
        if rc==0:errors.append("forged partition count accepted")
        damaged=OUT/"tampered_petersen.cnf"
        damaged.write_bytes((OUT/"petersen3.cnf").read_bytes()+b"c modified bytes\n")
        rc,_,_,_=execute([sys.executable,IPGCHECK,damaged,cert],30)
        if rc==0:errors.append("source tampering accepted")
    summary={
        "cases":len(cases),"runs":len(rows),
        "ipg1_independently_verified":sum(r["arm"]=="IPG1" and r["status"]=="IPG1_SOURCE_VERIFIED" for r in rows),
        "veripb_independently_verified":sum(r["arm"]=="IPG1" and r["status"]=="VERIPB_UNSAT_VERIFIED" for r in rows),
        "drat_independently_verified":sum(r["arm"]=="IPG1" and r["status"]=="DRAT_UNSAT_VERIFIED" for r in rows),
        "sat_models_verified":sum(r["arm"]=="IPG1" and r["status"]=="SAT_MODEL_VERIFIED" for r in rows),
        "errors":errors,
        "warning":"IPG1 structural exhaustive cert is NOT DRAT/LRAT/VeriPB; cannot claim polynomial general PCMAX.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("IPG1_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 1 if errors else 0

if __name__=="__main__":sys.exit(main())
