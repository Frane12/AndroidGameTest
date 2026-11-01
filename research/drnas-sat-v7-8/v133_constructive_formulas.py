#!/usr/bin/env python3
"""Deterministic SAT/UNSAT formulas with mathematical ground truth for V13.3.

Families (six instances each): planted 2-SAT, planted 3-SAT, colorable
3-coloring, pigeonhole UNSAT, and SAT/UNSAT cubic-prism Tseitin parity.
Generated BEFORE solver timing, with no accept/reject based on performance.
"""
import hashlib,random
FAMILIES=("planted_2sat","planted_3sat","colorable_3color",
          "pigeonhole_unsat","tseitin_sat","tseitin_unsat")
N_PER_FAMILY=6
SALT="DRNAS-V133-FROZEN-CONSTRUCTIVE-20261101-v1"

def rng_for(family,index):
    seed=int(hashlib.sha256(f"{SALT}/{family}/{index}".encode()).hexdigest(),16)
    return random.Random(seed)

def clauses_to_bytes(n,clauses):
    lines=[f"p cnf {n} {len(clauses)}"]
    lines.extend(" ".join(map(str,c))+" 0" for c in clauses)
    return ("\n".join(lines)+"\n").encode("ascii")

def valid_assignment(clauses,witness):
    return all(any(witness[abs(l)]==(l>0) for l in c) for c in clauses)

def planted(k,i,r):
    n=(80+24*i) if k==2 else (64+24*i)
    ratio=(2.0+0.3*i) if k==2 else (3.2+0.32*i)
    witness={j:bool(r.getrandbits(1)) for j in range(1,n+1)}
    cs=[];seen=set()
    while len(cs)<round(n*ratio):
        vs=r.sample(range(1,n+1),k)
        ls=[v if r.getrandbits(1) else -v for v in vs]
        if not any(witness[abs(l)]==(l>0) for l in ls):
            j=r.randrange(k);v=vs[j];ls[j]=v if witness[v] else -v
        c=tuple(sorted(ls,key=lambda x:abs(x)))
        if c not in seen:seen.add(c);cs.append(c)
    return n,cs,witness,{"type":"planted_witness"}

def colorable(i,r):
    vcount=21+5*i;n=3*vcount
    palette=[r.randrange(3) for _ in range(vcount)]
    witness={3*v+c+1:(palette[v]==c) for v in range(vcount) for c in range(3)}
    cs=[]
    for v in range(vcount):
        lits=[3*v+c+1 for c in range(3)]
        cs.append(tuple(lits))
        for x in range(3):
            for y in range(x+1,3):cs.append((-lits[x],-lits[y]))
    e=0
    for v in range(vcount):
        for w in range(v+1,vcount):
            if palette[v]!=palette[w] and r.random()<(0.25+0.025*i):
                e+=1
                for c in range(3):cs.append((-3*v-c-1,-3*w-c-1))
    return n,cs,witness,{"type":"constructive_3color","vertices":vcount,"edges":e}

def pigeonhole(i):
    holes=3+i;pigeons=holes+1
    var=lambda p,h:1+p*holes+h
    cs=[]
    for p in range(pigeons):
        cs.append(tuple(var(p,h) for h in range(holes)))
        for h in range(holes):
            for h2 in range(h+1,holes):cs.append((-var(p,h),-var(p,h2)))
    for h in range(holes):
        for p in range(pigeons):
            for p2 in range(p+1,pigeons):cs.append((-var(p,h),-var(p2,h)))
    return holes*pigeons,cs,None,{"type":"pigeonhole","pigeons":pigeons,"holes":holes}

def prism(i,r,unsat):
    m=3+i;vertices=2*m
    edges=[]
    for j in range(m):
        edges.append((j,(j+1)%m))
        edges.append((m+j,m+(j+1)%m))
        edges.append((j,m+j))
    incident=[[] for _ in range(vertices)]
    for ei,(u,v) in enumerate(edges):
        incident[u].append(ei+1);incident[v].append(ei+1)
    assert all(len(x)==3 for x in incident)
    assignment={ei+1:bool(r.getrandbits(1)) for ei in range(len(edges))}
    parity=[sum(assignment[x] for x in inc)%2 for inc in incident]
    assert sum(parity)%2==0
    if unsat:parity[0]^=1
    cs=[]
    for inc,rhs in zip(incident,parity):
        for bits in range(8):
            vals=[bool((bits>>b)&1) for b in range(3)]
            if sum(vals)%2==rhs:continue
            cs.append(tuple((-v if value else v) for v,value in zip(inc,vals)))
    proof={"type":"tseitin_parity","vertices":vertices,
           "sum_vertex_rhs_mod2":sum(parity)%2,
           "every_edge_incidence":2}
    return len(edges),cs,None if unsat else assignment,proof

def make(family,i):
    assert family in FAMILIES and 0<=i<N_PER_FAMILY
    r=rng_for(family,i)
    if family=="planted_2sat":n,cs,w,p=planted(2,i,r)
    elif family=="planted_3sat":n,cs,w,p=planted(3,i,r)
    elif family=="colorable_3color":n,cs,w,p=colorable(i,r)
    elif family=="pigeonhole_unsat":n,cs,w,p=pigeonhole(i)
    else:n,cs,w,p=prism(i,r,unsat=(family=="tseitin_unsat"))
    label="UNSAT" if family in ("pigeonhole_unsat","tseitin_unsat") else "SAT"
    if label=="SAT":
        assert w is not None and len(w)==n and valid_assignment(cs,w)
    else:
        assert w is None
        if family=="pigeonhole_unsat":assert p["pigeons"]>p["holes"]
        else:assert p["sum_vertex_rhs_mod2"]==1
    b=clauses_to_bytes(n,cs)
    case_id=f"generated/{family}/{i}"
    return {"id":case_id,"source":"synthetic","family":family,"index":i,
            "official_label":label,"sha256":hashlib.sha256(b).hexdigest(),
            "variables":n,"clauses":len(cs),"proof":p},b

def selftest():
    cases=[]
    for family in FAMILIES:
        for i in range(N_PER_FAMILY):
            row,payload=make(family,i)
            assert (row,payload)==make(family,i)
            assert payload.startswith(b"p cnf ")
            cases.append(row)
    assert len(cases)==36 and len({x["sha256"] for x in cases})==36
    assert sum(x["official_label"]=="SAT" for x in cases)==24
    assert sum(x["official_label"]=="UNSAT" for x in cases)==12
    print("V133_GENERATOR_SELFTEST_PASS",len(cases),flush=True)
if __name__=="__main__":selftest()
