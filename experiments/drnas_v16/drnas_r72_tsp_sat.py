#!/usr/bin/env python3
"""R72: exact weighted TSP decision CNFs vs pinned Kissat and R55/R61 policies.
8 unseen deterministic sources (n=8,10,12,14; each at optimum and optimum-1).
Held-Karp independent optimum, same one-core 15s wall cap including preprocessing.
"""
from __future__ import annotations
import argparse, hashlib, itertools, json, math, os, random
from pathlib import Path

PROTO='DRNAS-R72-TSP-EXACT-DECISION-CNF-20261103-v1'
COUNTS=(8,10,12,14)
CAP=15.0
REPS=2
SHARDS=4
MODES=('clean','r55_fixed18','r61_pair18')
SEED=7211032026
WIDTH=16

def ck(ok,msg):
    if not ok: raise RuntimeError('R72_FAIL_CLOSED '+msg)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def graph(n):
    rng=random.Random(SEED+n*1009)
    pts=[(rng.randrange(10,990),rng.randrange(10,990)) for _ in range(n)]
    ck(len(set(pts))==n,'duplicate coords')
    d=[[0 if i==j else max(1,math.isqrt((pts[i][0]-pts[j][0])**2+
       (pts[i][1]-pts[j][1])**2)//10) for j in range(n)] for i in range(n)]
    return pts,d

def held_karp(d):
    n=len(d)
    dp={(1<<j,j):(d[0][j],(0,j)) for j in range(1,n)}
    for k in range(2,n):
        new={}
        for subset in itertools.combinations(range(1,n),k):
            bits=sum(1<<j for j in subset)
            for j in subset:
                prev=bits^(1<<j)
                cost,p=min((dp[(prev,i)][0]+d[i][j],i) for i in subset if i!=j)
                new[(bits,j)]=(cost,dp[(prev,p)][1]+(j,))
        dp=new
    bits=(1<<n)-2
    cost,j=min((dp[(bits,j)][0]+d[j][0],j) for j in range(1,n))
    tour=dp[(bits,j)][1]+(0,)
    ck(len(tour)==n+1 and len(set(tour[:-1]))==n,'bad Held-Karp tour')
    ck(sum(d[a][b] for a,b in zip(tour,tour[1:]))==cost,'cost mismatch')
    return cost,list(tour)

class CNF:
    def __init__(self):self.vars=0;self.rows=[]
    def var(self):
        self.vars+=1
        return self.vars
    def add(self,*ls):
        ck(all(isinstance(x,int) and x!=0 for x in ls),'invalid literal')
        self.rows.append(ls)
    def onehot(self,vs):
        self.add(*vs)
        for a,b in itertools.combinations(vs,2):self.add(-a,-b)
    def adder(self,a,b,c):
        s=self.var();carry=self.var()
        for bits in itertools.product((0,1),repeat=3):
            if any(v is None and bit for v,bit in zip((a,b,c),bits)):continue
            negative_antecedent=[-v if bit else v for v,bit in zip((a,b,c),bits) if v is not None]
            total=sum(bits)
            self.add(*negative_antecedent,s if total%2 else -s)
            self.add(*negative_antecedent,carry if total>=2 else -carry)
        return s,carry
    def save(self,path):
        with Path(path).open('w',encoding='ascii') as f:
            f.write('c R72 exact weighted TSP SAT <=bound\n')
            f.write(f'p cnf {self.vars} {len(self.rows)}\n')
            for row in self.rows:f.write(' '.join(map(str,row))+' 0\n')

def encode(d,bound):
    n=len(d)
    ck(n>=4 and 0<=bound<1<<WIDTH,'bad instance or bound')
    f=CNF()
    x=[[f.var() for _ in range(n)] for _ in range(n)]
    for row in x:f.onehot(row)
    for c in range(n):f.onehot([x[t][c] for t in range(n)])
    f.add(x[0][0])
    for c in range(1,n):f.add(-x[0][c])
    num_bits=max(1,max(max(row) for row in d).bit_length())
    partial=[None]*WIDTH
    for t in range(n):
        next_t=(t+1)%n
        cost_bits=[f.var() for _ in range(num_bits)]
        for i in range(n):
            for j in range(n):
                if i==j:continue
                e=f.var()
                f.add(-e,x[t][i]);f.add(-e,x[next_t][j])
                f.add(-x[t][i],-x[next_t][j],e)
                for bit,v in enumerate(cost_bits):
                    f.add(-e,v if (d[i][j]>>bit)&1 else -v)
        result=[];carry=None
        for bit in range(WIDTH):
            v,carry=f.adder(partial[bit],cost_bits[bit] if bit<num_bits else None,carry)
            result.append(v)
        f.add(-carry)
        partial=result
    for k in range(WIDTH-1,-1,-1):
        if ((bound>>k)&1)==0:
            mismatch=[-partial[j] if (bound>>j)&1 else partial[j] for j in range(WIDTH-1,k,-1)]
            f.add(*mismatch,-partial[k])
    return f

def freeze(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for n in COUNTS:
        pts,d=graph(n);opt,tour=held_karp(d)
        for expected,bound in (('SAT',opt),('UNSAT',opt-1)):
            path=out/f'tsp_n{n}_{expected.lower()}.cnf'
            f=encode(d,bound);f.save(path)
            entry=dict(name=path.name,n=n,kind=expected,bound=bound,optimum=opt,
                optimum_tour=tour,coordinates=pts,distances=d,vars=f.vars,
                clauses=len(f.rows),sha256=sha(path))
            cases.append(entry)
            print('R72_FROZEN',path.name,'bound',bound,'optimum',opt,
                'vars',f.vars,'clauses',len(f.rows),flush=True)
    ck(len(cases)==8 and len({c['sha256'] for c in cases})==8,'bad unique cases')
    manifest=dict(protocol=PROTO,cases=cases,reps=REPS,cap_s=CAP,modes=list(MODES),
      limitations=['Synthetic exact TSP, not official TSPLIB','Precommitted R55 fixed18 from known source',
        '15s total wall for each method includes preprocessing and SAT model check',
        'UNSAT established by exact Held-Karp reference, no LRAT certificate'])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'sources.sha256').write_text(''.join(c['sha256']+'  '+c['name']+'\n' for c in cases))
    print('R72_FREEZE_PASS',sha(out/'manifest.json'),flush=True)

def check_source(root,c):
    src=Path(root)/c['name']
    ck(sha(src)==c['sha256'],'source SHA mismatch')
    ck(held_karp(c['distances'])[0]==c['optimum'],'Held-Karp mismatch')
    ck(c['bound']==c['optimum']-(c['kind']=='UNSAT'),'bound mismatch')
    return src

def measure(a):
    import r61_killer_transfer as core
    root=Path(a.sources);m=json.loads((root/'manifest.json').read_text())
    ck(m['protocol']==PROTO and m['cap_s']==CAP and
       m['modes']==list(MODES) and m['reps']==REPS,'protocol mismatch')
    ck(0<=a.shard<SHARDS,'bad shard')
    kb=Path(a.kissat).resolve();cb=Path(a.cadical).resolve()
    ck(kb.is_file() and cb.is_file(),'solver missing')
    core.CAP=CAP
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/'meta.json').write_text(json.dumps(dict(shard=a.shard,
      manifest_sha=sha(root/'manifest.json'),kissat_sha=sha(kb),
      cadical_sha=sha(cb),protocol=PROTO),indent=2)+'\n')
    rows=[]
    for case in m['cases'][a.shard::SHARDS]:
        src=check_source(root,case)
        for rep in range(REPS):
            order=list(MODES)
            rng=random.Random(int(hashlib.sha256(
                (case['sha256']+str(rep)+PROTO).encode()).hexdigest(),16))
            rng.shuffle(order)
            for mode in order:
                result=core.ordinary_trial(src,kb,cb,mode,cpu)
                ck(result['status']=='TIMEOUT' or result['status']==case['kind'],
                    'solver contradicts exact TSP')
                row=dict(case=case['name'],source_sha=case['sha256'],rep=rep,
                         mode=mode,**result)
                rows.append(row)
                (out/'rows.json').write_text(json.dumps(rows,indent=2)+'\n')
                print('R72_TRIAL',case['name'],rep,mode,result['status'],
                      result['wall_s'],'s',result['added'],'clauses',flush=True)
    ck(len(rows)==len(m['cases'][a.shard::SHARDS])*REPS*len(MODES),'missing trials')

def audit(a):
    root=Path(a.sources);m=json.loads((root/'manifest.json').read_text())
    ck(m['protocol']==PROTO and len(m['cases'])==8,'wrong manifest')
    pins=set();rows=[];seen=set()
    for i in range(SHARDS):
        p=Path(a.combined)/f'r72-tsp-shard-{i}'/'results'
        meta=json.loads((p/'meta.json').read_text())
        ck(meta['shard']==i and meta['manifest_sha']==sha(root/'manifest.json'),
           'source drift')
        pins.add((meta['kissat_sha'],meta['cadical_sha']))
        part=json.loads((p/'rows.json').read_text())
        ck(len(part)==len(m['cases'][i::SHARDS])*REPS*len(MODES),'missing shard')
        for row in part:
            key=(row['case'],row['rep'],row['mode'])
            ck(key not in seen,'duplicate row');seen.add(key)
            c=next(z for z in m['cases'] if z['name']==row['case'])
            ck(row['source_sha']==c['sha256'] and
               (row['status']=='TIMEOUT' or row['status']==c['kind']),'bad result')
        rows.extend(part)
    ck(len(pins)==1 and len(rows)==8*REPS*len(MODES),'pins or rows mismatch')
    summary={}
    for mode in MODES:
        r=[x for x in rows if x['mode']==mode]
        summary[mode]=dict(solved=sum(x['status']!='TIMEOUT' for x in r),
          trials=len(r),par2_total_s=round(sum(x['par2_s'] for x in r),6),
          cases_with_added=sum(x['added']>0 for x in r))
    result=dict(protocol=PROTO,summary=summary,rows=rows,
                binary_sha=next(iter(pins))[0],limitations=m['limitations'])
    Path(a.json).write_text(json.dumps(result,indent=2)+'\n')
    report=['# R72 exact TSP-to-SAT: pinned 15-second head-to-head',
      '8 exact near-optimal TSP decision CNFs: n=8,10,12,14; bound=opt or opt-1.',
      'Held-Karp verifies exact optimum; 48 one-core attempts, 2 repeats.',
      'Time includes preprocessing and SAT witness verification. PAR-2 timeout=30s.',
      '| Mode | Solved / 16 | PAR2 total (s) | With added certified clauses |',
      '|---|---:|---:|---:|']
    for mode in MODES:
        s=summary[mode]
        report.append(f"| {mode} | {s['solved']}/16 | {s['par2_total_s']:.4f} | {s['cases_with_added']} |")
    report+=['','| n | Bound | Status | Kissat (s) | R55 (s) | R61 (s) |',
             '|---:|---:|---|---|---|---|']
    for case in m['cases']:
        def fmt(mode):
            rr=sorted((r for r in rows if r['case']==case['name']
                       and r['mode']==mode),key=lambda r:r['rep'])
            return ','.join('TO' if z['status']=='TIMEOUT' else f"{z['wall_s']:.4f}" for z in rr)
        report.append(f"| {case['n']} | {case['bound']} | {case['kind']} | {fmt('clean')} | {fmt('r55_fixed18')} | {fmt('r61_pair18')} |")
    report+=['','## Limitations']+['- '+s for s in m['limitations']]
    Path(a.md).write_text('\n'.join(report)+'\n')
    print('R72_FINAL_AUDIT_PASS',json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    for n in (5,6,7):
        _,d=graph(n);best,_=held_karp(d)
        brute=min(sum(d[a][b] for a,b in zip((0,)+p,p+(0,)))
                  for p in itertools.permutations(range(1,n)))
        ck(best==brute,'DP vs brute force disagrees')
        for k in (best-1,best):
            f=encode(d,k)
            ck(f.vars>0 and len(f.rows)>0,'empty encoding')
            ck(all(all(0<abs(lit)<=f.vars for lit in row) for row in f.rows),
               'invalid CNF literal')
    print('R72_HELD_KARP_AND_DIMACS_SELFTEST_PASS',flush=True)

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='task',required=True)
    sub.add_parser('selftest')
    q=sub.add_parser('generate');q.add_argument('--out',required=True)
    q=sub.add_parser('measure')
    for name in ('sources','kissat','cadical','out'):q.add_argument('--'+name,required=True)
    q.add_argument('--shard',type=int,required=True)
    q=sub.add_parser('audit')
    for name in ('sources','combined','json','md'):q.add_argument('--'+name,required=True)
    a=p.parse_args()
    {'selftest':lambda:selftest(),'generate':lambda:freeze(a.out),
     'measure':lambda:measure(a),'audit':lambda:audit(a)}[a.task]()
if __name__=='__main__':main()
