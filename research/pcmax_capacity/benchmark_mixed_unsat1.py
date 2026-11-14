#!/usr/bin/env python3
"""Paired 116-source audit: unchanged native CLAUSE-HALL2, then tiny proofs.

Only independently checked source-bound UNSAT certificates count.
The 28 SAT controls have explicit satisfying assignments, no false positives.
"""
import argparse
import collections
import copy
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from random_unsat_probe import cases, SEED, write_cnf, native_run, satisfied, exact_sat
from check_clause_hall import check as check_hall
from propose_mixed_unsat import propose
from check_mixed_unsat import verify as check_mixed, InvalidProof

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--native-budget-ms",type=int,default=700)
    parser.add_argument("--proof-budget-ms",type=int,default=50)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    formulas=cases(random.Random(SEED))
    rows=[]
    with (args.out/"trials.jsonl").open("w") as stream:
        for idx,c in enumerate(formulas):
            src=args.out/(c["name"]+".cnf")
            cert=args.out/(c["name"]+".hall.json")
            raw=write_cnf(src,c["clauses"],c["nvars"])
            label=c["expected"]
            if label=="SAT":
                assert satisfied(c["clauses"],c["model"]),("invalid SAT witness",c["name"])
            elif c["family"] in ("random_3sat_unsat","xor_parity_unsat","unsat_2sat"):
                assert exact_sat(c["clauses"],c["nvars"]) is None
            rc,native_s,tele,err=native_run(args.binary,src,cert,args.native_budget_ms)
            assert rc in (0,20),(c["name"],rc,err)
            base=False
            method="none"
            mixed=None
            proof_s=checker_s=0.0
            if rc==20:
                assert cert.exists(),("missing Hall certificate",c["name"])
                check_hall(raw,json.loads(cert.read_text()))
                assert label=="UNSAT",("FALSE UNSAT Hall",c["name"])
                base=True
                method="hall2"
            else:
                assert not cert.exists(),("unexpected Hall certificate",c["name"])
                t=time.perf_counter()
                proposed=propose(raw,args.proof_budget_ms)
                proof_s=time.perf_counter()-t
                if proposed is not None:
                    t=time.perf_counter()
                    outcome=check_mixed(raw,proposed)
                    checker_s=time.perf_counter()-t
                    assert outcome["status"]=="UNSAT_VERIFIED"
                    assert label=="UNSAT",("FALSE UNSAT mixed",c["name"],proposed)
                    # Independent checker rejects one syntactically valid but
                    # wrong certificate for every accepted proof.
                    forged=copy.deepcopy(proposed)
                    forged["source_sha256"]="0"*64
                    try: check_mixed(raw,forged)
                    except (InvalidProof,ValueError): pass
                    else: raise AssertionError(("tampered digest accepted",c["name"]))
                    mixed=outcome
                    method=proposed["method"]
                    (args.out/(c["name"]+".mixed.json")).write_text(
                        json.dumps(proposed,sort_keys=True)+"\\n")
            row={"id":idx,"family":c["family"],"name":c["name"],"expected":label,
                 "clauses":len(c["clauses"]),"variables":c["nvars"],
                 "sha256":hashlib.sha256(raw).hexdigest(),
                 "hall2_verified":base,"mixed_verified":mixed is not None,
                 "method":method,"native_s":native_s,
                 "proof_proposal_s":round(proof_s,6),
                 "proof_checker_s":round(checker_s,6),
                 "mixed_metadata":mixed,"native_reason":tele.get("reason","not_reported")}
            rows.append(row)
            stream.write(json.dumps(row,sort_keys=True)+"\\n")
            stream.flush()
            print("MIXED_UNSAT_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    families={}
    for family in sorted(set(r["family"] for r in rows)):
        rr=[r for r in rows if r["family"]==family]
        families[family]={"total":len(rr),
                         "hall2":sum(r["hall2_verified"] for r in rr),
                         "new":sum(r["mixed_verified"] for r in rr),
                         "unresolved":sum(not (r["hall2_verified"] or r["mixed_verified"]) for r in rr),
                         "proofs":dict(collections.Counter(r["method"] for r in rr))}
    result={"seed":SEED,"single_logical_cpu":cpu,"total":len(rows),
            "expected_unsat":sum(r["expected"]=="UNSAT" for r in rows),
            "sat_controls":sum(r["expected"]=="SAT" for r in rows),
            "hall2_certified":sum(r["hall2_verified"] for r in rows),
            "newly_certified":sum(r["mixed_verified"] for r in rows),
            "combined_certified":sum(r["hall2_verified"] or r["mixed_verified"] for r in rows),
            "false_unsat":sum(r["expected"]=="SAT" and (r["hall2_verified"] or r["mixed_verified"]) for r in rows),
            "methods":dict(collections.Counter(r["method"] for r in rows)),
            "families":families}
    (args.out/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\\n")
    print("MIXED_UNSAT_FINAL "+json.dumps(result,sort_keys=True),flush=True)
    assert result["false_unsat"]==0
    assert result["total"]==116
if __name__=="__main__":main()
