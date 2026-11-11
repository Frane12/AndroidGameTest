#!/usr/bin/env python3
"""Proof-first selective GF(2) screening for DRNAS ATLAS.
Never changes CNF or asserts UNSAT without an independently checkable proof.
Recognizes only complete canonical parity encodings, not partial XOR guesses.
"""
from collections import defaultdict
from itertools import product
import random

def extract_exact_xors(clauses, max_width=5):
    groups=defaultdict(set)
    for clause in clauses:
        if not 2 <= len(clause) <= max_width: continue
        vars_=tuple(sorted(set(abs(x) for x in clause)))
        if len(vars_) != len(clause): continue
        groups[vars_].add(tuple(1 if v in clause else -1 for v in vars_))
    rows=[]
    for vs,patterns in groups.items():
        k=len(vs)
        if len(patterns)!=1<<(k-1): continue
        # Each clause forbids assignment matching the opposite of its literals.
        forbidden={tuple(0 if x==1 else 1 for x in p) for p in patterns}
        parity={sum(bits)%2 for bits in forbidden}
        if len(parity)!=1:continue
        # Every forbidden assignment is exactly one parity class.
        rhs=1-next(iter(parity))
        rows.append((vs,rhs))
    return rows

def gaussian_rank(rows):
    pivots={}
    dependent=0
    for vs,rhs in rows:
        mask=0
        for v in vs:mask^=1<<v
        r=int(rhs)
        while mask:
            p=mask.bit_length()-1
            if p not in pivots:
                pivots[p]=(mask,r);break
            m,b=pivots[p];mask^=m;r^=b
        else:
            if r: return len(pivots),dependent,True
            dependent+=1
    return len(pivots),dependent,False

def screen(clauses, max_width=5, max_clauses=25000, max_rows=1024,
           min_rows=2, min_density=0.002):
    if len(clauses)>max_clauses:
        return {"gate":"off","reason":"clause_budget","rows":0,"rank":0,"contradiction":False}
    rows=extract_exact_xors(clauses,max_width)
    density=len(rows)/max(1,len(clauses))
    if len(rows)<min_rows or density<min_density:
        return {"gate":"off","reason":"low_exact_xor_density","rows":len(rows),
                "rank":0,"contradiction":False,"density":density}
    if len(rows)>max_rows:
        return {"gate":"off","reason":"row_budget","rows":len(rows),"rank":0,
                "contradiction":False,"density":density}
    rank,dependent,contradiction=gaussian_rank(rows)
    # Contradiction is diagnostic until independently certified.
    return {"gate":"shadow","reason":"exact_xor_gaussian","rows":len(rows),
            "rank":rank,"dependent":dependent,"contradiction":contradiction,
            "density":density,"proof_status":"not_certified_no_unsat_claim"}

def parity_cnf(vars_,rhs):
    out=[]
    for bits in product((0,1),repeat=len(vars_)):
        if sum(bits)%2 != rhs:
            out.append([(-v if b else v) for v,b in zip(vars_,bits)])
    return out

def selftest():
    # Exact parity, dependent row, contradictory parity, and non-XOR controls.
    a=parity_cnf((1,2,3),0)
    assert extract_exact_xors(a)==[((1,2,3),0)]
    assert screen(a+a,min_rows=1)["rank"]==1
    inconsistent=(parity_cnf((1,2),0)+parity_cnf((2,3),0)+parity_cnf((1,3),1))
    assert screen(inconsistent,min_rows=1)["contradiction"]
    assert screen([[1,2,3],[-1,2,3]],min_rows=1)["gate"]=="off"
    r=random.Random(20261111)
    for _ in range(240):
        vs=tuple(range(1,r.randint(2,5)+1))
        rhs=r.randrange(2)
        clauses=parity_cnf(vs,rhs)
        rows=extract_exact_xors(clauses)
        assert (vs,rhs) in rows
        for bits in product((0,1),repeat=len(vs)):
            cnf=all(any((bits[abs(l)-1]==1)==(l>0) for l in c) for c in clauses)
            assert cnf==(sum(bits)%2==rhs)
    print("ATLAS_GF2_SELFTEST_PASS randomized_parity=240 contradiction_shadow_only=true")

if __name__=="__main__":selftest()
