#!/usr/bin/env python3
"""V13.7 independent-seed stress set: 40 fresh CNFs across five known classes.

New seeds and sizes, arbitrary variable renumbering, shuffled clauses and
occasional polarity flips. Not representative of arbitrary SAT.
SAT models checked after transformation; UNSAT labels from standard math.
"""
import hashlib,random
import v136_symbolic as old
import v134_constructive as base

SALT="DRNAS-V137-NEWSEED-PERMUTED-40-20261101-v1"
FAMILIES=old.FAMILIES
SIZES={
 "planted3_sat":(110,145,180,215,250,285,320,355),
 "color3_sat":(52,70,88,106,124,142,160,178),
 "pigeonhole_unsat":(7,9,11,13,15,17,19,21),
 "cubic_xor_sat":(38,50,62,74,86,98,110,122),
 "cubic_xor_unsat":(42,54,66,78,90,102,114,126)
}
def rng(f,i):
    return random.Random(int(hashlib.sha256((SALT+"/"+f+"/"+str(i)).encode()).hexdigest(),16))
def fresh(f,i):
    if f not in FAMILIES or not 0<=i<8:raise ValueError("Unknown case")
    r=rng(f,i);size=SIZES[f][i]
    if f=="planted3_sat":
        n=size;density=(3.65,3.85,4.05,4.18,4.30,4.42,4.55,4.70)[i]
        w={v:bool(r.getrandbits(1)) for v in range(1,n+1)}
        seen=set();clauses=[]
        while len(clauses)<round(n*density):
            vs=r.sample(range(1,n+1),3)
            ls=[v if r.getrandbits(1) else -v for v in vs]
            if not any(w[abs(l)]==(l>0) for l in ls):
                j=r.randrange(3);ls[j]=vs[j] if w[vs[j]] else -vs[j]
            t=tuple(sorted(ls,key=abs))
            if t not in seen:clauses.append(t);seen.add(t)
        label="SAT";cert={"type":"planted_witness","density":density}
    elif f=="color3_sat":
        vertices=size;n=vertices*3
        colors=[r.randrange(3) for _ in range(vertices)]
        w={3*v+c+1:colors[v]==c for v in range(vertices) for c in range(3)}
        clauses=[]
        for v in range(vertices):
            b=3*v+1;clauses.append((b,b+1,b+2))
            for c in range(3):
                for d in range(c+1,3):clauses.append((-b-c,-b-d))
        target=4.0+0.35*i
        edges=0
        for u in range(vertices):
            for v in range(u+1,vertices):
                if colors[u]!=colors[v] and r.random()<1.5*target/vertices:
                    edges+=1
                    for c in range(3):clauses.append((-(3*u+c+1),-(3*v+c+1)))
        label="SAT";cert={"type":"3color_witness","edges":edges}
    elif f=="pigeonhole_unsat":
        holes=size;birds=holes+1;n=holes*birds
        var=lambda p,h:1+p*holes+h
        clauses=[tuple(var(p,h) for h in range(holes)) for p in range(birds)]
        for h in range(holes):
            for p in range(birds):
                for q in range(p+1,birds):clauses.append((-var(p,h),-var(q,h)))
        label="UNSAT";w=None;cert={"type":"pigeonhole","birds":birds,"holes":holes}
    else:
        vertices=size;edges=base.graph(vertices,r);n=len(edges)
        inc=[[] for _ in range(vertices)]
        for edge,(u,v) in enumerate(edges,1):inc[u].append(edge);inc[v].append(edge)
        w={edge:bool(r.getrandbits(1)) for edge in range(1,n+1)}
        rhs=[sum(w[e] for e in adjacent)%2 for adjacent in inc]
        if f=="cubic_xor_unsat":rhs[0]^=1
        clauses=[]
        for adjacent,bit in zip(inc,rhs):
            for mask in range(8):
                v=[bool(mask>>k&1) for k in range(3)]
                if sum(v)%2!=bit:
                    clauses.append(tuple(-e if value else e for e,value in zip(adjacent,v)))
        label="UNSAT" if f.endswith("unsat") else "SAT"
        cert={"type":"odd_global_parity" if label=="UNSAT" else "xor_witness",
              "global_rhs_mod2":sum(rhs)%2}
        if label=="UNSAT":w=None
    # Uniform variable relabeling preserves the propositional language.
    permutation=list(range(1,n+1));r.shuffle(permutation)
    rename={v:permutation[v-1] for v in range(1,n+1)}
    # PHP proof detector is canonical-positive; leave its polarity unchanged.
    flip={v for v in range(1,n+1) if r.getrandbits(1)} if f!="pigeonhole_unsat" else set()
    changed=[]
    for clause in clauses:
        row=[]
        for lit in clause:
            v=abs(lit);sign=(lit>0) != (v in flip)
            row.append(rename[v] if sign else -rename[v])
        r.shuffle(row)
        changed.append(tuple(row))
    r.shuffle(changed)
    if label=="SAT":
        model={rename[v]: (not bit if v in flip else bit) for v,bit in w.items()}
        assert len(model)==n and base.valid(changed,model)
    elif f=="cubic_xor_unsat":
        assert cert["global_rhs_mod2"]==1
    else:assert cert["birds"]==cert["holes"]+1
    raw=base.dimacs(n,changed)
    info={"id":f"generated/v137/{f}/{i}","family":f,"index":i,"sha256":hashlib.sha256(raw).hexdigest(),
          "label":label,"source":"synthetic_permuted","variables":n,
          "clauses":len(changed),"certificate":cert}
    return info,raw

def selftest():
    import v137_fastpath as solver
    seen=set();paths={}
    for family in FAMILIES:
        for i in range(8):
            meta,raw=fresh(family,i)
            assert fresh(family,i)==(meta,raw)
            assert meta["sha256"] not in seen;seen.add(meta["sha256"])
            solved=solver.decide(raw)
            if family in ("cubic_xor_sat","cubic_xor_unsat"):
                assert solved["path"]=="affine_exact",(family,i,solved.get("path"))
            elif family=="pigeonhole_unsat":
                assert solved["path"]=="pigeonhole_exact",(family,i,solved.get("path"))
            else:assert solved["status"]=="FALLBACK",(family,i,solved)
            if solved["status"]!="FALLBACK":
                assert solved["status"]==meta["label"]
            paths[solved["path"]]=paths.get(solved["path"],0)+1
    assert len(seen)==40
    print("V137_GENERATOR_SELFTEST_PASS",len(seen),paths,flush=True)
if __name__=="__main__":selftest()
