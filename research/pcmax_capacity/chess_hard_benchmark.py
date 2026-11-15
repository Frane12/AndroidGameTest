#!/usr/bin/env python3
"""Fair, source-paired 1-core comparison on hard chess SAT families.

All input SHA256 hashes frozen before solver call. Generic DRNAS X5, native
source-clique PHP and 2SAT specialists, Kissat and CaDiCaL each run serially
on exactly the same CNF. Native SAT claims are checked against the original
CNF when a complete v-model is present. UNSAT accepted as standard-verified
only if the original CNF plus DRAT is accepted by external drat-trim.
Unknown output and all timeouts are retained. This is synthetic, not blind.
"""
import argparse
import hashlib
import json
import os
import pathlib
import resource
import subprocess
import time
from chess_hard_generator import freeze

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as fd:
        for chunk in iter(lambda:fd.read(1048576),b""):
            h.update(chunk)
    return h.hexdigest()

def execute(command,log,seconds):
    started=time.perf_counter()
    def restrict():
        resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
    with log.open("w") as fd:
        try:
            r=subprocess.run([str(x) for x in command],
                             stdout=fd,stderr=subprocess.STDOUT,
                             timeout=seconds,preexec_fn=restrict,check=False)
            return dict(returncode=r.returncode,elapsed_s=round(time.perf_counter()-started,6),
                        timeout=False)
        except subprocess.TimeoutExpired:
            return dict(returncode=None,elapsed_s=round(time.perf_counter()-started,6),
                        timeout=True)

def verified_model(path, output):
    variables=None
    for line in path.open("r"):
        if line.startswith("p cnf "):
            variables=int(line.split()[2]);break
    if variables is None:return False
    literals=[]
    for line in output.splitlines():
        if line.startswith("v "):
            try:literals.extend(int(x) for x in line.split()[1:])
            except ValueError:return False
    # A solver may provide multiple v-lines, terminated by 0.
    selected={}
    for literal in literals:
        if literal==0:continue
        if abs(literal)>variables:return False
        old=selected.get(abs(literal))
        if old is not None and old!=(literal>0):return False
        selected[abs(literal)]=(literal>0)
    if len(selected)!=variables:return False
    clause=[]
    for line in path.open("r"):
        if line.startswith("p ") or line.startswith("c") or not line.strip():continue
        for token in line.split():
            l=int(token)
            if l==0:
                if not any(selected[abs(x)]==(x>0) for x in clause):return False
                clause=[]
            else:clause.append(l)
    return not clause

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,choices=range(4),required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    p.add_argument("--x5",type=pathlib.Path,required=True)
    p.add_argument("--php",type=pathlib.Path,required=True)
    p.add_argument("--two-sat",type=pathlib.Path,required=True)
    p.add_argument("--kissat",type=pathlib.Path,required=True)
    p.add_argument("--cadical",type=pathlib.Path,required=True)
    p.add_argument("--drat-trim",type=pathlib.Path,required=True)
    p.add_argument("--cap",type=float,default=15.0)
    a=p.parse_args()
    if a.out.exists():raise RuntimeError("Refuse existing output folder")
    assert 2<=a.cap<=90
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    for path in (a.x5,a.php,a.two_sat,a.kissat,a.cadical,a.drat_trim):
        assert path.is_file(),path
    frozen=freeze(a.shard,a.out)
    binaries=dict(DRNAS_X5=a.x5,DRNAS_PHP=a.php,DRNAS_2SAT=a.two_sat,
                  KISSAT=a.kissat,CADICAL=a.cadical)
    protocol=dict(name="CHESS_HARD_TOROID_COMPLETION_FROZEN_V1",
                  one_logical_cpu=cpu,cap_s=a.cap,
                  source_count=len(frozen["cases"]),
                  sha256={name:digest(path) for name,path in
                          {**binaries,"DRAT_TRIM":a.drat_trim}.items()},
                  not_blind=True,source_only_no_label_to_solver=True,
                  no_proof_no_verified_unsat=True,
                  primary_timing="no-proof for general CDCL; separate UNSAT proof replay")
    (a.out/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    rows=[]
    with (a.out/"trials.jsonl").open("w") as trial_fd:
        for case in frozen["cases"]:
            cnf=a.out/(case["id"]+".cnf")
            assert digest(cnf)==case["sha256"]
            names=list(binaries)
            shift=int(hashlib.sha256(case["id"].encode()).hexdigest()[:2],16)%len(names)
            names=names[shift:]+names[:shift]
            for arm in names:
                tag=case["id"]+"_"+arm.lower()
                proof=a.out/(tag+(".pbp" if arm=="DRNAS_PHP" else ".drat"))
                log=a.out/(tag+".log")
                if arm=="DRNAS_X5":
                    command=[a.x5,cnf,"--mode","core","--time",str(a.cap)]
                elif arm=="DRNAS_PHP":
                    command=[a.php,cnf,"--proof",proof,"--time",str(a.cap)]
                elif arm=="DRNAS_2SAT":
                    command=[a.two_sat,cnf,"--proof",proof,"--time",str(a.cap)]
                elif arm=="KISSAT":
                    command=[a.kissat,cnf]
                else:
                    command=[a.cadical,"-q",cnf]
                data=execute(command,log,a.cap+2)
                outcome=("TIMEOUT" if data["timeout"] else
                         "SAT_REPORTED" if data["returncode"]==10 else
                         "UNSAT_REPORTED_UNVERIFIED" if data["returncode"]==20 else
                         "UNKNOWN" if data["returncode"]==0 else "EXECUTION_ERROR")
                row=dict(case=case["id"],family=case["family"],n=case["n"],
                         seed=case["seed"],expected=case["label"],
                         vars=case["variables"],clauses=case["clauses"],
                         source_sha256=case["sha256"],arm=arm,
                         status=outcome,**data,
                         sat_model_verified=False,unsat_standard_verified=False,
                         checker_s=None,proof_bytes=None,proof_replay_s=None,
                         execution_detail=log.read_text(errors="replace")[-500:] if outcome=="EXECUTION_ERROR" else None)
                if data["returncode"]==10:
                    row["sat_model_verified"]=verified_model(cnf,log.read_text(errors="replace"))
                    if row["sat_model_verified"]:row["status"]="SAT_MODEL_VERIFIED"
                    if case["label"]=="THEOREM_UNSAT":
                        row["status"]="CRITICAL_FALSE_SAT_VS_MATH"
                if data["returncode"]==20:
                    # Core timing above is always with identical no-proof options.
                    # Standard certification below is a SEPARATE proof-mode replay
                    # with its own time/resource costs, never conflated with speed.
                    if arm in ("DRNAS_X5","KISSAT","CADICAL"):
                        if arm=="DRNAS_X5":
                            cmd2=[a.x5,cnf,"--mode","core","--time",str(a.cap),"--proof",proof]
                        elif arm=="KISSAT":
                            cmd2=[a.kissat,cnf,proof]
                        else:
                            cmd2=[a.cadical,"-q","--no-binary",cnf,proof]
                        replay=execute(cmd2,a.out/(tag+".proofreplay.log"),a.cap+2)
                        row.update(proof_replay_s=replay["elapsed_s"],
                                   proof_replay_rc=replay["returncode"])
                    else:
                        replay=data
                    if replay["returncode"]==20 and proof.is_file() and proof.stat().st_size>0 and arm!="DRNAS_PHP":
                        checker_log=a.out/(tag+".dratcheck.log")
                        checked=execute([a.drat_trim,cnf,proof],checker_log,65)
                        verified=(checked["returncode"]==0 and not checked["timeout"]
                                  and "s VERIFIED" in checker_log.read_text(errors="replace"))
                        row.update(checker_s=checked["elapsed_s"],
                                   checker_rc=checked["returncode"],
                                   unsat_standard_verified=verified,
                                   proof_bytes=proof.stat().st_size,
                                   status="UNSAT_DRAT_VERIFIED" if verified else
                                          "UNSAT_PROOF_NOT_VERIFIED")
                    else:row["status"]="UNSAT_REPORTED_UNVERIFIED"
                    if case["label"]=="WITNESS_SAT":
                        row["status"]="CRITICAL_FALSE_UNSAT_VS_WITNESS"
                rows.append(row)
                trial_fd.write(json.dumps(row,sort_keys=True)+"\n")
                trial_fd.flush()
                print("CHESS_HARD_TRIAL "+json.dumps({k:row.get(k) for k in
                      ("case","n","arm","status","elapsed_s","checker_s","vars","clauses")},
                      sort_keys=True),flush=True)
    summary=dict(protocol=protocol,cases=frozen["cases"],rows=rows,
                 attempted=len(rows),
                 verified_unsat=sum(x["unsat_standard_verified"] for x in rows),
                 verified_sat=sum(x["sat_model_verified"] for x in rows),
                 invalid=sum(x["status"].startswith("CRITICAL") for x in rows))
    (a.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("CHESS_HARD_SUMMARY "+json.dumps({k:summary[k] for k in
          ("attempted","verified_unsat","verified_sat","invalid")},
          sort_keys=True),flush=True)
    if summary["invalid"]:raise SystemExit("CRITICAL false SAT/UNSAT found")

if __name__=="__main__":main()
