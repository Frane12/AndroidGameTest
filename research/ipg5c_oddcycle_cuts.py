#!/usr/bin/env python3
"""IPG5-C: discover bounded SOURCE-LITERAL odd-cycle PB cuts; verify only externally.

Read arbitrary original CNF, and identify source 3-way one-hot groups with
all three pairwise negative AMO clauses. Between DIFFERENT original job groups,
read binary negative clauses (-u or -v). Any odd simple cycle C of length
2k+1 gives a VALID Chvatal-Gomory rank-1 cutting-plane inequality:

    sum_{edges (u,v) in C} (~u + ~v >= 1)
    => 2 * sum_{u in C} ~u >= 2k+1
    => sum_{u in C} ~u >= k+1.

This is an algebraic source-level PB cut, with actual original clause IDs.
The compact generator DOES NOT claim those cuts alone prove UNSAT. An existing
bounded, original-RUP-verified structural DPLL suffix is retained. Both the
PB steps AND the final UNSAT must be independently accepted by VeriPB 3.0.2.

No fake source graph, no inferred job lengths, no CDCL invoked in this emitter.
"""
import argparse
import hashlib
import json
import pathlib
from collections import defaultdict
from ipg4_rup_drat_to_veripb import dimacs
from ipg5c_source_rup_to_veripb import convert

MAX_CYCLES=96
MAX_EDGES=160
MAX_LEN=7

def source_groups(clauses,nv):
    mutex=set()
    for c in clauses:
        if len(c)==2 and c[0]<0 and c[1]<0:
            mutex.add(frozenset((-c[0],-c[1])))
    groups=[];owner={}
    for c in clauses:
        if len(c)!=3 or any(x<=0 for x in c):continue
        group=tuple(sorted(c))
        if len(set(group))!=3:continue
        if not all(frozenset(pair) in mutex for pair in
                   ((group[0],group[1]),(group[0],group[2]),(group[1],group[2]))):
            continue
        if any(x in owner for x in group):
            raise ValueError("ambiguous overlapping original source groups")
        for x in group:owner[x]=len(groups)
        groups.append(group)
    if not 3<=len(groups)<=15 or set(owner)!=set(range(1,nv+1)):
        return [],{}
    return groups,owner

def odd_cycle_cuts(clauses,owner):
    edge_id={}
    for idx,c in enumerate(clauses,1):
        if len(c)!=2 or any(x>=0 for x in c):continue
        a,b=sorted((-c[0],-c[1]))
        if a==b or a not in owner or b not in owner or owner[a]==owner[b]:
            continue
        edge_id.setdefault((a,b),idx)
    if len(edge_id)>MAX_EDGES:
        return [],"binary_edge_gate"
    adj=defaultdict(set)
    for a,b in edge_id:
        adj[a].add(b);adj[b].add(a)
    all_cycles=set()
    for start in sorted(adj):
        def walk(path):
            node=path[-1]
            if len(path)>MAX_LEN:return
            for next_ in sorted(adj[node]):
                if next_==start:
                    if len(path)>=3 and len(path)%2 and path[1]<path[-1]:
                        all_cycles.add(tuple(path))
                elif next_>start and next_ not in path and len(path)<MAX_LEN:
                    walk(path+[next_])
        walk([start])
    output=[]
    for cycle in sorted(all_cycles,key=lambda c:(len(c),c))[:MAX_CYCLES]:
        source_ids=[]
        for a,b in zip(cycle,cycle[1:]+(cycle[0],)):
            source_ids.append(edge_id[tuple(sorted((a,b)))])
        if len(set(source_ids))!=len(cycle):
            raise ValueError("source cycle reused edge")
        output.append({"source_clause_ids":source_ids,"selector_cycle":list(cycle),
                       "length":len(cycle),"cut_rhs":(len(cycle)+1)//2,
                       "source_class":"original_cross_job_negative_pairs"})
    return output,("cycle_limit" if len(all_cycles)>MAX_CYCLES else "complete")

def generate(cnf,rup,pbp,meta,expected_sha):
    raw,nvars,clauses=dimacs(cnf)
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=expected_sha:
        raise ValueError("original source sha256 not pinned")
    groups,owner=source_groups(clauses,nvars)
    if not groups:raise ValueError("unsupported original one-hot structure")
    cycles,condition=odd_cycle_cuts(clauses,owner)
    # Independently source-replay ALL RUP additions before including them
    # with any cutting-plane lemmas.
    temporary=pbp.with_suffix(".tmp.pbp")
    base=convert(cnf,rup,temporary,sha)
    lines=temporary.read_text().splitlines()
    if lines[:2]!=["pseudo-Boolean proof version 3.0",
                   f"f {len(clauses)} ;"]:
        raise ValueError("invalid verifier-bound header")
    lines_pb=[]
    for cut in cycles:
        ids=cut["source_clause_ids"]
        instruction=[str(ids[0])]
        for cid in ids[1:]:instruction.extend([str(cid),"+"])
        instruction.extend(["2","d"])
        lines_pb.append("pol "+" ".join(instruction)+" ;")
    pbp.parent.mkdir(parents=True,exist_ok=True)
    pbp.write_text("\n".join(lines[:2]+lines_pb+lines[2:])+"\n")
    temporary.unlink(missing_ok=True)
    record={
        "status":"SOURCE_CG_CUTS_AND_RUP_EMITTED_NEED_EXTERNAL_VERIPB",
        "source_sha256":sha,
        "source_variables":nvars,
        "source_clauses":len(clauses),
        "recognized_onehot_groups":len(groups),
        "cross_job_odd_cycle_cuts":len(cycles),
        "cycle_lengths":{str(k):sum(c["length"]==k for c in cycles)
                         for k in (3,5,7)},
        "source_cut_instruction_steps":len(lines_pb),
        "cut_examples":cycles[:20],
        "odd_cycle_scan_status":condition,
        "source_RUP_steps":base["rup_steps"],
        "proof_bytes":pbp.stat().st_size,
        "cuts_alone_certify_UNSAT":False,
        "proof_provenance":"SOURCE_CP_DIVISION_PLUS_STRUCTURAL_JOB_BRANCH_RUP",
    }
    meta.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    return record
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--rup",required=True,type=pathlib.Path)
    p.add_argument("--veripb",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    p.add_argument("--expected-sha256",required=True)
    a=p.parse_args()
    try:
        report=generate(a.cnf,a.rup,a.veripb,a.meta,a.expected_sha256)
        print("IPG5C_CG "+json.dumps({k:v for k,v in report.items() if k!="cut_examples"},sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,UnicodeError) as e:
        a.veripb.unlink(missing_ok=True)
        print("IPG5C_CG_REJECT "+str(e),flush=True)
        return 1
if __name__=="__main__":
    raise SystemExit(main())
