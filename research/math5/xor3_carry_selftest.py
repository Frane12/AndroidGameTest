#!/usr/bin/env python3
"""Proof-safety tests for RED/RUP/CP XOR3 carry emitter.

24 constructed odd-charge 3-regular Tseitin UNSAT sources are verified
by external VeriPB. 24 even-charge SAT controls and 24 single-clause-
deleted SAT controls contain an independently checked all-false model;
the converter MUST reject each despite corrected source hash metadata.
No source filename or known outcome is used by the proof generator.
"""
from collections import Counter
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"/"math5"))
from emit_veripb_xor3_carry import compile_source

CHECKER=ROOT/"veripb-tool/bin/veripb"

def cubic_source(n,seed,odd_charge):
    assert n>=6 and n%2==0
    ring={tuple(sorted((v,(v+1)%n))) for v in range(n)}
    matching={tuple(sorted((v,(v+n//2)%n))) for v in range(n)}
    edges=sorted(ring|matching)
    assert len(edges)==3*n//2
    rng=random.Random(seed)
    rng.shuffle(edges)
    key={pair:i+1 for i,pair in enumerate(edges)}
    rows=[];support=[];clauses=[]
    for vertex in range(n):
        vars=sorted(key[pair] for pair in edges if vertex in pair)
        assert len(vars)==3
        support.append(vars)
        parity=1 if vertex==0 and odd_charge else 0
        rows.append({"vars":vars,"forbidden_parity":1-parity})
        for bits in itertools.product((0,1),repeat=3):
            if sum(bits)%2!=parity:
                clauses.append(tuple(-v if bit else v for v,bit in zip(vars,bits)))
    rng.shuffle(clauses)
    raw=render(n,clauses)
    cert={"format":"drnas-math5-eo-xor-unit-v1",
          "source_sha256":hashlib.sha256(raw).hexdigest(),
          "xor_rows":rows,"exact_one_groups":[],"root_units":[]}
    return raw,cert,clauses

def render(n,clauses):
    return (f"p cnf {3*n//2} {len(clauses)}\n"+
            "".join(" ".join(map(str,row))+" 0\n" for row in clauses)).encode()

def all_false_satisfies(clauses):
    return all(any(lit<0 for lit in row) for row in clauses)

def reject(raw,cert):
    try:compile_source(raw,cert)
    except (ValueError,TypeError,KeyError,IndexError):return
    raise AssertionError("UNSOUND: accepted known SAT source")

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert CHECKER.is_file()
    scores=Counter()
    with tempfile.TemporaryDirectory(prefix="xor3-veripb-adversarial-") as location:
        scratch=Path(location)
        cnf=scratch/"source.cnf"
        pbp=scratch/"source.pbp"
        for seed in range(24):
            n=6+2*(seed%8)
            raw,cert,source_clauses=cubic_source(n,seed,True)
            proof,meta=compile_source(raw,cert)
            assert meta["rhs_sum_odd"] and meta["fresh_carry_variables"]==n
            cnf.write_bytes(raw);pbp.write_text(proof)
            run=subprocess.run([str(CHECKER),"--cnf",str(cnf),str(pbp)],
                capture_output=True,text=True,timeout=15)
            assert run.returncode==0 and (
                "s VERIFIED UNSATISFIABLE" in run.stdout+run.stderr), (
                    "UNSAT_SOURCE_EXTERNAL_CHECK_REJECTED",seed,run.stdout,run.stderr)
            scores["external_VERIPB_UNSAT_PASSES"]+=1

            even,even_cert,even_clauses=cubic_source(n,seed,False)
            assert all_false_satisfies(even_clauses), "SAT model not valid"
            reject(even,even_cert)
            scores["SAT_even_rhs_rejected"]+=1

            bad_clause=frozenset(cert["xor_rows"][0]["vars"])
            assert bad_clause in {frozenset(c) for c in source_clauses}
            altered=[row for row in source_clauses if frozenset(row)!=bad_clause]
            assert len(altered)==len(source_clauses)-1
            assert all_false_satisfies(altered), "SAT model not valid"
            tampered=render(n,altered)
            rewritten={**cert,"source_sha256":hashlib.sha256(tampered).hexdigest()}
            reject(tampered,rewritten)
            scores["SAT_missing_original_clause_rejected"]+=1

            fake={**cert,"source_sha256":hashlib.sha256(b"altered").hexdigest()}
            reject(raw,fake)
            scores["SHA_mismatch_rejected"]+=1

    assert scores["external_VERIPB_UNSAT_PASSES"]==24
    assert scores["SAT_even_rhs_rejected"]==24
    assert scores["SAT_missing_original_clause_rejected"]==24
    assert scores["SHA_mismatch_rejected"]==24
    print("MATH5_XOR3_VERIPB_SAFETY_PASS "+json.dumps(scores,sort_keys=True),
          flush=True)

if __name__=="__main__":
    main()
