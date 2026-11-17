#!/usr/bin/env python3
"""Adversarial safety for direct-source XOR2-4 RED/RUP/CP generator.

24 externally VeriPB-verified true UNSAT inputs: widths 2,3,4 and
mixed [2,3,3] and [2,4,4,2] irregular formula shapes; selected original
variables each occur twice, sum of equation RHS is odd.
For each there are *two SAT inputs with complete false models*:
  (a) all XOR RHS are even, plus
  (b) remove a critical original forbidden-zero pattern clause from
      the odd charge row and update the metadata SHA to the tampered source.
Both must be REJECTED as unsupported, not falsely proved UNSAT.
Plus 24 forged source hash controls.
"""
from collections import Counter
from itertools import product
import hashlib,json,os
from pathlib import Path
import random,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/math5"))
from emit_veripb_xor234_split import compile_source

VERIPB=ROOT/"veripb-tool/bin/veripb"
TYPES=[
  [(1,2),(1,2)],
  [(1,2,3),(1,2,3)],
  [(1,2,3,4),(1,2,3,4)],
  [(1,2),(1,3,4),(2,3,4)],
  [(1,2),(1,3,4,5),(2,3,4,6),(5,6)]
]
def source(rows,truth,seed):
    rng=random.Random(seed)
    maxvar=max(max(row) for row in rows)
    labels=list(range(1,maxvar+1))
    rng.shuffle(labels)
    remap={i+1:labels[i] for i in range(maxvar)}
    actual=[tuple(remap[x] for x in row) for row in rows]
    clauses=[];positions=[]
    for row,b in zip(actual,truth):
        start=len(clauses)
        for assignment in product((0,1),repeat=len(row)):
            if sum(assignment)%2!=b:
                clauses.append(tuple(-x if bit else x
                                for x,bit in zip(row,assignment)))
        positions.append(start)
    rng.shuffle(clauses)
    raw=render(maxvar,clauses)
    cert={"format":"drnas-math5-eo-xor-unit-v1",
          "source_sha256":hashlib.sha256(raw).hexdigest(),
          "xor_rows":[{"vars":list(row),"forbidden_parity":1-b}
                      for row,b in zip(actual,truth)],
          "exact_one_groups":[],"root_units":[]}
    return raw,cert,clauses,actual

def render(nv,clauses):
    return ("p cnf "+str(nv)+" "+str(len(clauses))+"\n"+
            "".join(" ".join(map(str,row))+" 0\n" for row in clauses)).encode()

def rejects(raw,cert):
    try:compile_source(raw,cert)
    except (ValueError,TypeError,KeyError,UnicodeError):
        return
    raise AssertionError("UNSOUND UNSAT proof emitted for SAT or invalid source")

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert VERIPB.is_file()
    tally=Counter()
    with tempfile.TemporaryDirectory(prefix="xor234-safety-") as d:
        base=Path(d);cnf=base/"original.cnf";proof=base/"out.pbp"
        for seed in range(24):
            rows=TYPES[seed%len(TYPES)]
            rhs=[1]+[0]*(len(rows)-1)
            raw,cert,clauses,actual=source(rows,rhs,seed)
            degrees=Counter(v for row in actual for v in row)
            assert set(degrees.values())=={2}
            pb,meta=compile_source(raw,cert)
            cnf.write_bytes(raw);proof.write_text(pb)
            result=subprocess.run([str(VERIPB),"--cnf",str(cnf),str(proof)],
                capture_output=True,text=True,timeout=12)
            assert result.returncode==0 and (
                "s VERIFIED UNSATISFIABLE" in result.stdout+result.stderr),(
                "EXTERNAL_VERIPB_REJECTED",seed,result.stdout,result.stderr)
            tally["external_Veripb_UNSAT_pass"]+=1

            even,even_cert,even_clauses,_=source(rows,[0]*len(rows),seed+210)
            assert all(any(l<0 for l in row) for row in even_clauses),\
                "known all-false SAT control model invalid"
            rejects(even,even_cert)
            tally["known_SAT_even_parity_rejected"]+=1

            critical=frozenset(actual[0])
            assert critical in set(map(frozenset,clauses)),\
                "source row invalid, zero-assignment clause absent"
            altered=[c for c in clauses if frozenset(c)!=critical]
            assert len(altered)==len(clauses)-1
            assert all(any(l<0 for l in row) for row in altered),\
                "known all-false tampered SAT model invalid"
            damaged=render(max(max(row) for row in actual),altered)
            revised={**cert,"source_sha256":hashlib.sha256(damaged).hexdigest()}
            rejects(damaged,revised)
            tally["known_SAT_missing_source_clause_rejected"]+=1

            fake={**cert,"source_sha256":hashlib.sha256(b"forged").hexdigest()}
            rejects(raw,fake)
            tally["forged_SHA_rejected"]+=1
    assert tally==Counter({
      "external_Veripb_UNSAT_pass":24,
      "known_SAT_even_parity_rejected":24,
      "known_SAT_missing_source_clause_rejected":24,
      "forged_SHA_rejected":24})
    print("MATH5_XOR234_SAFETY_PASS "+json.dumps(tally,sort_keys=True),
          flush=True)
if __name__=="__main__":
    main()
