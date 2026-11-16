#!/usr/bin/env python3
"""Deterministic three-machine PCMAX fixtures for IPG1.

Petersen graph bin-packing gap from the previously documented
Caprara et al. inspired construction; these are ORIGINAL GENERATED
CNF bytes from this formula family, not an official SAT benchmark.
"""
import hashlib
import itertools
import json
from pathlib import Path

def pack(n,limit):
    cs=[]
    def variable(j,m): return 3*j+m+1
    for j in range(n):
        cs.append([variable(j,m) for m in range(3)])
        cs += [[-variable(j,a),-variable(j,b)]
               for a,b in itertools.combinations(range(3),2)]
    # Each machine accepts at most 'limit' jobs, using a negative source
    # clause for every (limit+1)-job forbidden subset.
    for jobs in itertools.combinations(range(n),limit+1):
        for m in range(3):
            cs.append([-variable(j,m) for j in jobs])
    return n*3,cs

def petersen():
    V=list(range(10))
    edges=[tuple(sorted((i,(i+1)%5))) for i in range(5)]
    edges += [(i,i+5) for i in range(5)]
    edges += [tuple(sorted((i+5, ((i+2)%5)+5))) for i in range(5)]
    assert len(set(edges))==15
    T=sum(3**v for v in V)
    p=[3**a+3**b for a,b in edges]
    assert sum(p)==3*T
    weights=[0]*(1<<15)
    for mask in range(1,1<<15):
        low=mask&-mask
        j=low.bit_length()-1
        weights[mask]=weights[mask^low]+p[j]
    clauses=[]
    var=lambda j,m: 3*j+m+1
    for j in range(15):
        clauses.append([var(j,m) for m in range(3)])
        clauses += [[-var(j,a),-var(j,b)] for a,b in itertools.combinations(range(3),2)]
    for mask in range(1,1<<15):
        if weights[mask]>T and all(weights[mask^(1<<j)]<=T
                                    for j in range(15) if mask>>j&1):
            jobs=[j for j in range(15) if mask>>j&1]
            clauses += [[-var(j,m) for j in jobs] for m in range(3)]
    assert len(clauses)==300
    header=('c Genuine PCMAX decision formula, no solution on 3 machines\n'
            +'c Item sizes: '+' '.join(map(str,p))+'\n'
            +f'p cnf 45 {len(clauses)}\n')
    source=header+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
    sha=hashlib.sha256(source.encode()).hexdigest()
    assert sha=="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70",sha
    return source

def main():
    root=Path('results/ipg1')
    root.mkdir(parents=True,exist_ok=True)
    path=root/'petersen3.cnf'
    path.write_bytes(petersen().encode())
    rows=[]
    for n,limit in [(5,2),(6,2),(7,2)]:
        nv,clauses=pack(n,limit)
        target=root/f'pack_{n}_3_capacity_{limit}.cnf'
        target.write_text(f'p cnf {nv} {len(clauses)}\n'
              +''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        rows.append({"name":target.name,"sha":hashlib.sha256(target.read_bytes()).hexdigest(),
                     "expected":"SAT" if n<=3*limit else "UNSAT"})
    rows.insert(0,{"name":path.name,"sha":hashlib.sha256(path.read_bytes()).hexdigest(),
                   "expected":"UNSAT"})
    (root/'manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
    print("IPG1_FIXTURES "+json.dumps(rows,sort_keys=True))
if __name__=="__main__":
    main()
