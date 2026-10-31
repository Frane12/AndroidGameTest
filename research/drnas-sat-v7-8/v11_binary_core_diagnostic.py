#!/usr/bin/env python3
"""Independent structural diagnosis of near-2-SAT V11 CNFs.

Exploratory post-hoc analysis, NOT a solver benchmark or proven
explanation of Kissat performance. Does not modify benchmark runs.
A contradictory binary+unit subformula proves the FULL CNF UNSAT;
a satisfiable binary projection says nothing about full CNF SAT.
"""
import argparse
import json
import tempfile
from pathlib import Path
import official_shortlong_select as source

MIN_BINARY=0.94
source.RAW_CAP=160*1024*1024
source.CNF_CAP=160*1024*1024
source.VARIABLE_CAP=1_000_000
source.CLAUSE_CAP=4_000_000

def require(condition, message):
    if not condition:
        raise ValueError(message)

def binary_core(variables, clauses):
    """Return SCC-based UNSAT proof on unit/binary clauses only."""
    adj=[[] for _ in range(2*variables)]
    rev=[[] for _ in range(2*variables)]
    count={1:0,2:0,"other":0}
    def node(lit):
        require(0 < abs(lit) <= variables, "Literal out of declared range")
        return 2*(abs(lit)-1)+(1 if lit<0 else 0)
    def edge(a,b):
        adj[a].append(b)
        rev[b].append(a)
    for clause in clauses:
        n=len(clause)
        require(n>0,"Empty clause")
        if n==1:
            count[1]+=1
            a=node(clause[0])
            edge(a^1,a)
        elif n==2:
            count[2]+=1
            a,b=map(node,clause)
            edge(a^1,b)
            edge(b^1,a)
        else:
            count["other"]+=1
    seen=bytearray(2*variables)
    order=[]
    for start in range(2*variables):
        if seen[start]: continue
        seen[start]=1
        stack=[(start,0)]
        while stack:
            v,j=stack[-1]
            if j<len(adj[v]):
                nxt=adj[v][j]
                stack[-1]=(v,j+1)
                if not seen[nxt]:
                    seen[nxt]=1
                    stack.append((nxt,0))
            else:
                order.append(v)
                stack.pop()
    group=[-1]*(2*variables)
    sizes=[]
    for start in reversed(order):
        if group[start]>=0: continue
        cid=len(sizes)
        stack=[start]
        group[start]=cid
        size=0
        while stack:
            v=stack.pop()
            size+=1
            for nxt in rev[v]:
                if group[nxt]<0:
                    group[nxt]=cid
                    stack.append(nxt)
        sizes.append(size)
    contradiction=[i+1 for i in range(variables) if group[2*i]==group[2*i+1]]
    return {"binary_core_unsat":bool(contradiction),
            "contradictory_variable_count":len(contradiction),
            "first_contradictory_variable":contradiction[0] if contradiction else None,
            "units":count[1],"binary":count[2],"nonbinary":count["other"],
            "largest_implication_scc":max(sizes,default=0),
            "nontrivial_implication_sccs":sum(s>1 for s in sizes)}

def parse_cnf(path):
    variables=declared=None
    clauses=[]
    pending=[]
    for line in Path(path).read_bytes().splitlines():
        line=line.strip()
        if not line or line.startswith((b"c",b"%")):continue
        if line.startswith(b"p "):
            parts=line.split()
            require(len(parts)>=4 and parts[1]==b"cnf" and variables is None,
                    "Invalid DIMACS header")
            variables,declared=int(parts[2]),int(parts[3])
            continue
        require(variables is not None,"Missing DIMACS header")
        for token in line.split():
            x=int(token)
            if x:
                require(abs(x)<=variables,"Variable exceeds header")
                pending.append(x)
            else:
                require(pending,"Empty DIMACS clause")
                clauses.append(tuple(pending))
                pending=[]
    require(variables is not None and not pending and len(clauses)==declared,
            "DIMACS clause count mismatch")
    return variables,clauses

def selftest():
    require(binary_core(1,[(1,),(-1,)])["binary_core_unsat"],
            "Opposite units not detected")
    require(binary_core(2,[(1,2),(-1,2)])["binary_core_unsat"] is False,
            "False positive SCC")
    require(binary_core(2,[(1,2),(-1,2),(1,-2),(-1,-2)])["binary_core_unsat"],
            "2-SAT contradiction not detected")
    require(binary_core(2,[(1,2,2),(-1,2)])["binary_core_unsat"] is False,
            "Nonbinary clause must not enter graph")
    print("V11_BINARY_CORE_SELFTEST_PASS")

def diagnose(args):
    m=json.loads(Path(args.manifest).read_text())
    require(m["accepted_count"]==50 and len(m["cases"])==50,
            "Expected pinned V11 50-case manifest")
    candidates=[c for c in m["cases"] if c["features"]["binary_frac"]>=MIN_BINARY]
    require(len(candidates)==6,f"Unexpected number of near-binary V11 cases: {len(candidates)}")
    results=[]
    with tempfile.TemporaryDirectory() as t:
        for c in candidates:
            path=Path(t)/(c["id"]+".cnf")
            fetched=source.download_and_features(c["id"],path)
            require(fetched["sha256"]==c["sha256"] and fetched["features"]==c["features"],
                    "SHA256/feature verification failed "+c["id"])
            v,clauses=parse_cnf(path)
            require(v==c["variables"] and len(clauses)==c["clauses"],"Header mismatch")
            diagnosis=binary_core(v,clauses)
            require(diagnosis["binary"]+diagnosis["units"]+diagnosis["nonbinary"]==c["clauses"],
                    "Inconsistent clause counts")
            if diagnosis["binary_core_unsat"]:
                require(c["official_label"]=="UNSAT","Projection UNSAT contradicts official label")
            result={"id":c["id"],"sha256":c["sha256"],"official_label":c["official_label"],
                    "binary_fraction":c["features"]["binary_frac"],
                    "variables":v,"clauses":len(clauses),**diagnosis}
            results.append(result)
            print("V11_BINARY_CORE_RESULT",c["id"],c["official_label"],
                  "binary_core_unsat="+str(diagnosis["binary_core_unsat"]),
                  "contradictions="+str(diagnosis["contradictory_variable_count"]),
                  "nonbinary="+str(diagnosis["nonbinary"]),flush=True)
            path.unlink(missing_ok=True)
    report={"analysis":"V11 near-binary implication SCC 2026-11-01",
            "scope":"Exploratory; 6 V11 formulas with >=94% binary clauses; no solver tuning",
            "protocol":m["protocol"],"results":results,
            "limitations":["UNSAT proof only if unit/binary projection has contradiction",
                           "A satisfiable 2-CNF projection does not imply full CNF SAT",
                           "Not a causal claim about Kissat speed",
                           "No test performance used as input to this diagnostic"]}
    Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    lines=["# V11 near-binary structural diagnostic","",
      "Exploratory, not a new performance measurement.","",
      "| CNF ID prefix | Official | Binary % | Nonbinary | Projection UNSAT? | Conflicting variables |",
      "|---|---|---:|---:|---|---:|"]
    for r in results:
        lines.append(f'| {r["id"][:12]} | {r["official_label"]} | {100*r["binary_fraction"]:.2f}% | {r["nonbinary"]} | {"YES" if r["binary_core_unsat"] else "NO"} | {r["contradictory_variable_count"]} |')
    lines.extend(["",
      "If binary projection is UNSAT, that is an independently checkable structural sufficient condition for full UNSAT.",
      "If binary projection is satisfiable, the full formula can still be UNSAT."])
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("V11_BINARY_CORE_AUDIT_PASS",len(results),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    a=sub.add_parser("diagnose")
    a.add_argument("--manifest",required=True)
    a.add_argument("--out",required=True)
    a.add_argument("--md",required=True)
    args=p.parse_args()
    selftest() if args.cmd=="selftest" else diagnose(args)
