#!/usr/bin/env python3
"""DRNAS X1 smoke + exploratory SAT2024 comparison.

X1 alone solves CNF; Python prepares cases, checks SAT witnesses and reports
verified PAR2. On official CNFs an UNSAT result without a proof is NOT counted
as solved. Historical SAT2024 archive is NOT a globally blind holdout.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

BIN = Path('build/drnas-x1')
ROOT = Path('drnas_x1_results')
SEED = 1172026


def emit(label, data):
    print(label+' '+json.dumps(data,sort_keys=True,separators=(',',':')),flush=True)


def brute(n,clauses):
    for bits in itertools.product((False,True), repeat=n):
        if all(any(bits[abs(lit)-1] == (lit > 0) for lit in clause) for clause in clauses):
            return True
    return False


def generate(k):
    rng=random.Random(SEED + 15427*k)
    family=('planted3sat','random3sat','parity3','horn','three_color')[k%5]
    clauses=[]
    if family in ('planted3sat','random3sat'):
        n=rng.randint(8,12)
        secret=[rng.choice((False,True)) for _ in range(n)]
        for _ in range(rng.randint(24,56)):
            vs=rng.sample(range(1,n+1),3)
            row=[v*rng.choice((-1,1)) for v in vs]
            if family=='planted3sat' and not any(secret[abs(l)-1]==(l>0) for l in row):
                row[0]=-row[0]
            clauses.append(row)
    elif family=='parity3':
        n=rng.randint(5,10)
        for _ in range(rng.randint(3,9)):
            vs=rng.sample(range(1,n+1),3)
            required=rng.randint(0,1)
            if 'last_vs' in locals() and rng.random()<.12:
                vs=last_vs[:]
                required=1-last_required
            for bits in itertools.product((0,1),repeat=3):
                if (sum(bits)%2)!=required:
                    clauses.append([(-v if bit else v) for v,bit in zip(vs,bits)])
            last_vs, last_required=vs,required
    elif family=='horn':
        n=rng.randint(8,12)
        for _ in range(rng.randint(20,45)):
            vs=rng.sample(range(1,n+1),rng.randint(1,4))
            row=[-v for v in vs]
            if rng.random()<.48:row[rng.randrange(len(row))]*=-1
            clauses.append(row)
    else:
        vertices=rng.choice((3,4,5))
        n=3*vertices
        for v in range(vertices):
            colors=[3*v+c+1 for c in range(3)]
            clauses.append(colors)
            for a in range(3):
                for b in range(a+1,3):clauses.append([-colors[a],-colors[b]])
        for a in range(vertices):
            for b in range(a+1,vertices):
                if rng.random()<.78 or vertices==5:
                    for c in range(3): clauses.append([-(3*a+c+1),-(3*b+c+1)])
        # Add a distinct harmless planted clause if needed for unique SHA.
        if k%3==0: clauses.append([1,2,3])
    return n,clauses,family


def valid_original_witness(path, output, n):
    lits=[]
    for line in output.splitlines():
        if line.startswith('v '):
            lits.extend(int(s) for s in line[2:].split() if s != '0')
    if len(lits)!=n or set(map(abs,lits))!=set(range(1,n+1)):
        return False
    assn={abs(v):v>0 for v in lits}
    clause=[]
    count=0
    with Path(path).open('r',errors='replace') as f:
        for ln in f:
            if not ln.strip() or ln.lstrip().startswith(('c','p','%')):continue
            for tok in ln.split():
                lit=int(tok)
                if not lit:
                    count+=1
                    if not any(assn[abs(v)]==(v>0) for v in clause):return False
                    clause=[]
                else:clause.append(lit)
    return not clause and count>0


def run_native(path,n,mode,cap,known_truth=None):
    start=time.monotonic()
    try:
        cp=subprocess.run([str(BIN),str(path),'--mode',mode,'--time',str(cap),'--stats'],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                          timeout=cap+0.75)
    except subprocess.TimeoutExpired:
        return dict(status='UNKNOWN',e2e_s=round(time.monotonic()-start,6),PAR2_verified_s=2*cap)
    elapsed=time.monotonic()-start
    if cp.returncode not in (0,10,20):
        raise RuntimeError(f'X1 failure {cp.returncode}: {cp.stderr[-2500:]}')
    status='UNKNOWN'
    if cp.returncode==10:
        if not valid_original_witness(path,cp.stdout,n):
            raise RuntimeError(f'INVALID SAT WITNESS on original CNF: {path}, {mode}')
        status='SAT_VERIFIED'
    if cp.returncode==20:
        status='UNSAT_BRUTE_VERIFIED' if known_truth is False else 'UNSAT_UNVERIFIED'
    if known_truth is not None:
        if (status=='SAT_VERIFIED') != known_truth and status!='UNKNOWN':
            raise RuntimeError(f'X1 disagrees with brute oracle: {path}, {mode}, {status}')
        if status=='UNKNOWN':raise RuntimeError('tiny synthetic should never time out')
    stats={}
    for ln in cp.stderr.splitlines():
        if ln.startswith('X1_STATS '):stats=json.loads(ln[9:])
    verified=status in ('SAT_VERIFIED','UNSAT_BRUTE_VERIFIED') and elapsed<=cap
    return dict(status=status if elapsed<=cap else 'UNKNOWN',
                e2e_s=round(elapsed,6),PAR2_verified_s=round(elapsed if verified else 2*cap,6),
                stats=stats)


def summarize(rows,arms):
    result={}
    for arm in arms:
        rs=[r for r in rows if r['arm']==arm]
        result[arm]=dict(trials=len(rs),solved=sum(r['status'] in ('SAT_VERIFIED','UNSAT_BRUTE_VERIFIED') for r in rs),
                         SAT_verified=sum(r['status']=='SAT_VERIFIED' for r in rs),
                         UNSAT_brute_verified=sum(r['status']=='UNSAT_BRUTE_VERIFIED' for r in rs),
                         UNSAT_unverified=sum(r['status']=='UNSAT_UNVERIFIED' for r in rs),
                         PAR2_verified_s=round(sum(r['PAR2_verified_s'] for r in rs),6),
                         e2e_s=round(sum(r['e2e_s'] for r in rs),6))
    return result


def smoke(cap=2.0):
    root=ROOT/'smoke';root.mkdir(parents=True,exist_ok=True)
    sources=[];rows=[];shas=set()
    with (root/'trials.jsonl').open('w') as out:
        for i in range(100):
            n,clauses,family=generate(i)
            path=root/f'{i:03d}.cnf'
            path.write_text(f'c X1 {family} #{i}\np cnf {n} {len(clauses)}\n'+
                            ''.join(' '.join(map(str,row))+' 0\n' for row in clauses))
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if sha in shas:raise RuntimeError('duplicate source SHA')
            shas.add(sha)
            truth=brute(n,clauses)
            sources.append(dict(id=i,sha256=sha,family=family,vars=n,clauses=len(clauses),
                                expected='SAT' if truth else 'UNSAT',
                                split='train' if i<60 else 'validation' if i<80 else 'holdout'))
            for mode in (('baseline','horizon') if i%2==0 else ('horizon','baseline')):
                r=run_native(path,n,mode,cap,truth)
                r.update(id=i,arm='X1_'+mode.upper(),family=family,cap_s=cap)
                rows.append(r);out.write(json.dumps(r,sort_keys=True)+'\n');out.flush()
            if (i+1)%20==0:emit('X1_SMOKE_PROGRESS',dict(completed=i+1,total=100))
    (root/'selection.json').write_text(json.dumps(sources,indent=2)+'\n')
    summary=summarize(rows,['X1_BASELINE','X1_HORIZON'])
    summary['synthetic']=True
    summary['brute_force_verified']=True
    summary['split']='60 train / 20 validation / 20 frozen holdout (no training in X1)'
    summary['cap_s']=cap
    (root/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    emit('X1_SMOKE_FINAL',summary)


def official(cap=3.0):
    # This prep helper only selects original published CNFs, never solves for X1.
    sys.path.insert(0,str(Path('research').resolve()))
    import drnas_s6_diverse as S6
    root=ROOT/'official';root.mkdir(parents=True,exist_ok=True)
    S6.B.ROOT=ROOT/'downloaded_sat2024'
    all_selected=S6.official_selection(S6.B.collect())
    selected=([s for s in all_selected if s['size_group']=='small'][:4]+
              [s for s in all_selected if s['size_group']=='medium'][:5]+
              [s for s in all_selected if s['size_group']=='large'][:3])
    assert len(selected)==12 and len({s['sha256'] for s in selected})==12
    (root/'selection.json').write_text(json.dumps([dict(id=s['id'],sha256=s['sha256'],
         family=s['normalized_name_family'],size_group=s['size_group'],nvars=s['nvars'],
         cap_s=cap) for s in selected],indent=2)+'\n')
    arms=('X1_BASELINE','X1_HORIZON','Kissat','CaDiCaL','CryptoMiniSat')
    rows=[]
    with (root/'trials.jsonl').open('w') as out:
        for i,source in enumerate(selected):
            shifted=list(arms)[i%len(arms):]+list(arms)[:i%len(arms)]
            for arm in shifted:
                if arm.startswith('X1_'):
                    mode=arm[3:].lower()
                    r=run_native(source['path'],source['nvars'],mode,cap)
                else:
                    ref=S6.B.run_solver(arm,source,17,cap)
                    status=ref['status']
                    elapsed=ref['e2e_s']
                    verified=status=='SAT_VERIFIED' and elapsed<=cap
                    r=dict(status=status if elapsed<=cap else 'UNKNOWN',
                           e2e_s=elapsed,PAR2_verified_s=round(elapsed if verified else 2*cap,6))
                r.update(id=source['id'],sha256=source['sha256'],arm=arm,
                         group=source['size_group'],cap_s=cap)
                rows.append(r);out.write(json.dumps(r,sort_keys=True)+'\n');out.flush()
                emit('X1_OFFICIAL_TRIAL',dict(id=r['id'],arm=arm,status=r['status'],
                                               e2e_s=r['e2e_s'],PAR2_verified_s=r['PAR2_verified_s']))
            emit('X1_OFFICIAL_PROGRESS',dict(completed=i+1,total=len(selected)))
    summary=summarize(rows,arms)
    summary['note']='SAT2024 original, previous archive reused; NOT globally blind; UNSAT unverified penalized'
    (root/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    emit('X1_OFFICIAL_FINAL',summary)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--official',action='store_true')
    parser.add_argument('--cap',type=float,default=None)
    args=parser.parse_args()
    if not BIN.exists():raise RuntimeError('compile build/drnas-x1 before benchmark')
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=True)
    if args.smoke:smoke(cap=args.cap or 2.0)
    if args.official:official(cap=args.cap or 3.0)
    if not args.smoke and not args.official:parser.error('select --smoke and/or --official')
if __name__=='__main__':main()
