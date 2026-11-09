#!/usr/bin/env python3
"""DRNAS X10: deterministic bounded-cost original-CNF structural signals.

Samples <=192 KiB, never runs a SAT solver to obtain features. For CNFs
larger than the budget, read bounded first/middle/last windows and accept only
complete single-line clauses. The graph and occurrence statistics describe
the SAMPLE, not a proved property of the entire CNF.
"""
from __future__ import annotations
import collections, math, pathlib, time

WINDOW=65536
MAX_BYTES=3*WINDOW
POLICY_VERSION="X10-source-only-binary-occurrence-implication-SCC-v1"

def _parts(p):
    p=pathlib.Path(p)
    size=p.stat().st_size
    if size<=MAX_BYTES:
        return [p.read_bytes()],True,size
    out=[]
    with p.open("rb") as f:
        for offset in (0,max(0,(size-WINDOW)//2),size-WINDOW):
            f.seek(offset)
            if offset:
                f.readline()  # discard possibly partial clause line
            part=f.read(WINDOW)
            if f.tell()<size and not part.endswith(b"\n"):
                end=part.rfind(b"\n")
                part=part[:end+1] if end>=0 else b""
            out.append(part)
    return out,False,size

def _clauses(parts,full,nvars):
    clauses=[]
    acc=[]
    for part in parts:
        for line in part.splitlines():
            s=line.strip()
            if not s or s.startswith((b"c",b"p",b"%")):
                continue
            try:
                nums=[int(x) for x in s.split()]
            except ValueError:
                if full:raise ValueError("invalid original DIMACS token")
                continue
            if not full and (not nums or nums[-1]!=0 or nums.count(0)!=1):
                continue
            for v in nums:
                if v==0:
                    if acc:clauses.append(tuple(acc))
                    acc=[]
                else:
                    if abs(v)>nvars or abs(v)==0:
                        if full:raise ValueError("literal outside DIMACS variable count")
                        acc=[]
                        break
                    acc.append(v)
            if not full:
                acc=[]
    if full and acc:
        raise ValueError("unterminated original DIMACS clause")
    return clauses

def _largest_scc(adjacency):
    nodes=set(adjacency)
    for destinations in adjacency.values():
        nodes.update(destinations)
    if not nodes:return 0,0,0
    reverse=collections.defaultdict(set)
    for u,targets in adjacency.items():
        for v in targets:reverse[v].add(u)
    visited=set();order=[]
    for root in nodes:
        if root in visited:continue
        visited.add(root)
        stack=[(root,iter(adjacency.get(root,())))]
        while stack:
            v,it=stack[-1]
            try:
                nxt=next(it)
                if nxt not in visited:
                    visited.add(nxt)
                    stack.append((nxt,iter(adjacency.get(nxt,()))))
            except StopIteration:
                order.append(v)
                stack.pop()
    seen=set();largest=0;cyclic=0
    for root in reversed(order):
        if root in seen:continue
        seen.add(root);todo=[root];size=0
        while todo:
            u=todo.pop();size+=1
            for v in reverse.get(u,()):
                if v not in seen:
                    seen.add(v);todo.append(v)
        largest=max(largest,size)
        if size>1:cyclic+=size
    return len(nodes),largest,cyclic

def probe(path,nvars,clauses_expected=None):
    start=time.perf_counter()
    parts,full,size=_parts(path)
    clauses=_clauses(parts,full,nvars)
    if not clauses:
        raise ValueError("zero sample CNF clauses: fail closed")
    if full and clauses_expected is not None and len(clauses)!=clauses_expected:
        raise ValueError("whole source geometry mismatch")
    n=len(clauses)
    widths=collections.Counter(len(c) for c in clauses)
    pos=collections.Counter();neg=collections.Counter()
    graph=collections.defaultdict(set)
    xor=collections.defaultdict(set)
    for clause in clauses:
        for v in clause:
            (pos if v>0 else neg)[abs(v)]+=1
        if len(clause)==2:
            a,b=clause
            if a!=b and a!=-b:
                graph[-a].add(b)
                graph[-b].add(a)
        if len(clause)==3:
            vars=sorted(abs(v) for v in clause)
            if len(set(vars))==3:
                signs={abs(v):int(v<0) for v in clause}
                mask=sum(signs[v]<<j for j,v in enumerate(vars))
                xor[tuple(vars)].add(mask)
    xor_quad=sum({0,3,5,6}.issubset(k) or {1,2,4,7}.issubset(k)
                 for k in xor.values())
    counts=[pos[v]+neg[v] for v in pos.keys()|neg.keys()]
    avg=sum(counts)/len(counts) if counts else 0.0
    cv=(math.sqrt(sum((x-avg)**2 for x in counts)/len(counts))/avg
        if avg>0 else 0.0)
    both=sum(v in pos and v in neg for v in pos.keys()|neg.keys())
    nodes,largest,cyclic=_largest_scc(graph)
    edges=sum(len(v) for v in graph.values())
    reciprocal=sum(u in graph.get(v,()) for u,targets in graph.items()
                   for v in targets)
    outmax=max((len(v) for v in graph.values()),default=0)
    ratio=lambda x:round(x/n,6)
    f=dict(version=POLICY_VERSION,bytes=size,nvars=nvars,
       nclauses=clauses_expected,sampled_clauses=n,
       sample_max_bytes=MAX_BYTES,full_source=full,
       sample_binary_ratio=ratio(widths[2]),
       sample_ternary_ratio=ratio(widths[3]),
       sample_unit_ratio=ratio(widths[1]),
       occurrence_degree_cv=round(cv,6),
       occurrence_max_over_mean=round(max(counts)/avg,6) if avg else 0.0,
       both_polarity_fraction=round(both/len(counts),6) if counts else 0.0,
       implication_vertices=nodes,implication_edges=edges,
       implication_largest_scc_fraction=round(largest/nodes,6) if nodes else 0.0,
       implication_cyclic_fraction=round(cyclic/nodes,6) if nodes else 0.0,
       implication_reciprocal_fraction=round(reciprocal/edges,6) if edges else 0.0,
       implication_max_outdegree=outmax,
       xor4_groups=xor_quad,
       xor4_clause_fraction=min(1,round(xor_quad*4/n,6)),
       no_solver_probe=True)
    return f,round(time.perf_counter()-start,6)

def route(f,with_graph=True):
    """Precommitted theoretical hypothesis; NO historical outcome fitted."""
    binary=f["sample_binary_ratio"]
    tern=f["sample_ternary_ratio"]
    imbalance=f["occurrence_degree_cv"]
    if f["xor4_groups"]>=2 and f["xor4_clause_fraction"]>=0.01:
        return "cms_orig","sampled_ternary_XOR4"
    if (binary>=0.20 and f["both_polarity_fraction"]>=0.65 and
        imbalance>=0.80 and
        (not with_graph or (f["implication_cyclic_fraction"]>=0.06 and
                            f["implication_vertices"]>=20))):
        return "cms_orig","binary_occurrence_graph_cycle" if with_graph else "binary_occurrence_only"
    if (tern>=0.60 and imbalance>=1.00 and f["both_polarity_fraction"]>=0.70 and
        (not with_graph or f["implication_largest_scc_fraction"]>=0.05)):
        return "cms_orig","ternary_occurrence_graph" if with_graph else "ternary_occurrence_only"
    if (f["sample_unit_ratio"]>=0.03 and binary>=0.15 and
        (not with_graph or f["implication_reciprocal_fraction"]>=0.05)):
        return "cadical_173","unit_binary_graph" if with_graph else "unit_binary_only"
    return "kissat_404","conservative_Kissat_fallback"

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"small.cnf"
        p.write_text("c synthetic\np cnf 3 7\n1 2 0\n-1 2 0\n"
                     "-1 -2 0\n1 -2 0\n1 3 0\n-2 3 0\n3 0\n")
        f,t=probe(p,3,7)
        assert f["sampled_clauses"]==7 and f["sample_binary_ratio"]==round(6/7,6),f
        assert f["implication_edges"]>=2 and f["implication_vertices"]>=2
        assert f["sample_unit_ratio"]==round(1/7,6)
        assert f["full_source"] and t>=0
        assert route(f)[0] in ("cms_orig","kissat_404","cadical_173")
        big=pathlib.Path(td)/"big.cnf"
        big.write_bytes(b"p cnf 3 100000\n"+b"1 2 0\n"*100000)
        b,_=probe(big,3,100000)
        assert not b["full_source"] and b["sampled_clauses"]>1000
        assert b["implication_edges"]==2 and b["sample_binary_ratio"]==1.0
    print("X10_PROFILE_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    selftest()
