#!/usr/bin/env python3
"""Produce and independently check source-only GF2+root-unit proofs.

The producer is not trusted. A UNSAT result counts only when an entirely
different independent checker recomputes source XOR clauses and root-UP.
"""
import argparse
import copy
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pcmax_capacity"))
from inspect_xor_units import SOURCES,read_cnf,discover_xor,root_units,reduce_xor
from check_xor_units import verify,InvalidMath4Proof

def build_candidate(raw,clauses):
    rows=discover_xor(clauses)
    forced,rounds,conflict,closed=root_units(clauses,limit_s=3.0)
    if not closed or conflict:
        return None,{"reason":"root_unit_closure_incomplete_or_conflicting","root_units":len(forced)}
    rank,used,kinds,entries=reduce_xor(rows,forced)
    details={"reason":"no_linear_contradiction","xor_rows_available":len(rows),
             "root_units_available":len(forced),"rank":rank,"trace_size":len(used)}
    if not used:return None,details
    xor_rows=[]
    literals=[]
    for idx in used:
        _,rhs,kind,support=entries[idx]
        if kind=="xor":
            xor_rows.append({"vars":list(support),"forbidden_parity":1-rhs})
        else:
            assert kind=="unit" and len(support)==1
            literals.append(support[0] if rhs else -support[0])
    cert={"format":"drnas-math4-xor-unit-v1",
          "source_sha256":hashlib.sha256(raw).hexdigest(),
          "xor_rows":xor_rows,"root_units":literals}
    details.update(reason="xor_unit_proof_proposed",
                   selected_xor=len(xor_rows),selected_units=len(literals))
    return cert,details

def negative_tests(raw,cert):
    edits=[]
    x=copy.deepcopy(cert);x["source_sha256"]="0"*64;edits.append(x)
    x=copy.deepcopy(cert);x["xor_rows"][0]["forbidden_parity"]^=1;edits.append(x)
    x=copy.deepcopy(cert);x["xor_rows"].pop();edits.append(x)
    if cert["root_units"]:
        x=copy.deepcopy(cert)
        x["root_units"][0]*=-1
        edits.append(x)
    for forged in edits:
        try:verify(raw,forged)
        except (InvalidMath4Proof,ValueError):pass
        else:raise AssertionError("FORGED_GF2_PROOF_ACCEPTED")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=Path("math4_certificates"))
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    m=json.loads(Path("research/hall3/manifest.json").read_text())
    records=[]
    for s in m["sources"]:
        if s["id"] not in SOURCES:continue
        path=Path(s["path"])
        raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==s["sha256"],("SOURCE_MISMATCH",s["id"])
        nv,clauses=read_cnf(path)
        proof,meta=build_candidate(raw,clauses)
        status="UNKNOWN"
        checked=None
        if proof is not None:
            checked=verify(raw,proof)
            assert checked["status"]=="UNSAT_VERIFIED"
            negative_tests(raw,proof)
            certfile=args.out/(f"source_{s['id']:02d}_gf2_unit_proof.json")
            certfile.write_text(json.dumps(proof,indent=2)+"\n")
            status="UNSAT_CERTIFIED"
        result={"id":s["id"],"family":s["family"],
                "catalog_label":s["catalog_label"],
                "source_sha256":s["sha256"],"status":status,
                "diagnostic":meta,"checked":checked}
        records.append(result)
        print("MATH4_CERT_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    summary={"sources":len(records),
             "unsat_certified":sum(r["status"]=="UNSAT_CERTIFIED" for r in records),
             "false_unsat_catalog_sat":sum(r["catalog_label"]=="sat" and
                  r["status"]=="UNSAT_CERTIFIED" for r in records),
             "proof_format":"drnas-math4-xor-unit-v1","cases":records}
    assert summary["false_unsat_catalog_sat"]==0
    (args.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("MATH4_CERT_FINAL "+json.dumps({
        "sources":summary["sources"],"unsat_certified":summary["unsat_certified"],
        "false_unsat_catalog_sat":summary["false_unsat_catalog_sat"],
        "successful_source_ids":[r["id"] for r in records if r["status"]=="UNSAT_CERTIFIED"]},
        sort_keys=True),flush=True)
if __name__=="__main__":main()
