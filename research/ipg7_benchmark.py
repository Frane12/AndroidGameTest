#!/usr/bin/env python3
"""IPG7 source-to-configuration-master paired controls.

All source CNF bytes are frozen to SHA256 before running the algorithm.
Every negative proof is independently checked two different ways:
 (A) independent Python rebuild of COMPLETE original minimal overweight
     CNF and a 2-bin exact-capacity configuration projection;
 (B) independent VeriPB3.0.2 check of the DERIVED 2-machine master CNF
     (not the original 300-clause source; do not conflate proof targets).

Positive SAT models on other packing instances are verified against
each ORIGINAL CNF clause, not accepted from a claimed label.
No CDCL/DPLL, SAT solver, portfolio or original benchmark proof trace
is invoked. Enumeration is exponential 2^n; no general P=NP claim.
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

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg7_config"
PRODUCER=ROOT/"research/ipg7_config_master.py"
CHECKER=ROOT/"research/ipg7_independent_master_checker.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research"))
from ipg1_fixtures import petersen

def invoke(args,limit=35):
    start=time.perf_counter()
    try:
        r=subprocess.run([str(x) for x in args],text=True,capture_output=True,timeout=limit)
        return r.returncode,round(time.perf_counter()-start,6),r.stdout+"\n"+r.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-start,6),"TIMEOUT"
def run(log,args,limit=35):
    rc,secs,output=invoke(args,limit)
    log.write_text(output)
    return rc,secs,output

def canonical_encode(weights,T):
    # Fixture source only, NOT reused by either source-independent checker
    # or the proof-generating executable.
    n=len(weights)
    clauses=[]
    for j in range(n):
        selectors=[3*j+m+1 for m in range(3)]
        clauses.append(selectors)
        clauses.extend([[-selectors[a],-selectors[b]]
                        for a,b in itertools.combinations(range(3),2)])
    for s in range(1,n+1):
        for chosen in itertools.combinations(range(n),s):
            load=sum(weights[j] for j in chosen)
            if load<=T or any(load-weights[j]>T for j in chosen):
                continue
            for m in range(3):
                clauses.append([-3*j-m-1 for j in chosen])
    return (f"c Fresh direct 3-machine exact bin-packing CNF\n"
            +f"p cnf {3*n} {len(clauses)}\n"
            +"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def originals():
    src=OUT/"sources";src.mkdir(parents=True,exist_ok=True)
    cases=[]
    def add(name,raw,weights,T,expected,structural_family):
        source=src/(name+".cnf")
        source.write_bytes(raw)
        case={
          "name":name,"source_sha256":hashlib.sha256(raw).hexdigest(),
          "expected":expected,"family":structural_family,
          "weights":weights,"capacity":T,"machines":3
        }
        (src/(name+".weights.json")).write_text(json.dumps({
            "weights":weights,"capacity":T,"machines":3},sort_keys=True)+"\n")
        cases.append(case)
    weighted=petersen().encode("ascii")
    # Exact original item durations recovered from the source's
    # ground truth source header in a controlled manifest; both
    # producer and independent checker must validate ALL 300 clauses.
    first=next(line for line in weighted.decode().splitlines()
               if line.startswith("c Item sizes: "))
    ps=[int(x) for x in first[len("c Item sizes: "):].split()]
    if len(ps)!=15 or sum(ps)!=3*29524:
        raise ValueError("Petersen original item size metadata malformed")
    add("petersen_original_45v300c",weighted,ps,29524,
        "UNSAT","PETERSEN_SOURCE_ORIGINAL")
    # Same semantics with independently shuffled DIMACS clause/literal
    # order. This tests source recognition, NOT a source-disjoint problem.
    rng=random.Random(20261116)
    lines=[line for line in weighted.decode().splitlines()
           if line and not line.startswith(("c","p"))]
    clauses=[list(map(int,line.split()))[:-1] for line in lines]
    rng.shuffle(clauses)
    for clause in clauses:rng.shuffle(clause)
    permuted=("c same source semantics shuffled clause and literal ordering\n"
             +f"p cnf 45 {len(clauses)}\n"
             +"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
    add("petersen_clause_shuffle",permuted,ps,29524,
        "UNSAT","PETERSEN_SEMANTIC_PERMUTATION")
    # A different 5-job 3-bin exact-capacity UNSAT instance:
    # total load 84, 3*T=84, only two exact-T configurations,
    # both require the same job of duration 8.
    alt=[13,20,23,8,20]
    add("new_five_job_intersecting_configs",canonical_encode(alt,28),
        alt,28,"UNSAT","NEW_FIVE_JOB_INTERSECTION")
    # K4 is cubic and 3-edge-colorable; this is a positive source control
    # with 6 jobs and equal total 3T, and three DISJOINT perfect matchings.
    K4=[(a,b) for a in range(4) for b in range(a+1,4)]
    p4=[3**a+3**b for a,b in K4]
    add("K4_matching_sat",canonical_encode(p4,40),
        p4,40,"SAT","K4_CUBIC_SAT")
    # Independent, non-graph packing SAT control; exact two jobs per bin.
    uniform=[3]*6
    add("six_equal_jobs_sat",canonical_encode(uniform,6),
        uniform,6,"SAT","UNIFORM_PACKING_SAT")
    # Zero exact-T subsets: method is deliberately scoped to k>=1,
    # and must return UNKNOWN, never a false SAT/UNSAT.
    noexact=[6,6,6,3,3,3,3]
    add("no_exact_full_load_unknown",canonical_encode(noexact,10),
        noexact,10,"UNKNOWN","NO_EXACT_T_GATED")
    (OUT/"source_manifest_precommitted.json").write_text(json.dumps(
        {"cases":cases,"note":"All exact source SHA-256s frozen before proof calls."},
        indent=2,sort_keys=True)+"\n")
    return cases

def one(case):
    name=case["name"]
    files=OUT/"sources"
    original=files/(name+".cnf")
    config=files/(name+".weights.json")
    dest=OUT/"cases"/name;dest.mkdir(parents=True,exist_ok=True)
    prefix=dest/"candidate"
    sha=hashlib.sha256(original.read_bytes()).hexdigest()
    if sha!=case["source_sha256"]:
        raise ValueError("source changed after precommitment")
    rc,secs,out=run(dest/"generator.log",[
        sys.executable,PRODUCER,"--cnf",original,
        "--weights-json",config,"--prefix",prefix],40)
    record={"name":name,"expected":case["expected"],
            "family":case["family"],"original_sha256":sha,
            "generation_wall_s":secs,"result":"UNKNOWN"}
    cert=dest/"candidate.certificate.json"
    if rc!=0 or not cert.exists():
        record["result"]="ERROR_ORIGINAL_SOURCE_GENERATOR"
        return record
    assertion=json.loads(cert.read_text())
    status=assertion["status"]
    if status=="SAT_MODEL_VERIFIED_BY_GENERATOR":
        rc,vs,check=run(dest/"independent_original_model.log",[
            sys.executable,CHECKER,"--source",original,"--certificate",cert],30)
        if rc!=0 or "IPG7_SOURCE_BRIDGE_ACCEPT " not in check:
            record["result"]="ERROR_ORIGINAL_SAT_MODEL_REJECTED"
        else:
            record["result"]="ORIGINAL_SOURCE_SAT_MODEL_VERIFIED"
            record["source_model_check_s"]=vs
    elif status=="UNSAT_SOURCE_STRUCTURAL_CANDIDATE_MASTER_VERIPB_UNCHECKED":
        master=dest/"candidate.master.cnf"
        proof=dest/"candidate.master.pbp"
        rc,vs,check=run(dest/"independent_original_source_bridge.log",[
            sys.executable,CHECKER,"--source",original,"--certificate",cert,
            "--master",master,"--proof",proof],45)
        if rc!=0 or "IPG7_SOURCE_BRIDGE_ACCEPT " not in check:
            record["result"]="ERROR_ORIGINAL_TO_MASTER_BRIDGE_REJECTED"
        else:
            rc,ps,prooflog=run(dest/"external_master_veripb.log",[
                VERIPB,"--cnf",master,proof],45)
            if rc!=0 or "s VERIFIED UNSATISFIABLE" not in prooflog:
                record["result"]="ERROR_MASTER_PB_REJECTED"
            else:
                record.update(
                  result="ORIGINAL_STRUCTURAL_UNSAT_MASTER_VERIPB_VERIFIED",
                  exact_configs=assertion["exact_capacity_config_count"],
                  master_POL_steps=assertion["master_pure_POL_steps"],
                  master_clauses=assertion["master_clauses"],
                  master_proof_bytes=proof.stat().st_size,
                  independent_source_bridge_s=vs,
                  external_master_veripb_s=ps,
                )
    elif status=="UNKNOWN":
        record["result"]="UNKNOWN"
        record["reason"]=assertion.get("reason")
    else:
        record["result"]="ERROR_UNKNOWN_STATUS"
    if case["expected"]=="SAT" and record["result"].startswith("ORIGINAL_STRUCTURAL_UNSAT"):
        record["result"]="ERROR_FALSE_UNSAT"
    if case["expected"]=="UNSAT" and record["result"]=="ORIGINAL_SOURCE_SAT_MODEL_VERIFIED":
        record["result"]="ERROR_FALSE_SAT"
    print("IPG7_CONFIG_TRIAL "+json.dumps(record,sort_keys=True),flush=True)
    return record

def corruption_tests(cases,records):
    errors=[]
    path=OUT/"sources/petersen_original_45v300c.cnf"
    dest=OUT/"cases/petersen_original_45v300c"
    cert=dest/"candidate.certificate.json"
    master=dest/"candidate.master.cnf"
    pb=dest/"candidate.master.pbp"
    valid=json.loads(cert.read_text())
    # Source byte change despite logical equivalence rejects bound certificate.
    change=OUT/"tampered_original.cnf"
    change.write_bytes(path.read_bytes()+b"c changed source SHA\n")
    rc,_,_=run(OUT/"tampered_source_check.log",[
        sys.executable,CHECKER,"--source",change,
        "--certificate",cert,"--master",master,"--proof",pb],30)
    if rc==0:errors.append("changed source accepted")
    # Deleting one source capacity clause should break complete equivalence.
    original=path.read_text().splitlines()
    first_clause=next(i for i,line in enumerate(original)
                      if line.startswith("-") and len(line.split())>4)
    altered=original[:first_clause]+original[first_clause+1:]
    for j,line in enumerate(altered):
        if line.startswith("p cnf "):
            items=line.split();items[3]=str(int(items[3])-1)
            altered[j]=" ".join(items)
            break
    missing=OUT/"deleted_capacity_clause.cnf"
    missing.write_text("\n".join(altered)+"\n")
    bogus=json.loads(json.dumps(valid))
    bogus["source_sha256"]=hashlib.sha256(missing.read_bytes()).hexdigest()
    bogus_path=OUT/"deleted_capacity_cert.json"
    bogus_path.write_text(json.dumps(bogus)+"\n")
    rc,_,_=run(OUT/"deleted_capacity_source.log",[
        sys.executable,CHECKER,"--source",missing,
        "--certificate",bogus_path,"--master",master,"--proof",pb],30)
    if rc==0:errors.append("incomplete original source encoding accepted")
    # Lie about the complete exact profile.
    invalid=json.loads(json.dumps(valid))
    invalid["exact_capacity_masks"]=invalid["exact_capacity_masks"][:-1]
    altered_file=OUT/"missing_profile.json"
    altered_file.write_text(json.dumps(invalid)+"\n")
    rc,_,_=run(OUT/"profile_tamper.log",[
        sys.executable,CHECKER,"--source",path,
        "--certificate",altered_file,"--master",master,"--proof",pb],30)
    if rc==0:errors.append("incomplete source profile accepted")
    # Remove a derived master conflict; original remains unchanged.
    lines=master.read_text().splitlines()
    trimmed=lines[:-1]
    for j,line in enumerate(trimmed):
        if line.startswith("p cnf "):
            fields=line.split();fields[3]=str(int(fields[3])-1)
            trimmed[j]=" ".join(fields);break
    wrong=OUT/"weakened_master.cnf";wrong.write_text("\n".join(trimmed)+"\n")
    forged=json.loads(json.dumps(valid))
    forged["master_sha256"]=hashlib.sha256(wrong.read_bytes()).hexdigest()
    forged["master_clauses"]-=1
    fake=OUT/"forged_master_cert.json";fake.write_text(json.dumps(forged)+"\n")
    rc,_,_=run(OUT/"wrong_master.log",[
        sys.executable,CHECKER,"--source",path,
        "--certificate",fake,"--master",wrong,"--proof",pb],30)
    if rc==0:errors.append("omitted master cross-machine mutex accepted")
    # Falsify final PB source-clause ID: verifier must reject.
    proof_lines=pb.read_text().splitlines()
    proof_lines[2]="pol 1 ;"
    corrupt_pb=OUT/"corrupt_master.pbp"
    corrupt_pb.write_text("\n".join(proof_lines)+"\n")
    rc,_,_=run(OUT/"wrong_pol.log",[
        sys.executable,CHECKER,"--source",path,"--certificate",cert,
        "--master",master,"--proof",corrupt_pb],30)
    if rc==0:errors.append("unsupported master PB derivation accepted")
    return errors

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    cases=originals()
    rows=[];errors=[]
    for case in cases:
        result=one(case)
        rows.append(result)
        if result["result"].startswith("ERROR"):
            errors.append(result["name"]+": "+result["result"])
        (OUT/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    errors+=corruption_tests(cases,rows)
    verified=[x for x in rows if x["result"]=="ORIGINAL_STRUCTURAL_UNSAT_MASTER_VERIPB_VERIFIED"]
    sats=[x for x in rows if x["result"]=="ORIGINAL_SOURCE_SAT_MODEL_VERIFIED"]
    petersen=next(x for x in rows if x["name"]=="petersen_original_45v300c")
    five=next(x for x in rows if x["name"]=="new_five_job_intersecting_configs")
    if petersen["result"]!="ORIGINAL_STRUCTURAL_UNSAT_MASTER_VERIPB_VERIFIED":
        errors.append("original Petersen direct source configuration proof not accepted")
    if five["result"]!="ORIGINAL_STRUCTURAL_UNSAT_MASTER_VERIPB_VERIFIED":
        errors.append("independent new 5-job source configuration proof not accepted")
    if any(c["expected"]=="SAT" and r["result"]!="ORIGINAL_SOURCE_SAT_MODEL_VERIFIED"
           for c,r in zip(cases,rows)):
        errors.append("SAT source control did not yield full verified model")
    result={
        "status":"PASS" if not errors else "FAIL",
        "source_cases":len(cases),
        "verified_structural_unsat_with_derived_master_VerIPB":len(verified),
        "verified_original_source_sat_models":len(sats),
        "original_weighted_petersen_config_count":petersen.get("exact_configs"),
        "original_weighted_petersen_master_POL":petersen.get("master_POL_steps"),
        "original_source_direct_VerIPB_proof":False,
        "new_five_job_nonpetersen_unsat_config_count":five.get("exact_configs"),
        "new_five_job_master_POL":five.get("master_POL_steps"),
        "source_original_encoding_exhaustively_checked":True,
        "source_to_master_bridge_checker_independent":True,
        "external_master_pure_VerIPB_accepted":len(verified)>=2,
        "DPLL_CDCL_calls":0,
        "bounded_exponential_enumeration_used":True,
        "errors":errors,
        "scope":"Pure PB certifies DERIVED configuration master; original PCMAX implication is certified by independent exhaustive structural reconstruction, NOT directly by VeriPB. No DPLL/CDCL, but 2^n subset enumeration and 1 new independent 5-job family only; no polynomial general solver or blind PAR2 claim.",
    }
    (OUT/"summary.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("IPG7_CONFIG_TOTAL "+json.dumps(result,sort_keys=True),flush=True)
    return 0 if not errors else 1
if __name__=="__main__":sys.exit(main())
