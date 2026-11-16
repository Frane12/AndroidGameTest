#!/usr/bin/env python3
"""MATCH2-BDD-MASK1: bounded EXACT job-mask profiles from original CNF.

Source negative clauses define implicit machine acceptance sets. An exact
disjoint-cover dynamic program determines whether ALL source ALO jobs can
be covered. More precise than MATCH2 scalar capacities / IPG-BDD1 two
count classes, but exponentially sized in jobs. NOT a native BDD1 graph
extractor, C++ integration, or standard proof.

Only a separate SOURCE verifier can promote UNSAT_UNCHECKED to verified.
"""
import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path
from match2 import parse, source_groups

FORMAT="DRNAS-MATCH2-BDD-MASK1-SOURCE-V1"
MAX_JOBS=15
MAX_MACHINES=5
MAX_SOURCE_CLAUSES=5000

def infer_resources(groups,clauses):
    owner={v:j for j,g in enumerate(groups) for v in g}
    parent={v:v for v in owner}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def link(a,b):
        x,y=find(a),find(b)
        if x!=y:parent[max(x,y)]=min(x,y)
    # Inference is a heuristic only: UNSAT depends on checker revalidating
    # each literal and all SOURCE-entailed machine forbidding constraints.
    for c in clauses:
        if len(c)<2 or not all(x<0 and -x in owner for x in c):
            continue
        if len({owner[-v] for v in c})!=len(c):
            continue
        for x in c[1:]:link(-c[0],-x)
    parts=defaultdict(list)
    for v in sorted(owner):parts[find(v)].append(v)
    resources=sorted(parts.values(),key=lambda x:x[0])
    m=len(resources);n=len(groups)
    if not(2<=m<=MAX_MACHINES) or any(len(g)!=m for g in groups):
        return None
    for resource in resources:
        if len(resource)!=n or len({owner[v] for v in resource})!=n:
            return None
    return resources

def local_support(groups,resources,clauses):
    n=len(groups)
    owner={v:j for j,g in enumerate(groups) for v in g}
    total=1<<n
    clause_set=set(tuple(c) for c in clauses)
    result=[];forbidden_counts=[]
    for resource in resources:
        variables=set(resource)
        bans=set()
        for c in clauses:
            if not c or any(v>=0 or -v not in variables for v in c):
                continue
            bans.add(sum(1<<owner[-v] for v in c))
        if not bans:
            # Allowed to be unrestricted, but no information -> UNKNOWN
            return None,None
        arr=bytearray(total)
        for mask in range(total):
            arr[mask]=int(all((mask & ban)!=ban for ban in bans))
        result.append(arr)
        forbidden_counts.append(len(bans))
    return result,forbidden_counts

def exact_mask_convolution(profiles,n):
    total=1<<n
    reachable=bytearray(total)
    reachable[0]=1
    layers=[1]
    examined=0
    for profile in profiles:
        next_reach=bytearray(total)
        for mask in range(total):
            sub=mask
            while True:
                examined+=1
                if profile[sub] and reachable[mask^sub]:
                    next_reach[mask]=1
                    break
                if sub==0:
                    break
                sub=(sub-1)&mask
        reachable=next_reach
        layers.append(sum(reachable))
    return bool(reachable[total-1]),layers,examined

def prove(raw):
    out={"format":FORMAT,"source_sha256":hashlib.sha256(raw).hexdigest(),
         "status":"UNKNOWN","method":"NONE"}
    try:
        nv,clauses=parse(raw)
        if len(raw)>1000000 or len(clauses)>MAX_SOURCE_CLAUSES:return out
        groups=source_groups(clauses)
        if not(2<=len(groups)<=MAX_JOBS):return out
        original={frozenset(c) for c in clauses}
        for g in groups:
            if any(frozenset((-x,-y)) not in original for x,y in itertools.combinations(g,2)):
                return out
        resources=infer_resources(groups,clauses)
        if resources is None:return out
        profiles,ban_counts=local_support(groups,resources,clauses)
        if profiles is None:return out
        sat_relaxed,layers,ops=exact_mask_convolution(profiles,len(groups))
        out.update({"method":"MATCH2-BDD-MASK1",
          "jobs":len(groups),"machines":len(resources),
          "source_variables":nv,"source_clauses":len(clauses),
          "allowed_support_counts":[sum(a) for a in profiles],
          "machine_source_forbidden_counts":ban_counts,
          "reachable_mask_counts":layers,
          "dp_transition_checks":ops})
        if sat_relaxed:
            out["reason"]="relaxation_permits_full_assignment"
        else:
            out.update({"status":"UNSAT_UNCHECKED","reason":"exact_source_mask_cover_unreachable",
                        "groups":groups,"resources":resources})
    except (ValueError,TypeError,UnicodeError,IndexError,OverflowError,RecursionError) as exc:
        out["reason"]=type(exc).__name__
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cnf",type=Path)
    p.add_argument("--certificate",type=Path,required=True)
    a=p.parse_args()
    result=prove(a.cnf.read_bytes())
    a.certificate.parent.mkdir(parents=True,exist_ok=True)
    a.certificate.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("MATCH2_BDD_MASK1_PRODUCER "+json.dumps(
        {k:v for k,v in result.items() if k not in ("groups","resources")},sort_keys=True),flush=True)
