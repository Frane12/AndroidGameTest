#!/usr/bin/env python3
import argparse,sys
from drnas_np_lab import read_dimacs, solve
p=argparse.ArgumentParser()
p.add_argument("cnf");p.add_argument("--budget",type=float,default=2.0)
a=p.parse_args()
n,clauses=read_dimacs(a.cnf)
r=solve(n,clauses,mode="auto",budget=a.budget)
if r.status=="SAT":
    if r.assignment is None or len(r.assignment)!=n: sys.exit(1)
    print("s SATISFIABLE")
    print("v "+" ".join(str(i+1 if v else -(i+1)) for i,v in enumerate(r.assignment))+" 0")
    sys.exit(10)
if r.status=="UNSAT":
    print("s UNSATISFIABLE")
    sys.exit(20)
if r.status=="LIMIT":
    print("s UNKNOWN")
    sys.exit(0)
print("bad solver status",r.status,file=sys.stderr)
sys.exit(1)
