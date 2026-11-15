#!/usr/bin/env python3
"""Frozen AUTO-UNSAT standalone DRUP/LRAT producer proof audit.

No SAT solver or DRAT-to-LRAT converter is used in this workflow.
The prover generates an actual DRUP and direct LRAT file; independent
drat-trim and upstream lrat-check only VERIFY the outputs against the
original untouched CNF.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import time

from benchmark_auto_unsat import make_synthetic, original_sources
from random_unsat_probe import write_cnf, satisfied
from standalone_lrat import produce
from strict_rup_lrat import check as strict_lrat_check, InvalidLRAT

def check(command,seconds):
    try:
        p=subprocess.run([str(x) for x in command],capture_output=True,text=True,
                         timeout=seconds)
        return p.returncode,p.stdout+"\n"+p.stderr
    except (OSError,subprocess.TimeoutExpired) as e:
        return None,str(e)

def independent_checks(cnf,drat,lrat,drat_trim,lrat_check,seconds):
    assert cnf.is_file() and drat.is_file() and lrat.is_file()
    rc1,raw1=check([drat_trim,cnf,drat],seconds)
    rc2,raw2=check([lrat_check,cnf,lrat],seconds)
    ok1=rc1==0 and "VERIFIED" in raw1 and "NOT VERIFIED" not in raw1
    ok2=rc2==0 and "c VERIFIED" in raw2 and "NOT VERIFIED" not in raw2
    try:
        strict_lrat_check(cnf.read_bytes(),lrat.read_bytes())
        ok3=True
        detail3="STRICT_RUP_LRAT_VERIFIED"
    except (InvalidLRAT,ValueError,UnicodeDecodeError) as exc:
        ok3=False
        detail3="INVALID_STRICT_RUP_LRAT: "+str(exc)
    return ok1,ok2,ok3,raw1[-300:],raw2[-300:],detail3

def run(args):
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        assert len(os.sched_getaffinity(0))==1
    args.out.mkdir(parents=True,exist_ok=False)
    baseline=args.base.resolve()
    orig=original_sources(args.pcmax20,args.unseen3)
    frozen=[json.loads(x) for x in (baseline/"trials.jsonl").read_text().splitlines() if x]
    assert len(frozen)==153
    labels={x["name"]:x for x in frozen}
    synthetic=make_synthetic(random.Random(79117))
    path= args.out/"inputs"
    path.mkdir()
    mapped={}
    for e in synthetic:
        cnf=path/(e["name"]+".cnf")
        write_cnf(cnf,e["clauses"],e["nvars"])
        mapped[e["name"]]=cnf
        if e["expected"]=="SAT" and e["model"] is not None:
            assert satisfied(e["clauses"],e["model"])
    for i,(cnf,sha) in enumerate(orig):
        mapped[f"original_{i:02d}"]=cnf
        assert hashlib.sha256(cnf.read_bytes()).hexdigest()==sha
    assert set(labels)==set(mapped)
    rows=[]
    attempted=0
    for idx,prior in enumerate(frozen):
        name=prior["name"]
        cnf=mapped[name]
        assert hashlib.sha256(cnf.read_bytes()).hexdigest()==prior["source_sha256"],name
        row={"name":name,"dataset":prior["dataset"],"family":prior["family"],
             "expected":prior["expected"],"method":prior["method"],
             "structural_verified":prior["structural_verified"],
             "standalone_generated":False,"drat_verified":False,
             "lrat_verified":False,"proof_steps":0,"proof_nodes":0,
             "mode":"none","reason":"no verified source proof","proof_s":0.0}
        if prior["structural_verified"]:
            attempted+=1
            folder=baseline/"proofs"/name
            cert=folder/"certificate.json"
            assert cert.is_file(),("missing independent structural cert",name)
            existing=(folder/"proof.drat") if prior["drat_verified"] else None
            proof_out=args.out/"proofs"/name
            budget=(args.original_budget_s if prior["dataset"]=="original_SAT2024"
                    else args.synthetic_budget_s)
            produced=produce(cnf,cert,proof_out,budget_s=budget,
                             nodes=args.max_nodes,existing_drup=existing,
                             max_core_clauses=args.max_core_clauses)
            row["proof_s"]=produced["generator_s"]
            row["reason"]=produced.get("reason",produced["status"])
            row["mode"]=produced.get("mode","none")
            row["proof_nodes"]=produced["nodes"]
            row["proof_steps"]=produced["proof_steps"]
            row["standalone_generated"]=produced["standalone_lrat"]
            if produced["standalone_lrat"]:
                assert produced["source_sha256"]==prior["source_sha256"]
                drat=proof_out/"proof.drat"
                lrat=proof_out/"proof.lrat"
                ok_drat,ok_lrat,ok_strict,detail1,detail2,detail3=independent_checks(
                    cnf,drat,lrat,args.drat_trim,args.lrat_check,args.checker_s)
                row["drat_verified"]=ok_drat
                row["lrat_verified"]=ok_drat and ok_lrat and ok_strict
                if not (ok_drat and ok_lrat and ok_strict):
                    row["reason"]="checker_rejected:"+detail1[-200:]+":"+detail2[-200:]+":"+detail3[-200:]
                else:
                    row["reason"]="DIRECT_DRUP_AND_LRAT_ORIGINAL_VERIFIED"
                    row["proof_sha256"]=hashlib.sha256(lrat.read_bytes()).hexdigest()
                    # Reject a forged LRAT reference on a genuine source.
                    if row["proof_steps"]>0 and idx%14==0:
                        lines=lrat.read_text().splitlines()
                        one=lines[0].split()
                        # Changed last positive hint to an invalid clause number.
                        if len(one)>=4:
                            one[-2]=str(10**9)
                            forgery=args.out/"forgery"
                            forgery.mkdir(exist_ok=True)
                            fake=forgery/(name+".lrat")
                            fake.write_text(" ".join(one)+"\n"+"\n".join(lines[1:])+"\n")
                            code,out=check([args.lrat_check,cnf,fake],args.checker_s)
                            assert not (code==0 and "c VERIFIED" in out and "NOT VERIFIED" not in out),name
                if prior["expected"]=="SAT" and (ok_drat or ok_lrat or ok_strict):
                    raise AssertionError(("false UNSAT on SAT",name))
        rows.append(row)
        with (args.out/"trials.jsonl").open("a") as f:
            f.write(json.dumps(row,sort_keys=True)+"\n")
        print("STANDALONE_TRIAL "+json.dumps({k:row[k] for k in
            ("name","dataset","expected","method","standalone_generated",
             "drat_verified","lrat_verified","proof_steps","proof_s","reason")},
            sort_keys=True),flush=True)
    # Independent checker must refuse a fake refutation of satisfiable CNF.
    sat=args.out/"sat_control.cnf"
    sat.write_text("p cnf 1 1\n1 0\n")
    fake_drat=args.out/"fake.drat"
    fake_lrat=args.out/"fake.lrat"
    fake_drat.write_text("0\n")
    fake_lrat.write_text("2 0 1 0\n")
    rc1,output1=check([args.drat_trim,sat,fake_drat],4)
    rc2,output2=check([args.lrat_check,sat,fake_lrat],4)
    assert rc1!=0 or "VERIFIED" not in output1 or "NOT VERIFIED" in output1
    try:
        strict_lrat_check(sat.read_bytes(),fake_lrat.read_bytes())
    except InvalidLRAT:
        strict_rejected=True
    else:
        strict_rejected=False
    assert strict_rejected, "independent LRAT RUP verifier accepted SAT"
    assert not (rc1==0 and "VERIFIED" in output1 and rc2==0
                and "c VERIFIED" in output2 and not strict_rejected), "combined checkers accepted SAT"
    cohorts={}
    families=collections.defaultdict(lambda:{"source_verified":0,"drat_verified":0,
                                              "lrat_verified":0,"generated":0})
    for cohort in ("synthetic","original_SAT2024"):
        rr=[x for x in rows if x["dataset"]==cohort]
        cohorts[cohort]={
            "sources":len(rr),
            "labelled_unsat":sum(x["expected"]=="UNSAT" for x in rr),
            "labelled_sat":sum(x["expected"]=="SAT" for x in rr),
            "previously_structural":sum(x["structural_verified"] for x in rr),
            "standalone_generated":sum(x["standalone_generated"] for x in rr),
            "standard_drat_verified":sum(x["drat_verified"] for x in rr),
            "direct_lrat_verified":sum(x["lrat_verified"] for x in rr),
            "from_rup_proof":sum(x["lrat_verified"] and x["mode"]=="direct_lrat_from_existing_rup" for x in rr),
            "new_no_solver_search":sum(x["lrat_verified"] and x["mode"]=="source_core_proof_producing_dpll" for x in rr),
            "false_unsat":sum(x["expected"]=="SAT" and x["lrat_verified"] for x in rr)
        }
        for x in rr:
            row=families[cohort+"/"+x["method"]]
            row["source_verified"]+=x["structural_verified"]
            row["generated"]+=x["standalone_generated"]
            row["drat_verified"]+=x["drat_verified"]
            row["lrat_verified"]+=x["lrat_verified"]
    summary={
        "status":"COMPLETE","protocol":"DRNAS-STANDALONE-DRAT-LRAT-1",
        "source_count":len(rows),"single_logical_cpu":True,
        "backend_sat_solvers_used":0,
        "standalone_proof_emitter":True,
        "drat_to_lrat_converter_used":False,
        "checkers":["drat-trim","lrat-check"],
        "results":cohorts,"methods":dict(families),
        "negative_controls_pass":True,
        "false_unsat":sum(x["expected"]=="SAT" and x["lrat_verified"] for x in rows)}
    assert len(rows)==153 and attempted==113 and summary["false_unsat"]==0
    (args.out/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("STANDALONE_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base",type=Path,required=True)
    parser.add_argument("--pcmax20",type=Path,required=True)
    parser.add_argument("--unseen3",type=Path,required=True)
    parser.add_argument("--drat-trim",type=Path,required=True)
    parser.add_argument("--lrat-check",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--checker-s",type=int,default=12)
    parser.add_argument("--synthetic-budget-s",type=float,default=2.0)
    parser.add_argument("--original-budget-s",type=float,default=7.0)
    parser.add_argument("--max-nodes",type=int,default=5000)
    parser.add_argument("--max-core-clauses",type=int,default=14000)
    args=parser.parse_args()
    args.drat_trim=args.drat_trim.resolve()
    args.lrat_check=args.lrat_check.resolve()
    run(args)
if __name__=="__main__":main()
