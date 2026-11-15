#!/usr/bin/env python3
"""Pre-registered random blocked N-Queens CNF phase sweep, with planted SAT controls.

This is an intentionally source-blind, RETROSPECTIVE SYNTHETIC set, not official
benchmark originals. Random blocked boards have k allowed squares per row, with
at least TWO allowed squares in each column to avoid trivial column starvation.
The source selection/rejection never calls a SAT solver. Unknown cases have no
SAT/UNSAT label until a full independently verified model or proof is obtained.

Full original N-Queens rules: exactly one square per row, at most one per
column, at most one per each diagonal. The output uses n^2 original variables;
blocked squares contribute negative unit clauses. All variable numbers and
clauses are independently shuffled after source freeze selection.
"""
import hashlib
import itertools
import json
import random
from collections import defaultdict
from pathlib import Path

SIZES=(20,28,40,56)
DEGREES=(4,6,9,12,16)
PLANTED_DEGREES={20:6,28:7,40:9,56:12}
CASES=[]
for n in SIZES:
    for k in DEGREES:
        CASES.append(dict(id=f"r{n}k{k:02}",family="random-blocked",
                          n=n,degree=k,seed=2026111500+n*31+k*131,
                          label="UNKNOWN"))
    CASES.append(dict(id=f"p{n}",family="planted-control",
                      n=n,degree=PLANTED_DEGREES[n],
                      seed=2026111599+n*97,label="WITNESS_SAT"))
assert len(CASES)==24 and len({c["id"] for c in CASES})==24

def known_solution(n):
    if n%6==2:
        p=[i-1 for i in list(range(2,n+1,2))+[3,1]+
           list(range(7,n+1,2))+[5]]
    elif n%6==3:
        p=[i-1 for i in list(range(4,n+1,2))+[2]+
           list(range(5,n+1,2))+[1,3]]
    else:
        p=[i-1 for i in list(range(2,n+1,2))+list(range(1,n+1,2))]
    assert len(p)==n and len(set(p))==n
    assert len({r-c for r,c in enumerate(p)})==n
    assert len({r+c for r,c in enumerate(p)})==n
    return p

def choose_board(case):
    n,k=case["n"],case["degree"]
    rng=random.Random(case["seed"])
    planted=case["family"]=="planted-control"
    solution=known_solution(n) if planted else None
    attempt=0
    while True:
        attempt+=1
        assert attempt<=5000,(case,"Could not sample balanced blocked board")
        allowed=[]
        for row in range(n):
            if planted:
                keep=solution[row]
                picks=set(rng.sample([c for c in range(n) if c!=keep],k-1))
                picks.add(keep)
            else:
                picks=set(rng.sample(range(n),k))
            allowed.append(picks)
        column_counts=[sum(c in allowed[r] for r in range(n)) for c in range(n)]
        if min(column_counts)>=2:
            return allowed,solution,attempt,min(column_counts),max(column_counts),rng

def generate(case,out):
    n=case["n"]
    allowed,solution,attempt,min_col,max_col,rng=choose_board(case)
    clauses=[]
    def v(r,c):return r*n+c+1
    rows=[[v(r,c) for c in range(n)] for r in range(n)]
    cols=[[v(r,c) for r in range(n)] for c in range(n)]
    d1=defaultdict(list);d2=defaultdict(list)
    for r in range(n):
        for c in range(n):
            d1[r-c].append(v(r,c))
            d2[r+c].append(v(r,c))
    clauses.extend(tuple(row) for row in rows)
    for collection in (rows,cols,list(d1.values()),list(d2.values())):
        for group in collection:
            clauses.extend((-a,-b) for a,b in itertools.combinations(group,2))
    blocked=0
    for r in range(n):
        for c in range(n):
            if c not in allowed[r]:
                clauses.append((-v(r,c),))
                blocked+=1
    witness=None
    if solution is not None:
        witness={v(r,c) for r,c in enumerate(solution)}
        assert all(any((abs(l) in witness)==(l>0) for l in clause)
                   for clause in clauses),"Planted solution violates original CNF"
    renumber=list(range(1,n*n+1))
    rng.shuffle(renumber)
    renumber=[0]+renumber
    shuffled=[tuple(renumber[abs(l)]*(1 if l>0 else -1) for l in clause)
              for clause in clauses]
    rng.shuffle(shuffled)
    if witness is not None:
        new_truth={renumber[x] for x in witness}
        assert all(any((abs(l) in new_truth)==(l>0) for l in clause)
                   for clause in shuffled),"Planted witness fails permuted CNF"
    out.mkdir(parents=True,exist_ok=True)
    dest=out/(case["id"]+".cnf")
    digest=hashlib.sha256()
    with dest.open("wb") as file:
        def write(b):file.write(b);digest.update(b)
        write(f"p cnf {n*n} {len(shuffled)}\n".encode())
        for clause in shuffled:
            write((" ".join(map(str,clause))+" 0\n").encode())
    assert dest.stat().st_size<20_000_000
    return dict(**case,variables=n*n,clauses=len(shuffled),bytes=dest.stat().st_size,
                sha256=digest.hexdigest(),blocked_squares=blocked,
                blocked_density=round(blocked/(n*n),6),
                resample_attempts=attempt,min_column_choices=min_col,
                max_column_choices=max_col,sat_witness_source_verified=bool(witness),
                known_truth="SAT" if witness else "UNKNOWN",
                cnf_kind="full_permuted_row_column_diagonal_queens",
                frozen_before_solver=True)
def freeze(shard,out):
    assert shard in range(4)
    selected=[c for i,c in enumerate(CASES) if i%4==shard]
    cases=[]
    for c in selected:
        row=generate(c,out)
        cases.append(row)
        print("BLOCKED_QUEEN_SOURCE "+json.dumps(row,sort_keys=True),flush=True)
    metadata=dict(protocol="BLOCKED_NQUEENS_PHASE_SYNTH_V1",
                  cases=cases,shard=shard,all_preregistered=CASES,
                  selection="row-degree fixed, min column choices>=2, no SAT solver used",
                  no_post_solver_rejection=True,
                  not_competition_blind=True)
    (out/"frozen.json").write_text(json.dumps(metadata,indent=2)+"\n")
    return metadata

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--shard",required=True,type=int,choices=range(4))
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    if a.out.exists():raise SystemExit("output exists")
    freeze(a.shard,a.out)
