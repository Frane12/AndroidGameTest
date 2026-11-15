#!/usr/bin/env python3
"""Single-logical-core matched 19 CNF evaluation. Never infer UNSAT from labels."""
from pathlib import Path
import hashlib, json, os, subprocess, tempfile, time, sys, re, csv, signal
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/"research/challenge19"
RESULT=ROOT/"challenge19_results"
RESULT.mkdir(exist_ok=True)
CAP_SOLVER=5.0
CAP_E2E=8.0
ARMS=("DRNAS_MATH5","DRNAS_HALL","Kissat","CaDiCaL")
BINS={"DRNAS_MATH5":ROOT/"build/drnas-x59-xor-math5-unified1",
      "DRNAS_HALL":ROOT/"build/drnas-pcmax",
      "Kissat":ROOT/"build/kissat","CaDiCaL":ROOT/"build/cadical"}
CHECKERS={"DRNAS_MATH5":ROOT/"research/math5/check_math5.py",
          "DRNAS_HALL":ROOT/"research/pcmax_capacity/check_clause_hall.py"}
SHA_FROZEN={
"tseitin_3regular_40_odd":"e0df76700e2e19325f7780643f3a873dbbeb1b6dd0f1809d38384f25294fa42d",
"tseitin_3regular_80_odd":"bd66962990040d689c2319148c592163a852ecaf3a384eb0182d59295e4f215c",
"tseitin_3regular_160_odd":"19f1388addcad268b1363b745580523ecd8d71066e7b2fc83770ae2ee7e83fff",
"tseitin_3regular_320_odd":"6014c059ca5a4f11a6be16932bcb70d51d3ebf3c816e63d0cb9cd5812d31bbd6",
"tseitin_3regular_40_even":"b3f4accb6a864a923e01387cbb93357363d8e75a004147e4b72687eedb05b00a",
"tseitin_3regular_80_even":"a4dff9b198a55975a1be8af38d5c0951a221febe2ed25fbd0c24df963c3d04d0",
"php_10_into_9":"d2f42a842b96ebcb12bcf3a78e167cec1f2b56a017a21db56c7ceff1d8f4a2df",
"php_16_into_15":"27258604263d5471ffc2d51b7c1fd335c01de812c1af715a08644ee610131974",
"php_21_into_20":"b597bb18104c44771ee75c66167d9881143289d092e96ee2753baa03875202a8",
"php_20_into_20":"3f6ff1065bf5dd5f7d1d3fce2b0f09dced4feaa74e826d9e4a1fcd348f125bd8",
"hall_15_jobs_14_slots_unsat":"adc1a45fa5a199c998a3b5397423d245b6cae03cd961e0b21583990f96a15a51",
"hall_23_jobs_22_slots_unsat":"24b806bc7b1b8fd307fae80dae1f0533fbce99ffdfb890f87f03f1be5cbbb1d7",
"hall_31_jobs_30_slots_unsat":"b9103ba3d1486e400004b283d7c950714c90ae320a78c199a9dc177f016e6035",
"hall_15_jobs_15_slots_sat":"86c717bcd3f9040d2575d1287fceb6a73f656cf5c555fe36a38b3e4206578fcf",
"hall_23_jobs_23_slots_sat":"cb556e68d11c6ff065d39d9c4ae547ab18e38dd18d2d113f9f38ba476ebbdaae",
"schur_3colors_13":"d0b0eb88074f5748e5458a71ac88cb81e1f78189964c2480a5aa5321f56ee50b",
"schur_3colors_14":"b1c4a952b748f95cbc2cb94804f4ee62f6b7ecba0c90d510c6c5d0efb0b81531",
"schur_4colors_44":"ed7e55c4bfb2b7cb62a5ef2a4bcf832e7a3df22baa7c972c22da368d6bdd03ac",
"schur_4colors_45":"98065e13ae8fd20eee1ea1732771d1717b3215c691a5c6d0637e46025e9330ab"}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def model_valid(cnf, stdout):
    values={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for token in line[2:].split():
            try:lit=int(token)
            except ValueError:return False
            if not lit:continue
            if abs(lit) in values and values[abs(lit)]!=(lit>0):return False
            values[abs(lit)]=lit>0
    if not values:return False
    clause=[]
    for line in cnf.read_text().splitlines():
        if line.startswith(("p ","c ")) or not line.strip():continue
        for x in map(int,line.split()):
            if x==0:
                if not any(values.get(abs(a))==(a>0) for a in clause):return False
                clause=[]
            else: clause.append(x)
    return not clause
CPU=min(os.sched_getaffinity(0))
def pin():os.sched_setaffinity(0,{CPU})
def invoke(cmd, cap, cwd=None):
    p=subprocess.Popen(list(map(str,cmd)),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,start_new_session=True,preexec_fn=pin,cwd=cwd)
    try:
        out,err=p.communicate(timeout=cap)
        return dict(rc=p.returncode,stdout=out,stderr=err,timeout=False)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL)
        out,err=p.communicate()
        return dict(rc=p.returncode,stdout=out,stderr=err,timeout=True)
def trial(case,arm,idx):
    cnf=DATA/case["file"];stem=Path(case["file"]).stem
    folder=RESULT/f"{idx:02}-{stem}-{arm}";folder.mkdir()
    drat=folder/"proof.drat";cert=folder/"structural.json"
    binary=BINS[arm].resolve()
    if arm=="DRNAS_MATH5":
        cmd=[binary,cnf,"--mode","core","--time",str(CAP_SOLVER),
             "--sat-construct-ms","25","--math5-ms","200",
             "--math5-certificate",cert,"--stats"]
    elif arm=="DRNAS_HALL":
        cmd=[binary,cnf,"--mode","core","--time",str(CAP_SOLVER),
             "--pcmax-clause-guard","--pcmax-budget-ms","500",
             "--pcmax-certificate",cert,"--stats"]
    elif arm=="Kissat":cmd=[binary,cnf,drat]
    else:cmd=[binary,"-q","--no-binary",cnf,drat]
    t0=time.perf_counter();p=invoke(cmd,CAP_SOLVER)
    solver_s=time.perf_counter()-t0
    (folder/"solver.stdout").write_text(p["stdout"])
    (folder/"solver.stderr").write_text(p["stderr"])
    claim="UNKNOWN";status="TIMEOUT" if p["timeout"] else "UNKNOWN";kind=None;verified=False
    if not p["timeout"]:
        if p["rc"]==10 and "s SATISFIABLE" in p["stdout"].splitlines():
            claim="SAT";kind="MODEL";verified=model_valid(cnf,p["stdout"])
            status="SAT_VERIFIED" if verified else "INVALID_MODEL"
        elif p["rc"]==20 and "s UNSATISFIABLE" in p["stdout"].splitlines():
            claim="UNSAT"
            check=None
            if cert.is_file() and arm in CHECKERS:
                kind="SOURCE_STRUCTURAL"
                check=[sys.executable,CHECKERS[arm],cnf,cert]
            elif drat.is_file() and drat.stat().st_size:
                kind="DRAT";check=[ROOT/"build/drat-trim",cnf,drat]
            if check:
                remaining=CAP_E2E-(time.perf_counter()-t0)
                if remaining>0:
                    q=invoke(check,remaining)
                    (folder/"checker.stdout").write_text(q["stdout"])
                    (folder/"checker.stderr").write_text(q["stderr"])
                    verified=(not q["timeout"] and q["rc"]==0 and
                              ("VERIFIED" in q["stdout"] if kind=="SOURCE_STRUCTURAL"
                               else "VERIFIED" in q["stdout"]))
                    status="UNSAT_VERIFIED" if verified else ("CHECK_TIMEOUT" if q["timeout"] else "INVALID_PROOF")
                else:status="CHECK_BUDGET"
            else:status="UNSAT_UNVERIFIED"
        elif p["rc"] not in (0,10,20):status="SOLVER_ERROR"
    elapsed=time.perf_counter()-t0
    correct=(claim==case["expected"] or claim=="UNKNOWN")
    if not correct:status="WRONG_ANSWER";verified=False
    accepted=verified and elapsed<=CAP_E2E
    result=dict(index=idx,case=stem,family=case["family"],sha256=case["sha256"],expected=case["expected"],
                arm=arm,claim=claim,status=status,proof_kind=kind,accepted=accepted,
                solver_s=round(solver_s,6),e2e_s=round(elapsed,6),
                PAR2_verified_s=round(elapsed if accepted else 2*CAP_E2E,6))
    (folder/"trial.json").write_text(json.dumps(result,indent=2))
    print("CHALLENGE19_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    return result
def main():
    manifest=json.loads((DATA/"manifest.json").read_text())["benchmarks"]
    assert len(manifest)==19 and len(SHA_FROZEN)==19
    for case in manifest:
        cnf=DATA/case["file"]
        assert cnf.is_file() and sha(cnf)==case["sha256"]==SHA_FROZEN[Path(case["file"]).stem], case
    assert sum(c["expected"]=="UNSAT" for c in manifest)==12
    assert sum(c["expected"]=="SAT" for c in manifest)==7
    for arm,p in BINS.items():assert p.is_file(),(arm,p)
    print("CHALLENGE19_PREFLIGHT "+json.dumps(dict(cases=19,one_core=CPU,binary_sha256={k:sha(v) for k,v in BINS.items()},seed=20261115,solver_timeout_s=CAP_SOLVER,verified_e2e_cap_s=CAP_E2E)),flush=True)
    rows=[]
    for i,case in enumerate(manifest):
        order=list(ARMS);offset=i%len(order);order=order[offset:]+order[:offset]
        for arm in order:rows.append(trial(case,arm,i))
    assert len(rows)==76
    with (RESULT/"trials.csv").open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
    summary={a:dict(verified_solved=sum(x["accepted"] for x in rows if x["arm"]==a),
      verified_unsat=sum(x["status"]=="UNSAT_VERIFIED" for x in rows if x["arm"]==a),
      verified_sat=sum(x["status"]=="SAT_VERIFIED" for x in rows if x["arm"]==a),
      unknown=sum(x["claim"]=="UNKNOWN" for x in rows if x["arm"]==a),
      invalid=sum(x["status"].startswith(("WRONG","INVALID")) for x in rows if x["arm"]==a),
      PAR2_verified_sum_s=round(sum(x["PAR2_verified_s"] for x in rows if x["arm"]==a),4))
      for a in ARMS}
    final=dict(protocol="19 frozen synthetic CNF; NOT blind industrial",cases=19,attempts=len(rows),summary=summary)
    (RESULT/"summary.json").write_text(json.dumps(final,indent=2,sort_keys=True))
    print("CHALLENGE19_FINAL "+json.dumps(final,sort_keys=True),flush=True)
    if any(x["status"].startswith(("WRONG","INVALID")) for x in rows):raise SystemExit("CRITICAL: an invalid claim/proof was detected")
if __name__=="__main__":main()
