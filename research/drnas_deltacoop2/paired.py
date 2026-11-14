#!/usr/bin/env python3
"""Frozen REAL36 discovery: seven arms, same sources/CPU/cap, no promotion."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import tempfile
import time

R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research'))
sys.path.insert(0,str(R/'tests'))
import drnas_x55_cpu_real36 as B
from test_drnas_deltacoop2 import check_witness
ARMS=('OFF','LOCAL','SHADOW','JOIN','DELTA1','KISSAT','CADICAL')
BINS={a:'build/drnas-deltacoop2' for a in ARMS[:4]}
BINS.update(DELTA1='build/drnas-deltacoop1',KISSAT='cross/x59/build/kissat',CADICAL='cross/x59/build/cadical')
CAP=5.0
REPS=2
SHARDS=6
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def emit(tag,x):print(tag+' '+json.dumps(x,sort_keys=True),flush=True)
def hashes():return {**{a:sha(p) for a,p in BINS.items()},'DRAT':sha('build/drat-trim')}

def sample(src,arm,rep,cap,rawdir):
    raw=Path(src['path']).read_bytes();assert B.sha(raw)==src['sha256']
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/'trial.drat'
        cmd=[str(Path(BINS[arm]).resolve())]
        if arm in ('KISSAT','CADICAL'):
            if arm=='CADICAL':cmd+=['-q','--no-binary']
            cmd+=[str(Path(src['path']).resolve()),str(proof)]
        else:
            cmd+=[str(Path(src['path']).resolve()),'--mode','core','--time',str(max(.01,cap-.07)),
                  '--stats','--x5-no-minimize','--coop4','off' if arm=='OFF' else 'gate',
                  '--coop5','off','--proof',str(proof)]
            if arm!='DELTA1':cmd+=['--delta2','local' if arm=='OFF' else arm.lower()]
        started=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        killed=False
        try:out,err=p.communicate(timeout=cap+.15)
        except subprocess.TimeoutExpired:
            killed=True;os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
        wall=time.perf_counter()-started
        status='TIMEOUT' if killed else 'UNKNOWN';check_s=0
        if not killed:
            if p.returncode==10:
                n,cs=B.parse_cnf(raw)
                t=time.perf_counter();assert B.check_sat(out,cs,n),('BAD_MODEL',src['id'],arm)
                check_s=time.perf_counter()-t;status='SAT_VERIFIED'
            elif p.returncode==20:
                if proof.exists() and proof.stat().st_size:
                    t=time.perf_counter()
                    try:
                        q=subprocess.run(['build/drat-trim',src['path'],str(proof)],capture_output=True,text=True,timeout=25)
                        assert q.returncode>=0 and 's VERIFIED' in q.stdout,('BAD_UNSAT_PROOF',src['id'],arm,q.stdout[-500:],q.stderr[-500:])
                        status='UNSAT_CERTIFIED'
                    except subprocess.TimeoutExpired:status='UNSAT_CHECK_TIMEOUT'
                    check_s=time.perf_counter()-t
                else:status='UNSAT_UNVERIFIED'
            else:assert p.returncode in (0,153),('PROCESS_ERROR',arm,p.returncode,err[-600:])
        stats={};witnesses=[]
        for line in err.splitlines():
            tag,_,value=line.partition(' ')
            if tag in ('DELTA2_JOIN','DELTA_COOP1','X41_STATS','X5_STATS','COOP4_STATS'):
                assert tag not in stats,('DUPLICATE_TELEMETRY',tag)
                stats[tag]=json.loads(value)
            elif tag=='DELTA2_WITNESS':
                w=json.loads(value);check_witness(w);witnesses.append(w)
        if witnesses:
            _,original_clauses=B.parse_cnf(raw)
            original_set={tuple(sorted(set(c))) for c in original_clauses}
            for w in witnesses:
                for side in ('left','right'):
                    assert all(tuple(sorted(set(c))) in original_set for c in w[side]['cnf']), 'WITNESS_NOT_FROM_ORIGINAL'
        if arm in ARMS[:4] and not killed:
            assert 'DELTA2_JOIN' in stats and 'DELTA_COOP1' in stats,('MISSING_TELEMETRY',arm)
        if arm in ('OFF','SHADOW'):
            assert stats.get('DELTA_COOP1',{}).get('certified_lemmas',0)==0
        accepted=status in ('SAT_VERIFIED','UNSAT_CERTIFIED') and wall<=cap
        rawdir.mkdir(parents=True,exist_ok=True)
        (rawdir/f"{src['id']}-{rep}-{arm}.stderr").write_text(err)
        row={'id':src['id'],'sha256':src['sha256'],'family':src['family'],'arm':arm,'rep':rep,
             'status':status,'verified':accepted,'wall_e2e_s':wall,'verification_s':check_s,
             'PAR2_verified_s':wall if accepted else 2*cap,'stats':stats,
             'independently_checked_nonlinear_witnesses':sum(w.get('kind')!='tuple' for w in witnesses),
             'independently_checked_tuple_witnesses':sum(w.get('kind')=='tuple' for w in witnesses)}
        emit('DELTA2_TRIAL',{k:v for k,v in row.items() if k!='stats'})
        return row

def shard(index,smoke=False):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    src,meta=B.official_manifest()
    if smoke:
        sources=src;cap=.25;reps=1;arms=('JOIN',);folder=Path('delta2_smoke')
    else:
        sources=[z for i,z in enumerate(src) if i%SHARDS==index]
        cap=CAP;reps=REPS;arms=ARMS;folder=Path(f'delta2_shards/{index}')
    folder.mkdir(parents=True,exist_ok=False)
    save(folder/'manifest.json',{'arms':arms,'cap_s':cap,'reps':reps,'shard':index,
         'source_manifest_sha256':meta['manifest_sha256'],'binary_sha256':hashes(),
         'one_cpu':sorted(os.sched_getaffinity(0)),'retrospective':True,'blind_holdout':False,
         'promotion':False,'source_run':43582788399,'policy':'bounded-pair-join-v1'})
    with (folder/'trials.jsonl').open('w') as f:
        for s in sources:
            for rep in range(reps):
                order=list(arms);random.Random(int(s['sha256'][:16],16)+71*rep).shuffle(order)
                for arm in order:
                    row=sample(s,arm,rep,cap,folder/'raw')
                    f.write(json.dumps(row,sort_keys=True)+'\n');f.flush()
    emit('DELTA2_SHARD_PASS',{'shard':index,'sources':len(sources),'smoke':smoke})

def aggregate():
    src,meta=B.official_manifest();rows=[];manifests=[]
    for i in range(SHARDS):
        p=Path(f'delta2_downloads/delta2-shard-{i}/delta2_shards/{i}')
        manifests.append(json.loads((p/'manifest.json').read_text()))
        rows += [json.loads(l) for l in (p/'trials.jsonl').read_text().splitlines()]
    expected={(s['sha256'],r,a) for s in src for r in range(REPS) for a in ARMS}
    actual=[(r['sha256'],r['rep'],r['arm']) for r in rows]
    assert len(actual)==len(set(actual))==len(expected)==504 and set(actual)==expected
    for m in manifests:
        assert m['cap_s']==CAP and m['reps']==REPS and tuple(m['arms'])==ARMS
        assert m['binary_sha256']==manifests[0]['binary_sha256']
        assert len({m['binary_sha256'][a] for a in ARMS[:4]})==1
        assert m['source_manifest_sha256']==meta['manifest_sha256'] and len(m['one_cpu'])==1
        assert not m['blind_holdout'] and not m['promotion']
    statuses=collections.defaultdict(set)
    for r in rows:
        if r['verified']:statuses[r['sha256']].add(r['status'])
    assert all(len(s)==1 for s in statuses.values()),'CONTRADICTORY_CERTIFICATES'
    bykey={(r['sha256'],r['rep'],r['arm']):r for r in rows}
    shadow_trajectory_pairs=0
    for s in src:
        for rep in range(REPS):
            off=bykey[(s['sha256'],rep,'OFF')];shadow=bykey[(s['sha256'],rep,'SHADOW')]
            if off['verified'] and shadow['verified']:
                for key in ('decisions','conflicts'):
                    assert off['stats']['X41_STATS'][key]==shadow['stats']['X41_STATS'][key],('SHADOW_CHANGED_SEARCH',s['id'],key)
                shadow_trajectory_pairs+=1
    fields={}
    for a in ARMS:
        rr=[r for r in rows if r['arm']==a]
        keys={k for r in rr for k,v in r['stats'].get('DELTA2_JOIN',{}).items() if isinstance(v,(int,float))}
        fields[a]={'trials':len(rr),'verified':sum(r['verified'] for r in rr),
                   'par2_s':sum(r['PAR2_verified_s'] for r in rr),
                   'math':{k:sum(r['stats'].get('DELTA2_JOIN',{}).get(k,0) for r in rr) for k in keys},
                   'bridge_calls':sum(r['stats'].get('DELTA_COOP1',{}).get('bridge_calls',0) for r in rr),
                   'cascade_forces':sum(r['stats'].get('DELTA_COOP1',{}).get('cascade_forces',0) for r in rr),
                   'verified_witnesses':sum(r['independently_checked_nonlinear_witnesses'] for r in rr),
                   'verified_tuple_witnesses':sum(r['independently_checked_tuple_witnesses'] for r in rr)}
    families=sorted({r['family'] for r in rows});rng=random.Random(26021114)
    draws=[[rng.choice(families) for _ in families] for _ in range(2000)]
    comparisons={}
    for a in ('OFF','LOCAL','DELTA1','KISSAT','CADICAL'):
        gains=[]
        ft={k:{f:sum(r['PAR2_verified_s'] for r in rows if r['arm']==k and r['family']==f) for f in families} for k in (a,'JOIN')}
        for d in draws:
            before=sum(ft[a][f] for f in d);after=sum(ft['JOIN'][f] for f in d)
            gains.append(100*(before-after)/before if before else 0)
        gains.sort()
        comparisons['JOIN_vs_'+a]={'par2_gain_pct':100*(fields[a]['par2_s']-fields['JOIN']['par2_s'])/fields[a]['par2_s'],
            'family_cluster_ci95_pct':[gains[49],gains[1949]],'verified_solved_delta':fields['JOIN']['verified']-fields[a]['verified']}
    signal=[r for r in rows if r['arm']=='JOIN' and r['stats'].get('DELTA2_JOIN',{}).get('join_nonlinear_certified',0)>0]
    tuples=[r for r in rows if r['arm']=='JOIN' and r['independently_checked_tuple_witnesses']>0]
    report={'status':'COMPLETE','originals':36,'trials':504,'cap_s':CAP,'reps':REPS,
       'retrospective':True,'blind_holdout':False,'promotion':False,'novel_mathematics_proven':False,
       'verified_off_shadow_trajectory_pairs':shadow_trajectory_pairs,
       'fields':fields,'comparisons':comparisons,'source_manifest_sha256':meta['manifest_sha256'],
       'binary_sha256':manifests[0]['binary_sha256'],
       'nonlinear_signal_distinct_sources':len({r['sha256'] for r in signal}),
       'nonlinear_signal_families':sorted({r['family'] for r in signal}),
       'tuple_only_signal_distinct_sources':len({r['sha256'] for r in tuples}),
       'tuple_only_signal_families':sorted({r['family'] for r in tuples}),
       'interpretation':'Beyond exact single-block units and the affine hulls of the same two blocks only; not beyond all GF2/CSP algorithms.'}
    save('delta2_final/report.json',report)
    save('delta2_final/trials.json',rows)
    emit('DELTA2_FINAL',report)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('smoke','shard','aggregate'));p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.stage=='aggregate':aggregate()
    else:shard(a.shard,a.stage=='smoke')
