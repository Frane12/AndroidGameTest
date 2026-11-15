#!/usr/bin/env python3
"""Hall/PHP structural certificate to standard DRAT using Extended Resolution.

The source CNF, not the claimed UNSAT status, determines every accepted row,
column and at-most-one edge. RAT introduces fresh y_ij equivalent to
(x_ij OR (x_i,last_hole AND x_last_pigeon,j)). RUP then reduces
PHP(h+1,h) to PHP(h,h-1), ending at the empty clause.
An independent standard DRAT checker is mandatory before acceptance.
"""
import argparse, hashlib, json, time
from pathlib import Path

def read_cnf(path):
    nvars=nclauses=None;clauses=[];pending=[]
    for raw in path.read_text(encoding="ascii").splitlines():
        s=raw.strip()
        if not s or s[0] in "c%":continue
        if s.startswith("p "):
            if nvars is not None:raise ValueError("duplicate CNF header")
            _,fmt,n,m=s.split()
            if fmt!="cnf":raise ValueError("not CNF")
            nvars,nclauses=int(n),int(m);continue
        if nvars is None:raise ValueError("missing DIMACS header")
        for tok in s.split():
            v=int(tok)
            if v==0:clauses.append(tuple(pending));pending.clear()
            elif abs(v)>nvars:raise ValueError("literal out of range")
            else:pending.append(v)
    if pending or len(clauses)!=nclauses:raise ValueError("bad DIMACS count")
    return nvars,clauses

def source_matrix(cnf,certificate):
    n,clauses=read_cnf(cnf)
    if hashlib.sha256(cnf.read_bytes()).hexdigest()!=certificate["source_sha256"]:
        raise ValueError("source SHA mismatch")
    if certificate["format"]!="pcmax-clause-hall-v1":
        raise ValueError("unsupported certificate format")
    rows=certificate["alo_groups"];cols=certificate["resource_cliques"]
    if len(rows)!=certificate["required_groups"] or len(cols)!=certificate["resource_bound"]:
        raise ValueError("certificate dimensions mismatch")
    h=len(cols)
    if h<1 or len(rows)<=h:raise ValueError("not a strict Hall deficiency")
    rows=rows[:h+1];p=len(rows)
    source={frozenset(c) for c in clauses};matrix=[]
    for i,row in enumerate(rows):
        if len(row)!=h or len(set(row))!=h or not all(0<x<=n for x in row):
            raise ValueError("nonrectangular or invalid ALO")
        if frozenset(row) not in source:
            raise ValueError("source ALO clause missing")
        matrix.append([])
        for j,col in enumerate(cols):
            hits=set(row).intersection(col)
            if len(hits)!=1:raise ValueError("row/column intersection not unique")
            matrix[-1].append(next(iter(hits)))
    if len({x for r in matrix for x in r})!=p*h:
        raise ValueError("repeated source variable")
    for j in range(h):
        for i in range(p):
            for k in range(i+1,p):
                if frozenset((-matrix[i][j],-matrix[k][j])) not in source:
                    raise ValueError("missing source resource at-most-one")
    return n,matrix

def generate(cnf,certificate,output):
    n,matrix=source_matrix(cnf,certificate);nextvar=n
    steps=rat=rup=0;t0=time.perf_counter()
    with output.open("w",encoding="ascii") as out:
        def add(c,kind):
            nonlocal steps,rat,rup
            out.write((" ".join(map(str,c))+" 0\n") if c else "0\n")
            steps+=1
            if kind=="RAT":rat+=1
            else:rup+=1
        while len(matrix[0])>1:
            h=len(matrix[0]);p=len(matrix)
            if p!=h+1:raise ValueError("PHP induction invariant")
            last=matrix[-1];reduced=[]
            for i in range(p-1):
                newrow=[]
                for j in range(h-1):
                    nextvar+=1;y=nextvar
                    a=matrix[i][j];b=matrix[i][h-1];c=last[j]
                    add([y,-a],"RAT")
                    add([y,-b,-c],"RAT")
                    add([-y,a,b],"RAT")
                    add([-y,a,c],"RAT")
                    newrow.append(y)
                reduced.append(newrow)
            for r in reduced:add(r,"RUP")
            for j in range(h-1):
                for i in range(p-1):
                    for k in range(i+1,p-1):
                        y1=reduced[i][j];y2=reduced[k][j]
                        add([-y1,-matrix[k][j]],"RUP")
                        add([-y1,-matrix[k][h-1],-last[j]],"RUP")
                        add([-y1,-y2],"RUP")
            matrix=reduced
        add([],"RUP")
    return dict(steps=steps,rat_steps=rat,rup_steps=rup,
                auxiliary_variables=nextvar-n,proof_bytes=output.stat().st_size,
                generation_s=round(time.perf_counter()-t0,6))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cnf",type=Path)
    ap.add_argument("certificate",type=Path)
    ap.add_argument("drat",type=Path)
    args=ap.parse_args()
    print(json.dumps(generate(args.cnf,json.loads(args.certificate.read_text()),args.drat),
                     sort_keys=True))
