#!/usr/bin/env python3
"""Independent IPG2 certificate checker.

The verifier parses ORIGINAL bytes, checks source implication clauses and
enumerates bounded perfect matchings with a separate blossom-oracle traversal.
A valid mathematical certificate is not a VeriPB/DRAT proof. No generic
CNF UNSAT claim follows for unsupported encodings or >K matchings.
"""
import hashlib
import itertools
import json
import pathlib
import sys
from collections import Counter

import networkx as nx

FIXED_BOUND=8

def read_original(raw):
    declared=ncl=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        toks=line.split()
        if not toks or toks[0]=="c":continue
        if toks[0]=="p":
            if declared is not None or len(toks)!=4 or toks[1]!="cnf":
                raise ValueError("invalid original header")
            declared,ncl=map(int,toks[2:])
            continue
        if declared is None:raise ValueError("no source header")
        for word in toks:
            lit=int(word)
            if abs(lit)>declared:raise ValueError("source literal outside header")
            if lit:pending.append(lit)
            else:clauses.append(tuple(pending));pending=[]
    if declared is None or pending or ncl!=len(clauses):
        raise ValueError("incomplete original source")
    return declared,clauses

def graph_from_clauses(raw):
    count,clauses=read_original(raw)
    positive=[tuple(c) for c in clauses if len(c)==3 and all(x>0 for x in c)]
    n=len(positive)
    if n<6 or n>64 or count!=3*n:raise ValueError("unsupported source cardinality layout")
    taken=set()
    ids={frozenset(c) for c in clauses}
    for group in positive:
        if len(set(group))!=3 or not taken.isdisjoint(group):
            raise ValueError("source groups overlap")
        taken.update(group)
        if any(frozenset((-a,-b)) not in ids for a,b in itertools.combinations(group,2)):
            raise ValueError("source lacks exactly-one clauses")
    if taken!=set(range(1,count+1)):raise ValueError("uncovered source selector")

    neighbors=[set() for _ in positive]
    for i in range(n):
        for j in range(i+1,n):
            if all(frozenset((-positive[i][k],-positive[j][k])) in ids
                   for k in range(3)):
                neighbors[i].add(j)
                neighbors[j].add(i)
    tris=[]
    for a in range(n):
        for b in sorted(v for v in neighbors[a] if v>a):
            for c in sorted(v for v in neighbors[a] if v>b and v in neighbors[b]):
                tris.append((a,b,c))
    touches=Counter(x for tri in tris for x in tri)
    if len(tris)<4 or any(touches[x]!=2 for x in range(n)):
        raise ValueError("not a cubic line-graph source")
    incidence={}
    for v,tri in enumerate(tris):
        for e in tri:incidence.setdefault(e,[]).append(v)
    G=nx.Graph()
    G.add_nodes_from(range(len(tris)))
    for e,pair in incidence.items():
        if len(pair)!=2 or pair[0]==pair[1] or G.has_edge(*pair):
            raise ValueError("ambiguous reconstructed edge")
        G.add_edge(*pair)
    if G.number_of_edges()!=n or any(deg!=3 for _,deg in G.degree()):
        raise ValueError("source not cubic")
    return G,len(positive)

def independent_bounded_enumeration(G):
    answer=[]
    oracle_count=0
    def match_possible(vertices):
        nonlocal oracle_count
        oracle_count+=1
        H=G.subgraph(vertices)
        if H.number_of_nodes()%2: return False
        return 2*len(nx.max_weight_matching(H,maxcardinality=True))==H.number_of_nodes()
    def recurse(vertices,edges):
        if len(answer)>FIXED_BOUND:return
        if not match_possible(vertices):return
        if not vertices:
            answer.append(tuple(sorted(edges)))
            return
        v=min(vertices)
        for neighbor in sorted(G[v]):
            if neighbor not in vertices:continue
            pair=tuple(sorted((v,neighbor)))
            recurse(vertices-{v,neighbor},edges+[pair])
            if len(answer)>FIXED_BOUND:return
    recurse(set(G.nodes),[])
    return answer,oracle_count,len(answer)>FIXED_BOUND

def check(raw,cert):
    if cert.get("format")!="DRNAS-IPG2-CUBIC-MATCHING-PARITY-V1":
        raise ValueError("wrong certificate format")
    if cert.get("source_sha256")!=hashlib.sha256(raw).hexdigest():
        raise ValueError("source bytes changed")
    if cert.get("bound")!=FIXED_BOUND:
        raise ValueError("matching budget changed")
    if cert.get("status")!="UNSAT_SOURCE_PARITY_CERTIFICATE_UNCHECKED":
        raise ValueError("no claimed bounded graph proof")
    G,source_jobs=graph_from_clauses(raw)
    if cert.get("source_variables")!=source_jobs*3 or cert.get("jobs")!=source_jobs:
        raise ValueError("source declared sizes disagree")
    if cert.get("graph_vertices")!=len(G) or cert.get("graph_edges")!=G.number_of_edges():
        raise ValueError("reconstruction sizes disagree")
    matches,calls,overflow=independent_bounded_enumeration(G)
    if overflow:raise ValueError("more than K perfect matchings; cannot prove")
    described=cert.get("matchings")
    if not isinstance(described,list) or len(described)!=len(matches):
        raise ValueError("matching list incomplete")
    source={tuple(sorted(m)) for m in matches}
    checked=set()
    for evidence in described:
        pairs=tuple(sorted(tuple(sorted(e)) for e in evidence["matching"]))
        if pairs in checked or pairs not in source:
            raise ValueError("not a distinct source perfect matching")
        checked.add(pairs)
        verts=[v for edge in pairs for v in edge]
        if len(pairs)*2!=len(G) or len(set(verts))!=len(G):
            raise ValueError("not a perfect matching")
        cycle=evidence["odd_cycle"]
        if not isinstance(cycle,list) or len(cycle)<3 or len(cycle)%2!=1:
            raise ValueError("missing odd cycle")
        if len(set(cycle))!=len(cycle):
            raise ValueError("repeated vertex in cycle")
        if any(not G.has_edge(u,v) or tuple(sorted((u,v))) in pairs
               for u,v in zip(cycle,cycle[1:]+cycle[:1])):
            raise ValueError("cycle is not in complement of matching")
    if checked!=source:
        raise ValueError("exhaustive perfect matching coverage mismatch")
    return {"status":"IPG2_POLYNOMIAL_PARITY_SOURCE_VERIFIED",
            "graph_vertices":len(G),"graph_edges":G.number_of_edges(),
            "perfect_matchings":len(source),"independent_oracle_calls":calls,
            "odd_cycle_witnesses":len(checked)}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("cnf",type=pathlib.Path)
    p.add_argument("certificate",type=pathlib.Path)
    ns=p.parse_args()
    try:
        result=check(ns.cnf.read_bytes(),json.loads(ns.certificate.read_text()))
        print("IPG2_CERTIFIED "+json.dumps(result,sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError,IndexError) as e:
        print("IPG2_CERTIFICATE_REJECTED "+str(e))
        return 1
if __name__=="__main__":sys.exit(main())
