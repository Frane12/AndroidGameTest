#!/usr/bin/env python3
"""SHA-frozen retrospective PCMAX proof check (not blind, not solver PAR2)."""
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark import materialize
from check_capacity import check
OUT=ROOT/"results/weighted2"
BIN=ROOT/"build/drnas-pcmax"
GEN=ROOT/"research/pcmax_capacity/emit_veripb_capacity_weighted2.py"
VERI=ROOT/"veripb-tool/bin/veripb"
manifest=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]

def max_filesize():
    limit=70*1024*1024
    resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))

def run(argv,timeout,limit=False):
    started=time.perf_counter()
    try:
        result=subprocess.run([str(x) for x in argv],capture_output=True,text=True,timeout=timeout,
               preexec_fn=max_filesize if limit else None)
        return result.returncode,round(time.perf_counter()-started,5),result.stdout+"\n"+result.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-started,5),"TIMEOUT"

def main():
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"originals").mkdir(exist_ok=True)
    indices=list(range(20))
    result=[]
    for i in indices:
        e=manifest[i]
        case=OUT/f"{i:02d}"
        case.mkdir(exist_ok=True)
        record={"index":i,"name":e["name"],"sha256":e["sha256"],
                "status":"UNKNOWN","accepted":False,"label":e["expected_status"]}
        try:
            cnf=materialize(e,OUT/"originals",True)
            digest=hashlib.sha256(cnf.read_bytes()).hexdigest()
            if digest!=e["sha256"]:raise RuntimeError("original source hash mismatch")
            cert=case/"capacity.json"
            rc,sec,msg=run([BIN,cnf.resolve(),"--mode","core","--time","7",
                "--pcmax-only","--pcmax-capacity","--pcmax-budget-ms","5000",
                "--pcmax-certificate",cert.resolve()],12)
            (case/"native.log").write_text(msg[-12000:])
            record.update(native_rc=rc,native_s=sec)
            if rc!=20 or not cert.exists():raise RuntimeError("native did not provide certificate")
            evidence=check(cnf.read_bytes(),json.loads(cert.read_text()))
            record.update(demand=evidence["required"],capacity=evidence["capacity_sum"])
            if evidence["status"]!="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
                raise RuntimeError("structural check rejected")
            proof=case/"weighted.pbp"
            rc,sec,msg=run([sys.executable,GEN,"--cnf",cnf,"--certificate",cert,
                             "--output",proof],45,True)
            (case/"emitter.log").write_text(msg[-10000:])
            record.update(generator_rc=rc,generator_s=sec)
            if rc!=0 or not proof.is_file() or not proof.stat().st_size:
                record["status"]="PROOF_NOT_EMITTED"
            else:
                record["proof_bytes"]=proof.stat().st_size
                rc,sec,msg=run([VERI,"--cnf",cnf,proof],120)
                (case/"veripb.log").write_text(msg[-12000:])
                record.update(checker_rc=rc,checker_s=sec)
                if rc==0 and "s VERIFIED UNSATISFIABLE" in msg:
                    record.update(status="VERIFIED_UNSAT",accepted=True)
                else:
                    record["status"]="REJECTED_OR_TIMED_OUT"
                    # Never treat an unaccepted proof as UNSAT.
            if record["accepted"] and e["expected_status"]=="SAT":
                record["status"]="FATAL_SAT_CONTROL_CONFLICT"
                record["accepted"]=False
        except Exception as ex:
            record["status"]="AUDIT_ERROR"
            record["error"]=str(ex)[:300]
        print("WEIGHTED2_TRIAL "+json.dumps(record,sort_keys=True),flush=True)
        result.append(record)
        (OUT/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("WEIGHTED2_TOTAL "+json.dumps({"selected":len(result),
         "verified":sum(r["accepted"] for r in result),
         "rejected":sum(r["status"]=="REJECTED_OR_TIMED_OUT" for r in result),
         "not_emitted":sum(r["status"]=="PROOF_NOT_EMITTED" for r in result),
         "errors":sum(r["status"]=="AUDIT_ERROR" for r in result)},sort_keys=True),flush=True)
    return 1 if any(r["status"] in ("AUDIT_ERROR","REJECTED_OR_TIMED_OUT","FATAL_SAT_CONTROL_CONFLICT") for r in result) else 0

if __name__=="__main__":
    sys.exit(main())
