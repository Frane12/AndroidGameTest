"""Positive equality quotient using certificates in the ORIGINAL CNF only."""
import itertools, random

def quotient(original, source_rows=()):
    binary={frozenset(c) for c in original if len(c)==2}
    pairs=set()
    for c in binary:
        if len(c)!=2: continue
        x,y=tuple(c)
        if x*y<0 and abs(x)!=abs(y) and frozenset((-x,-y)) in binary:
            pairs.add(tuple(sorted((abs(x),abs(y)))))
    parent={}
    def find(v):
        parent.setdefault(v,v)
        while parent[v]!=v:
            parent[v]=parent[parent[v]]; v=parent[v]
        return v
    for a,b in sorted(pairs):
        # Replay each edge against original input, never against rewritten CNF.
        assert frozenset((-a,b)) in binary and frozenset((a,-b)) in binary
        a,b=find(a),find(b)
        if a!=b: parent[max(a,b)]=min(a,b)
    mapping={v:find(v) for v in list(parent) if find(v)!=v}
    if not mapping:
        return list(original),list(source_rows),{},dict(pairs=0,merges=0,classes=0,replaced_occurrences=0)
    cnf=[]; seen=set(); replaced=0; taut=0; duplicates=0
    def add(c):
        nonlocal taut,duplicates
        key=frozenset(c)
        if any(-l in key for l in key): taut+=1; return
        if key in seen: duplicates+=1; return
        seen.add(key); cnf.append(tuple(dict.fromkeys(c)))
    for c in original:
        mapped=[(1 if l>0 else -1)*mapping.get(abs(l),abs(l)) for l in c]
        replaced+=sum(a!=b for a,b in zip(c,mapped)); add(mapped)
    rows=[]; rowseen=set(); units=0; constants=0
    for vs,rhs in source_rows:
        assert rhs in (0,1)
        parity=set()
        for v in vs:
            assert v>0
            w=mapping.get(v,v)
            if w in parity: parity.remove(w)
            else: parity.add(w)
        if not parity:
            constants+=1
            if rhs: add(())  # Certified contradiction, preserve as empty CNF clause.
        elif len(parity)==1:
            v=next(iter(parity)); add((v if rhs else -v,)); units+=1
        else:
            row=(tuple(sorted(parity)),rhs)
            if row not in rowseen: rows.append(row); rowseen.add(row)
    assert all(abs(l) not in mapping for c in cnf for l in c)
    assert all(v not in mapping for vs,_ in rows for v in vs)
    return cnf,rows,mapping,dict(pairs=len(pairs),merges=len(mapping),classes=len(set(mapping.values())),replaced_occurrences=replaced,removed_tautologies=taut,removed_duplicates=duplicates,xor_units=units,xor_constants=constants)

def reconstruct(model,mapping):
    out=dict(model)
    for v,root in mapping.items():
        if root not in out or not isinstance(out[root],bool):
            raise RuntimeError('missing representative in model')
        out[v]=out[root]
    return out

def selftest():
    def sat(cnf,m): return all(any(m[abs(l)]==(l>0) for l in c) for c in cnf)
    rng=random.Random(629041)
    checks=0
    for i in range(120):
        n=5
        cnf=[tuple(rng.choice((-1,1))*rng.randint(1,n) for _ in range(rng.randint(0,4))) for j in range(8)]
        for a,b in [(1,2),(2,3),(1,3),(4,5)][:i%5]: cnf.extend([(-a,b),(a,-b)])
        rows=[((1,2,3),i%2),((1,2),i%2),((2,4,5),1)]
        reduced,xors,mapping,_=quotient(cnf,rows)
        for bits in itertools.product((False,True),repeat=n):
            m=dict(enumerate(bits,1)); lifted=reconstruct(m,mapping)
            lhs=sat(cnf,lifted) and all(sum(lifted[v] for v in vs)%2==rhs for vs,rhs in rows)
            rhs=sat(reduced,m) and all(sum(m[v] for v in vs)%2==rhs for vs,rhs in xors)
            assert lhs==rhs,(i,m)
            if sat(cnf,m): assert all(m[v]==m[root] for v,root in mapping.items())
            checks+=1
    assert quotient([(-1,2)])[2]=={}
    c,r,m,st=quotient([(-1,2),(1,-2),(-2,3),(2,-3)])
    assert m=={2:1,3:1} and st['merges']==2 and c==[]
    print('MRE6D_EXHAUSTIVE_SELFTEST_PASS',checks,flush=True)
if __name__=='__main__': selftest()
