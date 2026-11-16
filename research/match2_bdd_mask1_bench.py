#!/usr/bin/env python3
"""Source-frozen MATCH2 -> exact-mask/implicit-BDD research pilot.
Petersen original 45/300 is an ALREADY KNOWN UNSAT instance, not discovery.
NO general polynomial algorithm or verified official blind PAR2 claim.
"""
import copy
import hashlib
import itertools
import json
import os
import pathlib
import random
from match2 import prove as old_match2
from match2_bdd_mask1 import prove as new_proof,parse
from match2_bdd_mask1_checker import check as independently_check
from ipg1_fixtures import petersen,pack

ROOT=pathlib.Path("results/match2_bdd_mask1")
rows=[]
rng=random.Random(202611161052)
EXPECTED_PETERSEN_SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def encode(nvars,clauses,tag):
    return (f"c {tag}\np cnf {nvars} {len(clauses)}\n"
            + "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def source_sat_model(raw,assignment):
    _,clauses=parse(raw)
    for clause in clauses:
        if not any(assignment.get(abs(lit),False)==(lit>0) for lit in clause):
            return False
    return True

def known_pack_model(n,m=3):
    # For capacity two, 2 jobs per machine; all literals assigned.
    assignment={}
    for job in range(n):
        machine=job//2
        for s in range(m):
            assignment[job*m+s+1]=(s==machine)
    return assignment

def test_case(name,raw,expected,model=None,require_new=False,required_counts=None):
    sourcepath=ROOT/"originals"/(name+".cnf")
    sourcepath.parent.mkdir(parents=True,exist_ok=True)
    sourcepath.write_bytes(raw)
    if model is not None:
        if expected!="SAT" or not source_sat_model(raw,model):
            raise AssertionError(name+" invalid independent SAT witness")
    old=old_match2(raw)
    new=new_proof(raw)
    verified=None
    if new["status"]=="UNSAT_UNCHECKED":
        verified=independently_check(raw,new)
        if expected=="SAT":
            raise AssertionError(name+" false source UNSAT")
    elif new["status"]!="UNKNOWN":
        raise AssertionError(name+" unsupported claim status")
    if expected=="UNSAT" and require_new and verified is None:
        raise AssertionError(name+" expected new source proof")
    if required_counts is not None and (
            new.get("allowed_support_counts")!=required_counts[0] or
            new.get("reachable_mask_counts")!=required_counts[1]):
        raise AssertionError(name+" unexpected reproducibility counts")
    if name=="petersen_45_300" and old["status"]=="UNSAT_UNCHECKED":
        raise AssertionError("prior MATCH2 unexpectedly solved Petersen")
    certpath=ROOT/"certificates"/(name+".json")
    certpath.parent.mkdir(parents=True,exist_ok=True)
    certpath.write_text(json.dumps(new,sort_keys=True,indent=2)+"\n")
    rows.append({
        "name":name,"expected":expected,
        "original_sha256":hashlib.sha256(raw).hexdigest(),
        "old_match2":old["status"],"bridge":new["status"],
        "external_check":verified["status"] if verified else "UNKNOWN",
        "jobs":new.get("jobs"),"machines":new.get("machines"),
        "machine_profiles":new.get("allowed_support_counts"),
        "reachable_layers":new.get("reachable_mask_counts"),
        "sat_model_verified":model is not None})
    return new

def build():
    original=petersen().encode()
    if hashlib.sha256(original).hexdigest()!=EXPECTED_PETERSEN_SHA:
        raise AssertionError("original 45/300 bytes changed")
    verified=test_case(
        "petersen_45_300",original,"UNSAT",require_new=True,
        required_counts=([7036,7036,7036],[1,7036,25694,32766]))
    # Same original clauses, globally relabeled variables and re-shuffled
    # clauses; SHA is different but source-grounded proof must survive.
    _,clauses=parse(original)
    for t in range(2):
        mapping=list(range(1,46));rng.shuffle(mapping)
        mutated=[tuple((1 if lit>0 else -1)*mapping[abs(lit)-1]
                       for lit in clause) for clause in clauses]
        rng.shuffle(mutated)
        raw=encode(45,mutated,"permuted genuine original Petersen")
        test_case("petersen_permuted_"+str(t),raw,"UNSAT",require_new=True)
    for n in (5,6,7,8):
        nv,cs=pack(n,2)
        raw=encode(nv,cs,"original packed capacity 2, generated")
        model=known_pack_model(n) if n<=6 else None
        test_case("pack_"+str(n)+"_capacity2",raw,
                  "SAT" if n<=6 else "UNSAT",
                  model=model,require_new=n>=7)
    # Remove exactly ONE forbidden triple from a 7-job/three-resource
    # pigeonhole source: that specific triple can share a resource,
    # and two other pairs occupy the remaining machines.
    nv,cs=pack(7,2)
    missing=next(c for c in cs if len(c)==3 and all(l<0 for l in c))
    cs.remove(missing)
    changed=encode(nv,cs,"weakened capacity 2 triple")
    assignment={}
    on_machine_zero={(-l-1)//3 for l in missing}
    rest=[j for j in range(7) if j not in on_machine_zero]
    assignment_to_machine={j:0 for j in on_machine_zero}
    for j in rest[:2]:assignment_to_machine[j]=1
    for j in rest[2:]:assignment_to_machine[j]=2
    for j in range(7):
        for s in range(3):
            assignment[3*j+s+1]=(assignment_to_machine[j]==s)
    test_case("single_missing_capacity_triple",changed,"SAT",model=assignment)
    # Removing every weighted packing forbidden clause leaves 15
    # independent source exactly-one groups: SAT model exists.
    stripped=[c for c in clauses if len(c)==3 and all(v>0 for v in c)
              or len(c)==2 and all(v<0 and
                                  (abs(v)-1)//3==(abs(c[0])-1)//3 for v in c)]
    if len(stripped)!=60:
        raise AssertionError("expected 15 ALO and 45 AMO")
    weakened=encode(45,stripped,"removed ALL weighted packing conflicts")
    all_machine_zero={3*j+s+1:(s==0) for j in range(15) for s in range(3)}
    test_case("petersen_all_weighted_forbiddens_removed",weakened,
              "SAT",model=all_machine_zero)

    # Independent verifier must fail all malicious proof mutations.
    rejected=0
    for name in ("petersen_45_300","pack_7_capacity2"):
        raw=(ROOT/"originals"/(name+".cnf")).read_bytes()
        valid=json.loads((ROOT/"certificates"/(name+".json")).read_text())
        invalids=[dict(valid,source_sha256="0"*64),
                  dict(valid,status="UNKNOWN"),
                  dict(valid,allowed_support_counts=[0]*valid["machines"]),
                  dict(valid,reachable_mask_counts=[1]*(valid["machines"]+1))]
        bad=copy.deepcopy(valid);bad["groups"][0][0]=bad["groups"][1][0]
        invalids.append(bad)
        bad=copy.deepcopy(valid);bad["resources"][0]=bad["resources"][0][:-1]
        invalids.append(bad)
        for attack in invalids:
            try:independently_check(raw,attack)
            except (ValueError,TypeError,KeyError,IndexError,OverflowError):
                rejected+=1
            else:raise AssertionError(name+" forged certificate accepted")
        try:independently_check(raw+b"c modified source suffix\n",valid)
        except ValueError:rejected+=1
        else:raise AssertionError(name+" changed original source accepted")
    result={
        "status":"PASS","cases":len(rows),
        "source_verified_unsat":sum(row["external_check"].endswith("VERIFIED") for row in rows),
        "sat_controls":sum(row["sat_model_verified"] for row in rows),
        "false_unsat":sum(row["expected"]=="SAT" and row["external_check"].endswith("VERIFIED") for row in rows),
        "tamper_rejected":rejected,
        "original_petersen_recovered":rows[0]["external_check"].endswith("VERIFIED"),
        "original_petersen_sha256":EXPECTED_PETERSEN_SHA,
        "original_petersen_profile_counts":rows[0]["machine_profiles"],
        "original_petersen_reachable_layers":rows[0]["reachable_layers"],
        "original_petersen_old_match2":rows[0]["old_match2"],
        "scope":"retrospective source-frozen exact mask DP, exponential in job count, not native BDD1 graph or standard DRAT/VeriPB, not blind official E2E PAR2"}
    (ROOT/"summary.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    (ROOT/"trials.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
    print("MATCH2_BDD_MASK1_FINAL "+json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    build()
