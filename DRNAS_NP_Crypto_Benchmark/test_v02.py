#!/usr/bin/env python3
"""v0.2 exactness and differential tests; independent of benchmarks."""
from itertools import product
import random
from drnas_np_lab import normalize,cancel_complementary_pairs,check,solve,detect_xor3
from experiment_v02 import sample_instance
from experiment_masked import mask

def validate_rewriting():
    rng=random.Random(314159);tested=0
    for n in range(1,9):
        for _ in range(65):
            clauses=[]
            for _ in range(22):
                length=rng.randint(0,min(n,4))
                selected=rng.sample(range(1,n+1),length)
                clauses.append(tuple(v if rng.getrandbits(1) else -v for v in selected))
            if n>=2:
                common=rng.sample(range(1,n+1),rng.randint(0,min(2,n-1)))
                pivot=next(v for v in range(1,n+1) if v not in common)
                base=tuple(v if rng.getrandbits(1) else -v for v in common)
                clauses.extend([base+(pivot,),base+(-pivot,)])
            clauses=normalize(n,clauses)
            changed,steps=cancel_complementary_pairs(n,clauses,max_rounds=5)
            for bits in product((False,True),repeat=n):
                assert check(clauses,bits)==check(changed,bits),(n,clauses,changed,bits)
            tested+=1
    print(f"PASS: {tested} CNFs with exhaustive rewriting truth-table equivalence")

def validate_solver():
    rng=random.Random(271828);tested=0
    for n in range(3,11):
        for _ in range(60):
            clauses=[]
            for _ in range(rng.randint(1,24)):
                vs=rng.sample(range(1,n+1),rng.randint(0,min(4,n)))
                clauses.append(tuple(v if rng.getrandbits(1) else -v for v in vs))
            cnf=normalize(n,clauses)
            brute=any(check(cnf,v) for v in product((False,True),repeat=n))
            ans=solve(n,cnf,budget=None)
            assert ans.status==("SAT" if brute else "UNSAT"),(n,cnf,ans)
            tested+=1
    print(f"PASS: {tested} random SAT/UNSAT, brute-force reference")

def validate_masked():
    for v in (11,21,41,81):
        for family in ("SAT","UNSAT"):
            n,c=sample_instance(v,30400+v,satisfiable=(family=="SAT"))
            new_n,masked,k=mask(n,c)
            eq0,_=detect_xor3(masked)
            assert len(eq0)==0
            r=solve(new_n,masked,budget=None)
            assert r.status==family,(family,v,r)
            assert r.resolved_pairs>=k and r.interface==3
    print("PASS: 8 camouflaged parity systems")

def validate_satlib_eof():
    """SATLIB original files end with a percent terminator and trailing zero."""
    import tempfile
    from pathlib import Path
    from drnas_np_lab import read_dimacs
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'original.cnf'
        p.write_text("""c SATLIB original suffix
p cnf 2 1
1 2 0
%
0
""")
        n, clauses=read_dimacs(p)
        assert n==2 and clauses==[(1,2)], (n,clauses)
        assert solve(n,clauses,budget=1).status=='SAT'
    print('PASS: SATLIB percent EOF does not inject an empty clause')

if __name__=="__main__":
    validate_satlib_eof()
    validate_rewriting();validate_solver();validate_masked()
