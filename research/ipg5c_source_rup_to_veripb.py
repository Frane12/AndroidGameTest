#!/usr/bin/env python3
"""IPG5C generic verified RUP -> VeriPB 3.0 source-bound converter.

The tool does NOT trust a generator's CNF structural claim. It
independently parses the exact source clauses and replays each RUP
inference against the original formula plus preceding RUP lemmas.
The SHA-256 of exact original input must match a precommitted
--expected-sha256 manifest entry. The standard VeriPB 3.0.2
checker is additionally required before accepting any UNSAT.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time
from ipg4_rup_drat_to_veripb import dimacs,parse_rup_trace,rup_unit_conflict,clause_to_pbp

def convert(source,trace,out,expected):
    begin=time.perf_counter()
    raw,nvars,clauses=dimacs(source)
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected:
        raise ValueError("input source digest not pinned to manifest")
    if nvars>45 or nvars<9 or nvars%3:
        raise ValueError("input variable count outside source gate")
    if not 1<=len(clauses)<=20000:
        raise ValueError("unsupported original clauses")
    proof=parse_rup_trace(trace,nvars)
    if len(proof)>120000:
        raise ValueError("proof too large")
    database=list(clauses)
    for index,clause in enumerate(proof,1):
        if not rup_unit_conflict(database,(-lit for lit in clause)):
            raise ValueError(f"invalid original-CNF RUP lemma {index}")
        database.append(clause)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w") as f:
        f.write(f"pseudo-Boolean proof version 3.0\nf {len(clauses)} ;\n")
        for clause in proof:f.write(clause_to_pbp(clause))
        f.write("output NONE ;\nconclusion UNSAT ;\nend pseudo-Boolean proof ;\n")
    return {
        "status":"ORIGINAL_SOURCE_RUP_REPLAY_VERIFIED_PB_EXTERNAL_CHECK_REQUIRED",
        "source_sha256":digest,
        "original_variables":nvars,
        "original_clauses":len(clauses),
        "rup_steps":len(proof),
        "rup_sha256":hashlib.sha256(trace.read_bytes()).hexdigest(),
        "veripb_bytes":out.stat().st_size,
        "replay_s":round(time.perf_counter()-begin,6),
    }
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--rup",required=True,type=pathlib.Path)
    p.add_argument("--veripb",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    p.add_argument("--expected-sha256",required=True)
    a=p.parse_args()
    try:
        report=convert(a.cnf,a.rup,a.veripb,a.expected_sha256)
        a.meta.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        print("IPG5C_INDEPENDENT_RUP "+json.dumps(report,sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,UnicodeError) as exc:
        a.veripb.unlink(missing_ok=True)
        print("IPG5C_RUP_REJECT "+str(exc))
        return 1
if __name__=="__main__":sys.exit(main())
