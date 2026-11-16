#!/usr/bin/env python3
"""IPG2-A/B polynomial-scope audit: genuine fixed-types PCMAX and cubic graphs.

No generic CNF/PCMAX universal completeness claim. Two independent mathematical
source-bound checkers are always invoked. All 2/3-machine integer scheduling
tests are checked by an independent tiny exact oracle where feasible.
"""
import hashlib
import itertools
import json
import os
import pathlib
import random
import subprocess
import sys
import time

from ipg2_fixed_types import solve,canonical_sha
from ipg2_bounded_matchings import make_cases,prove,fixture

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg2_poly"
DP_CHECK=ROOT/"research/ipg2_dp_checker.py"
GRAPH_CHECK=ROOT/"research/ipg2_parity_checker.py"
rng=random.Random(16112602)

def run(argv,timeout=60):
    try:
        p=subprocess.run([str(a) for a in argv],capture_output=True,text=True,
                         timeout=timeout)
        return p.returncode,p.stdout+p.stderr
    except subprocess.TimeoutExpired:
        return 124,"TIMEOUT"

def exact_oracle(jobs,m,T):
    jobs=sorted(jobs,reverse=True)
    loads=[0]*m
    def walk(pos):
        if pos==len(jobs):return True
        v=jobs[pos]
        seen=set()
        for i in range(m):
            if loads[i] in seen:continue
            seen.add(loads[i])
            if loads[i]+v<=T:
                loads[i]+=v
                if walk(pos+1):return True
                loads[i]-=v
        return False
    return walk(0)

def schedule_tests():
    dest=OUT/"schedules";dest.mkdir(parents=True,exist_ok=True)
    rows=[];errors=[];max_elapsed=0
    # 2 and 3 machines in paired form for identical job multiset and deadline.
    # Small instances also receive an exact backtracking oracle.
    for trial in range(75):
        n=rng.randint(4,10)
        a=rng.randint(1,40)
        b=rng.randint(1,40)
        while b==a:b=rng.randint(1,40)
        jobs=[rng.choice((a,b)) for _ in range(n)]
        cap=rng.randint(max(a,b)-3,max(a,b)+sum(jobs)//2+1)
        cap=max(0,cap)
        for machines in (2,3):
            source={"durations":jobs,"machines":machines,"capacity":cap}
            path=dest/f"small_{trial:03d}_m{machines}.json"
            cert=dest/f"small_{trial:03d}_m{machines}.certificate.json"
            path.write_text(json.dumps(source,sort_keys=True)+"\n")
            evidence=solve(source)
            evidence["schedule_sha256"]=canonical_sha(source)
            cert.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
            rc,msg=run([sys.executable,DP_CHECK,path,cert])
            if rc!=0:errors.append(path.name+" independent DP rejected: "+msg[-200:])
            exact="SAT" if exact_oracle(jobs,machines,cap) else "UNSAT"
            if evidence["status"]!=exact:
                errors.append(path.name+f" DP {evidence['status']} != oracle {exact}")
            rows.append({"name":path.name,"m":machines,"n":n,"result":evidence["status"],
                         "transitions":evidence.get("transitions",0),
                         "dp_verified":rc==0})
            max_elapsed=max(max_elapsed,evidence.get("elapsed_s",0.0))
    # Larger arbitrary numeric job lengths: exact polynomial recurrence,
    # no n*T pseudo-polynomial array and no brute-force 3^n search.
    for trial in range(24):
        n=rng.randint(100,220)
        a=rng.randint(1,1000000000)
        b=rng.randint(1,1000000000)
        while a==b:b=rng.randint(1,1000000000)
        jobs=[a]*(n//2)+[b]*(n-n//2)
        rng.shuffle(jobs)
        cap=rng.randint(max(a,b),max(a,b)+2*max(a,b))
        for machines in (2,3):
            source={"durations":jobs,"machines":machines,"capacity":cap}
            path=dest/f"large_{trial:02d}_m{machines}.json"
            cert=dest/f"large_{trial:02d}_m{machines}.certificate.json"
            path.write_text(json.dumps(source,sort_keys=True)+"\n")
            evidence=solve(source)
            evidence["schedule_sha256"]=canonical_sha(source)
            cert.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
            rc,msg=run([sys.executable,DP_CHECK,path,cert])
            if rc!=0:errors.append(path.name+" large DP rejected: "+msg[-200:])
            rows.append({"name":path.name,"m":machines,"n":n,"result":evidence["status"],
                         "transitions":evidence.get("transitions",0),
                         "dp_verified":rc==0})
            max_elapsed=max(max_elapsed,evidence.get("elapsed_s",0.0))
    # Three-size CNF/scheduling cases are intentionally unsupported.
    three={"durations":[4,5,6,4,5,6,4],"machines":3,"capacity":12}
    evidence=solve(three)
    evidence["schedule_sha256"]=canonical_sha(three)
    p=dest/"three_sizes.json";c=dest/"three_sizes.certificate.json"
    p.write_text(json.dumps(three)+"\n");c.write_text(json.dumps(evidence)+"\n")
    rc,msg=run([sys.executable,DP_CHECK,p,c])
    if rc!=0 or evidence["status"]!="UNKNOWN":
        errors.append("three-size formula not safely skipped")
    # Mutated proof must be rejected.
    tampered=json.loads((dest/"small_000_m2.certificate.json").read_text())
    tampered["status"]="UNSAT" if tampered["status"]=="SAT" else "SAT"
    bad=dest/"forged.certificate.json";bad.write_text(json.dumps(tampered)+"\n")
    frc,_=run([sys.executable,DP_CHECK,dest/"small_000_m2.json",bad])
    if frc==0:errors.append("forged DP verdict was accepted")
    (OUT/"schedules_summary.json").write_text(json.dumps(rows,indent=2)+"\n")
    return {
        "cases":len(rows),"two_machines":sum(x["m"]==2 for x in rows),
        "three_machines":sum(x["m"]==3 for x in rows),
        "verified":sum(x["dp_verified"] for x in rows),
        "small_oracle_checked":150,
        "max_dp_elapsed_s":max_elapsed,
        "max_transitions":max(x["transitions"] for x in rows),
        "errors":errors
    }

def valid_source_sat(path,assigned):
    from ipg2_parity_checker import read_original
    n,clauses=read_original(path.read_bytes())
    if set(assigned)!=set(range(1,n+1)):return False
    return all(any(assigned[abs(lit)]==(lit>0) for lit in c) for c in clauses)

def graph_tests():
    dest=OUT/"graphs";dest.mkdir(parents=True,exist_ok=True)
    cases=make_cases(dest)
    rows=[];errors=[]
    for name,label,path in cases:
        raw=path.read_bytes()
        evidence=prove(raw)
        cert=dest/(name+".certificate.json")
        cert.write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
        if label=="UNSAT":
            rc,msg=run([sys.executable,GRAPH_CHECK,path,cert])
            if rc!=0 or evidence["status"]!="UNSAT_SOURCE_PARITY_CERTIFICATE_UNCHECKED":
                errors.append(name+" independent parity rejection: "+msg[-250:])
            if len(evidence.get("matchings",[]))!=6:
                errors.append("Petersen must have 6 perfect matchings")
            if evidence.get("oracle_calls",0)>250:
                errors.append("unusually many matching-oracle calls")
            # Modify witness data and assert independent verifier rejects it.
            forged=json.loads(cert.read_text())
            forged["matchings"]=forged["matchings"][:-1]
            fp=dest/"forged_missing_matching.json"
            fp.write_text(json.dumps(forged)+"\n")
            frc,_=run([sys.executable,GRAPH_CHECK,path,fp])
            if frc==0:errors.append("forged matching coverage accepted")
            modified=dest/"changed_source.cnf"
            modified.write_bytes(raw+b"c modified suffix\n")
            trc,_=run([sys.executable,GRAPH_CHECK,modified,cert])
            if trc==0:errors.append("tampered graph input accepted")
        else:
            if evidence["status"]!="UNKNOWN":
                errors.append("SAT graph claimed UNSAT by parity detector")
            # For K3,3 3-edge-color by (i+j) modulo 3.
            # The fixture generator sorts edges lexicographically.
            edges=[(i,3+j) for i in range(3) for j in range(3)]
            a={}
            for edge,(i,v) in enumerate(edges):
                color=(i+v-3)%3
                for c in range(3):a[3*edge+c+1]=(c==color)
            if not valid_source_sat(path,a):
                errors.append("K3,3 control source SAT witness invalid")
        rows.append({"name":name,"label":label,"status":evidence["status"],
                     "graph_vertices":evidence.get("graph_vertices"),
                     "matchings":len(evidence.get("matchings",[])),
                     "oracle_calls":evidence.get("oracle_calls"),
                     "producer_elapsed_s":evidence.get("elapsed_s")})
    # Original 300-clause weighted bin-packing CNF uses a DIFFERENT encoding.
    # Explicitly verify the polynomial graph recognizer rejects it rather than
    # quietly claiming a proof about original source clauses.
    from ipg1_fixtures import petersen as old_petersen_cnf
    old=dest/"original_weighted_petersen_300.cnf"
    old.write_bytes(old_petersen_cnf().encode())
    rejected=False
    try:
        prove(old.read_bytes())
    except ValueError:
        rejected=True
    if not rejected: errors.append("polynomial graph recognizer misidentified original 300-clause encoding")
    (OUT/"graphs_summary.json").write_text(json.dumps(rows,indent=2)+"\n")
    return {"cases":len(rows),"petersen_matching_count":rows[0]["matchings"],
            "petersen_oracle_calls":rows[0]["oracle_calls"],
            "petersen_producer_s":rows[0]["producer_elapsed_s"],
            "graph_original_300_supported":not rejected,"errors":errors}

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    st=time.perf_counter()
    dp=schedule_tests()
    print("IPG2_DP_TOTAL "+json.dumps(dp,sort_keys=True),flush=True)
    g=graph_tests()
    print("IPG2_GRAPH_TOTAL "+json.dumps(g,sort_keys=True),flush=True)
    summary={
        "status":"PASS" if not dp["errors"] and not g["errors"] else "FAIL",
        "dp":dp,"graphs":g,
        "total_elapsed_s":round(time.perf_counter()-st,4),
        "note":"Fixed-type PCMAX is polynomial. Bounded-matching parity is polynomial for fixed K on graph-edge-coloring SOURCE encoding only. Prior original weighted 300 CNF is unsupported by this proof route. No P=NP claim, no generic real CNF gain."
    }
    (OUT/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("IPG2_POLY_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if summary["status"]=="PASS" else 1
if __name__=="__main__":sys.exit(main())
