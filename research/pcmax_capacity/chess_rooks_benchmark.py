#!/usr/bin/env python3
"""Serial matched chess-rook benchmark on frozen permuted original generated CNFs.

No claim of external blind competition data or general polynomial SAT.
Native source-clique proof requires external independent VeriPB acceptance.
References are raw statuses only; SAT controls have an independent clause oracle.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import time

from chess_rooks_generate import freeze

def hash_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for piece in iter(lambda:f.read(1048576),b""):h.update(piece)
    return h.hexdigest()

def child(cmd,timeout,log_path):
    started=time.perf_counter()
    with log_path.open("w") as log:
        try:
            p=subprocess.run(list(map(str,cmd)),stdout=log,stderr=subprocess.STDOUT,
                             check=False,timeout=timeout)
            return dict(rc=p.returncode,wall_s=round(time.perf_counter()-started,6),
                        timeout=False)
        except subprocess.TimeoutExpired:
            return dict(rc=None,wall_s=round(time.perf_counter()-started,6),timeout=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,choices=(0,1),required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    p.add_argument("--native",type=pathlib.Path,required=True)
    p.add_argument("--kissat",type=pathlib.Path,required=True)
    p.add_argument("--cadical",type=pathlib.Path,required=True)
    p.add_argument("--veripb",type=pathlib.Path,required=True)
    p.add_argument("--cap",type=int,default=20)
    a=p.parse_args()
    assert 5<=a.cap<=120
    for path in (a.native,a.kissat,a.cadical,a.veripb):
        assert path.is_file(),path
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    a.out.mkdir(parents=True,exist_ok=False)
    frozen=freeze(a.shard,a.out)
    bins=dict(DRNAS_NATIVE=hash_file(a.native),KISSAT=hash_file(a.kissat),
              CADICAL=hash_file(a.cadical),VERIPB=hash_file(a.veripb))
    protocol=dict(frozen=frozen["protocol"],shard=a.shard,cap_s=a.cap,
                  logical_cpu=cpu,one_process_at_a_time=True,
                  binary_sha256=bins,source_frozen_before_all_solver_calls=True,
                  source="synthetic chess rook placements; seeded permutations, not external blind",
                  external_proof_check="VeriPB 3.0.2",references_standard_proofs=False)
    (a.out/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    trials=[]
    with (a.out/"trials.jsonl").open("w") as log:
        for case in frozen["cases"]:
            path=a.out/(case["id"]+".cnf")
            assert hash_file(path)==case["sha256"]
            # Rotate arm order and keep all arms on exactly the same source bytes.
            arms=["DRNAS_NATIVE","KISSAT","CADICAL"]
            rot=int(case["id"][1:])%3
            arms=arms[rot:]+arms[:rot]
            for arm in arms:
                trial_id=case["id"]+"_"+arm.lower()
                runlog=a.out/(trial_id+".log")
                proof=a.out/(case["id"]+".pbp")
                if arm=="DRNAS_NATIVE":
                    assert not proof.exists()
                    cmd=[a.native,path,"--proof",proof,"--time",str(a.cap)]
                elif arm=="KISSAT":
                    cmd=[a.kissat,"--quiet",path]
                else:
                    cmd=[a.cadical,"-q",path]
                stats=child(cmd,a.cap+2,runlog)
                txt=runlog.read_text(errors="replace")
                if stats["timeout"]:
                    status="TIMEOUT"
                elif stats["rc"]==10:
                    status="SAT_REPORTED"
                elif stats["rc"]==20:
                    status="UNSAT_REPORTED_UNVERIFIED"
                elif stats["rc"]==0:
                    status="UNKNOWN"
                else:
                    status="EXECUTION_ERROR"
                row=dict(case=case["id"],expected=case["expected"],rooks=case["rooks"],
                         rows=case["rows"],mode=case["mode"],sha256=case["sha256"],
                         variables=case["variables"],clauses=case["clauses"],
                         arm=arm,**stats,status=status,
                         proof_verifier_s=None,standard_verified=False)
                if arm=="DRNAS_NATIVE":
                    if stats["rc"]==20:
                        if not proof.is_file() or "UNSAT_PBP_EMITTED_UNCHECKED" not in txt:
                            row["status"]="INVALID_NATIVE_UNSAT_NO_PROOF"
                        else:
                            v=child([a.veripb,"--cnf",path,proof],120,
                                    a.out/(trial_id+".veripb.log"))
                            row["proof_verifier_s"]=v["wall_s"]
                            row["proof_bytes"]=proof.stat().st_size
                            row["proof_sha256"]=hash_file(proof)
                            row["verifier_rc"]=v["rc"]
                            row["standard_verified"]=(v["rc"]==0 and not v["timeout"])
                            row["status"]=("UNSAT_VERIPB3_VERIFIED" if row["standard_verified"]
                                           else "UNSAT_VERIPB_REJECTED")
                    elif proof.exists():
                        row["status"]="INVALID_PROOF_ON_UNKNOWN"
                if case["expected"]=="SAT" and stats["rc"]==20:
                    row["status"]="CRITICAL_FALSE_UNSAT_ON_SAT_CONTROL"
                if case["expected"]=="UNSAT" and stats["rc"]==10:
                    row["status"]="CRITICAL_FALSE_SAT_ON_UNSAT_CONTROL"
                trials.append(row)
                log.write(json.dumps(row,sort_keys=True)+"\n")
                log.flush()
                print("ROOK_TRIAL "+json.dumps({k:row.get(k) for k in
                      ("case","rooks","rows","mode","arm","status","wall_s",
                       "proof_verifier_s","standard_verified")},sort_keys=True),flush=True)
    summary=dict(protocol=protocol,total=len(trials),cases=frozen["cases"],trials=trials,
                 native_verified=sum(r["standard_verified"] for r in trials),
                 critical=sum(r["status"].startswith(("INVALID","CRITICAL","EXECUTION_ERROR",
                                                      "UNSAT_VERIPB_REJECTED")) for r in trials))
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("ROOK_SUMMARY "+json.dumps({k:summary[k] for k in
          ("total","native_verified","critical")},sort_keys=True),flush=True)
    if summary["critical"]:
        raise SystemExit("CRITICAL: inspect trial logs")
    wanted=sum(c["expected"]=="UNSAT" for c in frozen["cases"])
    if summary["native_verified"]!=wanted:
        raise SystemExit("Some UNSAT rook cases not standard-verified")

if __name__=="__main__":
    main()
