#!/usr/bin/env python3
"""Independent source-only clique-vs-coloring CNF schema. Fail closed."""
from collections import Counter
from pathlib import Path
import hashlib,sys,json

class Unsupported(ValueError):pass

def need(condition,why):
    if not condition:raise Unsupported(why)

def recover(raw):
    need(len(raw)<=30_000_000,"source bytes budget")
    nv=nc=None;pending=[];clauses=[]
    for line in raw.decode("ascii").splitlines():
        fields=line.split()
        if not fields or fields[0]=="c":continue
        if fields[0]=="p":
            need(nv is None and len(fields)==4 and fields[1]=="cnf","bad header")
            nv,nc=int(fields[2]),int(fields[3])
            need(0<nv<=200000 and 0<nc<=400000,"bounded header")
            continue
        need(nv is not None,"missing header")
        for v in map(int,fields):
            need(abs(v)<=nv,"source literal out of range")
            if v:pending.append(v)
            else:
                need(len(set(pending))==len(pending),"duplicate original literal")
                clauses.append(tuple(pending));pending=[]
    need(nv is not None and not pending and len(clauses)==nc,"clause count")
    original=set(map(frozenset,clauses))
    positive=[tuple(sorted(r)) for r in clauses if len(r)>1 and all(v>0 for v in r)]
    widths=Counter(map(len,positive))
    need(len(widths)==2,"not clique-coloring source")
    c,n=sorted(widths)
    k=widths[n]
    need(2<=c<k<=n and k==c+1 and widths[c]==n,"unsupported dimensions")
    need(n<=150 and k<=16 and c<=16,"source parameter budget")
    P=sorted((g for g in positive if len(g)==n),key=min)
    C=sorted((g for g in positive if len(g)==c),key=min)
    need(len(P)==k and len(C)==n,"positive groups")
    owners=set()
    for row in P+C:
        for v in row:
            need(v not in owners,"overlapping original selection groups")
            owners.add(v)
    edge_vars=set(range(1,nv+1))-owners
    need(len(edge_vars)==n*(n-1)//2,"edge vars count")
    color_by_var={-v:(u,z) for u,row in enumerate(C) for z,v in enumerate(row)}
    edges={}
    for row in clauses:
        if len(row)!=3 or any(v>=0 for v in row):continue
        colors=[color_by_var[v] for v in row if v in color_by_var]
        ev=[-v for v in row if -v in edge_vars]
        if len(colors)!=2 or len(ev)!=1:continue
        (u,z),(v,w)=colors
        if u!=v and z==w==0:
            pair=tuple(sorted((u,v)))
            need(pair not in edges or edges[pair]==ev[0],"ambiguous edge")
            edges[pair]=ev[0]
    need(len(edges)==n*(n-1)//2 and len(set(edges.values()))==len(edges),"edge mapping")
    for (u,v),e in edges.items():
        for z in range(c):
            need(frozenset((-e,-C[u][z],-C[v][z])) in original,"missing color conflict")
    for i in range(k):
        need(frozenset(P[i]) in original,"missing clique position ALO")
        for j in range(i+1,k):
            for u in range(n):
                need(frozenset((-P[i][u],-P[j][u])) in original,"missing injectivity")
                for v in range(n):
                    if u!=v:
                        e=edges[tuple(sorted((u,v)))]
                        need(frozenset((-P[i][u],-P[j][v],e)) in original,
                             "missing source clique-edge rule")
    for u in range(n):
        need(frozenset(C[u]) in original,"missing vertex color ALO")
    return {"nv":nv,"clauses":clauses,"P":P,"C":C,"edges":edges,
            "n":n,"k":k,"c":c,"sha256":hashlib.sha256(raw).hexdigest()}

if __name__=="__main__":
    for a in sys.argv[1:]:
        try:
            s=recover(Path(a).read_bytes())
            print("CLIQUE_COLOR_SOURCE_OK "+json.dumps(
                {z:s[z] for z in ("sha256","n","k","c")},sort_keys=True))
        except (ValueError,UnicodeError,TypeError) as e:
            print("CLIQUE_COLOR_SOURCE_UNKNOWN "+str(e))
            raise SystemExit(2)
