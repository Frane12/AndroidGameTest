#!/usr/bin/env python3
"""Independent source-bound IPG-BDD1 count-profile UNSAT verifier.

No import of the native BDD extractor or producer and NO reliance on an
expected SAT/UNSAT label. Every exported BDD transition, root, terminal and
selected exactly-one group is checked against exact ORIGINAL CNF bytes.
Profiles are recomputed BACKWARD through every BDD and machine-sum DP is
recomputed separately. A source model, if one existed, would necessarily
produce the global target count. Only target-unreachable yields UNSAT.

The structural certificate format is NOT DRAT/LRAT/VeriPB. The algorithm
is polynomial in the EXPLICIT source BDD size and number of selected groups
for two count classes; does not imply polynomial general PCMAX.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
import time

MAX_SOURCE_BYTES=32000000
MAX_VARS=200000
MAX_CLAUSES=1000000
MAX_LITERALS=10000000
MAX_ELIGIBLE=56
MAX_MACHINES=48

def read_source(raw):
    if len(raw)>MAX_SOURCE_BYTES:raise ValueError("source_bytes_limit")
    nv=nc=None
    clauses=set()
    seen=0;numlits=0
    pending=[]
    for line in raw.decode("ascii").splitlines():
        items=line.split()
        if not items or items[0]=="c":continue
        if items[0]=="p":
            if nv is not None or len(items)!=4 or items[1]!="cnf":
                raise ValueError("malformed_source_header")
            nv,nc=int(items[2]),int(items[3])
            if nv<0 or nv>MAX_VARS or nc<0 or nc>MAX_CLAUSES:
                raise ValueError("bad_source_size")
            continue
        if nv is None:raise ValueError("missing_dimacs_header")
        for item in items:
            v=int(item)
            if abs(v)>nv:raise ValueError("literal_outside_source_range")
            if v:
                pending.append(v);numlits+=1
                if len(pending)>1024 or numlits>MAX_LITERALS:
                    raise ValueError("source_literal_limit")
            else:
                clauses.add(frozenset(pending))
                pending.clear();seen+=1
                if seen>MAX_CLAUSES:raise ValueError("source_clause_limit")
    if nv is None or pending or seen!=nc:
        raise ValueError("incomplete_source")
    return nv,nc,clauses

def is_integer(x):
    return type(x)==int

def check_graph(raw,graph):
    if graph.get("format")!="IPG-BDD1-SOURCE-GRAPH-V1":
        raise ValueError("wrong_source_graph_format")
    if graph.get("source_sha256")!=hashlib.sha256(raw).hexdigest():
        raise ValueError("source_sha256_mismatch")
    nv,nc,clauses=read_source(raw)
    if graph.get("source_variables")!=nv or graph.get("source_clauses")!=nc:
        raise ValueError("source_size_mismatch")
    groups=graph.get("eligible_groups")
    machines=graph.get("machine_graphs")
    if not isinstance(groups,list) or not 3<=len(groups)<=MAX_ELIGIBLE:
        raise ValueError("invalid_selected_groups")
    if not isinstance(machines,list) or not 1<=len(machines)<=MAX_MACHINES:
        raise ValueError("invalid_machine_count")
    picked=set()
    for group in groups:
        if not isinstance(group,list) or not group or len(group)>128 or not all(
                is_integer(x) and 1<=x<=nv for x in group):
            raise ValueError("bad_group_literals")
        if len(set(group))!=len(group) or set(group)&picked:
            raise ValueError("overlapping_group")
        if frozenset(group) not in clauses:
            raise ValueError("group_at_least_one_missing_from_source")
        for x,y in itertools.combinations(group,2):
            if frozenset((-x,-y)) not in clauses:
                raise ValueError("group_at_most_one_missing_from_source")
        picked.update(group)

    used_selectors=set()
    used_states=set()
    for machine in machines:
        order=machine.get("variable_order")
        transitions=machine.get("transitions")
        if not isinstance(order,list) or not order or len(order)>128 or not all(
                is_integer(x) and 1<=x<=nv for x in order):
            raise ValueError("invalid_machine_variable_order")
        if len(order)!=len(set(order)) or used_selectors.intersection(order):
            raise ValueError("shared_or_duplicate_machine_selectors")
        used_selectors.update(order)
        if not isinstance(transitions,list) or not transitions:
            raise ValueError("empty_machine_transition_graph")
        nodes={}
        rank={x:i for i,x in enumerate(order)}
        for row in transitions:
            if (not isinstance(row,list) or len(row)!=4 or
                    not all(is_integer(x) and 1<=x<=nv for x in row)):
                raise ValueError("bad_BDD_transition")
            parent,x,lo,hi=row
            if parent in nodes or x not in rank or len({parent,x,lo})!=3 or len({parent,x,hi})!=3:
                raise ValueError("invalid_or_aliased_BDD_transition")
            if (frozenset((-parent,x,lo)) not in clauses or
                    frozenset((-parent,-x,hi)) not in clauses):
                raise ValueError("BDD_transition_not_entailed_by_source_clauses")
            nodes[parent]=(x,lo,hi)
        root=machine.get("root")
        yes=machine.get("true_terminal")
        no=machine.get("false_terminal")
        if not all(is_integer(x) and 1<=x<=nv for x in (root,yes,no)):
            raise ValueError("invalid_root_or_terminal")
        if root not in nodes or yes==no or yes in nodes or no in nodes:
            raise ValueError("invalid_machine_state_structure")
        states=set(nodes)|{yes,no}
        if used_states & states:
            raise ValueError("shared_BDD_state_between_machines")
        used_states|=states
        if (frozenset((root,)) not in clauses or
                frozenset((yes,)) not in clauses or
                frozenset((-no,)) not in clauses):
            raise ValueError("BDD_root_terminal_units_missing")
        levels={s:rank[row[0]] for s,row in nodes.items()}
        levels[yes]=levels[no]=len(order)
        for parent,(x,lo,hi) in nodes.items():
            if lo not in states or hi not in states:
                raise ValueError("foreign_or_unsupported_BDD_child")
            if levels[lo]<=levels[parent] or levels[hi]<=levels[parent]:
                raise ValueError("unordered_or_cyclic_BDD_nodes")
    if picked-used_selectors:
        raise ValueError("selected_job_selector_not_covered_by_machine")
    if used_selectors & used_states:
        raise ValueError("selector_aliased_with_BDD_state")
    return {"groups":groups,"machines":machines,
            "source_sha256":hashlib.sha256(raw).hexdigest(),
            "variables":nv,"source_clauses":nc,
            "transition_count":sum(len(m["transitions"]) for m in machines)}

def add_optional(sums,variables,weight,bound):
    # A BDD path may skip selector levels entirely. Both assignments must
    # remain available in the relaxation; a unit from an unrelated source
    # clause may restrict it, which can only REDUCE actual possibilities.
    possible=set(sums)
    for variable in variables:
        ca,cb=weight.get(variable,(0,0))
        if ca or cb:
            moved={(a+ca,b+cb) for a,b in possible if a+ca<=bound[0] and b+cb<=bound[1]}
            possible.update(moved)
    return possible

def independent_backward(machine,weight,bound):
    order=machine["variable_order"]
    loc={v:i for i,v in enumerate(order)}
    yes=machine["true_terminal"];no=machine["false_terminal"]
    transitions={p:(x,lo,hi) for p,x,lo,hi in machine["transitions"]}
    ranks={p:loc[row[0]] for p,row in transitions.items()}
    ranks[yes]=ranks[no]=len(order)
    # Backward path sets represent count vectors from the node's OWN
    # selector onwards to the accepting source-asserted terminal.
    paths={yes:{(0,0)},no:set()}
    for p in sorted(transitions,key=lambda t:(-ranks[t],t)):
        x,lo,hi=transitions[p]
        candidates=set()
        for child,pick in ((lo,False),(hi,True)):
            suffix=add_optional(paths[child],order[ranks[p]+1:ranks[child]],weight,bound)
            dx,dy=weight.get(x,(0,0)) if pick else (0,0)
            candidates.update((a+dx,b+dy) for a,b in suffix
                              if a+dx<=bound[0] and b+dy<=bound[1])
        paths[p]=candidates
    root=machine["root"]
    complete=add_optional(paths[root],order[:ranks[root]],weight,bound)
    return [list(p) for p in sorted(complete)]

def independent_global(profiles,bound):
    # Compute in target-count order rather than the forward producer's
    # state-major iteration; same exact source-entailed relaxation.
    present={(0,0)}
    rows=[1]
    for machine in profiles:
        next_levels=set()
        for target_a in range(bound[0]+1):
            for target_b in range(bound[1]+1):
                for ca,cb in machine:
                    if ca<=target_a and cb<=target_b and (
                            target_a-ca,target_b-cb) in present:
                        next_levels.add((target_a,target_b))
                        break
        present=next_levels
        rows.append(len(present))
    return (bound[0],bound[1]) not in present,rows

def check(raw,graph,cert):
    original=check_graph(raw,graph)
    if cert.get("format")!="DRNAS-IPG-BDD1-COUNT-CERT-V1":
        raise ValueError("wrong_certificate_format")
    if cert.get("status")!="UNSAT_SOURCE_BDD_COUNT_UNCHECKED":
        raise ValueError("certificate_does_not_claim_UNSAT")
    if cert.get("source_sha256")!=original["source_sha256"]:
        raise ValueError("certificate_source_sha256_mismatch")
    computed_graph_sha=hashlib.sha256(
        json.dumps(graph,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    if cert.get("graph_sha256")!=computed_graph_sha:
        raise ValueError("exported_graph_was_replaced")
    if cert.get("source_variables")!=original["variables"] or (
       cert.get("source_clauses")!=original["source_clauses"]):
        raise ValueError("certificate_source_size_wrong")
    if cert.get("eligible_jobs")!=len(original["groups"]) or (
       cert.get("machine_count")!=len(original["machines"])):
        raise ValueError("certificate_group_machine_count_wrong")

    groups=original["groups"];n=len(groups)
    classes=cert.get("classes")
    if not isinstance(classes,list) or len(classes)!=2:
        raise ValueError("missing_two_class_partition")
    A,B=classes
    if (not isinstance(A,list) or not isinstance(B,list) or
            any(not is_integer(x) or x<0 or x>=n for x in A+B) or
            len(set(A+B))!=len(A+B) or not A+B):
        raise ValueError("selected_class_partition_invalid")
    amax=len(A);bmax=len(B)
    weight={}
    for j in A:
        for lit in groups[j]:weight[lit]=(1,0)
    for j in B:
        for lit in groups[j]:weight[lit]=(0,1)
    profiles=[independent_backward(m,weight,(amax,bmax))
              for m in original["machines"]]
    if profiles!=cert.get("per_machine_profiles"):
        raise ValueError("machine_BDD_count_profiles_wrong")
    infeasible,rows=independent_global(profiles,(amax,bmax))
    if rows!=cert.get("global_reachable_sizes"):
        raise ValueError("global_count_DP_wrong")
    if not infeasible:
        raise ValueError("count_target_reachable_so_no_UNSAT_proof")
    return {
        "status":"IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED",
        "sha256":original["source_sha256"],
        "selected_jobs":n,"count_classes":[amax,bmax],
        "machines":len(original["machines"]),
        "source_bdd_transitions":original["transition_count"],
        "machine_profile_sizes":[len(p) for p in profiles],
        "global_count_rows":rows,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cnf",required=True,type=pathlib.Path)
    ap.add_argument("--graph",required=True,type=pathlib.Path)
    ap.add_argument("--certificate",required=True,type=pathlib.Path)
    args=ap.parse_args()
    try:
        result=check(args.cnf.read_bytes(),
                     json.loads(args.graph.read_text()),
                     json.loads(args.certificate.read_text()))
        print("IPG_BDD_ACCEPT "+json.dumps(result,sort_keys=True),flush=True)
        return 0
    except (ValueError,KeyError,TypeError,IndexError,UnicodeError,
            OverflowError,OSError,json.JSONDecodeError) as exc:
        print("IPG_BDD_REJECT "+str(exc),flush=True)
        return 1
if __name__=="__main__":
    sys.exit(main())
