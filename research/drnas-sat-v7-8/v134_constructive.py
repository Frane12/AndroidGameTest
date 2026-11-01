#!/usr/bin/env python3
"""V13.4 reproducible middle-difficulty structural ladders. No solver selection."""
import hashlib,random
SALT='DRNAS-V134-STRUCTURAL-LADDERS-20261101-LOCKED-v1'
FAMILIES=('planted3_sat','color3_sat','pigeonhole_unsat','cubic_xor_sat','cubic_xor_unsat')
SIZES={'planted3_sat':(90,120,150,180,210,240),
'color3_sat':(45,60,75,90,105,120),
'pigeonhole_unsat':(8,10,12,14,16,18),
'cubic_xor_sat':(30,42,54,66,78,90),
'cubic_xor_unsat':(30,42,54,66,78,90)}
def rng(f,i):
    return random.Random(int(hashlib.sha256((SALT+'/'+f+'/'+str(i)).encode()).hexdigest(),16))
def dimacs(n,cs):
    return ('p cnf '+str(n)+' '+str(len(cs))+'\n'+'\n'.join(' '.join(map(str,c))+' 0' for c in cs)+'\n').encode()
def valid(cs,w):
    return all(any(w[abs(l)]==(l>0) for l in c) for c in cs)
def planted(i,r):
    n=SIZES['planted3_sat'][i];ratio=(3.5,3.9,4.15,4.3,4.5,4.7)[i]
    w={v:bool(r.getrandbits(1)) for v in range(1,n+1)}
    cs=[];seen=set()
    while len(cs)<round(n*ratio):
        vs=r.sample(range(1,n+1),3)
        ls=[v if r.getrandbits(1) else -v for v in vs]
        if not any(w[abs(l)]==(l>0) for l in ls):
            k=r.randrange(3);ls[k]=vs[k] if w[vs[k]] else -vs[k]
        t=tuple(sorted(ls,key=abs))
        if t not in seen:cs.append(t);seen.add(t)
    return n,cs,w,{'certificate':'constructive_sat_witness','density':ratio}
def color(i,r):
    vcount=SIZES['color3_sat'][i];n=vcount*3
    palette=[r.randrange(3) for _ in range(vcount)]
    w={3*v+c+1:(palette[v]==c) for v in range(vcount) for c in range(3)}
    cs=[]
    for v in range(vcount):
        b=3*v+1
        cs.append((b,b+1,b+2))
        for c in range(3):
            for d in range(c+1,3):cs.append((-b-c,-b-d))
    target=(3.8,4.2,4.6,5.0,5.4,5.8)[i]
    edges=0
    for u in range(vcount):
        for v in range(u+1,vcount):
            if palette[u]!=palette[v] and r.random()<1.5*target/vcount:
                edges+=1
                for c in range(3):cs.append((-(3*u+c+1),-(3*v+c+1)))
    return n,cs,w,{'certificate':'explicit_3coloring','vertices':vcount,'edges':edges}
def pigeon(i):
    holes=SIZES['pigeonhole_unsat'][i];birds=holes+1
    var=lambda p,h:1+p*holes+h
    cs=[]
    for p in range(birds):cs.append(tuple(var(p,h) for h in range(holes)))
    for h in range(holes):
        for p in range(birds):
            for q in range(p+1,birds):cs.append((-var(p,h),-var(q,h)))
    return holes*birds,cs,None,{'certificate':'pigeonhole_unsat','pigeons':birds,'holes':holes}
def graph(n,r):
    for _ in range(1500):
        slots=[v for v in range(n) for j in range(3)]
        r.shuffle(slots);edges=set();ok=True
        for a,b in zip(slots[0::2],slots[1::2]):
            t=tuple(sorted((a,b)))
            if a==b or t in edges:ok=False;break
            edges.add(t)
        if not ok:continue
        adj=[set() for v in range(n)]
        for a,b in edges:adj[a].add(b);adj[b].add(a)
        visited={0};stack=[0]
        while stack:
            for v in adj[stack.pop()]:
                if v not in visited:visited.add(v);stack.append(v)
        if len(visited)==n and all(len(x)==3 for x in adj):return sorted(edges)
    raise RuntimeError('Could not make simple connected cubic graph')
def xor(f,i,r):
    unsat=f.endswith('unsat');n=SIZES[f][i]
    edges=graph(n,r);inc=[[] for j in range(n)]
    for ei,(u,v) in enumerate(edges,1):inc[u].append(ei);inc[v].append(ei)
    w={e:bool(r.getrandbits(1)) for e in range(1,len(edges)+1)}
    rhs=[sum(w[e] for e in adj)%2 for adj in inc]
    if unsat:rhs[0]^=1
    cs=[]
    for adj,bit in zip(inc,rhs):
        assert len(adj)==3
        for mask in range(8):
            vs=[bool(mask>>j&1) for j in range(3)]
            if sum(vs)%2==bit:continue
            cs.append(tuple((-e if val else e) for e,val in zip(adj,vs)))
    return len(edges),cs,None if unsat else w,{
        'certificate':'odd_global_parity_unsat' if unsat else 'constructive_sat_witness',
        'vertices':n,'edges':len(edges),'rhs_mod2':sum(rhs)%2}
def make(f,i):
    assert f in FAMILIES and 0<=i<6
    r=rng(f,i)
    if f=='planted3_sat':n,cs,w,cert=planted(i,r)
    elif f=='color3_sat':n,cs,w,cert=color(i,r)
    elif f=='pigeonhole_unsat':n,cs,w,cert=pigeon(i)
    else:n,cs,w,cert=xor(f,i,r)
    label='UNSAT' if f.endswith('unsat') else 'SAT'
    if label=='SAT':assert w and len(w)==n and valid(cs,w)
    elif f=='pigeonhole_unsat':assert cert['pigeons']==cert['holes']+1
    else:assert cert['rhs_mod2']==1 and cert['edges']*2==cert['vertices']*3
    payload=dimacs(n,cs)
    return {'id':f'generated/v134/{f}/{i}','source':'synthetic','family':f,
            'index':i,'official_label':label,'sha256':hashlib.sha256(payload).hexdigest(),
            'variables':n,'clauses':len(cs),'certificate':cert},payload
def selftest():
    a=[make(f,i)[0] for f in FAMILIES for i in range(6)]
    assert len(a)==30 and len({x['sha256'] for x in a})==30
    assert sum(x['official_label']=='SAT' for x in a)==18
    assert sum(x['official_label']=='UNSAT' for x in a)==12
    for f in FAMILIES:
        for i in range(6):
            assert make(f,i)==make(f,i)
    print('V134_GENERATOR_PASS',len(a),flush=True)
if __name__=='__main__':selftest()
