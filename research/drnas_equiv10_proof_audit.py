#!/usr/bin/env python3
"""DRNAS EQUIV10P: attempt independent certificate of EQUIV9 native UNSAT.
Only independently checked DRAT-to-LRAT on the ORIGINAL SHA counts as certified.
Uses existing CaDiCaL3.0.1 proof producer and independently pinned drat-trim
and lrat-check. If anything fails or times out, output UNVERIFIED.
Never claim native itself emitted a proof.
"""
import argparse,hashlib,json,os,pathlib,re,resource,subprocess,tempfile,time

import drnas_equiv9_prospective_seed_holdout as e9

OUT=pathlib.Path("mre_equiv10proof")
TARGET_SHA="327bfcaa1933d1c2b293f90f5761bfb25448c577d4a6958b962d4a09a1c88b7a"
PROTO="DRNAS-EQUIV10P-INDEPENDENT-ORIGINAL-CNF-DRAT-LRAT-v1"
CAD=pathlib.Path("mre_equiv7/bin/cadical_3_0_1")
DRAT=pathlib.Path("/tmp/drat-trim/drat-trim")
LRAT=pathlib.Path("/tmp/drat-trim/lrat-check")
CAP=180
PROOF_BYTES_LIMIT=96*1024*1024

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def need(cond,msg):
    if not cond:raise RuntimeError("EQUIV10P_FAIL_CLOSED "+msg)
def run(cmd,seconds,limit_fsize=None):
    def impose():
        if limit_fsize:
            resource.setrlimit(resource.RLIMIT_FSIZE,(limit_fsize,limit_fsize))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    t=time.monotonic()
    try:
        p=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,
                          errors="replace",timeout=seconds,check=False,
                          preexec_fn=impose,start_new_session=True)
        return dict(rc=p.returncode,stdout=p.stdout[-2000:],stderr=p.stderr[-2000:],
                    elapsed_s=round(time.monotonic()-t,5),timeout=False)
    except subprocess.TimeoutExpired as e:
        return dict(rc=None,stdout="",stderr="TIMEOUT",
                    elapsed_s=round(time.monotonic()-t,5),timeout=True)
def valid_verified(out):
    text=(out.get("stdout","")+" "+out.get("stderr",""))
    return (out["rc"]==0 and re.search(r"\bVERIFIED\b",text)
            and not re.search(r"NOT VERIFIED|NOT VERIFIED|FAILED|ERROR",text,re.I))
def original():
    m=e9.verify()
    found=[c for c in m["cases"] if c["sha256"]==TARGET_SHA]
    need(len(found)==1 and found[0]["cohort"]=="holdout","target does not match original EQUIV9 holdout")
    src=e9.SOURCE/found[0]["filename"]
    need(sha(src)==TARGET_SHA,"original SHA drift")
    return src,found[0]
def selftest():
    OUT.mkdir(exist_ok=True)
    need(CAD.is_file() and DRAT.is_file() and LRAT.is_file(),"missing independent tools")
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)
        cnf=p/"toy-unsat.cnf"
        cnf.write_text("p cnf 1 2\n1 0\n-1 0\n")
        generated=run([CAD,"--no-binary",cnf,p/"toy.drat"],30)
        need(generated["rc"]==20 and (p/"toy.drat").exists(),"proof producer toy UNSAT failed")
        checked=run([DRAT,cnf,p/"toy.drat","-L",p/"toy.lrat"],30)
        need(bool(valid_verified(checked)) and (p/"toy.lrat").is_file(),"independent DRAT toy verification failed")
        replay=run([LRAT,cnf,p/"toy.lrat"],30)
        need(bool(valid_verified(replay)),"independent LRAT toy replay failed")
        sat=p/"toy-sat.cnf"
        sat.write_text("p cnf 1 1\n1 0\n")
        satresult=run([CAD,"--no-binary",sat,p/"sat.drat"],30)
        need(satresult["rc"]==10,"SAT negative control failed")
        print("EQUIV10P_SELFTEST_PASS "+json.dumps(dict(toy_UNSAT_DRAT_verified=True,toy_LRAT_verified=True,toy_SAT_not_misclassified=True)),flush=True)
def certify():
    OUT.mkdir(exist_ok=True)
    source,case=original()
    native=e9.trial(case,0,"native1",10)
    need(native["sha256"]==TARGET_SHA,"native trial SHA")
    result=dict(protocol=PROTO,original_sha256=TARGET_SHA,
        source_year=case["year"],source_gbd=case["gbd"],
        native_backend_status=native["status"],
        native_backend_time_s=native["wall_E2E_s"],
        native_produced_independent_proof=False,
        source_original_verified=sha(source)==TARGET_SHA,
        proof_producer="pinned CaDiCaL 3.0.1, independent from native",
        checker="drat-trim / lrat-check pinned commit 2e5e29c",
        independent_LRAT_verified=False,certification_status="UNVERIFIED",
        child_affinity=[min(os.sched_getaffinity(0))],cap_s=CAP,
        proof_bytes_limit=PROOF_BYTES_LIMIT)
    with tempfile.TemporaryDirectory(prefix="equiv10p-") as d:
        p=pathlib.Path(d)
        drat=p/"original.drat";lrat=p/"original.lrat"
        generated=run([CAD,source,drat],CAP,PROOF_BYTES_LIMIT)
        result["DRAT_format"]="binary"
        result["cadical_proof_solve"]=generated
        if generated["rc"]==20 and drat.is_file() and drat.stat().st_size>0:
            result["DRAT_bytes"]=drat.stat().st_size
            result["DRAT_sha256"]=sha(drat)
            checked=run([DRAT,source,drat,"-L",lrat],min(90,CAP),PROOF_BYTES_LIMIT)
            result["DRAT_checker_result"]=checked
            if valid_verified(checked) and lrat.is_file() and lrat.stat().st_size>0:
                result["LRAT_bytes"]=lrat.stat().st_size
                result["LRAT_sha256"]=sha(lrat)
                replay=run([LRAT,source,lrat],min(90,CAP),None)
                result["independent_LRAT_replay"]=replay
                if valid_verified(replay):
                    result["independent_LRAT_verified"]=True
                    result["certification_status"]="CERTIFIED_ORIGINAL_UNSAT"
    if not result["independent_LRAT_verified"]:
        # This is only a second backend opinion, NEVER a certified UNSAT proof.
        plain=run([CAD,source],90,None)
        result["cadical_plain_no_proof_crosscheck"]=dict(
            rc=plain["rc"],elapsed_s=plain["elapsed_s"],timeout=plain["timeout"],
            status="UNSAT" if plain["rc"]==20 else "SAT" if plain["rc"]==10 else "UNKNOWN")
        result["independent_backend_agreement_no_LRAT"]=(plain["rc"]==20)
    else:
        result["independent_backend_agreement_no_LRAT"]=True
    need(sha(source)==TARGET_SHA,"original CNF modified")
    (OUT/"report.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("EQUIV10P_FINAL "+json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","certify"))
    args=parser.parse_args()
    globals()[args.action]()
