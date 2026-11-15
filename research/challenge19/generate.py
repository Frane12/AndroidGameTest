#!/usr/bin/env python3
"""Deterministic, public-rule synthetic SAT/UNSAT benchmark set, not a blind holdout."""
from pathlib import Path
import itertools, json, random, hashlib
import networkx as nx

ROOT=Path(__file__).resolve().parent
CNF=ROOT/'cnf'; CNF.mkdir(exist_ok=True)
CERTS=ROOT/'certs';CERTS.mkdir(exist_ok=True)
WIT=ROOT/'witnesses';WIT.mkdir(exist_ok=True)
SEED=20261115
manifest=[]

class Formula:
    def __init__(self): self.n=0; self.clauses=[]
    def var(self): self.n+=1; return self.n
    def add(self,*xs):
        l=tuple(dict.fromkeys(xs))
        if not l or any(-x in l for x in l): raise ValueError(('invalid clause',l))
        self.clauses.append(l)
    def save(self,name,family,answer,reason,meta=None,witness=None):
        r=random.Random(SEED + sum(map(ord,name)))
        p=list(range(1,self.n+1)); r.shuffle(p); mp={i:p[i-1] for i in range(1,self.n+1)}
        clauses=[tuple(mp[abs(x)]*(1 if x>0 else -1) for x in c) for c in self.clauses]
        for c in clauses: assert len(c)==len(set(c)) and not(set(c)&{-x for x in c})
        r.shuffle(clauses)
        text='c DRNAS SYNTHETIC challenge (NOT an official/independent blind holdout)\n'
        text+=f'c family={family} expected={answer} seed={SEED}\n'
        text+=f'p cnf {self.n} {len(clauses)}\n'
        text+=''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
        dest=CNF/(name+'.cnf'); dest.write_text(text,encoding='ascii')
        sha=hashlib.sha256(dest.read_bytes()).hexdigest()
        if witness is not None:
            solution={mp[i]:bool(b) for i,b in witness.items()}
            assert len(solution)==self.n
            assert all(any((x>0)==solution[abs(x)] for x in c) for c in clauses),name
            (WIT/(name+'.json')).write_text(json.dumps({'type':'SAT_MODEL','assignment':{str(k):int(v) for k,v in solution.items()}},sort_keys=True))
        manifest.append({'file':f'cnf/{name}.cnf','family':family,'expected':answer,
                         'vars':self.n,'clauses':len(clauses),'sha256':sha,
                         'ground_truth':reason,'parameters':meta or {},
                         'witness_checked':witness is not None})
        return mp

def make_php(pigeon,hole):
    f=Formula(); v=[[f.var() for h in range(hole)] for p in range(pigeon)]
    for row in v: f.add(*row)
    for h in range(hole):
        for a,b in itertools.combinations(range(pigeon),2): f.add(-v[a][h],-v[b][h])
    w=None
    if pigeon<=hole:
        w={v[i][h]:int(i==h) for i in range(pigeon) for h in range(hole)}
    name=f'php_{pigeon}_into_{hole}'
    mp=f.save(name, 'pigeonhole', 'SAT' if w else 'UNSAT',
           'injective mapping impossible by pigeonhole' if not w else 'explicit injective assignment',
           {'pigeons':pigeon,'holes':hole},w)
    if w is None:
        cert={'type':'HALL_MATCHING', 'jobs':[[mp[x] for x in row] for row in v],
          'resources':[[mp[v[i][h]] for i in range(pigeon)] for h in range(hole)]}
        (CERTS/(name+'.json')).write_text(json.dumps(cert))

def make_tseitin(n,odd):
    g=nx.random_regular_graph(3,n,seed=SEED+n)
    assert nx.is_connected(g)
    f=Formula()
    edges=sorted(tuple(sorted(e)) for e in g.edges())
    v={e:f.var() for e in edges}
    charges={i:0 for i in g.nodes()}
    if odd: charges[n//2]=1
    for u in sorted(g.nodes()):
        vv=[v[tuple(sorted((u,k)))] for k in sorted(g.neighbors(u))]
        for bits in itertools.product([0,1],repeat=3):
            if sum(bits)%2 !=charges[u]:
                f.add(*[(-x if b else x) for x,b in zip(vv,bits)])
    w=None if odd else {x:0 for x in v.values()}
    name=f'tseitin_3regular_{n}_{"odd" if odd else "even"}'
    mp=f.save(name, 'tseitin_xor',
           'UNSAT' if odd else 'SAT',
           'XOR sum of vertex charges is odd, every edge appears twice' if odd else 'all-zero edge assignment',
           {'vertices':n,'edges':len(edges),'total_charge_mod2':sum(charges.values())%2,
           'graph_seed':SEED+n,'connected':True},w)
    if odd:
        cert={'type':'XOR_PARITY','equations':[{'vars':[mp[v[tuple(sorted((u,k)))]] for k in sorted(g.neighbors(u))], 'rhs':charges[u]} for u in sorted(g.nodes())]}
        (CERTS/(name+'.json')).write_text(json.dumps(cert))

def make_hall(k,outs=12,spares=3,sat=False):
    shared=k if sat else k-1
    resources=shared+outs+spares
    jobs=k+outs
    rng=random.Random(SEED+k+int(sat))
    f=Formula(); options={}
    for i in range(jobs):
        if i<k: resources_i=list(range(shared))
        else:
            resources_i=[shared+(i-k)]
            resources_i+=list(range(shared+outs,resources))
        options[i]=resources_i
    allpairs=[(i,r) for i,rs in options.items() for r in rs]
    rng.shuffle(allpairs)
    v={(i,r):f.var() for i,r in allpairs}
    for i,rs in options.items():
        f.add(*[v[i,r] for r in rs])
        for a,b in itertools.combinations(rs,2):f.add(-v[i,a],-v[i,b])
    for r in range(resources):
        takers=[i for i,rs in options.items() if r in rs]
        for i,j in itertools.combinations(takers,2):f.add(-v[i,r],-v[j,r])
    w=None
    if sat:
        w={x:0 for x in v.values()}
        for i in range(jobs):
            r=i if i<k else shared+(i-k)
            w[v[i,r]]=1
    name=f'hall_{k}_jobs_{shared}_slots_{"sat" if sat else "unsat"}'
    mp=f.save(name, 'hall_matching',
           'SAT' if sat else 'UNSAT',
           'constructive perfect matching' if sat else f'Hall violating subset: {k} jobs restricted to {shared} slots',
           {'critical_jobs':k,'critical_resources':shared,'outside_jobs':outs,'global_jobs':jobs,
            'global_resources':resources},w)
    if not sat:
        cert={'type':'HALL_MATCHING',
          'jobs':[[mp[v[i,r]] for r in options[i]] for i in range(k)],
          'resources':[[mp[v[i,r]] for i in range(k)] for r in range(shared)]}
        (CERTS/(name+'.json')).write_text(json.dumps(cert))

def make_schur(colors,n,partition=None):
    f=Formula(); v=[[f.var() for c in range(colors)] for i in range(n)]
    for row in v:
        f.add(*row)
        for a,b in itertools.combinations(row,2): f.add(-a,-b)
    for x in range(1,n+1):
        for y in range(x,n+1):
            z=x+y
            if z>n:break
            for c in range(colors):f.add(-v[x-1][c],-v[y-1][c],-v[z-1][c])
    w=None
    if partition:
        w={i:0 for row in v for i in row}
        for c,els in enumerate(partition):
            for el in els:w[v[el-1][c]]=1
    f.save(f'schur_{colors}colors_{n}', 'schur', 'SAT' if w else 'UNSAT',
           'explicit sum-free partition' if w else f'known theorem S({colors})={n-1}',
           {'colors':colors,'n':n,'coloring_forbidden': 'x+y=z with x<=y, x,y,z in [1,n]'},w)

if __name__=='__main__':
    for n in [40,80,160,320]:make_tseitin(n,True)
    for n in [40,80]:make_tseitin(n,False)
    for p,h in [(10,9),(16,15),(21,20),(20,20)]:make_php(p,h)
    for k in [15,23,31]:make_hall(k,sat=False)
    for k in [15,23]:make_hall(k,sat=True)
    s3=[[1,4,10,13],[2,3,11,12],[5,6,7,8,9]]
    s4=[[1,4,9,12,19,26,33,36,41,44],[2,3,10,11,15,16,29,34,35,42,43],
        [5,6,7,8,17,18,27,28,37,38,39,40],[13,14,20,21,22,23,24,25,30,31,32]]
    make_schur(3,13,s3);make_schur(3,14)
    make_schur(4,44,s4);make_schur(4,45)
    (ROOT/'manifest.json').write_text(json.dumps({'title':'DRNAS synthetic unsat challenge',
      'generated_on':'2026-11-15','seed':SEED,'holdout':False,'benchmarks':manifest},indent=2),encoding='utf8')
    print('generated',len(manifest),'cases')
    for x in manifest:print(x['expected'],x['family'],x['vars'],x['clauses'],x['file'])
