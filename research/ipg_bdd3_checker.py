#!/usr/bin/env python3
"""IPG-BDD3 independent source-CNF three-class count-certificate checker.

No import from C++ or from its producer. Revalidates the original source CNF
BDD graph via the frozen IPG-BDD1 source checker, recomputes every machine
profile BACKWARD through the accepted BDD (different direction from native
forward propagation), and independently recomputes final global three-class
DP. Rejects source tampering, forged profiles, incomplete group assignment,
and any reachable target.

This validates a compact STRUCTURAL proof, not a standard VeriPB/DRAT proof.
The state bound is polynomial in explicit BDD size and selected groups only
for this fixed dimension (three classes). General PCMAX remains NP-hard.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from ipg_bdd_checker import check_graph

MAX_PROFILE=5000
MAX_OPS=30000000
MAX_WALL=45

def independently_check(raw,graph,cert):
    begin=time.monotonic()
    source=check_graph(raw,graph)
    if cert.get("format")!="DRNAS-IPG-BDD3-3COUNT-CERT-V1":
        raise ValueError("wrong_format")
    if cert.get("status")!="UNSAT_SOURCE_BDD3_COUNT_UNCHECKED":
        raise ValueError("no_UNSAT_claim")
    if cert.get("source_sha256")!=source["source_sha256"]:
        raise ValueError("source_hash_mismatch")
    graph_digest=hashlib.sha256(
        json.dumps(graph,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    if cert.get("graph_sha256")!=graph_digest:
        raise ValueError("source_BDD_graph_hash_mismatch")
    if cert.get("source_variables")!=source["variables"] or (
            cert.get("source_clauses")!=source["source_clauses"]):
        raise ValueError("source_size_mismatch")
    machines=source["machines"]
    if cert.get("machine_count")!=len(machines):
        raise ValueError("machine_count_mismatch")
    groups=source["groups"]
    classes=cert.get("classes")
    if not isinstance(classes,list) or len(classes)!=3:
        raise ValueError("classes_invalid")
    if any(not isinstance(group,list) or not group for group in classes):
        raise ValueError("three_nonempty_groups_required")
    union=[i for group in classes for i in group]
    if (any(type(i)!=int or not 0<=i<len(groups) for i in union) or
            len(set(union))!=len(union)):
        raise ValueError("groups_not_disjoint_subset")
    max_counts=tuple(map(len,classes))
    if (max_counts[0]+1)*(max_counts[1]+1)*(max_counts[2]+1)>MAX_PROFILE:
        raise ValueError("three_class_size_gate")

    # Each selected original job is one-hot and is assigned exactly once.
    weights={}
    for cls,group in enumerate(classes):
        for j in group:
            for lit in groups[j]:
                if lit in weights:raise ValueError("overlapping_original_selector")
                weights[lit]=tuple(1 if coordinate==cls else 0 for coordinate in range(3))
    zero=(0,0,0)
    def optional(profile,vars_):
        result=set(profile)
        for variable in vars_:
            w=weights.get(variable,zero)
            if w==zero:continue
            additions={
                (a+w[0],b+w[1],c+w[2]) for a,b,c in result
                if a+w[0]<=max_counts[0] and
                   b+w[1]<=max_counts[1] and
                   c+w[2]<=max_counts[2]
            }
            result.update(additions)
        return result

    operation_count=0
    machine_profiles=[]
    # Producer is FORWARD over the BDD. Verify BACKWARD from both terminals.
    for m in machines:
        if time.monotonic()-begin>MAX_WALL:
            raise ValueError("independent_verifier_timeout")
        ordering=m["variable_order"]
        rank={x:i for i,x in enumerate(ordering)}
        transitions={p:(x,lo,hi) for p,x,lo,hi in m["transitions"]}
        level={p:rank[x] for p,(x,lo,hi) in transitions.items()}
        level[m["true_terminal"]]=len(ordering)
        level[m["false_terminal"]]=len(ordering)
        reach={m["true_terminal"]:{zero},m["false_terminal"]:set()}
        for p in sorted(transitions,key=lambda v:(-level[v],v)):
            variable,left,right=transitions[p]
            local=set()
            for child,take in ((left,False),(right,True)):
                skipped=ordering[level[p]+1:level[child]]
                suffix=optional(reach[child],skipped)
                delta=weights.get(variable,zero) if take else zero
                local.update((a+delta[0],b+delta[1],c+delta[2])
                             for a,b,c in suffix
                             if a+delta[0]<=max_counts[0] and
                                b+delta[1]<=max_counts[1] and
                                c+delta[2]<=max_counts[2])
                operation_count+=len(suffix)
                if operation_count>MAX_OPS:
                    raise ValueError("independent_verifier_operation_limit")
            reach[p]=local
            if len(local)>MAX_PROFILE:
                raise ValueError("independent_verifier_state_limit")
        accepted=optional(reach[m["root"]],ordering[:level[m["root"]]])
        machine_profiles.append(sorted(accepted))
    sizes=[len(p) for p in machine_profiles]
    if cert.get("machine_profile_sizes")!=sizes:
        raise ValueError("forged_machine_profile_sizes")

    # Independent global count DP in target-major order, not source-major.
    present={zero}
    rows=[1]
    for profile in machine_profiles:
        new=set()
        candidates=set(profile)
        for aa in range(max_counts[0]+1):
            for bb in range(max_counts[1]+1):
                for cc in range(max_counts[2]+1):
                    operation_count+=1
                    if operation_count>MAX_OPS:
                        raise ValueError("independent_verifier_global_limit")
                    for a,b,c in candidates:
                        if (aa>=a and bb>=b and cc>=c and
                                (aa-a,bb-b,cc-c) in present):
                            new.add((aa,bb,cc))
                            break
        present=new
        rows.append(len(present))
    if cert.get("global_reachable_sizes")!=rows:
        raise ValueError("forged_global_reachability")
    if max_counts in present:
        raise ValueError("actual_count_target_REACHABLE")
    return {
        "status":"IPG_BDD3_SOURCE_UNSAT_VERIFIED",
        "source_sha256":source["source_sha256"],
        "selected_jobs":len(union),
        "classes":list(max_counts),
        "machines":len(machines),
        "transitions":source["transition_count"],
        "machine_profile_sizes":sizes,
        "global_rows":rows,
        "checker_operations":operation_count,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=Path)
    p.add_argument("--graph",required=True,type=Path)
    p.add_argument("--certificate",required=True,type=Path)
    a=p.parse_args()
    try:
        r=independently_check(
            a.cnf.read_bytes(),
            json.loads(a.graph.read_text()),
            json.loads(a.certificate.read_text()))
        print("IPG_BDD3_ACCEPT "+json.dumps(r,sort_keys=True),flush=True)
        return 0
    except (OSError,TypeError,KeyError,ValueError,UnicodeError,
            OverflowError,IndexError,json.JSONDecodeError) as e:
        print("IPG_BDD3_REJECT "+str(e),flush=True)
        return 1
if __name__=="__main__":sys.exit(main())
