#!/usr/bin/env python3
"""Independent exact rational checker for IPG5E LP obstruction.

Does NOT import SciPy or the LP discovery module. Verifies EVERY
reported rational solution against unchanged source clauses using
integer arithmetic and independently reconstructs the 81 missing
graph adjacency pairs plus the three original-clause CG triangles.
Rejects fractional witness forgery, missing source, source SHA change,
duplicate pair entries or source-CG-triangle violations.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
from ipg1_fixtures import petersen
from ipg4_petersen_parity_proof import source_graph,graph_cnf

EXPECTED="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"

def read(raw):
    nv=nc=None;out=[];partial=[]
    for line in raw.decode("ascii").splitlines():
        t=line.split()
        if not t or t[0]=="c":continue
        if t[0]=="p":
            if nv is not None or len(t)!=4 or t[1]!="cnf":
                raise ValueError("invalid source header")
            nv,nc=int(t[2]),int(t[3])
            continue
        for field in t:
            x=int(field)
            if x:partial.append(x)
            else:
                out.append(tuple(partial))
                partial=[]
    if nv!=45 or nc!=len(out) or partial:
        raise ValueError("source does not match 45v/300c original")
    return out

def verify(path):
    data=json.loads(path.read_text())
    source=petersen().encode("ascii")
    if hashlib.sha256(source).hexdigest()!=EXPECTED:
        raise ValueError("reconstructed source sha mismatch")
    if data.get("source_sha256")!=EXPECTED:
        raise ValueError("saved evidence not source bound")
    clauses=read(source)
    if len(clauses)!=300:raise ValueError("source clause count differs")
    edge,vertices=source_graph()
    graphraw,graphclauses=graph_cnf(edge,vertices)
    indexed={frozenset(c) for c in clauses}
    missing={tuple(sorted((-c[0],-c[1]))) for c in graphclauses
             if len(c)==2 and c[0]<0 and c[1]<0 and
             frozenset(c) not in indexed}
    if len(missing)!=81:raise ValueError("source-missing graph mutex count differs")
    triangles=[]
    for m in range(3):
        xs=tuple(3*j+m+1 for j in (9,12,14))
        if not all(frozenset((-a,-b)) in indexed for a,b in itertools.combinations(xs,2)):
            raise ValueError("claimed CG triangle not source-grounded")
        triangles.append(xs)
    first=data.get("initial_witnesses",[])
    second=data.get("after_source_triangle_CG_witnesses",[])
    def check_set(items,need_all,with_cg):
        keys=set()
        for item in items:
            pair=tuple(sorted(item["forced_selectors"]))
            if pair not in missing or pair in keys:raise ValueError("witness pair missing or duplicated")
            keys.add(pair)
            d=item["denominator"];nums=item["numerators"]
            if type(d)!=int or not 1<=d<=100000 or len(nums)!=45 or any(
                    type(x)!=int or not 0<=x<=d for x in nums):
                raise ValueError("invalid exact rational witness values")
            if any(nums[k-1]!=d for k in pair):
                raise ValueError("forced conflict pair not simultaneously 1")
            for clause in clauses:
                lhs=sum(nums[lit-1] if lit>0 else d-nums[-lit-1] for lit in clause)
                if lhs<d:raise ValueError("witness violates ORIGINAL source clause")
            if with_cg:
                if any(sum(nums[lit-1] for lit in trio)>d for trio in triangles):
                    raise ValueError("witness violates one of 3 valid source CG cuts")
        if need_all and keys!=missing:raise ValueError("some missing graph mutex has no witness")
        return keys
    a=check_set(first,True,False)
    b=check_set(second,False,True)
    if not b.issubset(a):raise ValueError("post-cut witnesses include alien pairs")
    if (data.get("fractional_witnesses_for_all_missing_pair_mutexes")!=len(a) or
        data.get("exact_fractional_witnesses_surviving_three_triangle_CG_cuts")!=len(b)):
        raise ValueError("saved witness totals forged")
    return {
        "status":"SOURCE_EXACT_RATIONAL_WITNESSES_VERIFIED",
        "source_sha256":EXPECTED,
        "source_clauses":len(clauses),
        "missing_graph_conflicts":len(missing),
        "original_relaxation_exact_feasible_pairs":len(a),
        "after_three_source_CG_exact_feasible_pairs":len(b),
        "original_source_numeric_approximations_used_by_checker":False,
        "mathematical_implication":"None of the 81 source-missing graph mutexes follows from the unrounded linear LP relaxation alone."
    }
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--witness",required=True,type=pathlib.Path)
    a=p.parse_args()
    try:
        result=verify(a.witness)
        print("IPG5E_RATIONAL_ACCEPT "+json.dumps(result,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,UnicodeError) as e:
        print("IPG5E_RATIONAL_REJECT "+str(e),flush=True)
        return 1
if __name__=="__main__":
    raise SystemExit(main())
