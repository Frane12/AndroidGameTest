#!/usr/bin/env python3
"""R36: sound binary-clause implication-path certificates at XOR/CNF boundary.
A path x -> not(x) proves unit not(x). No solver modification."""
import argparse,collections,hashlib,json,pathlib,time

def scan(path, max_clauses=250000, max_sources=128, max_visits=25000):
    t=time.monotonic(); clauses=[]; groups={}; n=0; declared=0; truncated=False; pending=[]
    with path.open("rb") as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith(b"c") or s.startswith(b"%"):continue
            if s.startswith(b"p "):
                p=s.split();n=int(p[2]);declared=int(p[3]);continue
            for token in s.split():
                v=int(token)
                if v:pending.append(v);continue
                c=tuple(pending);pending=[]
                if len(clauses)>=max_clauses:truncated=True;break
                clauses.append(c)
                if 2<=len(c)<=4 and len(set(map(abs,c)))==len(c):
                    key=tuple(sorted(map(abs,c)))
                    ordered=sorted(c,key=lambda x:abs(x))
                    mask=sum(1<<i for i,x in enumerate(ordered) if x<0)
                    groups.setdefault(key,set()).add(mask)
            if truncated:break
    xor_vars=set()
    for key,masks in groups.items():
        k=len(key)
        for parity in (0,1):
            if all(m in masks for m in range(1<<k) if m.bit_count()%2==parity):
                xor_vars.update(key);break
    graph=collections.defaultdict(list);edges=0
    for i,c in enumerate(clauses):
        if len(c)==2 and c[0]!=c[1]:
            a,b=c;graph[-a].append((b,i));graph[-b].append((a,i));edges+=2
    # Choose variables that actually touch binary edges, bounded by source count.
    degree=collections.Counter()
    for v,links in graph.items():
        if abs(v) in xor_vars:degree[abs(v)]+=len(links)
    candidates=[v for v,_ in degree.most_common(max_sources)]
    def prove(start,target):
        q=collections.deque([start]);prev={start:None}
        while q and len(prev)<max_visits:
            u=q.popleft()
            if u==target:
                chain=[];cur=u
                while prev[cur] is not None:
                    parent,idx=prev[cur];chain.append(idx);cur=parent
                chain.reverse()
                return chain,len(prev)
            for v,idx in graph.get(u,()):
                if v not in prev:
                    prev[v]=(u,idx);q.append(v)
        return None,len(prev)
    proofs=[];visits=0
    for v in candidates:
        for lit in (v,-v):
            chain,seen=prove(lit,-lit);visits+=seen
            if chain is None:continue
            # Independently verify every edge in proof path.
            current=lit
            for idx in chain:
                a,b=clauses[idx]
                if current==-a:current=b
                elif current==-b:current=a
                else:raise RuntimeError("Invalid path certificate")
            if current!=-lit:raise RuntimeError("Wrong path endpoint")
            proofs.append(dict(implied_unit=-lit,assumption=lit,
                               clause_indices_zero_based=chain,
                               path_length=len(chain)))
    return dict(file=path.name,declared_vars=n,declared_clauses=declared,
        scanned_clauses=len(clauses),truncated=truncated,
        xor_variables=len(xor_vars),binary_implication_edges=edges,
        tested_xor_boundary_variables=len(candidates),bfs_visited_total=visits,
        certified_binary_units=len(proofs),proofs=proofs[:32],
        proof_truncated=len(proofs)>32,elapsed_s=round(time.monotonic()-t,6),
        mode="shadow_only",solver_interventions=0,
        caveat="Certificates are implication paths from original binary clauses; no XOR/CDCL combination yet.")

def main():
    p=argparse.ArgumentParser();p.add_argument("--inputs",required=True);p.add_argument("--out",required=True)
    a=p.parse_args();root=pathlib.Path(a.inputs);cases=json.loads((root/"manifest.json").read_text())["cases"]
    if len(cases)!=14:raise RuntimeError("expected 14 original cases")
    rows=[]
    for c in cases:
        path=root/c["path"];h=hashlib.sha256(path.read_bytes()).hexdigest()
        if h!=c["raw_sha256"]:raise RuntimeError("CNF SHA drift")
        row=scan(path);row.update(case_id=c["id"],sha256=h)
        rows.append(row);print("R36_PROOF_SCAN",json.dumps({k:v for k,v in row.items() if k!="proofs"},sort_keys=True),flush=True)
    out=dict(protocol="R36_binary_path_certificates_v1",cases=14,rows=rows,
        total_certified_units=sum(r["certified_binary_units"] for r in rows),
        warning="No active SAT intervention or speedup measured; XOR-aware candidate selection only.")
    pathlib.Path(a.out).write_text(json.dumps(out,indent=2)+"\n")
    print("R36_AUDIT_PASS",len(rows),"verified original CNFs")
if __name__=="__main__":main()
