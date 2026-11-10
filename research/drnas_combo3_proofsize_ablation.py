#!/usr/bin/env python3
"""COMBO3: exact original-CNF proof-generation/validation overhead ablation.
Two previously Certified COMBO2 original SHA; 4 precommitted CMS5.17 modes,
2 repetitions, 1 logical CPU, 50s solver cap, 40s CakeML verifier cap,
320MiB max transient proof; 16 trials total. No blind optimization claims.
Only CakeML s VERIFIED UNSAT counts as solved. Never upload proof files.
The proof is CMS-generated, NOT DRNAS native, and original 10s PAR2 unchanged.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,random,time
import drnas_combo2_independent_xlrup_cert as prev

ROOT=pathlib.Path("mre_combo3proof")
PROTO="DRNAS-COMBO3-CMS517-XLRUP-GAUSS-PRESIMP-2SHA-4ARM-2REP-ONECPU-v1"
TARGETS=prev.TARGETS
REPS=2
ARMS={
    "cms_default":[],
    "gauss_persist":["--autodisablegauss","0"],
    "gauss_wide":["--autodisablegauss","0","--maxnummatrices","32",
                  "--maxmatrixrows","20000","--maxmatrixcols","20000",
                  "--minmatrixrows","1"],
    "no_presimp":["--presimp","0"],
}
SOLVE_CAP=50.
CHECKER_CAP=40.
TOTAL_CERT_CAP=90.
MAX_PROOF=320*1024*1024
EXPECTED=len(TARGETS)*REPS*len(ARMS)

def need(x,msg):
    if not x:raise RuntimeError("COMBO3_FAIL_CLOSED "+msg)

def read(p):return json.loads(pathlib.Path(p).read_text())
def digest(p):return prev.digest(p)
def save(p,obj):return prev.save(p,obj)
def config():
    return dict(protocol=PROTO,arms=ARMS,targets=list(TARGETS),
      reps=REPS,expected_trials=EXPECTED,solve_cap_s=SOLVE_CAP,
      certified_total_wall_cap_s=TOTAL_CERT_CAP,
      checker_cap_s=CHECKER_CAP,max_transient_proof_bytes=MAX_PROOF,
      unmodified_original_CNF=True,single_logical_CPU=True,
      independent_CakeML_XLRUP_certificate_required=True,
      no_proof_artifact_uploaded=True,not_blind_same_two_known_formulas=True,
      no_automatic_promotion=True,code_sha=digest(__file__),
      earlier_cert_report_SHA=digest("prior_combo2proof/report.json"),
      base_proof_driver_sha=digest("research/drnas_combo2_independent_xlrup_cert.py"),
      original_manifest_sha=digest(prev.MAN))
def precheck():
    need(prev.CMS.is_file() and prev.CAKE.is_file(),"pinned CMS/CAKE absent")
    old=read("prior_combo2proof/report.json")
    need(old["protocol"]==prev.PROTO and
         old["independent_XLRUP_CakeML_verified_count"]==2,
         "prior original certified report not verified")
    cases=prev.source_manifest()
    need(all(old["certificates"][s]["independent_verified"] for s in TARGETS),
         "both prior source certificates must be accepted")
    return cases
def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    precheck()
    save(ROOT/"manifest.json",config())
    verify()
    print("COMBO3_FROZEN "+json.dumps(dict(trials=EXPECTED,arms=len(ARMS),
        exact_original_SHA=len(TARGETS),oneCPU=True,
        selection="previously certified, not blind"),sort_keys=True),flush=True)
def verify():
    precheck()
    need(read(ROOT/"manifest.json")==config(),"manifest/binary/code hash changed")
def selftest():
    precheck()
    prev.toy_tests() if hasattr(prev,"toy_tests") else prev.selftest()
    print("COMBO3_SELFTEST_PASS "+json.dumps(dict(CakeML_toy_UNSAT=True,
       SAT_negative_control=True,source_lock_two_SHA=True),sort_keys=True),flush=True)

def trial(source,arm,rep):
    need(arm in ARMS and rep in range(REPS),"bad arm/rep")
    case=prev.source_manifest()[source]
    src=prev.SOURCES/case["filename"]
    need(digest(src)==source,"original SHA drift")
    root=ROOT/("trial-"+source[:10]+"-"+arm+"-"+str(rep))
    root.mkdir(exist_ok=True,parents=True)
    proof=root/"temporary.xlrupb"
    cmd=[prev.CMS,"--xlrup","2","-t","1","--verb","0"]+ARMS[arm]+[src,proof]
    started=time.perf_counter()
    info=prev.run(cmd,SOLVE_CAP,root,"generator",MAX_PROOF)
    status=prev.status_of(info)
    if status=="UNKNOWN" and info["wall_s"]<0.1:
        need(False,"CMS failed immediately with rc="+str(info["return_code"])+
             " stderr="+info["stderr_tail"][:500])
    ck=None;verified=False;bytes_=0;proof_sha=None;reason="UNVERIFIED"
    if proof.is_file():
        bytes_=proof.stat().st_size
        if 0<bytes_<=MAX_PROOF:
            proof_sha=digest(proof)
    if status=="UNSAT" and 0<bytes_<=MAX_PROOF:
        ck=prev.run([prev.CAKE,src,proof],CHECKER_CAP,root,"CakeML_checker")
        verified=prev.checker_verified(ck)
        reason="CERTIFIED_ORIGINAL_UNSAT_XLRUP" if verified else "UNVERIFIED_CHECKER"
    elif info["timed_out"]:
        reason="UNVERIFIED_SOLVE_TIMEOUT"
    elif info["return_code"]==-25:
        reason="UNVERIFIED_PROOF_FILE_CAP"
    elif bytes_>MAX_PROOF:
        reason="UNVERIFIED_PROOF_TOO_LARGE"
    elif status=="SAT":
        # Unexpected SAT: fail the experiment, do not assert source UNSAT.
        need(False,"SAT contradiction with previously independently certified original UNSAT")
    else:
        reason="UNVERIFIED_INCOMPLETE_PROOF_OR_UNKNOWN"
    elapsed=time.perf_counter()-started
    need(digest(src)==source,"original SHA changed after solver")
    row=dict(protocol=PROTO,sha256=source,arm=arm,rep=rep,
       precommitted=True,CMS_commit=prev.CMS_COMMIT,CakeML_commit=prev.CAKE_COMMIT,
       original_SHA_verified=True,one_logical_CPU=info["logical_CPU"],
       status=status,CakeML_verified_UNSAT=verified,
       solve_wall_s=info["wall_s"],checker_wall_s=ck["wall_s"] if ck else None,
       proof_bytes=bytes_,proof_SHA256=proof_sha,
       proof_certification_status=reason,
       verified_E2E_wall_s=round(elapsed,6),
       certified_PAR2_90s_s=round(elapsed if verified and elapsed<=TOTAL_CERT_CAP else 2*TOTAL_CERT_CAP,6),
       checker_returncode=ck["return_code"] if ck else None,
       checker_verdict=ck["stdout_tail"].strip() if ck else None)
    # Save metadata before removing potentially huge transient proof.
    save(ROOT/("row-"+source[:12]+"-"+arm+"-"+str(rep)+".json"),row)
    import shutil
    shutil.rmtree(root)
    print("COMBO3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row
def shard(index):
    verify()
    need(index in (0,1),"two source sharded")
    src=TARGETS[index]
    todo=[(arm,rep) for rep in range(REPS) for arm in ARMS]
    random.Random(src+"COMBO3").shuffle(todo)
    rows=[]
    for arm,rep in todo:
        rows.append(trial(src,arm,rep))
        save(ROOT/f"shard-{index}.json",rows)
    need(len(rows)==len(ARMS)*REPS,"incomplete source shard")
    print("COMBO3_SHARD_PASS "+str(index)+" "+str(len(rows)),flush=True)
def audit():
    verify()
    rows=read(ROOT/"shard-0.json")+read(ROOT/"shard-1.json")
    needed={(sha,arm,rep) for sha in TARGETS for arm in ARMS for rep in range(REPS)}
    got={(r["sha256"],r["arm"],r["rep"]) for r in rows}
    need(len(rows)==len(got)==EXPECTED and got==needed,"missing, duplicate or unexpected trial")
    for r in rows:
        need(r["protocol"]==PROTO and r["original_SHA_verified"] and
             r["precommitted"] and r["status"] in ("UNSAT","TIMEOUT","UNKNOWN") and
             r["CMS_commit"]==prev.CMS_COMMIT and
             r["CakeML_commit"]==prev.CAKE_COMMIT and
             (not r["CakeML_verified_UNSAT"] or r["checker_verdict"]=="s VERIFIED UNSAT"),
             "untrusted proof or roster drift")
    stats={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        stats[arm]=dict(trials=len(a),certified=sum(x["CakeML_verified_UNSAT"] for x in a),
          solve_wall_total_s=round(sum(x["solve_wall_s"] for x in a),6),
          certified_E2E_total_s=round(sum(x["verified_E2E_wall_s"] for x in a),6),
          PAR2_90s_s=round(sum(x["certified_PAR2_90s_s"] for x in a),6),
          proof_bytes_total=sum(x["proof_bytes"] for x in a),
          by_source={s:[dict(rep=x["rep"],verified=x["CakeML_verified_UNSAT"],
                solve_s=x["solve_wall_s"],check_s=x["checker_wall_s"],
                E2E_s=x["verified_E2E_wall_s"],
                proof_bytes=x["proof_bytes"],reason=x["proof_certification_status"])
                for x in a if x["sha256"]==s] for s in TARGETS})
    b=stats["cms_default"]["PAR2_90s_s"]
    for arm in stats:
        stats[arm]["PAR2_ratio_vs_default_x"]=round(
            b/stats[arm]["PAR2_90s_s"],6)
    report=dict(protocol=PROTO,source_original_SHA=list(TARGETS),total_trials=EXPECTED,
       CakeML_original_proof_checker_required=True,no_LRAT_claim_for_original_COMBO2_runs=True,
       proof_generation_is_separate_re_run_not_original_COMBO2_timing=True,
       original_COMBO2_10s_PAR2_is_not_overwritten=True,no_automatic_promotion=True,
       stats=stats)
    save(ROOT/"report.json",report)
    print("COMBO3_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    q=p.parse_args()
    if q.action=="shard":shard(q.shard)
    else:
        globals()[q.action]()
        if q.action=="verify":print("COMBO3_VERIFY_PASS",flush=True)
