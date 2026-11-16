#!/usr/bin/env python3
"""IPG2-CNF BRIDGE1: proof-gated original-source comparison.

A. Generate exact DIMACS CNF encodings of small *real scheduling decisions*
   with two duration types for 2 and 3 machines, and paired 2/3 variants.
   These are constructed controls, NOT official SAT Competition originals.
B. Re-open 8 SHA-frozen original benchmark PCMAX CNFs; never infer structure
   from filename or known source label (harness uses label only for auditing).
C. Include Petersen 45-var/300-clause old representation; never claim proof
   unless independent source count checker accepts it.
D. Reject forged source hashes, fake count bounds, and tampered certificates.

Any claim is accepted only if independent checker recomputes original premises
and DP. It is NOT DRAT/VeriPB and results are not verified competition PAR2.
One logical CPU, serial, bounded pattern rank 3 and 2 type classes.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
from ipg2_cnf_bridge import analyze
from ipg1_fixtures import petersen
from ipg2_poly_benchmark import exact_oracle

OUT=ROOT/"results/ipg2_cnf_bridge"
CHECK=ROOT/"research/ipg2_cnf_checker.py"
RNG=random.Random(26111601)

def run(*cmd):
    p=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,timeout=45)
    return p.returncode,(p.stdout or "")+(p.stderr or "")

def encode(jobs,m,cap):
    n=len(jobs)
    x=lambda j,k: j*m+k+1
    clauses=[]
    for j in range(n):
        clauses.append(tuple(x(j,k) for k in range(m)))
        for a,b in itertools.combinations(range(m),2):
            clauses.append((-x(j,a),-x(j,b)))
    # Exact bin-packing CNF: for each machine, forbid every inclusion-minimal
    # job subset whose sum exceeds the capacity. Thus the source CNF is
    # equisatisfiable with the explicit scheduling problem.
    minimal=[]
    for mask in range(1,1<<n):
        selected=[j for j in range(n) if mask>>j&1]
        total=sum(jobs[j] for j in selected)
        if total<=cap or any(total-jobs[j]>cap for j in selected):
            continue
        minimal.append(tuple(selected))
    for S in minimal:
        for k in range(m):
            clauses.append(tuple(-x(j,k) for j in S))
    return (f"c Exact direct PCMAX one-hot generated source; jobs={len(jobs)} machines={m}\n"
            +f"p cnf {n*m} {len(clauses)}\n"
            +"".join(" ".join(map(str,c))+" 0\n" for c in clauses)),len(minimal)

def inspect(name,raw,expected,kind,short_stats=False):
    path=OUT/(name+".cnf")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)
    r=analyze(raw)
    file=OUT/(name+".certificate.json")
    file.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
    row={
        "name":name,"source_kind":kind,"expected":expected,
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "bridge_status":r.get("status"),"reason":r.get("reason"),
        "jobs":r.get("jobs"),"machines":r.get("machines"),
        "types":list(map(len,r.get("classes",[]))),
        "producer_elapsed_s":r.get("elapsed_s"),
        "verified":False
    }
    if r["status"]=="UNSAT_SOURCE_COUNT_CERTIFICATE_UNCHECKED":
        rc,out=run(sys.executable,CHECK,path,file)
        (OUT/(name+".checker.log")).write_text(out)
        row["verified"]=bool(rc==0 and "IPG2_BRIDGE_ACCEPT " in out)
        if not row["verified"]:
            row["failure"]="independent source count proof rejected"
        if expected=="SAT":
            row["failure"]="false UNSAT on independent SAT oracle"
    elif r["status"]!="UNKNOWN":
        row["failure"]="unexpected unverified bridge status"
    if short_stats or row["verified"]:
        print("BRIDGE_CASE "+json.dumps(row,sort_keys=True),flush=True)
    return row

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[];errors=[]
    begin=time.monotonic()
    targeted=[
        ("two_vs_three_three_jobs",[6,6,6],10),
        ("count_gap_6_3",[6,6,6,3,3,3,3],10),
        ("count_feasible_6_3",[6,6,6,3,3,3],10),
        ("equal_size_seven",[5]*7,9),
        ("equal_size_six",[4]*6,8),
    ]
    for trial in range(30):
        n=RNG.randint(4,10)
        a,b=RNG.sample(range(2,13),2)
        times=[RNG.choice((a,b)) for _ in range(n)]
        cap=RNG.randint(max(times)-1,max(times)+max(times))
        targeted.append((f"random_{trial:02d}",times,cap))
    for label,times,cap in targeted:
        for machines in (2,3):
            raw,oversets=encode(times,machines,cap)
            expected="SAT" if exact_oracle(times,machines,cap) else "UNSAT"
            row=inspect(f"generated/{label}_m{machines}",raw.encode(),expected,
                        "exact_generated_scheduling",short_stats=label.startswith(("two_vs","count_")))
            row.update(jobs=len(times),durations_distinct=len(set(times)),
                       source_minimal_overload_sets=oversets)
            rows.append(row)
            if row.get("failure"): errors.append(row["name"]+": "+row["failure"])
    target=next((r for r in rows if r["name"]=="generated/count_gap_6_3_m3"),None)
    if target is None or not target["verified"]:
        errors.append("bridge failed required mixed two-size / 3-machine count-gap test")
    old=petersen().encode()
    row=inspect("petersen_45v_300c",old,"UNSAT","original_older_weighted_encoding",True)
    rows.append(row)
    if row.get("failure"):errors.append(row["failure"])
    sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
    from benchmark import materialize
    manifest=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
    orig=OUT/"originals";orig.mkdir(exist_ok=True)
    for i in [0,2,5,10,1,6,11,12]:
        e=manifest[i]
        path=materialize(e,orig,True)
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=e["sha256"]:
            errors.append(e["name"]+": original source byte hash mismatch")
            continue
        row=inspect(f"official_original_{i:02d}",raw,e["expected_status"],
                    "official_original_PCMax_BDD",True)
        rows.append(row)
        if row.get("failure"):errors.append(row["name"]+": "+row["failure"])
    # All independent verifier mutation tests must reject.
    good=next((r for r in rows if r["verified"]),None)
    if good is None:
        errors.append("no source-verified bridge certificate to adversarially test")
    else:
        name=good["name"];rawpath=OUT/(name+".cnf")
        cert=json.loads((OUT/(name+".certificate.json")).read_text())
        mutations=[
            ("sha",{"source_sha256":"0"*64}),
            ("dp",{"reachable_sizes":[1,1,1]}),
            ("unsupported",{"status":"SAT"}),
            ("patterns",{"forbidden_counts":[[[0,1]],[[0,1]],[[0,1]]]}),
        ]
        for kind,changes in mutations:
            forged={**cert,**changes}
            out=OUT/(f"forged_{kind}.json")
            out.write_text(json.dumps(forged)+"\n")
            rc,msg=run(sys.executable,CHECK,rawpath,out)
            if rc==0:errors.append("independent checker accepted "+kind+" mutation")
        changed=OUT/"tampered_original.cnf"
        changed.write_bytes(rawpath.read_bytes()+b"c changed source bytes\n")
        rc,_=run(sys.executable,CHECK,changed,OUT/(name+".certificate.json"))
        if rc==0:errors.append("source byte modification accepted")
    summary={
        "generated_cases":sum(r["source_kind"]=="exact_generated_scheduling" for r in rows),
        "original_cases":sum(r["source_kind"]=="official_original_PCMax_BDD" for r in rows),
        "old_petersen_cases":1,
        "generated_verified_unsat":sum(r["verified"] and r["source_kind"]=="exact_generated_scheduling" for r in rows),
        "original_verified_unsat":sum(r["verified"] and r["source_kind"]=="official_original_PCMax_BDD" for r in rows),
        "original_unknown":sum(r["bridge_status"]=="UNKNOWN" and r["source_kind"]=="official_original_PCMax_BDD" for r in rows),
        "generated_unsat":sum(r["expected"]=="UNSAT" and r["source_kind"]=="exact_generated_scheduling" for r in rows),
        "generated_sat":sum(r["expected"]=="SAT" and r["source_kind"]=="exact_generated_scheduling" for r in rows),
        "source_bound_checked":sum(r["verified"] for r in rows),
        "errors":errors,
        "wall_elapsed_s":round(time.monotonic()-begin,3),
        "warning":"Retrospective exact-generated direct PCMAX and source-frozen BDD originals. No new UNSAT claim without independent checker; no standard VeriPB/DRAT, no blind PAR2 or generic PCMAX algorithm."
    }
    (OUT/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("BRIDGE_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if not errors else 1
if __name__=="__main__":raise SystemExit(main())
