#!/usr/bin/env python3
"""Independent mathematical/SOURCE-CNF checker of Petersen fractional gap.

No import of proof generator, native solver, or expected solver status.
Reconstructs EXACT 45-variable/300-clause original encoding from
integer durations and every inclusion-minimal overweight set, verifies
the original byte SHA-256, and independently certifies:
(1) six exact-capacity perfect matchings, pairwise intersecting;
(2) each job occurs in exactly two of six;
(3) therefore all nonnegative scalar capacity inequalities fail to
    separate integer-unsatisfiable 3-machine bin packing.
Checks the separate 150-clause source is the corresponding cubic edge
3-coloring instance. Standard VeriPB itself checks the UNSAT proof.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys

SOURCE_SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def read_cnf(raw):
    nv,nc=None,None
    clauses=[];current=[]
    for line in raw.decode("ascii").splitlines():
        words=line.split()
        if not words or words[0]=="c":continue
        if words[0]=="p":
            if nv is not None or len(words)!=4 or words[1]!="cnf":
                raise ValueError("malformed source CNF header")
            nv,nc=int(words[2]),int(words[3])
            continue
        if nv is None:raise ValueError("source clause before header")
        for word in words:
            v=int(word)
            if abs(v)>nv:raise ValueError("source literal outside DIMACS variables")
            if v:current.append(v)
            else:clauses.append(tuple(current));current=[]
    if nv is None or current or nc!=len(clauses):
        raise ValueError("bad DIMACS source count")
    return nv,clauses

def check(weighted_raw,graph_raw,certificate):
    if hashlib.sha256(weighted_raw).hexdigest()!=SOURCE_SHA:
        raise ValueError("wrong frozen source SHA")
    if certificate.get("weighted_cnf_sha256")!=SOURCE_SHA:
        raise ValueError("fractional certificate not source-bound")
    if certificate.get("format")!="DRNAS-IPG4-PETERSEN-FRACTIONAL-GAP-V1":
        raise ValueError("wrong fractional certificate format")
    if certificate.get("edge_coloring_source_sha256")!=hashlib.sha256(graph_raw).hexdigest():
        raise ValueError("graph proof source hash mismatch")
    nv,original=read_cnf(weighted_raw)
    gv,graph_source=read_cnf(graph_raw)
    if nv!=45 or len(original)!=300 or gv!=45 or len(graph_source)!=150:
        raise ValueError("unexpected source dimensions")
    a=[(i,(i+1)%5) for i in range(5)]
    b=[(i,i+5) for i in range(5)]
    c=[(i+5,5+(i+2)%5) for i in range(5)]
    # Job indices are part of the ORIGINAL CNF semantics. Keep the
    # original generator order instead of sorting the graph's edge set.
    edges=[tuple(sorted(e)) for e in a+b+c]
    if len(set(edges))!=15:raise ValueError("duplicate original edge")
    if len(edges)!=15:raise ValueError("not 15 edges")
    incidence=[set() for _ in range(10)]
    for j,(x,y) in enumerate(edges):
        incidence[x].add(j)
        incidence[y].add(j)
    if any(len(e)!=3 for e in incidence):
        raise ValueError("not cubic Petersen graph")
    durations=[3**x+3**y for x,y in edges]
    T=sum(3**x for x in range(10))
    if T!=29524 or sum(durations)!=3*T:
        raise ValueError("invalid numeric fractional instance")
    if certificate.get("duration_list")!=durations or certificate.get("capacity_per_machine")!=T:
        raise ValueError("fractional duration data differs")
    exact_mask=[]
    subset_sum=[0]*(1<<15)
    for mask in range(1,1<<15):
        lo=mask&-mask
        index=lo.bit_length()-1
        subset_sum[mask]=subset_sum[mask^lo]+durations[index]
        if subset_sum[mask]==T:
            exact_mask.append(mask)
    if len(exact_mask)!=6:
        raise ValueError("not six exact-capacity configurations")
    if any(mask.bit_count()!=5 or any(
            sum((mask>>j)&1 for j in inc)!=1 for inc in incidence
        ) for mask in exact_mask):
        raise ValueError("exact configs not six perfect matchings")
    if any((x&y)==0 for x,y in itertools.combinations(exact_mask,2)):
        raise ValueError("two disjoint exact machine loads, no integer obstruction")
    if any(sum((mask>>j)&1 for mask in exact_mask)!=2 for j in range(15)):
        raise ValueError("fractional cover with half coefficients invalid")
    expected=[sorted([i+1 for i in range(15) if mask>>i&1]) for mask in exact_mask]
    reported=sorted(tuple(sorted(v)) for v in certificate.get("perfect_matching_configurations",[]))
    if reported!=sorted(tuple(x) for x in expected):
        raise ValueError("six source configurations differ")
    # EXACT original weighted CNF encoding: one-hot on each job and all
    # inclusion-minimal overweight subsets for every machine.
    x=lambda j,m:3*j+m+1
    clauses=[]
    for j in range(15):
        clauses.append((x(j,0),x(j,1),x(j,2)))
        for m1,m2 in itertools.combinations(range(3),2):
            clauses.append((-x(j,m1),-x(j,m2)))
    for mask in range(1,1<<15):
        total=subset_sum[mask]
        if total<=T:continue
        if any(total-durations[j]>T for j in range(15) if mask>>j&1):
            continue
        chosen=[j for j in range(15) if mask>>j&1]
        for m in range(3):
            clauses.append(tuple(-x(j,m) for j in chosen))
    if sorted(clauses)!=sorted(original):
        raise ValueError("weighted source CNF is not the claimed PCMAX encoding")
    # Separate graph source: proper 3-edge-coloring of the SAME Petersen graph.
    graph_clauses=[]
    for j in range(15):
        graph_clauses.append(tuple(x(j,m) for m in range(3)))
        for m1,m2 in itertools.combinations(range(3),2):
            graph_clauses.append((-x(j,m1),-x(j,m2)))
    for inc in incidence:
        for i,j in itertools.combinations(sorted(inc),2):
            for m in range(3):
                graph_clauses.append((-x(i,m),-x(j,m)))
    if sorted(graph_clauses)!=sorted(graph_source):
        raise ValueError("graph CNF not equivalent edge-coloring source")
    if certificate.get("nonnegative_weighted_capacity_strict_separator_possible") is not False:
        raise ValueError("invalid capacity-gap claim")
    if certificate.get("no_disjoint_pair") is not True:
        raise ValueError("invalid integer obstruction metadata")
    return {
        "status":"PETERSEN_NONSCALAR_SOURCE_GAP_VERIFIED",
        "weighted_source_sha256":SOURCE_SHA,
        "graph_source_sha256":hashlib.sha256(graph_raw).hexdigest(),
        "perfect_matchings":len(exact_mask),
        "each_job_matching_occurrences":2,
        "fractional_configuration_mass":3,
        "integer_three_bin_cover_possible":False,
        "strict_nonnegative_weighted_separator_possible":False,
        "original_weighted_clauses":len(original),
        "graph_proof_source_clauses":len(graph_source),
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--weighted-cnf",required=True,type=pathlib.Path)
    p.add_argument("--graph-cnf",required=True,type=pathlib.Path)
    p.add_argument("--fractional-certificate",required=True,type=pathlib.Path)
    args=p.parse_args()
    try:
        result=check(
            args.weighted_cnf.read_bytes(),
            args.graph_cnf.read_bytes(),
            json.loads(args.fractional_certificate.read_text()))
        print("IPG4_GAP_ACCEPT "+json.dumps(result,sort_keys=True),flush=True)
        return 0
    except (ValueError,OSError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as error:
        print("IPG4_GAP_REJECT "+str(error),flush=True)
        return 1
if __name__=="__main__":
    sys.exit(main())
