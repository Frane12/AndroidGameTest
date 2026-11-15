#!/usr/bin/env python3
"""MG6 proof-first retrospective check on all 20 source-frozen PCMAX originals.

No labels are passed to MG6; source hashes pinned in sources20.json.
Do not classify PROOF_EMITTED_UNCHECKED as UNSAT. VeriPB is authoritative.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark import materialize

MANIFEST=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
OUT=ROOT/"results/mg6_real20"
CNF=OUT/"originals"
VERIFIER=(ROOT/"veripb-tool/bin/veripb").resolve()
GENERATOR=ROOT/"research/mg6_general_capacity.py"

def execute(args,timeout):
    try:
        t=time.monotonic()
        p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=timeout)
        return p.returncode,round(time.monotonic()-t,5),p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.monotonic()-t,5),"TIMEOUT"

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    CNF.mkdir(exist_ok=True)
    rows=[];bad=[]
    for index,entry in enumerate(MANIFEST):
        row={"index":index,"name":entry["name"],"catalog_label":entry["expected_status"],
             "source_sha256":entry["sha256"],"status":"UNKNOWN","accepted":False}
        try:
            path=materialize(entry,CNF,True)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:
                raise ValueError("source identity mismatch")
            stem=f"{index:02d}"
            proof=OUT/(stem+".pbp")
            report=OUT/(stem+".json")
            rc,elapsed,stdout=execute([sys.executable,GENERATOR,
                    "--cnf",path,"--proof",proof,"--report",report],30)
            row.update(producer_rc=rc,producer_s=elapsed)
            if rc!=0:raise ValueError("producer error "+stdout[-300:])
            data=json.loads(report.read_text())
            row.update(groups=data.get("groups"),cliques=data.get("cliques"),steps=data.get("proof_steps"))
            if data["status"]=="PROOF_EMITTED_UNCHECKED":
                rc,elapsed,stdout=execute([VERIFIER,"--cnf",path,proof],60)
                row.update(verifier_rc=rc,verifier_s=elapsed)
                (OUT/(stem+".veripb.log")).write_text(stdout[-12000:])
                if rc==0 and "s VERIFIED UNSATISFIABLE" in stdout:
                    row.update(status="VERIPB_UNSAT_VERIFIED",accepted=True)
                else:
                    row["status"]="PROOF_REJECTED"
                    bad.append(entry["name"]+": verifier rejected")
                if row["accepted"] and entry["expected_status"]=="SAT":
                    row["status"]="SAT_CONTROL_CONFLICT"
                    bad.append(entry["name"]+": SAT-labeled original accepted as UNSAT")
            elif data["status"]=="UNKNOWN":
                row["status"]="UNKNOWN"
                if proof.exists():raise ValueError("UNKNOWN emitted proof")
            else:raise ValueError("unexpected result")
        except Exception as exc:
            row["status"]="ERROR"
            row["error"]=str(exc)[:400]
            bad.append(entry["name"]+": "+str(exc)[:100])
        print("MG6_REAL20_CASE "+json.dumps(row,sort_keys=True),flush=True)
        rows.append(row)
        (OUT/"summary.json").write_text(json.dumps(rows,indent=2)+"\n")
    total={"completed":len(rows),"verified":sum(r["accepted"] for r in rows),
           "unknown":sum(r["status"]=="UNKNOWN" for r in rows),"failures":bad}
    print("MG6_REAL20_TOTAL "+json.dumps(total,sort_keys=True),flush=True)
    (OUT/"totals.json").write_text(json.dumps(total,indent=2)+"\n")
    return 1 if bad else 0

if __name__=="__main__":
    sys.exit(main())
