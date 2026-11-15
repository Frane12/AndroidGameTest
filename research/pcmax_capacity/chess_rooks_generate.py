#!/usr/bin/env python3
"""Source-frozen synthetic SAT chess rook placements on rectangular boards.

Each rook has a dedicated column, so the remaining non-attacking condition is
unique rows. These are genuine rook constraints, not arbitrary pasted UNSAT
cores. Every rook must occupy exactly one of its legal rows, and every row can
contain at most one rook. Domain=sparse_cycle2/3 or dense_all. Full byte-wise
variable renaming and clause permutation obscure row/rook indexing.
"""
import hashlib
import json
import random
from itertools import combinations
from pathlib import Path

# All eight cases frozen before comparing native C++/Kissat/CaDiCaL.
# Label is for independent oracle/harness only, never passed to solvers.
CASES = [
    dict(id="c00", rooks=100, rows=99, mode="dense_all", seed=17, expected="UNSAT"),
    dict(id="c01", rooks=100, rows=100, mode="dense_all", seed=29, expected="SAT"),
    dict(id="c02", rooks=500, rows=499, mode="sparse_cycle2", seed=17, expected="UNSAT"),
    dict(id="c03", rooks=500, rows=500, mode="sparse_cycle2", seed=29, expected="SAT"),
    dict(id="c04", rooks=1000, rows=999, mode="sparse_cycle2", seed=17, expected="UNSAT"),
    dict(id="c05", rooks=1000, rows=1000, mode="sparse_cycle2", seed=29, expected="SAT"),
    dict(id="c06", rooks=1000, rows=999, mode="sparse_cycle3", seed=47, expected="UNSAT"),
    dict(id="c07", rooks=1000, rows=1000, mode="sparse_cycle3", seed=53, expected="SAT"),
]

def make(spec, root):
    R,M=spec["rooks"],spec["rows"]
    assert R in (100,500,1000) and M in (R,R-1)
    assert spec["expected"]==("UNSAT" if R>M else "SAT")
    mode=spec["mode"]
    opts= M if mode=="dense_all" else int(mode[-1])
    assert 2<=opts<=M
    rng=random.Random(spec["seed"])
    # Rook column c, allowed rows J(c), with row permutation before encoding.
    rows=list(range(M));rng.shuffle(rows)
    domains=[list(range(M)) if mode=="dense_all" else
             [((j+t)%M) for t in range(opts)] for j in range(R)]
    if mode!="dense_all":
        domains=[[rows[k] for k in values] for values in domains]
    if mode=="dense_all":
        # Ensures SAT control model maps rook j to row j.
        domains=[list(rows) for _ in range(R)]
    lookup={}
    for j,domain in enumerate(domains):
        for row in domain:lookup[j,row]=len(lookup)+1
    n=len(lookup)
    shuffle=list(range(1,n+1));rng.shuffle(shuffle)
    rename=[0,*shuffle]
    clauses=[]
    # Exact one square for each physical rook (one fixed column).
    for j,domain in enumerate(domains):
        choices=[lookup[j,row] for row in domain]
        clauses.append(tuple(choices))
        for a,b in combinations(choices,2):
            clauses.append((-a,-b))
    # Two rooks on the same row attack each other.
    perrow=[[] for _ in range(M)]
    for (j,row),v in lookup.items():perrow[row].append(v)
    for candidates in perrow:
        for a,b in combinations(candidates,2):
            clauses.append((-a,-b))
    renamed=[tuple(rename[abs(v)]*(1 if v>0 else -1) for v in c)
             for c in clauses]
    rng.shuffle(renamed)
    assert len(renamed)<=1_000_000 and n<=200_000
    path=root/(spec["id"]+".cnf")
    path.parent.mkdir(parents=True,exist_ok=True)
    sha=hashlib.sha256()
    def write(fd,buf):
        fd.write(buf);sha.update(buf)
    with path.open("wb") as fd:
        write(fd,f"p cnf {n} {len(renamed)}\n".encode())
        for clause in renamed:
            write(fd,(" ".join(map(str,clause))+" 0\n").encode())
    # Independent SAT witness checked against each actual permuted clause.
    # UNSAT follows from source ALOs, row AMOs and R>M; checked additionally by
    # standard VeriPB after native source discovery.
    witness_checked=0
    if spec["expected"]=="SAT":
        truths={rename[lookup[j,rows[j]]] for j in range(R)}
        assert len(truths)==R
        for clause in renamed:
            assert any((abs(v) in truths)==(v>0) for v in clause),"SAT control invalid"
            witness_checked+=1
    info={k:v for k,v in spec.items()}
    info.update(variables=n,clauses=len(renamed),bytes=path.stat().st_size,
                sha256=sha.hexdigest(),witness_checked_clauses=witness_checked,
                number_of_columns=R,number_of_rows=M,
                mathematical_oracle="R>M pigeonhole" if R>M else "explicit verified SAT witness",
                note="permuted synthetic rectangular rook board; dense and sparse encodings are distinct")
    return info

def freeze(shard,root):
    assert shard in (0,1)
    selected=[x for i,x in enumerate(CASES) if i%2==shard]
    items=[make(x,root) for x in selected]
    output=dict(protocol="CHESS_ROOKS_PHP_PERMUTED_SYNTH_V1",
                source="explicit chess rook placements, each rook occupies a fixed column",
                preregistered_all=[dict(x) for x in CASES],shard=shard,
                cases=items,sparse_domains_are_easier_than_dense=True)
    (root/"frozen.json").write_text(json.dumps(output,indent=2)+"\n")
    return output

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int,choices=(0,1),required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.out.exists():raise SystemExit("Refuse output overwrite")
    a.out.mkdir(parents=True)
    result=freeze(a.shard,a.out)
    for c in result["cases"]:
        print("ROOK_FREEZE "+json.dumps(c,sort_keys=True),flush=True)
