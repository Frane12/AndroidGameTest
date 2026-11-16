#!/usr/bin/env python3
"""IPG5-A: SOURCE-CNF parity bridge, directly to an ORIGINAL weighted PCMAX RUP.

Strict research prototype. DOES NOT import, invoke, or use a CDCL/SAT solver.
Constructs a source-validated mathematical bridge:
  Original Petersen 45v/300c weighted packing CNF
      -> 90 adjacency/color mutex clauses by bounded job-size-ordered
         DPLL + unit propagation, emitting SOURCE-RUP lemmas;
      -> the already validated IPG4 six-matching odd-cycle argument,
         59 RUP lemmas on graph coloring CNF (each of its clauses now
         present in or source-RUP derived from ORIGINAL CNF).
All lemmas are locally replayed against unchanged original clauses;
external DRAT-trim and VeriPB 3.0.2 MUST independently accept the result.

The source graph and CNF variable-to-job mapping are checked by the
independent IPG4 exact-encoding checker, not inferred from a filename.
The DPLL certificate search IS EXPONENTIAL IN GENERAL, despite a
short found proof here. This is not a polynomial algorithm or generic
3D-BDD-to-PB compilation. It is genuinely NOT a CDCL-derived trace.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
import time

from ipg4_petersen_parity_proof import (
    WEIGHTED_SHA, source_graph, matching_sets, graph_cnf,
    parity_proof, weighted_gap_audit
)
from ipg4_fractional_gap_checker import check as independent_encoding_check
from ipg4_rup_drat_to_veripb import dimacs as read_dimacs

MAX_NODES=10000
MAX_PROOF_STEPS=8000
MAX_WALL_S=30.0

def masks(clause):
    pos=neg=0
    for lit in clause:
        if lit>0: pos|=1<<(lit-1)
        else:neg|=1<<(-lit-1)
    return pos,neg

def propagate_original(source_masks,true_bits,false_bits):
    """Pure unit propagation on SOURCE clauses, no learned clauses."""
    if true_bits & false_bits:return True,true_bits,false_bits
    while True:
        delta_true=delta_false=0
        for positive,negative in source_masks:
            if positive & true_bits or negative & false_bits:continue
            remaining_pos=positive & ~(true_bits|false_bits)
            remaining_neg=negative & ~(true_bits|false_bits)
            available=remaining_pos|remaining_neg
            if not available:return True,true_bits,false_bits
            if not (available & (available-1)):
                if remaining_pos:delta_true|=remaining_pos
                else:delta_false|=remaining_neg
        if ((delta_true & (false_bits|delta_false)) or
                (delta_false & true_bits)):
            return True,true_bits,false_bits
        if not (delta_true|delta_false)&~(true_bits|false_bits):
            return False,true_bits,false_bits
        true_bits|=delta_true
        false_bits|=delta_false

def emit_source_rup_for_missing_graph_clauses(clauses,missing,edges):
    """
    Resolve each graph mutex *from original packing CNF only*, using
    deterministic DPLL case splits by DESCENDING SOURCE-RECONSTRUCTED
    job duration. No CDCL, no conflict analysis, no learnt clause
    influences the tree: each leaf is a source UP contradiction.
    Each internal branch joins two child RUP clauses by resolution.
    """
    ordered_jobs=sorted(range(len(edges)),key=lambda j:(-(3**edges[j][0]+3**edges[j][1]),j))
    order=[3*j+color+1 for j in ordered_jobs for color in range(3)]
    source_masks=[masks(c) for c in clauses]
    proof=[];nodes=0;leaf_nodes=0;max_branch_depth=0;started=time.monotonic()
    stats=[]
    for target in missing:
        if len(target)!=2 or any(lit>=0 for lit in target):
            raise ValueError("only literal negative same-color graph mutex supported")
        assumptions=[-lit for lit in target]
        if len(set(assumptions))!=2:
            raise ValueError("bad identical adjacency selectors")
        start_nodes=nodes
        start_proof=len(proof)
        true_bits=sum(1<<(lit-1) for lit in assumptions)
        def split(true_bits,false_bits,path):
            nonlocal nodes,leaf_nodes,max_branch_depth
            nodes+=1
            if (nodes>MAX_NODES or len(proof)>MAX_PROOF_STEPS or
                    time.monotonic()-started>MAX_WALL_S):
                raise TimeoutError("bounded non-CDCL source-lemma search exhausted")
            max_branch_depth=max(max_branch_depth,len(path)-2)
            contradicted,assigned_true,assigned_false=propagate_original(
                source_masks,true_bits,false_bits)
            if contradicted:
                leaf_nodes+=1
                # Source CNF + path is UP-UNSAT, hence negate path is RUP.
                proof.append(tuple(-lit for lit in path))
                return
            undecided=~(assigned_true|assigned_false)
            chosen=next((x for x in order if undecided & (1<<(x-1))),None)
            if chosen is None:
                raise ValueError("SOURCE HAS MODEL under supposed graph mutex")
            bit=1<<(chosen-1)
            split(assigned_true|bit,assigned_false,path+[chosen])
            split(assigned_true,assigned_false|bit,path+[-chosen])
            # Both child no-goods now imply this parent no-good, RUP.
            proof.append(tuple(-lit for lit in path))
        split(true_bits,0,assumptions)
        if frozenset(proof[-1])!=frozenset(target):
            raise AssertionError("source graph mutex not derived")
        stats.append({
            "target":list(target),
            "resolution_tree_nodes":nodes-start_nodes,
            "rup_steps":len(proof)-start_proof,
        })
    return proof,{
        "graph_mutex_count":len(missing),
        "lemma_DPLL_nodes":nodes,
        "lemma_unit_propagation_leaves":leaf_nodes,
        "max_branch_depth_after_pair_assumptions":max_branch_depth,
        "source_lemma_total_RUP":len(proof),
        "per_lemma":stats,
    }

def verify_all_rup(source_clauses,steps):
    """Local source-clause replay; official external check is STILL mandatory."""
    indexed=[masks(c) for c in source_clauses]
    for n,clause in enumerate(steps,1):
        opposite=tuple(-lit for lit in clause)
        tr=fr=0
        for lit in opposite:
            bit=1<<(abs(lit)-1)
            if lit>0:tr|=bit
            else:fr|=bit
        contradiction,_,_=propagate_original(indexed,tr,fr)
        if not contradiction:raise ValueError(f"RUP step {n} is not source-entailed")
        indexed.append(masks(clause))
    if steps[-1]:
        raise ValueError("last RUP step must be the empty contradiction")
    return len(steps)

def generate(original_path,graph_path,rup_path,metadata_path,fractional_path):
    start=time.monotonic()
    raw=original_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=WEIGHTED_SHA:
        raise ValueError("unsupported source SHA, no proof claim")
    _,nv,source_clauses=read_dimacs(original_path)
    if nv!=45 or len(source_clauses)!=300:
        raise ValueError("not the source-frozen 45v/300c weighted PCMAX")
    edges,vertices=source_graph()
    matches=matching_sets(edges,vertices)
    graph_raw,graph_clauses=graph_cnf(edges,vertices)
    gap=weighted_gap_audit(raw,edges,matches)
    gap["edge_coloring_source_sha256"]=hashlib.sha256(graph_raw).hexdigest()
    gap["graph_edges"]=[list(e) for e in edges]
    # INDEPENDENT mathematical checker rederives all 300 source clauses,
    # the graph-coloring map, fractional feasibility, and integer obstruction.
    checked=independent_encoding_check(raw,graph_raw,gap)
    if checked["status"]!="PETERSEN_NONSCALAR_SOURCE_GAP_VERIFIED":
        raise ValueError("source 300->150 equivalence/fractional-gap audit failed")

    source_clauses=[tuple(c) for c in source_clauses]
    known={frozenset(c) for c in source_clauses}
    missing=[c for c in graph_clauses if frozenset(c) not in known]
    source_graph_units=sum(frozenset(c) in known for c in graph_clauses)
    existing_mutex=source_graph_units-60
    if len(graph_clauses)!=150 or not 0<=existing_mutex<=90 or (
            len(missing)+existing_mutex!=90):
        raise ValueError("original source-to-graph incidence accounting invalid")
    derived,details=emit_source_rup_for_missing_graph_clauses(
        source_clauses,missing,edges)
    graph_proof,graph_tally,odd_cycles,search_nodes,leaves=parity_proof(
        graph_clauses,vertices,edges,matches)
    proof=derived+graph_proof
    accepted=verify_all_rup(source_clauses,proof)

    graph_path.parent.mkdir(parents=True,exist_ok=True)
    graph_path.write_bytes(graph_raw)
    fractional_path.write_text(json.dumps(gap,indent=2,sort_keys=True)+"\n")
    with rup_path.open("w") as f:
        for row in proof:
            f.write(" ".join(map(str,row))+" 0\n")
    report={
        "status":"SOURCE_RUP_EMITTED_EXTERNAL_VERIPB_REQUIRED",
        "method":"IPG5_NONCDCL_PACKING_TO_GRAPH_PARITY",
        "source_sha256":WEIGHTED_SHA,
        "source_vars":nv,"source_clauses":len(source_clauses),
        "graph_source_sha256":hashlib.sha256(graph_raw).hexdigest(),
        "graph_source_clauses":len(graph_clauses),
        "fractional_gap_independently_checked":True,
        "missing_graph_mutex_derived":len(missing),
        "graph_mutex_already_original":existing_mutex,
        "total_graph_mutex_clauses":len(missing)+existing_mutex,
        "lemma_tree_nodes":details["lemma_DPLL_nodes"],
        "lemma_UP_conflict_leaves":details["lemma_unit_propagation_leaves"],
        "lemma_tree_depth":details["max_branch_depth_after_pair_assumptions"],
        "graph_mutex_RUP_steps":len(derived),
        "odd_cycle_parity_RUP_steps":len(graph_proof),
        "odd_cycle_witnesses":len(odd_cycles),
        "matching_case_split_nodes":search_nodes,
        "RUP_steps_locally_replayed":accepted,
        "rup_trace_sha256":hashlib.sha256(rup_path.read_bytes()).hexdigest(),
        "rup_trace_bytes":rup_path.stat().st_size,
        "generator_s":round(time.monotonic()-start,6),
        "origin":"MATHEMATICALLY_GUIDED_DPLL_NO_CDCL_NO_CONFLICT_LEARNING",
        "caveat":"This is bounded exponential case-splitting; not a general polynomial IPG. Standard proof must be checked by VeriPB against ORIGINAL 300-clause CNF.",
    }
    metadata_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original",type=pathlib.Path,required=True)
    p.add_argument("--graph-out",type=pathlib.Path,required=True)
    p.add_argument("--rup-out",type=pathlib.Path,required=True)
    p.add_argument("--metadata",type=pathlib.Path,required=True)
    p.add_argument("--fractional",type=pathlib.Path,required=True)
    a=p.parse_args()
    try:
        result=generate(a.original,a.graph_out,a.rup_out,a.metadata,a.fractional)
        print("IPG5_NONCDCL_SOURCE_RUP "+json.dumps(result,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,AssertionError,TimeoutError) as e:
        a.rup_out.unlink(missing_ok=True)
        a.graph_out.unlink(missing_ok=True)
        a.fractional.unlink(missing_ok=True)
        a.metadata.parent.mkdir(parents=True,exist_ok=True)
        a.metadata.write_text(json.dumps({
            "status":"UNKNOWN","reason":str(e),
            "source_claim":False})+"\n")
        print("IPG5_SOURCE_UNKNOWN "+str(e),flush=True)
        return 1

if __name__=="__main__":
    sys.exit(main())
