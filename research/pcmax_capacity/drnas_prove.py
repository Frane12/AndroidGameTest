#!/usr/bin/env python3
"""One-command independent DRNAS proof generator (no outside SAT solver).

The DRNAS C++ Hall module and Python mixed-math detector select a source-proof.
The DRNAS standalone proof emitter independently derives a DRUP/LRAT proof.
Only independent proof checkers may upgrade the outcome to UNSAT_STANDARD_VERIFIED.

Usage:
  python3 research/pcmax_capacity/drnas_prove.py formula.cnf \
    --binary build/drnas-pcmax --drat-trim build/drat-trim \
    --lrat-check build/lrat-check --out results/my-formula
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from auto_unsat import run_one
from standalone_lrat import produce
from benchmark_standalone_lrat import independent_checks

def run(src,binary,drat_trim,lrat_check,out,native_ms=1100,standard_s=3.0,
        checker_s=12,max_nodes=5000):
    src=Path(src).resolve()
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False)
    pinned=False
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        pinned=len(os.sched_getaffinity(0))==1
        assert pinned, "single CPU affinity not enforced"
    native_dir=out/"discovery"
    started=time.perf_counter()
    # drat-trim is used as a checker ONLY, not to find a SAT/UNSAT result.
    discovery=run_one(src,Path(binary).resolve(),native_dir,
                      budget_ms=native_ms,drat_checker=Path(drat_trim).resolve())
    source_sha=hashlib.sha256(src.read_bytes()).hexdigest()
    assert discovery["source_sha256"]==source_sha
    result={
        "source_sha256":source_sha,"input":src.name,
        "status":"UNKNOWN","method":discovery["method"],
        "uses_external_sat_solver":False,"source_structural_verified":False,
        "drat_verified":False,"lrat_verified":False,
        "drnas_standalone_generated":False,"proof_steps":0,
        "proof_generation_s":0.0,"original_cnf_check":True,
        "no_sat_backend_invoked":True,"single_logical_cpu":pinned,
    }
    if not discovery["structural_verified"]:
        result["status"]="UNKNOWN"
        result["reason"]="no_source_verified_structural_contradiction"
    else:
        result["status"]="UNSAT_STRUCTURAL_ONLY"
        result["source_structural_verified"]=True
        existing=native_dir/"proof.drat" if discovery["drat_verified"] else None
        created=produce(src,native_dir/"certificate.json",
                        out/"standalone",budget_s=standard_s,
                        nodes=max_nodes,existing_drup=existing)
        result["proof_generation_s"]=created["generator_s"]
        result["drnas_standalone_generated"]=created["standalone_drat"]
        result["proof_steps"]=created["proof_steps"]
        result["reason"]=created.get("reason",created["status"])
        result["proof_mode"]=created.get("mode")
        if created["standalone_drat"] and created["standalone_lrat"]:
            folder=out/"standalone"
            drat=folder/"proof.drat"
            lrat=folder/"proof.lrat"
            good_drat,good_lrat,good_strict,d1,d2,d3=independent_checks(
                src,drat,lrat,Path(drat_trim).resolve(),
                Path(lrat_check).resolve(),checker_s)
            result["drat_verified"]=good_drat
            result["lrat_verified"]=good_drat and good_lrat and good_strict
            if result["lrat_verified"]:
                result["status"]="UNSAT_STANDARD_VERIFIED"
                result["reason"]="three_independent_original_cnf_checks_pass"
                for f in (drat,lrat):
                    shutil.copy2(f,out/f.name)
                result["drat_sha256"]=hashlib.sha256((out/"proof.drat").read_bytes()).hexdigest()
                result["lrat_sha256"]=hashlib.sha256((out/"proof.lrat").read_bytes()).hexdigest()
            else:
                result["reason"]="checker_rejected:"+d1[-160:]+":"+d2[-160:]+":"+d3[-160:]
    result["total_wall_s"]=round(time.perf_counter()-started,6)
    (out/"result.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("cnf",type=Path)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--drat-trim",type=Path,required=True)
    parser.add_argument("--lrat-check",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--native-budget-ms",type=int,default=1100)
    parser.add_argument("--proof-budget-s",type=float,default=3.0)
    parser.add_argument("--checker-s",type=int,default=12)
    parser.add_argument("--max-nodes",type=int,default=5000)
    args=parser.parse_args()
    if not (50<=args.native_budget_ms<=10000):
        parser.error("native budget 50 to 10000 ms")
    if not (0.05<=args.proof_budget_s<=30.0):
        parser.error("standalone proof budget 0.05 to 30 seconds")
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        assert len(os.sched_getaffinity(0))==1
    result=run(args.cnf,args.binary,args.drat_trim,args.lrat_check,args.out,
               args.native_budget_ms,args.proof_budget_s,args.checker_s,args.max_nodes)
    print("DRNAS_PROVE "+json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":main()
