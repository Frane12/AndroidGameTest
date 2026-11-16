#!/usr/bin/env python3
"""IPG-BDD1 polynomial machine-count profile + global two-class DP.

Consumes source-derived graph from the existing native PCMAX BDD extractor.
Its standalone independent checker MUST validate all BDD implication
clauses against the ORIGINAL CNF before promoting any UNSAT claim.

This is sound but INCOMPLETE: for each machine, compute every reachable
(#type-A,#type-B) selected-eligible-selector count on any BDD path ending
in source-unit TRUE. BDD skipped levels are freely 0/1; false terminal
never contributes. Convolve per-machine counts. If all groups have an
exactly-one CNF constraint and the total count pair is unreachable, UNSAT.

Every operation is polynomial in input BDD size and # selected groups for
a fixed number (=2) of classes. BDD extraction may itself be large.
No P=NP claim. No general SAT conclusion from a reachable count pair.
"""
import argparse
import hashlib
import json
import pathlib
import time
from collections import Counter

LIMIT_SECONDS=10.
LIMIT_STATES=1200
LIMIT_OPS=10000000

class Budget(Exception):pass
def key_value(order,groupclass,upper):
    return [groupclass.get(v,(-0,-0)) for v in order]

def optional_extend(states,costs,cap):
    amax,bmax=cap
    states=set(states)
    for ca,cb in costs:
        if not (ca or cb):continue
        states|={(a+ca,b+cb) for a,b in states
                 if a+ca<=amax and b+cb<=bmax}
        if len(states)>LIMIT_STATES:raise Budget("machine_profile_state_gate")
    return states

def machine_profile(graph,cls,cap,clock):
    order=graph["variable_order"]
    index={v:i for i,v in enumerate(order)}
    T=graph["true_terminal"];F=graph["false_terminal"]
    transitions={row[0]:tuple(row[1:]) for row in graph["transitions"]}
    if graph["root"] not in transitions:raise ValueError("unrooted BDD")
    rank={p:index[row[0]] for p,row in transitions.items()}
    rank[T]=len(order);rank[F]=len(order)
    costs=key_value(order,cls,cap)
    initial=optional_extend({(0,0)},costs[:rank[graph["root"]]],cap)
    reach={graph["root"]:initial}
    ops=0
    for parent in sorted(transitions,key=lambda p:(rank[p],p)):
        if parent not in reach:continue
        if time.monotonic()>clock:raise Budget("profile_time_gate")
        x,left,right=transitions[parent]
        pr=rank[parent]
        for chosen,child in ((0,left),(1,right)):
            if child==F:continue
            cur=reach[parent]
            if chosen:
                ca,cb=cls.get(x,(0,0))
                cur={(a+ca,b+cb) for a,b in cur
                     if a+ca<=cap[0] and b+cb<=cap[1]}
            extended=optional_extend(cur,costs[pr+1:rank[child]],cap)
            ops+=len(cur)*(1+rank[child]-pr)
            if ops>LIMIT_OPS:raise Budget("profile_operation_gate")
            if extended:
                reach.setdefault(child,set()).update(extended)
            if child in reach and len(reach[child])>LIMIT_STATES:
                raise Budget("profile_state_gate")
    profile=reach.get(T,set())
    return sorted([list(x) for x in profile]),ops

def global_reach(profiles,cap,clock):
    out={(0,0)};rows=[1];ops=0
    for machine in profiles:
        before=out
        out=set()
        for a,b in before:
            for ca,cb in machine:
                ops+=1
                if ops>LIMIT_OPS:raise Budget("global_operation_gate")
                if a+ca<=cap[0] and b+cb<=cap[1]:
                    out.add((a+ca,b+cb))
        rows.append(len(out))
        if time.monotonic()>clock:raise Budget("global_time_gate")
    return ((cap[0],cap[1]) not in out),rows,ops

def partitions(graph):
    groups=graph["eligible_groups"]
    n=len(groups)
    if n<3 or n>56:return []
    selector_to_group={x:j for j,group in enumerate(groups) for x in group}
    occurrence=Counter()
    for machine in graph["machine_graphs"]:
        for parent,x,left,right in machine["transitions"]:
            if x in selector_to_group:occurrence[selector_to_group[x]]+=1
    idx=tuple(range(n))
    given=graph.get("eligible_group_order",[])
    if sorted(given)==list(range(n)):
        topological=tuple(given)
    else:topological=idx
    half=n//2
    priority=tuple(sorted(idx,key=lambda j:(-occurrence[j],j)))
    proposals=[
        (idx,()),
        (idx[:half],idx[half:]),
        (idx[::2],idx[1::2]),
        (priority[:half],priority[half:]),
    ]
    # Selecting only some exactly-one clauses is always sound:
    # others get weight zero, allowing the checker to prove a stronger
    # global impossibility without assuming anything about omitted jobs.
    # The native weighted capacity extractor already benefits from this
    # idea; here we combine it with *two-dimensional* integer count DP.
    for order in (topological,priority):
        for k in range(3,n+1):
            subset=tuple(order[:k])
            proposals.append((subset,()))
            if k>=6:
                proposals.append((subset[:k//2],subset[k//2:]))
        for k in range(3,n):
            proposals.append((tuple(order[n-k:]),()))
    seen=set();ans=[]
    for aa,bb in proposals:
        if not aa:continue
        a=tuple(sorted(aa));b=tuple(sorted(bb))
        if not a and not b:continue
        if (a,b) not in seen:
            seen.add((a,b));ans.append((a,b))
    return ans

def calculate(graph,classes,clock):
    groups=graph["eligible_groups"]
    A,B=classes;cap=(len(A),len(B))
    mapping={}
    for j in A:
        for x in groups[j]:mapping[x]=(1,0)
    for j in B:
        for x in groups[j]:mapping[x]=(0,1)
    profiles=[];ops=0
    for m in graph["machine_graphs"]:
        states,work=machine_profile(m,mapping,cap,clock)
        profiles.append(states);ops+=work
    unsat,rows,globalwork=global_reach(profiles,cap,clock)
    return {
        "classes":[list(A),list(B)],
        "per_machine_profiles":profiles,
        "global_reachable_sizes":rows,
        "machine_transition_ops":ops,
        "global_count_ops":globalwork,
        "unreachable":unsat,
    }

def analyze(graph):
    start=time.monotonic()
    source_sha=graph.get("source_sha256","")
    result={
        "format":"DRNAS-IPG-BDD1-COUNT-CERT-V1",
        "source_sha256":source_sha,
        "graph_sha256":hashlib.sha256(json.dumps(graph,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        "source_variables":graph.get("source_variables",0),
        "source_clauses":graph.get("source_clauses",0),
        "status":"UNKNOWN","reason":"no_count_contradiction",
        "machine_count":len(graph.get("machine_graphs",[])),
        "eligible_jobs":len(graph.get("eligible_groups",[])),
    }
    deadline=start+LIMIT_SECONDS
    for classes in partitions(graph):
        try:trial=calculate(graph,classes,deadline)
        except (Budget,ValueError) as exc:
            result["reason"]="bounded_analysis_"+str(exc)
            break
        if trial["unreachable"]:
            result.update(status="UNSAT_SOURCE_BDD_COUNT_UNCHECKED",
                          reason="global_two_class_count_profile_gap",
                          **{k:v for k,v in trial.items() if k!="unreachable"})
            break
    result["elapsed_s"]=round(time.monotonic()-start,6)
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=pathlib.Path,required=True)
    p.add_argument("--certificate",type=pathlib.Path,required=True)
    args=p.parse_args()
    graph=json.loads(args.graph.read_text())
    result=analyze(graph)
    args.certificate.parent.mkdir(parents=True,exist_ok=True)
    args.certificate.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("IPG_BDD_PROFILE "+json.dumps(
        {k:v for k,v in result.items() if k not in ("per_machine_profiles","classes")},
        sort_keys=True),flush=True)
    return 0
if __name__=="__main__":raise SystemExit(main())
