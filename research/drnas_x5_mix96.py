#!/usr/bin/env python3
"""MIX96: fixed prospective synthetic suite; no outcome-based filtering."""
import argparse,hashlib,itertools,json,os,random,tempfile
from pathlib import Path
import drnas_x5_bench as B
from drnas_x5_diverse72 import CNF
FAMILIES=('random3','random4','cardinality','scheduling','xor','circuit','coloring','php')

def source(family,index):
    level=index%3;sat=(index//3)%2==0
    rng=random.Random(int.from_bytes(hashlib.sha256(f'MIX96-v1|{family}|{index}'.encode()).digest()[:8],'big'))
    expected='SAT' if sat else 'UNSAT'
    if family in ('random3','random4'):
        # Uniform random k-SAT, including both outcomes, without planting or screening.
        k=3 if family=='random3' else 4
        n=(100,150,220)[level] if k==3 else (50,70,90)[level]
        density=(4.20,4.26,4.32)[level] if k==3 else (9.7,9.9,10.1)[level]
        c=CNF(n,rng);expected='UNKNOWN'
        for _ in range(round(n*density)):
            c.cs.append([v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),k)])
    elif family=='cardinality':
        n=(18,22,26)[level];k=n//2;c=CNF(n,rng)
        chosen=set(rng.sample(range(1,n+1),k))
        for v in range(1,n+1):c.model[v]=v in chosen
        pos=list(range(1,n+1));neg=list(range(-1,-n-1,-1));rng.shuffle(pos);rng.shuffle(neg)
        c.at_most(pos,k);c.at_most(neg,n-k if sat else n-k-1)
    elif family in ('scheduling','php'):
        # Unit-duration jobs choose a time/resource cell; domains differ per job.
        cells=(8,10,12)[level] if family=='scheduling' else (7,8,9)[level]
        jobs=cells if sat else cells+1;c=CNF(cells*jobs,rng)
        assigned=list(range(cells));rng.shuffle(assigned)
        var=lambda j,h:j*cells+h+1
        for j in range(jobs):
            allowed=set(range(cells)) if family=='php' else {h for h in range(cells) if rng.random()<.65}
            allowed.add(assigned[j%cells]);c.cs.append([var(j,h) for h in sorted(allowed)])
            for h in range(cells):
                c.model[var(j,h)]=h==assigned[j%cells]
                if h not in allowed:c.cs.append([-var(j,h)])
            c.cs.extend([[-var(j,a),-var(j,b)] for a,b in itertools.combinations(range(cells),2)])
        for h in range(cells):
            c.cs.extend([[-var(a,h),-var(b,h)] for a,b in itertools.combinations(range(jobs),2)])
    elif family=='xor':
        nodes=(32,48,64)[level];edges={tuple(sorted((i,(i+1)%nodes))) for i in range(nodes)}
        while True:
            perm=list(range(nodes));rng.shuffle(perm)
            matching={tuple(sorted(perm[i:i+2])) for i in range(0,nodes,2)}
            if not matching&edges:break
        edges=sorted(edges|matching);c=CNF(len(edges),rng)
        for v in range(nodes):
            vs=[i+1 for i,e in enumerate(edges) if v in e]
            rhs=sum(c.model[x] for x in vs)%2
            if not sat and v==0:rhs^=1
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=rhs:c.cs.append([-x if b else x for x,b in zip(vs,bits)])
    elif family=='circuit':
        # Equivalent parity circuits with unrelated tree shapes and input orders.
        n=(10,14,18)[level];c=CNF(n,rng)
        outputs=[]
        for _ in range(2):
            pending=list(range(1,n+1));rng.shuffle(pending)
            while len(pending)>1:
                a=pending.pop(rng.randrange(len(pending)));b=pending.pop(rng.randrange(len(pending)))
                pending.append(c.gate(a,b,'xor'))
            outputs.append(pending[0])
        x,y=outputs;c.cs.extend([[-x,y],[x,-y]] if sat else [[x,y],[-x,-y]])
    elif family=='coloring':
        if sat:
            nodes=(30,50,80)[level];colors=[rng.randrange(3) for _ in range(nodes)]
            edges={(a,b) for a,b in itertools.combinations(range(nodes),2) if colors[a]!=colors[b] and rng.random()<.15}
        else:
            # Mycielski transformation of an odd cycle: triangle-free, 4-chromatic.
            rim=(11,15,19)[level];nodes=2*rim+1;colors=[0]*nodes
            base={tuple(sorted((i,(i+1)%rim))) for i in range(rim)};edges=set(base)
            for a,b in base:edges.update((tuple(sorted((a,b+rim))),tuple(sorted((b,a+rim)))))
            edges.update((i+rim,2*rim) for i in range(rim))
        c=CNF(nodes*3,rng);var=lambda v,k:3*v+k+1
        for v in range(nodes):
            lits=[var(v,k) for k in range(3)];c.cs.append(lits)
            c.cs.extend([[-x,-y] for x,y in itertools.combinations(lits,2)])
            for k in range(3):c.model[var(v,k)]=colors[v]==k
        for v,w in sorted(edges):
            for k in range(3):c.cs.append([-var(v,k),-var(w,k)])
    else:raise ValueError(family)
    cs=[]
    for clause in c.cs:
        clause=set(clause)
        if any(-l in clause for l in clause):continue
        cs.append(tuple(sorted(clause)))
    cs=sorted(set(cs));assert cs
    if expected=='SAT':assert all(any(c.val(l) for l in clause) for clause in cs)
    perm=list(range(1,c.n+1));rng.shuffle(perm)
    mapping={v:perm[v-1]*rng.choice((-1,1)) for v in range(1,c.n+1)}
    renamed=[[mapping[abs(l)]*(1 if l>0 else -1) for l in clause] for clause in cs]
    for clause in renamed:rng.shuffle(clause)
    rng.shuffle(renamed)
    if expected=='SAT':
        witness={abs(mapping[v]):c.model[v] if mapping[v]>0 else not c.model[v] for v in c.model}
        assert all(any(witness[abs(l)]==(l>0) for l in clause) for clause in renamed)
    text=f'p cnf {c.n} {len(renamed)}\n'+''.join(' '.join(map(str,clause))+' 0\n' for clause in renamed)
    return {'family':family,'source_id':index,'level':('small','medium','larger')[level],
            'expected_status':expected,'kind':'synthetic_mix96',
            'cert':'SAT_CONSTRUCTED_CHECK_WITNESS' if expected=='SAT' else 'UNVERIFIED',
            'nvars':c.n,'nclauses':len(renamed),'sha256':hashlib.sha256(text.encode()).hexdigest(),'content':text}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--cap',type=float,default=5);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--per-family',type=int,default=12);p.add_argument('--offset',type=int,default=9600000)
    p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=1)
    p.add_argument('--arms',default='CORE,X5_NO_MIN,X5,Kissat,CaDiCaL,CMS')
    p.add_argument('--model',type=Path,default=B.ROOT/'experiments/drnas_x5/frozen_models/frozen_cost_model.txt')
    p.add_argument('--checker',type=Path,default=B.ROOT/'build/drat-trim');p.add_argument('--frat',type=Path,default=B.ROOT/'build/frat-rs')
    p.add_argument('--kissat',default='build/kissat');p.add_argument('--cadical',default='build/cadical');p.add_argument('--cms',default='build/cms')
    a=p.parse_args();assert a.cap>0 and a.repeats>=1 and a.per_family>0 and 0<=a.shard<a.shards
    arms=a.arms.split(',');os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=[source(f,a.offset+i) for f in FAMILIES for i in range(a.per_family)]
    assert len({s['sha256'] for s in cases})==len(cases)
    total=len(cases);random.Random(961113).shuffle(cases);cases=cases[a.shard::a.shards]
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
                    if s['expected_status']!='UNKNOWN' and r['status'] in ('SAT','UNSAT'):assert r['status']==s['expected_status'],('wrong result',arm,s['sha256'])
                    r.update({'sha256':s['sha256'],'family':s['family'],'rep':rep,'shard':a.shard,'level':s['level']})
                    rows.append(r);log.write(json.dumps(r,sort_keys=True)+'\n');log.flush();B.emit('MIX96_TRIAL',r)
            B.emit('MIX96_PROGRESS',{'completed':i+1,'sources':len(cases),'shard':a.shard})
    assert B.sha(a.model)==manifest['model_sha256']
    r={'cohort':'synthetic','sources':len(cases),'trials':len(rows),'totals':B.summarize(rows,arms),
       'by_family':{f:B.summarize([r for r in rows if r['family']==f],arms) for f in FAMILIES if any(r['family']==f for r in rows)}}
    (a.out/'report.json').write_text(json.dumps(r,indent=2)+'\n');B.emit('MIX96_FINAL',r)
if __name__=='__main__':main()
