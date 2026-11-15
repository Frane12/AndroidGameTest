#!/usr/bin/env python3
"""Frozen demanding chess SAT CNFs: toroidal queens and blocked N-Queens Completion.

Toroidal full constraints use four complete lines through each square: rows,
columns, wraparound (r-c)%n and (r+c)%n. Truth for this subfamily follows the
classical Polya theorem: toroidal n-queens exists iff gcd(n,6)=1.

Completion includes pinned non-attacking queens plus many forbidden squares,
and FULL row/column/ordinary diagonal clauses (not binary-only 2SAT).
Planted SAT controls carry independently checked assignments. Unplanted
completion cases are UNKNOWN until measured solver/model/proof confirms status.
All original CNFs are SHA256-frozen before any solver invocation.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import math
import random
from collections import defaultdict
from pathlib import Path

CASES = [
    dict(id="t18", family="toroidal", n=18, seed=101, label="THEOREM_UNSAT"),
    dict(id="t19", family="toroidal", n=19, seed=102, label="WITNESS_SAT"),
    dict(id="t24", family="toroidal", n=24, seed=103, label="THEOREM_UNSAT"),
    dict(id="t25", family="toroidal", n=25, seed=104, label="WITNESS_SAT"),
    dict(id="t42", family="toroidal", n=42, seed=105, label="THEOREM_UNSAT"),
    dict(id="t43", family="toroidal", n=43, seed=106, label="WITNESS_SAT"),
    dict(id="t60", family="toroidal", n=60, seed=107, label="THEOREM_UNSAT"),
    dict(id="t61", family="toroidal", n=61, seed=108, label="WITNESS_SAT"),
    dict(id="c20sat",family="completion", n=20, seed=201, label="WITNESS_SAT"),
    dict(id="c20unk",family="completion", n=20, seed=202, label="UNKNOWN"),
    dict(id="c28sat",family="completion", n=28, seed=203, label="WITNESS_SAT"),
    dict(id="c28unk",family="completion", n=28, seed=204, label="UNKNOWN"),
    dict(id="c36sat",family="completion", n=36, seed=205, label="WITNESS_SAT"),
    dict(id="c36unk",family="completion", n=36, seed=206, label="UNKNOWN"),
    dict(id="c44sat",family="completion", n=44, seed=207, label="WITNESS_SAT"),
    dict(id="c44unk",family="completion", n=44, seed=208, label="UNKNOWN"),
]
def normal_solution(n):
    if n%6==2:
        # Valid even-n construction.
        p=[i-1 for i in list(range(2,n+1,2))+[3,1]+list(range(7,n+1,2))+[5]]
    elif n%6==3:
        p=[i-1 for i in list(range(4,n+1,2))+[2]+list(range(5,n+1,2))+[1,3]]
    else:
        p=[i-1 for i in list(range(2,n+1,2))+list(range(1,n+1,2))]
    assert len(p)==n and set(p)==set(range(n))
    assert len({r-c for r,c in enumerate(p)})==n
    assert len({r+c for r,c in enumerate(p)})==n
    return p
def independent_partial(n, rng, count):
    for attempt in range(250):
        rows=list(range(n));rng.shuffle(rows)
        cols=set(); d1=set();d2=set();partial={}
        for r in rows:
            opts=[c for c in range(n) if c not in cols and
                  r-c not in d1 and r+c not in d2]
            if not opts:break
            c=rng.choice(opts)
            partial[r]=c
            cols.add(c);d1.add(r-c);d2.add(r+c)
            if len(partial)>=count:return partial
    raise ValueError("Unable to create random non-attacking partial queens")
def create(case, out):
    rng=random.Random(case["seed"])
    n=case["n"]
    tor=case["family"]=="toroidal"
    variables=n*n
    # Keep all chessboard positions explicit. Scramble literal numbering later.
    def variable(r,c):return 1+r*n+c
    rows=[[variable(r,c) for c in range(n)] for r in range(n)]
    cols=[[variable(r,c) for r in range(n)] for c in range(n)]
    diag_a=defaultdict(list);diag_b=defaultdict(list)
    for r in range(n):
        for c in range(n):
            d1=(r-c)%n if tor else r-c
            d2=(r+c)%n if tor else r+c
            diag_a[d1].append(variable(r,c))
            diag_b[d2].append(variable(r,c))
    clauses=[]
    # Genuine N queens: choose exactly one square each row, no same column
    # or diagonal, including mutually exclusive choices on a single row.
    clauses.extend(tuple(g) for g in rows)
    for family in (rows,cols,list(diag_a.values()),list(diag_b.values())):
        for group in family:
            clauses.extend((-a,-b) for a,b in itertools.combinations(group,2))
    pinned={}
    blocked=set()
    truth=None
    if tor:
        assert (math.gcd(n,6)==1)==(case["label"]=="WITNESS_SAT")
        if case["label"]=="WITNESS_SAT":
            truth={variable(r,(2*r)%n) for r in range(n)}
    else:
        if case["label"]=="WITNESS_SAT":
            solution=normal_solution(n)
            choice=list(range(n));rng.shuffle(choice)
            pinned={r:solution[r] for r in choice[:max(3,n//4)]}
            truth={variable(r,solution[r]) for r in range(n)}
        else:
            pinned=independent_partial(n,rng,max(4,int(0.38*n)))
        for r,c in pinned.items():clauses.append((variable(r,c),))
        for r in range(n):
            if r in pinned:continue
            options=[c for c in range(n) if (r,c) not in pinned.items() and
                     (truth is None or variable(r,c) not in truth)]
            rng.shuffle(options)
            for c in options:
                if rng.random()<0.60:
                    blocked.add((r,c))
            # In unplanted cases, avoid direct empty/one-option rows.
            if truth is None:
                available=[c for c in range(n) if (r,c) not in blocked]
                if len(available)<4:
                    for c in options:
                        blocked.discard((r,c))
                        available=[x for x in range(n) if (r,x) not in blocked]
                        if len(available)>=4:break
        clauses.extend((-variable(r,c),) for r,c in sorted(blocked))
        if truth is not None:
            assert all(variable(r,solution[r]) not in
                       {variable(x,y) for x,y in blocked} for r in range(n))
    if truth is not None:
        for clause in clauses:
            assert any((abs(lit) in truth)==(lit>0) for lit in clause), \
                ("SAT witness failed original chess rules",case["id"])
    rename=list(range(1,variables+1));rng.shuffle(rename)
    rename=[0]+rename
    new_clauses=[tuple(rename[abs(v)]*(1 if v>0 else -1) for v in c)
                 for c in clauses]
    rng.shuffle(new_clauses)
    if truth is not None:
        t={rename[v] for v in truth}
        assert all(any((abs(lit) in t)==(lit>0) for lit in c) for c in new_clauses)
    out.mkdir(parents=True,exist_ok=True)
    path=out/(case["id"]+".cnf")
    h=hashlib.sha256()
    with path.open("wb") as f:
        def write(b):f.write(b);h.update(b)
        write(f"p cnf {variables} {len(new_clauses)}\n".encode())
        for clause in new_clauses:
            write((" ".join(map(str,clause))+" 0\n").encode())
    return dict(**case,variables=variables,clauses=len(new_clauses),
                bytes=path.stat().st_size,sha256=h.hexdigest(),
                pinned_queens=len(pinned),forbidden_squares=len(blocked),
                source_label_is_oracle=(case["label"]!="UNKNOWN"),
                oracle=("Polya gcd(n,6) theorem" if case["label"]=="THEOREM_UNSAT" else
                        "full original-CNF assignment checked" if truth else
                        "unknown until independent solve/model/proof"),
                full_queens_cnf=True,permuted_variables_and_clauses=True)
def freeze(shard,out):
    assert shard in range(4)
    selected=[c for i,c in enumerate(CASES) if i%4==shard]
    rows=[]
    for c in selected:
        record=create(c,out)
        rows.append(record)
        print("CHESS_HARD_SOURCE "+json.dumps(record,sort_keys=True),flush=True)
    obj=dict(protocol="CHESS_HARD_TOROID_COMPLETION_FROZEN_V1",shard=shard,
             cases=rows,all_predeclared=CASES,
             no_solver_tuned_selection=True,
             original_families=["toroidal","completion"])
    (out/"frozen.json").write_text(json.dumps(obj,indent=2)+"\n")
    return obj
if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int,choices=range(4),required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.out.exists():raise SystemExit("Refuse existing output directory")
    freeze(a.shard,a.out)
