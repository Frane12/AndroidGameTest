#!/usr/bin/env python3
"""Deterministic synthetic SAT formula construction for DELTAX semantics.

Positive family is a renaming of the exact LOCAL original-clause pattern
from SAT2024 hardware-miter, not a hardcoded solver fixture. Two overlapping
local relations contain a nonlinear-separator gap; when both guard literals
are false, the joint truth table admits precisely 000/111 on (a,z,y).
No generator metadata is passed to the solver. Controls challenge the
need for the guard, for nonlinear joining, and for the reverse clause.
"""
import hashlib
import json
import random
from pathlib import Path

BASE=[
    [1,-2,3],[2,-3],[-1,-3],
    [-1,-2,5],[1,-5],[2,-5],
    [-1,2,4],[1,-4],[-2,-4],
]

def remap(clauses,mapping):
    return [[(1 if lit>0 else -1)*mapping[abs(lit)] for lit in row]
            for row in clauses]

def generate():
    cases=[]
    def put(name,n,clauses,group,expect_alias=False):
        assert max((abs(l) for row in clauses for l in row),default=0)<=n
        cases.append({"name":name,"n":n,"clauses":clauses,
                      "group":group,"expect_alias":expect_alias})
    # Unambiguous real-witness-derived relation with both guards false.
    put("guarded_core",5,BASE+[[-3],[-4]],"positive",True)
    # Downstream chain, a way to make useful trail assignments observable.
    put("guarded_downstream",7,BASE+[[-3],[-4],[-5,6],[-6,7]],
        "positive",True)
    put("guarded_with_decoy",8,BASE+[[-3],[-4],
        [1,6],[-1,7],[1,-7],[-6,8],[-8,6]],"positive",True)
    # Reproducible polarity-preserving variable renaming, clause-order
    # permutations: prevents benchmark-specific variable ID assumptions.
    for seed in range(8):
        rng=random.Random(150114+seed)
        perm=list(range(1,6));rng.shuffle(perm)
        mapping={k:v for k,v in zip(range(1,6),perm)}
        cnf=remap(BASE+[[-3],[-4]],mapping)
        rng.shuffle(cnf)
        put(f"renamed_{seed}",5,cnf,"positive",True)
    # Without unit guards the implication remains CONDITIONAL, not global.
    put("guards_unassigned",5,BASE,"negative")
    put("one_guard_only",5,BASE+[[-3]],"negative")
    # Remove both original reverse implications. The same-looking relation
    # cannot be claimed as a guarded equivalence without source entailment.
    put("reverse_removed",5,[c for c in BASE if c not in ([1,-5],[2,-5])]
        +[[-3],[-4]],"negative")
    # A linear equivalence must not be labeled nonlinear discovery.
    put("linear_only",5,[[-1,2],[1,-2],[-2,5],[2,-5],[-3],[-4]],
        "negative")
    # A true contradiction must be proof-checked, not inferred from
    # an unverified nonlinear witness.
    put("root_unsat",5,BASE+[[-3],[-4],[1],[-5]],"negative")
    # Add an unrelated parity component, not relevant to the alias itself.
    parity=[[6,7,8],[6,-7,-8],[-6,7,-8],[-6,-7,8]]
    put("guarded_with_parity",8,BASE+[[-3],[-4]]+parity,
        "positive",True)
    return cases

def write(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    out=[]
    for case in generate():
        text=("p cnf %d %d\n"%(case["n"],len(case["clauses"]))+
             "".join(" ".join(map(str,row))+" 0\n" for row in case["clauses"]))
        p=folder/(case["name"]+".cnf")
        p.write_text(text)
        out.append({k:v for k,v in case.items() if k!="clauses"}|
                   {"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
                    "path":str(p)})
    (folder/"manifest.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    return out

if __name__=="__main__":
    rows=write("deltax_synthetic_inputs")
    print("DELTAX_SYNTH_SOURCE_MANIFEST",json.dumps({
        "cases":len(rows),"positive":sum(z["group"]=="positive" for z in rows),
        "negative":sum(z["group"]=="negative" for z in rows)}))
