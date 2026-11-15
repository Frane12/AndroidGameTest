#!/usr/bin/env python3
"""Frozen AUTO-UNSAT1 coverage audit, including original CNFs and SAT controls.

This test measures proof coverage, NOT a general solver PAR2 benchmark.
Original labels are catalog metadata; only independently checked proofs count.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import sys

from auto_unsat import run_one, check_drat
from random_unsat_probe import (cases,SEED,write_cnf,satisfied,
                                random_3sat_unsat,xor_parity_conflict,unsat_2sat)
from test_hall3_hybrid import instance

def make_synthetic(rng):
    examples=cases(random.Random(SEED))
    assert len(examples)==116
    for e in examples:
        if e["expected"]=="SAT":
            assert satisfied(e["clauses"],e["model"])
    hybrid=[("hybrid_unsat_n4",instance(4),"UNSAT"),
            ("hybrid_sat_n2",instance(2),"SAT"),
            ("hybrid_sat_n4_no_mutex",instance(4,mutex=False),"SAT")]
    hybrid.extend((f"hybrid_unsat_permutation_{i}",instance(4,scramble=i),"UNSAT")
                  for i in range(10))
    for name,clauses,label in hybrid:
        examples.append(dict(name=name,family="hybrid_hall3",
                             expected=label,clauses=clauses,
                             nvars=max(abs(l) for c in clauses for l in c),model=None))
    # Out-of-distribution variable names, including >256 header variables.
    # No training on these inputs. Source-only proofs remain exact.
    for kind,fn in [("2sat",unsat_2sat),("xor",xor_parity_conflict),
                    ("3sat",random_3sat_unsat)]:
        for shift in (300,4000):
            clauses,n,_=fn(rng)
            renamed=[tuple((abs(l)+shift)*(1 if l>0 else -1) for l in c)
                     for c in clauses]
            examples.append(dict(name=f"highvar_{kind}_{shift}",
                                 family="highvar_"+kind,expected="UNSAT",
                                 clauses=renamed,nvars=shift+n,model=None))
    return examples

def original_sources(pcmax20,unseen3):
    records=json.loads((pcmax20/"report.json").read_text())["results"]
    manifest=unseen3/"source_manifest.json"
    if not manifest.is_file():manifest=unseen3.parent/"source_manifest.json"
    three=json.loads(manifest.read_text())
    result=[]
    for e in records:
        if e.get("status")=="OK":
            path=pcmax20/Path(e["path"]).name
            result.append((path,e["sha256"]))
    for e in three:
        result.append((unseen3/e["name"].removesuffix(".xz"),e["sha256"]))
    assert len(result)==18,len(result)
    for path,digest in result:
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest,(path,digest)
    assert len({sha for _,sha in result})==18
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--drat-trim",type=Path,required=True)
    p.add_argument("--pcmax20",type=Path,required=True)
    p.add_argument("--unseen3",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--budget-ms",type=int,default=1500)
    args=p.parse_args()
    if hasattr(os,"sched_setaffinity"):
        cpu=min(os.sched_getaffinity(0))
        os.sched_setaffinity(0,{cpu})
        assert len(os.sched_getaffinity(0))==1
    args.out.mkdir(parents=True,exist_ok=False)
    args.binary=args.binary.resolve()
    args.drat_trim=args.drat_trim.resolve()
    local=args.out/"inputs";local.mkdir()
    rows=[]
    def trial(name,path,label,cohort,family):
        dest=args.out/"proofs"/name
        row=run_one(path,args.binary,dest,args.budget_ms,args.drat_trim)
        row.update(dataset=cohort,expected=label,family=family,name=name)
        if label=="SAT":
            assert not row["structural_verified"] and not row["drat_verified"],("FALSE UNSAT",row)
        rows.append(row)
        print("AUTO_UNSAT_TRIAL "+json.dumps({k:row[k] for k in
              ("dataset","family","name","expected","status","method",
               "structural_verified","drat_verified","total_s")},sort_keys=True),flush=True)
        with (args.out/"trials.jsonl").open("a") as s:
            s.write(json.dumps(row,sort_keys=True)+"\n")
    synthetic=make_synthetic(random.Random(79117))
    assert len(synthetic)==135,len(synthetic)
    for e in synthetic:
        path=local/(e["name"]+".cnf")
        write_cnf(path,e["clauses"],e["nvars"])
        trial(e["name"],path,e["expected"],"synthetic",e["family"])
    for i,(path,sha) in enumerate(original_sources(args.pcmax20,args.unseen3)):
        label="UNSAT" if "-UNSAT." in path.name else "SAT" if "-SAT." in path.name else "UNKNOWN"
        trial(f"original_{i:02d}",path,label,"original_SAT2024",path.name.split("-")[0])
        assert rows[-1]["source_sha256"]==sha
    # Do not trust status codes alone: a forged proof of SAT must be rejected.
    satfile=local/"drat_negative_control.cnf"
    satfile.write_bytes(b"p cnf 1 1\n1 0\n")
    forged=local/"forged.drat";forged.write_text("0\n")
    accepted,_=check_drat(satfile,forged,args.drat_trim)
    assert not accepted,"DRAT checker accepted SAT as UNSAT"
    methods=collections.Counter(r["method"] for r in rows if r["structural_verified"])
    summary={
        "protocol":"AUTO-UNSAT1-SOURCE-FROZEN-ORIGINAL18+SYNTHETIC135",
        "single_logical_cpu":True,"seed":SEED,"total":len(rows),
        "by_cohort":{},
        "methods":dict(methods),
        "false_unsat":sum(r["expected"]=="SAT" and r["structural_verified"] for r in rows),
        "drat_checker_negative_control_rejected":not accepted,
        "notes":"Structural verifier success != DRAT/LRAT. No universal coverage claim."
    }
    for cohort in ("synthetic","original_SAT2024"):
        rs=[r for r in rows if r["dataset"]==cohort]
        summary["by_cohort"][cohort]={
            "sources":len(rs),
            "labelled_unsat":sum(r["expected"]=="UNSAT" for r in rs),
            "labelled_sat":sum(r["expected"]=="SAT" for r in rs),
            "structural_unsat":sum(r["structural_verified"] for r in rs),
            "strict_drat_unsat":sum(r["drat_verified"] for r in rs),
            "unknown":sum(r["status"]=="UNKNOWN" for r in rs),
            "methods":dict(collections.Counter(r["method"] for r in rs if r["structural_verified"]))
        }
    assert summary["false_unsat"]==0 and len(rows)==153
    (args.out/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("AUTO_UNSAT_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
