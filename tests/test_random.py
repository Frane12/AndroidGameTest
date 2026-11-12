#!/usr/bin/env python3
"""Differential brute-force tests on small CNFs; no external SAT solver used."""
import argparse
import itertools
import json
import pathlib
import random
import subprocess
import tempfile
import time

EXE=pathlib.Path(__file__).resolve().parents[1]/'build'/'drnas-x1'

def brute(n, clauses):
    for bits in itertools.product([False, True], repeat=n):
        if all(any((lit>0)==bits[abs(lit)-1] for lit in clause) for clause in clauses):
            return True
    return False

def witness(stdout,n,clauses):
    lits=[]
    for ln in stdout.splitlines():
        if ln.startswith('v '):lits.extend(int(x) for x in ln[2:].split() if x!='0')
    if len(lits)!=n or set(map(abs,lits))!=set(range(1,n+1)):
        return False
    assign={abs(x):x>0 for x in lits}
    return all(any((x>0)==assign[abs(x)] for x in clause) for clause in clauses)

def main():
    p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=1200)
    args=p.parse_args()
    rng=random.Random(11971112)
    begin=time.monotonic()
    with tempfile.TemporaryDirectory() as d:
        path=pathlib.Path(d)/'f.cnf'
        for i in range(args.cases):
            n=rng.randrange(0,11)
            clauses=[]
            for _ in range(rng.randrange(0,45)):
                width=rng.randrange(0,8) if n else 0
                clauses.append([(1 if rng.random()<.5 else -1)*rng.randint(1,n) for __ in range(width)])
            if i%23==0 and n>1:
                clauses += [[v] for v in range(1,n+1)] + [[-v for v in range(1,n+1)]]
            with open(path,'w') as f:
                f.write(f'c case {i}\np cnf {n} {len(clauses)}\n')
                for row in clauses:f.write(' '.join(map(str,row))+' 0\n')
            truth=brute(n,clauses)
            for mode in ('baseline','horizon'):
                r=subprocess.run([str(EXE),str(path),'--mode',mode,'--time','2','--stats'],text=True,capture_output=True)
                if (truth and r.returncode!=10) or (not truth and r.returncode!=20) or (truth and not witness(r.stdout,n,clauses)):
                    print('FAIL',i,n,clauses,'truth',truth,'mode',mode,'return',r.returncode,r.stdout,r.stderr)
                    raise SystemExit(1)
    print('X1_RANDOM_PASS',json.dumps({'formulas':args.cases,'modes':2,'trials':args.cases*2,'s':round(time.monotonic()-begin,3)}))
if __name__=='__main__':main()
