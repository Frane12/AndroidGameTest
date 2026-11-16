#!/usr/bin/env python3
"""Experimental UNION prefix: serial proof-producing source analyzers.

This is NOT a second SAT solver or a portfolio: each bounded detector
returns a source-proof candidate or UNKNOWN. Native DRNAS is the fallback.
The independent checker is always mandatory; no result from this file
alone may be accepted as verified.
"""
import argparse,hashlib,json,sys
from collections import defaultdict,deque
from pathlib import Path
RESEARCH=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RESEARCH))
from match2 import parse as read_dimacs
from match2 import prove as match2
from match2_bdd_mask1 import prove as mask1
from structure1_prover import prove as structure1

def binary_source_unsat(raw):
    n,clauses=read_dimacs(raw)
    if n>20000 or len(clauses)>100000:return None
    if any(not c for c in clauses):
        return {"status":"UNSAT_UNCHECKED","method":"SOURCE_BINARY_SUBSET",
                "witness":"EMPTY_SOURCE_CLAUSE"}
    adjacent=defaultdict(list);reverse=defaultdict(list)
    for clause in clauses:
        if len(clause)==1:
            v=clause[0]
            e=[(-v,v)]
        elif len(clause)==2:
            a,b=clause
            e=[(-a,b),(-b,a)]
        else:continue
        for a,b in e:
            adjacent[a].append(b);reverse[b].append(a)
    # Iterative Kosaraju on source binary/unit implication graph.
    nodes=set(adjacent)|set(reverse)
    for v in list(nodes):
        nodes.add(-v)
    visited=set();finish=[]
    for start in nodes:
        if start in visited:continue
        stack=[(start,False)]
        while stack:
            v,post=stack.pop()
            if post:
                finish.append(v);continue
            if v in visited:continue
            visited.add(v);stack.append((v,True))
            stack.extend((w,False) for w in adjacent[v] if w not in visited)
    component={};cid=0
    for root in reversed(finish):
        if root in component:continue
        component[root]=cid;todo=[root]
        while todo:
            v=todo.pop()
            for w in reverse[v]:
                if w not in component:
                    component[w]=cid;todo.append(w)
        cid+=1
    for v in range(1,n+1):
        if v in component and -v in component and component[v]==component[-v]:
            return {"status":"UNSAT_UNCHECKED","method":"SOURCE_BINARY_SUBSET",
                    "witness":"CONTRADICTORY_IMPLICATION_CYCLE","variable":v}
    return None

def prove(raw):
    result={"status":"UNKNOWN","format":"DRNAS-UNION-PRECHECK-V1",
            "source_sha256":hashlib.sha256(raw).hexdigest(),"method":"NONE"}
    if len(raw)>256000:return result
    try:
        binary=binary_source_unsat(raw)
        if binary:
            result.update(binary);return result
        if len(raw)<=120000:
            cert=structure1(raw)
            if cert["status"]=="UNSAT_UNCHECKED":
                result.update(method="STRUCTURE1",inner=cert,status="UNSAT_UNCHECKED")
                return result
            cert=match2(raw)
            if cert["status"]=="UNSAT_UNCHECKED":
                result.update(method="MATCH2",inner=cert,status="UNSAT_UNCHECKED")
                return result
        if len(raw)<=24000:
            cert=mask1(raw)
            if cert["status"]=="UNSAT_UNCHECKED":
                result.update(method="MASK1",inner=cert,status="UNSAT_UNCHECKED")
                return result
    except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError) as error:
        result["reason"]=type(error).__name__
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("cnf",type=Path);p.add_argument("certificate",type=Path)
    args=p.parse_args()
    raw=args.cnf.read_bytes()
    result=prove(raw)
    if result["status"]=="UNSAT_UNCHECKED":
        args.certificate.write_text(json.dumps(result,sort_keys=True)+"\n")
        print("UNION_PRECHECK_UNSAT "+str(result["method"]),flush=True)
        return 20
    print("UNION_PRECHECK_UNKNOWN",flush=True)
    return 0

if __name__=="__main__":raise SystemExit(main())
