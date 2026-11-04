#!/usr/bin/env python3
"""R105: certified XOR contradiction-only GF(2) prepass.

No heuristics, no UNSAT claim without replaying all source 3-XOR certificates
and the exact GF(2) ancestry of 0=1. On no proof, emit source CNF unchanged.
"""
import argparse
import json
import pathlib
import sys
import time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r92_verified_xor_bridge as r92
import r93_export_verified_rows as r93
import r104_static_xor_prepass as r104
import r88_cooperative as r88

def run(source,augmented,evidence):
    t=time.perf_counter()
    source=pathlib.Path(source)
    n,clauses=r88.read_cnf(source)
    originals=r92.xor_sources(clauses)
    independently_read=r93.independent_index(clauses)
    if any((mask,rhs) not in independently_read for mask,rhs,_ in originals):
        raise RuntimeError("R105_FAIL_CLOSED: original XOR signature disagreement")
    pivots,contradiction=r104.elimination(originals)
    proof=[]
    extras=[]
    if contradiction is not None:
        mask,rhs,ancestors=contradiction
        if mask != 0 or rhs != 1 or not r104.independent_replay(
                mask,rhs,ancestors,originals,independently_read):
            raise RuntimeError("R105_FAIL_CLOSED: contradictory row not independently proved")
        proof=sorted(ancestors)
        extras=[()]
    augmented=pathlib.Path(augmented)
    augmented.parent.mkdir(parents=True,exist_ok=True)
    r88.write_augmented(n,clauses,extras,augmented)
    diag=dict(protocol="R105-CONTRADICTION-ONLY-GF2-CERT",
              sha256=r88.sha(source),variables=n,clauses=len(clauses),
              original_xors=len(originals),matrix_rank=len(pivots),
              contradiction=bool(extras),proof_original_row_ids=proof,
              augmented_clauses=len(clauses)+len(extras),
              prep_s=round(time.perf_counter()-t,7))
    pathlib.Path(evidence).write_text(json.dumps(diag,indent=2)+"\n")
    print("R105_GF2_CERT",json.dumps(diag),flush=True)
    return diag

def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp:
        root=pathlib.Path(temp)
        p=root/"input.cnf"
        clauses=[]
        for variables in ((1,2,3),(1,2,4)):
            for sign in (1,2,4,7):
                clauses.append(tuple(-v if sign & (1<<i) else v
                                     for i,v in enumerate(variables)))
        r88.write_augmented(4,clauses,[],p)
        s=run(p,root/"sat.cnf",root/"sat.json")
        assert not s["contradiction"]
        for sign in (0,3,5,6):
            clauses.append(tuple(-v if sign & (1<<i) else v
                                 for i,v in enumerate((1,2,3))))
        r88.write_augmented(4,clauses,[],p)
        u=run(p,root/"unsat.cnf",root/"unsat.json")
        assert u["contradiction"] and len(u["proof_original_row_ids"])==2
        assert r88.read_cnf(root/"unsat.cnf")[1][-1] == ()
    print("R105_GF2_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=["selftest","export"])
    ap.add_argument("--cnf");ap.add_argument("--out");ap.add_argument("--evidence")
    args=ap.parse_args()
    if args.action=="selftest":selftest()
    else:
        if not (args.cnf and args.out and args.evidence):ap.error("missing paths")
        run(args.cnf,args.out,args.evidence)
