#!/usr/bin/env python3
"""IPG2 CNF bridge: polynomial, sound, incomplete 2-type capacity abstraction.

Original DIMACS ONLY. Requires disjoint one-hot m=2/3 groups that cover
every declared variable. Source all-negative clauses yield *guaranteed*
forbidden per-machine count patterns of total size at most 3, independently
of the names or alleged durations of jobs. This establishes a conservative
relaxation: if a bounded 2-type count dynamic program cannot place every
job, the complete original CNF is UNSAT.

The job classes are heuristic and may be wrong about underlying durations:
soundness relies ONLY on the source-checked universal forbidden patterns.
No SAT result is ever returned. Unsupported structure -> UNKNOWN.
Integer arithmetic and O(n^3) pattern probes plus O(m*n^4) count DP
are polynomial (for the fixed two classes and 3-literal pattern cutoff).
No exponential 2^n subset enumeration, SAT oracle, or BDD assumption.
Certificate MUST be independently checked against identical input bytes.
This is not DRAT / LRAT / VeriPB.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import time
from collections import defaultdict

MAX_JOBS=48
MAX_VARS=144
MAX_CLAUSES=350000
PATTERN_K=3

def source(raw):
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        tok=line.split()
        if not tok or tok[0]=="c":continue
        if tok[0]=="p":
            if nv is not None or len(tok)!=4 or tok[1]!="cnf":
                raise ValueError("bad_DIMACS_header")
            nv,nc=int(tok[2]),int(tok[3])
            if nv<0 or nc<0 or nc>MAX_CLAUSES:raise ValueError("source_size_limit")
            continue
        if nv is None:raise ValueError("missing_header")
        for word in tok:
            x=int(word)
            if abs(x)>nv:raise ValueError("out_of_range_literal")
            if x:pending.append(x)
            else:
                clauses.append(tuple(pending));pending=[]
                if len(clauses)>MAX_CLAUSES:raise ValueError("clause_limit")
    if nv is None or pending or nc!=len(clauses):
        raise ValueError("source_clause_count_mismatch")
    return nv,clauses

def extract(nv,clauses):
    if nv<4 or nv>MAX_VARS:return None
    for m in (2,3):
        groups=[c for c in clauses if len(c)==m and all(x>0 for x in c)]
        n=len(groups)
        if n<3 or n>MAX_JOBS or m*n!=nv:
            continue
        own={};position={}
        okay=True
        for j,group in enumerate(groups):
            if len(set(group))!=m:okay=False;break
            for machine,v in enumerate(group):
                if v in own:okay=False;break
                own[v]=j;position[v]=machine
            if not okay:break
        if not okay or set(own)!=set(range(1,nv+1)):continue
        indexed={frozenset(c) for c in clauses}
        if any(frozenset((-a,-b)) not in indexed
               for group in groups for a,b in itertools.combinations(group,2)):
            continue
        forbids=[set() for _ in range(m)]
        for c in clauses:
            if not 1<=len(c)<=PATTERN_K or any(x>=0 for x in c):
                continue
            machine=position.get(-c[0],-1)
            if machine<0 or any(position.get(-x,-1)!=machine for x in c):
                continue
            jobs=frozenset(own[-x] for x in c)
            if len(jobs)==len(c):forbids[machine].add(jobs)
        return m,groups,forbids
    return None

def partitions(groups,forbids):
    n=len(groups);m=len(forbids)
    pairs=[set().union(*[set(f) for f in machine if len(f)==2])
           for machine in forbids]
    # Classification is purely a heuristic; source-universal clauses
    # remain the only proof premises, regardless of the class labels.
    signatures=[]
    for j in range(n):
        sig=[]
        for machine in forbids:
            for size in (2,3):
                sig.append(sum(j in f for f in machine if len(f)==size))
        signatures.append(tuple(sig))
    classes=defaultdict(list)
    for j,sig in enumerate(signatures):classes[sig].append(j)
    choices=[(tuple(range(n)),tuple())]
    if len(classes)>1:
        sorted_groups=sorted(classes.values(),key=lambda g:(-len(g),g[0]))
        for group in sorted_groups[:min(6,len(sorted_groups))]:
            a=tuple(sorted(group))
            b=tuple(j for j in range(n) if j not in set(a))
            if a and b: choices.append((a,b))
    # Additional degree-bisection to avoid depending on encoded job order.
    order=sorted(range(n),key=lambda j:(signatures[j],j))
    if n>=4:
        half=n//2
        choices.append((tuple(sorted(order[:half])),tuple(sorted(order[half:]))))
    distinct=[];seen=set()
    for a,b in choices:
        key=(a,b)
        if key not in seen:
            seen.add(key);distinct.append(key)
    return distinct

def universal_forbidden(forbids,classes):
    # Check each possible selected subset of total size <=3. When EVERY
    # subset of this count-vector violates a literal source clause, ALL
    # machines obey the resulting cardinality pattern restriction.
    a,b=classes
    a,b=tuple(a),tuple(b)
    blocked=[]
    for u in range(min(PATTERN_K,len(a))+1):
        for v in range(min(PATTERN_K-u,len(b))+1):
            if u+v==0:continue
            all_bad=True
            for s1 in itertools.combinations(a,u):
                if not all_bad:break
                for s2 in itertools.combinations(b,v):
                    sel=frozenset(s1+s2)
                    if not any(f.issubset(sel) for f in forbids):
                        all_bad=False
                        break
            if all_bad:blocked.append((u,v))
    # Retain only Pareto-minimal obstructions.
    return sorted((u,v) for u,v in blocked if not any(
        (x,y)!=(u,v) and x<=u and y<=v for x,y in blocked))

def dp_unreachable(m,na,nb,blocked):
    # A machine can use a count pair only if it is NOT prohibited by
    # a source-implied universal negative pattern. Ignoring other source
    # constraints makes the DP an over-approximation of real schedules.
    reachable={(0,0)}
    sizes=[len(reachable)]
    for k in range(m):
        no=blocked[k]
        allowed=[(a,b) for a in range(na+1) for b in range(nb+1)
                 if not any(a>=u and b>=v for u,v in no)]
        nxt=set()
        for a,b in reachable:
            for u,v in allowed:
                if a+u<=na and b+v<=nb:
                    nxt.add((a+u,b+v))
        reachable=nxt
        sizes.append(len(reachable))
    return (na,nb) not in reachable,sizes

def analyze(raw):
    started=time.monotonic()
    meta={"format":"DRNAS-IPG2-CNF-COUNT-V1",
          "source_sha256":hashlib.sha256(raw).hexdigest(),
          "status":"UNKNOWN","reason":"unsupported"}
    nv,clauses=source(raw)
    meta.update(source_variables=nv,source_clauses=len(clauses))
    e=extract(nv,clauses)
    if e is None:
        meta["reason"]="not_source_onehot_or_auxiliary_encoding"
        return meta
    m,groups,forbids=e
    meta.update(machines=m,jobs=len(groups),
                source_negative_patterns=[len(f) for f in forbids])
    for a,b in partitions(groups,forbids):
        blocked=[universal_forbidden(f,(a,b)) for f in forbids]
        unsat,rows=dp_unreachable(m,len(a),len(b),blocked)
        if unsat:
            meta.update(status="UNSAT_SOURCE_COUNT_CERTIFICATE_UNCHECKED",
                        reason="two_type_universal_forbidden_count_dp",
                        classes=[list(a),list(b)],forbidden_counts=blocked,
                        reachable_sizes=rows)
            break
    else:
        meta["reason"]="source_count_relaxation_feasible"
    meta["elapsed_s"]=round(time.monotonic()-started,7)
    return meta

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",type=pathlib.Path,required=True)
    p.add_argument("--certificate",type=pathlib.Path,required=True)
    ns=p.parse_args()
    try:
        result=analyze(ns.cnf.read_bytes())
    except (ValueError,UnicodeError,OverflowError) as err:
        result={"status":"UNKNOWN","reason":str(err)}
    ns.certificate.parent.mkdir(parents=True,exist_ok=True)
    ns.certificate.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("IPG2_CNF_BRIDGE "+json.dumps({k:v for k,v in result.items() if k not in ("classes","forbidden_counts")},sort_keys=True),flush=True)
    return 0
if __name__=="__main__":main()
