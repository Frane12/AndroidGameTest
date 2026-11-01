#!/usr/bin/env python3
"""V13.6 finite-family structural holdout and label-blind symbolic selector.

Recognizes two mathematically defined *subclasses*, not general SAT:
  1. the complete pigeonhole contradiction encoded by positive pigeon
     clauses and negative pairwise capacity clauses;
  2. 3-XOR equations with a global odd parity contradiction in a
     degree-two incidence graph.
These standard structures are not new mathematical discoveries.
No solver runtime or SAT/UNSAT label is read during route selection.
"""
import collections,hashlib,itertools,random
import v134_constructive as old
SALT="DRNAS-V136-NEW-SEED-EIGHT-SIZES-LOCKED-20261101"
FAMILIES=("planted3_sat","color3_sat","pigeonhole_unsat","cubic_xor_sat","cubic_xor_unsat")
SIZES={
 "planted3_sat":(100,130,160,190,220,250,280,310),
 "color3_sat":(50,65,80,95,110,125,140,155),
 "pigeonhole_unsat":(7,9,11,13,15,17,19,21),
 "cubic_xor_sat":(34,38,46,58,70,82,94,106),
 "cubic_xor_unsat":(34,38,46,58,70,82,94,106)
}
def rng(f,i):
    s=hashlib.sha256((SALT+"/"+f+"/"+str(i)).encode()).hexdigest()
    return random.Random(int(s,16))
def make(f,i):
    assert f in FAMILIES and 0<=i<8
    r=rng(f,i);size=SIZES[f][i]
    if f=="planted3_sat":
        n=size;ratio=(3.6,3.82,4.04,4.22,4.35,4.48,4.60,4.72)[i]
        w={v:bool(r.getrandbits(1)) for v in range(1,n+1)}
        cs=[];seen=set()
        while len(cs)<round(n*ratio):
            vs=r.sample(range(1,n+1),3)
            ls=[v if r.getrandbits(1) else -v for v in vs]
            if not any(w[abs(l)]==(l>0) for l in ls):
                k=r.randrange(3);ls[k]=vs[k] if w[vs[k]] else -vs[k]
            t=tuple(sorted(ls,key=abs))
            if t not in seen:seen.add(t);cs.append(t)
        label="SAT";cert={"kind":"witness","ratio":ratio}
    elif f=="color3_sat":
        vcount=size;n=3*vcount
        palette=[r.randrange(3) for _ in range(vcount)]
        w={3*v+c+1:(palette[v]==c) for v in range(vcount) for c in range(3)}
        cs=[]
        for v in range(vcount):
            b=3*v+1;cs.append((b,b+1,b+2))
            for c in range(3):
                for d in range(c+1,3):cs.append((-b-c,-b-d))
        target=(3.9,4.1,4.45,4.8,5.1,5.5,5.9,6.2)[i]
        edges=0
        for u in range(vcount):
            for v in range(u+1,vcount):
                if palette[u]!=palette[v] and r.random()<1.5*target/vcount:
                    edges+=1
                    for c in range(3):cs.append((-(3*u+c+1),-(3*v+c+1)))
        label="SAT";cert={"kind":"3coloring","edges":edges}
    elif f=="pigeonhole_unsat":
        h=size;b=h+1;n=h*b
        var=lambda p,j:1+p*h+j
        cs=[tuple(var(p,j) for j in range(h)) for p in range(b)]
        for j in range(h):
            for p in range(b):
                for q in range(p+1,b):cs.append((-var(p,j),-var(q,j)))
        label="UNSAT";cert={"kind":"pigeonhole","pigeons":b,"holes":h};w=None
    else:
        vertices=size;edges=old.graph(vertices,r);n=len(edges)
        inc=[[] for _ in range(vertices)]
        for e,(u,v) in enumerate(edges,1):inc[u].append(e);inc[v].append(e)
        w={e:bool(r.getrandbits(1)) for e in range(1,n+1)}
        rhs=[sum(w[e] for e in adj)%2 for adj in inc]
        unsat=f.endswith("unsat")
        if unsat:rhs[0]^=1
        cs=[]
        for adj,bit in zip(inc,rhs):
            assert len(adj)==3
            for mask in range(8):
                vals=[bool(mask>>j&1) for j in range(3)]
                if sum(vals)%2!=bit:cs.append(tuple(-e if val else e for e,val in zip(adj,vals)))
        label="UNSAT" if unsat else "SAT"
        cert={"kind":"odd_parity" if unsat else "witness","global_rhs_mod2":sum(rhs)%2}
        if unsat:w=None
    if label=="SAT":assert old.valid(cs,w)
    elif f=="cubic_xor_unsat":assert cert["global_rhs_mod2"]==1
    else:assert cert["pigeons"]==cert["holes"]+1
    payload=old.dimacs(n,cs)
    info={"id":f"generated/v136/{f}/{i}","family":f,"index":i,"source":"synthetic",
          "sha256":hashlib.sha256(payload).hexdigest(),"label":label,
          "variables":n,"clauses":len(cs),"certificate":cert}
    return info,payload

def classify(payload):
    """Return chosen solver and structural reason; ONLY consumes DIMACS bytes."""
    lines=payload.splitlines()
    header=lines[0].split();assert header[:2]==[b"p",b"cnf"]
    n=int(header[2]);m=int(header[3])
    cs=[]
    for raw in lines[1:]:
        c=tuple(int(x) for x in raw.split())
        if c:assert c[-1]==0;cs.append(c[:-1])
    assert len(cs)==m and m>0
    # Complete at-least-one / at-most-one pigeonhole graph recognition.
    pos=[c for c in cs if len(c)>=5 and all(x>0 for x in c)]
    neg=[c for c in cs if len(c)==2 and all(x<0 for x in c)]
    if pos and len(pos)+len(neg)==len(cs):
        birds=len(pos);holes=len(pos[0])
        if birds==holes+1 and all(len(c)==holes for c in pos):
            lookup={}
            for bird,c in enumerate(pos):
                for var in c:
                    if var in lookup:break
                    lookup[var]=bird
            allvars=set(lookup)
            edges=set()
            for c in neg:
                a,b=abs(c[0]),abs(c[1])
                if a!=b and a in allvars and b in allvars and lookup[a]!=lookup[b]:
                    edges.add(tuple(sorted((a,b))))
            # Verify every capacity-edge is present, exactly h cliques
            # with exactly one variable from each pigeon per clique.
            if (len(lookup)==n==birds*holes and len(edges)==holes*birds*(birds-1)//2
                and len(neg)==len(edges)):
                adj={v:set() for v in allvars}
                for a,b in edges:adj[a].add(b);adj[b].add(a)
                components=[];visited=set()
                for v in sorted(allvars):
                    if v in visited:continue
                    comp=set();stack=[v]
                    while stack:
                        a=stack.pop()
                        if a in visited:continue
                        visited.add(a);comp.add(a);stack.extend(adj[a]-visited)
                    components.append(comp)
                if len(components)==holes and all(len(c)==birds and
                    {lookup[v] for v in c}==set(range(birds)) and
                    all(len(adj[v])==birds-1 for v in c) for c in components):
                    return "Kissat404","complete_pigeonhole"
    # Four 3-CNF clauses forbidding exactly one parity class on each
    # triple = an XOR equation. Odd global RHS with even incidence -> UNSAT.
    if all(len(c)==3 and len(set(map(abs,c)))==3 for c in cs):
        groups=collections.defaultdict(set)
        for clause in cs:
            ordered=sorted(clause,key=abs)
            support=tuple(abs(x) for x in ordered)
            mask=sum((1<<j) for j,x in enumerate(ordered) if x<0)
            groups[support].add(mask)
        if len(groups)*4==len(cs) and all(len(v)==4 for v in groups.values()):
            rhs=0;occ=collections.Counter();valid=True
            for support,masks in groups.items():
                parity={int(x).bit_count()%2 for x in masks}
                if len(parity)!=1:valid=False;break
                bad=next(iter(parity))
                if masks!={x for x in range(8) if x.bit_count()%2==bad}:
                    valid=False;break
                rhs^=(1-bad)
                for v in support:occ[v]+=1
            if valid and rhs==1 and len(occ)==n and all(count%2==0 for count in occ.values()):
                return "Kissat404","odd_global_xor_parity"
    return "DRNAS_Legacy","safe_default"

def selftest():
    cases=[];detected=collections.Counter()
    for family in FAMILIES:
        for idx in range(8):
            c,b=make(family,idx)
            assert make(family,idx)==(c,b)
            guess,why=classify(b)
            # Test intended structure detection, not a performance claim.
            expected=family in ("pigeonhole_unsat","cubic_xor_unsat")
            assert (guess=="Kissat404")==expected,(family,idx,guess,why)
            detected[why]+=1;cases.append(c)
    assert len(cases)==40 and len({c["sha256"] for c in cases})==40
    print("V136_SELFTEST_PASS",len(cases),dict(detected),flush=True)
if __name__=="__main__":selftest()
