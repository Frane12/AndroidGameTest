#!/usr/bin/env python3
"""Frozen real queen-board rules encoded into CNF.

STANDARD: one queen per row, at most one per column, both diagonal families.
CYCLE2: two allowed squares per row; col/row nonattack always, diagonals toggled.
The diagonal-on case is UNSAT although row/column-only has perfect matchings.
All variables and clauses are permuted before any solver executes. The generator
checks SAT controls by evaluating the exact shuffled CNF, and checks UNSAT
using a separate bitmask oracle (n=2/3) or exact 2-SAT SCC (cycle2).
"""
import hashlib
import itertools
import json
import random
from collections import defaultdict
from pathlib import Path

CASES=[
 dict(id="q00",kind="standard",n=2,seed=17,expected="UNSAT"),
 dict(id="q01",kind="standard",n=3,seed=29,expected="UNSAT"),
 dict(id="q02",kind="standard",n=8,seed=31,expected="SAT"),
 dict(id="q03",kind="standard",n=16,seed=37,expected="SAT"),
 dict(id="q04",kind="standard",n=32,seed=41,expected="SAT"),
 dict(id="q05",kind="standard",n=64,seed=43,expected="SAT"),
 dict(id="q06",kind="cycle2",n=32,diagonals=True,seed=47,expected="UNSAT"),
 dict(id="q07",kind="cycle2",n=32,diagonals=False,seed=53,expected="SAT"),
 dict(id="q08",kind="cycle2",n=128,diagonals=True,seed=59,expected="UNSAT"),
 dict(id="q09",kind="cycle2",n=128,diagonals=False,seed=61,expected="SAT"),
 dict(id="q10",kind="cycle2",n=512,diagonals=True,seed=67,expected="UNSAT"),
 dict(id="q11",kind="cycle2",n=512,diagonals=False,seed=71,expected="SAT"),
]
def known_queen_solution(n):
    if n%6==2:
        return [i-1 for i in (list(range(2,n+1,2))+[3,1]+
                             list(range(7,n+1,2))+[5])]
    if n%6==3:
        return [i-1 for i in list(range(4,n+1,2))+[2]+
                list(range(5,n+1,2))+[1,3]]
    return [i-1 for i in list(range(2,n+1,2))+list(range(1,n+1,2))]

def two_sat_is_unsat(clauses,num_vars):
    # Independent polynomial implication SCC oracle used ONLY by the generator.
    g=[[] for _ in range(num_vars*2)]
    rev=[[] for _ in range(num_vars*2)]
    def node(x):return (abs(x)-1)*2+(x<0)
    for c in clauses:
        if len(c)>2:raise AssertionError("cycle source is not 2-CNF")
        if not c:return True
        a=node(c[0]);b=node(c[1] if len(c)==2 else c[0])
        for x,y in ((a^1,b),(b^1,a)):
            g[x].append(y);rev[y].append(x)
    seen=bytearray(num_vars*2);order=[]
    for s in range(num_vars*2):
        if seen[s]:continue
        seen[s]=1
        stack=[(s,0)]
        while stack:
            v,i=stack[-1]
            if i<len(g[v]):
                w=g[v][i];stack[-1]=(v,i+1)
                if not seen[w]:seen[w]=1;stack.append((w,0))
            else:order.append(v);stack.pop()
    comp=[-1]*(num_vars*2)
    for s in reversed(order):
        if comp[s]>=0:continue
        group=s
        comp[s]=group
        stack=[s]
        while stack:
            v=stack.pop()
            for w in rev[v]:
                if comp[w]<0:comp[w]=group;stack.append(w)
    return any(comp[2*i]==comp[2*i+1] for i in range(num_vars))

def make(case,root):
    n=case["n"]
    domain=([(r,c) for r in range(n) for c in range(n)]
            if case["kind"]=="standard" else
            [(r,c) for r in range(n) for c in (r,(r+1)%n)])
    rng=random.Random(case["seed"])
    rng.shuffle(domain)
    symbols={point:i+1 for i,point in enumerate(domain)}
    N=len(symbols)
    rows=[[] for _ in range(n)]
    cols=[[] for _ in range(n)]
    diag1=defaultdict(list);diag2=defaultdict(list)
    for (r,c),v in symbols.items():
        rows[r].append(v)
        cols[c].append(v)
        diag1[r-c].append(v)
        diag2[r+c].append(v)
    clauses=[]
    # One queen per row, at most one per column and diagonal.
    for group in rows:
        clauses.append(tuple(group))
    for groups in [rows,cols]:
        for group in groups:
            clauses.extend((-a,-b) for a,b in itertools.combinations(group,2))
    if case["kind"]=="standard" or case["diagonals"]:
        for groups in (diag1.values(),diag2.values()):
            for group in groups:
                clauses.extend((-a,-b) for a,b in itertools.combinations(group,2))
    if case["kind"]=="standard":
        if n in (2,3):
            assert not any(
                len({r-c for r,c in enumerate(p)})==n and
                len({r+c for r,c in enumerate(p)})==n
                for p in itertools.permutations(range(n)))
        else:
            p=known_queen_solution(n)
            assert len(p)==n and len(set(p))==n
            assert len({r-c for r,c in enumerate(p)})==n
            assert len({r+c for r,c in enumerate(p)})==n
            truth={symbols[(r,c)] for r,c in enumerate(p)}
    else:
        oracle=two_sat_is_unsat(clauses,N)
        assert oracle==case["diagonals"],("cycle2 truth mismatch",n,oracle)
        if not case["diagonals"]:
            truth={symbols[(r,r)] for r in range(n)}
    if case["expected"]=="SAT":
        assert all(any((abs(v) in truth)==(v>0) for v in clause)
                   for clause in clauses),"independent queen SAT witness failed"
    else:
        assert (case["kind"]=="standard" and n in (2,3)) or (case["kind"]=="cycle2" and case["diagonals"])
    # Source byte permutation, not just variable naming conventions.
    rename=[0]+list(range(1,N+1));perm=rename[1:];rng.shuffle(perm);rename[1:]=perm
    altered=[tuple(rename[abs(x)]*(1 if x>0 else -1) for x in clause)
             for clause in clauses]
    rng.shuffle(altered)
    if case["expected"]=="SAT":
        shuffled_true={rename[v] for v in truth}
        assert all(any((abs(lit) in shuffled_true)==(lit>0) for lit in clause)
                   for clause in altered),"permuted original-CNF SAT witness invalid"
    filepath=root/(case["id"]+".cnf")
    sha=hashlib.sha256()
    with filepath.open("wb") as f:
        def emit(b):sha.update(b);f.write(b)
        emit(f"p cnf {N} {len(altered)}\n".encode())
        for clause in altered:emit((" ".join(map(str,clause))+" 0\n").encode())
    return dict(**case,variables=N,clauses=len(altered),bytes=filepath.stat().st_size,
                sha256=sha.hexdigest(),witness_verified=case["expected"]=="SAT",
                unsat_independent_oracle=("2SAT-SCC" if case["kind"]=="cycle2" and case["diagonals"]
                                           else "exhaustive queen permutations" if case["expected"]=="UNSAT" else None),
                constraints=("row,column,diagonal" if case["kind"]=="standard" or case.get("diagonals") else "row,column"),
                source_class="synthetic_permuted_queen_CNFs_not_official_blind")

def freeze(shard,out):
    selected=[case for i,case in enumerate(CASES) if i%2==shard]
    records=[]
    for c in selected:
        r=make(c,out);records.append(r)
        print("QUEEN_SOURCE "+json.dumps(r,sort_keys=True),flush=True)
    frozen=dict(protocol="DRNAS_QUEEN_STANDARD_AND_DIAGONAL_CYCLE2_V1",
                shard=shard,preregistered=CASES,cases=records)
    (out/"frozen.json").write_text(json.dumps(frozen,indent=2)+"\n")
    return frozen
