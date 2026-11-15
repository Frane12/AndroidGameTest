#!/usr/bin/env python3
"""60-second targeted replay of three unresolved FULL blocked N-Queens originals.

No regeneration or refreeze: original bytes come exclusively from 24-case
previous source archive, matched bytewise to frozen manifest and SHA-256.
This is a retrospective, pre-specified focus, NOT a fresh blind test.
Serial one-logical-CPU, proof logging disabled during solver timing.
Any UNSAT is replayed with DRAT, then independently checked on original source.
Any SAT model is checked clause by clause against the source.
"""
import argparse
import json
import os
import pathlib
from blocked_nqueens_phase_benchmark import run,sha256,model_ok

SELECTED={"r40k06","r56k06","r56k09"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--originals",type=pathlib.Path,required=True)
    p.add_argument("--case",type=str,required=True,choices=sorted(SELECTED))
    p.add_argument("--x5",type=pathlib.Path,required=True)
    p.add_argument("--kissat",type=pathlib.Path,required=True)
    p.add_argument("--cadical",type=pathlib.Path,required=True)
    p.add_argument("--drat-trim",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,required=True)
    p.add_argument("--cap",type=int,default=60)
    a=p.parse_args()
    assert 20<=a.cap<=90
    assert not a.out.exists()
    a.out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    frozen_files=list(a.originals.rglob("frozen.json"))
    assert len(frozen_files)==1,frozen_files
    manifest=json.loads(frozen_files[0].read_text())
    matches=[c for c in manifest["cases"] if c["id"]==a.case]
    assert len(matches)==1
    source=matches[0]
    assert source["label"]=="UNKNOWN" and source["family"]=="random-blocked"
    cnfs=list(a.originals.rglob(a.case+".cnf"))
    assert len(cnfs)==1
    cnf=cnfs[0]
    assert sha256(cnf)==source["sha256"],"frozen CNF byte mismatch"
    paths={"DRNAS_X5":a.x5,"KISSAT":a.kissat,"CADICAL":a.cadical}
    for path in list(paths.values())+[a.drat_trim]:assert path.is_file()
    protocol=dict(source_id=a.case,source_sha256=source["sha256"],
                  frozen_source_run=43746699667,previous_cap_s=12,new_cap_s=a.cap,
                  cpu=cpu,arms=list(paths),
                  binary_sha256={k:sha256(v) for k,v in paths.items()},
                  original_vars=source["variables"],original_clauses=source["clauses"],
                  replay_only=True,not_fresh_blind=True)
    (a.out/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    rows=[]
    for arm,binary in paths.items():
        assert sha256(cnf)==source["sha256"],"source changed before run"
        tag=a.case+"-"+arm.lower()
        primary_log=a.out/(tag+".primary.log")
        if arm=="DRNAS_X5":
            args=[binary,cnf,"--mode","core","--time",str(a.cap)]
        elif arm=="KISSAT":
            args=[binary,cnf]
        else:
            args=[binary,"-q",cnf]
        measured=run(args,primary_log,a.cap+2,256)
        status=("TIMEOUT" if measured["timeout"] else
                "SAT_UNVERIFIED" if measured["rc"]==10 else
                "UNSAT_UNVERIFIED" if measured["rc"]==20 else
                "UNKNOWN" if measured["rc"]==0 else "EXECUTION_ERROR")
        row=dict(arm=arm,**measured,status=status,
                 original_id=a.case,source_sha256=source["sha256"],
                 standard_verified=False,sat_model_verified=False,
                 proof_replay_s=None,proof_check_s=None)
        if measured["rc"]==10:
            ok=model_ok(cnf,primary_log.read_text(errors="replace"))
            row["sat_model_verified"]=ok
            if ok:row["status"]="SAT_MODEL_VERIFIED"
        if measured["rc"]==20:
            proof=a.out/(tag+".drat")
            if arm=="DRNAS_X5":
                cmd=[binary,cnf,"--mode","core","--time",str(a.cap),"--proof",proof]
            elif arm=="KISSAT":
                cmd=[binary,cnf,proof]
            else:
                cmd=[binary,"-q","--no-binary",cnf,proof]
            replay=run(cmd,a.out/(tag+".replay.log"),a.cap+2,256)
            row.update(proof_replay_s=replay["wall_s"],replay_rc=replay["rc"])
            if replay["rc"]==20 and proof.exists() and proof.stat().st_size:
                log=a.out/(tag+".drat-trim.log")
                checked=run([a.drat_trim,cnf,proof],log,120,256)
                ok=(checked["rc"]==0 and not checked["timeout"] and
                    "s VERIFIED" in log.read_text(errors="replace"))
                row.update(standard_verified=ok,proof_check_s=checked["wall_s"],
                           proof_bytes=proof.stat().st_size,
                           proof_sha256=sha256(proof),
                           status="UNSAT_DRAT_VERIFIED" if ok else "UNSAT_PROOF_REJECTED")
            else:
                row["status"]="UNSAT_REPLAY_UNVERIFIED"
        rows.append(row)
        print("QUEENS_FOCUS60_TRIAL "+json.dumps({k:row.get(k) for k in
             ("original_id","arm","status","wall_s","sat_model_verified",
              "standard_verified","proof_replay_s","proof_check_s")},sort_keys=True),
              flush=True)
        with (a.out/"trials.jsonl").open("a") as fd:
            fd.write(json.dumps(row,sort_keys=True)+"\n")
    verified_sat=sum(x["sat_model_verified"] for x in rows)
    verified_unsat=sum(x["standard_verified"] for x in rows)
    contradiction=verified_sat and verified_unsat
    report=dict(protocol=protocol,rows=rows,verified_sat=verified_sat,
                verified_unsat=verified_unsat,conflict=bool(contradiction))
    (a.out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("QUEENS_FOCUS60_SUMMARY "+json.dumps({k:report[k] for k in
          ("verified_sat","verified_unsat","conflict")},sort_keys=True),flush=True)
    if contradiction or any(x["status"]=="UNSAT_PROOF_REJECTED" for x in rows):
        raise SystemExit("CRITICAL: contradictory result or rejected proof")

if __name__=="__main__":
    main()
