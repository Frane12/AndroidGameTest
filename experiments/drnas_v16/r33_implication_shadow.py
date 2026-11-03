#!/usr/bin/env python3
"""R33 bounded, read-only CNF implication/XOR candidate scanner. No SAT claims."""
import argparse, collections, hashlib, json, pathlib, time

def scan(path, max_bytes, max_clauses, max_edges, max_groups):
    start=time.monotonic()
    h=hashlib.sha256()
    variables=0; declared=0; clauses=0; binary=0; scanned=0; truncated=False
    graph=collections.defaultdict(set)
    groups={}
    pending=[]
    with open(path,"rb") as f:
        while True:
            line=f.readline()
            if not line: break
            h.update(line)
            if scanned >= max_bytes or clauses >= max_clauses:
                truncated=True
                for rest in iter(lambda:f.read(1024*1024),b""): h.update(rest)
                break
            scanned+=len(line)
            s=line.strip()
            if not s or s.startswith(b"c") or s.startswith(b"%"):continue
            if s.startswith(b"p "):
                fields=s.split()
                if len(fields)>=4 and fields[1]==b"cnf":
                    variables=int(fields[2]);declared=int(fields[3])
                continue
            for tok in s.split():
                v=int(tok)
                if v:pending.append(v)
                else:
                    clauses+=1
                    if len(pending)==2:
                        binary+=1
                        a,b=pending
                        if sum(map(len,graph.values()))<max_edges:
                            graph[-a].add(b);graph[-b].add(a)
                    if 2<=len(pending)<=4 and len(groups)<max_groups:
                        ids=tuple(sorted(map(abs,pending)))
                        if len(set(ids))==len(ids):
                            ordered=sorted(pending,key=lambda x:abs(x))
                            mask=sum(1<<i for i,x in enumerate(ordered) if x<0)
                            groups.setdefault(ids,set()).add(mask)
                    pending=[]
                    if clauses>=max_clauses:break
            if clauses>=max_clauses:
                truncated=True
                for rest in iter(lambda:f.read(1024*1024),b""):h.update(rest)
                break
    complete=0; partial=0
    for ids,masks in groups.items():
        k=len(ids)
        parity=[sum((m>>j)&1 for j in range(k))%2 for m in range(1<<k)]
        even={m for m,p in enumerate(parity) if p==0}
        odd={m for m,p in enumerate(parity) if p==1}
        if even<=masks or odd<=masks:complete+=1
        elif len(masks)>=max(2,(1<<(k-1))-1):partial+=1
    reciprocal=sum(1 for a,bs in graph.items() for b in bs if a in graph.get(b,set()))
    return dict(file=path.name,sha256=h.hexdigest(),declared_vars=variables,
                declared_clauses=declared,scanned_clauses=clauses,
                binary_clauses=binary,implication_nodes=len(graph),
                implication_edges=sum(map(len,graph.values())),
                reciprocal_edges=reciprocal,full_xor_supports=complete,
                near_xor_candidates=partial,group_count=len(groups),
                truncated=truncated,elapsed_s=round(time.monotonic()-start,6),
                mode="shadow_only",proofs=0,solver_interventions=0)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--inputs",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--max-bytes",type=int,default=8*1024*1024)
    p.add_argument("--max-clauses",type=int,default=15000)
    p.add_argument("--max-edges",type=int,default=100000)
    p.add_argument("--max-groups",type=int,default=25000)
    a=p.parse_args()
    root=pathlib.Path(a.inputs)
    manifest=json.loads((root/"manifest.json").read_text())
    cases=manifest["cases"]
    rows=[]
    for case in cases:
        candidates=[v for v in case.values() if isinstance(v,str) and v.endswith(".cnf")]
        if not candidates:
            raise RuntimeError("No normalized CNF filename in manifest case: "+repr(case))
        path=root/pathlib.Path(candidates[0]).name
        if not path.exists():raise FileNotFoundError(str(path))
        result=scan(path,a.max_bytes,a.max_clauses,a.max_edges,a.max_groups)
        rows.append(result)
        print("R33_SHADOW",json.dumps(result,sort_keys=True),flush=True)
    pathlib.Path(a.out).write_text(json.dumps({"protocol":"R33_shadow_v1","rows":rows,
        "case_count":len(rows),"no_certified_inferences":True},indent=2))
    assert len(rows)==14
    print("R33_SHADOW_AUDIT_PASS",len(rows),"official reused cases; no solver modifications")
if __name__=="__main__":main()
