#!/usr/bin/env python3
"""Paired, synthetic XOR and pigeonhole investigation; proof limits explicit."""
import hashlib, json, os, random, pathlib
import drnas_hybrid_bench_helpers as B

B.CAP=4.0
B.REPS=2
B.ARMS=('R153_NATIVE','LTM9_NATIVE','DRNAS_HYBRID','DRNAS_GATED','Kissat','CaDiCaL','CryptoMiniSat')
kind=os.environ['CLASS_STUDY']
assert kind in ('xor','php')
B.ROOT=pathlib.Path('class_study_'+kind); B.ROOT.mkdir(exist_ok=True)

def transform(n, clauses, seed):
    rng=random.Random(seed); perm=list(range(1,n+1)); rng.shuffle(perm)
    flip=[rng.randrange(2) for _ in range(n)]
    result=[]
    for clause in clauses:
        row=[]
        for lit in clause:
            j=abs(lit)-1; v=perm[j]
            row.append(v if ((lit>0) != bool(flip[j])) else -v)
        rng.shuffle(row); result.append(row)
    rng.shuffle(result)
    return result

def php(holes, pigeons):
    x=lambda p,h: p*holes+h+1
    clauses=[[x(p,h) for h in range(holes)] for p in range(pigeons)]
    clauses += [[-x(p,h),-x(q,h)] for h in range(holes) for p in range(pigeons) for q in range(p+1,pigeons)]
    return holes*pigeons, clauses

def xor_case(n, seed, unsat, mixed):
    rng=random.Random(seed); planted={i:rng.randrange(2) for i in range(1,n+1)}
    clauses=[]; eq=[]; seen=set()
    # Four distinct XOR equations cancel in pairs. Flipping one parity
    # makes their sum 0 = 1, without any duplicate opposing equation.
    a,b,c,d,e,f=rng.sample(range(1,n+1),6)
    cycle=[tuple(sorted(t)) for t in ((a,b,c),(c,d,e),(a,d,f),(b,e,f))]
    for i,support in enumerate(cycle):
        rhs=sum(planted[v] for v in support)%2
        if unsat and i==3: rhs ^= 1
        eq.append((support,rhs)); seen.add(support)
        clauses.extend(B.parity(support,rhs))
    while len(eq)<n+8:
        support=tuple(sorted(rng.sample(range(1,n+1),3)))
        if support in seen: continue
        seen.add(support); rhs=sum(planted[v] for v in support)%2
        eq.append((support,rhs)); clauses.extend(B.parity(support,rhs))
    if mixed:
        for _ in range(n//3):
            vs=rng.sample(range(1,n+1),3)
            c=[v if planted[v] else -v for v in vs]
            clauses.append(c)
    return n,clauses

def generate():
    cases=[]
    for size in ((10,15,20,25,30,40,50,60) if kind=='xor' else (7,8,9)):
        for variant in range(4):
            for unsat in (False,True):
                for mixed in ((False,True) if kind=='xor' else (False,)):
                    seed=7502100+size*101+variant*7+int(unsat)*3+int(mixed)
                    if kind=='php':
                        n,clauses=php(size,size+int(unsat)); family='php_unsat' if unsat else 'php_sat'
                    else:
                        n,clauses=xor_case(size*10,seed,unsat,mixed)
                        family=('mixed_' if mixed else 'pure_')+('unsat' if unsat else 'sat')
                    clauses=transform(n,clauses,seed+773)
                    raw=B.W.canonical(n,clauses); sha=hashlib.sha256(raw).hexdigest()
                    path=B.ROOT/(sha+'.cnf'); path.write_bytes(raw)
                    cases.append(dict(origin=family,family=family,index=size*100+variant*10+int(unsat)*2+int(mixed),sha256=sha,vars=n,clauses=clauses,nclauses=len(clauses),path=str(path.resolve())))
    assert len({c['sha256'] for c in cases})==len(cases)
    return cases

cases=generate()
shard=int(os.environ["CLASS_SHARD"])
assert kind=="xor" and 0<=shard<4 and len(cases)==128
cases=[c for i,c in enumerate(cases) if (i//4)%4==shard]
assert len(cases)==32
manifest=[{k:v for k,v in c.items() if k not in ('clauses','path')} for c in cases]
(B.ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print('CLASS_STUDY_START '+json.dumps({'class':kind,'shard':shard,'cases':len(cases),'reps':B.REPS,'arms':B.ARMS,'cap_s':B.CAP,'unsat_control':'four distinct XOR equations with contradictory parity' if kind=='xor' else 'standard pigeonhole encoding','other_unsat':'unverified','solver_cpu':1}),flush=True)
rows=[]
for c in cases:
    for rep in range(B.REPS):
        statuses=set()
        for arm in (B.ARMS if rep==0 else tuple(reversed(B.ARMS))):
            r=B.run(c,arm,rep); rows.append(r); statuses.add(r['status'])
            print('CLASS_STUDY_TRIAL '+json.dumps(r,sort_keys=True),flush=True)
            (B.ROOT/'results.json').write_text(json.dumps(rows,indent=2))
        if 'SAT_VERIFIED' in statuses and ('UNSAT_GF2_VERIFIED' in statuses or 'UNSAT_UNVERIFIED' in statuses):
            raise RuntimeError('Conflicting SAT/UNSAT on original CNF')
summary={f:B.report([r for r in rows if r['family']==f]) for f in sorted({c['family'] for c in cases})}
(B.ROOT/'summary.json').write_text(json.dumps(summary,indent=2))
print('CLASS_STUDY_FINAL '+json.dumps(summary,sort_keys=True),flush=True)
