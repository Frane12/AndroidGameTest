#!/usr/bin/env python3
"""Retrospective paired REAL60, 10s, 1 CPU; no tuning/selection using results."""
import argparse
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import signal
import subprocess
import sys
import time

R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research'))
import drnas_x55_cpu_real36 as B
from drnas_deltacoop4.collect import load
from drnas_delta4x.verify import validate_events,events,validate_lemma,canon

CAP=10.0; REPS=2; SHARDS=12
PIN_MANIFEST='d714d58cce595b6f5a5b67703a773d0adc8530fe83b12f1b736ffe0b9ce79597'
ARMS=('OFF','D4_FROZEN','D4_FIXED','X_SHADOW','DELTA4X','KISSAT','CADICAL')
BINS={a:'build/drnas-delta4x' for a in ARMS[:5]}
BINS.update(D4_FROZEN='build/drnas-deltacoop4',KISSAT='cross/x59/build/kissat',CADICAL='cross/x59/build/cadical')
MODES={'OFF':'local','D4_FROZEN':'d4','D4_FIXED':'d4','X_SHADOW':'d4x-shadow','DELTA4X':'d4x'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def emit(tag,x):print(tag+' '+json.dumps(x,sort_keys=True),flush=True)
def hashes():return {**{a:sha(p) for a,p in BINS.items()},'CHECKER':sha('build/drat-trim')}
def sources():
    src,digest=load();assert digest==PIN_MANIFEST,'ORIGINAL_D4_COHORT_CHANGED'
    return src,digest

def freeze():
    src,digest=sources()
    protocol={'source_manifest_sha256':digest,'source_sha256':[s['sha256'] for s in src],
              'binary_sha256':hashes(),'cap_s':CAP,'reps':REPS,'arms':ARMS,'shards':SHARDS,
              'retrospective':True,'blind_holdout':False,'promotion':False,
              'time_definition':'solve wall incl parsing/collection/proof emission; proof check separately',
              'same_binary_controls':['OFF','D4_FIXED','X_SHADOW','DELTA4X'],
              'original_frozen_DELTA4_run':43589616448}
    save('delta4x_protocol.json',protocol);emit('DELTA4X_FREEZE',protocol)

def sample(s,arm,rep,folder,cap=CAP):
    stem=f"{s['id']}-{rep}-{arm}";folder.mkdir(parents=True,exist_ok=True)
    cnf=Path(s['path']).resolve();raw=cnf.read_bytes();assert B.sha(raw)==s['sha256']
    proof=folder/(stem+'.drat');usage=folder/(stem+'.usage')
    cmd=[str(Path(BINS[arm]).resolve())]
    if arm in ('KISSAT','CADICAL'):
        if arm=='CADICAL':cmd+=['-q','--no-binary']
        cmd+=[str(cnf),str(proof)]
    else:
        cmd+=[str(cnf),'--mode','core','--time',str(max(.01,cap-.07)),'--stats',
              '--x5-no-minimize','--coop4','off' if arm=='OFF' else 'gate','--coop5','off',
              '--delta2',MODES[arm],'--proof',str(proof)]
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2))
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
    start=time.perf_counter()
    p=subprocess.Popen(['/usr/bin/time','-f','%U %S %M','-o',str(usage),*cmd],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                       start_new_session=True,preexec_fn=limits)
    killed=False
    try:out,err=p.communicate(timeout=cap+.10)
    except subprocess.TimeoutExpired:
        killed=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,err=p.communicate()
    wall=time.perf_counter()-start
    (folder/(stem+'.stdout')).write_text(out);(folder/(stem+'.stderr')).write_text(err)
    status='TIMEOUT' if killed else 'UNKNOWN';check_s=0.0;proof_hash=None
    n,cs=B.parse_cnf(raw)
    if not killed and p.returncode==10:
        tick=time.perf_counter();assert B.check_sat(out,cs,n),('INVALID_ORIGINAL_MODEL',stem)
        check_s=time.perf_counter()-tick;status='SAT_VERIFIED'
    elif not killed and p.returncode==20:
        assert proof.exists() and proof.stat().st_size,('UNSAT_WITHOUT_PROOF',stem)
        tick=time.perf_counter()
        try:
            q=subprocess.run(['build/drat-trim',str(cnf),str(proof)],capture_output=True,text=True,timeout=25)
            (folder/(stem+'.check')).write_text(q.stdout+'\n'+q.stderr)
            assert q.returncode==0 and 's VERIFIED' in q.stdout,('INVALID_ORIGINAL_UNSAT_PROOF',stem)
            status='UNSAT_CERTIFIED'
        except subprocess.TimeoutExpired:status='UNSAT_CHECK_TIMEOUT'
        check_s=time.perf_counter()-tick;proof_hash=sha(proof)
    elif not killed and p.returncode not in (0,153,128+signal.SIGXFSZ,-signal.SIGXFSZ):
        raise RuntimeError(('SOLVER_PROCESS_ERROR',stem,p.returncode,err[-2000:]))
    stats={}
    for tag in ('DELTA2_JOIN','DELTA4X_STATS','DELTA_COOP1','X41_STATS','COOP52_GATE'):
        e=events(err,tag)
        assert len(e)<=1,('DUPLICATE_TELEMETRY',stem,tag)
        if e:stats[tag]=e[0]
    novel=0;causal_logged=0
    if arm in ('OFF','D4_FIXED','X_SHADOW','DELTA4X') and not killed and p.returncode in (0,10,20):
        st,novel,causal_logged=validate_events(err,cs)
        if arm in ('X_SHADOW','DELTA4X') and n<=1000000:
            assert st['math_enabled'],('MATHEMATICAL_MODULE_UNEXPECTEDLY_DISABLED',stem,n)
    elif arm=='D4_FROZEN':
        original={canon(c) for c in cs}
        for e in events(err,'DELTA3_LEMMA'):validate_lemma(e,original)
    # Save accepted original UNSAT proofs, and all stderr certificates/models.
    if proof.exists():
        if status in ('UNSAT_CERTIFIED','UNSAT_CHECK_TIMEOUT'):
            with proof.open('rb') as src,gzip.open(str(proof)+'.gz','wb') as dst:
                import shutil;shutil.copyfileobj(src,dst)
        proof.unlink()
    accepted=status in ('SAT_VERIFIED','UNSAT_CERTIFIED') and wall<=cap
    rss=cpu=None
    if usage.exists():
        for line in usage.read_text().splitlines():
            vals=line.split()
            if len(vals)==3:
                try:cpu=float(vals[0])+float(vals[1]);rss=int(vals[2])
                except ValueError:pass
    x=stats.get('DELTA4X_STATS',{})
    row={'id':s['id'],'sha256':s['sha256'],'family':s['family'],'arm':arm,'rep':rep,
         'status':status,'verified':accepted,'wall_e2e_s':wall,'proof_check_s':check_s,
         'wall_plus_check_s':wall+check_s,'PAR2_verified_s':wall if accepted else 2*cap,
         'returncode':p.returncode,'maxrss_kib':rss,'cpu_s':cpu,'proof_sha256':proof_hash,
         'x_installed':x.get('installed',0),'x_novel_original_clauses':novel,
         'x_actual_enqueues':x.get('actual_enqueues',0),'x_causal_logged':causal_logged,'stats':stats}
    emit('DELTA4X_TRIAL',{k:v for k,v in row.items() if k!='stats'})
    return row

def shard(index):
    assert 0<=index<SHARDS
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    src,digest=sources();protocol=json.load(open('delta4x_protocol.json'))
    assert protocol['binary_sha256']==hashes() and protocol['source_manifest_sha256']==digest
    selected=[s for s in src if s['shard']==index];assert len(selected)==5
    folder=Path(f'delta4x_shards/{index}');folder.mkdir(parents=True,exist_ok=False)
    save(folder/'manifest.json',dict(protocol,shard=index,one_cpu=sorted(os.sched_getaffinity(0))))
    rows=[]
    with (folder/'trials.jsonl').open('w') as f:
        for s in selected:
            for rep in range(REPS):
                order=list(ARMS);random.Random(int(s['sha256'][:16],16)+199*rep).shuffle(order)
                for arm in order:
                    row=sample(s,arm,rep,folder/'raw');rows.append(row)
                    f.write(json.dumps(row,sort_keys=True)+'\n');f.flush()
    assert len(rows)==70
    emit('DELTA4X_SHARD_PASS',{'shard':index,'trials':70,
         'installed':sum(r['x_installed'] for r in rows if r['arm']=='DELTA4X'),
         'actual_enqueues':sum(r['x_actual_enqueues'] for r in rows if r['arm']=='DELTA4X')})

def pilot():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    src,_=sources();rows=[]
    # Predeclared diagnostic sources, not used for selection or policy tuning.
    for s in src:
        if s['id'] in (0,14):
            for arm in ('D4_FIXED','X_SHADOW','DELTA4X'):
                rows.append(sample(s,arm,0,Path('delta4x_audit/real_pilot'),1.0))
    save('delta4x_audit/real_pilot.json',rows)
    emit('DELTA4X_REAL_PILOT_PASS',{'attempts':len(rows),'original_source_safety':True,'speed_claim':False})

def aggregate():
    src,digest=sources();rows=[];manifests=[]
    for i in range(SHARDS):
        p=Path(f'delta4x_downloads/delta4x-shard-{i}/delta4x_shards/{i}')
        manifests.append(json.load(open(p/'manifest.json')))
        rows += [json.loads(l) for l in (p/'trials.jsonl').read_text().splitlines()]
    expected={(s['sha256'],rep,arm) for s in src for rep in range(REPS) for arm in ARMS}
    actual=[(r['sha256'],r['rep'],r['arm']) for r in rows]
    assert len(rows)==len(set(actual))==840 and set(actual)==expected
    for m in manifests:
        assert m['source_manifest_sha256']==digest and m['binary_sha256']==manifests[0]['binary_sha256']
        assert m['cap_s']==CAP and m['reps']==REPS and tuple(m['arms'])==ARMS and len(m['one_cpu'])==1
    outcomes=collections.defaultdict(set)
    for r in rows:
        if r['status'] in ('SAT_VERIFIED','UNSAT_CERTIFIED'):outcomes[r['sha256']].add(r['status'])
    assert all(len(v)<=1 for v in outcomes.values()),'CONTRADICTORY_CERTIFIED_VERDICTS'
    totals={}
    for arm in ARMS:
        rr=[r for r in rows if r['arm']==arm]
        totals[arm]={'trials':len(rr),'verified':sum(r['verified'] for r in rr),
            'par2_verified_s':sum(r['PAR2_verified_s'] for r in rr),
            'independent_check_s':sum(r['proof_check_s'] for r in rr),
            'x_installed':sum(r['x_installed'] for r in rr),'x_novel':sum(r['x_novel_original_clauses'] for r in rr),
            'actual_enqueues':sum(r['x_actual_enqueues'] for r in rr),
            'sources_with_x_candidates':len({r['sha256'] for r in rr if r['stats'].get('DELTA4X_STATS',{}).get('guarded_candidates',0)>0}),
            'sources_with_x_insertion':len({r['sha256'] for r in rr if r['x_installed']>0}),
            'sources_with_x_use':len({r['sha256'] for r in rr if r['x_actual_enqueues']>0}),
            'module_disabled_trials':sum(r['stats'].get('COOP52_GATE',{}).get('algebra_disabled',False) for r in rr)}
    by={(r['sha256'],r['rep'],r['arm']):r for r in rows};comparisons={}
    for ref in ARMS:
        if ref=='DELTA4X':continue
        rng=random.Random(440414);gains=[]
        pair=[(sum(by[(s['sha256'],rep,ref)]['PAR2_verified_s'] for rep in range(REPS)),
               sum(by[(s['sha256'],rep,'DELTA4X')]['PAR2_verified_s'] for rep in range(REPS))) for s in src]
        for _ in range(2000):
            draw=rng.choices(pair,k=len(pair));old=sum(a for a,b in draw);new=sum(b for a,b in draw)
            gains.append(100*(old-new)/old)
        gains.sort();old=totals[ref]['par2_verified_s'];new=totals['DELTA4X']['par2_verified_s']
        comparisons[ref]={'gain_pct':100*(old-new)/old,'source_cluster_ci95_pct':[gains[49],gains[1949]],
                          'verified_delta':totals['DELTA4X']['verified']-totals[ref]['verified']}
    report={'status':'COMPLETE','sources':60,'attempts':840,'cap_s':CAP,'one_cpu':True,
            'retrospective':True,'blind_holdout':False,'promotion':False,'novel_math_claim':False,
            'fields':totals,'comparisons':comparisons,'manifest_sha256':digest,
            'binary_sha256':manifests[0]['binary_sha256']}
    save('delta4x_final/report.json',report);save('delta4x_final/trials.json',rows)
    emit('DELTA4X_FINAL',report)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('freeze','pilot','shard','aggregate'));p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.stage=='shard':shard(a.shard)
    else:globals()[a.stage]()
