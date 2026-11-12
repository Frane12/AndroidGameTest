#!/usr/bin/env python3
"""Independent CNF-based GF(2) contradiction checker.
Recognizes a *complete* truth-table CNF encoding of a small XOR equation,
then uses exact binary Gaussian elimination. This is an independently
reconstructed contradiction, NOT a solver-produced DRAT/LRAT proof.
"""
from collections import defaultdict
from itertools import combinations
def verify(clauses,max_width=4,max_groups=4000):
    groups=defaultdict(set)
    for clause in clauses:
        if not (2<=len(clause)<=max_width):continue
        ids=tuple(sorted(abs(x) for x in clause))
        if len(set(ids))!=len(ids):continue
        groups[ids].add(tuple(sorted(clause)))
    if len(groups)>max_groups:return False
    equations=[]
    for ids,actual in groups.items():
        k=len(ids)
        # A clause with one literal per variable forbids exactly one
        # assignment: variable truth bits equal its negative-literal mask.
        masks={sum(1<<j for j,v in enumerate(ids) if -v in c) for c in actual}
        # Each *complete* forbidden parity class entails the opposite
        # XOR equation. Mixed/extra clauses are fine: entailment is
        # established only by full coverage, not the clause count.
        for forbidden_parity in (0,1):
            full={mask for mask in range(1<<k)
                  if mask.bit_count()%2==forbidden_parity}
            if not full.issubset(masks):continue
            rhs=1-forbidden_parity
            bits=sum(1<<(v-1) for v in ids)
            equations.append((bits,rhs))
    pivots={}
    for bits,rhs in equations:
        while bits:
            pivot=bits.bit_length()-1
            if pivot not in pivots:
                pivots[pivot]=(bits,rhs)
                break
            b,r=pivots[pivot];bits^=b;rhs^=r
        if not bits and rhs:return True
    return False

def selftest():
    def xor(v,parity):
        out=[]
        for mask in range(1<<len(v)):
            if mask.bit_count()%2 != parity:
                out.append([(-x if (mask>>j)&1 else x) for j,x in enumerate(v)])
        return out
    assert verify(xor([1,2,3],0)+xor([1,2,3],1))
    assert not verify(xor([1,2,3],0)+xor([1,2,3],1)[:-1])
    # A duplicated clause or irrelevant partial parity must never invent proof.
    assert not verify(xor([1,2,3],0)+xor([1,2,3],0)[:1])
    assert verify(xor([4,7,2],0)+xor([4,7,2],1))
    assert not verify(xor([1,2,3],0))
    assert verify(xor([1,2],0)+xor([2,3],0)+xor([1,3],1))
    assert not verify(xor([1,2],0)+xor([2,3],0)+xor([1,3],0))
    print('LTM9C_GF2_INDEPENDENT_SELFTEST_PASS')
if __name__=='__main__':selftest()
