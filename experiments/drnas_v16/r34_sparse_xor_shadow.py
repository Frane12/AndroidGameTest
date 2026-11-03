#!/usr/bin/env python3
"""R34: bounded read-only XOR extraction and sparse GF(2) elimination.
Full parity mask coverage only. Never asserts SAT/UNSAT or changes a solver."""
import argparse, collections, hashlib, json, pathlib, time

def scan(path, max_clauses=15000, max_groups=30000, max_rows=4000, max_ops=150000):
    start=time.monotonic()
    patterns={}
    clauses=0; binary=0; truncated=False; n=0; pending=[]
    digest=hashlib.sha256()
    with path.open("rb") as f:
        for line in f:
            digest.update(line)
            s=line.strip()
            if not s or s.startswith(b"c") or s.startswith(b"%"):continue
            if s.startswith(b"p "):
                t=s.split()
                if len(t)>3:n=int(t[2])
                continue
            if clauses>=max_clauses:
                truncated=True
                break
            for token in s.split():
                lit=int(token)
                if lit:pending.append(lit);continue
                clauses+=1
                if len(pending)==2:binary+=1
                if 2<=len(pending)<=4:
                    key=tuple(sorted(map(abs,pending)))
                    if len(set(key))==len(key) and (key in patterns or len(patterns)<max_groups):
                        order=sorted(pending,key=lambda x:abs(x))
                        mask=sum(1<<i for i,x in enumerate(order) if x<0)
                        patterns.setdefault(key,set()).add(mask)
                pending=[]
                if clauses>=max_clauses:break
            if clauses>=max_clauses:
                truncated=True
                break
    # SHA is pinned by the original normalized manifest, not the sampled stream.
    equations=[];near=0
    for key,masks in patterns.items():
        k=len(key); parity=lambda x:x.bit_count()%2
        even={i for i in range(1<<k) if parity(i)==0}
        odd={i for i in range(1<<k) if parity(i)==1}
        if even.issubset(masks):equations.append((key,1))
        if odd.issubset(masks):equations.append((key,0))
        if not (even.issubset(masks) or odd.issubset(masks)) and len(masks)>=max(2,(1<<(k-1))-1):near+=1
    # Sparse XOR basis: row represented by set of variables. Bound all operations.
    basis={}; contradictions=0; units=set(); operations=0; processed=0
    for key,rhs in equations[:max_rows]:
        row=set(key);value=rhs;processed+=1
        while row:
            pivot=min(row)
            if pivot not in basis:
                basis[pivot]=(row,value)
                break
            other,v=basis[pivot]
            row.symmetric_difference_update(other);value^=v;operations+=1
            if operations>=max_ops:break
        if operations>=max_ops:break
        if not row and value:contradictions+=1
    # Single-variable equations in reduced basis are implied by source XOR subset.
    # This is NOT an independently checked original-CNF certificate.
    for row,rhs in basis.values():
        if len(row)==1:units.add((next(iter(row)),rhs))
    return dict(file=path.name,declared_vars=n,scanned_clauses=clauses,
        binary_clauses=binary,group_count=len(patterns),full_xor_equations=len(equations),
        near_xor_candidates=near,eliminated_rows=processed,rank=len(basis),
        algebraic_contradictions=contradictions,basis_singletons=len(units),
        elimination_ops=operations,resource_limit_hit=operations>=max_ops or len(equations)>max_rows,
        truncated=truncated,scan_and_eliminate_s=round(time.monotonic()-start,6),
        certified_original_clause_proofs=0,solver_interventions=0,mode="shadow_only")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--inputs",required=True);a.add_argument("--out",required=True)
    x=a.parse_args();root=pathlib.Path(x.inputs)
    manifest=json.loads((root/"manifest.json").read_text())
    rows=[]
    for case in manifest["cases"]:
        path=root/case["path"]
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=case["raw_sha256"]:raise RuntimeError("SHA mismatch "+str(path))
        row=scan(path)
        row["sha256"]=actual;row["case_id"]=case["id"]
        rows.append(row);print("R34_SHADOW",json.dumps(row,sort_keys=True),flush=True)
    if len(rows)!=14:raise RuntimeError("expected 14 cases")
    output={"protocol":"R34_sparse_shadow_v1","source_run":41623227197,
      "case_count":len(rows),"total_equations":sum(r["full_xor_equations"] for r in rows),
      "total_algebraic_contradictions":sum(r["algebraic_contradictions"] for r in rows),
      "total_basis_singletons":sum(r["basis_singletons"] for r in rows),
      "warning":"Algebraic observations only. No original-clause proof certificates, no solver intervention, no PAR2 speedup measured.",
      "rows":rows}
    pathlib.Path(x.out).write_text(json.dumps(output,indent=2)+"\n")
    print("R34_AUDIT_PASS",len(rows),"original SHA-verified; read-only")
if __name__=="__main__":main()
