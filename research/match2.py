#!/usr/bin/env python3
"""MATCH2: bounded, original-CNF capacitated Hall proof producer.
Only direct positive ALO jobs, negative resource-forbidden tuples and
negative unit exclusions. This is not an arbitrary BDD/PB decoder.
"""
import hashlib,itertools,json,math
from collections import defaultdict
from pathlib import Path

FORMAT="DRNAS-MATCH2-CAPACITATED-HALL-V1"
MAX_SELECTORS=128
MAX_TUPLES=50000

def parse(raw):
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        tokens=line.split()
        if not tokens or tokens[0]=="c":continue
        if tokens[0]=="p":
            if nv is not None or len(tokens)!=4 or tokens[1]!="cnf":
                raise ValueError("invalid header")
            nv,nc=int(tokens[2]),int(tokens[3])
            if not(0<=nv<=100000 and 0<=nc<=200000):raise ValueError("input out of scope")
            continue
        if nv is None:raise ValueError("header missing")
        for word in tokens:
            lit=int(word)
            if abs(lit)>nv:raise ValueError("literal out of range")
            if lit==0:clauses.append(tuple(pending));pending=[]
            else:pending.append(lit)
    if nv is None or pending or len(clauses)!=nc:raise ValueError("incomplete DIMACS")
    return nv,clauses

def source_groups(clauses):
    candidates=[c for c in clauses if 2<=len(c)<=16 and len(set(c))==len(c) and all(v>0 for v in c)]
    if len(candidates)<2 or len(candidates)>40:return []
    used=set()
    for c in candidates:
        if not used.isdisjoint(c):return []
        used.update(c)
    if len(used)>MAX_SELECTORS:return []
    return [list(c) for c in candidates]

def components(groups,clauses):
    job={v:j for j,g in enumerate(groups) for v in g}
    parent={v:v for v in job}
    def root(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def join(a,b):
        x,y=root(a),root(b)
        if x!=y:parent[max(x,y)]=min(x,y)
    for clause in clauses:
        if not(2<=len(clause)<=8 and all(v<0 and -v in job for v in clause)):
            continue
        if len({job[-lit] for lit in clause})!=len(clause):continue
        for v in clause[1:]:join(-clause[0],-v)
    parts=defaultdict(list)
    for v in sorted(job):parts[root(v)].append(v)
    return list(parts.values())

def find_proof(groups,resources,clauses):
    source={frozenset(c) for c in clauses}
    job={v:j for j,g in enumerate(groups) for v in g}
    active={v for v in job if frozenset((-v,)) not in source}
    capacities=[];num_checked=0
    for r in resources:
        vs=[v for v in r if v in active]
        upper=len({job[v] for v in vs})
        cap=upper
        for q in range(1,min(4,upper)):
            if math.comb(len(vs),q+1)>MAX_TUPLES:break
            complete=True
            for t in itertools.combinations(vs,q+1):
                if len({job[v] for v in t})!=len(t):continue
                num_checked+=1
                if num_checked>MAX_TUPLES:return None
                if frozenset(-v for v in t) not in source:
                    complete=False
                    break
            if complete:
                cap=q
                break
        capacities.append(cap)
    n=len(groups)
    if n>18:return None
    for k in range(1,n+1):
        for subset in itertools.combinations(range(n),k):
            S=set(subset);bound=0
            for r,cap in zip(resources,capacities):
                choices={job[v] for v in r if v in active and job[v] in S}
                bound+=min(cap,len(choices))
                if bound>=k:break
            if bound<k:
                return {"status":"UNSAT_UNCHECKED","method":"MATCH-2",
                    "groups":groups,"resources":resources,"capacities":capacities,
                    "hall_jobs":list(subset),"capacity_bound":bound,
                    "deficiency":k-bound,"checked_tuples":num_checked}
    return None

def prove(raw):
    doc={"format":FORMAT,"source_sha256":hashlib.sha256(raw).hexdigest(),
         "status":"UNKNOWN","method":"NONE"}
    try:
        _,clauses=parse(raw)
        if len(clauses)>50000:return doc
        groups=source_groups(clauses)
        if not groups:return doc
        proof=find_proof(groups,components(groups,clauses),clauses)
        if proof:doc.update(proof)
    except (ValueError,UnicodeError,OverflowError,RecursionError) as err:
        doc["reason"]=type(err).__name__
    return doc

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("cnf",type=Path)
    p.add_argument("--certificate",type=Path,required=True)
    args=p.parse_args()
    out=prove(args.cnf.read_bytes())
    args.certificate.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("MATCH2_PRODUCER "+json.dumps({k:v for k,v in out.items() if k not in ("groups","resources")},sort_keys=True))
