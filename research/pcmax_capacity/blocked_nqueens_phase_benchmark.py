#!/usr/bin/env python3
"""One-logical-CPU source-paired benchmark on 24 frozen blocked N-Queens CNFs.

All four arms see identical original CNF bytes. Generic solvers timed with
proof output disabled. A separate, separately timed proof replay is attempted
only on raw UNSAT. No result counts as verified UNSAT until a pinned external
drat-trim accepts the original source CNF and proof. Original CNF SAT models
must be complete and satisfy every clause. The PHP structural module uses
VeriPB instead, and has no CDCL fallback. Unknown labels are never guessed.
"""
import argparse
import hashlib
import json
import os
import resource
import subprocess
import time
from pathlib import Path
from blocked_nqueens_phase_generate import freeze

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def run(command,out,seconds,file_limit_mb=96):
    t=time.perf_counter()
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(file_limit_mb<<20,file_limit_mb<<20))
    with out.open("w") as f:
        try:
            p=subprocess.run([str(c) for c in command],stdout=f,
                             stderr=subprocess.STDOUT,timeout=seconds,
                             preexec_fn=limits,check=False)
            return dict(rc=p.returncode,wall_s=round(time.perf_counter()-t,6),
                        timeout=False)
        except subprocess.TimeoutExpired:
            return dict(rc=None,wall_s=round(time.perf_counter()-t,6),
                        timeout=True)

def model_ok(cnf,stdout):
    n=None
    assignment={}
    for line in stdout.splitlines():
        if line.startswith("v "):
            try: lits=[int(t) for t in line.split()[1:]]
            except ValueError:return False
            for lit in lits:
                if not lit:continue
                old=assignment.get(abs(lit))
                if old is not None and old!=(lit>0):return False
                assignment[abs(lit)]=lit>0
    with cnf.open() as source:
        clause=[]
        count=0
        declared=None
        for line in source:
            s=line.split()
            if not s or s[0]=="c":continue
            if s[0]=="p":
                if len(s)!=4:return False
                n=int(s[2]);declared=int(s[3])
                if len(assignment)!=n:return False
                continue
            for t in s:
                l=int(t)
                if l:clause.append(l)
                else:
                    count+=1
                    if not any(assignment.get(abs(x))==(x>0) for x in clause):
                        return False
                    clause=[]
        return bool(n and declared==count and not clause)

def summarize_trial(case,arm,row):
    return {k:row.get(k) for k in
            ("case","board_n","allowed_per_row","arm","status",
             "wall_s","proof_replay_s","checker_s",
             "model_verified","proof_verified")}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,required=True,choices=range(4))
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--x5",type=Path,required=True)
    p.add_argument("--php",type=Path,required=True)
    p.add_argument("--kissat",type=Path,required=True)
    p.add_argument("--cadical",type=Path,required=True)
    p.add_argument("--drat-trim",type=Path,required=True)
    p.add_argument("--veripb",type=Path,required=True)
    p.add_argument("--cap",type=int,default=12)
    args=p.parse_args()
    assert 5<=args.cap<=45
    assert not args.out.exists(),"Output directory must be fresh"
    for path in (args.x5,args.php,args.kissat,args.cadical,
                 args.drat_trim,args.veripb):
        assert path.is_file(),path
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    assert len(os.sched_getaffinity(0))==1
    frozen=freeze(args.shard,args.out)
    binpaths={"DRNAS_X5":args.x5,"KISSAT":args.kissat,
              "CADICAL":args.cadical,"DRNAS_PHP":args.php}
    protocol=dict(name="BLOCKED_NQUEENS_PHASE_SYNTH_V1",cpu=cpu,cap_s=args.cap,
                  script_sha256=sha256(Path(__file__).resolve()),
                  binary_sha256={k:sha256(v) for k,v in
                                 {**binpaths,"DRAT_TRIM":args.drat_trim,
                                  "VERIPB":args.veripb}.items()},
                  one_cpu_per_solver=True,arms=list(binpaths),
                  proof_replay_cap_s=args.cap,
                  standard_checker_cap_s=65,
                  synthetic_not_external_blind=True,
                  unknown_truth_requires_model_or_proof=True,
                  source_sha_before_each_arm=True,
                  measurement="no-proof primary solve; proof replay independently timed")
    (args.out/"protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")
    rows=[]
    with (args.out/"trials.jsonl").open("w") as logfile:
        for case in frozen["cases"]:
            cnf=args.out/(case["id"]+".cnf")
            sourcesha=case["sha256"]
            arms=list(binpaths)
            rotation=int(hashlib.sha256(case["id"].encode()).hexdigest()[:4],16)%len(arms)
            arms=arms[rotation:]+arms[:rotation]
            for arm in arms:
                assert sha256(cnf)==sourcesha,"Source input changed after freeze"
                tag=case["id"]+"_"+arm.lower()
                dest=args.out/(tag+".log")
                proof=args.out/(tag+(".pbp" if arm=="DRNAS_PHP" else ".drat"))
                if arm=="DRNAS_X5":
                    command=[args.x5,cnf,"--mode","core","--time",str(args.cap)]
                elif arm=="KISSAT":
                    command=[args.kissat,cnf]
                elif arm=="CADICAL":
                    command=[args.cadical,"-q",cnf]
                else:
                    command=[args.php,cnf,"--proof",proof,"--time",str(args.cap)]
                measured=run(command,dest,args.cap+2)
                status=("TIMEOUT" if measured["timeout"] else
                        "SAT_UNVERIFIED" if measured["rc"]==10 else
                        "UNSAT_UNVERIFIED" if measured["rc"]==20 else
                        "UNKNOWN" if measured["rc"]==0 else "EXECUTION_ERROR")
                row=dict(case=case["id"],family=case["family"],
                         board_n=case["n"],allowed_per_row=case["degree"],
                         blocked_density=case["blocked_density"],expected=case["label"],
                         sha256=sourcesha,variables=case["variables"],
                         clauses=case["clauses"],arm=arm,
                         model_verified=False,proof_verified=False,
                         proof_replay_s=None,checker_s=None,
                         proof_bytes=None,**measured,status=status)
                if measured["rc"]==10:
                    row["model_verified"]=model_ok(cnf,dest.read_text(errors="replace"))
                    if row["model_verified"]:row["status"]="SAT_MODEL_VERIFIED"
                    if case["label"]=="WITNESS_SAT" and not row["model_verified"]:
                        row["status"]="SAT_UNVERIFIED_CONTROL"
                if measured["rc"]==20:
                    replay=measured
                    if arm!="DRNAS_PHP":
                        if arm=="DRNAS_X5":
                            cmd=[args.x5,cnf,"--mode","core","--time",
                                 str(args.cap),"--proof",proof]
                        elif arm=="KISSAT":
                            cmd=[args.kissat,cnf,proof]
                        else:
                            cmd=[args.cadical,"-q","--no-binary",cnf,proof]
                        replay=run(cmd,args.out/(tag+".replay.log"),args.cap+2)
                        row["proof_replay_s"]=replay["wall_s"]
                        row["replay_rc"]=replay["rc"]
                    if replay["rc"]==20 and proof.is_file() and proof.stat().st_size:
                        chklog=args.out/(tag+".checker.log")
                        chkcmd=([args.veripb,"--cnf",cnf,proof] if arm=="DRNAS_PHP"
                                else [args.drat_trim,cnf,proof])
                        checked=run(chkcmd,chklog,65)
                        accepted=checked["rc"]==0 and not checked["timeout"]
                        if arm!="DRNAS_PHP":
                            accepted &= "s VERIFIED" in chklog.read_text(errors="replace")
                        row.update(checker_s=checked["wall_s"],checker_rc=checked["rc"],
                                   proof_bytes=proof.stat().st_size,
                                   proof_sha256=sha256(proof),proof_verified=accepted,
                                   status=("UNSAT_"+("VERIPB" if arm=="DRNAS_PHP" else "DRAT")+"_VERIFIED"
                                           if accepted else "UNSAT_PROOF_REJECTED"))
                    else:row["status"]="UNSAT_REPLAY_NOT_CERTIFIED"
                if arm=="DRNAS_PHP" and measured["rc"]!=20 and proof.exists():
                    row["status"]="INVALID_PROOF_ON_UNKNOWN"
                if case["label"]=="WITNESS_SAT" and measured["rc"]==20:
                    row["status"]="CRITICAL_FALSE_UNSAT_ON_SAT_CONTROL"
                rows.append(row)
                logfile.write(json.dumps(row,sort_keys=True)+"\n")
                logfile.flush()
                print("BLOCKED_QUEEN_TRIAL "+json.dumps(summarize_trial(case,arm,row),
                                                        sort_keys=True),flush=True)
    summary=dict(protocol=protocol,cases=frozen["cases"],trials=rows,
                 trial_count=len(rows),
                 models_verified=sum(r["model_verified"] for r in rows),
                 unsat_proofs_verified=sum(r["proof_verified"] for r in rows),
                 errors=sum(r["status"].startswith(("CRITICAL","INVALID",
                                                   "EXECUTION_ERROR","UNSAT_PROOF_REJECTED"))
                            for r in rows))
    (args.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("BLOCKED_QUEEN_SUMMARY "+json.dumps({k:summary[k] for k in
          ("trial_count","models_verified","unsat_proofs_verified","errors")},
          sort_keys=True),flush=True)
    if summary["errors"]:
        raise SystemExit("AUDIT_ERROR: inspect trials and checker logs")

if __name__=="__main__":
    main()
