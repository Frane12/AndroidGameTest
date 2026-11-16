#!/usr/bin/env python3
"""IPG5 generic RUP replay and standard VeriPB 3.0 proof conversion.

Does not assume or assert whether the RUP trace came from CDCL. Independently
replays ALL input RUP steps from original CNF + previously verified RUP.
Source must equal the frozen 45v/300c Petersen weighted PCMAX SHA-256.
The origin of a proof trace is not inferred by a verifier; the separate
source generator and reproducible CI command establish its provenance.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import time

from ipg4_rup_drat_to_veripb import (
    dimacs,parse_rup_trace,rup_unit_conflict,clause_to_pbp
)
EXPECTED_SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def convert(original,trace,output):
    started=time.perf_counter()
    raw,nv,clauses=dimacs(original)
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=EXPECTED_SHA:raise ValueError("original byte checksum mismatch")
    proof_steps=parse_rup_trace(trace,nv)
    known=list(clauses)
    for index,clause in enumerate(proof_steps,1):
        if not rup_unit_conflict(known,(-lit for lit in clause)):
            raise ValueError(f"lemma {index} is NOT RUP relative to source")
        known.append(clause)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("w") as stream:
        stream.write("pseudo-Boolean proof version 3.0\n")
        stream.write(f"f {len(clauses)} ;\n")
        for clause in proof_steps:
            stream.write(clause_to_pbp(clause))
        stream.write("output NONE ;\nconclusion UNSAT ;\nend pseudo-Boolean proof ;\n")
    return {
        "status":"SOURCE_RUP_REPLAY_VERIFIED_EXTERNAL_VERIPB_REQUIRED",
        "source_sha256":sha,
        "source_clauses":len(clauses),
        "rup_sha256":hashlib.sha256(trace.read_bytes()).hexdigest(),
        "rup_steps_replayed":len(proof_steps),
        "last_clause_empty":proof_steps[-1]==(),
        "veripb_bytes":output.stat().st_size,
        "replay_s":round(time.perf_counter()-started,6),
        "provenance":"RUP_SOURCE_CHECK_ONLY_ORIGIN_REQUIRES_REPRODUCIBLE_GENERATOR_AUDIT",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original",required=True,type=pathlib.Path)
    p.add_argument("--rup",required=True,type=pathlib.Path)
    p.add_argument("--veripb",required=True,type=pathlib.Path)
    p.add_argument("--metadata",required=True,type=pathlib.Path)
    a=p.parse_args()
    try:
        result=convert(a.original,a.rup,a.veripb)
        a.metadata.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("IPG5_RUP_REPLAY "+json.dumps(result,sort_keys=True),flush=True)
        return 0
    except (ValueError,TypeError,KeyError,OSError,IndexError,UnicodeError) as e:
        a.veripb.unlink(missing_ok=True)
        print("IPG5_REPLAY_REJECT "+str(e),flush=True)
        return 1

if __name__=="__main__":sys.exit(main())
