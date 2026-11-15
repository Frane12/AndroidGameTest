#!/usr/bin/env python3
"""Experimental structural-to-DRAT/LRAT bridge for AUTO-UNSAT1.

Only report standard success if BOTH:
1. DRAT-trim verifies a proof against the BYTE-EXACT ORIGINAL CNF.
2. Independently compiled upstream LRAT-check verifies derived LRAT against
   the same byte-exact original CNF.
The source-derived sub-CNF is a proof-search hint, never evidence by itself.
A subformula DRAT proof might use RAT steps invalid in the full CNF; reject it.
All formula evaluations are single-core, sequential, and bounded.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

from check_capacity import parse_cnf, check as check_capacity
from check_clause_hall import check as check_hall
from check_hall3_hybrid import verify as check_hall3
from check_mixed_unsat import verify as check_mixed
from benchmark_auto_unsat import original_sources

CHECKERS={
    "pcmax-capacity-v1":check_capacity,
    "pcmax-clause-hall-v1":check_hall,
    "pcmax-hall3-hybrid-v1":check_hall3,
    "drnas-mixed-unsat1":check_mixed,
}
def bounded(command,seconds=12,max_output=2200):
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(48*1024*1024,48*1024*1024))
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    try:
        p=subprocess.run(list(map(str,command)),capture_output=True,text=True,
                         timeout=seconds,preexec_fn=limits)
        return p.returncode,(p.stdout+"\n"+p.stderr)[-max_output:],"completed"
    except subprocess.TimeoutExpired:
        return None,"process timeout","timeout"
    except (OSError,ValueError) as e:
        return None,repr(e),"exception"

def lrat_has_empty_clause(path):
    if not path.is_file() or path.stat().st_size>48*1024*1024:return False
    with path.open() as fd:
        for raw in fd:
            parts=raw.split()
            if len(parts)>=4 and parts[0].isdigit() and parts[1]=="0" and parts[-1]=="0":
                return True
    return False

def checked_standard(original,drat,lrat,drat_trim,lrat_check,seconds=12):
    if not drat.is_file() or not drat.stat().st_size:return False,"proof_missing"
    if drat.stat().st_size>48*1024*1024:return False,"proof_size_limit"
    if lrat.exists():lrat.unlink()
    code,output,status=bounded([drat_trim,original,drat,"-L",lrat],seconds)
    if code!=0 or "VERIFIED" not in output or "NOT VERIFIED" in output:
        return False,"drat_failed:"+status+":"+output[-300:]
    if not lrat_has_empty_clause(lrat):
        return False,"lrat_empty_clause_missing"
    code,out,status=bounded([lrat_check,original,lrat],seconds)
    if code!=0 or "c VERIFIED" not in out or "NOT VERIFIED" in out:
        return False,"lrat_failed:"+status+":"+out[-300:]
    return True,"DRAT_and_LRAT_independently_checked"

def extract_core(raw,proof):
    """Return subset of literal-identical original input clauses.

    Every certificate is first rechecked from raw original CNF.
    This extraction never adds a strengthening fact: the only clauses
    in the subset must appear byte-for-byte in the original clause set.
    """
    fmt=proof.get("format")
    if fmt not in CHECKERS:raise ValueError("unsupported source proof")
    result=CHECKERS[fmt](raw,proof)
    if "VERIFIED" not in result["status"]:raise ValueError("independent structural verifier rejected")
    nvars,source=parse_cnf(raw)
    core=set()
    if fmt=="drnas-mixed-unsat1":
        # Not needed: mixed producers already emit direct DRUP.
        return nvars,core
    if fmt=="pcmax-clause-hall-v1":
        core.update(frozenset(g) for g in proof["alo_groups"])
        for resource in proof["resource_cliques"]:
            for i,a in enumerate(resource):
                for b in resource[:i]:core.add(frozenset((-a,-b)))
    else:
        if fmt=="pcmax-capacity-v1":
            groups=proof["selected_groups"]
            machines=proof["machines"]
            cliques=[]
        else:
            groups=proof["selected_groups"]
            machines=proof["machines"]
            cliques=proof["resource_cliques"]
        core.update(frozenset(g) for g in groups)
        for resource in cliques:
            for i,a in enumerate(resource):
                for b in resource[:i]:core.add(frozenset((-a,-b)))
        for machine in machines:
            core.update({frozenset((machine["root"],)),
                         frozenset((machine["true_terminal"],)),
                         frozenset((-machine["false_terminal"],))})
            for p,x,lo,hi in machine["transitions"]:
                core.add(frozenset((-p,x,lo)))
                core.add(frozenset((-p,-x,hi)))
    if not core or not core.issubset(source):
        raise ValueError("source-core extraction attempted unknown clauses")
    return nvars,core

def write_core(path,nvars,clauses):
    lines=[f"p cnf {nvars} {len(clauses)}"]
    for clause in sorted(clauses,key=lambda x:(len(x),tuple(sorted(x)))):
        lines.append(" ".join(str(x) for x in sorted(clause,key=lambda v:(abs(v),v)))+" 0")
    path.write_text("\n".join(lines)+"\n")

def record_path(row,base,originals):
    if row["dataset"]=="synthetic":return base/"inputs"/(row["name"]+".cnf")
    assert row["dataset"]=="original_SAT2024"
    idx=int(row["name"].split("_")[-1])
    return originals[idx][0]

def audit(args):
    root=args.base.resolve()
    rows=[json.loads(l) for l in (root/"trials.jsonl").read_text().splitlines() if l]
    assert len(rows)==153
    originals=original_sources(args.pcmax20,args.unseen3)
    args.out.mkdir(parents=True,exist_ok=False)
    checked=[]
    for index,row in enumerate(rows):
        src=record_path(row,root,originals)
        raw=src.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==row["source_sha256"],row["name"]
        work=root/"proofs"/row["name"]
        out=args.out/"cases"/row["name"]
        out.mkdir(parents=True,exist_ok=False)
        result={"name":row["name"],"dataset":row["dataset"],
                "family":row["family"],"expected":row["expected"],
                "source_sha256":row["source_sha256"],
                "structural_verified":bool(row["structural_verified"]),
                "existing_drat_verified":bool(row["drat_verified"]),
                "new_drat_verified":False,"lrat_verified":False,
                "bridge_reason":"not_applicable","core_clauses":0,
                "bridge_wall_s":0.0}
        start=time.perf_counter()
        drat=work/"proof.drat"
        if row["drat_verified"]:
            good,why=checked_standard(src,drat,out/"proof.lrat",
                  args.drat_trim,args.lrat_check,args.checker_s)
            result["lrat_verified"]=good
            result["bridge_reason"]="existing_drat_to_lrat:"+why
        elif row["structural_verified"]:
            cert_path=work/"certificate.json"
            if not cert_path.is_file():
                raise AssertionError("structural accepted without certificate")
            proof=json.loads(cert_path.read_text())
            if proof.get("source_sha256")!=row["source_sha256"]:
                raise AssertionError("certificate SHA mismatch")
            fmt=proof.get("format")
            if fmt in CHECKERS:
                # Mandatory recheck certificate even if we cannot extract a core.
                nvars,core=extract_core(raw,proof)
                result["core_clauses"]=len(core)
                if len(core)>0 and len(core)<=args.max_core_clauses:
                    core_file=out/"core.cnf"
                    write_core(core_file,nvars,core)
                    proof_file=out/"core_proof.drat"
                    timeout=(args.original_solver_s if row["dataset"]=="original_SAT2024"
                             else args.synthetic_solver_s)
                    rc,output,status=bounded([args.kissat,core_file,proof_file],timeout)
                    result["core_solver_exit_code"]=rc
                    result["core_solver_diagnostic"]=output[-220:]
                    if rc==20 and proof_file.is_file():
                        good,why=checked_standard(src,proof_file,out/"proof.lrat",
                                  args.drat_trim,args.lrat_check,args.checker_s)
                        result["new_drat_verified"]=good
                        result["lrat_verified"]=good
                        result["bridge_reason"]="extracted_source_core:"+why
                    else:
                        result["bridge_reason"]="core_solver_"+status
                else:result["bridge_reason"]="core_empty_or_size_gate"
            else:result["bridge_reason"]="unsupported_structural_proof"
        result["bridge_wall_s"]=round(time.perf_counter()-start,6)
        if row["expected"]=="SAT":
            assert not result["new_drat_verified"] and not result["lrat_verified"],("FALSE_UNSAT",row)
        if result["new_drat_verified"] or result["lrat_verified"]:
            result["proof_sha256"]=hashlib.sha256((out/"proof.lrat").read_bytes()).hexdigest()
        checked.append(result)
        with (args.out/"trials.jsonl").open("a") as stream:
            stream.write(json.dumps(result,sort_keys=True)+"\n")
        print("STANDARD_TRIAL "+json.dumps({k:result[k] for k in (
            "name","dataset","expected","core_clauses",
            "existing_drat_verified","new_drat_verified","lrat_verified",
            "bridge_reason","bridge_wall_s")},sort_keys=True),flush=True)
    # Explicit SAT negative control is independent of original source metadata.
    sat=args.out/"sat_negative.cnf"
    sat.write_text("p cnf 1 1\n1 0\n")
    fake=args.out/"forged.drat"
    fake.write_text("0\n")
    accepted,_=checked_standard(sat,fake,args.out/"forged.lrat",args.drat_trim,args.lrat_check,3)
    assert not accepted,"standard proof bridge falsely certified SAT"
    # A syntactically plausible LRAT proof without the empty clause is invalid.
    invalid=args.out/"invalid.lrat"
    invalid.write_text("2 1 0 1 0\n")
    code,msg,reason=bounded([args.lrat_check,sat,invalid],3)
    assert not (code==0 and "c VERIFIED" in msg and "NOT VERIFIED" not in msg)
    counts={}
    for cohort in ("synthetic","original_SAT2024"):
        rs=[r for r in checked if r["dataset"]==cohort]
        counts[cohort]={
            "sources":len(rs),
            "expected_unsat":sum(r["expected"]=="UNSAT" for r in rs),
            "structural_verified":sum(r["structural_verified"] for r in rs),
            "previous_drat_verified":sum(r["existing_drat_verified"] for r in rs),
            "new_drat_verified":sum(r["new_drat_verified"] for r in rs),
            "total_lrat_verified":sum(r["lrat_verified"] for r in rs),
            "sat_false_positives":sum(r["expected"]=="SAT" and r["lrat_verified"] for r in rs)
        }
    summary={"status":"COMPLETE","protocol":"AUTO-UNSAT-DRAT-LRAT1",
        "original_cnf_certification":True,"independent_lrat_check":True,
        "source_disjoint_mixed_family_generalization_not_yet_proven":True,
        "results":counts,"total_sources":len(checked),
        "negative_controls_pass":True,
        "false_unsat":sum(r["expected"]=="SAT" and r["lrat_verified"] for r in checked)}
    assert summary["false_unsat"]==0
    (args.out/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("STANDARD_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--base",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--pcmax20",type=Path,required=True)
    p.add_argument("--unseen3",type=Path,required=True)
    p.add_argument("--kissat",type=Path,required=True)
    p.add_argument("--drat-trim",type=Path,required=True)
    p.add_argument("--lrat-check",type=Path,required=True)
    p.add_argument("--checker-s",type=int,default=15)
    p.add_argument("--synthetic-solver-s",type=float,default=1.0)
    p.add_argument("--original-solver-s",type=float,default=3.0)
    p.add_argument("--max-core-clauses",type=int,default=30000)
    args=p.parse_args()
    assert args.checker_s>=1 and args.synthetic_solver_s>0 and args.original_solver_s>0
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        assert len(os.sched_getaffinity(0))==1
    args.kissat=args.kissat.resolve()
    args.drat_trim=args.drat_trim.resolve()
    args.lrat_check=args.lrat_check.resolve()
    audit(args)
if __name__=="__main__":main()
