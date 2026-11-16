#!/usr/bin/env python3
"""Paired source-frozen IPG-BDD3 structural and standard VeriPB proof pilot.

DO NOT infer VeriPB verification from BDD3 JSON checker: the scalar-to-PB
bridge must independently emit a weighted source-clause proof which is then
accepted by externally pinned VeriPB 3.0.2 on the identical original DIMACS.

Failure to find a 3-class nonnegative scalar separating direction is UNKNOWN
for the bridge, not a failure of the original structural proof or a false
claim of arbitrary 3D-to-PB translation.

One CPU, serialized single-process C++ runs and external verification
steps; independent proof validation is timed separately.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg_bdd3_veripb"
NATIVE=ROOT/"build/drnas-pcmax-mg7-ipg1-bdd3"
CAP_NATIVE=ROOT/"build/drnas-pcmax"
BRIDGE=ROOT/"research/ipg_bdd3_veripb_scalar_bridge.py"
SOURCE_CHECK=ROOT/"research/ipg_bdd3_checker.py"
CAP_EMIT=ROOT/"research/pcmax_capacity/emit_veripb_capacity_weighted2.py"
CAP_CHECK=ROOT/"research/pcmax_capacity/check_capacity.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research"))
from ipg_bdd3_native_benchmark import frozen_new_cases
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark import materialize


def execute(cmd,timeout=40):
    start=time.monotonic()
    try:
        p=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,timeout=timeout)
        return p.returncode,round(time.monotonic()-start,6),p.stdout or "",p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124,round(time.monotonic()-start,6),"","TIMEOUT"

def text_log(path,out,err):
    path.write_text(out+"\n"+err)
    return path

def source_cases():
    entries=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
    original_dir=OUT/"original_source"
    original_dir.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i in (0,10,3,1,6):
        e=entries[i]
        path=materialize(e,original_dir,True)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=e["sha256"]:
            raise ValueError("original bytes changed for "+e["name"])
        rows.append((path,e["expected_status"],"ORIGINAL"))
    sealed=frozen_new_cases()
    for p,expected,kind in sealed:
        if any(f"sealed_{num:03d}_" in p.name for num in (12,20,22)):
            rows.append((p,expected,"SEALED_SYNTHETIC"))
    # Inputs are frozen from existing repo fixture generator and are NOT
    # a prospective blind competition benchmark.
    manifest=[{"name":path.name,
               "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
               "catalog_expected":expected,"kind":kind} for path,expected,kind in rows]
    (OUT/"input_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return rows

def one(path,expected,kind):
    folder=OUT/"cases"/path.stem
    folder.mkdir(parents=True,exist_ok=True)
    graph=folder/"source_graph.json"
    cert=folder/"bdd3_structural.json"
    cap_unused=folder/"capacity_skipped.json"
    drat=folder/"fallback.drat"
    argv=[
        NATIVE,path.resolve(),"--mode","core","--time","4",
        "--pcmax-capacity","--pcmax-budget-ms","0",
        "--pcmax-certificate",cap_unused,
        "--ipg-bdd3","--ipg-bdd3-budget-ms","700",
        "--ipg-bdd3-graph",graph,
        "--ipg-bdd3-certificate",cert,
        "--residual-scc","--proof",drat,
    ]
    rc,native_s,out,err=execute(argv,10)
    text_log(folder/"native.log",out,err)
    status={"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "name":path.stem,"expected":expected,"kind":kind,
            "native_rc":rc,"native_s":native_s,
            "bdd3_status":"UNKNOWN","scalar_bridge_status":"NOT_RUN",
            "veripb_status":"NOT_RUN"}
    if rc==20 and "s UNSATISFIABLE" in out and graph.exists() and cert.exists():
        if "c PCMAX_UNIFIED_PROOF_KIND IPG_BDD3_JSON_NEEDS_INDEPENDENT_CHECKER" not in out:
            status["bdd3_status"]="ERROR_WRONG_PROOF_KIND"
            return status
        chk,cs,so,se=execute([sys.executable,SOURCE_CHECK,
                             "--cnf",path,"--graph",graph,"--certificate",cert],50)
        text_log(folder/"bdd3_independent.log",so,se)
        status.update(bdd3_checker_rc=chk,bdd3_checker_s=cs)
        if chk!=0 or "IPG_BDD3_ACCEPT " not in so:
            status["bdd3_status"]="ERROR_UNVERIFIED_BDD3"
            return status
        status["bdd3_status"]="SOURCE_BDD3_VERIFIED"
        cap=folder/"scalar_capacity.json"
        proof=folder/"veripb_scalar.pbp"
        meta=folder/"converter_meta.json"
        args=[sys.executable,BRIDGE,
              "--cnf",path,
              "--graph",graph,
              "--bdd3-certificate",cert,
              "--capacity-certificate",cap,
              "--pb-proof",proof,
              "--meta",meta,
              "--max-alpha","12",
              "--search-seconds","16"]
        rr,rt,ro,re=execute(args,58)
        text_log(folder/"bridge.log",ro,re)
        report=json.loads(meta.read_text()) if meta.exists() else {}
        status.update(scalar_bridge_status=report.get("status","ERROR_NO_REPORT"),
                      scalar_search_s=rt,
                      directions_checked=report.get("directions_checked",0),
                      scalar_objective=report.get("objective"),
                      scalar_delta=report.get("delta"))
        if rr!=0 or report.get("status")=="UNKNOWN_OR_CONVERTER_ERROR":
            status["scalar_bridge_status"]="ERROR_CONVERTER"
            return status
        if report.get("status")=="EMITTED_VERIPB_NEEDS_EXTERNAL_CHECK":
            if not proof.exists() or not cap.exists():
                status["veripb_status"]="ERROR_MISSING_PROOF"
                return status
            ver,vs,vo,ve=execute([VERIPB,"--cnf",path,proof],120)
            text_log(folder/"veripb_external.log",vo,ve)
            status.update(veripb_rc=ver,veripb_s=vs,
                          veripb_bytes=proof.stat().st_size)
            status["veripb_status"]=(
                "EXTERNALLY_VERIPB_UNSAT_VERIFIED" if
                ver==0 and "s VERIFIED UNSATISFIABLE" in vo+"\n"+ve
                else "ERROR_VERIPB_REJECTED")
    elif expected=="SAT" and rc in (0,10):
        # This pilot's purpose is UNSAT PB; never use a returned SAT
        # result without checking every original CNF clause.
        if rc==10:
            import ipg_bdd_checker
            nv,nc,clauses=ipg_bdd_checker.read_source(path.read_bytes())
            model={}
            for line in out.splitlines():
                t=line.split()
                if t and t[0]=="v":
                    for st in t[1:]:
                        v=int(st)
                        if v:model[abs(v)]=(v>0)
            if len(model)!=nv or not all(
                any(model[abs(x)]==(x>0) for x in clause) for clause in clauses):
                status["bdd3_status"]="ERROR_FALSE_SAT_MODEL"
            else:
                status["bdd3_status"]="SAT_MODEL_VERIFIED"
        else:
            status["bdd3_status"]="UNKNOWN"
    else:
        status["bdd3_status"]="UNKNOWN" if rc in (0,124) else "ERROR_SOLVER"
    print("IPG3_PB_CASE "+json.dumps(status,sort_keys=True),flush=True)
    return status

def historical_capacity_reference(path):
    """Already known original capacity proof, strictly separate from BDD3."""
    case=OUT/"historical_capacity_reference"
    case.mkdir(exist_ok=True)
    cap=case/"capacity.json"
    pb=case/"weighted.pbp"
    rc,wall,out,err=execute([
        CAP_NATIVE,path.resolve(),"--mode","core","--time","4",
        "--pcmax-capacity","--pcmax-budget-ms","1600",
        "--pcmax-certificate",cap],9)
    text_log(case/"native.log",out,err)
    result={"capacity_native_rc":rc,"native_wall_s":wall,
            "status":"NO_SOURCE_CAPACITY_CERTIFICATE"}
    if rc==20 and cap.exists():
        cc,cs,co,ce=execute([sys.executable,CAP_CHECK,path,cap],30)
        text_log(case/"structural.log",co,ce)
        if cc!=0 or "UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED" not in co:
            result["status"]="ERROR_BAD_CAPACITY_STRUCTURAL"
            return result
        pbc,pt,po,pe=execute([sys.executable,CAP_EMIT,
                             "--cnf",path,"--certificate",cap,
                             "--output",pb],75)
        text_log(case/"producer.log",po,pe)
        if pbc!=0 or not pb.exists():
            result["status"]="ERROR_CAPACITY_PRODUCER"
            return result
        ver,vt,vo,ve=execute([VERIPB,"--cnf",path,pb],125)
        text_log(case/"veripb.log",vo,ve)
        result.update(veripb_rc=ver,veripb_s=vt,
                      proof_bytes=pb.stat().st_size,
                      status=("HISTORICAL_CAPACITY_VERIPB_VERIFIED"
                              if ver==0 and "s VERIFIED UNSATISFIABLE" in vo+"\n"+ve
                              else "ERROR_HISTORICAL_VERIPB"))
    return result

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    sources=source_cases()
    rows=[];failures=[]
    for path,expected,kind in sources:
        row=one(path,expected,kind)
        rows.append(row)
        if row["bdd3_status"].startswith("ERROR") or (
                row["scalar_bridge_status"].startswith("ERROR")) or (
                row["veripb_status"].startswith("ERROR")):
            failures.append(row["name"]+": error status")
        if expected=="SAT" and row["bdd3_status"]=="SOURCE_BDD3_VERIFIED":
            failures.append(row["name"]+": false UNSAT")
        (OUT/"rows.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
    original_m20=next(path for path,expected,kind in sources
                      if kind=="ORIGINAL" and "m20-4135" in path.name)
    baseline=historical_capacity_reference(original_m20)
    print("IPG3_HISTORICAL_BASE "+json.dumps(baseline,sort_keys=True),flush=True)
    if baseline["status"]!="HISTORICAL_CAPACITY_VERIPB_VERIFIED":
        failures.append("historical original m20 capacity VeriPB baseline lost")
    # Source/graph tampering must always be rejected by the converter.
    structural=next((r for r in rows if r["bdd3_status"]=="SOURCE_BDD3_VERIFIED"),None)
    if structural:
        name=structural["name"]
        folder=OUT/"cases"/name
        orig=next(p for p,_,_ in sources if p.stem==name)
        corrupted=OUT/"corrupted_source.cnf"
        corrupted.write_bytes(orig.read_bytes()+b"c changed after source pinning\n")
        meta=OUT/"corrupted_meta.json"
        rc,_,_,_=execute([
            sys.executable,BRIDGE,"--cnf",corrupted,
            "--graph",folder/"source_graph.json",
            "--bdd3-certificate",folder/"bdd3_structural.json",
            "--capacity-certificate",OUT/"corrupted_cap.json",
            "--pb-proof",OUT/"corrupted.pbp",
            "--meta",meta],35)
        if rc==0 or (OUT/"corrupted.pbp").exists():
            failures.append("source-bound scalar bridge accepted tampered CNF bytes")
    summary={
        "source_cases":len(rows),
        "bdd3_structural_verified":sum(r["bdd3_status"]=="SOURCE_BDD3_VERIFIED" for r in rows),
        "scalar_separators_found":sum(r["scalar_bridge_status"]=="EMITTED_VERIPB_NEEDS_EXTERNAL_CHECK" for r in rows),
        "scalar_external_veripb_verified":sum(r["veripb_status"]=="EXTERNALLY_VERIPB_UNSAT_VERIFIED" for r in rows),
        "nonseparable_under_bound":sum(r["scalar_bridge_status"]=="NO_NONNEGATIVE_SCALAR_SEPARATOR" for r in rows),
        "historical_original_m20_veripb_status":baseline["status"],
        "failures":failures,
        "status":"PASS" if not failures else "FAIL",
        "scope":"Scalar objective from 3-class BDD3 proof is a LIMITED CUT, not arbitrary 3D proof translation; historical reference PB proof is separate.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("IPG3_PB_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if not failures else 1

if __name__=="__main__":
    sys.exit(main())
