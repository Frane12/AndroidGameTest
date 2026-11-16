#!/usr/bin/env python3
"""DRAT-RUP -> VeriPB 3.0 for SOURCE-VALIDATED RUP-ONLY traces.

Every original clause and every proposed learned clause is independently
replayed under UNIT PROPAGATION. A clause that is RAT-but-not-RUP is
REJECTED; this is intentionally NOT a generic DRAT-to-VeriPB converter.
Deletion entries are rejected to avoid silently changing the semantics.
The last added clause must be empty, proven RUP.

This is a STANDARD VeriPB proof of the original 45-variable / 300-clause
weighted Petersen source after external VeriPB acceptance. However,
the underlying search was done by native CDCL/MG7; this is NOT proof
that a new polynomial integer-cover or parity algorithm emitted that trace.
The separate 150-clause graph-coloring proof is combinatorial/parity guided.
"""
import argparse
import hashlib
import json
import pathlib
import sys

def dimacs(path):
    raw=path.read_bytes()
    nv=nc=None;pending=[];clauses=[]
    for line in raw.decode("ascii").splitlines():
        tok=line.split()
        if not tok or tok[0]=="c":continue
        if tok[0]=="p":
            if nv is not None or len(tok)!=4 or tok[1]!="cnf":
                raise ValueError("invalid source DIMACS header")
            nv,nc=int(tok[2]),int(tok[3])
            continue
        if nv is None:raise ValueError("source DIMACS missing header")
        for field in tok:
            value=int(field)
            if abs(value)>nv:raise ValueError("literal outside source header")
            if value:
                pending.append(value)
            else:
                clauses.append(tuple(pending));pending=[]
    if nv is None or pending or len(clauses)!=nc:
        raise ValueError("invalid source DIMACS clause count")
    return raw,nv,clauses

def rup_unit_conflict(clauses,assumptions):
    assigned={}
    for lit in assumptions:
        var=abs(lit)
        val=lit>0
        if var in assigned and assigned[var]!=val:
            return True
        assigned[var]=val
    while True:
        changed=False
        for clause in clauses:
            satisfied=False
            free=0
            last=None
            for lit in clause:
                var=abs(lit)
                if var in assigned:
                    if assigned[var]==(lit>0):
                        satisfied=True
                        break
                else:
                    free+=1
                    last=lit
            if satisfied:continue
            if free==0:return True
            if free==1:
                var=abs(last);val=last>0
                if var in assigned and assigned[var]!=val:return True
                if var not in assigned:
                    assigned[var]=val
                    changed=True
        if not changed:return False

def parse_rup_trace(path,nv):
    rows=[]
    for i,line in enumerate(path.read_text().splitlines(),1):
        tok=line.split()
        if not tok or tok[0]=="c":continue
        if tok[0]=="d":
            raise ValueError(f"DRAT deletion unsupported on line {i}")
        try:
            lits=[int(x) for x in tok]
        except ValueError as error:
            raise ValueError(f"non-integer DRAT row on line {i}") from error
        if lits[-1:]!=[0] or 0 in lits[:-1]:
            raise ValueError(f"malformed DRAT row on line {i}")
        clause=tuple(lits[:-1])
        if any(abs(x)>nv or x==0 for x in clause):
            raise ValueError(f"invalid learned literal on line {i}")
        if len(clause)!=len(set(clause)) or any(-x in clause for x in clause):
            raise ValueError(f"tautological or duplicate learned clause on line {i}")
        rows.append(clause)
    if not rows or rows[-1] or any(not c for c in rows[:-1]):
        raise ValueError("RUP trail must end with one empty contradiction")
    return rows

def clause_to_pbp(c):
    if not c:
        # Inconsistent 0 >= 1, check its parsing and RUP nature externally.
        return "rup >= 1 ;\n"
    return "rup "+" ".join(
        f"1 {'~' if lit<0 else ''}x{abs(lit)}" for lit in c
    )+" >= 1 ;\n"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--drat",required=True,type=pathlib.Path)
    p.add_argument("--veripb",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    p.add_argument("--expected-sha256",default="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70")
    a=p.parse_args()
    try:
        raw,nv,clauses=dimacs(a.cnf)
        sha=hashlib.sha256(raw).hexdigest()
        if sha!=a.expected_sha256:
            raise ValueError("original source changed: SHA mismatch")
        rows=parse_rup_trace(a.drat,nv)
        database=list(clauses)
        for step,c in enumerate(rows,1):
            if not rup_unit_conflict(database,[-x for x in c]):
                raise ValueError(f"not a RUP lemma at step {step}")
            database.append(c)
        a.veripb.parent.mkdir(parents=True,exist_ok=True)
        with a.veripb.open("w") as fd:
            fd.write("pseudo-Boolean proof version 3.0\n")
            fd.write(f"f {len(clauses)} ;\n")
            for clause in rows:fd.write(clause_to_pbp(clause))
            fd.write("output NONE ;\nconclusion UNSAT ;\n")
            fd.write("end pseudo-Boolean proof ;\n")
        report={
            "status":"RUP_ONLY_VERIPB_EMITTED_NOT_YET_CHECKED",
            "source_sha256":sha,
            "source_vars":nv,
            "source_clauses":len(clauses),
            "drat_sha256":hashlib.sha256(a.drat.read_bytes()).hexdigest(),
            "all_RUP_steps_locally_replayed":len(rows),
            "empty_contradiction_last":True,
            "standard_veripb_bytes":a.veripb.stat().st_size,
            "proof_provenance":"NATIVE_CDCL_LEARNT_RUP_NOT_INTEGER_GUARD",
        }
        a.meta.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        print("IPG4_WEIGHTED_RUP_CONVERT "+json.dumps(report,sort_keys=True))
        return 0
    except (ValueError,IndexError,KeyError,OSError,UnicodeError) as error:
        a.veripb.unlink(missing_ok=True)
        print("IPG4_WEIGHTED_CONVERTER_REJECT "+str(error))
        return 1

if __name__=="__main__":
    sys.exit(main())
