#!/usr/bin/env python3
"""DRNAS X4: instrumentation-only ablation vs X3 and pinned references.

X4 executable never invokes external solvers. Reference solvers in THIS Python
benchmark only. SAT verified against original DIMACS. UNSAT official without
independent proof receives PAR2 penalty. Source SHA and family IDs are recorded.
"""
import argparse
import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path('drnas_x4_results')
X3 = Path('build/drnas-x3')
X4 = Path('build/drnas-x4')
NATIVE = ('X3_CORE','X3_ADAPTIVE','X4_CORE','X4_TRACE')
REFS = ('Kissat','CaDiCaL','CryptoMiniSat')


def emit(tag,value):
    print(tag+' '+json.dumps(value,sort_keys=True,separators=(',',':')),flush=True)


def dimacs(n, clauses, path):
    path.write_text(f'p cnf {n} {len(clauses)}\n'+
                    ''.join(' '.join(map(str,row))+' 0\n' for row in clauses))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(i, root):
    rng=random.Random(0xD12A500+i*1597)
    family=['hidden_2sat_sat','hidden_2sat_unsat','planted_3sat','random_3sat',
            'horn_mix','parity_mix','pigeonhole_unsat','graph_color_unsat'][i%8]
    clauses=[]; n=0; oracle=None
    if family=='hidden_2sat_sat':
        n=80+i%40
        secret=[rng.choice((0,1)) for _ in range(n)]
        for _ in range(6*n):
            a,b=rng.sample(range(2,n+1),2)
            pair=[rng.choice((-1,1))*a,rng.choice((-1,1))*b]
            if not any(secret[abs(x)-1]==(x>0) for x in pair):pair[0]*=-1
            clauses.extend((pair+[1],pair+[-1]))
        oracle='SAT_BY_WITNESS'
    elif family=='hidden_2sat_unsat':
        n=80+i%30
        a,b=2,3
        for pair in ([a,b],[-a,b],[a,-b],[-a,-b]):
            clauses.extend((pair+[1],pair+[-1]))
        for _ in range(n):
            a,b=rng.sample(range(2,n+1),2)
            clauses.extend(([a,b,1],[a,b,-1]))
        oracle='UNSAT_BY_EXACT_2SAT_CORE'
    elif family=='planted_3sat':
        n=100+i%70
        secret=[rng.choice((0,1)) for _ in range(n)]
        for _ in range(5*n):
            vars=rng.sample(range(1,n+1),3)
            clause=[rng.choice((-1,1))*v for v in vars]
            if not any(secret[abs(x)-1]==(x>0) for x in clause):clause[0]*=-1
            clauses.append(clause)
        oracle='SAT_BY_WITNESS'
    elif family=='random_3sat':
        n=80+i%65
        for _ in range(int(n*4.26)):
            clauses.append([rng.choice((-1,1))*x for x in rng.sample(range(1,n+1),3)])
    elif family=='horn_mix':
        n=120+i%50
        for _ in range(5*n):
            width=rng.randint(2,5)
            literals=[-x for x in rng.sample(range(1,n+1),width)]
            if rng.random()<0.35:literals[0]*=-1
            clauses.append(literals)
    elif family=='parity_mix':
        n=60+i%40
        secret=[rng.choice((0,1)) for _ in range(n)]
        for _ in range(n):
            vars=rng.sample(range(1,n+1),3)
            parity=sum(secret[v-1] for v in vars)%2
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=parity:
                    clauses.append([(-v if bit else v) for v,bit in zip(vars,bits)])
        oracle='SAT_BY_WITNESS'
    elif family=='pigeonhole_unsat':
        pigeons=4+i//8;holes=pigeons-1;n=pigeons*holes
        for p in range(pigeons):clauses.append([p*holes+h+1 for h in range(holes)])
        for h in range(holes):
            for p in range(pigeons):
                for q in range(p+1,pigeons):
                    clauses.append([-(p*holes+h+1),-(q*holes+h+1)])
        oracle='UNSAT_BY_PHP_THEOREM'
    elif family=='graph_color_unsat':
        k=4+i//8;n=3*k
        for v in range(k):
            cols=[3*v+c+1 for c in range(3)]
            clauses.append(cols)
            for a in range(3):
                for b in range(a+1,3):clauses.append([-cols[a],-cols[b]])
        for u in range(k):
            for v in range(u+1,k):
                for color in range(3):clauses.append([-(3*u+color+1),-(3*v+color+1)])
        oracle='UNSAT_BY_K4_SUBGRAPH'
    src=root/f's_{i:03d}.cnf'
    sha=dimacs(n,clauses,src)
    return dict(id=i,path=str(src),sha256=sha,group=family,nvars=n,
                clauses=len(clauses),oracle=oracle,
                split='train' if i<32 else 'validation' if i<48 else 'holdout')


def parse_dimacs(path):
    clauses=[];clause=[];n=None
    with Path(path).open('r',encoding='ascii') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(('c','%')):continue
            if line.startswith('p '):
                _,_,n,_=line.split();n=int(n);continue
            for tok in line.split():
                if tok=='c':break
                lit=int(tok)
                if lit:clause.append(lit)
                else:
                    clauses.append(clause);clause=[]
    if clause or n is None:raise RuntimeError('invalid CNF')
    return n,clauses


def verify_sat(path, output, expected_n):
    assn={}
    for line in output.splitlines():
        if line.startswith('v '):
            for tok in line[2:].split():
                lit=int(tok)
                if lit:
                    if abs(lit) in assn:return False
                    assn[abs(lit)]=(lit>0)
    if len(assn)!=expected_n or set(assn)!=set(range(1,expected_n+1)):return False
    n,clauses=parse_dimacs(path)
    return n==expected_n and all(any(assn[abs(l)]==(l>0) for l in c) for c in clauses)


def run_native(src, arm, cap, cohort):
    path=Path(src['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=src['sha256']:
        raise RuntimeError('original CNF SHA mismatch')
    if arm.startswith('X3_'):
        command=[str(X3),str(path),'--mode','core' if arm=='X3_CORE' else 'x3']
    else:
        command=[str(X4),str(path),'--mode','core' if arm=='X4_CORE' else 'trace']
    if arm=='X4_TRACE':
        trace_dir=ROOT/cohort/'traces'
        trace_dir.mkdir(parents=True,exist_ok=True)
        command += ['--transitions',str(trace_dir/(src['sha256'][:24]+'.jsonl'))]
    t=time.monotonic()
    try:
        cp=subprocess.run(command+['--time',str(cap),'--stats'],
                          capture_output=True,text=True,timeout=cap+1.5)
        elapsed=time.monotonic()-t
    except subprocess.TimeoutExpired:
        return dict(status='UNKNOWN',e2e_s=cap+1.5,PAR2_verified_s=2*cap,stats={})
    if cp.returncode not in (0,10,20):
        raise RuntimeError(f'{arm} solver error {cp.returncode}: {cp.stderr[-1200:]}')
    status='UNKNOWN'
    if cp.returncode==10:
        if not verify_sat(path,cp.stdout,src['nvars']):
            raise RuntimeError('SAT model failed independently on original CNF')
        status='SAT_VERIFIED'
    elif cp.returncode==20:
        oracle=src.get('oracle','')
        status=('UNSAT_CONSTRUCTION_CHECKED' if oracle and oracle.startswith('UNSAT_BY_')
                else 'UNSAT_UNVERIFIED')
    if (src.get('oracle') or '').startswith('SAT_BY_') and status.startswith('UNSAT'):
        raise RuntimeError('UNSAT contradicts planted SAT construction')
    if (src.get('oracle') or '').startswith('UNSAT_BY_') and status=='SAT_VERIFIED':
        raise RuntimeError('SAT contradicts UNSAT construction')
    stats={}
    for line in cp.stderr.splitlines():
        if line.startswith(('X3_STATS ','X4_STATS ')):
            stats=json.loads(line.split(' ',1)[1])
    if elapsed>cap:status='UNKNOWN'
    verified=status in ('SAT_VERIFIED','UNSAT_CONSTRUCTION_CHECKED')
    return dict(status=status,e2e_s=round(elapsed,6),
                PAR2_verified_s=round(elapsed if verified else 2*cap,6),stats=stats)


def official_sources():
    sys.path.insert(0,str(Path('research').resolve()))
    import drnas_s6_diverse as S6
    S6.B.ROOT=ROOT/'sat2024_sources'
    pool=S6.official_selection(S6.B.collect())
    sources=([s for s in pool if s['size_group']=='small'][:4]+
             [s for s in pool if s['size_group']=='medium'][:5]+
             [s for s in pool if s['size_group']=='large'][:3])
    if len(sources)!=12:raise RuntimeError('source selection failed')
    return [dict(id=s['id'],path=s['path'],sha256=s['sha256'],
             nvars=s['nvars'],group=s['normalized_name_family'],
             source_group=s['size_group'],oracle=None,
             split='historical_official') for s in sources]


def benchmark(sources, cohort, cap, refs=False):
    root=ROOT/cohort;root.mkdir(parents=True,exist_ok=True)
    arms=NATIVE+REFS if refs else NATIVE
    manifest=[{k:v for k,v in s.items() if k!='path'} for s in sources]
    (root/'selection.json').write_text(json.dumps(manifest,indent=2)+'\n')
    rows=[]
    with (root/'trials.jsonl').open('w') as out:
        for i,src in enumerate(sources):
            shift=i%len(arms)
            for arm in arms[shift:]+arms[:shift]:
                if arm in NATIVE:res=run_native(src,arm,cap,cohort)
                else:
                    # Reference solvers are isolated in benchmark Python and
                    # are NEVER linked/invoked inside the native X4 process.
                    sys.path.insert(0,str(Path('research').resolve()))
                    import drnas_s6_diverse as S6
                    source=dict(src,split='holdout',known_sat=False)
                    ref=S6.B.run_solver(arm,source,17,cap)
                    elapsed=ref['e2e_s'];status=ref['status']
                    verified=status=='SAT_VERIFIED' and elapsed<=cap
                    res=dict(status=status if elapsed<=cap else 'UNKNOWN',
                             e2e_s=elapsed,PAR2_verified_s=elapsed if verified else 2*cap,stats={})
                row={**res,'id':src['id'],'sha256':src['sha256'],'arm':arm,
                     'family':src['group'],'tier':src.get('source_group',src['group']),
                     'split':src['split'],'cap_s':cap}
                rows.append(row);out.write(json.dumps(row,sort_keys=True)+'\n');out.flush()
                emit('X4_TRIAL',{k:row[k] for k in ('id','arm','status','e2e_s','PAR2_verified_s')})
            emit('X4_PROGRESS',dict(dataset=cohort,completed=i+1,total=len(sources)))
    sums={}
    for arm in arms:
        rs=[r for r in rows if r['arm']==arm]
        sums[arm]=dict(solved=sum(r['status'] in ('SAT_VERIFIED','UNSAT_CONSTRUCTION_CHECKED') for r in rs),
                       SAT_verified=sum(r['status']=='SAT_VERIFIED' for r in rs),
                       UNSAT_construction_checked=sum(r['status']=='UNSAT_CONSTRUCTION_CHECKED' for r in rs),
                       UNSAT_unverified=sum(r['status']=='UNSAT_UNVERIFIED' for r in rs),
                       PAR2_verified_s=round(sum(r['PAR2_verified_s'] for r in rs),6),
                       e2e_s=round(sum(r['e2e_s'] for r in rs),6),trials=len(rs))
    groups={}
    for tier in sorted({row['tier'] for row in rows}):
        subset=[row for row in rows if row['tier']==tier]
        groups[tier]={arm:dict(solved=sum(r['status'] in ('SAT_VERIFIED','UNSAT_CONSTRUCTION_CHECKED')
                                         for r in subset if r['arm']==arm),
                               PAR2_verified_s=round(sum(r['PAR2_verified_s']
                                          for r in subset if r['arm']==arm),6)) for arm in arms}
    telemetry={arm:{key:sum(r.get('stats',{}).get(key,0) for r in rows if r['arm']==arm)
        for key in ('backdoor_checks','backdoor_leaves','backdoor_sat','backdoor_unsat',
                    'backdoor_nogoods','depth_probes','depth_conflicts','depth_positive_gain',
                    'pattern_samples','prefilter_attempts','prefilter_rejects',
                    'controller_probed_decisions','controller_feedback','controller_positive',
                    'controller_conflict_feedback','controller_cooldowns','controller_gained_long',
                    'controller_actual_implied',
                    'binary_propagations','decisions','conflicts',
                    'trace_samples_total','trace_samples_retained','trace_conflicts','trace_implied','trace_evicted')}
        for arm in arms}
    result=dict(dataset=cohort,cap_s=cap,source_count=len(sources),
                original_sha_distinct=len({s['sha256'] for s in sources})==len(sources),
                source_only_selection=(cohort=='official'),globally_blind=False,
                cpu_affinity=sorted(os.sched_getaffinity(0)),
                arms=sums,groups=groups,telemetry=telemetry,results_note=('Synthetic UNSAT checked by generator construction, '
                 'not independent DRAT/LRAT proof. Official UNSAT unverified penalized.'))
    (root/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    emit('X4_'+cohort.upper()+'_FINAL',result)
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--smoke',action='store_true')
    p.add_argument('--official',action='store_true')
    p.add_argument('--synthetic-count',type=int,default=64)
    p.add_argument('--smoke-cap',type=float,default=.35)
    p.add_argument('--official-cap',type=float,default=5.)
    args=p.parse_args()
    if not args.smoke and not args.official:p.error('select --smoke and/or --official')
    if not X3.exists() or not X4.exists():p.error('compile native X3 and X4 executables')
    if hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=True)
    if args.smoke:
        d=ROOT/'generated';d.mkdir(exist_ok=True)
        sources=[generate(i,d) for i in range(args.synthetic_count)]
        benchmark(sources,'synthetic',args.smoke_cap)
    if args.official:
        benchmark(official_sources(),'official',args.official_cap,refs=True)

if __name__=='__main__':main()