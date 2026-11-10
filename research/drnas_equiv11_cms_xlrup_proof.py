#!/usr/bin/env python3
"""EQUIV11-PROOF: independently check CryptoMiniSat XLRUP on the exact original
EQUIV9 SHA. This does NOT certify any proof emitted by DRNAS native itself.
Certificate accepted only on explicit 's VERIFIED UNSAT' from pinned CakeML
cake_xlrup using original-CNF bytes and the complete binary XLRUP proof.
No solved-status claim on timeout, size cap, or checker error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import resource
import signal
import subprocess
import tempfile
import time

import drnas_equiv9_prospective_seed_holdout as e9

ROOT=pathlib.Path("mre_equiv11proof")
PROTO="DRNAS-EQUIV11-CMS5.17-XLRUP-ORIGINAL-SHA-CERTIFICATE-v1"
TARGET_SHA="327bfcaa1933d1c2b293f90f5761bfb25448c577d4a6958b962d4a09a1c88b7a"
CMS_SHA="03954f7f7815ea3984774c95a66e7c224cd25952"
CAKE_REPO_SHA="18cd6bc17af10a9891c10a846ce966166f9fe0dc"
CMS=pathlib.Path("/tmp/drnas-e11-cms/build/cryptominisat5")
CAKE=pathlib.Path("/tmp/drnas-e11-frat/cake_xlrup/cake_xlrup")
SOLVE_CAP=180.0
CHECKER_CAP=120.0
PROOF_MAX_BYTES=256*1024*1024

def need(value,message):
    if not value:raise RuntimeError("EQUIV11_FAIL_CLOSED "+str(message))

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def run(cmd,cap,folder,tag,size_cap=None):
    """One pinned logical CPU, process group, wall deadline and RLIMIT_FSIZE.
    Output is retained only in small capped summaries and never as huge CI logs.
    """
    folder=pathlib.Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    stdout=folder/(tag+".stdout")
    stderr=folder/(tag+".stderr")
    cpu=min(os.sched_getaffinity(0))
    def setup():
        os.setsid()
        os.sched_setaffinity(0,{cpu})
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        if size_cap is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE,(size_cap,size_cap))
    start=time.perf_counter()
    with stdout.open("wb") as fo,stderr.open("wb") as fe:
        p=subprocess.Popen([str(a) for a in cmd],stdout=fo,stderr=fe,
                           preexec_fn=setup)
        timed_out=False
        try:p.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            timed_out=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
    result=dict(return_code=p.returncode,timed_out=timed_out,
                wall_s=round(time.perf_counter()-start,5),logical_cpu=cpu)
    for field,path in (("stdout_tail",stdout),("stderr_tail",stderr)):
        with open(path,"rb") as f:
            f.seek(max(0,path.stat().st_size-1800))
            result[field]=f.read(1800).decode("utf-8","replace")
    return result

def cms_status(info):
    output=info["stdout_tail"]+"\n"+info["stderr_tail"]
    if info["timed_out"]:return "TIMEOUT"
    if info["return_code"]==20 and "s UNSATISFIABLE" in output:return "UNSAT"
    if info["return_code"]==10 and "s SATISFIABLE" in output:return "SAT"
    return "UNKNOWN"

def checker_verified(info):
    output=info["stdout_tail"]+"\n"+info["stderr_tail"]
    return (not info["timed_out"] and info["return_code"]==0
            and any(line.strip()=="s VERIFIED UNSAT" for line in output.splitlines()))

def check_proof(src,proof,folder,tag):
    need(proof.is_file() and proof.stat().st_size>0,"proof missing or empty")
    verified=run([CAKE,src,proof],CHECKER_CAP,folder,tag)
    return verified

def toy_tests():
    ROOT.mkdir(exist_ok=True)
    need(CMS.is_file() and CAKE.is_file(),"proof solver/checker missing")
    with tempfile.TemporaryDirectory(prefix="e11-toy-") as d:
        tmp=pathlib.Path(d)
        unsat=tmp/"toy-unsat.cnf"
        unsat.write_text("p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n")
        proof=tmp/"toy.xlrupb"
        solved=run([CMS,"--xlrup","2","-t","1","--verb","0",
                    unsat,proof],30,tmp,"unsat-solver",8*1024*1024)
        need(cms_status(solved)=="UNSAT","UNSAT toy solve failed")
        checked=check_proof(unsat,proof,tmp,"unsat-checker")
        need(checker_verified(checked),"independent UNSAT toy check failed "+
             str(checked))
        sat=tmp/"toy-sat.cnf"
        sat.write_text("p cnf 2 2\n1 2 0\n-1 2 0\n")
        solve_sat=run([CMS,"--xlrup","2","-t","1","--verb","0",
                       sat,tmp/"sat-proof.xlrupb"],30,tmp,"sat-solver",
                      8*1024*1024)
        need(cms_status(solve_sat)=="SAT","SAT negative control failed")
        need(not checker_verified(solve_sat),"SAT misclassified as verified UNSAT")
    print("EQUIV11_SELFTEST_PASS "+json.dumps(dict(
        original_toy_UNSAT_XLRUP_check=True,
        SAT_negative_control=True,
        cake_repo_sha=CAKE_REPO_SHA,cms_sha=CMS_SHA),
        sort_keys=True),flush=True)

def source_original():
    m=e9.verify()
    targets=[c for c in m["cases"] if c["sha256"]==TARGET_SHA]
    need(len(targets)==1 and targets[0]["cohort"]=="holdout",
         "target must be single EQUIV9 source")
    c=targets[0]
    src=e9.SOURCE/c["filename"]
    need(digest(src)==TARGET_SHA,"original CNF SHA mismatch")
    return src,c

def certificate():
    ROOT.mkdir(exist_ok=True)
    need(CMS.is_file() and CAKE.is_file(),"independent tools absent")
    src,c=source_original()
    result=dict(protocol=PROTO,source_original_sha256=TARGET_SHA,
        source_year=c["year"],source_gbd=c["gbd"],
        crypto_minisat_source_commit=CMS_SHA,
        independent_cake_checker_commit=CAKE_REPO_SHA,
        original_sha_verified=True,
        original_native_claim="UNSAT in EQUIV9; independent proof not produced by native",
        proof_generator="CryptoMiniSat 5.17, 1 logical CPU",
        proof_format="binary XLRUP",proof_max_bytes=PROOF_MAX_BYTES,
        max_solve_wall_s=SOLVE_CAP,max_checker_wall_s=CHECKER_CAP,
        UNSAT_certified_by_independent_proof=False,
        certification_status="UNVERIFIED",no_automatic_promotion=True,
        provenance_sane=True)
    with tempfile.TemporaryDirectory(prefix="e11-original-") as d:
        tmp=pathlib.Path(d)
        proof=tmp/"original.xlrupb"
        solved=run([CMS,"--xlrup","2","-t","1","--verb","0",
                    src,proof],SOLVE_CAP,tmp,"original-solver",PROOF_MAX_BYTES)
        result["cms_solve"]=solved
        status=cms_status(solved)
        result["cms_status"]=status
        if status=="SAT":
            # Contradiction alarm, not a certified conclusion:
            # model will be checked separately on ORIGINAL CNF below.
            out=(tmp/"original-solver.stdout").read_text(errors="replace")
            n,clauses=e9.x22.read_cnf(src)
            valid=e9.x22.solver_result("cms",10,out,clauses,{})[1]
            need(valid,"CMS SAT witness invalid on original CNF")
            result["SAT_original_witness_verified"]=True
            result["certification_status"]="SAT_WITNESS_CONTRADICTS_NATIVE_UNSAT"
        elif status=="UNSAT" and proof.is_file() and 0<proof.stat().st_size<=PROOF_MAX_BYTES:
            result["proof_bytes"]=proof.stat().st_size
            result["proof_sha256"]=digest(proof)
            check=check_proof(src,proof,tmp,"original-checker")
            result["independent_cake_result"]=check
            if checker_verified(check):
                result["UNSAT_certified_by_independent_proof"]=True
                result["certification_status"]="CERTIFIED_ORIGINAL_UNSAT_BY_CMS_XLRUP"
        elif solved["return_code"]==-signal.SIGXFSZ:
            result["certification_status"]="UNVERIFIED_PROOF_SIZE_CAP"
        elif solved["timed_out"]:
            result["certification_status"]="UNVERIFIED_SOLVER_TIMEOUT"
        else:
            result["certification_status"]="UNVERIFIED_NO_COMPLETE_PROOF"
    need(digest(src)==TARGET_SHA,"original source changed during validation")
    (ROOT/"report.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("EQUIV11_FINAL "+json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","certificate"))
    args=parser.parse_args()
    if args.action=="selftest":toy_tests()
    else:certificate()
