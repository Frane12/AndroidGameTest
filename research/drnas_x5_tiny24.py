#!/usr/bin/env python3
"""Outcome-blind small-source generator. Frozen solvers and proof policy unchanged."""
import hashlib,itertools,random
import drnas_x5_bench as Bench

def make_small(family,index):
    rng=random.Random(int.from_bytes(hashlib.sha256(f'X5-TINY24|{family}|{index}|v1'.encode()).digest()[:8],'big'))
    slot=index%4;n=24+8*slot;cs=[]
    target=[False]+[bool(rng.randrange(2)) for _ in range(n)]
    cert='SAT_CONSTRUCTED_CHECK_WITNESS'
    def planted(vs):
        c=[v*rng.choice((-1,1)) for v in vs]
        if not any(target[abs(l)]==(l>0) for l in c):c[rng.randrange(len(c))]*=-1
        return c
    if family in ('critical3_planted','critical4_planted'):
        k=3 if family=='critical3_planted' else 4
        if k==4:
            n=16+4*slot;target=target[:n+1]
        for _ in range(round(n*(3.6 if k==3 else 7.0))):cs.append(planted(rng.sample(range(1,n+1),k)))
    elif family=='xor_planted':
        for _ in range(n):
            vs=rng.sample(range(1,n+1),3);rhs=sum(target[v] for v in vs)%2
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=rhs:cs.append([-v if b else v for v,b in zip(vs,bits)])
        for _ in range(n):cs.append(planted(rng.sample(range(1,n+1),3)))
    elif family=='graph_coloring_sat':
        nodes=8+2*slot;n=nodes*3;colors=[rng.randrange(3) for _ in range(nodes)]
        var=lambda v,c:3*v+c+1
        for v in range(nodes):
            lits=[var(v,c) for c in range(3)];cs.append(lits)
            cs.extend([[-x,-y] for x,y in itertools.combinations(lits,2)])
        for v,w in itertools.combinations(range(nodes),2):
            if colors[v]!=colors[w] and rng.random()<.4:
                cs.extend([[-var(v,c),-var(w,c)] for c in range(3)])
        target=[False]+[colors[(v-1)//3]==(v-1)%3 for v in range(1,n+1)]
    elif family=='modular3_planted':
        for start in range(1,n+1,6):
            vs=list(range(start,min(n+1,start+6)))
            if len(vs)>=3:
                for _ in range(4*len(vs)):cs.append(planted(rng.sample(vs,3)))
        for _ in range(n//2):cs.append(planted(rng.sample(range(1,n+1),3)))
    elif family=='php_structural_unsat':
        holes=min(5,3+slot);pigeons=holes+1;core=holes*pigeons;n=core+6+slot
        var=lambda p,h:p*holes+h+1
        for p in range(pigeons):cs.append([var(p,h) for h in range(holes)])
        for h in range(holes):
            for p,q in itertools.combinations(range(pigeons),2):cs.append([-var(p,h),-var(q,h)])
        target=[False]+[bool(rng.randrange(2)) for _ in range(n)]
        for _ in range(20):cs.append(planted(rng.sample(range(core+1,n+1),3)))
        cert='PHP_STRUCTURAL_CORE';target=None
    else:raise ValueError(family)
    cs=sorted(set(tuple(sorted(c,key=lambda z:(abs(z),z<0))) for c in cs))
    if target is not None:assert all(any(target[abs(l)]==(l>0) for l in c) for c in cs)
    content=f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)
    return {'kind':'synthetic_tiny','family':family,'source_id':index,'nvars':n,'nclauses':len(cs),'cert':cert,'clauses':cs,'content':content,'sha256':hashlib.sha256(content.encode()).hexdigest(),'filename':f'tiny_{family}_{index}.cnf'}

if __name__=='__main__':
    Bench.B.make_synthetic=make_small
    Bench.main()
