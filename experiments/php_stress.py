#!/usr/bin/env python3
"""Reproducible metamorphic tests for php_subcore.cpp.
Compile first: g++ -O2 -std=c++17 experiments/php_subcore.cpp -o php_subcore
Run: python3 experiments/php_stress.py ./php_subcore
"""
import random, subprocess, sys

def php(n, holes, extra, seed):
    rng=random.Random(seed)
    rows=[[i*holes+j+1 for j in range(holes)] for i in range(n)]
    clauses=[r[:] for r in rows]
    clauses += [[-rows[i][j],-rows[k][j]]
                for j in range(holes) for i in range(n) for k in range(i)]
    v=n*holes
    if extra:
        clauses += [[v+i+1,-rows[i%n][i%holes]] for i in range(2*n)]
        v+=2*n
    perm=list(range(1,v+1));rng.shuffle(perm)
    clauses=[[(-1 if x<0 else 1)*perm[abs(x)-1] for x in c] for c in clauses]
    rng.shuffle(clauses)
    return v,clauses

def invoke(exe,v,cs):
    data=f'p cnf {v} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)
    p=subprocess.run([exe],input=data,text=True,capture_output=True,timeout=30)
    if p.returncode not in (0,20):
        raise RuntimeError(f'bad exit {p.returncode}: {p.stderr}')
    return p.stdout.strip()

def main(exe):
    count=0
    for n in (4,8,16,32):
        for seed in range(20):
            v,cs=php(n,n-1,True,seed)
            assert invoke(exe,v,cs)=='s UNSATISFIABLE',(n,seed)
            count+=1
    for n in (4,8,16):
        for seed in range(20):
            v,cs=php(n,n,True,seed)
            assert invoke(exe,v,cs)=='s UNKNOWN',('SAT',n,seed)
            count+=1
    print(f'PASS {count} metamorphic cases (80 UNSAT + 60 SAT controls)')
if __name__=='__main__':
    main(sys.argv[1] if len(sys.argv)>1 else './php_subcore')
