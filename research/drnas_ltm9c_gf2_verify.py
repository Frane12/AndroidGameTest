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
    equations=[]
    for ids,actual in groups.items():
        if len(groups)>max_groups:return False
        k=len(ids)
        if len(actual)!=(1<<(k-1)):continue
        parities=set()
        masks=set()
        for c in actual:
            mask=sum(1<<j for j,v in enumerate(ids) if -v in c)
            masks.add(mask);parities.add(mask.bit_count()%2)
        if len(parities)!=1 or len(masks)!=(1<<(k-1)):continue
        # A clause forbids its unique all-false assignment.
        # For negative-literal mask M, forbidden truth parity is parity(M).
        # Thus the XOR constraint has the *opposite* parity.
        rhs=1-next(iter(parities))
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
    assert not verify(xor([1,2,3],0))
    assert verify(xor([1,2],0)+xor([2,3],0)+xor([1,3],1))
    assert not verify(xor([1,2],0)+xor([2,3],0)+xor([1,3],0))
    print('LTM9C_GF2_INDEPENDENT_SELFTEST_PASS')
if __name__=='__main__':selftest()
