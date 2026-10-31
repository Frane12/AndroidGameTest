#!/usr/bin/env python3
"""Regression and exhaustive truth-table checks for NeuroFlow 0.3."""
from itertools import product
import random
from neuroflow_v03 import NeuroFlowPolicy,renamable_horn
from drnas_np_lab import normalize,check,solve_horn,xor_to_cnf

def groundtruth(n,clauses):
    return any(check(clauses,bits) for bits in product((False,True),repeat=n))

def run():
    rng=random.Random(20261031);count=0;recognized=0
    for n in range(1,10):
        for _ in range(100):
            clauses=normalize(n,[tuple((v if rng.random()<0.5 else -v)
                for v in rng.sample(range(1,n+1),rng.randint(0,min(n,4))))
                for _ in range(rng.randint(0,24))])
            expected='SAT' if groundtruth(n,clauses) else 'UNSAT'
            candidate,reason,_=renamable_horn(n,clauses,max_pairs=50000)
            if candidate is not None:
                recognized+=1
                flips,transformed=candidate
                assert all(sum(l>0 for l in c)<=1 for c in transformed)
                status,model=solve_horn(n,transformed)
                if model is not None:model=[bool(x)^bool(f) for x,f in zip(model,flips)]
                assert status==expected,(n,clauses,status,expected)
                if model is not None:assert check(clauses,model)
            for mode in ('adaptive','shadow','off'):
                p=NeuroFlowPolicy(mode,probe_cap_ms=30)
                r=p.solve(n,clauses,budget=0.4)
                assert r.status==expected,(n,mode,clauses,r.status,expected)
                assert r.model_valid
            count+=1
    print(f'PASS: {count} exhaustive random CNFs; renamable Horn recognized {recognized} cases',flush=True)
    for n in (12,24,60):
        flips=[bool(rng.getrandbits(1)) for _ in range(n)]
        clauses=[]
        for _ in range(n*3):
            vs=rng.sample(range(1,n+1),3)
            pos=rng.randrange(4)
            horn=[v if i==pos else -v for i,v in enumerate(vs)]
            clauses.append(tuple(-l if flips[abs(l)-1] else l for l in horn))
        cf=normalize(n,clauses)
        assert renamable_horn(n,cf)[0] is not None
        r=NeuroFlowPolicy('adaptive',probe_cap_ms=25).solve(n,cf,budget=1.5)
        assert r.status in ('SAT','UNSAT') and r.model_valid
        assert r.method=='renamable Horn + 2-SAT flips',r.method
    print('PASS: constructed 12-,24-,60-variable renamable Horn cases',flush=True)
    clauses=xor_to_cnf((1,2,3),0)+xor_to_cnf((1,2,3),1)
    assert NeuroFlowPolicy('adaptive',probe_cap_ms=25).solve(3,clauses,budget=1).status=='UNSAT'
    print('PASS: GF2 fallback preserves XOR contradiction',flush=True)
if __name__=='__main__':run()
