#!/usr/bin/env python3
"""DRNAS TSP-SAT3: exact integer Held-Karp *1-tree relaxation*, NOT exact DP.

For any integer vertex potentials p_i, every Hamiltonian cycle H has
sum_(i,j in H)(d_ij + p_i + p_j) - 2*sum(p_i) = cost(H).
The minimum *one-tree* (MST over V\{root}, plus cheapest 2 root edges)
therefore yields a mathematically sound lower bound on TSP optimum:

    LB(p) = minimum_1tree(d + p_i + p_j) - 2*sum(p_i) <= OPT.

Integer subgradient ascent searches for a useful p. All certificates are
rechecked by an independent Kruskal-based verifier, no SAT solver, no exact
Held-Karp DP and no result labels are consulted by the optimization routine.
The bound may match the optimum on easy instances but is NOT a polynomial
algorithm for all TSP inputs. Even matching the route cost does NOT count
as a standard CNF UNSAT proof.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[2]

def need(v,message):
    if not v:raise ValueError("ONE_TREE_INVALID "+message)

def valid_d(D):
    n=len(D)
    need(4<=n<=20,"size")
    for i in range(n):
        need(len(D[i])==n and D[i][i]==0,"shape/diagonal")
        for j in range(i):
            need(type(D[i][j]) is int and D[i][j]>=0 and
                 D[i][j]==D[j][i],"distance must be symmetric nonnegative integer")
    return n

def minimum_one_tree(D,p):
    """Independent of SAT. Prim over non-root vertices then 2 edges to root."""
    n=valid_d(D)
    need(len(p)==n and all(type(x) is int for x in p),"bad potentials")
    in_tree={1}
    degrees=[0]*n
    edges=[]
    adjusted=0
    for _ in range(n-2):
        value,a,b=min((D[i][j]+p[i]+p[j],i,j)
                      for i in in_tree for j in range(1,n) if j not in in_tree)
        adjusted+=value
        in_tree.add(b)
        edges.append((a,b))
        degrees[a]+=1
        degrees[b]+=1
    for j in sorted(range(1,n),key=lambda k:(D[0][k]+p[0]+p[k],k))[:2]:
        adjusted+=D[0][j]+p[0]+p[j]
        degrees[0]+=1
        degrees[j]+=1
        edges.append((0,j))
    need(len(edges)==n and sum(degrees)==2*n,"not a one-tree")
    return adjusted-2*sum(p),degrees,edges

def verify_independent_kruskal(D,certificate):
    """Checker uses Kruskal, unlike Prim in the producer."""
    n=valid_d(D)
    p=certificate.get("potentials")
    need(type(p) is list and len(p)==n and
         all(type(x) is int and abs(x)<=1000000 for x in p),
         "invalid potential vector")
    parents=list(range(n))
    def find(i):
        while parents[i]!=i:
            i=parents[i]
        return i
    weighted=sorted((D[i][j]+p[i]+p[j],i,j)
                    for i in range(1,n) for j in range(i+1,n))
    total=0
    edges=0
    for price,i,j in weighted:
        a,b=find(i),find(j)
        if a!=b:
            parents[b]=a
            total+=price;edges+=1
            if edges==n-2:break
    need(edges==n-2,"missing tree edges")
    root=sorted((D[0][j]+p[0]+p[j],j) for j in range(1,n))[:2]
    total+=sum(price for price,j in root)
    lower=total-2*sum(p)
    need(lower==certificate.get("one_tree_lower_bound"),
         "Kruskals independently recomputed bound differs")
    need(certificate.get("inequality")=="ONE_TREE_POTENTIAL_DEGREE2",
         "invalid bound type")
    return lower

def degree_bound(D):
    n=valid_d(D)
    return (sum(sum(sorted(D[i][j] for j in range(n) if j!=i)[:2])
                for i in range(n))+1)//2

def improve_bound(D,known_feasible_cost,iterations=128):
    """Deterministic bounded integer subgradient ascent; no exact-TSP oracle."""
    n=valid_d(D)
    need(type(known_feasible_cost) is int and known_feasible_cost>=0,
         "upper bound type")
    need(1<=iterations<=512,"iteration range")
    p=[0]*n
    best,deg,_=minimum_one_tree(D,p)
    bestp=p[:]
    trace=[]
    for k in range(iterations):
        gradient=[d-2 for d in deg]
        norm=sum(x*x for x in gradient)
        if not norm:break
        # Depend on a FEASIBLE incumbent only; no exact optimum is used.
        gap=max(1,known_feasible_cost-best)
        factor=(2.0 if k<20 else 1.0 if k<64 else
                0.25 if k<112 else 0.1)
        step=max(1,round(factor*gap/norm))
        p=[p[i]+step*gradient[i] for i in range(n)]
        lb,deg,_=minimum_one_tree(D,p)
        if lb>best:
            best, bestp=lb,p[:]
        if (k%16)==0:trace.append({"iteration":k,"latest":lb,"best":best})
    cert={"inequality":"ONE_TREE_POTENTIAL_DEGREE2",
          "potentials":bestp,"one_tree_lower_bound":best,
          "iterations_requested":iterations,
          "degree_lower_bound":degree_bound(D),
          "source_upper_bound":known_feasible_cost,
          "trace":trace,
          "no_Held_Karp_exact_DP":True}
    independently_checked=verify_independent_kruskal(D,cert)
    chosen=max(independently_checked,cert["degree_lower_bound"])
    # An integer linear lower bound cannot exceed a feasible route.
    need(chosen<=known_feasible_cost,"one-tree bound exceeds feasible upper")
    cert["combined_lower_bound"]=chosen
    return chosen,cert

def selftest():
    sys.path.insert(0,str(ROOT/"research/tsp_sat2"))
    import optimizer as base
    result=[]
    for name,n,seed in base.CASES:
        coords=base.coords_for(n,seed)
        D=base.enc.euc_distance(coords)
        tour=base.two_opt(base.nearest_neighbor(D),D)
        U=base.enc.cost(tour,D)
        lb,cert=improve_bound(D,U)
        # Exact Held-Karp used ONLY here for an independent diagnostic audit.
        exact,_=base.enc.held_karp(D)
        need(lb<=exact<=U, "lower bound unsound against Held-Karp")
        need(verify_independent_kruskal(D,cert)
             ==cert["one_tree_lower_bound"],"cross-check failed")
        result.append(dict(name=name,n=n,upper=U,one_tree_lb=lb,
                           exact_audit_only=exact,remaining_gap=U-lb))
    print("TSP_SAT3_ONE_TREE_SELFTEST_PASS "+json.dumps(
        {"cases":result,"independent_Kruskal_verifier":True,
         "held_karp_used_only_in_selftest":True},
        sort_keys=True),flush=True)

if __name__=="__main__":selftest()
