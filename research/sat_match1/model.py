#!/usr/bin/env python3
"""SAT-MATCH1: constructive SAT witness from clauses only, no backend solver.
Pure positive ALO + negative binary mutex CNFs; all outputs verified on source.
Failure to find matching means UNKNOWN, never UNSAT without an independent proof.
"""
from collections import defaultdict
from pathlib import Path

def parse_cnf(path, max_bytes=24_000_000, max_vars=15_000, max_clauses=130_000):
    path=Path(path)
    if path.stat().st_size>max_bytes:return None,"TOO_LARGE"
    n=m=None;clauses=[];cur=[]
    with path.open() as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(("c","%")):continue
            if line.startswith("p "):
                h=line.split()
                if len(h)!=4 or h[1]!="cnf" or n is not None:return None,"BAD_HEADER"
                n,m=map(int,h[2:])
                if n>max_vars or m>max_clauses:return None,"SIZE_GUARD"
                continue
            if n is None:return None,"MISSING_HEADER"
            for tok in line.split():
                lit=int(tok)
                if abs(lit)>n:return None,"BAD_LITERAL"
                if not lit:
                    clauses.append(cur);cur=[]
                    if len(clauses)>m:return None,"CLAUSE_OVERFLOW"
                else:
                    cur.append(lit)
    if n is None or cur or len(clauses)!=m:return None,"BAD_COUNT"
    return (n,clauses),"OK"

def verify(n, clauses, model):
    return len(model)==n and all(any(
        model[abs(lit)-1]==(lit>0) for lit in clause) for clause in clauses)

def construct_sat(n, clauses, node_guard=12000):
    """Returns (status, model, diagnostics). Only SAT or UNKNOWN are possible."""
    groups=[];var_job={};negative=[]
    for c in clauses:
        if not c:return "UNKNOWN",None,{"reason":"empty_clause"}
        unique=set(c)
        if all(l>0 for l in unique):
            group=sorted(unique)
            for v in group:
                if v in var_job:
                    return "UNKNOWN",None,{"reason":"overlapping_alo"}
                var_job[v]=len(groups)
            groups.append(group)
        elif len(unique)==2 and len(c)==2 and all(l<0 for l in unique):
            u,v=sorted(-l for l in unique)
            negative.append((u,v))
        else:
            return "UNKNOWN",None,{"reason":"unsupported_clause"}
    if sum(map(len,groups))>node_guard or len(groups)>node_guard:
        return "UNKNOWN",None,{"reason":"size_guard"}
    # Unconstrained/ALO-absent variables default FALSE. Negative-only clauses
    # are automatically satisfied by that choice.
    adj={v:set() for v in var_job}
    for u,v in negative:
        if u not in var_job or v not in var_job:continue
        if var_job[u]==var_job[v]:continue
        adj[u].add(v);adj[v].add(u)
    components={};resource=0
    for v in sorted(adj):
        if v in components:continue
        todo=[v];components[v]=resource
        while todo:
            x=todo.pop()
            for y in adj[x]:
                if y not in components:
                    components[y]=resource
                    todo.append(y)
        resource+=1
    options=[]
    for group in groups:
        choices={}
        for v in group:choices.setdefault(components[v],v)
        options.append(choices)
    # A matching assigns one different resource component to each ALO group.
    # This is conservative: UNKNOWN can still be SAT if components are coarse.
    occupied={};choice={}
    def augment(job,seen):
        for r,v in sorted(options[job].items()):
            if r in seen:continue
            seen.add(r)
            if r not in occupied or augment(occupied[r],seen):
                occupied[r]=job
                choice[job]=v
                return True
        return False
    for job in sorted(range(len(groups)),key=lambda j:len(options[j])):
        if not augment(job,set()):
            return "UNKNOWN",None,{"reason":"no_distinct_component_matching",
                                   "alo_groups":len(groups),"components":resource}
    model=[False]*n
    for v in choice.values():model[v-1]=True
    if not verify(n,clauses,model):
        raise RuntimeError("SAT-MATCH1 failed original-CNF witness validation")
    return "SAT",model,{"reason":"exact_original_model_verified",
                        "alo_groups":len(groups),"components":resource,
                        "mutex_clauses":len(negative),"positive_model_vars":sum(model)}
