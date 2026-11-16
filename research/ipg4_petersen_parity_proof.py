#!/usr/bin/env python3
"""IPG4: NON-SCALAR Petersen PCMAX witness + mathematical parity VeriPB 3.0.

Two distinct but mathematically equivalent source CNF encodings:
  * original source-frozen exact WEIGHTED bin-packing 45v/300c,
    SHA256 c2fefeff...; its direct standard VeriPB proof is generated
    separately from a fresh native CDCL RUP trail (see ipg4_drat_to_veripb.py).
  * explicit Petersen cubic three-edge-coloring 45v/150c, for which THIS
    script constructs a graph-theoretic case-split/parity source-RUP proof
    using 6 perfect matchings, odd-cycle obstacles and a tiny resolution
    tree over the first machine's perfect matching.

Mathematical fractional-gap certificate:
  - Each of the six perfect matchings loads exactly T on one bin.
  - Each of the 15 jobs occurs in exactly two of six matchings.
  - Hence for ANY w>=0, 6*K(w)>=2*sum(w), so sum(w)<=3*K(w).
  - No positive weighted-capacity separation can prove this UNSAT.
  - All six pairwise intersect; 3-machine integer packing is impossible.
The proof of UNSAT on the 150-clause source is 100% VeriPB RUP and
independent of numerical scalar capacity inequalities.

The generator itself checks every proposed RUP lemma by independent
unit propagation on all original clauses plus already accepted lemmas.
It never trusts a SAT solver or the expected status. VeriPB must still
verify the final proof externally against the exact unchanged source.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
from collections import Counter

WEIGHTED_SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"
WEIGHTED_T=sum(3**i for i in range(10))

def source_graph():
    E=[tuple(sorted((i,(i+1)%5))) for i in range(5)]
    E += [(i,i+5) for i in range(5)]
    E += [tuple(sorted((i+5,5+((i+2)%5)))) for i in range(5)]
    # Preserve the EXACT original weighted CNF job order: outer five,
    # spokes five, inner five. Sorting changes item-selector identities.
    edges=E
    if len(set(edges))!=15:raise ValueError("duplicate original graph edges")
    if len(edges)!=15:raise ValueError("invalid graph edges")
    vertices=[[] for _ in range(10)]
    for i,(u,v) in enumerate(edges):
        vertices[u].append(i)
        vertices[v].append(i)
    if not all(len(es)==3 for es in vertices):
        raise ValueError("Petersen graph not cubic")
    return edges,vertices

def matching_sets(edges,vertices):
    M=[]
    for mask in range(1<<len(edges)):
        if mask.bit_count()!=5:continue
        if all(sum((mask>>e)&1 for e in group)==1 for group in vertices):
            M.append(tuple(i for i in range(len(edges)) if (mask>>i)&1))
    if len(M)!=6:raise ValueError("expected six perfect matchings")
    if any(sum(e in matching for matching in M)!=2 for e in range(15)):
        raise ValueError("fractional two-occurrence property failed")
    if any(not(set(a)&set(b)) for a,b in itertools.combinations(M,2)):
        raise ValueError("two disjoint matchings found; not Petersen")
    return M

def odd_complement_cycle(edges,M):
    others=set(range(len(edges)))-set(M)
    neigh=[[] for _ in range(10)]
    for e in others:
        u,v=edges[e]
        neigh[u].append((v,e))
        neigh[v].append((u,e))
    if not all(len(row)==2 for row in neigh):
        raise ValueError("matching complement is not 2-regular")
    start=0;current=start;previous=-1;result=[]
    for _ in range(20):
        choices=[(v,e) for v,e in neigh[current] if v!=previous]
        if not choices:raise ValueError("complement cycle broken")
        nxt,e=choices[0]
        result.append(e)
        previous,current=current,nxt
        if current==start:break
    if current!=start or len(result)<3 or len(result)%2!=1:
        raise ValueError("odd-cycle obstruction missing")
    return result

def graph_cnf(edges,vertices):
    var=lambda e,c:3*e+c+1
    clauses=[]
    for e in range(15):
        clauses.append(tuple(var(e,c) for c in range(3)))
        for a,b in itertools.combinations(range(3),2):
            clauses.append((-var(e,a),-var(e,b)))
    for incident in vertices:
        for i,j in itertools.combinations(incident,2):
            for color in range(3):
                clauses.append((-var(i,color),-var(j,color)))
    if len(clauses)!=150:raise ValueError("unexpected graph CNF size")
    out="c Petersen edge three-coloring equivalent to PCMAX weighted 300-clause encoding\n"
    out+="p cnf 45 150\n"
    out+="".join(" ".join(map(str,c))+" 0\n" for c in clauses)
    return out.encode("ascii"),clauses

def up_conflict(clauses,assumptions):
    assignment={}
    for lit in assumptions:
        v=abs(lit);want=lit>0
        if v in assignment and assignment[v]!=want:return True
        assignment[v]=want
    while True:
        changed=False
        for clause in clauses:
            free=0;remaining=0;satisfied=False
            for lit in clause:
                v=abs(lit)
                if v in assignment:
                    if assignment[v]==(lit>0):
                        satisfied=True
                        break
                else:
                    free+=1;remaining=lit
            if satisfied:continue
            if free==0:return True
            if free==1:
                v=abs(remaining);want=remaining>0
                if v in assignment and assignment[v]!=want:return True
                if v not in assignment:
                    assignment[v]=want
                    changed=True
        if not changed:return False

def rup_pbp_line(clause):
    if not clause:
        # Constant zero on the LHS is a contradiction, followed by external
        # VeriPB check on the entire proof (parser compatibility CI-tested).
        return "rup 0 >= 1 ;\n"
    return "rup "+" ".join(
        f"1 {'~' if lit<0 else ''}x{abs(lit)}" for lit in clause
    )+" >= 1 ;\n"

def parity_proof(source_clauses,vertices,edges,M):
    augmented=list(source_clauses)
    source_set=set(map(frozenset,source_clauses))
    proof=[]
    by_type=Counter()
    evidence=[]
    var=lambda e,c:3*e+c+1
    def add_rup(clause,label):
        tupleclause=tuple(clause)
        if not up_conflict(augmented,(-x for x in tupleclause)):
            raise ValueError(f"RUP failed for {label}, step={len(proof)+1}: {tupleclause}")
        proof.append(tupleclause)
        augmented.append(tupleclause)
        by_type[label]+=1

    # 6 perfect matchings for the FIRST machine. Under each matching M
    # all other first-color edges are forced false; the 2-regular
    # complement contains an odd cycle and cannot alternate colors 2/3.
    # We split on one edge's second-color literal, derive both guarded
    # RUP clauses by unit propagation, then resolve them by RUP to block M.
    for matching in M:
        cycle=odd_complement_cycle(edges,matching)
        guard=[-var(e,0) for e in matching]
        probe=var(cycle[0],1)
        add_rup(guard+[probe],"odd_cycle_guard")
        add_rup(guard+[-probe],"odd_cycle_guard")
        add_rup(guard,"matching_nogood")
        evidence.append({
            "perfect_matching_jobs_1based":[e+1 for e in matching],
            "odd_cycle_complement_jobs_1based":[e+1 for e in cycle],
            "parity_probe_literal":probe,
        })

    # Source one-hot edge colors plus 3 incident edges at every cubic
    # vertex imply at least one first-color edge at each vertex, by a
    # 3-edge/2-color pigeonhole RUP argument.
    for v,incident in enumerate(vertices):
        group=[var(e,0) for e in incident]
        probe=var(incident[0],1)
        add_rup(group+[probe],"vertex_pigeonhole_guard")
        add_rup(group+[-probe],"vertex_pigeonhole_guard")
        add_rup(group,"vertex_color_one_alo")

    # The already derived color-one vertex ALOs, source pairwise AMO
    # and 6 perfect-matching nogoods are enough for a tiny complete
    # binary case split. This is mathematical matching enumeration,
    # not a full 45-variable CDCL solve.
    matching_formula=[]
    for incident in vertices:
        matching_formula.append(tuple(var(e,0) for e in incident))
        for a,b in itertools.combinations(incident,2):
            mutex=(-var(a,0),-var(b,0))
            if frozenset(mutex) not in source_set:
                raise ValueError("missing original color-one AMO")
            matching_formula.append(mutex)
    for matching in M:
        matching_formula.append(tuple(-var(e,0) for e in matching))

    def propagate_matching(assumptions):
        assignment={}
        for lit in assumptions:
            v=abs(lit);want=lit>0
            if v in assignment and assignment[v]!=want:return True,assignment
            assignment[v]=want
        while True:
            changed=False
            for clause in matching_formula:
                nfree=0;remaining=0;sat=False
                for lit in clause:
                    v=abs(lit)
                    if v in assignment:
                        if assignment[v]==(lit>0):
                            sat=True
                            break
                    else:
                        nfree+=1
                        remaining=lit
                if sat:continue
                if nfree==0:return True,assignment
                if nfree==1:
                    v=abs(remaining);wanted=remaining>0
                    if v in assignment and assignment[v]!=wanted:
                        return True,assignment
                    if v not in assignment:
                        assignment[v]=wanted
                        changed=True
            if not changed:return False,assignment

    decision_nodes=0;leaf_conflicts=0
    def split(path):
        nonlocal decision_nodes,leaf_conflicts
        decision_nodes+=1
        if decision_nodes>10000:
            raise ValueError("matching case split explosion")
        conflict,assignment=propagate_matching(path)
        if conflict:
            leaf_conflicts+=1
            add_rup([-lit for lit in path],"matching_split_conflict")
            return
        choice=None
        for incident in vertices:
            candidates=[var(e,0) for e in incident if var(e,0) not in assignment]
            if candidates and (choice is None or len(candidates)<choice[0]):
                choice=(len(candidates),candidates[0])
        if choice is None:
            raise ValueError("a valid first-color matching escapes all six nogoods")
        lit=choice[1]
        split(path+[lit])
        split(path+[-lit])
        add_rup([-v for v in path],"matching_case_resolution")
    split([])
    if not proof or proof[-1]:
        raise ValueError("proof must end with the empty contradiction")
    return proof,by_type,evidence,decision_nodes,leaf_conflicts

def weighted_gap_audit(weighted,edges,M):
    expected_header=f"p cnf 45 300"
    if expected_header.encode() not in weighted:
        raise ValueError("original weighted source is not 45-var/300-clause CNF")
    sha=hashlib.sha256(weighted).hexdigest()
    if sha!=WEIGHTED_SHA:
        raise ValueError("frozen weighted PCMAX source SHA mismatch")
    weights=[3**a+3**b for a,b in edges]
    if sum(weights)!=3*WEIGHTED_T:raise ValueError("total load not 3T")
    for matching in M:
        if sum(weights[e] for e in matching)!=WEIGHTED_T:
            raise ValueError("some perfect matching is not a feasible bin")
    if any(sum(e in matching for matching in M)!=2 for e in range(15)):
        raise ValueError("configuration half-cover invalid")
    # Valid for ALL nonnegative w: 6*K(w) >= 2*sum_j w_j,
    # so 3*K(w)>=sum_j w_j. This is a constructive fractional
    # configuration certificate, no floating-point LP solver required.
    return {
        "format":"DRNAS-IPG4-PETERSEN-FRACTIONAL-GAP-V1",
        "weighted_cnf_sha256":sha,"jobs":15,"machines":3,
        "duration_base":3,"duration_list":[int(p) for p in weights],
        "capacity_per_machine":WEIGHTED_T,
        "total_duration":sum(weights),
        "perfect_matching_configurations":[[e+1 for e in match] for match in M],
        "fractional_coefficient_per_configuration":"1/2",
        "occurrences_per_job":[2]*15,
        "no_disjoint_pair":True,
        "nonnegative_weighted_capacity_strict_separator_possible":False,
        "conclusion":"INTEGER_UNSAT_BUT_FRACTIONAL_FEASIBLE",
        "note":"Constructive six-configuration fractional cover plus pairwise-overlap integer obstruction.",
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--weighted-original",required=True,type=pathlib.Path)
    ap.add_argument("--graph-cnf",required=True,type=pathlib.Path)
    ap.add_argument("--veripb",required=True,type=pathlib.Path)
    ap.add_argument("--fractional-certificate",required=True,type=pathlib.Path)
    ap.add_argument("--meta",required=True,type=pathlib.Path)
    args=ap.parse_args()
    try:
        edges,vertices=source_graph()
        M=matching_sets(edges,vertices)
        fractional=weighted_gap_audit(args.weighted_original.read_bytes(),edges,M)
        src,clauses=graph_cnf(edges,vertices)
        proof,tally,parity,decision_nodes,conflict_leaves=parity_proof(
            clauses,vertices,edges,M)
        args.graph_cnf.parent.mkdir(parents=True,exist_ok=True)
        args.graph_cnf.write_bytes(src)
        graph_sha=hashlib.sha256(src).hexdigest()
        with args.veripb.open("w") as fd:
            fd.write("pseudo-Boolean proof version 3.0\n")
            fd.write(f"f {len(clauses)} ;\n")
            for clause in proof:
                fd.write(rup_pbp_line(clause))
            fd.write("output NONE ;\n")
            fd.write("conclusion UNSAT ;\n")
            fd.write("end pseudo-Boolean proof ;\n")
        fractional["edge_coloring_source_sha256"]=graph_sha
        fractional["graph_edges"]=list(map(list,edges))
        fractional["parity_witnesses"]=parity
        args.fractional_certificate.write_text(
            json.dumps(fractional,sort_keys=True,indent=2)+"\n")
        meta={
            "status":"VERIPB_EMITTED_EXTERNAL_CHECK_REQUIRED",
            "source_weighted_sha256":fractional["weighted_cnf_sha256"],
            "source_graph_sha256":graph_sha,
            "graph_source_clauses":len(clauses),
            "RUP_steps":len(proof),
            "RUP_kinds":dict(sorted(tally.items())),
            "matching_case_nodes":decision_nodes,
            "matching_conflict_leaves":conflict_leaves,
            "perfect_matchings":len(M),
            "odd_cycle_parity_witnesses":len(parity),
            "veripb_bytes":args.veripb.stat().st_size,
        }
        args.meta.write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n")
        print("IPG4_PARITY_PROOF "+json.dumps(meta,sort_keys=True),flush=True)
        return 0
    except (ValueError,TypeError,OSError,AssertionError) as exc:
        args.veripb.unlink(missing_ok=True)
        print("IPG4_PARITY_UNKNOWN "+str(exc),flush=True)
        return 1

if __name__=="__main__":
    sys.exit(main())
