#!/usr/bin/env python3
"""DELTAX conflict-depth 1: independently constructed guarded-CNF families.

Seed motif is the previously verified real-miter nonlinear pair; new chains
and guarded-selector traps add separate structure. Renaming is not counted
as independent mathematics. Role annotations stay in the TEST harness and
are NEVER passed to the solver.
"""
import hashlib
import json
import random
from pathlib import Path

from synthetic_formulas import BASE,remap

def generate():
    out=[]
    def add(name,n,clauses,group,role=None):
        assert max((abs(l) for c in clauses for l in c),default=0)<=n
        out.append({"name":name,"n":n,"clauses":clauses,
                    "group":group,"role":role or {i:i for i in range(1,6)}})
    add("original_motif",5,BASE+[[-3],[-4]],"guarded_positive")

    # Distinct downstream chain lengths, ending in a free literal.
    # They can be satisfied, and never force an UNSAT claim from an oracle.
    for length in range(1,6):
        clauses=BASE+[[-3],[-4]]
        for v in range(5,5+length):
            clauses.append([-v,v+1])
        add(f"tail_{length}",5+length,clauses,"guarded_positive")

    # Selector traps: selector=1 forces x1=1 and x5=0. This branch is
    # inconsistent; selector=0 remains a satisfying assignment. No control
    # assumption is silently injected into a solver.
    for length in range(0,6):
        clauses=BASE+[[-3],[-4]]
        selector=6
        if length==0:
            clauses += [[-selector,1],[-selector,-5]]
            n=6
        else:
            for v in range(selector,selector+length):
                clauses.append([-v,v+1])
            last=selector+length
            clauses += [[-last,1],[-last,-5]]
            n=last
        add(f"selector_trap_{length}",n,clauses,"selector_trap")

    # Renamed and reordered examples: 12 stimuli, only one underlying
    # structural family; prevent hardcoded ID or clause-order dependence.
    for seed in range(12):
        rng=random.Random(14061114+seed)
        n=7 if seed%2==0 else 9
        mapping={v:p for v,p in zip(range(1,n+1),rng.sample(range(1,n+1),n))}
        clauses=BASE+[[-3],[-4],[-5,6],[-6,7]]
        if n==9 and seed%3==1:
            clauses += [[-7,8],[-8,9]]
        cnf=remap(clauses,mapping)
        rng.shuffle(cnf)
        add(f"renamed_chain_{seed:02}",n,cnf,"renamed_positive",mapping)

    # Negative controls: they must NOT be counted as newly discovered
    # nonlinear-join guarded equalities.
    add("no_guard_units",5,BASE,"negative")
    add("single_guard_only",5,BASE+[[-3]],"negative")
    add("reverse_leg_missing",5,
        [c for c in BASE if c not in ([1,-5],[2,-5])]+[[-3],[-4]],"negative")
    add("linear_only",5,[[-1,2],[1,-2],[-2,5],[2,-5],[-3],[-4]],"negative")
    add("root_unsat_control",5,BASE+[[-3],[-4],[1],[-5]],"negative")
    return out

def write(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    results=[]
    for case in generate():
        content=(f"p cnf {case['n']} {len(case['clauses'])}\n"+
                 "".join(" ".join(map(str,c))+" 0\n" for c in case["clauses"]))
        dest=folder/(case["name"]+".cnf")
        dest.write_text(content)
        results.append({k:v for k,v in case.items() if k!="clauses"}|
                       {"path":str(dest),"sha256":hashlib.sha256(dest.read_bytes()).hexdigest(),
                        "clauses":len(case["clauses"])})
    (folder/"manifest.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    return results

if __name__=="__main__":
    rows=write("deltax_depth1_inputs")
    print("DELTAX_DEPTH1_SOURCES",json.dumps({
        "sources":len(rows),"groups":{g:sum(c["group"]==g for c in rows)
                 for g in sorted({c["group"] for c in rows})}},sort_keys=True))
