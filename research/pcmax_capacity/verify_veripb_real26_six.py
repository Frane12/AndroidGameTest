#!/usr/bin/env python3
"""External VeriPB 3.0 standard verification of six frozen real SAT2026 CNFs.

Not a new blind holdout or a timed PAR2 solver comparison. Each source CNF must
match earlier immutable SHA-256, plus the clique certificate must match source.
Only independently accepted original-CNF VeriPB proofs count as verified.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from emit_veripb_source_clique import emit

IDS = (
 "266e890b706cf336378bf148bbda1aff",
 "4676e00348f494bfbee37c5ec592ec7c",
 "5d8b47745dba3fe50f9c8712be389cd5",
 "6045a464ee2c202630728c86168efae4",
 "68ab843144710875f37f714ef8872630",
 "6eb49b2189f09219995daa0aaf54d72d",
)

def hash_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for data in iter(lambda:f.read(1<<20),b""):
            h.update(data)
    return h.hexdigest()

def run_checker(executable,cnf,pbp,log,max_seconds):
    start=time.perf_counter()
    with log.open("w") as f:
        try:
            r=subprocess.run([str(executable),"--cnf",str(cnf),str(pbp)],
                             stdout=f,stderr=subprocess.STDOUT,
                             timeout=max_seconds,check=False)
            rc=r.returncode
            timeout=False
        except subprocess.TimeoutExpired:
            rc=None
            timeout=True
    return dict(returncode=rc,checker_s=round(time.perf_counter()-start,6),
                timeout=timeout,veripb_accepted=(rc==0 and not timeout))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archived",type=Path,required=True)
    p.add_argument("--certificates",type=Path,required=True)
    p.add_argument("--veripb",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--verifier-cap-s",type=int,default=300)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    reports=list(a.archived.rglob("summary.json"))
    if len(reports)!=4:raise RuntimeError("expected_exactly_four_frozen_archived_shards")
    frozen={}
    for report in reports:
        for record in json.loads(report.read_text())["cases"]:
            if record["md5"] in IDS:
                if record["md5"] in frozen:raise RuntimeError("duplicate_frozen_source")
                frozen[record["md5"]]=(report.parent,record)
    if set(frozen)!=set(IDS):raise RuntimeError("frozen_source_list_missing")
    versions=dict(format="VeriPB 3.0",binary_sha256=hash_file(a.veripb),
                  proof_producer_sha256=hash_file(Path(__file__).with_name("emit_veripb_source_clique.py")),
                  source_checker_sha256=hash_file(Path(__file__).with_name("check_php_partition.py")),
                  use_exact_original_cnf=True,
                  independent_checker=True,
                  source_count=len(IDS))
    (a.out/"protocol.json").write_text(json.dumps(versions,indent=2)+"\n")
    rows=[]
    with (a.out/"trials.jsonl").open("w") as fd:
        for mid in IDS:
            basedir,source=frozen[mid]
            actual=list(basedir.rglob("*"+mid+".cnf"))
            certificates=list(a.certificates.rglob(mid+".certificate.json"))
            row=dict(file_id=mid,source_sha256=source["source_sha256"],
                     catalog_label=source["label"],variables=source["variables"],
                     clauses=source["clauses"],status="NOT_RUN",veripb_accepted=False)
            try:
                if len(actual)!=1 or len(certificates)!=1:
                    raise RuntimeError("source_or_structural_certificate_missing")
                cnf=actual[0];cert=certificates[0]
                if hash_file(cnf)!=source["source_sha256"]:
                    raise RuntimeError("original_CNF_SHA256_mismatch")
                proof=a.out/(mid+".pbp")
                produced=emit(cnf,cert,proof)
                row.update(producer=produced,
                           status="PRODUCED_UNCHECKED")
                log=a.out/(mid+".veripb.log")
                standard=run_checker(a.veripb,cnf,proof,log,a.verifier_cap_s)
                row.update(**standard)
                row["status"]="VERIPB3_ORIGINAL_UNSAT_VERIFIED" if standard["veripb_accepted"] else \
                              "VERIPB_TIMEOUT" if standard["timeout"] else "VERIPB_REJECTED"
                if source["label"]=="sat" and standard["veripb_accepted"]:
                    row["status"]="CRITICAL_FALSE_UNSAT_VS_CATALOG"
                # Full proof retained even if checker rejects, for auditing.
            except Exception as exc:
                row.update(status="PRODUCER_OR_INPUT_ERROR",error=repr(exc))
            rows.append(row)
            fd.write(json.dumps(row,sort_keys=True)+"\n")
            fd.flush()
            print("SOURCE_CLIQUE_VERIPB_CASE "+json.dumps({k:row.get(k) for k in
                  ("file_id","status","variables","clauses","veripb_accepted","checker_s")},
                  sort_keys=True),flush=True)
    summary=dict(total=len(rows),verified=sum(r["status"]=="VERIPB3_ORIGINAL_UNSAT_VERIFIED" for r in rows),
                 failures=sum(r["status"]!="VERIPB3_ORIGINAL_UNSAT_VERIFIED" for r in rows),
                 checked_original_cnf=True,independent_verifier="VeriPB 3.0",
                 rows=rows)
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("SOURCE_CLIQUE_VERIPB_SUMMARY "+json.dumps({k:summary[k] for k in
          ("total","verified","failures")},sort_keys=True),flush=True)
    if summary["verified"]!=len(IDS):
        raise SystemExit("NOT ALL ORIGINALS STANDARD VERIFIED — inspect per-case logs")

if __name__=="__main__":
    main()
