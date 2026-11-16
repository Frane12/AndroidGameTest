#!/usr/bin/env python3
"""IPG2-B bounded-matching parity certificate for source-CNF cubic edge colorings.

This is a polynomial-time sufficient UNSAT test when the number of perfect
matchings is at most the FIXED constant K (default 8). Enumerating with a
polynomial blossom feasibility oracle and stopping after K+1 candidates means
the whole algorithm has a polynomial worst-case bound for this fixed K.
Does not settle generic PCMAX, and does NOT directly recognize the previous
300-clause weighted-bin-packing encoding of Petersen; this applies to its
explicit graph-edge-coloring CNF representation.
"""
import hashlib
import itertools
import json
import pathlib
import sys
import time
from collections import Counter

import networkx as nx

BOUND=8

def parse_source(raw):
    nvars=expected=None
    clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        p=line.split()
        if not p or p[0]=="c":continue
        if p[0]=="p":
            if nvars is not None or len(p)!=4 or p[1]!="cnf":
                raise ValueError("invalid source DIMACS")
            nvars,expected=int(p[2]),int(p[3])
            continue
        if nvars is None:raise ValueError("missing source header")
        for word in p:
            v=int(word)
            if abs(v)>nvars:raise ValueError("invalid source literal")
            if v:pending.append(v)
            else:clauses.append(tuple(pending));pending=[]
    if nvars is None or pending or len(clauses)!=expected:
        raise ValueError("source clause count mismatch")
    return nvars,clauses

def reconstruct(raw):
    nvars,clauses=parse_source(raw)
    groups=[c for c in clauses if len(c)==3 and all(v>0 for v in c)]
    n=len(groups)
    if n<6 or n>64 or nvars!=3*n:
        raise ValueError("outside cubic-clausal graph scope")
    where={}
    for i,group in enumerate(groups):
        if len(set(group))!=3:raise ValueError("duplicate assignment selector")
        for color,v in enumerate(group):
            if v in where:raise ValueError("source groups overlap")
            where[v]=(i,color)
    if set(where)!=set(range(1,nvars+1)):raise ValueError("source groups do not cover variables")
    ids={frozenset(c) for c in clauses}
    for group in groups:
        for u,v in itertools.combinations(group,2):
            if frozenset((-u,-v)) not in ids:
                raise ValueError("missing same-job exclusivity clauses")
    jobs=range(n)
    adj=[set() for _ in jobs]
    for i,j in itertools.combinations(jobs,2):
        if all(frozenset((-groups[i][c],-groups[j][c])) in ids for c in range(3)):
            adj[i].add(j);adj[j].add(i)

    triangles=[]
    for a in jobs:
        for b in sorted(x for x in adj[a] if x>a):
            for c in sorted(x for x in adj[a] if x>b):
                if c in adj[b]:triangles.append((a,b,c))
    incidence=Counter(j for tri in triangles for j in tri)
    if len(triangles)<4 or any(incidence[j]!=2 for j in jobs):
        raise ValueError("cannot uniquely decode cubic triangle-incidence graph")
    pair={}
    for t,tri in enumerate(triangles):
        for j in tri:pair.setdefault(j,[]).append(t)
    G=nx.Graph()
    G.add_nodes_from(range(len(triangles)))
    for job,twins in pair.items():
        a,b=twins
        if a==b or G.has_edge(a,b):
            raise ValueError("parallel or loop graph not supported")
        G.add_edge(a,b,job=job)
    if G.number_of_edges()!=n or any(G.degree(v)!=3 for v in G):
        raise ValueError("reconstructed graph is not cubic")
    return G,groups,triangles

def list_matchings_bounded(G,limit=BOUND):
    """Polynomial-delay self-reduction with blossom oracle, capped at K+1."""
    vertices=frozenset(G.nodes)
    found=[]
    oracle_calls=0
    def recurse(unused,chosen):
        nonlocal oracle_calls
        if len(found)>limit:return
        oracle_calls+=1
        if unused:
            H=G.subgraph(unused)
            # Edmonds blossom matching, polynomial in vertex count.
            matching=nx.max_weight_matching(H,maxcardinality=True)
            if len(matching)*2!=len(unused):
                return
            v=min(unused)
            for u in sorted(G.neighbors(v)):
                if u in unused:
                    edge=(min(v,u),max(v,u))
                    recurse(unused-{v,u},chosen+(edge,))
                    if len(found)>limit:return
        else:
            found.append(tuple(sorted(chosen)))
    recurse(vertices,tuple())
    return found,oracle_calls,len(found)>limit

def odd_cycle_for_matching(G,matching):
    H=G.copy()
    H.remove_edges_from(matching)
    if any(H.degree(v)!=2 for v in H.nodes):
        raise ValueError("cubic matching left non-two-regular complement")
    for cycle in nx.cycle_basis(H):
        if len(cycle)%2:
            return cycle
    return None

def prove(raw,limit=BOUND):
    start=time.perf_counter()
    if limit!=BOUND:raise ValueError("bound is a fixed compiled constant")
    G,groups,triangles=reconstruct(raw)
    matchings,calls,overflow=list_matchings_bounded(G,limit)
    data={
        "format":"DRNAS-IPG2-CUBIC-MATCHING-PARITY-V1",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "source_variables":len(groups)*3,
        "jobs":len(groups),
        "graph_vertices":G.number_of_nodes(),
        "graph_edges":G.number_of_edges(),
        "bound":limit,
        "oracle_calls":calls,
        "status":"UNKNOWN",
    }
    if overflow:
        data["reason"]="more_than_fixed_matching_budget"
        data["found_before_stop"]=len(matchings)
    else:
        bad_cycles=[]
        for matching in matchings:
            odd=odd_cycle_for_matching(G,matching)
            if odd is None:
                data["reason"]="a_perfect_matching_has_even_complement"
                break
            bad_cycles.append({"matching":[list(e) for e in matching],
                               "odd_cycle":odd})
        else:
            data.update(status="UNSAT_SOURCE_PARITY_CERTIFICATE_UNCHECKED",
                        reason="all_at_most_K_perfect_matchings_leave_odd_cycles",
                        matchings=bad_cycles)
    data["elapsed_s"]=round(time.perf_counter()-start,6)
    return data

def fixture(edges,name):
    edges=sorted(set(tuple(sorted(e)) for e in edges))
    nv=max(max(e) for e in edges)+1
    graph=nx.Graph();graph.add_nodes_from(range(nv));graph.add_edges_from(edges)
    if any(d!=3 for _,d in graph.degree()):
        raise ValueError("test graph not cubic")
    clauses=[]
    def x(edge,color):return 3*edge+color+1
    for i,_ in enumerate(edges):
        clauses.append((x(i,0),x(i,1),x(i,2)))
        for a,b in itertools.combinations(range(3),2):
            clauses.append((-x(i,a),-x(i,b)))
    index={e:i for i,e in enumerate(edges)}
    for vertex in graph:
        incident=[index[tuple(sorted((vertex,u)))] for u in graph.neighbors(vertex)]
        for i,j in itertools.combinations(incident,2):
            for color in range(3):
                clauses.append((-x(i,color),-x(j,color)))
    # All source conclusions rely only on the actual DIMACS clause literals.
    txt=f"c {name} cubic graph three-color source encoding\np cnf {3*len(edges)} {len(clauses)}\n"
    txt+="".join(" ".join(map(str,c))+" 0\n" for c in clauses)
    return txt.encode()

def make_cases(root):
    outer=[(i,(i+1)%5) for i in range(5)]
    spokes=[(i,i+5) for i in range(5)]
    inner=[(i+5,((i+2)%5)+5) for i in range(5)]
    graph_cases={
        "petersen_edge3_unsat":(outer+spokes+inner,"UNSAT"),
        "k33_edge3_sat":([(i,3+j) for i in range(3) for j in range(3)],"SAT"),
    }
    result=[]
    for name,(edges,label) in graph_cases.items():
        path=root/(name+".cnf")
        path.write_bytes(fixture(edges,name))
        result.append((name,label,path))
    return result

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=pathlib.Path,required=True)
    p.add_argument("--certificate",type=pathlib.Path,required=True)
    ns=p.parse_args()
    try:
        result=prove(ns.input.read_bytes())
        ns.certificate.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("IPG2_MATCHING "+json.dumps({k:v for k,v in result.items() if k!="matchings"},sort_keys=True))
    except Exception as e:
        print("IPG2_UNKNOWN "+str(e))
        return 1
    return 0
if __name__=="__main__":sys.exit(main())
