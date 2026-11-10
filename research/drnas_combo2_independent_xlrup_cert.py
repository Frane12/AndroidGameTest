#!/usr/bin/env python3
"""COMBO2-PROOF: Independently certify TWO prior COMBO2 UNSAT-original CNFs.

Generator: pinned CMS 5.17 commit, binary XLRUP. Validator: pinned CakeML
cake_xlrup, run on unmodified ORIGINAL DIMACS bytes (SHA-256 locked).
A backend UNSAT alone is *never* a certificate. The baseline COMBO2 168-trial
report is immutable: optional post-hoc rescoring is clearly separated and
applies only after an independent checker returns exact "s VERIFIED UNSAT".
The new proof was NOT produced by DRNAS Native nor by the original COMBO2 run.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,resource,signal,subprocess,tempfile,time

ROOT=pathlib.Path("mre_combo2proof")
MAN=pathlib.Path("mre_combo2/manifest.json")
OLD=pathlib.Path("prior_combo2/report.json")
SOURCES=pathlib.Path("mre_search6/cases")
PROTO="DRNAS-COMBO2-2ORIGINAL-SHA-PINNED-CMS17-CAKEML-BINARY-XLRUP-v1"
CMS_COMMIT="03954f7f7815ea3984774c95a66e7c224cd25952"
CAKE_COMMIT="18cd6bc17af10a9891c10a846ce966166f9fe0dc"
CMS=pathlib.Path("/tmp/drnas-c2proof-cms/build/cryptominisat5")
CAKE=pathlib.Path("/tmp/drnas-c2proof-frat/cake_xlrup/cake_xlrup")
TARGETS=(
 "6e054967f4c71d900b2bba2508fea2054ac13de78fa0b0b6a94753f66e9e95fc",
 "732145a705686c5e303fd54b8fbd4370c5f7abc083e2c4320ac375ef4c7d1b0f",
)
SOLVE_CAP=180.0
CHECKER_CAP=120.0
PROOF_BYTES_MAX=256*1024*1024

def need(v,msg):
    if not v:raise RuntimeError("COMBO2_PROOF_FAIL_CLOSED "+str(msg))

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for data in iter(lambda:f.read(1024*1024),b""):
            h.update(data)
    return h.hexdigest()

def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def read(p):return json.loads(pathlib.Path(p).read_text())

def source_manifest():
    need(MAN.is_file(),"original COMBO2 frozen manifest missing")
    m=read(MAN)
    need(m["protocol"]=="DRNAS-COMBO2-MINPATH-SEARCH6-GF2-CMS17-KISSAT4-12SHA-7ARM-2REP-10S-v1",
         "COMBO2 manifest protocol mismatch")
    cases=m["original_cases"]
    need(len(cases)==12 and len({c["sha256"] for c in cases})==12,
         "COMBO2 manifest source count invalid")
    bysha={c["sha256"]:c for c in cases}
    need(set(TARGETS)<=set(bysha),"target not frozen in COMBO2 source roster")
    for sha in TARGETS:
        case=bysha[sha]
        need(case["gbd"]+".cnf"==case["filename"],"source naming unexpected")
        p=SOURCES/case["filename"]
        need(p.is_file() and digest(p)==sha,"original source byte SHA mismatch "+sha)
    return bysha

def run(command,cap,folder,name,size_cap=None):
    """One CPU process affinity; wall clock deadline; file limits; no huge log uploads."""
    folder=pathlib.Path(folder)
    out=folder/(name+".out")
    err=folder/(name+".err")
    cpu=min(os.sched_getaffinity(0))
    def setup():
        os.setsid()
        os.sched_setaffinity(0,{cpu})
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        if size_cap is not None:
            resource.setrlimit(resource.RLIMIT_FSIZE,(size_cap,size_cap))
    started=time.perf_counter()
    with out.open("wb") as f,err.open("wb") as e:
        child=subprocess.Popen([str(a) for a in command],
            stdout=f,stderr=e,preexec_fn=setup)
        timed_out=False
        try:child.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            timed_out=True
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait()
    result=dict(return_code=child.returncode,timed_out=timed_out,
                wall_s=round(time.perf_counter()-started,6),logical_CPU=cpu)
    for name,p in (("stdout_tail",out),("stderr_tail",err)):
        with p.open("rb") as f:
            f.seek(max(0,p.stat().st_size-2000))
            result[name]=f.read(2000).decode(errors="replace")
    return result

def status_of(r):
    text=r["stdout_tail"]+"\n"+r["stderr_tail"]
    if r["timed_out"]:return "TIMEOUT"
    if r["return_code"]==20 and "s UNSATISFIABLE" in text:return "UNSAT"
    if r["return_code"]==10 and "s SATISFIABLE" in text:return "SAT"
    return "UNKNOWN"

def checker_verified(r):
    output=r["stdout_tail"]+"\n"+r["stderr_tail"]
    return not r["timed_out"] and r["return_code"]==0 and any(
        t.strip()=="s VERIFIED UNSAT" for t in output.splitlines())

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(CMS.is_file() and CAKE.is_file(),"pinned CMS / CakeML executables absent")
    source_manifest()
    with tempfile.TemporaryDirectory(prefix="combo2proof-toy-") as folder:
        d=pathlib.Path(folder)
        unsat=d/"unsat.cnf"
        unsat.write_text("p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n")
        pr=d/"unsat.xlrupb"
        r=run([CMS,"--xlrup","2","-t","1","--verb","0",unsat,pr],
              25,d,"unsat_generator",8*1024*1024)
        need(status_of(r)=="UNSAT" and pr.is_file() and pr.stat().st_size>0,
             "toy UNSAT proof absent")
        ck=run([CAKE,unsat,pr],25,d,"unsat_checker")
        need(checker_verified(ck),"independent CakeML toy UNSAT rejected")
        sat=d/"sat.cnf"
        sat.write_text("p cnf 2 2\n1 2 0\n-1 2 0\n")
        sr=run([CMS,"--xlrup","2","-t","1","--verb","0",
                sat,d/"sat.xlrupb"],25,d,"sat_negative",8*1024*1024)
        need(status_of(sr)=="SAT" and not checker_verified(sr),
             "SAT negative control failed")
    print("COMBO2_PROOF_SELFTEST_PASS "+json.dumps(dict(
        toy_UNSAT_CakeML_XLRUP_verified=True,toy_SAT_not_UNSAT=True,
        exact_original_SHA_targets=list(TARGETS),
        CMS_commit=CMS_COMMIT,CakeML_commit=CAKE_COMMIT),sort_keys=True),flush=True)

def certify_one(sha,case):
    src=SOURCES/case["filename"]
    need(digest(src)==sha,"source SHA precheck failed")
    result=dict(source_sha256=sha,year=case["year"],gbd=case["gbd"],
       original_SHA256_checked=True,
       CMS_source_commit=CMS_COMMIT,CakeML_checker_commit=CAKE_COMMIT,
       single_logical_CPU=True,proof_format="binary XLRUP",
       proof_max_bytes=PROOF_BYTES_MAX,solve_wall_cap_s=SOLVE_CAP,
       checker_wall_cap_s=CHECKER_CAP,backend_status="UNKNOWN",
       independent_verified=False,certification_status="UNVERIFIED")
    with tempfile.TemporaryDirectory(prefix="combo2proof-original-") as folder:
        d=pathlib.Path(folder);pr=d/"original.xlrupb"
        r=run([CMS,"--xlrup","2","-t","1","--verb","0",src,pr],
            SOLVE_CAP,d,"cms_generator",PROOF_BYTES_MAX)
        result["cms_solve"]=r
        st=status_of(r);result["backend_status"]=st
        if st=="UNSAT" and pr.exists() and 0<pr.stat().st_size<=PROOF_BYTES_MAX:
            result["proof_bytes"]=pr.stat().st_size
            result["proof_sha256"]=digest(pr)
            ck=run([CAKE,src,pr],CHECKER_CAP,d,"CakeML_checker")
            result["CakeML_checker"]=ck
            if checker_verified(ck):
                result["independent_verified"]=True
                result["certification_status"]="CERTIFIED_ORIGINAL_UNSAT_BY_CMS_XLRUP_CAKEML"
            else:
                result["certification_status"]="UNVERIFIED_CHECKER_REJECTED_OR_TIMEOUT"
        elif r["return_code"]==-signal.SIGXFSZ:
            result["certification_status"]="UNVERIFIED_PROOF_SIZE_CAP"
        elif r["timed_out"]:
            result["certification_status"]="UNVERIFIED_SOLVER_TIMEOUT"
        elif st=="SAT":
            # Recheck the SAT model against every clause of original DIMACS.
            import sys
            sys.path.insert(0,str(pathlib.Path("research").resolve()))
            import drnas_equiv9_prospective_seed_holdout as e9
            n,clauses=e9.x22.read_cnf(src)
            out=(d/"cms_generator.out").read_text(errors="replace")
            satstatus,verified=e9.x22.solver_result("cms",10,out,clauses,{})
            need(satstatus=="SAT" and verified,
                 "ALARM: reported SAT but witness is not valid on original CNF")
            result["SAT_original_witness_verified"]=True
            result["certification_status"]="ALARM_ORIGINAL_SAT_WITNESS_CONTRADICTS_EARLIER_UNSAT"
        else:
            result["certification_status"]="UNVERIFIED_NO_COMPLETE_PROOF"
        # Don't upload proof bytes: keep proof hashes/sizes; avoid huge artifacts.
    need(digest(src)==sha,"source SHA changed after proof generation")
    save(ROOT/("proof_"+sha[:12]+".json"),result)
    print("COMBO2_PROOF_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    return result

def posthoc_rescore(results):
    """No benchmark trials rerun. Original COMBO2 report preserved unchanged.
    Recalculate whether previously unverified ORIGINAL-CNF UNSAT flags can
    count as verified *formula statuses* with independent external CMS proof.
    This is NOT a Native/Kissat/COMBO self-produced proof.
    """
    old=read(OLD)
    need(old["protocol"]=="DRNAS-COMBO2-MINPATH-SEARCH6-GF2-CMS17-KISSAT4-12SHA-7ARM-2REP-10S-v1"
         and old["sources"]==12 and old["trials"]==168,
         "original 168-trial report or protocol mismatch")
    need(set(TARGETS)<=set(old["per_SHA"]),"reported benchmark SHA mismatch")
    accepted={sha for sha,r in results.items() if r["independent_verified"]}
    before_agreed=set(old["backend_UNSAT_agreement"])
    prior_proofs=set(old["math_certified_originals"])
    updated={}
    for arm,v in old["scores"].items():
        new=dict(base_STRICT_PAR2_s=v["PAR2_s"],base_STRICT_solved=v["solved"])
        savings=0;newsolved=0;accepted_rows=[]
        for sha in accepted-(before_agreed|prior_proofs):
            arr=old["per_SHA"][sha][arm]
            need(len(arr)==2,"missing paired original SHA in prior report")
            for row in arr:
                if row["status"]=="UNSAT":
                    delta=2*10.0-row["E2E_s"]
                    savings+=delta;newsolved+=1
                    accepted_rows.append(dict(sha=sha,rep=row["rep"],
                         newly_certified_formula_UNSAT=True,original_solver_arm=arm,
                         recorded_E2E_s=row["E2E_s"]))
        new.update(newly_verified_original_UNSAT_attempts=newsolved,
                   posthoc_STRICT_solved=v["solved"]+newsolved,
                   posthoc_STRICT_PAR2_s=round(v["PAR2_s"]-savings,6),
                   savings_vs_unchanged_original_audit_s=round(savings,6),
                   new_accepted_rows=accepted_rows)
        updated[arm]=new
    for arm in updated:
        updated[arm]["posthoc_PAR2_ratio_vs_kissat_x"]=round(
            updated["kissat_plain"]["posthoc_STRICT_PAR2_s"]/
            updated[arm]["posthoc_STRICT_PAR2_s"],6)
    return dict(recalculation_type="POSTHOC_ONLY_NOT_REEXECUTED",
       original_benchmark="COMBO2 run 42793704014, 168 original E2E SHA-locked trials",
       original_benchmark_report_SHA256=digest(OLD),
       externally_certified_new_source_SHA=sorted(accepted),
       independent_certification_is_for_original_formula_status_not_native_solver_proof=True,
       do_not_replace_original_benchmark_report=True,
       scores=updated)

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(CMS.is_file() and CAKE.is_file(),"required pinned proof tooling absent")
    cases=source_manifest()
    results={}
    for target in TARGETS:
        results[target]=certify_one(target,cases[target])
    rescore=posthoc_rescore(results)
    final=dict(protocol=PROTO,
      two_original_SHA=list(TARGETS),
      source_originals_verified=2,
      independent_XLRUP_CakeML_verified_count=sum(v["independent_verified"]
                                                       for v in results.values()),
      certificates=results,posthoc_PAR2=rescore,
      no_automatic_promotion=True,
      proof_generator_is_CryptoMiniSat_not_DRNAS_Native=True,
      no_LRAT_claim_for_original_COMBO2_solver_runs=True)
    save(ROOT/"report.json",final)
    print("COMBO2_PROOF_FINAL "+json.dumps(dict(
        protocol=PROTO,
        confirmed=sum(v["independent_verified"] for v in results.values()),
        source_status={sha:r["certification_status"] for sha,r in results.items()},
        posthoc_PAR2_by_arm={a:dict(solved=v["posthoc_STRICT_solved"],
            PAR2_s=v["posthoc_STRICT_PAR2_s"],
            ratio_vs_kissat_x=v["posthoc_PAR2_ratio_vs_kissat_x"])
            for a,v in rescore["scores"].items()},
        no_automatic_promotion=True),sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","certify"))
    a=p.parse_args()
    if a.action=="selftest":selftest()
    else:main()
