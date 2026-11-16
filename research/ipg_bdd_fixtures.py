#!/usr/bin/env python3
"""Generate genuine exact direct scheduling CNF + *BDD encoded* machine loads.

All source BDD transition clauses are emitted from deterministic canonical
dynamic programs. These are generated CONTROLS, not original SAT
competition formulas. Testing against their independent exact scheduling
oracle is critical; no expected label is visible to BDD extractor/solver.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import itertools
import json

def instance(jobs,m,T):
    n=len(jobs)
    x=lambda j,k:j*m+k+1
    clauses=[]
    for j in range(n):
        group=[x(j,k) for k in range(m)]
        clauses.append(group)
        clauses.extend([[-a,-b] for a,b in itertools.combinations(group,2)])
    nodes=m*n
    def newvar():
        nonlocal nodes
        nodes+=1
        return nodes
    machines=[]
    for k in range(m):
        yes=newvar()
        no=newvar()
        clauses.append([yes])
        clauses.append([-no])
        memo={}
        transitions={}
        def visit(i,used):
            if i==n:return yes
            key=i,used
            if key in memo:return memo[key]
            state=newvar()
            memo[key]=state
            left=visit(i+1,used)
            right=visit(i+1,used+jobs[i]) if used+jobs[i]<=T else no
            transitions[state]=(i,left,right)
            return state
        root=visit(0,0)
        clauses.append([root])
        for state,(j,left,right) in sorted(transitions.items()):
            clauses.append([-state,x(j,k),left])
            clauses.append([-state,-x(j,k),right])
        machines.append({"machine":k,"root":root,"yes":yes,"no":no,
                         "BDD_nodes":len(transitions)})
    text=(f"c Source-derived PCMAX BDD fixture; job-count={n}, m={m}, T={T}\n"
          +f"p cnf {nodes} {len(clauses)}\n"
          +"".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    return text.encode(),machines

def oracle(jobs,m,T):
    remaining=[T]*m
    jobs=sorted(jobs,reverse=True)
    def solve(i):
        if i==len(jobs):return True
        seen=set()
        for k in range(m):
            if remaining[k]<jobs[i] or remaining[k] in seen:continue
            seen.add(remaining[k])
            remaining[k]-=jobs[i]
            if solve(i+1):return True
            remaining[k]+=jobs[i]
        return False
    return solve(0)

def cases(folder):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    jobs=[
        ("three_large",[6,6,6],10),
        ("four_large",[6,6,6,6],10),
        ("mixed_gap",[6,6,6,3,3,3,3],10),
        ("mixed_fit",[6,6,6,3,3,3],10),
        ("five_mixed",[6,6,3,3,3],10),
        ("seven_equal",[5]*7,9),
        ("six_equal",[4]*6,8),
        ("two_class",[7,7,5,5,5,5,5],12),
    ]
    found=[]
    for key,durations,cap in jobs:
        for m in (2,3):
            src,details=instance(durations,m,cap)
            path=folder/(key+f"_m{m}.cnf")
            path.write_bytes(src)
            found.append({
                "name":path.name,
                "expected":"SAT" if oracle(durations,m,cap) else "UNSAT",
                "sha256":hashlib.sha256(src).hexdigest(),
                "jobs":durations,"machines":m,"capacity":cap,
                "bdd_nodes":sum(z["BDD_nodes"] for z in details),
            })
    (folder/"manifest.json").write_text(json.dumps(found,indent=2)+"\n")
    return found

if __name__=="__main__":
    x=cases("results/ipg_bdd1/generated")
    print("IPG_BDD_FIXTURES "+json.dumps(x,sort_keys=True))
