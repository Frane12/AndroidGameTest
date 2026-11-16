#!/usr/bin/env python3
"""IPG5E mathematical obstacle: exact rational LP witnesses.

The source-encoding original weighted Petersen CNF has 81 binary
Petersen same-machine graph conflicts NOT literally present among its
300 input clauses. For EACH candidate implication (-u OR -v),
solve the *continuous* relaxation of ALL ORIGINAL 300 source PB
inequalities with u=v=1. Verify the returned model using exact
fractions, not floating-point checks. A valid rational feasible
witness proves that this mutex cannot be derived by *linear
combination alone* from original inequalities.

Add the three ORIGINAL 3-clique rank-one Chvatal-Gomory cuts on
jobs 9/12/14, and seek exact rational feasible witnesses again.
Only POSITIVE rational witnesses are treated as mathematical proof.
LP solver "infeasible" status is diagnostic and NOT a certified
integer/PB proof of the remaining forced-pair conflicts.

SciPy is used OFFLINE for witness DISCOVERY only; exact fraction
validation is local and an independent rechecking tool can
validate all saved numerators/denominators. No CDCL, DPLL, SAT
oracle or novel UNSAT conclusion. This is a restricted known
weighted Petersen source, not general source-blind SAT analysis.
"""
import argparse
import hashlib
import itertools
import json
import math
from fractions import Fraction
from pathlib import Path

from scipy.optimize import linprog
from ipg1_fixtures import petersen
from ipg4_rup_drat_to_veripb import dimacs
from ipg4_petersen_parity_proof import source_graph,graph_cnf

EXPECTED_SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def linear_ub(clauses,nv):
    rows=[];rhs=[]
    for c in clauses:
        row=[0]*nv
        neg=0
        for lit in c:
            if lit>0:row[lit-1]-=1
            else:row[-lit-1]+=1;neg+=1
        rows.append(row)
        rhs.append(neg-1)
    return rows,rhs

def exact_valid(clauses,nums,denom):
    assert denom>0
    assert all(0<=a<=denom for a in nums)
    return all(sum(nums[lit-1] if lit>0 else denom-nums[-lit-1]
                   for lit in clause)>=denom for clause in clauses)

def reduced_solution(result,clauses,forced,cuts):
    if not result.success:return None
    xs=[Fraction(float(x)).limit_denominator(4096) for x in result.x]
    denominator=math.lcm(*(x.denominator for x in xs))
    numbers=[int(x*denominator) for x in xs]
    if not exact_valid(clauses,numbers,denominator):
        raise ValueError("LP FLOATING SOLUTION DOES NOT HAVE EXACT RATIONAL SOURCE WITNESS")
    if any(numbers[lit-1]!=denominator for lit in forced):
        raise ValueError("fractional model fails forced original graph pair")
    if any(sum(numbers[lit-1] for lit in trio)>denominator
           for trio in cuts):
        raise ValueError("fractional model fails source CG triangle")
    return {"forced_selectors":list(forced),"denominator":denominator,
            "numerators":numbers}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    source=a.output.parent/"original_45v300c.cnf"
    source.write_bytes(petersen().encode("ascii"))
    raw,nv,clauses=dimacs(source)
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=EXPECTED_SHA or nv!=45 or len(clauses)!=300:
        raise ValueError("original weighted source identity mismatch")
    graph,vertices=source_graph()
    graph_bytes,graph_clauses=graph_cnf(graph,vertices)
    index={frozenset(c) for c in clauses}
    missing=[tuple(-lit for lit in c) for c in graph_clauses
             if len(c)==2 and all(l<0 for l in c)
             and frozenset(c) not in index]
    if len(missing)!=81:
        raise ValueError("expected precisely 81 source-missing Petersen graph conflicts")
    rows,b=linear_ub(clauses,nv)
    triangles=[]
    for machine in range(3):
        selectors=tuple(3*j+machine+1 for j in (9,12,14))
        if not all(frozenset((-x,-y)) in index
                   for x,y in itertools.combinations(selectors,2)):
            raise ValueError("one rank-one CG triangle not source-grounded")
        triangles.append(selectors)
    cutrows=[]
    for t in triangles:
        arr=[0]*nv
        for lit in t:arr[lit-1]=1
        cutrows.append(arr)
    initial=[];after=[];uncertified=[]
    for u,v in missing:
        bounds=[(0.0,1.0) for _ in range(nv)]
        bounds[u-1]=bounds[v-1]=(1.0,1.0)
        r=linprog([0.0]*nv,A_ub=rows,b_ub=b,bounds=bounds,method="highs")
        witness=reduced_solution(r,clauses,(u,v),[])
        if witness is None:
            raise ValueError("one original forced-pair LP unexpectedly infeasible")
        initial.append(witness)
        r2=linprog([0.0]*nv,A_ub=rows+cutrows,b_ub=b+[1]*3,
                   bounds=bounds,method="highs")
        second=reduced_solution(r2,clauses,(u,v),triangles)
        if second is not None:after.append(second)
        else:uncertified.append([u,v])
    result={
        "status":"PASS_EXACT_RATIONAL_SOURCE_RELAXATION_WITNESSES",
        "source_sha256":sha,
        "original_vars":nv,
        "original_clauses":len(clauses),
        "source_missing_graph_mutexes":len(missing),
        "fractional_witnesses_for_all_missing_pair_mutexes":len(initial),
        "exact_fractional_witnesses_surviving_three_triangle_CG_cuts":len(after),
        "remaining_pair_relaxations_without_saved_witness":len(uncertified),
        "uncertified_pairs":uncertified,
        "max_initial_witness_denominator":max(w["denominator"] for w in initial),
        "max_after_triangle_witness_denominator":max(w["denominator"] for w in after),
        "initial_witnesses":initial,
        "after_source_triangle_CG_witnesses":after,
        "scope":"Positive rational witnesses certify that ordinary LP combinations cannot derive those binary mutexes. Additional three rank-one CG cuts still admit exact rational witnesses on stated pairs. No claim that unsolved 9 pairs are integer-infeasible based only on numeric LP status.",
    }
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("IPG5E_LP_OBSTRUCTION "+json.dumps({
        k:v for k,v in result.items() if k not in (
          "initial_witnesses","after_source_triangle_CG_witnesses")
    },sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
