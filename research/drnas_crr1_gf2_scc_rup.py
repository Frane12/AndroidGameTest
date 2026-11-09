#!/usr/bin/env python3
"""CRR1: GF(2) + binary implication SCC -> shared rows -> original-CNF RUP-certified lemmas."""
import collections, json, sys

def parse(path):
    clauses=[]; cur=[]; n=0; declared=None
    for line in open(path):
        s=line.strip()
        if not s or s.startswith('c') or s=='%': continue
        if s.startswith('p '):
            _,kind,ns,cs=s.split(); assert kind=='cnf'
            n=int(ns); declared=int(cs); continue
        for v in map(int,s.split()):
            if v==0: clauses.append(tuple(cur)); cur=[]
            else: assert 0<abs(v)<=n; cur.append(v)
    assert not cur and len(clauses)==declared
    return n,clauses

def rup(clauses,lemma):
    assignment={}; queue=[-x for x in lemma]
    while queue:
        lit=queue.pop(); v=abs(lit); val=lit>0
        if v in assignment:
            if assignment[v]!=val: return True
            continue
        assignment[v]=val
        changed=True
        while changed:
            changed=False
            for clause in clauses:
                if any(assignment.get(abs(x))==(x>0) for x in clause): continue
                free=[x for x in clause if abs(x) not in assignment]
                if not free: return True
                if len(free)==1:
                    x=free[0]; w=abs(x); b=x>0
                    if w in assignment:
                        if assignment[w]!=b: return True
                    else: assignment[w]=b; changed=True
    return False

def gf2_rows(clauses):
    groups=collections.defaultdict(set)
    for c in clauses:
        vs=tuple(sorted(set(map(abs,c))))
        if len(vs) not in (2,3) or len(vs)!=len(c): continue
        signs=tuple(next(x>0 for x in c if abs(x)==v) for v in vs)
        groups[vs].add(signs)
    rows=[]
    for vs,patterns in groups.items():
        if len(patterns)!=2**(len(vs)-1): continue
        parities={sum(not b for b in p)%2 for p in patterns}
        if len(parities)==1: rows.append((set(vs),1-next(iter(parities))))
    return rows

def scc_rows(clauses,n):
    g=collections.defaultdict(list); rev=collections.defaultdict(list)
    for c in clauses:
        if len(c)!=2 or abs(c[0])==abs(c[1]): continue
        a,b=c
        for u,v in ((-a,b),(-b,a)): g[u].append(v); rev[v].append(u)
    nodes=[v for i in range(1,n+1) for v in (i,-i)]
    seen=set(); order=[]
    for root in nodes:
        if root in seen: continue
        seen.add(root); stack=[(root,0)]
        while stack:
            v,j=stack[-1]
            if j<len(g[v]):
                w=g[v][j]; stack[-1]=(v,j+1)
                if w not in seen: seen.add(w); stack.append((w,0))
            else: order.append(v); stack.pop()
    comp={}; groups=collections.defaultdict(list); index=0
    for root in reversed(order):
        if root in comp: continue
        stack=[root]; comp[root]=index
        while stack:
            for w in rev[stack.pop()]:
                if w not in comp: comp[w]=index; stack.append(w)
        index+=1
    for v in nodes: groups[comp[v]].append(v)
    rows=[]
    for group in groups.values():
        a=min(group,key=lambda x:(abs(x),x<0))
        for b in group:
            if abs(a)!=abs(b):
                rows.append(({abs(a),abs(b)},int((a<0)!=(b<0))))
    return rows

def eliminate(rows):
    pivots={}
    for vs,rhs in rows:
        bits=set(vs); b=rhs
        while bits:
            p=min(bits)
            if p not in pivots: pivots[p]=(bits,b); break
            old,ob=pivots[p]; bits.symmetric_difference_update(old); b^=ob
    for p in sorted(pivots,reverse=True):
        bits,b=pivots[p]
        for q in [q for q in pivots if q<p]:
            qb,qv=pivots[q]
            if p in qb: pivots[q]=(qb^bits,qv^b)
    return list(pivots.values())

def candidate_clauses(rows):
    out=set()
    for vs,rhs in rows:
        if len(vs)==1:
            v=next(iter(vs)); out.add((v if rhs else -v,))
        elif len(vs)==2:
            a,b=sorted(vs)
            out.update(((-a,b),(a,-b)) if rhs==0 else ((a,b),(-a,-b)))
    return sorted(out,key=lambda c:(len(c),c))

def run(source,destination,report):
    n,original=parse(source)
    xor=gf2_rows(original); scc=scc_rows(original,n)
    rows=eliminate(xor+scc)
    proposed=candidate_clauses(rows)
    accepted=[]; seen={tuple(sorted(c)) for c in original}
    for c in proposed[:256]:
        key=tuple(sorted(c))
        if key not in seen and rup(original+accepted,c):
            accepted.append(c); seen.add(key)
    with open(destination,'w') as f:
        f.write(f'p cnf {n} {len(original)+len(accepted)}\n')
        for c in original+accepted: f.write(' '.join(map(str,c))+' 0\n')
    data=dict(original_clauses=len(original),xor_rows=len(xor),scc_rows=len(scc),
              combined_rows=len(rows),proposed=len(proposed),rup_lemmas=len(accepted),
              units=sum(len(c)==1 for c in accepted),binary=sum(len(c)==2 for c in accepted),
              unsat_claimed=False,proof='original-CNF RUP')
    with open(report,'w') as f: json.dump(data,f,indent=2)
    print('CRR1_RESULT',json.dumps(data,sort_keys=True))

def selftest():
    import tempfile,os
    with tempfile.TemporaryDirectory() as d:
        tests=[(3,[(1,-2),(-1,2),(2,-3),(-2,3)]),
               (3,[(1,2),(-1,-2),(2,3),(-2,-3)]),
               (2,[(1,),(2,),(-1,-2)])]
        for n,cs in tests:
            src=os.path.join(d,'in.cnf');dst=os.path.join(d,'out.cnf');rep=os.path.join(d,'report.json')
            with open(src,'w') as f:
                f.write(f'p cnf {n} {len(cs)}\n')
                for c in cs:f.write(' '.join(map(str,c))+' 0\n')
            run(src,dst,rep)
            _,out=parse(dst)
            assert all(rup(cs,c) for c in out[len(cs):])
    print('CRR1_SELFTEST_PASS')

if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='selftest': selftest()
    elif len(sys.argv)==5 and sys.argv[1]=='run': run(*sys.argv[2:])
    else: raise SystemExit('usage: crr1.py selftest | run original.cnf output.cnf report.json')
