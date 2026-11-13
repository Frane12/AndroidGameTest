#!/usr/bin/env python3
"""X4.1: collect real transition observations, never turn conflicts into distance labels.

Synthetic controls are labelled SYNTHETIC; SAT2024 originals form a separately
labelled, retrospective cohort. Families are split before any solver outcomes.
External SAT witness checking is mandatory. UNSAT without a checked proof has
no supervised finishing-time target. X4.1's policy is not learned or altered.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time

ROOT=Path('drnas_x41_results')
BIN=Path('build/drnas-x41')
FAMILIES={
    'train': ('planted_3sat','hidden_2sat_sat','horn_implications','pigeonhole_unsat'),
    'validation': ('parity3_planted','graph_k4_unsat'),
    'holdout': ('random_2sat_sat','structured_mix_sat'),
}

def emit(tag, obj):
    print(tag+' '+json.dumps(obj,sort_keys=True,separators=(',',':')),flush=True)

def dimacs(path,n,clauses):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
    return hashlib.sha256(path.read_bytes()).hexdigest()

def generate(family,rep,root):
    """Small diverse *synthetic controls*, never advertised as real SAT2024."""
    seed=int.from_bytes(hashlib.sha256(f'{family}:20261113:{rep}'.encode()).digest()[:8],'big')
    rng=random.Random(seed)
    clauses=[]; oracle='SAT_BY_PLANTED_WITNESS'
    n=24+(rep%21)
    secret=[rng.choice((False,True)) for _ in range(n)]
    def satisfied(c):return any(secret[abs(v)-1]==(v>0) for v in c)
    def planted(width):
        vs=rng.sample(range(1,n+1),width)
        c=[rng.choice((-1,1))*v for v in vs]
        if not satisfied(c): c[0]=-c[0]
        assert satisfied(c)
        return c
    if family=='planted_3sat':
        for _ in range(4*n):clauses.append(planted(3))
    elif family=='hidden_2sat_sat':
        for _ in range(5*n):
            c=planted(2)
            clauses.extend((c+[1],c+[-1]))
    elif family=='horn_implications':
        secret=[False]*n
        for _ in range(5*n):
            vs=rng.sample(range(1,n+1),rng.randint(2,4))
            c=[-v for v in vs]
            if rng.random()<.25:c[0]=vs[0]
            clauses.append(c)
        for _ in range(2):clauses.append([-rng.randint(1,n)])
    elif family=='pigeonhole_unsat':
        oracle='UNSAT_BY_PHP_THEOREM'
        p=4+rep%4;h=p-1;n=p*h
        for pigeon in range(p):clauses.append([pigeon*h+j+1 for j in range(h)])
        for j in range(h):
            for a in range(p):
                for b in range(a+1,p):clauses.append([-(a*h+j+1),-(b*h+j+1)])
        # Additional varying SAT clauses on fresh variables diversify the
        # mathematical PHP core without duplicating identical CNF files.
        offset=n;aux=4+(rep%11);n+=aux
        other=[rng.choice((False,True)) for _ in range(aux)]
        for _ in range(4*aux+rep%7):
            vs=rng.sample(range(aux),3)
            c=[rng.choice((-1,1))*(offset+v+1) for v in vs]
            if not any(other[abs(t)-offset-1]==(t>0) for t in c):c[0]=-c[0]
            clauses.append(c)
    elif family=='parity3_planted':
        for _ in range(2*n):
            vs=rng.sample(range(1,n+1),3)
            parity=sum(secret[v-1] for v in vs)%2
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=parity:
                    clauses.append([(-v if bit else v) for v,bit in zip(vs,bits)])
    elif family=='graph_k4_unsat':
        oracle='UNSAT_BY_K4_SUBGRAPH'
        k=4+rep%5;n=3*k
        for v in range(k):
            cols=[3*v+c+1 for c in range(3)]
            clauses.append(cols)
            for a in range(3):
                for b in range(a+1,3):clauses.append([-cols[a],-cols[b]])
        edges={(i,j) for i in range(4) for j in range(i+1,4)}
        for _ in range(k+rep%4):
            a,b=rng.sample(range(k),2)
            edges.add(tuple(sorted((a,b))))
        for u,v in sorted(edges):
            for color in range(3):clauses.append([-(3*u+color+1),-(3*v+color+1)])
        offset=n;aux=4+rep%13;n+=aux
        other=[rng.choice((False,True)) for _ in range(aux)]
        for _ in range(4*aux+rep%5):
            vs=rng.sample(range(aux),3)
            c=[rng.choice((-1,1))*(offset+v+1) for v in vs]
            if not any(other[abs(t)-offset-1]==(t>0) for t in c):c[0]=-c[0]
            clauses.append(c)
    elif family=='random_2sat_sat':
        for _ in range(6*n):clauses.append(planted(2))
    elif family=='structured_mix_sat':
        for _ in range(3*n):clauses.append(planted(rng.choice([2,3,4])))
        for _ in range(n//2):
            vs=rng.sample(range(1,n+1),3)
            parity=sum(secret[v-1] for v in vs)%2
            for bits in itertools.product((0,1),repeat=3):
                if sum(bits)%2!=parity:
                    clauses.append([(-v if bit else v) for v,bit in zip(vs,bits)])
    else:raise ValueError(family)
    if oracle.startswith('SAT'):
        assert all(satisfied(c) for c in clauses),(family,rep)
    name=f's_{family}_{rep:03d}.cnf';path=root/name
    sha=dimacs(path,n,clauses)
    split=next(k for k,v in FAMILIES.items() if family in v)
    return dict(id=name,path=str(path),sha256=sha,nvars=n,
                nclauses=len(clauses),family='synthetic:'+family,
                oracle=oracle,cohort='synthetic_controls',split=split)

def select_official(n):
    sys.path.insert(0,str(Path('research').resolve()))
    import drnas_s6_diverse as S6
    S6.B.ROOT=ROOT/'official_sources'
    pool=S6.B.collect()
    # Select with ONLY pre-solve nvars/bytes. No known outcome, trial, or filename.
    entries=[]
    for src in pool:
        p=Path(src['path'])
        entries.append(dict(src,nvars=S6.B.nvars(p),bytes=p.stat().st_size))
    selected=sorted(entries,key=lambda v:(v['nvars'],v['bytes'],v['sha256']))[:n]
    # Deterministic family-disjoint split: no same normalized name family in
    # two splits; holds separately from synthetic families.
    unique={s['normalized_name_family'] for s in selected}
    if len(unique)!=len(selected):raise RuntimeError('official family overlap; need grouping')
    rng=random.Random(20261113)
    families=sorted(unique);rng.shuffle(families)
    split={fam:('train' if i%5<3 else 'validation' if i%5==3 else 'holdout')
           for i,fam in enumerate(families)}
    return [dict(id='real:'+s['sha256'][:12],path=s['path'],sha256=s['sha256'],
                 nvars=s['nvars'],nclauses=0,family='SAT2024:'+s['normalized_name_family'],
                 oracle=None,cohort='retrospective_SAT2024_original',split=split[s['normalized_name_family']])
            for s in selected]

def parse_dimacs(path):
    n=None; clauses=[]; cur=[]
    with Path(path).open('r',encoding='ascii',errors='strict') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(('c','%')):continue
            if line.startswith('p '):
                parts=line.split()
                if len(parts)!=4 or parts[1]!='cnf' or n is not None:raise ValueError('header')
                n=int(parts[2]); continue
            for tok in line.split():
                if tok=='c':break
                x=int(tok)
                if x:cur.append(x)
                else:clauses.append(cur);cur=[]
    if n is None or cur:raise ValueError('invalid CNF')
    return n,clauses

def verify_sat(path,stdout,nvars):
    assn={}
    for line in stdout.splitlines():
        if not line.startswith('v '):continue
        for token in line[2:].split():
            l=int(token)
            if not l:continue
            if abs(l) in assn:return False
            assn[abs(l)]=l>0
    if len(assn)!=nvars or set(assn)!=set(range(1,nvars+1)):return False
    n,clauses=parse_dimacs(path)
    return n==nvars and all(any(assn[abs(x)]==(x>0) for x in c) for c in clauses)

def run(src,cap,trace_dir):
    path=Path(src['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=src['sha256']:
        raise RuntimeError('CNF SHA changed')
    trace=trace_dir/(src['sha256']+'.jsonl')
    cmd=[str(BIN),str(path),'--mode','trace','--time',str(cap),'--stats','--transitions',str(trace)]
    started=time.monotonic()
    try:
        cp=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+1.25)
    except subprocess.TimeoutExpired:
        return dict(status='UNKNOWN',e2e_s=cap+1.25,PAR2_verified_s=2*cap,trace_samples=0,learner_rows=[])
    elapsed=time.monotonic()-started
    if cp.returncode not in (0,10,20):
        raise RuntimeError(f'x41 failed: {src["id"]} code {cp.returncode}: {cp.stderr[-1200:]}')
    status='UNKNOWN'
    if cp.returncode==10:
        if not verify_sat(path,cp.stdout,src['nvars']):raise RuntimeError('invalid original CNF SAT witness')
        status='SAT_VERIFIED'
    elif cp.returncode==20:
        status=('UNSAT_CONSTRUCTION_CHECKED' if (src.get('oracle') or '').startswith('UNSAT_BY_')
                else 'UNSAT_UNVERIFIED')
    if (src.get('oracle') or '').startswith('SAT_BY_') and status.startswith('UNSAT'):
        raise RuntimeError('known SAT contradicted')
    if (src.get('oracle') or '').startswith('UNSAT_BY_') and status=='SAT_VERIFIED':
        raise RuntimeError('known UNSAT contradicted')
    if elapsed>cap:status='UNKNOWN'  # includes process IO and trace serialization
    verified=status in ('SAT_VERIFIED','UNSAT_CONSTRUCTION_CHECKED')
    trace_records=[]
    if trace.exists():
        for line in trace.read_text().splitlines():
            trace_records.append(json.loads(line))
        if trace_records and (trace_records[0]['type']!='meta' or trace_records[0]['version']!=2):
            raise RuntimeError('incompatible transition trace')
    rows=[]
    for step in trace_records[1:]:
        if step.get('type')!='transition':raise RuntimeError('unexpected event')
        # The native SAT label is permitted only AFTER independent original-CNF
        # witness verification and E2E cap enforcement.
        label=(step.get('remaining_finish_wall_s') if status=='SAT_VERIFIED' else None)
        rows.append({'sha256':src['sha256'],'id':src['id'],'cohort':src['cohort'],
                     'family':src['family'],'split':src['split'],'nvars':src['nvars'],
                     'result':status,'logic':step['logic'],'structure':step['structure'],
                     'before':step['before'],'after':step['after'],
                     'label_remaining_wall_s':label,'target_is_observed_not_causal':True})
    return dict(status=status,e2e_s=round(elapsed,6),PAR2_verified_s=round(elapsed if verified else 2*cap,6),
                trace_samples=len(rows),learner_rows=rows)

def collect(sources,cohort,cap):
    root=ROOT/cohort
    root.mkdir(parents=True,exist_ok=True)
    manifest=[{k:v for k,v in s.items() if k!='path'} for s in sources]
    if len({s['sha256'] for s in sources})!=len(sources):raise RuntimeError('SHA collision')
    for a in ('train','validation','holdout'):
        af={s['family'] for s in sources if s['split']==a}
        if any(af & {s['family'] for s in sources if s['split']==b} for b in ('train','validation','holdout') if b!=a):
            raise RuntimeError('family split leakage')
    # Freeze manifest before running a single solver. Names and outcomes do not
    # reach the X4.1 branch policy; manifest only belongs to Python harness.
    mp=root/'frozen_manifest.json'
    encoded=json.dumps(manifest,sort_keys=True,indent=2)+'\n'
    mp.write_text(encoded)
    manifest_sha=hashlib.sha256(encoded.encode()).hexdigest()
    counts=collections.defaultdict(collections.Counter)
    label_count=0;total_records=0
    with (root/'trials.jsonl').open('w') as trials,(root/'transitions.jsonl').open('w') as trans:
        for i,src in enumerate(sources):
            (root/'traces').mkdir(exist_ok=True)
            r=run(src,cap,root/'traces')
            fields={k:v for k,v in r.items() if k!='learner_rows'}
            row=dict(src_id=src['id'],sha256=src['sha256'],family=src['family'],split=src['split'],**fields)
            trials.write(json.dumps(row,sort_keys=True)+'\n');trials.flush()
            for step in r['learner_rows']:
                trans.write(json.dumps(step,separators=(',',':'))+'\n')
                label_count+=step['label_remaining_wall_s'] is not None
            trans.flush()
            total_records+=r['trace_samples']
            c=counts[src['split']];c['trials']+=1;c['solved']+=r['status'] in ('SAT_VERIFIED','UNSAT_CONSTRUCTION_CHECKED')
            c['sat_verified']+=r['status']=='SAT_VERIFIED';c['unsat_construction_checked']+=r['status']=='UNSAT_CONSTRUCTION_CHECKED'
            c['unverified_unsat']+=r['status']=='UNSAT_UNVERIFIED';c['unknown']+=r['status']=='UNKNOWN'
            c['PAR2_milliseconds']+=round(r['PAR2_verified_s']*1000)
            if i%16==0 or i+1==len(sources):emit('X41_PROGRESS',dict(cohort=cohort,completed=i+1,total=len(sources),verified_labels=label_count))
    report=dict(cohort=cohort,source_count=len(sources),manifest_sha256=manifest_sha,
                cap_s=cap,split={k:dict(v) for k,v in counts.items()},transition_records=total_records,
                verified_future_labels=label_count,blind_holdout_not_trained=True,
                official_globally_blind=False,
                note='UNSAT without checked certificate has no future label; synthetic UNSAT mathematical constructions are not DRAT/LRAT proofs. All labels are observational, not causal.')
    (root/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    emit('X41_'+('SYNTHETIC' if cohort=='synthetic_controls' else 'OFFICIAL')+'_FINAL',report)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--synthetic',action='store_true');p.add_argument('--official',action='store_true')
    p.add_argument('--per-family',type=int,default=48)
    p.add_argument('--official-count',type=int,default=80)
    p.add_argument('--synthetic-cap',type=float,default=.35)
    p.add_argument('--official-cap',type=float,default=1.5)
    args=p.parse_args()
    if not (args.synthetic or args.official):p.error('choose --synthetic and/or --official')
    if not BIN.is_file():p.error('compile build/drnas-x41 first')
    if args.per_family<1 or args.official_count<1 or args.official_count>100:p.error('unsupported count')
    if hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=True)
    if args.synthetic:
        generated=ROOT/'generated'
        sources=[generate(fam,i,generated) for sp,fs in FAMILIES.items() for fam in fs for i in range(args.per_family)]
        collect(sources,'synthetic_controls',args.synthetic_cap)
    if args.official:collect(select_official(args.official_count),'retrospective_SAT2024_original',args.official_cap)

if __name__=='__main__':main()