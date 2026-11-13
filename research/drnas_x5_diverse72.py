#!/usr/bin/env python3
"""Twelve source categories, three prescribed sizes, balanced SAT/UNSAT.
No outcome screening, training or source-family information enters any solver.
"""
import argparse,hashlib,itertools,json,os,random,tempfile
from pathlib import Path
import drnas_x5_bench as B
FAMILIES=('random3_sat','random4_sat','coloring_sat','xor_sat','cardinality_sat','circuit_sat',
          'coloring_unsat','xor_unsat','two_sat_unsat','cardinality_unsat','circuit_unsat','php_unsat')

class CNF:
    def __init__(self,n,rng):
        self.n=n;self.cs=[];self.rng=rng;self.model={v:bool(rng.randrange(2)) for v in range(1,n+1)}
    def new(self,value=False):
        self.n+=1;self.model[self.n]=bool(value);return self.n
    def val(self,l):return self.model[abs(l)]==(l>0)
    def gate(self,a,b,op):
        fn={'and':lambda x,y:x and y,'or':lambda x,y:x or y,'xor':lambda x,y:x!=y}[op]
        z=self.new(fn(self.val(a),self.val(b)))
        for x,y in itertools.product((False,True),repeat=2):
            # Exclude the unique incorrect output for each input combination.
            wrong=not fn(x,y)
            self.cs.append([-a if x else a,-b if y else b,-z if wrong else z])
        return z
    def at_most(self,lits,k):
        true=self.new(True);self.cs.append([true]);false=-true
        prev=[true]+[false]*(k+1)
        for i,x in enumerate(lits):
            row=[true]
            for j in range(1,k+2):
                if j>i+1:row.append(false);continue
                both=self.gate(prev[j-1],x,'and')
                row.append(self.gate(prev[j],both,'or'))
            prev=row
        self.cs.append([-prev[k+1]])

def source(family,index):
    level=index%3
    seed=int.from_bytes(hashlib.sha256(f'X5-DIVERSE72-v1|{family}|{index}'.encode()).digest()[:8],'big')
    rng=random.Random(seed);sat=family.endswith('_sat');c=CNF((32,64,112)[level],rng)
    if family.startswith('random'):
        k=3 if family.startswith('random3') else 4
        if k==4:c=CNF((28,48,80)[level],rng)
        density=(3.8,4.15,4.4)[level] if k==3 else (8.0,8.8,9.6)[level]
        for _ in range(round(c.n*density)):
            vs=rng.sample(range(1,c.n+1),k);lits=[v*rng.choice((-1,1)) for v in vs]
            if not any(c.val(l) for l in lits):lits[rng.randrange(k)]*=-1
            c.cs.append(lits)
    elif family.startswith('coloring'):
        nodes=(12,24,40)[level] if sat else (10,18,26)[level]
        c=CNF(nodes*3,rng);colors=[rng.randrange(3) for _ in range(nodes)];edges=set()
        if sat:
            for a,b in itertools.combinations(range(nodes),2):
                if colors[a]!=colors[b] and rng.random()<(.25,.35,.45)[level]:edges.add((a,b))
        else:
            # An odd rim with a universal hub needs four colors.
            rim=nodes-1
            edges.update(tuple(sorted((i,(i+1)%rim))) for i in range(rim))
            edges.update((i,rim) for i in range(rim))
            for a,b in itertools.combinations(range(rim),2):
                if rng.random()<.06:edges.add((a,b))
        var=lambda v,k:3*v+k+1
        for v in range(nodes):
            lits=[var(v,k) for k in range(3)];c.cs.append(lits)
            c.cs.extend([[-x,-y] for x,y in itertools.combinations(lits,2)])
            for k in range(3):c.model[var(v,k)]=colors[v]==k
        for v,w in sorted(edges):
            for k in range(3):c.cs.append([-var(v,k),-var(w,k)])
    elif family=='xor_sat':
        c=CNF((24,40,64)[level],rng)
        for _ in range(c.n+4):
            vs=rng.sample(range(1,c.n+1),3);rhs=sum(c.model[v] for v in vs)%2
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=rhs:c.cs.append([-v if b else v for v,b in zip(vs,bits)])
    elif family=='xor_unsat':
        # Tseitin on a connected cubic graph, total parity odd.
        nodes=(12,20,28)[level];edges={tuple(sorted((i,(i+1)%nodes))) for i in range(nodes)}
        while True:
            perm=list(range(nodes));rng.shuffle(perm)
            matching={tuple(sorted(perm[i:i+2])) for i in range(0,nodes,2)}
            if not matching&edges:break
        edges=sorted(edges|matching);c=CNF(len(edges),rng)
        parities=[rng.randrange(2) for _ in range(nodes)];parities[-1]^=(sum(parities)%2)^1
        assert sum(parities)%2==1
        for v in range(nodes):
            vs=[i+1 for i,e in enumerate(edges) if v in e];assert len(vs)==3
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=parities[v]:c.cs.append([-x if b else x for x,b in zip(vs,bits)])
    elif family=='two_sat_unsat':
        c=CNF((32,64,128)[level],rng)
        # Equality path plus inequality between its endpoints, no unit clauses.
        for v in range(1,c.n):c.cs.extend([[-v,v+1],[v,-v-1]])
        c.cs.extend([[1,c.n],[-1,-c.n]])
        for _ in range(c.n//5):
            x,y=rng.sample(range(1,c.n+1),2);c.cs.extend([[-x,y],[x,-y]])
    elif family.startswith('cardinality'):
        n=(10,14,18)[level];k=n//2;c=CNF(n,rng)
        chosen=set(rng.sample(range(1,n+1),k))
        for v in range(1,n+1):c.model[v]=v in chosen
        positive=list(range(1,n+1));negative=list(range(-1,-n-1,-1));rng.shuffle(positive);rng.shuffle(negative)
        c.at_most(positive,k)
        # A separate counter for complements prevents direct opposing units.
        c.at_most(negative,n-k if sat else n-k-1)
    elif family.startswith('circuit'):
        n=(12,20,32)[level];gates=(24,48,96)[level];c=CNF(n,rng)
        left=list(range(1,n+1));right=left.copy()
        for j in range(gates):
            a=len(left)-1;b=rng.randrange(len(left)-1);op=rng.choice(('and','or','xor'))
            left.append(c.gate(left[a],left[b],op));right.append(c.gate(right[b],right[a],op))
        x,y=left[-1],right[-1]
        c.cs.extend([[-x,y],[x,-y]] if sat else [[x,y],[-x,-y]])
    elif family=='php_unsat':
        holes=(4,5,7)[level];pigeons=holes+1;c=CNF(holes*pigeons,rng)
        var=lambda p,h:p*holes+h+1
        for p in range(pigeons):c.cs.append([var(p,h) for h in range(holes)])
        for h in range(holes):
            for p,q in itertools.combinations(range(pigeons),2):c.cs.append([-var(p,h),-var(q,h)])
        aux=[c.new(rng.randrange(2)) for _ in range(6+index%7)]
        for _ in range(4*len(aux)):
            lits=[v*rng.choice((-1,1)) for v in rng.sample(aux,3)]
            if not any(c.val(l) for l in lits):lits[0]*=-1
            c.cs.append(lits)
    else:raise ValueError(family)
    # Remove tautologies/duplicates and apply a reversible signed renaming.
    cs=[]
    for clause in c.cs:
        clause=set(clause)
        if any(-l in clause for l in clause):continue
        cs.append(tuple(sorted(clause)))
    cs=sorted(set(cs));assert cs
    if sat:assert all(any(c.val(l) for l in clause) for clause in cs),(family,index)
    perm=list(range(1,c.n+1));rng.shuffle(perm)
    mapping={v:perm[v-1]*rng.choice((-1,1)) for v in range(1,c.n+1)}
    renamed=[[mapping[abs(l)]*(1 if l>0 else -1) for l in clause] for clause in cs]
    for clause in renamed:rng.shuffle(clause)
    rng.shuffle(renamed)
    if sat:
        witness={abs(mapping[v]):c.model[v] if mapping[v]>0 else not c.model[v] for v in c.model}
        assert all(any(witness[abs(l)]==(l>0) for l in clause) for clause in renamed)
    text=f'p cnf {c.n} {len(renamed)}\n'+''.join(' '.join(map(str,clause))+' 0\n' for clause in renamed)
    return {'family':family,'source_id':index,'level':('small','medium','larger')[level],
            'expected_status':'SAT' if sat else 'UNSAT','kind':'synthetic_diverse',
            'cert':'SAT_CONSTRUCTED_CHECK_WITNESS' if sat else 'EXPECTED_UNSAT_PROOF_REQUIRED',
            'nvars':c.n,'nclauses':len(renamed),'sha256':hashlib.sha256(text.encode()).hexdigest(),'content':text}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cap',type=float,default=2);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--per-family',type=int,default=6);p.add_argument('--offset',type=int,default=9300000)
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    p.add_argument('--arms',default='CORE,X46_LEARNED,X5,X5_NO_MIN,Kissat,CaDiCaL,CMS')
    p.add_argument('--model',type=Path,default=B.ROOT/'experiments/drnas_x5/frozen_models/frozen_cost_model.txt')
    p.add_argument('--checker',type=Path,default=B.ROOT/'build/drat-trim');p.add_argument('--frat',type=Path,default=B.ROOT/'build/frat-rs')
    p.add_argument('--kissat',default='build/kissat');p.add_argument('--cadical',default='build/cadical');p.add_argument('--cms',default='build/cms')
    a=p.parse_args();assert a.cap>0 and a.repeats>=1 and a.per_family>0 and 0<=a.shard<a.shards
    arms=a.arms.split(',');os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=[source(f,a.offset+i) for f in FAMILIES for i in range(a.per_family)]
    assert len({s['sha256'] for s in cases})==len(cases)
    total=len(cases);random.Random(931113).shuffle(cases);cases=cases[a.shard::a.shards]
    a.out.mkdir(parents=True,exist_ok=False);(a.out/'sources').mkdir()
    manifest={'cohort':'synthetic','count':len(cases),'total_count':total,'cap':a.cap,'repeats':a.repeats,'arms':arms,
      'source_offset':a.offset,'shard':a.shard,'shards':a.shards,'logical_cpus':list(os.sched_getaffinity(0)),
      'model_sha256':B.sha(a.model),'candidate_sha256':B.sha(B.ROOT/'src/drnas_x5.cpp'),
      'baseline_sha256':B.sha(B.ROOT/'src/drnas_x41.cpp'),'checker_sha256':B.sha(a.checker),
      'sources':[{k:v for k,v in s.items() if k!='content'} for s in cases]}
    (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');rows=[]
    with tempfile.TemporaryDirectory() as tmp,(a.out/'trials.jsonl').open('w') as log:
        td=Path(tmp)
        for i,s in enumerate(cases):
            cnf=a.out/'sources'/(s['sha256']+'.cnf');cnf.write_text(s['content']);assert B.sha(cnf)==s['sha256']
            for rep in range(a.repeats):
                order=list(arms);random.Random(a.offset+i*31+rep).shuffle(order)
                for arm in order:
                    r=B.run(arm,s,cnf.resolve(),td,a)
                    if r['status'] in ('SAT','UNSAT'):assert r['status']==s['expected_status'],('wrong result',arm,s['sha256'])
                    r.update({'sha256':s['sha256'],'family':s['family'],'rep':rep,'shard':a.shard,'level':s['level']})
                    rows.append(r);log.write(json.dumps(r,sort_keys=True)+'\n');log.flush();B.emit('DIVERSE72_TRIAL',r)
            B.emit('DIVERSE72_PROGRESS',{'completed':i+1,'sources':len(cases),'shard':a.shard})
    assert B.sha(a.model)==manifest['model_sha256']
    r={'cohort':'synthetic','sources':len(cases),'trials':len(rows),'totals':B.summarize(rows,arms),
       'by_family':{f:B.summarize([r for r in rows if r['family']==f],arms) for f in FAMILIES if any(r['family']==f for r in rows)}}
    (a.out/'report.json').write_text(json.dumps(r,indent=2)+'\n');B.emit('DIVERSE72_FINAL',r)
if __name__=='__main__':main()
