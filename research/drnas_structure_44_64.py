#!/usr/bin/env python3
"""Exact structural audit of ORIGINAL official SAT2024 PCMAX #44 and WORKER #64.

Observational research only. Never claim UNSAT without a proof artifact.
Analyzes renamable-Horn (2-SAT), binary implication graph, Horn closure,
root unit propagation, pure-literal elimination and a Horn backdoor upper bound.
No solver implementation changes or benchmark-promotion decisions.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import drnas_focus_44_64 as F

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"pcmax_structure"
def emit(k,v):print(k+" "+json.dumps(v,sort_keys=True),flush=True)

def parse(path,expected):
    assert F.sha(path)==expected,"original CNF SHA drift"
    clauses=[];current=[];declared=None;taut=0;duplicated=0
    for line in path.open("r",encoding="ascii",errors="replace"):
        line=line.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("%"):break
        if line.startswith("p "):
            parts=line.split()
            assert parts[1]=="cnf" and len(parts)>=4
            declared=(int(parts[2]),int(parts[3]))
            continue
        for s in line.split():
            lit=int(s)
            if lit:
                assert declared and 0<abs(lit)<=declared[0]
                current.append(lit)
            else:
                z=tuple(dict.fromkeys(current))
                duplicated+=len(current)-len(z)
                if any(-v in z for v in z):taut+=1
                else:clauses.append(z)
                current=[]
    assert declared and not current
    assert len(clauses)+taut==declared[1]
    return declared[0],clauses,{"tautological_clauses_omitted":taut,"duplicate_literals_removed":duplicated}

def scc(graph,reverse):
    n=len(graph);seen=bytearray(n);order=[]
    for root in range(n):
        if seen[root]:continue
        seen[root]=1;stack=[(root,0)]
        while stack:
            v,i=stack[-1]
            if i<len(graph[v]):
                w=graph[v][i];stack[-1]=(v,i+1)
                if not seen[w]:
                    seen[w]=1;stack.append((w,0))
            else:order.append(v);stack.pop()
    group=[-1]*n;counts=[];cid=0
    for root in reversed(order):
        if group[root]>=0:continue
        stack=[root];group[root]=cid;size=0
        while stack:
            v=stack.pop();size+=1
            for w in reverse[v]:
                if group[w]<0:group[w]=cid;stack.append(w)
        counts.append(size);cid+=1
    return group,counts

def renamable_horn(n,clauses):
    # flip[v]=1 flips signs of occurrences of v.
    # A literal is positive after flipping for flip[v]==0 if it
    # was positive, and flip[v]==1 if it was negative.
    adj=[[] for _ in range(2*n)];rev=[[] for _ in range(2*n)]
    constraints=0
    for clause in clauses:
        for i in range(len(clause)):
            a=clause[i];u=2*(abs(a)-1)+(0 if a>0 else 1)
            for b in clause[i+1:]:
                v=2*(abs(b)-1)+(0 if b>0 else 1)
                # forbid (positive-after-flip(a) & positive-after-flip(b))
                adj[u].append(v^1);rev[v^1].append(u)
                adj[v].append(u^1);rev[u^1].append(v)
                constraints+=1
    comps,sizes=scc(adj,rev)
    conflicts=[v for v in range(1,n+1) if comps[2*(v-1)]==comps[2*(v-1)+1]]
    result={"renamable_horn":not bool(conflicts),"pair_constraints":constraints,
            "scc_count":len(sizes),"max_scc_nodes":max(sizes,default=0),
            "contradictory_flip_variables":len(conflicts)}
    if not conflicts:
        flips={v:comps[2*(v-1)]<comps[2*(v-1)+1] for v in range(1,n+1)}
        assert all(sum((lit>0)!=flips[abs(lit)] for lit in clause)<=1 for clause in clauses)
        transformed=[tuple(-lit if flips[abs(lit)] else lit for lit in clause) for clause in clauses]
        horn=horn_closure(n,transformed)
        result.update(flipped_variables=sum(flips.values()),
                      transformed_horn_contradiction=horn["contradiction"],
                      transformed_horn_forced_true=horn["forced_true"])
        if not horn["contradiction"]:
            chosen=set(horn["true_vars"])
            original_model={v:(v in chosen)^flips[v] for v in range(1,n+1)}
            valid=all(any(original_model[abs(l)]==(l>0) for l in clause) for clause in clauses)
            assert valid,"renamable Horn SAT assignment did not verify"
            result["transformed_sat_model_valid"]=valid
    return result

def binary_implication(n,clauses):
    adj=[[] for _ in range(2*n)];rev=[[] for _ in range(2*n)]
    edges=0;binary=0;units=0
    def node(lit):return 2*(abs(lit)-1)+(1 if lit>0 else 0)
    def add(a,b):
        nonlocal edges
        u=node(a);v=node(b);adj[u].append(v);rev[v].append(u);edges+=1
    for clause in clauses:
        if len(clause)==1:
            units+=1;add(-clause[0],clause[0])
        elif len(clause)==2:
            binary+=1
            a,b=clause
            add(-a,b);add(-b,a)
    groups,sizes=scc(adj,rev)
    contradictory=[v for v in range(1,n+1) if groups[node(v)]==groups[node(-v)]]
    return {"unit_clauses":units,"binary_clauses":binary,"implication_edges":edges,
            "scc_count":len(sizes),"nontrivial_sccs":sum(size>1 for size in sizes),
            "largest_scc":max(sizes,default=0),
            "binary_subformula_unsat":bool(contradictory),
            "contradictory_variables":len(contradictory)}

def horn_closure(n,clauses):
    # Exact Dowling-Gallier style forward closure for a Horn subformula.
    heads=[];needs=[];depend=[[] for _ in range(n+1)]
    horn_count=0;nonhorn=0;queue=collections.deque()
    for clause in clauses:
        positives=[x for x in clause if x>0]
        if len(positives)>1:
            nonhorn+=1;continue
        idx=len(heads);horn_count+=1
        head=positives[0] if positives else 0
        heads.append(head)
        needs.append(sum(x<0 for x in clause))
        for lit in clause:
            if lit<0:depend[-lit].append(idx)
        if needs[idx]==0:
            if head==0:
                return {"horn_count":horn_count,"nonhorn_count":nonhorn,
                        "contradiction":True,"forced_true":0,"true_vars":[]}
            queue.append(head)
    truevars=set()
    while queue:
        v=queue.popleft()
        if v in truevars:continue
        truevars.add(v)
        for c in depend[v]:
            needs[c]-=1
            if needs[c]==0:
                if heads[c]==0:
                    return {"horn_count":horn_count,"nonhorn_count":nonhorn,
                        "contradiction":True,"forced_true":len(truevars),
                        "true_vars":sorted(truevars)}
                queue.append(heads[c])
    return {"horn_count":horn_count,"nonhorn_count":nonhorn,
            "contradiction":False,"forced_true":len(truevars),
            "true_vars":sorted(truevars)}

def propagation(n,clauses,pure=False):
    occurrences=[[] for _ in range(n+1)]
    for i,clause in enumerate(clauses):
        for lit in clause:occurrences[abs(lit)].append((i,lit))
    assigned=[0]*(n+1)
    satisfied=[False]*len(clauses)
    remaining=[len(x) for x in clauses]
    forced=0;chosen_pure=0;rounds=0;conflict=False
    queue=collections.deque(c[0] for c in clauses if len(c)==1)
    if any(len(c)==0 for c in clauses):conflict=True
    def process():
        nonlocal conflict,forced
        while queue and not conflict:
            lit=queue.popleft();v=abs(lit);sign=1 if lit>0 else -1
            if assigned[v]:
                if assigned[v]!=sign:conflict=True
                continue
            assigned[v]=sign;forced+=1
            for ci,occ in occurrences[v]:
                if satisfied[ci]:continue
                if occ*sign>0:
                    satisfied[ci]=True
                else:
                    remaining[ci]-=1
                    if remaining[ci]==0:conflict=True;break
                    if remaining[ci]==1:
                        rest=next((x for x in clauses[ci] if assigned[abs(x)]==0),None)
                        assert rest is not None
                        queue.append(rest)
    process()
    root_forced=forced
    if pure:
        while not conflict:
            pos=[0]*(n+1);neg=[0]*(n+1)
            for ci,cl in enumerate(clauses):
                if satisfied[ci]:continue
                for lit in cl:
                    if assigned[abs(lit)]!=0:continue
                    if lit>0:pos[lit]+=1
                    else:neg[-lit]+=1
            chosen=[v if pos[v]>0 else -v for v in range(1,n+1)
                    if not assigned[v] and ((pos[v]>0) != (neg[v]>0))]
            if not chosen:break
            rounds+=1;chosen_pure+=len(chosen)
            queue.extend(chosen);process()
    live=[i for i in range(len(clauses)) if not satisfied[i]]
    return {"contradiction":conflict,"root_forced":root_forced,
            "assignments_total":sum(bool(x) for x in assigned),"pure_rounds":rounds,
            "pure_selected":chosen_pure,
            "remaining_clauses":len(live),
            "remaining_nonhorn":sum(sum(lit>0 and not assigned[lit] for lit in clauses[i])>1 for i in live),
            "remaining_variables":len({abs(lit) for i in live for lit in clauses[i] if not assigned[abs(lit)]})}

def greedy_horn_backdoor(clauses):
    # Valid *upper bound* for a strong Horn backdoor by deleting every
    # chosen variable from all clauses. Not a minimal-backdoor claim.
    bad=[set(lit for lit in c if lit>0) for c in clauses if sum(l>0 for l in c)>1]
    counts=[len(x) for x in bad]
    incidence=collections.defaultdict(list)
    for j,vs in enumerate(bad):
        for v in vs:incidence[v].append(j)
    selected=[]
    while any(k>1 for k in counts):
        scores={v:sum(counts[i]>1 for i in ids) for v,ids in incidence.items()
                if v not in selected}
        v=max(scores,key=lambda x:(scores[x],-x))
        assert scores[v]>0
        selected.append(v)
        for idx in incidence[v]:
            counts[idx]-=1
        assert len(selected)<=len(incidence)
    return {"nonhorn_original":len(bad),"backdoor_upper_bound_variables":len(selected),
            "backdoor_fraction":round(len(selected)/max(1,len(incidence)),5),
            "backdoor_first_20":selected[:20],
            "nonhorn_positive_variables":len(incidence)}

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    src=F.pick_sources()
    OUTPUT.mkdir(exist_ok=True)
    report={"protocol":"ORIGINAL44-64-STRUCTURE-V1",
            "read_only":True,"no_solver_mutation":True,
            "source_run":43613581688,"formulas":{}}
    for ident in (44,64):
        t=time.perf_counter()
        item=src[ident];p=ROOT/item["path"]
        n,clauses,normalization=parse(p,item["sha256"])
        horn=horn_closure(n,clauses)
        del horn["true_vars"]
        details={"source_sha256":item["sha256"],"family":item["normalized_name_family"],
                 "vars":n,"clauses":len(clauses),"normalization":normalization,
                 "horn_closure":horn,
                 "renamable_horn":renamable_horn(n,clauses),
                 "binary_implication":binary_implication(n,clauses),
                 "root_unit_propagation":propagation(n,clauses,pure=False),
                 "pure_literal_plus_unit":propagation(n,clauses,pure=True),
                 "greedy_horn_backdoor":greedy_horn_backdoor(clauses)}
        details["audit_elapsed_s"]=round(time.perf_counter()-t,5)
        report["formulas"][str(ident)]=details
        emit("STRUCTURE_CASE",{"id":ident,**details})
    (OUTPUT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("STRUCTURE_FINAL",{"status":"COMPLETE","formulas":report["formulas"]})
if __name__=="__main__":main()
