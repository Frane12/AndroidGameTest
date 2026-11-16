#!/usr/bin/env python3
"""IPG5-B: derive genuine ORIGINAL-source Chvatal-Gomory odd-cycle PB cuts.

For each of the 3 machines, find source clauses forming a (literal)
3-cycle of pairwise overweight forbidden jobs. Sum its 3 binary PB
constraints and divide by 2:

 (~x_A+~x_B>=1) + (~x_B+~x_C>=1) + (~x_A+~x_C>=1)
  => 2(~x_A+~x_B+~x_C)>=3
  => (~x_A+~x_B+~x_C)>=2.

These are actual cutting-plane proof steps with input-clause IDs, not
CDCL. They strengthen the algebraic proof description but DO NOT ALONE
prove the whole source UNSAT. The final contradiction still uses the
source-verified 100-step structural DPLL RUP trace.

Outputs: standard VeriPB proof with 3 genuine CG cuts followed by
unchanged independently replayed RUP lines, plus source-bound metadata.
External VeriPB 3.0.2 MUST accept. No generic PCMAX / P=NP claim.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys

from ipg4_rup_drat_to_veripb import dimacs
from ipg5_rup_to_veripb import convert

EXPECTED="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def generate(original,rup,output,meta):
    raw=original.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:
        raise ValueError("not frozen original source")
    _,clauses=dimacs(raw)
    if len(clauses)!=300:raise ValueError("source clause mismatch")
    triangles=[]
    for machine in range(3):
        source_edges={}
        for index,clause in enumerate(clauses,1):
            if len(clause)!=2 or any(v>=0 for v in clause):
                continue
            vars_=[-v for v in clause]
            if any((x-1)%3!=machine for x in vars_):
                continue
            jobs=tuple(sorted((x-1)//3 for x in vars_))
            if jobs[0]!=jobs[1]:
                source_edges.setdefault(jobs,index)
        selected=[]
        for triple in itertools.combinations(range(15),3):
            a,b,c=triple
            pairs=[(a,b),(a,c),(b,c)]
            if all(pair in source_edges for pair in pairs):
                selected.append((triple,[source_edges[pair] for pair in pairs]))
        if len(selected)!=1:
            raise ValueError("source overweight pair graph has no unique triangle")
        triple,ids=selected[0]
        triangles.append({"machine":machine,"jobs_zero_based":list(triple),
                          "source_clause_ids":ids,
                          "method":"sum_three_source_amo_and_divide_by_two"})

    # The independent fixed source-RUP verifier is used first to check
    # the old 100-step suffix BEFORE we add cutting-plane lines.
    intermediate=output.with_suffix(".rup_only_tmp.pbp")
    converted=convert(original,rup,intermediate)
    parts=intermediate.read_text().splitlines()
    if (parts[0]!="pseudo-Boolean proof version 3.0" or
            parts[1]!=f"f {len(clauses)} ;"):
        raise ValueError("unexpected frozen standard VeriPB header")
    pb_lines=[]
    for cut in triangles:
        ids=cut["source_clause_ids"]
        pb_lines.append(f"pol {ids[0]} {ids[1]} + {ids[2]} + 2 d ;")
    final=parts[:2]+pb_lines+parts[2:]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text("\n".join(final)+"\n")
    intermediate.unlink(missing_ok=True)
    report={
        "status":"CG_CUTS_EMITTED_EXTERNAL_VERIPB_REQUIRED",
        "source_sha256":EXPECTED,
        "original_clauses":300,
        "chvatal_gomory_rank1_source_cuts":3,
        "source_overweight_triangles":triangles,
        "rup_source_steps":converted["rup_steps_replayed"],
        "proof_size_bytes":output.stat().st_size,
        "cutting_planes_ALONE_prove_unsat":False,
        "total_proof_kind":"THREE_SOURCE_CP_DIVISION_CUTS_PLUS_NONCDCL_RUP",
    }
    meta.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("IPG5B_ODDCYCLE_PB "+json.dumps(report,sort_keys=True),flush=True)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original",required=True,type=pathlib.Path)
    p.add_argument("--rup",required=True,type=pathlib.Path)
    p.add_argument("--veripb",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    a=p.parse_args()
    try:
        generate(a.original,a.rup,a.veripb,a.meta)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError) as err:
        a.veripb.unlink(missing_ok=True)
        print("IPG5B_ODDCYCLE_PB_REJECT "+str(err),flush=True)
        return 1

if __name__=="__main__":sys.exit(main())
