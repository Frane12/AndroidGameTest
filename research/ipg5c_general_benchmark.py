#!/usr/bin/env python3
"""IPG5C generalization pilot: exact-source one-hot recognition, non-CDCL C++.

Distinct source types:
- frozen Petersen original 45v/300c
- 12 *semantically equivalent but independently byte-distinct* Petersen
  CNFs with shuffled clauses, literal order, and randomly permuted variables
- 9 generated truly distinct UNSAT cardinality packing instances
- 9 generated genuinely SAT cardinality packing controls
- 2 unsupported non-one-hot CNF controls
All are precommitted to a manifest BEFORE solver trial; labels withheld
from solver. Same single logical CPU and bounded runtime per source.

Every UNSAT candidate requires externally accepted DRAT-trim and VeriPB3.0.2
on the EXACT source. Source one-hot recognition never implies UNSAT alone.
The extra odd-cycle CP rank-one cuts are separately generated from original
binary SOURCE clauses, never from mathematical side metadata.

These 12 Petersen variants are NOT source-disjoint test data: they are
permutations of the SAME formula, not a new mathematical benchmark.
Neither successful permutations nor easy packing controls establish
generalization to arbitrary PCMAX or competitive PAR2.
"""
import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg5c_general"
NATIVE=ROOT/"build/drnas-ipg5c-onehot"
BASE=ROOT/"build/drnas-ipg5b-jobbranch"
RUP_CHECK=ROOT/"research/ipg5c_source_rup_to_veripb.py"
CUT=ROOT/"research/ipg5c_oddcycle_cuts.py"
DRAT=ROOT/"drat-trim/drat-trim"
VERIPB=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research"))
from ipg1_fixtures import pack,petersen
from ipg4_rup_drat_to_veripb import dimacs

SEED=161126501

def command(argv,seconds=30):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(a) for a in argv],capture_output=True,
                         text=True,timeout=seconds)
        return p.returncode,round(time.perf_counter()-start,6),p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-start,6),"TIMEOUT"

def execute(log,argv,seconds=30):
    rc,dt,out=command(argv,seconds)
    log.write_text(out)
    return rc,dt,out

def permute(raw,seed,name):
    rng=random.Random(seed)
    _,nv,clauses=dimacs_bytes(raw)
    values=list(range(1,nv+1))
    shuffled=values[:]
    rng.shuffle(shuffled)
    lookup=dict(zip(values,shuffled))
    remapped=[[(1 if v>0 else -1)*lookup[abs(v)] for v in c] for c in clauses]
    for c in remapped:rng.shuffle(c)
    rng.shuffle(remapped)
    output=(f"c generated_semantic_permutation={name} seed={seed}\n"
            +f"p cnf {nv} {len(remapped)}\n"
            +"".join(" ".join(map(str,c))+" 0\n" for c in remapped))
    return output.encode()
def dimacs_bytes(raw):
    # Use independent source parser on freshly written bytes.
    nv=nc=None;clauses=[];partial=[]
    for line in raw.decode("ascii").splitlines():
        fields=line.split()
        if not fields or fields[0]=="c":continue
        if fields[0]=="p":
            nv,nc=int(fields[2]),int(fields[3])
            continue
        for field in fields:
            v=int(field)
            if v:partial.append(v)
            else:clauses.append(tuple(partial));partial=[]
    if nv is None or len(clauses)!=nc or partial:raise ValueError("invalid input DIMACS")
    return raw,nv,clauses

def create_inputs():
    rng=random.Random(SEED)
    sources=OUT/"sources";sources.mkdir(parents=True,exist_ok=True)
    base=petersen().encode("ascii")
    entries=[]
    def add(name,raw,answer,family,independent):
        path=sources/(name+".cnf")
        path.write_bytes(raw)
        entries.append({
           "name":name,"sha256":hashlib.sha256(raw).hexdigest(),
           "expected":answer,"family":family,
           "independent_structure":independent,"variables":dimacs_bytes(raw)[1],
        })
    add("petersen_original",base,"UNSAT","PETERSEN_ORIGINAL",False)
    for trial in range(12):
        add(f"petersen_perm_{trial:02d}",
            permute(base,rng.randrange(10000000),f"petersen_{trial}"),
            "UNSAT","PETERSEN_PERMUTATION",False)
    for n in (7,8,9):
        nv,cs=pack(n,2)
        raw=(f"c source family=cardinality_packing_n{n}_T2\n"
             +f"p cnf {nv} {len(cs)}\n"
             +"".join(" ".join(map(str,c))+" 0\n" for c in cs)).encode("ascii")
        for trial in range(3):
            add(f"packing_unsat_{n}_{trial}",
                permute(raw,rng.randrange(10000000),f"pack_{n}_{trial}"),
                "UNSAT","CARDINALITY_PACKING_UNSAT",True)
    for n in (4,5,6):
        nv,cs=pack(n,2)
        raw=(f"c source family=satisfiable_packing_n{n}_T2\n"
             +f"p cnf {nv} {len(cs)}\n"
             +"".join(" ".join(map(str,c))+" 0\n" for c in cs)).encode("ascii")
        for trial in range(3):
            add(f"packing_sat_{n}_{trial}",
                permute(raw,rng.randrange(10000000),f"sat_pack_{n}_{trial}"),
                "SAT","CARDINALITY_PACKING_SAT",True)
    for i in range(2):
        add(f"unsupported_no_onehot_{i}",
            f"p cnf 9 2\n1 2 3 0\n-{i+1} 4 0\n".encode(),
            "UNKNOWN","UNSUPPORTED_CONTROL",True)
    # Manifest created and frozen before ANY C++ solver run.
    (OUT/"precommitted_source_manifest.json").write_text(json.dumps({
        "seed":SEED,"notes":"Petersen permutations are semantically equivalent, not source disjoint.",
        "cases":entries},indent=2,sort_keys=True)+"\n")
    return entries

def proof_case(entry):
    path=OUT/"sources"/(entry["name"]+".cnf")
    dest=OUT/"trials"/entry["name"]
    dest.mkdir(parents=True,exist_ok=True)
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    if sha!=entry["sha256"]:raise ValueError("precommitted source bytes changed")
    rup=dest/"proof.rup"
    rc,native_s,out=execute(dest/"native.log",
        [NATIVE,path,"--output",rup,"--budget-ms","1500"],8)
    row={
        "name":entry["name"],"family":entry["family"],
        "expected":entry["expected"],"source_sha256":sha,
        "native_s":native_s,"native_rc":rc,
        "result":"UNKNOWN","source_verified":False,"veripb_verified":False,
    }
    telemetry={}
    for line in out.splitlines():
        if line.startswith("IPG5C_NATIVE "):
            telemetry=json.loads(line[len("IPG5C_NATIVE "):])
    row["telemetry"]=telemetry
    if rc!=0 or telemetry.get("status") not in (
           "UNKNOWN","RUP_EMITTED_NEEDS_EXTERNAL_CHECK"):
        row["result"]="ERROR_UNSUPPORTED_NATIVE_RESPONSE"
    elif telemetry["status"]=="UNKNOWN":
        if rup.exists():row["result"]="ERROR_UNKNOWN_LEFT_PROOF"
        else:row["reason"]=telemetry.get("reason")
    else:
        if not rup.is_file() or not rup.stat().st_size:
            row["result"]="ERROR_MISSING_PROOF"
        else:
            dr,dt,dlog=execute(dest/"external_drat.log",
                [DRAT,path,rup],35)
            row["external_drat_s"]=dt
            if dr!=0 or "s VERIFIED" not in dlog:
                row["result"]="ERROR_DRAT_REJECTED"
            else:
                pb=dest/"veripb_original.pbp";audit=dest/"rup_replay.json"
                pr,pt,plog=execute(dest/"replay.log",[
                    sys.executable,RUP_CHECK,"--cnf",path,"--rup",rup,
                    "--veripb",pb,"--meta",audit,
                    "--expected-sha256",sha],40)
                row["independent_rup_s"]=pt
                if pr or not pb.exists():
                    row["result"]="ERROR_SOURCE_RUP_REJECTED"
                else:
                    vr,vt,vlog=execute(dest/"external_veripb.log",[
                        VERIPB,"--cnf",path,pb],50)
                    row["veripb_s"]=vt
                    if vr or "s VERIFIED UNSATISFIABLE" not in vlog:
                        row["result"]="ERROR_VERIPB_REJECTED"
                    else:
                        row.update(result="SOURCE_VERIFIED_UNSAT",source_verified=True,
                                   veripb_verified=True,
                                   rup_steps=json.loads(audit.read_text())["rup_steps"],
                                   pbp_bytes=pb.stat().st_size,
                                   rup_bytes=rup.stat().st_size)
                        # Test new SOURCE-derived odd-cycle cuts + proven RUP.
                        cut=dest/"pb_cuts_plus_rup.pbp"
                        cm=dest/"pb_cut_meta.json"
                        cr,ct,clog=execute(dest/"pb_cut_emitter.log",[
                            sys.executable,CUT,"--cnf",path,
                            "--rup",rup,"--veripb",cut,"--meta",cm,
                            "--expected-sha256",sha],40)
                        if cr or not cut.is_file():
                            row["result"]="ERROR_CP_CUT_EMITTER"
                        else:
                            cutmeta=json.loads(cm.read_text())
                            row["source_pb_cuts"]=cutmeta["cross_job_odd_cycle_cuts"]
                            row["source_pb_cycle_lengths"]=cutmeta["cycle_lengths"]
                            vv,vs,vout=execute(dest/"external_pb_cuts_veripb.log",[
                                VERIPB,"--cnf",path,cut],50)
                            row["pb_cuts_verifier_s"]=vs
                            if vv or "s VERIFIED UNSATISFIABLE" not in vout:
                                row["result"]="ERROR_SOURCE_PB_CUTS_REJECTED"
    if entry["expected"]=="SAT" and row["result"]=="SOURCE_VERIFIED_UNSAT":
        row["result"]="ERROR_FALSE_UNSAT_SAT_CONTROL"
    print("IPG5C_TRIAL "+json.dumps({k:v for k,v in row.items() if k!="telemetry"},sort_keys=True),flush=True)
    return row

def additional_adversarial(rows):
    errors=[]
    solved=next((x for x in rows if x["result"]=="SOURCE_VERIFIED_UNSAT" and
                 x["name"]=="petersen_original"),None)
    if not solved:return ["original source not verified — cannot perform corruption tests"]
    path=OUT/"sources/petersen_original.cnf"
    folder=OUT/"trials/petersen_original"
    rup=folder/"proof.rup"
    sha=solved["source_sha256"]
    truncated=OUT/"truncated_original.rup"
    truncated.write_text("\n".join(rup.read_text().splitlines()[:-1])+"\n")
    fake=OUT/"replay_fake.pbp"
    rr,_,_=execute(OUT/"truncated_rup_reject.log",[
        sys.executable,RUP_CHECK,"--cnf",path,"--rup",truncated,
        "--veripb",fake,"--meta",OUT/"bad_meta.json",
        "--expected-sha256",sha],20)
    if rr==0 or fake.exists():errors.append("truncated original RUP accepted")
    tampered=OUT/"comment_changed_source.cnf"
    tampered.write_bytes(path.read_bytes()+b"c byte changed but logically same\n")
    new_sha=hashlib.sha256(tampered.read_bytes()).hexdigest()
    # SHA pin of precommitted ORIGINAL must reject the new bytes.
    rr,_,_=execute(OUT/"wrong_sha_reject.log",[
        sys.executable,RUP_CHECK,"--cnf",tampered,"--rup",rup,
        "--veripb",OUT/"wrong_sha.pbp","--meta",OUT/"bad_sha_meta.json",
        "--expected-sha256",sha],20)
    if rr==0 or (OUT/"wrong_sha.pbp").exists():
        errors.append("changed source SHA was accepted against precommitment")
    # New C++ engine SHOULD accept the logically identical comment-modified
    # CNF because it no longer has a fixed literal source SHA gate.
    proof=OUT/"comment_variant_proof.rup"
    rc,_,out=execute(OUT/"comment_variant_native.log",[
        NATIVE,tampered,"--output",proof,"--budget-ms","1500"],10)
    if rc!=0 or not proof.exists():
        errors.append("new structural recognizer cannot accept comment-only source variant")
    else:
        vc,_,text=execute(OUT/"comment_variant_external_drat.log",
                          [DRAT,tampered,proof],25)
        if vc!=0 or "s VERIFIED" not in text:
            errors.append("comment variant proof rejected by independent DRAT-trim")
    return errors

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    entries=create_inputs()
    results=[];errors=[]
    for entry in entries:
        row=proof_case(entry)
        results.append(row)
        if row["result"].startswith("ERROR"):
            errors.append(f"{entry['name']}: {row['result']}")
        (OUT/"rows.json").write_text(json.dumps(results,sort_keys=True,indent=2)+"\n")
    errors+=additional_adversarial(results)
    unsat=[r for r in results if r["expected"]=="UNSAT"]
    sat=[r for r in results if r["expected"]=="SAT"]
    verified=[r for r in unsat if r["result"]=="SOURCE_VERIFIED_UNSAT"]
    src_new=[r for r in verified if r["family"]=="CARDINALITY_PACKING_UNSAT"]
    perm=[r for r in verified if r["family"]=="PETERSEN_PERMUTATION"]
    summary={
        "status":"PASS" if not errors and len(verified)>=1 and len(src_new)>=1 else "FAIL",
        "inputs":len(entries),
        "petersen_semantic_permutations":12,
        "petersen_permutations_source_verified":len(perm),
        "distinct_packing_unsat_cases":len([r for r in unsat if r["family"]=="CARDINALITY_PACKING_UNSAT"]),
        "distinct_packing_unsat_verified":len(src_new),
        "sat_controls":len(sat),
        "sat_controls_proofs":sum(r["result"]=="SOURCE_VERIFIED_UNSAT" for r in sat),
        "source_verified_total":len(verified),
        "source_pb_rank1_cuts_on_original":next((r.get("source_pb_cuts",0)
                            for r in verified if r["name"]=="petersen_original"),0),
        "verified_original_rup_steps":next((r.get("rup_steps")
                            for r in verified if r["name"]=="petersen_original"),None),
        "errors":errors,
        "scope":"Petersen permutations are mathematically SAME instance (not source-disjoint). Distinct small cardinality packings only show bounded source-family coverage. Solver RUP is bounded exponential branch search, not cut-only or polynomial; no comparison with strongest DRNAS/competition PAR2.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("IPG5C_GENERAL_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if summary["status"]=="PASS" else 1
if __name__=="__main__":sys.exit(main())
