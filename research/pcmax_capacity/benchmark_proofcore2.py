#!/usr/bin/env python3
"""UNSAT PROOFCORE2: original-SAT2024 source proof coverage + native DRNAS core-CDCL DRAT/LRAT.

No external SAT solver is used. DRAT-trim and upstream lrat-check act only as
INDEPENDENT proof checkers. Structural proof is separately validated against
the original CNF. A core DRAT proof is accepted ONLY if checked against the
complete, unmodified original CNF (sub-CNF RAT can be invalid on a superset).
One logical CPU, sequential methods, bounded resources. All failed
standard-proof attempts stay UNKNOWN_STANDARD, not certified.
"""
import argparse, collections, hashlib, json, os, pathlib, resource
import subprocess, sys, time, statistics, gzip

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark_auto_unsat import original_sources
from bridge_standard import CHECKERS, extract_core, write_core, checked_standard

STAGES=(("CAPACITY","--pcmax-capacity",650),
        ("HALL2","--pcmax-hall2",650),
        ("HALL3","--pcmax-hall3",650),
        ("CLAUSE_HALL","--pcmax-clause-guard",350))

def bounded(command,timeout_s=8,size_mb=48):
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(size_mb*1024**2,size_mb*1024**2))
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    started=time.perf_counter()
    try:
        p=subprocess.run([str(a) for a in command],capture_output=True,
                         text=True,timeout=timeout_s,preexec_fn=limits)
        return p.returncode,p.stdout[-2000:],p.stderr[-1000:],round(time.perf_counter()-started,6)
    except subprocess.TimeoutExpired:
        return None,"","TIME_LIMIT",round(time.perf_counter()-started,6)
    except (OSError,ValueError) as exc:
        return None,"",repr(exc),round(time.perf_counter()-started,6)

def independent_source(raw,proof):
    fmt=proof.get("format")
    if fmt not in CHECKERS:return None
    checked=CHECKERS[fmt](raw,proof)
    if "VERIFIED" not in checked["status"]:
        raise AssertionError(("NOT_SOURCE_VERIFIED",fmt,checked))
    return fmt

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pcmax20",type=pathlib.Path,required=True)
    ap.add_argument("--unseen3",type=pathlib.Path,required=True)
    ap.add_argument("--prior",type=pathlib.Path,required=True)
    ap.add_argument("--native",type=pathlib.Path,required=True)
    ap.add_argument("--base",type=pathlib.Path,required=True)
    ap.add_argument("--drat-trim",type=pathlib.Path,required=True)
    ap.add_argument("--lrat-check",type=pathlib.Path,required=True)
    ap.add_argument("--output",type=pathlib.Path,required=True)
    ap.add_argument("--solver-cap",type=float,default=8.0)
    ap.add_argument("--checker-cap",type=float,default=12.0)
    args=ap.parse_args()
    assert 1<=args.solver_cap<=30 and 1<=args.checker_cap<=60
    if hasattr(os,"sched_setaffinity"):
        allowed=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(allowed)})
        assert len(os.sched_getaffinity(0))==1
    args.native=args.native.resolve()
    args.base=args.base.resolve()
    args.drat_trim=args.drat_trim.resolve()
    args.lrat_check=args.lrat_check.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    srcs=original_sources(args.pcmax20,args.unseen3)
    assert len(srcs)==18
    prior_rows=[json.loads(s) for s in (args.prior/"trials.jsonl").read_text().splitlines() if s]
    old={r["name"]:r for r in prior_rows if r.get("dataset")=="original_SAT2024"}
    assert len(old)==18
    output=[]
    for i,(src,sha) in enumerate(srcs):
        name=f"original_{i:02d}"
        raw=src.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==sha==old[name]["source_sha256"]
        label=old[name]["expected"]
        assert label in ("SAT","UNSAT")
        folder=args.output/name
        folder.mkdir()
        row={"id":i,"name":src.name,"source_sha256":sha,"label_from_manifest":label,
             "prior_structural":bool(old[name]["structural_verified"]),
             "source_certified":False,"new_source_certificate":False,
             "standard_drat_verified":False,"standard_lrat_verified":False,
             "method":None,"reason":"no_source_proof","source_arms":[]}
        certificate=None
        if row["prior_structural"]:
            path=args.prior/"proofs"/name/"certificate.json"
            assert path.is_file(),("MISSING_FROZEN_CERT",name)
            certificate=json.loads(path.read_text())
            fmt=independent_source(raw,certificate)
            assert fmt==old[name]["method"],(fmt,old[name]["method"])
            row["source_certified"]=True
            row["method"]=fmt
            row["reason"]="frozen_source_certificate_rechecked"
        # Try complementary methods only for source gaps, including SAT controls.
        else:
            for stage,flag,budget in STAGES:
                proof_path=folder/(stage.lower()+".json")
                cmd=[args.native,src.resolve(),"--mode","core","--time","1.5",
                     "--pcmax-only",flag,"--pcmax-budget-ms",budget,
                     "--pcmax-certificate",proof_path.resolve()]
                rc,out,err,t=bounded(cmd,timeout_s=3)
                log={"method":stage,"exit_code":rc,"seconds":t,
                     "status":"UNKNOWN"}
                if rc==20:
                    assert proof_path.is_file(),("UNSAT_MISSING_CERT",name,stage)
                    proposal=json.loads(proof_path.read_text())
                    fmt=independent_source(raw,proposal)
                    assert fmt is not None,("UNSUPPORTED_CERT",name,stage)
                    assert label!="SAT",("FALSE_UNSAT_ON_CATALOG_SAT",name,stage)
                    certificate=proposal
                    row.update(source_certified=True,new_source_certificate=True,
                               method=fmt,reason="new_original_source_certificate")
                    log["status"]="UNSAT_SOURCE_INDEPENDENTLY_VERIFIED"
                    row["source_arms"].append(log)
                    break
                assert rc==0 and not proof_path.exists(),("INCORRECT_UNKNOWN",name,stage,rc,err)
                row["source_arms"].append(log)
        if certificate is not None:
            (folder/"source_certificate.json").write_text(json.dumps(certificate,sort_keys=True)+"\n")
            nvars,core=extract_core(raw,certificate)
            row["core_clauses"]=len(core)
            # Use exactly original source clauses. No fabricated strengthening.
            if 0<len(core)<=24000:
                core_file=folder/"original_subset.cnf"
                write_core(core_file,nvars,core)
                proof_file=folder/"drnas_core.drat"
                rc,out,err,elapsed=bounded([args.base,core_file,
                                            "--mode","core",
                                            "--time",str(args.solver_cap),
                                            "--proof",proof_file],
                                            timeout_s=args.solver_cap+2)
                row.update(core_cdcl_status=rc,core_cdcl_wall_s=elapsed)
                assert rc!=10,("NATIVE_CDCL_FALSE_SAT_ON_SOURCE_PROVEN_UNSAT_CORE",name)
                if rc==20 and proof_file.is_file() and proof_file.stat().st_size>0:
                    good,detail=checked_standard(src,proof_file,folder/"proof.lrat",
                         args.drat_trim,args.lrat_check,args.checker_cap)
                    row["standard_drat_verified"]=bool(good)
                    row["standard_lrat_verified"]=bool(good)
                    row["reason"]="ORIGINAL_DRAT_AND_LRAT_VERIFIED" if good else "proof_check_rejected"
                    row["proof_check_diagnostic"]=detail[:240]
                    if good:
                        # Independent strict LRAT source check, no producer trust.
                        strict_cmd=[sys.executable,ROOT/"research/pcmax_capacity/strict_rup_lrat.py",
                                    src,folder/"proof.lrat"]
                        strict_rc,strict_out,strict_err,strict_s=bounded(strict_cmd,
                             timeout_s=args.checker_cap,size_mb=48)
                        row["strict_lrat_verified"]=strict_rc==0
                        row["strict_check_s"]=strict_s
                        if strict_rc!=0:
                            row["standard_lrat_verified"]=False
                            row["standard_drat_verified"]=False
                            row["reason"]="strict_RUP_LRAT_rejected_or_timeout"
                        if row["standard_lrat_verified"]:
                            for f in (proof_file,folder/"proof.lrat"):
                                row[f.name+"_sha256"]=hashlib.sha256(f.read_bytes()).hexdigest()
                                with f.open("rb") as fd, gzip.open(str(f)+".gz","wb",compresslevel=9) as gz:
                                    for chunk in iter(lambda:fd.read(1024*1024),b""):gz.write(chunk)
                                f.unlink()
                else:
                    row["reason"]="core_cdcl_unfinished"
                if proof_file.exists():proof_file.unlink() # no unverified massive files
                if (folder/"proof.lrat").exists() and not row["standard_lrat_verified"]:
                    (folder/"proof.lrat").unlink()
            else:
                row["reason"]="core_empty_or_size_limit"
        assert not (label=="SAT" and (row["source_certified"] or row["standard_lrat_verified"])),("FALSE_UNSAT",name)
        output.append(row)
        with (args.output/"trials.jsonl").open("a") as f:
            f.write(json.dumps(row,sort_keys=True)+"\n")
        print("PROOFCORE_TRIAL "+json.dumps({k:row.get(k) for k in
            ("id","name","label_from_manifest","prior_structural","new_source_certificate",
             "source_certified","core_clauses","core_cdcl_status","standard_lrat_verified","reason")},
            sort_keys=True),flush=True)
    # Forged DRAT on SAT must never be accepted by the external checkers.
    sat_control=args.output/"sat_negative_control.cnf"
    sat_control.write_text("p cnf 1 1\n1 0\n")
    invalid=args.output/"forged_empty.drat"
    invalid.write_text("0\n")
    fake_ok,why=checked_standard(sat_control,invalid,args.output/"forged.lrat",
                                 args.drat_trim,args.lrat_check,3)
    assert not fake_ok,("FALSE_UNSAT_FORGED_DRAT_ACCEPTED",why)
    counts={"sources":len(output),"catalog_unsat":sum(x["label_from_manifest"]=="UNSAT" for x in output),
            "catalog_sat":sum(x["label_from_manifest"]=="SAT" for x in output),
            "baseline_structural":sum(x["prior_structural"] for x in output),
            "new_structural":sum(x["new_source_certificate"] for x in output),
            "total_source_certified":sum(x["source_certified"] for x in output),
            "standard_lrat_verified":sum(x["standard_lrat_verified"] for x in output),
            "false_unsat":sum(x["label_from_manifest"]=="SAT" and x["source_certified"] for x in output)}
    assert counts["sources"]==18 and counts["baseline_structural"]==8 and counts["false_unsat"]==0
    result={"protocol":"DRNAS-UNSAT-PROOFCORE2-ORIGINAL18-20261115",
            "single_logical_cpu":True,"main_unchanged":True,
            "inequality_guard_off":True,"only_original_source_clauses":True,
            "standard_requires_original_drat_and_lrat_and_strict_check":True,
            "not_a_blind_new_dataset":True,"baseline_original_lrat":0,
            "solver_cap_s":args.solver_cap,"checker_cap_s":args.checker_cap,
            "summary":counts,"rows":output}
    (args.output/"summary.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("PROOFCORE_FINAL "+json.dumps(counts,sort_keys=True),flush=True)

if __name__=="__main__":main()
