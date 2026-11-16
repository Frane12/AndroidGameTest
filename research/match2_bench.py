#!/usr/bin/env python3
"""MATCH-2: paired local and Actions tests; exact DPLL small oracle and forgeries.
Source-proven small generated classes, NOT official blind benchmark or PAR2.
"""
import copy,hashlib,itertools,json,os,random
from pathlib import Path
from match2 import prove,parse
from match2_checker import verify
from structure1_prover import match1

OUT=Path("results/match2")
RNG=random.Random(16112602)
ROWS=[]

def pack(n,caps):
    m=len(caps);var=lambda j,s:1+j*m+s
    clauses=[tuple(var(j,s) for s in range(m)) for j in range(n)]
    for j in range(n):
        clauses.extend((-var(j,a),-var(j,b)) for a,b in itertools.combinations(range(m),2))
    for s,cap in enumerate(caps):
        if cap<n:
            clauses.extend(tuple(-var(j,s) for j in js)
                           for js in itertools.combinations(range(n),cap+1))
    return n*m,clauses

def dimacs(n,clauses,name):
    return (f"c {name} generated research fixture\np cnf {n} {len(clauses)}\n"
            +"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def small_dpll(n,clauses):
    """Independent recursive unit-propagating DPLL for <=18 variables."""
    def solve(assignment):
        while True:
            pending=[];unit=None
            for clause in clauses:
                if any(abs(v) in assignment and assignment[abs(v)]==(v>0) for v in clause):
                    continue
                remaining=[v for v in clause if abs(v) not in assignment]
                if not remaining:return False
                if len(remaining)==1:
                    unit=remaining[0];break
                pending.append(remaining)
            if unit is None:break
            assignment=assignment.copy();assignment[abs(unit)]=(unit>0)
        if not pending:return True
        v=abs(pending[0][0])
        yes=assignment.copy();yes[v]=True
        if solve(yes):return True
        no=assignment.copy();no[v]=False
        return solve(no)
    return "SAT" if solve({}) else "UNSAT"

def check(name,raw,label,expected_proof=False,exact=False):
    result=prove(raw)
    claimed=result["status"]=="UNSAT_UNCHECKED"
    if expected_proof and not claimed:raise AssertionError("missed "+name)
    if claimed and label=="SAT":raise AssertionError("false UNSAT "+name)
    verified=None
    if claimed:
        verified=verify(raw,result)
        if verified["status"]!="MATCH2_SOURCE_CAPACITATED_HALL_VERIFIED":
            raise AssertionError("source certificate failed "+name)
    nv,clauses=parse(raw)
    if exact and nv<=18 and small_dpll(nv,clauses)!=label:
        raise AssertionError("oracle ground truth mismatch "+name)
    # Compare without modifying the prior MATCH-1 experiment.
    old=match1(nv,clauses)
    (OUT/"cnf").mkdir(parents=True,exist_ok=True)
    (OUT/"proofs").mkdir(parents=True,exist_ok=True)
    (OUT/"cnf"/(name+".cnf")).write_bytes(raw)
    (OUT/"proofs"/(name+".json")).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    ROWS.append({"name":name,"known":label,"match2":"UNSAT" if claimed else "UNKNOWN",
                 "match1":"UNSAT" if old else "UNKNOWN",
                 "verified":bool(verified),"exact_checked":bool(exact and nv<=18),
                 "sha256":hashlib.sha256(raw).hexdigest()})

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    fixed=[
       ("capacity2_unsat",7,[2,2,2],"UNSAT"),
       ("capacity2_sat",6,[2,2,2],"SAT"),
       ("mixed_capacity_unsat",6,[1,2,2],"UNSAT"),
       ("mixed_capacity_sat",5,[1,2,2],"SAT"),
       ("pigeonhole_unsat",5,[1,1,1,1],"UNSAT"),
       ("pigeonhole_sat",4,[1,1,1,1],"SAT"),
       ("capacity3_unsat",7,[2,3,1],"UNSAT")]
    for name,n,caps,label in fixed:
        nv,cs=pack(n,caps)
        check(name,dimacs(nv,cs,name),label,label=="UNSAT",nv<=18)
    # Nonuniform independent job-column permutations: MATCH-1 fails, source proof remains valid.
    for t in range(15):
        nv,cs=pack(7,[2,2,2]);mapping=list(range(1,nv+1))
        for j in range(7):
            v=mapping[j*3:j*3+3]
            RNG.shuffle(v);mapping[j*3:j*3+3]=v
        cs=[tuple((1 if x>0 else -1)*mapping[abs(x)-1] for x in c) for c in cs]
        RNG.shuffle(cs)
        check("permuted_capacity_"+str(t),
              dimacs(nv,cs,"permuted_capacity_"+str(t)),"UNSAT",True)
    # Random distinct generated instances; independent exhaustive oracle for <=18 vars.
    for t in range(20):
        n=RNG.randint(2,5);m=RNG.randint(2,4);capacity=RNG.randint(1,2)
        nv,cs=pack(n,[capacity]*m)
        label="UNSAT" if n>m*capacity else "SAT"
        check("tiny_"+str(t),dimacs(nv,cs,"tiny_"+str(t)),label,exact=True)
    from ipg1_fixtures import petersen
    check("original_petersen_45_300",petersen().encode(),"UNSAT")
    # Removing a complete triple from a 2-capacity machine makes the
    # otherwise overloaded 7-job instance SAT (3+2+2 partition exists).
    nv,cs=pack(7,[2,2,2])
    missing=next(c for c in cs if len(c)==3 and all(x<0 for x in c))
    cs.remove(missing)
    check("missing_forbidden_triple",dimacs(nv,cs,"missing_forbidden_triple"),"SAT")
    if ROWS[-1]["match2"]!="UNKNOWN":
        raise AssertionError("incomplete source proof accepted")
    # Wrong source hashes, witness cuts, resource partitions must all fail.
    rejected=0
    for name in ("capacity2_unsat","mixed_capacity_unsat","pigeonhole_unsat"):
        raw=(OUT/"cnf"/(name+".cnf")).read_bytes()
        valid=json.loads((OUT/"proofs"/(name+".json")).read_text())
        attacks=[dict(valid,source_sha256="forged"),
                 dict(valid,capacity_bound=-1),
                 dict(valid,status="UNKNOWN")]
        bad=copy.deepcopy(valid);bad["capacities"][0]=0;attacks.append(bad)
        bad=copy.deepcopy(valid);bad["resources"]=bad["resources"][:-1]
        bad["capacities"]=bad["capacities"][:-1];attacks.append(bad)
        for attack in attacks:
            try:verify(raw,attack)
            except (ValueError,KeyError,TypeError,IndexError,OverflowError):rejected+=1
            else:raise AssertionError("forged proof accepted: "+name)
        try:verify(raw+b"c source tampered\n",valid)
        except ValueError:rejected+=1
        else:raise AssertionError("changed source accepted: "+name)
    result={
      "status":"PASS","cases":len(ROWS),
      "match2_verified_unsat":sum(x["verified"] for x in ROWS),
      "match1_detected":sum(x["match1"]=="UNSAT" for x in ROWS),
      "new_over_match1":sum(x["verified"] and x["match1"]!="UNSAT" for x in ROWS),
      "known_sat":sum(x["known"]=="SAT" for x in ROWS),
      "unknown":sum(x["match2"]=="UNKNOWN" for x in ROWS),
      "false_unsat":sum(x["known"]=="SAT" and x["verified"] for x in ROWS),
      "exact_oracle_count":sum(x["exact_checked"] for x in ROWS),
      "tamper_rejections":rejected,
      "petersen":next(x["match2"] for x in ROWS if x["name"]=="original_petersen_45_300"),
      "scope":"generated packing/PHP and historical original PCMAX; NOT official blind, DRAT, or E2E PAR2"}
    (OUT/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    (OUT/"trials.json").write_text(json.dumps(ROWS,indent=2,sort_keys=True)+"\n")
    print("MATCH2_FINAL "+json.dumps(result,sort_keys=True),flush=True)
    return 0

if __name__=="__main__":
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    raise SystemExit(run())
