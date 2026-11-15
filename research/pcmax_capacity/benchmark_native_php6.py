#!/usr/bin/env python3
"""Original REAL26 six-case one-CPU native C++ / external VeriPB 3.0 audit.

Python only orchestrates benchmarks. The C++ solver binary neither runs nor
imports Python and writes its own VerIPB proof in the same invocation.
"""
import argparse
import hashlib
import json
import os
import pathlib
import resource
import subprocess
import time

IDS=[
 "266e890b706cf336378bf148bbda1aff",
 "4676e00348f494bfbee37c5ec592ec7c",
 "5d8b47745dba3fe50f9c8712be389cd5",
 "6045a464ee2c202630728c86168efae4",
 "68ab843144710875f37f714ef8872630",
 "6eb49b2189f09219995daa0aaf54d72d",
]
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for buf in iter(lambda:f.read(1048576),b""):h.update(buf)
    return h.hexdigest()

def run(args,out,seconds):
    started=time.perf_counter()
    with out.open("w") as f:
        try:
            r=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,timeout=seconds,check=False)
            return dict(rc=r.returncode,elapsed_s=round(time.perf_counter()-started,6),timeout=False)
        except subprocess.TimeoutExpired:
            return dict(rc=None,elapsed_s=round(time.perf_counter()-started,6),timeout=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sources",type=pathlib.Path,required=True)
    p.add_argument("--native",type=pathlib.Path,required=True)
    p.add_argument("--veripb",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError("refuse_reuse_existing_output_directory")
    a.out.mkdir(parents=True)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    reports=list(a.sources.rglob("summary.json"))
    assert len(reports)==4,reports
    frozen={}
    for report in reports:
        data=json.loads(report.read_text())
        for item in data["cases"]:
            if item["md5"] in IDS:
                assert item["md5"] not in frozen
                frozen[item["md5"]]=(report.parent,item)
    assert set(frozen)==set(IDS)
    binaries=dict(native=sha(a.native),veripb=sha(a.veripb))
    proto=dict(protocol="REAL2026_SIX_SOURCE_ORIGINAL_NATIVE_CPP_VERIPB3",
               original_catalog_ids=IDS,binaries_sha256=binaries,one_logical_cpu=cpu,
               source_bytes_untouched=True,generated_proof_drat_lrat=False,
               standard_proof_format="VeriPB 3.0.2",native_time_cap_s=10,
               checker_time_cap_s=120,not_blind_retrospective=True)
    (a.out/"protocol.json").write_text(json.dumps(proto,indent=2)+"\n")
    rows=[]
    with (a.out/"trials.jsonl").open("w") as fd:
        for mid in IDS:
            basedir,item=frozen[mid]
            matches=list(basedir.rglob("*"+mid+".cnf"))
            assert len(matches)==1,(mid,matches)
            cnf=matches[0]
            assert item["label"]=="unsat"
            assert sha(cnf)==item["source_sha256"]
            proof=a.out/(mid+".pbp")
            native_log=a.out/(mid+".native.log")
            native=run([str(a.native),str(cnf),"--proof",str(proof),"--time","10"],
                       native_log,12)
            row=dict(original_id=mid,original_sha256=item["source_sha256"],
                     variables=item["variables"],clauses=item["clauses"],
                     native=native,status="NATIVE_UNKNOWN_OR_ERROR",standard_verified=False)
            if native["rc"]==20 and proof.exists():
                output=native_log.read_text()
                assert "s UNSATISFIABLE" in output
                assert "UNSAT_PBP_EMITTED_UNCHECKED" in output
                checker_log=a.out/(mid+".veripb.log")
                checked=run([str(a.veripb),"--cnf",str(cnf),str(proof)],checker_log,120)
                row.update(checker=checked,proof_bytes=proof.stat().st_size,
                           proof_sha256=sha(proof))
                if checked["rc"]==0:
                    row.update(status="VERIPB3_ORIGINAL_UNSAT_VERIFIED",standard_verified=True)
                else:
                    row["status"]="VERIPB_REJECTED_OR_TIMEOUT"
            rows.append(row)
            fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()
            print("NATIVEPHP6_TRIAL "+json.dumps({k:row.get(k) for k in
                  ("original_id","variables","clauses","status","native","checker","proof_bytes")},
                  sort_keys=True),flush=True)
    summary=dict(protocol=proto["protocol"],total=len(rows),
                 standard_verified=sum(x["standard_verified"] for x in rows),
                 failures=sum(not x["standard_verified"] for x in rows),rows=rows)
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("NATIVEPHP6_SUMMARY "+json.dumps({k:summary[k] for k in
          ("total","standard_verified","failures")},sort_keys=True),flush=True)
    if summary["standard_verified"]!=6:raise SystemExit("NATIVE_VERIPB_6_NOT_ALL_VERIFIED")

if __name__=="__main__":
    main()
