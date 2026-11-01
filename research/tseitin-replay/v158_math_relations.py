#!/usr/bin/env python3
"""DRNAS V15.8 mathematical relations preflight, detection ONLY (never SAT/UNSAT).
Read each clause once. Exact XOR parity blocks (width 2..6), binary 2-SAT
implications and syntactic Hall candidates. Never claim an unverified theorem.
Output JSON with counts and relations suitable for an experimental selector.
"""
import argparse,collections,json,time
from pathlib import Path

def read_cnf(path):
    n=None; declared=None; cls=[];pending=[]
    for raw in Path(path).read_text().splitlines():
        l=raw.strip()
        if not l or l.startswith('c'):continue
        if l.startswith('p '):
            parts=l.split()
            if len(parts)!=4 or parts[1]!='cnf' or n is not None:raise ValueError('bad DIMACS header')
            n=int(parts[2]);declared=int(parts[3])
            if n<1 or n>500000 or declared<0:raise ValueError('invalid header')
            continue
        if l.startswith('%'):break
        if n is None:raise ValueError('missing header')
        for word in l.split():
            lit=int(word)
            if abs(lit)>n:raise ValueError('invalid literal')
            if lit:pending.append(lit)
            else:
                cls.append(tuple(pending));pending=[]
                if len(cls)>declared:raise ValueError('too many clauses')
    if pending or n is None or len(cls)!=declared:raise ValueError('clause count mismatch')
    return n,cls

def relations(n,clauses):
    patterns=collections.defaultdict(set)
    binary_edges=collections.defaultdict(set)
    pos_alo=[];negative_binary=[]
    units=0;binary=0;xor=collections.Counter();partial_xor=collections.Counter()
    for cl in clauses:
        if len(cl)==1:units+=1
        if len(cl)==2:
            binary+=1
            a,b=cl
            binary_edges[-a].add(b);binary_edges[-b].add(a)
            if a<0 and b<0 and a!=b:negative_binary.append(tuple(sorted((-a,-b))))
        if 3<=len(cl)<=32 and all(v>0 for v in cl):pos_alo.append(frozenset(cl))
        if 2<=len(cl)<=6:
            support=tuple(sorted(abs(x) for x in cl))
            if len(set(support))!=len(cl):continue
            mask=sum(1<<j for j,v in enumerate(support) if -v in cl)
            patterns[support].add(mask)
    xor_relations=[]
    for support,masks in patterns.items():
        width=len(support);size=1<<width
        allowed=[i for i in range(size) if i not in masks]
        if not allowed:continue
        parity={i.bit_count()%2 for i in allowed}
        if len(parity)==1:
            # Every assignment surviving clauses on this support has fixed
            # XOR parity. This is an exact logical implication, not a guess.
            rhs=next(iter(parity))
            if len(masks)>=size//2:
                xor_relations.append({"vars":support,"rhs":rhs,"patterns":len(masks),
                                      "full_half":len(masks)==size//2})
                xor[width]+=1
        elif len(masks)>=2:partial_xor[width]+=1
    # Syntactic Hall candidate: each positive clause means at least one
    # option; negatives identify pairwise incompatibilities. No unsupported
    # claim that options share an equivalence/resource group.
    hall_pairs=len(set(negative_binary))
    hall_candidates=sum(1 for cl in pos_alo if any(a in cl or b in cl for a,b in negative_binary))
    n_edges=sum(map(len,binary_edges.values()))
    signals={"units":units,"binary_clauses":binary,"implication_edges":n_edges,
       "positive_alo":len(pos_alo),"negative_amo":hall_pairs,
       "hall_alo_candidates":hall_candidates,
       "exact_xor_equations":len(xor_relations),
       "xor_widths":dict(sorted(xor.items())),
       "partial_same_support":dict(sorted(partial_xor.items()))}
    # Weighted sound preflight chooses WHAT to attempt, not SAT status.
    gate={"unit":units>0,
          "binary_scc":binary>=2,
          "affine_exact":bool(xor_relations),
          "hall_check":hall_candidates>=3 and hall_pairs>=3}
    return {"variables":n,"clauses":len(clauses),"signals":signals,
            "gate":gate,"xor_relations":xor_relations[:24],
            "warning":"Hall is a candidate only; verify independently against original CNF before any SAT/UNSAT conclusion"}

def main():
    p=argparse.ArgumentParser();p.add_argument("cnf");a=p.parse_args()
    t=time.perf_counter();n,clauses=read_cnf(a.cnf)
    result=relations(n,clauses);result["analysis_seconds"]=round(time.perf_counter()-t,8)
    print("DRNAS_RELATIONS "+json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
