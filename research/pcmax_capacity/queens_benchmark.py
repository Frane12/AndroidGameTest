#!/usr/bin/env python3
"""Reproducible serial 1-logical-CPU, source-paired queen benchmark.

Two variants:
(1) standard N queens, including real diagonal attack rules;
(2) cycle2 restricted positions with complete row/column matching but
    unsatisfiable specifically because diagonal attack clauses were added.
Native 2SAT produces a source DRAT proof; the old PHP route uses VeriPB.
Never treat raw reference UNSAT as independently certified.
"""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from queens_cnf_generate import freeze

def checksum(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):h.update(chunk)
    return h.hexdigest()

def execute(command,seconds,path):
    start=time.perf_counter()
    with path.open("w") as fd:
        try:
            r=subprocess.run(list(map(str,command)),stdout=fd,
                             stderr=subprocess.STDOUT,timeout=seconds)
            return dict(rc=r.returncode,wall_s=round(time.perf_counter()-start,6),
                        timeout=False)
        except subprocess.TimeoutExpired:
            return dict(rc=None,wall_s=round(time.perf_counter()-start,6),
                        timeout=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,choices=[0,1],required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--two-sat",type=Path,required=True)
    p.add_argument("--php",type=Path,required=True)
    p.add_argument("--kissat",type=Path,required=True)
    p.add_argument("--cadical",type=Path,required=True)
    p.add_argument("--drat-trim",type=Path,required=True)
    p.add_argument("--veripb",type=Path,required=True)
    p.add_argument("--cap",type=int,default=12)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError("refusing_existing_result_folder")
    assert 5<=a.cap<=60
    for path in (a.two_sat,a.php,a.kissat,a.cadical,a.drat_trim,a.veripb):
        assert path.is_file(),path
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    a.out.mkdir(parents=True)
    source=freeze(a.shard,a.out)
    paths={"DRNAS_2SAT":a.two_sat,"DRNAS_PHP":a.php,
           "KISSAT":a.kissat,"CADICAL":a.cadical}
    protocol=dict(name="DRNAS_NQUEENS_DIA2SAT_SOURCE_FROZEN_V1",logical_cpu=cpu,
                  cap_s=a.cap,source_class="synthetic_permuted_N_queens_and_cycle2",
                  arms=list(paths),binaries={name:checksum(path) for name,path in
                                              {**paths,"DRAT_TRIM":a.drat_trim,
                                               "VERIPB":a.veripb}.items()},
                  frozen_before_solver_runs=True,
                  unsat_native_requires_external_checker=True,
                  reference_unsat_and_sat_raw_not_independently_checked=True)
    (a.out/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    rows=[]
    with (a.out/"trials.jsonl").open("w") as fd:
        for case in source["cases"]:
            cnf=a.out/(case["id"]+".cnf")
            assert checksum(cnf)==case["sha256"]
            arms=list(paths)
            rotation=int(case["id"][1:])%len(arms)
            arms=arms[rotation:]+arms[:rotation]
            for arm in arms:
                name=case["id"]+"-"+arm.lower()
                logfile=a.out/(name+".log")
                proof=a.out/(name+(".drat" if arm=="DRNAS_2SAT" else ".pbp"))
                if arm=="DRNAS_2SAT":
                    command=[a.two_sat,cnf,"--proof",proof,"--time",str(a.cap)]
                elif arm=="DRNAS_PHP":
                    command=[a.php,cnf,"--proof",proof,"--time",str(a.cap)]
                elif arm=="KISSAT":
                    command=[a.kissat,"--quiet",cnf]
                else:
                    command=[a.cadical,"-q",cnf]
                measured=execute(command,a.cap+2,logfile)
                std_status=("TIMEOUT" if measured["timeout"] else
                            "SAT_REPORTED" if measured["rc"]==10 else
                            "UNSAT_REPORTED_UNVERIFIED" if measured["rc"]==20 else
                            "UNKNOWN" if measured["rc"]==0 else "EXECUTION_ERROR")
                row=dict(case_id=case["id"],source_sha256=case["sha256"],
                         source_kind=case["kind"],n=case["n"],
                         expected=case["expected"],diagonals=case.get("diagonals",True),
                         variables=case["variables"],clauses=case["clauses"],
                         arm=arm,**measured,status=std_status,
                         external_checker_s=None,verified=False)
                if arm.startswith("DRNAS_"):
                    if measured["rc"]==20:
                        if not proof.is_file():
                            row["status"]="INVALID_MISSING_PROOF"
                        else:
                            check_log=a.out/(name+".external.log")
                            if arm=="DRNAS_2SAT":
                                checker=[a.drat_trim,cnf,proof]
                            else:
                                checker=[a.veripb,"--cnf",cnf,proof]
                            verification=execute(checker,100,check_log)
                            validator_output=check_log.read_text(errors="replace")
                            accepted=(verification["rc"]==0 and not verification["timeout"] and
                                      (arm=="DRNAS_PHP" or "s VERIFIED" in validator_output))
                            row.update(verified=accepted,
                                       checker_rc=verification["rc"],
                                       external_checker_s=verification["wall_s"],
                                       proof_bytes=proof.stat().st_size,
                                       proof_sha256=checksum(proof),
                                       status=("UNSAT_"+("DRAT" if arm=="DRNAS_2SAT" else "VERIPB")+"_VERIFIED"
                                               if accepted else "INVALID_EXTERNAL_PROOF_REJECTED"))
                    elif proof.exists():
                        row["status"]="INVALID_PROOF_WITHOUT_UNSAT"
                if case["expected"]=="SAT" and measured["rc"]==20:
                    row["status"]="CRITICAL_FALSE_UNSAT_SAT_CONTROL"
                if case["expected"]=="UNSAT" and measured["rc"]==10:
                    row["status"]="CRITICAL_FALSE_SAT_UNSAT_CONTROL"
                rows.append(row)
                fd.write(json.dumps(row,sort_keys=True)+"\n")
                fd.flush()
                print("QUEEN_TRIAL "+json.dumps({k:row.get(k) for k in
                      ("case_id","arm","n","source_kind","status","wall_s",
                       "external_checker_s","verified")},sort_keys=True),flush=True)
    critical=[r for r in rows if r["status"].startswith(("CRITICAL","INVALID","EXECUTION_ERROR"))]
    report=dict(protocol=protocol,cases=source["cases"],rows=rows,trials=len(rows),
                independent_2sat_drat=sum(r["arm"]=="DRNAS_2SAT" and r["verified"] for r in rows),
                independent_php_veripb=sum(r["arm"]=="DRNAS_PHP" and r["verified"] for r in rows),
                critical=len(critical))
    (a.out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("QUEEN_SUMMARY "+json.dumps({k:report[k] for k in
          ("trials","independent_2sat_drat","independent_php_veripb","critical")},
          sort_keys=True),flush=True)
    if critical:raise SystemExit("Critical solver error or forged proof")
    # Primary expected behavior: three cycle2 diagonal-only UNSAT proofs from
    # the new generic 2SAT module; they MUST pass external DRAT verification.
    want=sum(c["kind"]=="cycle2" and c["expected"]=="UNSAT" for c in source["cases"])
    found=sum(r["arm"]=="DRNAS_2SAT" and r["verified"] and
              r["source_kind"]=="cycle2" for r in rows)
    if found!=want:raise SystemExit("Missing independently checked queen diagonal 2SAT proof")

if __name__=="__main__":main()
