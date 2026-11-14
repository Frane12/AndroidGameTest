#!/usr/bin/env python3
"""DELTAX-HARD: reproducible medium-sized connected CNF families.

Hard cores: planted/unplanted 3-SAT, 3-regular Tseitin parity contradictions,
pigeonhole UNSAT. Two-to-four guarded nonlinear-equivalence motifs per
formula, linked into the hard core through ordinary source clauses. No solver
is told the family, target result, variable roles, or generator metadata.

This is a deliberately *synthetic* discovery set, NOT a blind SAT holdout.
"""
import hashlib
import itertools
import json
import random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MOTIF=(
    (1,-2,3),(2,-3),(-1,-3),
    (-1,-2,5),(1,-5),(2,-5),
    (-1,2,4),(1,-4),(-2,-4),
)

def motif(offset):
    return [[(1 if l>0 else -1)*(abs(l)+offset) for l in clause]
            for clause in MOTIF]

def rng3(n, density, seed, planted=False):
    rng=random.Random(seed)
    assignment=[bool(rng.randrange(2)) for _ in range(n)] if planted else None
    count=round(density*n)
    out=[]
    seen=set()
    while len(out)<count:
        vs=rng.sample(range(1,n+1),3)
        lits=tuple(v if rng.randrange(2) else -v for v in vs)
        if planted and not any((lit>0)==assignment[abs(lit)-1] for lit in lits):
            continue
        c=tuple(sorted(lits))
        if c in seen:continue
        seen.add(c);out.append(list(c))
    return out,assignment

def php(p):
    h=p-1
    idx=lambda i,j:i*h+j+1
    clauses=[]
    for i in range(p):
        clauses.append([idx(i,j) for j in range(h)])
        for j,k in itertools.combinations(range(h),2):
            clauses.append([-idx(i,j),-idx(i,k)])
    for j in range(h):
        for i,k in itertools.combinations(range(p),2):
            clauses.append([-idx(i,j),-idx(k,j)])
    return p*h,clauses

def tseitin(n):
    assert n%2==0 and n>=12
    edges={}
    adjacency=[[] for _ in range(n)]
    def add(u,v):
        key=tuple(sorted((u,v)))
        assert key not in edges
        idx=len(edges)+1
        edges[key]=idx
        adjacency[u].append(idx)
        adjacency[v].append(idx)
    for i in range(n):
        add(i,(i+1)%n) if tuple(sorted((i,(i+1)%n))) not in edges else None
    for i in range(n//2):
        add(i,i+n//2)
    assert all(len(a)==3 for a in adjacency)
    clauses=[]
    for i,vars_ in enumerate(adjacency):
        rhs=int(i==0)
        for bits in itertools.product((0,1),repeat=3):
            if sum(bits)%2==rhs:continue
            clauses.append([-v if bit else v for v,bit in zip(vars_,bits)])
    return len(edges),clauses

def guarded_join(core_n,core,seed,count=3,plant=None):
    """Use separate 5-var motifs coupled to existing core variables.

    Every motif keeps both root guards false, preserving the exact
    nonlinear local separator; integration may exploit the resulting
    short RUP resolvents. Equivalence to core variables creates
    cross-component constraints (not isolated decorative gadgets).
    """
    rng=random.Random(seed+5533)
    n=core_n+5*count
    shifted=[[(1 if l>0 else -1)*(abs(l)+5*count) for l in c] for c in core]
    cs=[]
    for i in range(count):
        off=5*i
        a=off+1;g1=off+3;g2=off+4;y=off+5
        cs+=motif(off)
        cs += [[-g1],[-g2]]
        v=5*count+1+(rng.randrange(core_n) if core_n else 0)
        # Source-entailed link y <-> core variable v
        cs += [[-y,v],[y,-v]]
        # One additional cross-module clause, nontrivial but no
        # generator label or expected solution is fed to the solver.
        if i>0:
            prev=5*(i-1)+5
            hard_idx=rng.randrange(core_n)
            third=5*count+1+hard_idx
            # In the planted family the known core witness must extend
            # to the WHOLE formula. Pick a sign satisfied by that witness.
            if plant is not None and not plant[hard_idx]:
                third=-third
            cs.append([-prev,y,third])
    cs+=shifted
    return n,cs

def generate():
    result=[]
    seedbase=20261114
    for n in (50,70,90,120,150):
        for replicate in range(2):
            seed=seedbase+101*n+replicate*971
            core,plant=rng3(n,4.23+0.09*replicate,seed,planted=True)
            nv,cs=guarded_join(n,core,seed,count=3,plant=plant)
            result.append(dict(name=f"planted3_n{n}_s{replicate}",family="planted3",
                               seed=seed,nvars=nv,clauses=cs,core_nvars=n,
                               motifs=3,expected_core="SAT_PLANTED",
                               core_planted_assignment=plant))
    for n in (46,62,84,110):
        for replicate in range(2):
            seed=seedbase+307*n+replicate*877
            core,_=rng3(n,4.25+0.12*replicate,seed,planted=False)
            nv,cs=guarded_join(n,core,seed,count=3)
            result.append(dict(name=f"random3_n{n}_s{replicate}",family="random3",
                               seed=seed,nvars=nv,clauses=cs,core_nvars=n,
                               motifs=3,expected_core="UNKNOWN",
                               core_planted_assignment=None))
    for n in (20,28,36,44,52,64):
        seed=seedbase+17*n
        core_n,core=tseitin(n)
        nv,cs=guarded_join(core_n,core,seed,count=2)
        result.append(dict(name=f"tseitin_unsat_v{n}",family="tseitin_unsat",
                           seed=seed,nvars=nv,clauses=cs,core_nvars=core_n,
                           motifs=2,expected_core="UNSAT_PARITY",
                           core_planted_assignment=None))
    for p in (6,7,8,9):
        seed=seedbase+513*p
        core_n,core=php(p)
        nv,cs=guarded_join(core_n,core,seed,count=2)
        result.append(dict(name=f"php_unsat_{p}_{p-1}",family="php_unsat",
                           seed=seed,nvars=nv,clauses=cs,core_nvars=core_n,
                           motifs=2,expected_core="UNSAT_PHP",
                           core_planted_assignment=None))
    assert len(result)==28
    return result

def write(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    listed=[]
    for case in generate():
        cs=case["clauses"]
        text=f"p cnf {case['nvars']} {len(cs)}\n"+"".join(
            " ".join(map(str,c))+" 0\n" for c in cs)
        path=folder/(case["name"]+".cnf")
        path.write_text(text)
        listed.append({k:v for k,v in case.items() if k not in ("clauses","core_planted_assignment")}|
                      {"path":str(path),"nclauses":len(cs),
                       "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    (folder/"manifest.json").write_text(json.dumps(listed,indent=2,sort_keys=True)+"\n")
    print("DELTAX_HARD_GENERATED",json.dumps({
       "sources":len(listed),
       "families":{k:sum(r["family"]==k for r in listed)
                   for k in sorted({r["family"] for r in listed})},
       "nvars_range":[min(r["nvars"] for r in listed),max(r["nvars"] for r in listed)],
       "nclauses_range":[min(r["nclauses"] for r in listed),
                         max(r["nclauses"] for r in listed)],
       "motifs_total":sum(r["motifs"] for r in listed)
    },sort_keys=True),flush=True)
    return listed

if __name__=="__main__":write("deltax_hard_inputs")
