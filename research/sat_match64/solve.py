#!/usr/bin/env python3
"""Stand-alone clause-derived SAT model constructor: no CDCL dependency."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"sat_match1"))
from model import construct_sat,parse_cnf,verify

def main():
    if len(sys.argv)!=2:
        print("usage: python3 solve.py source.cnf",file=sys.stderr);return 2
    begin=time.perf_counter()
    parsed,reason=parse_cnf(sys.argv[1])
    if parsed is None:
        print("s UNKNOWN");return 0
    n,clauses=parsed
    status,model,meta=construct_sat(n,clauses)
    if status!="SAT":
        print("s UNKNOWN");return 0
    assert verify(n,clauses,model)
    print("s SATISFIABLE")
    for pos in range(0,n,20):
        print("v "+" ".join(str(i+1 if model[i] else -(i+1))
                           for i in range(pos,min(pos+20,n)))+" 0")
    print("c MATCH1_INTERNAL_S %.9f"%(time.perf_counter()-begin),file=sys.stderr)
    return 10

if __name__=="__main__":sys.exit(main())
