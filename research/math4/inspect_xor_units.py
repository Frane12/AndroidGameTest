#!/usr/bin/env python3
"""Explore original XOR constraints after *root* unit propagation.

Scientific diagnostic only. It never labels CNFs UNSAT: a proposal becomes
certified only after an independent source-clause checker validates it.
Operates only on small SHA-frozen original instances with exact XOR rows.
"""
import collections
import hashlib
import json
import os
import time
from pathlib import Path

SOURCES={6,7,10,11,17}  # light-out, circuit miters, van-der-Waerden

def read_cnf(path,max_clauses=50000):
    pending=[]
    clauses=[]
    nvars=None
    with path.open("r",encoding="ascii") as fd:
        for line in fd:
            words=line.split()
            if not words or words[0]=="c":continue
            if words[0]=="p":
                assert nvars is None and words[:2]==["p","cnf"]
                nvars=int(words[2]);continue
            for word in words:
                lit=int(word)
                if lit:pending.append(lit)
                else:
                    clauses.append(tuple(pending));pending=[]
                    assert len(clauses)<=max_clauses
    assert not pending
    return nvars,clauses

def discover_xor(clauses):
    patterns={}
    for clause in clauses:
        if not 2<=len(clause)<=6:continue
        support=tuple(sorted(abs(l) for l in clause))
        if len(set(support))!=len(support):continue
        signs=frozenset(abs(l) for l in clause if l<0)
        entry=patterns.setdefault(support,[set(),set()])
        entry[len(signs)%2].add(signs)
    rows=[]
    for support,parities in patterns.items():
        for forbid in (0,1):
            if len(parities[forbid])==1<<(len(support)-1):
                rows.append((support,1-forbid))
    return rows

def root_units(clauses,limit_s=1.2):
    assigned={}
    rounds=0
    begin=time.perf_counter()
    while time.perf_counter()-begin<limit_s:
        rounds+=1
        changes=0
        for clause in clauses:
            unknown=0
            unknown_lit=0
            satisfied=False
            for lit in clause:
                val=assigned.get(abs(lit))
                if val is None:
                    unknown+=1;unknown_lit=lit
                    # Unknown count beyond one doesn't need full counting
                elif val==(lit>0):
                    satisfied=True
                    break
            if satisfied:continue
            if unknown==0:return assigned,rounds,True,True
            if unknown==1:
                var=abs(unknown_lit)
                value=unknown_lit>0
                if var in assigned and assigned[var]!=value:
                    return assigned,rounds,True,True
                if var not in assigned:
                    assigned[var]=value
                    changes+=1
        if changes==0:return assigned,rounds,False,True
    return assigned,rounds,False,False

def reduce_xor(rows,unit_assignments):
    basis={}
    entries=[(sum(1<<(v-1) for v in support),parity,"xor",support)
             for support,parity in rows]
    entries.extend([(1<<(var-1),int(v),"unit",(var,))
                    for var,v in sorted(unit_assignments.items())])
    for i,(bits,rhs,typ,support) in enumerate(entries):
        bitset=1<<i
        while bits:
            pivot=bits.bit_length()-1
            if pivot not in basis:
                basis[pivot]=(bits,rhs,bitset)
                break
            bb,br,bt=basis[pivot]
            bits^=bb;rhs^=br;bitset^=bt
        if bits==0 and rhs==1:
            used=[j for j in range(len(entries)) if (bitset>>j)&1]
            return len(basis),used,collections.Counter(entries[j][2] for j in used),entries
    return len(basis),[],{},entries

def main():
    manifest=json.loads(Path("research/hall3/manifest.json").read_text())
    out=Path("math4_unit_audit")
    out.mkdir(exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    rows=[]
    for src in manifest["sources"]:
        if src["id"] not in SOURCES:continue
        path=Path(src["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest()==src["sha256"]
        started=time.perf_counter()
        nv,clauses=read_cnf(path)
        equations=discover_xor(clauses)
        units,rounds,root_unsat,closed=root_units(clauses)
        rank,used,types,entries=reduce_xor(equations,units)
        witness=[{"kind":entries[j][2],"variables":list(entries[j][3]),
                  "rhs":entries[j][1]} for j in used]
        row={"id":src["id"],"family":src["family"],"catalog_label":src["catalog_label"],
             "sha256":src["sha256"],"variables":nv,"clauses":len(clauses),
             "xor_source_equations":len(equations),"root_units":len(units),
             "bcp_rounds":rounds,"bcp_closed":closed,"bcp_conflict":root_unsat,
             "gf2_rank":rank,"xor_plus_units_conflict_candidate":bool(used),
             "trace_count":len(used),"trace_kinds":dict(types),
             "trace":witness,"elapsed_s":round(time.perf_counter()-started,5)}
        rows.append(row)
        print("MATH4_UNIT_SOURCE "+json.dumps({k:row[k] for k in
            ("id","family","catalog_label","xor_source_equations","root_units",
             "bcp_closed","bcp_conflict","gf2_rank",
             "xor_plus_units_conflict_candidate","trace_count","trace_kinds","elapsed_s")},sort_keys=True),flush=True)
    result={"sources":len(rows),"candidates":sum(r["xor_plus_units_conflict_candidate"] for r in rows),
            "all_sha_verified":True,"rows":rows}
    (out/"results.json").write_text(json.dumps(result,indent=2)+"\n")
    print("MATH4_UNIT_FINAL "+json.dumps({
        "sources":result["sources"],"candidates":result["candidates"],
        "source_ids":[r["id"] for r in rows if r["xor_plus_units_conflict_candidate"]]
    },sort_keys=True),flush=True)
if __name__=="__main__":main()
