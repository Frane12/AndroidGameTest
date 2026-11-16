#!/usr/bin/env python3
"""Separate MATCH2 checker: re-read ORIGINAL CNF and recheck every capacity cut.
Proof form is project-specific; it is NOT DRAT/LRAT/VeriPB.
"""
import hashlib,itertools,json,math
from pathlib import Path

FORMAT="DRNAS-MATCH2-CAPACITATED-HALL-V1"

def parse_source(raw):
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        parts=line.split()
        if not parts or parts[0]=="c":continue
        if parts[0]=="p":
            if nv is not None or len(parts)!=4 or parts[1]!="cnf":raise ValueError("header")
            nv,nc=int(parts[2]),int(parts[3])
            if not(0<=nv<=100000 and 0<=nc<=200000):raise ValueError("too large")
            continue
        if nv is None:raise ValueError("header missing")
        for word in parts:
            x=int(word)
            if abs(x)>nv:raise ValueError("literal outside source")
            if x==0:clauses.append(frozenset(pending));pending=[]
            else:pending.append(x)
    if nv is None or pending or len(clauses)!=nc:raise ValueError("incomplete source")
    return nv,set(clauses)

def verify(raw,cert):
    if cert.get("format")!=FORMAT or cert.get("method")!="MATCH-2" or cert.get("status")!="UNSAT_UNCHECKED":
        raise ValueError("unsupported proof")
    if cert.get("source_sha256")!=hashlib.sha256(raw).hexdigest():
        raise ValueError("source SHA mismatch")
    nvars,source=parse_source(raw)
    groups=cert.get("groups");resources=cert.get("resources")
    caps=cert.get("capacities");S=cert.get("hall_jobs")
    if not isinstance(groups,list) or not 2<=len(groups)<=40:
        raise ValueError("invalid ALO groups")
    if not isinstance(resources,list) or not resources or not isinstance(caps,list) or len(caps)!=len(resources):
        raise ValueError("invalid resource partition")
    if not isinstance(S,list) or not S or any(type(j)!=int or not 0<=j<len(groups) for j in S) or len(set(S))!=len(S):
        raise ValueError("invalid job subset")
    varjob={}
    for j,g in enumerate(groups):
        if not isinstance(g,list) or not 2<=len(g)<=16 or len(set(g))!=len(g):
            raise ValueError("invalid job group")
        if frozenset(g) not in source:raise ValueError("missing original ALO")
        for v in g:
            if type(v)!=int or not 0<v<=nvars or v in varjob:
                raise ValueError("reused selector")
            varjob[v]=j
    if len(varjob)>128:raise ValueError("too many selectors")
    active={v for v in varjob if frozenset((-v,)) not in source}
    seen=set();eligible_by_resource=[];checks=0
    for vs,cap in zip(resources,caps):
        if not isinstance(vs,list) or not vs or len(set(vs))!=len(vs) or any(type(v)!=int or v not in varjob for v in vs):
            raise ValueError("invalid resource elements")
        if seen.intersection(vs):raise ValueError("resource overlap")
        seen.update(vs)
        available=[v for v in vs if v in active]
        jobs={varjob[v] for v in available}
        if type(cap)!=int or not 0<=cap<=len(jobs):
            raise ValueError("unjustified cap")
        if cap==0 and available:raise ValueError("nonempty zero-cap resource")
        if cap>0 and cap<len(jobs):
            if math.comb(len(available),cap+1)>50000:
                raise ValueError("proof exceeds tuple budget")
            for t in itertools.combinations(available,cap+1):
                if len({varjob[v] for v in t})!=len(t):continue
                checks+=1
                if checks>50000:raise ValueError("total proof budget")
                if frozenset(-v for v in t) not in source:
                    raise ValueError("missing source forbidden tuple")
        eligible_by_resource.append(jobs)
    if seen!=set(varjob):raise ValueError("not all ALO selectors mapped")
    subset=set(S)
    bound=sum(min(q,len(jobs&subset)) for q,jobs in zip(caps,eligible_by_resource))
    if bound>=len(S) or cert.get("capacity_bound")!=bound or cert.get("deficiency")!=len(S)-bound:
        raise ValueError("no certified Hall deficiency")
    return {"status":"MATCH2_SOURCE_CAPACITATED_HALL_VERIFIED",
            "hall_jobs":len(S),"resource_capacity_sum":bound,
            "deficiency":len(S)-bound,"resources":len(resources),
            "source_tuples_rechecked":checks}

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("cnf",type=Path);p.add_argument("certificate",type=Path);a=p.parse_args()
    try:
        result=verify(a.cnf.read_bytes(),json.loads(a.certificate.read_text()))
        print("MATCH2_CERTIFIED "+json.dumps(result,sort_keys=True))
    except (ValueError,TypeError,KeyError,IndexError,OverflowError) as err:
        print("MATCH2_REJECTED "+str(err));raise SystemExit(1)
