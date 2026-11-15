#!/usr/bin/env python3
"""AUTO-UNSAT1: one-source, fail-closed, independently checked UNSAT discovery.

A source-bound certificate is required before reporting UNSAT. Structural
proofs are NOT standard DRAT. Small independently checked binary/DPLL cores
can additionally emit DRUP (a subset of DRAT), accepted only by drat-trim.
All detectors are sequential and share a bounded budget; no SAT claim.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from check_capacity import parse_cnf, check as check_capacity
from check_clause_hall import check as check_hall
from check_hall3_hybrid import verify as check_hall3
from check_mixed_unsat import verify as check_mixed
from propose_mixed_unsat import wrap, xor_proof, dpll_proof

CHECKERS = {
    "pcmax-capacity-v1": check_capacity,
    "pcmax-clause-hall-v1": check_hall,
    "pcmax-hall3-hybrid-v1": check_hall3,
}

def binary_scc(raw, nvars, clauses, deadline):
    """Detect arbitrary-size 2-SAT contradictory SCC and return source paths."""
    graph=collections.defaultdict(list)
    reverse=collections.defaultdict(list)
    for i,clause in enumerate(clauses):
        if i%4096==0 and time.perf_counter()>=deadline:
            return None
        if len(clause)==1:
            (a,)=tuple(clause)
            edges=[(-a,a)]
        elif len(clause)==2:
            a,b=tuple(clause)
            edges=[(-a,b),(-b,a)]
        else:
            continue
        for u,v in edges:
            graph[u].append(v)
            reverse[v].append(u)
            graph.setdefault(v,[])
            reverse.setdefault(u,[])
    nodes=set(graph)|set(reverse)
    visited=set()
    order=[]
    for root in sorted(nodes):
        if root in visited: continue
        visited.add(root)
        stack=[(root,iter(graph[root]))]
        while stack:
            if len(visited)%4096==0 and time.perf_counter()>=deadline:
                return None
            node,neighbors=stack[-1]
            nxt=next(neighbors,None)
            if nxt is None:
                order.append(node)
                stack.pop()
            elif nxt not in visited:
                visited.add(nxt)
                stack.append((nxt,iter(graph[nxt])))
    component={}
    cid=0
    for root in reversed(order):
        if root in component:continue
        cid+=1
        component[root]=cid
        stack=[root]
        while stack:
            if len(component)%4096==0 and time.perf_counter()>=deadline:return None
            for v in reverse[stack.pop()]:
                if v not in component:
                    component[v]=cid
                    stack.append(v)
    def path(start,goal):
        q=collections.deque([start])
        parents={start:None}
        while q:
            if time.perf_counter()>=deadline:return None
            node=q.popleft()
            if node==goal:
                result=[]
                while node is not None:
                    result.append(node)
                    node=parents[node]
                return result[::-1]
            for nxt in graph[node]:
                if component.get(nxt)!=component[start] or nxt in parents:continue
                parents[nxt]=node
                q.append(nxt)
        return None
    for variable in sorted({abs(node) for node in nodes}):
        if time.perf_counter()>=deadline:return None
        if component.get(variable) is None or component.get(variable)!=component.get(-variable):continue
        pos=path(variable,-variable)
        neg=path(-variable,variable)
        if pos is not None and neg is not None:
            return wrap(raw,"binary_cycle",pivot=variable,pos_to_neg=pos,neg_to_pos=neg)
    return None

def tiny_component_dpll(raw, clauses, deadline):
    """Find an UNSAT sub-CNF of <=8 connected variables in a big original CNF.

    Only ORIGINAL clauses belonging wholly to a component are submitted to the
    proof producer. Ignoring outside clauses is safe: an UNSAT subformula
    makes its parent UNSAT. The independent checker validates all leaves.
    """
    if len(clauses)>75000:return None
    parent={}
    def root(x):
        parent.setdefault(x,x)
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def join(a,b):
        a,b=root(a),root(b)
        if a!=b: parent[b]=a
    for i,c in enumerate(clauses):
        if i%1024==0 and time.perf_counter()>=deadline:return None
        if not c or len(c)>8:continue
        vs=sorted({abs(l) for l in c})
        for v in vs[1:]:join(vs[0],v)
    groups=collections.defaultdict(list)
    for v in parent:groups[root(v)].append(v)
    eligible={r for r,vs in groups.items() if len(vs)<=8}
    by=collections.defaultdict(set)
    for c in clauses:
        if not c or len(c)>8:continue
        ids={root(abs(l)) for l in c}
        if len(ids)==1:
            r=next(iter(ids))
            if r in eligible:by[r].add(c)
    for r in sorted(eligible,key=lambda x:(len(by[x]),x)):
        if time.perf_counter()>=deadline:return None
        sub=by[r]
        if not sub or len(sub)>512:continue
        proof=dpll_proof(raw,8,sub,deadline)
        if proof is not None:return proof
    return None

def propose_auto(raw,nvars,clauses,deadline):
    if frozenset() in clauses:
        return wrap(raw,"empty_clause")
    for producer in (binary_scc, xor_proof):
        if time.perf_counter()>=deadline:return None
        p=producer(raw,nvars,clauses,deadline)
        if p is not None:return p
    if time.perf_counter()>=deadline:return None
    return tiny_component_dpll(raw,clauses,deadline)

def generate_drup(proof):
    """Only binary-cycle and complete checked DPLL trees have this conversion."""
    method=proof["method"]
    if method=="empty_clause":return "0\n"
    if method=="binary_cycle":
        v=proof["pivot"]
        return f"{-v} 0\n{v} 0\n0\n"
    if method!="dpll_tree":return None
    lines=[]
    def descend(node,assignment):
        if "clause" not in node:
            v=node["split"]
            descend(node["false"],{**assignment,v:False})
            descend(node["true"],{**assignment,v:True})
        lines.append(" ".join(str(-v if value else v)
                              for v,value in sorted(assignment.items())) + " 0")
    descend(proof["tree"],{})
    return "\n".join(lines)+"\n"

def check_drat(src,proof_path,checker,timeout_s=15):
    if checker is None:return False,"checker_missing"
    try:
        p=subprocess.run([str(Path(checker).resolve()),str(src.resolve()),
                          str(proof_path.resolve())],capture_output=True,text=True,
                          timeout=timeout_s)
        report=(p.stdout+"\n"+p.stderr)[-3000:]
        return p.returncode==0 and "VERIFIED" in report,report[-700:]
    except (OSError,subprocess.TimeoutExpired) as e:
        return False,str(e)[-700:]

def run_one(src,binary,out,budget_ms=1200,drat_checker=None):
    started=time.perf_counter()
    deadline=started+budget_ms/1000
    raw=src.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    nvars,clauses=parse_cnf(raw)
    out.mkdir(parents=True,exist_ok=False)
    row={"input":src.name,"source_sha256":digest,"variables":nvars,
         "clauses":len(clauses),"status":"UNKNOWN","method":"none",
         "structural_verified":False,"drat_verified":False,
         "drat_kind":None,"stages":[]}
    def remain_ms():
        return max(0,int((deadline-time.perf_counter())*1000))
    # Prefer Hall for wide scheduling formulas, otherwise low-cost logical cores.
    wide=any(len(c)>8 for c in clauses)
    stages=["hall","mixed"] if wide else ["mixed","hall"]
    chosen=None
    for stage in stages:
        available=remain_ms()
        if available<10:break
        phase_started=time.perf_counter()
        if stage=="mixed":
            p=propose_auto(raw,nvars,clauses,
                 time.perf_counter()+min(available,320)/1000)
            if p is not None:
                # Reconstruct independently, without trusting any proposal.
                evidence=check_mixed(raw,p)
                if evidence["status"]!="UNSAT_VERIFIED":
                    raise AssertionError("unchecked mixed UNSAT proposal")
                chosen=p
                row.update(status="UNSAT_STRUCTURAL_VERIFIED",method=p["method"],
                           structural_verified=True,certificate_format=p["format"])
        else:
            cert=out/"native_hall.json"
            limit=min(available,750)
            command=[str(binary.resolve()),str(src.resolve()),"--mode","core",
                     "--time",str(limit/1000+1),"--pcmax-only","--pcmax-hall3",
                     "--pcmax-budget-ms",str(limit),
                     "--pcmax-certificate",str(cert.resolve())]
            try:
                p=subprocess.run(command,text=True,capture_output=True,
                                 timeout=limit/1000+5)
            except subprocess.TimeoutExpired:
                p=None
            if p is not None and p.returncode not in (0,20):
                raise RuntimeError("native solver unexpected exit: "+str(p.returncode)+" "+p.stderr[-400:])
            if p is not None and p.returncode==20:
                if not cert.is_file():raise AssertionError("missing native Hall certificate")
                proposed=json.loads(cert.read_text())
                fmt=proposed.get("format")
                if fmt not in CHECKERS:raise AssertionError("unrecognized Hall format "+str(fmt))
                evidence=CHECKERS[fmt](raw,proposed)
                if not evidence["status"].startswith("UNSAT_"):
                    raise AssertionError("native Hall did not verify")
                chosen=proposed
                row.update(status="UNSAT_STRUCTURAL_VERIFIED",method=fmt,
                           structural_verified=True,certificate_format=fmt)
            elif cert.exists():
                raise AssertionError("UNSAT certificate from UNKNOWN native result")
        row["stages"].append({"stage":stage,"wall_s":round(time.perf_counter()-phase_started,6),
                              "found":bool(chosen)})
        if chosen is not None:
            (out/"certificate.json").write_text(json.dumps(chosen,sort_keys=True)+"\n")
            break
    if chosen is not None:
        rup=None
        if chosen.get("format")=="drnas-mixed-unsat1":
            rup=generate_drup(chosen)
            if rup is None and chosen.get("method")=="xor_gf2" and remain_ms()>30:
                # RUP-derive small XOR contradictions through a bounded full tree.
                selected={v for b in chosen["blocks"] for v in b["vars"]}
                if len(selected)<=8:
                    sub={c for c in clauses if {abs(l) for l in c} <= selected}
                    d=dpll_proof(raw,8,sub,time.perf_counter()+min(remain_ms(),120)/1000)
                    if d is not None:
                        assert check_mixed(raw,d)["status"]=="UNSAT_VERIFIED"
                        rup=generate_drup(d)
        elif nvars<=8 and len(clauses)<=512 and remain_ms()>30:
            d=dpll_proof(raw,8,clauses,time.perf_counter()+min(remain_ms(),100)/1000)
            if d is not None:
                assert check_mixed(raw,d)["status"]=="UNSAT_VERIFIED"
                rup=generate_drup(d)
        if rup is not None:
            drat=out/"proof.drat"
            drat.write_text(rup)
            good,detail=check_drat(src,drat,drat_checker)
            row["drat_verified"]=good
            row["drat_kind"]="DRUP" if good else None
            row["drat_checker_message"]=detail
            if good:row["status"]="UNSAT_DRAT_VERIFIED"
    row["total_s"]=round(time.perf_counter()-started,6)
    (out/"result.json").write_text(json.dumps(row,sort_keys=True,indent=2)+"\n")
    return row

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("cnf",type=Path)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--drat-checker",type=Path)
    parser.add_argument("--budget-ms",type=int,default=1200)
    args=parser.parse_args()
    if args.budget_ms<50 or args.budget_ms>10000:parser.error("budget 50..10000 ms")
    row=run_one(args.cnf,args.binary,args.out,args.budget_ms,args.drat_checker)
    print("AUTO_UNSAT_RESULT "+json.dumps(row,sort_keys=True))
if __name__=="__main__":main()
