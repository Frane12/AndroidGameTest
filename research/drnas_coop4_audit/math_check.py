#!/usr/bin/env python3
"""Audit the COOP4 heuristic mathematically, without a SAT outcome oracle."""
from itertools import combinations
def rank(points,k):
    if not points:return 0
    piv={}
    for p in points:
        x=p^points[0]
        while x:
            bit=x.bit_length()-1
            if bit in piv:x^=piv[bit]
            else:piv[bit]=x;break
    return len(piv)
def score(points,k,j):
    lo=[p for p in points if not (p>>j)&1]
    hi=[p for p in points if (p>>j)&1]
    if not lo or not hi:return None
    r=rank(points,k);r0=rank(lo,k);r1=rank(hi,k)
    n=len(points);n0=len(lo);n1=len(hi)
    d=2**r-n
    d0=2**r0-n0
    d1=2**r1-n1
    observed=(d-d0-d1)/2**r
    reduced=(2**r-2**r0-2**r1)/2**r
    assert observed==reduced
    return {"mask":1<<j,"score":observed,"N0":n0,"N1":n1,"rank":r,"rank0":r0,"rank1":r1}
def main():
    example=(0,1,2,5)
    a=score(example,3,0);b=score(example,3,1)
    assert a["score"]==.5 and (a["N0"],a["N1"])==(2,2)
    assert b["score"]==.375 and (b["N0"],b["N1"])==(3,1)
    count=0;dominates=0
    for size in range(3,8):
        for pts in combinations(range(8),size):
            r=rank(pts,3)
            if len(pts)==2**r:continue
            trials=[score(pts,3,j) for j in range(3)]
            trials=[t for t in trials if t and t["score"]>0]
            if len(trials)<2:continue
            count+=1
            top=max(trials,key=lambda t:t["score"])
            if any(t["score"]<top["score"] and min(t["N0"],t["N1"])<min(top["N0"],top["N1"]) for t in trials):
                dominates+=1
    assert dominates>0
    import json
    print("COOP4_INSTRUCTION_MATH_AUDIT "+json.dumps({
        "exact_support_example":[format(x,"03b") for x in example],
        "current_top_heuristic":a,"more_unbalanced_alternative":b,
        "tested_nontrivial_3bit_functions":count,
        "functions_with_score_vs_split_disagreement":dominates,
        "conclusion":"affine-hull rank proxy is not actual remaining-solution reduction"
    },sort_keys=True))
if __name__=="__main__":main()
