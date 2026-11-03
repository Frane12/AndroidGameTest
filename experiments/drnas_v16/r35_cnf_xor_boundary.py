#!/usr/bin/env python3
"""R35 read-only CNF/XOR boundary census; no logical claims from heuristics."""
import argparse,collections,hashlib,json,pathlib,time

def analyze(path,limit=250000,max_groups=120000):
    start=time.monotonic()
    groups={}; clauses=[]; n=0; declared=0; seen=0; stop=False
    with path.open("rb") as f:
        pending=[]
        for line in f:
            s=line.strip()
            if not s or s.startswith(b"c") or s.startswith(b"%"):continue
            if s.startswith(b"p "):
                t=s.split()
                if len(t)>=4:n=int(t[2]);declared=int(t[3])
                continue
            for token in s.split():
                x=int(token)
                if x:pending.append(x);continue
                seen+=1
                c=tuple(pending);pending=[]
                if len(clauses)<limit:clauses.append(c)
                else:stop=True;break
                if 2<=len(c)<=4:
                    key=tuple(sorted(map(abs,c)))
                    if len(set(key))==len(key) and (key in groups or len(groups)<max_groups):
                        order=sorted(c,key=lambda z:abs(z))
                        mask=sum(1<<i for i,z in enumerate(order) if z<0)
                        groups.setdefault(key,set()).add(mask)
            if stop:break
    # A full XOR clause group is only recognized if all required sign masks occur.
    xor_keys=set()
    for key,masks in groups.items():
        k=len(key)
        parity=lambda m:m.bit_count()%2
        for rhs in (0,1):
            required={m for m in range(1<<k) if parity(m)==rhs}
            if required<=masks:xor_keys.add(key)
    xor_vars=set(v for key in xor_keys for v in key)
    xor_clauses=0;outside=0;boundary=0;nonxor_internal=0
    outside_degree=collections.Counter();bridge_degree=collections.Counter()
    binary_edges=0;cross_binary=0
    for c in clauses:
        support=tuple(sorted(map(abs,c)))
        if support in xor_keys and 2<=len(c)<=4:
            order=sorted(c,key=lambda z:abs(z))
            mask=sum(1<<i for i,z in enumerate(order) if z<0)
            k=len(support)
            # A clause is part of an exact XOR only if its mask belongs to
            # one of the complete sign-parity classes.
            masks=groups[support]
            parity=lambda m:m.bit_count()%2
            if any({m for m in range(1<<k) if parity(m)==rhs}<=masks
                   and parity(mask)==rhs for rhs in (0,1)):
                xor_clauses+=1;continue
        vs={abs(v) for v in c}
        overlap=vs&xor_vars
        if overlap and len(overlap)<len(vs):
            boundary+=1
            for v in overlap:bridge_degree[v]+=1
        elif overlap:nonxor_internal+=1
        else:outside+=1
        for v in overlap:outside_degree[v]+=1
        if len(c)==2:
            binary_edges+=2
            if overlap and len(overlap)<len(vs):cross_binary+=2
    return dict(file=path.name,declared_vars=n,declared_clauses=declared,
        scanned_clauses=len(clauses),truncated=stop or len(clauses)<declared,
        exact_xor_supports=len(xor_keys),xor_variables=len(xor_vars),
        xor_clauses=xor_clauses,nonxor_boundary_clauses=boundary,
        nonxor_internal_clauses=nonxor_internal,nonxor_outside_clauses=outside,
        nonxor_touching_xor_variables=boundary+nonxor_internal,
        crossing_binary_implications=cross_binary,
        top_boundary_variables=bridge_degree.most_common(10),
        elapsed_s=round(time.monotonic()-start,6),
        mode="shadow_only",certified_new_implications=0,solver_interventions=0)

def main():
    p=argparse.ArgumentParser();p.add_argument("--inputs",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();root=pathlib.Path(a.inputs)
    cases=json.loads((root/"manifest.json").read_text())["cases"]
    if len(cases)!=14:raise RuntimeError("expected frozen 14 cases")
    rows=[]
    for c in cases:
        path=root/c["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=c["raw_sha256"]:raise RuntimeError("SHA mismatch")
        row=analyze(path);row["case_id"]=c["id"];row["sha256"]=c["raw_sha256"]
        rows.append(row);print("R35_BOUNDARY",json.dumps(row,sort_keys=True),flush=True)
    out={"protocol":"R35_boundary_shadow_v1","case_count":len(rows),
         "note":"Retrospective mp1 family; counts are structural, not proof of new implications or speedup.",
         "rows":rows}
    pathlib.Path(a.out).write_text(json.dumps(out,indent=2)+"\n")
    print("R35_AUDIT_PASS",len(rows),"original CNF hashes verified; no solver modifications")
if __name__=="__main__":main()
