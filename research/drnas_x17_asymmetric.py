#!/usr/bin/env python3
"""DRNAS X17: asymmetric learned-clause transfer; no simulated sharing.

CaDiCaL learner callback exports true learned clauses from unassumed scout on
identical original SHA. Only leader is credited; placebo has no import.
Reused X15 cohort is DEVELOPMENT, not a blind holdout.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import random
import resource
import signal
import subprocess
import tempfile
import time

import drnas_x16_singlecore_dual as x16
import mre_x11_placebo_causal as x11

ROOT=pathlib.Path('mre_x17')
DRIVER=ROOT/'bin'/'asymmetric'
CAP=12.0
SOLVER_CAP=11.55
SHARDS=8
REPS=2
ARMS=('native1','kissat1','cadical1','placebo2','asym2','asym3','asym1')
PROTO='DRNAS-X17-ASMM-ONE-WAY-LEARNER-16SHA-7ARM-2REP-12S-v1'
EXPECTED=16*REPS*len(ARMS)
PER_SHARD=EXPECTED//SHARDS

def need(ok,msg):
    if not ok:raise RuntimeError('X17_FAIL_CLOSED '+str(msg))

def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for part in iter(lambda:f.read(1<<20),b''):h.update(part)
    return h.hexdigest()

def configure():
    x16.ROOT=ROOT
    x11.ROOT=ROOT

def freeze():
    configure()
    need(DRIVER.is_file(),'compile driver before freezing sources')
    # Reuse X16's already frozen source-SHA checked X15 importer.
    x16.freeze()
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['expected_trials']==256 and len(m['cases'])==16,'upstream X16 freeze changed')
    m.update(protocol=PROTO,arms=list(ARMS),expected_trials=EXPECTED,
        per_shard=PER_SHARD,solver_cap_s=SOLVER_CAP,
        driver_sha256=digest(DRIVER),
        independent_LRAT=False,
        source_replay_not_blind=True,
        sender='CaDiCaL learner callback, no assumptions',
        receiver='incremental CaDiCaL leader, imports only at solve boundaries',
        asymmetric_scout_wins_not_counted=True,
        placebo_identical_scout_no_import=True,
        between_engines='one_way_scout_to_leader',
        control_cpu_mode='two logical CPUs with thread affinity, physical cores not proven',
        cpu_par2_policy='accepted: measured full child CPU; failure: 2*12s*logical_vcpus',
        no_auto_promotion=True,
        note='X17 does not have independent LRAT; original-model replay for SAT, independent backend agreement for UNSAT')
    save(ROOT/'manifest.json',m)
    verify()
    print('X17_FROZEN',json.dumps(dict(cases=16,trials=EXPECTED,arms=ARMS,driver_sha256=m['driver_sha256']),sort_keys=True),flush=True)

def verify():
    configure()
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and m['expected_trials']==EXPECTED and m['arms']==list(ARMS)
         and m['cap_s']==CAP and m['solver_cap_s']==SOLVER_CAP
         and len(m['cases'])==16 and m['per_shard']==PER_SHARD,'manifest protocol drift')
    need(DRIVER.is_file() and digest(DRIVER)==m['driver_sha256'],'driver SHA drift')
    need(x16.binaries()==m['backend_sha256'],'comparator binary drift')
    need(len(set(c['sha256'] for c in m['cases']))==16,'duplicate frozen original')
    for c in m['cases']:
        need((ROOT/c['filename']).is_file() and digest(ROOT/c['filename'])==c['sha256'],
             'source original SHA mismatch')
    need(len(x16.topology()['allowed'])>=2,'requires two guest logical CPUs')
    return m

def parse_driver(text,src,arm):
    head=[line for line in text.splitlines() if line.startswith('X17_RESULT ')]
    need(len(head)==1,'missing or repeated X17_RESULT')
    fields=dict(t.split('=',1) for t in head[0].split()[1:])
    need(fields.get('arm')==arm and fields.get('status') in ('SAT','UNSAT','TIMEOUT'),'invalid result header')
    for k in ('imported','exported','rejected','dropped','windows','scout_status','leader_cpu','scout_cpu'):
        fields[k]=int(fields[k])
    need(fields['imported']>=0 and fields['exported']>=0 and fields['imported']<=128,'bad transfer counters')
    if arm in ('cadical1','placebo2'):need(fields['imported']==0,'control imported learned clauses')
    if arm=='asym1':need(fields['leader_cpu']==fields['scout_cpu'],'one CPU violated')
    if arm in ('asym2','asym3','placebo2'):need(fields['leader_cpu']!=fields['scout_cpu'],'two CPUs violated')
    status=fields['status']
    if status=='SAT':
        model={}
        for line in text.splitlines():
            if line.startswith('v '):
                for lit in map(int,line.split()[1:]):
                    if lit:
                        need(abs(lit) not in model or model[abs(lit)]==(lit>0),'contradictory model')
                        model[abs(lit)]=lit>0
        need(model,'SAT returned empty witness')
        x11.x9.x6.x4.base.cms.verify_model(src,model)
    return status,fields

def run_driver(c,rep,arm):
    src=ROOT/c['filename']
    need(digest(src)==c['sha256'],'original source changed')
    seed=x11.seed(c,rep)
    top=x16.topology()
    cpu0,cpu1=top['first'],top['second']
    solo_cpu=arm in ('cadical1','asym1')
    affinity={cpu0} if solo_cpu else {cpu0,cpu1}
    start=time.perf_counter()
    ch0=x16.rusage_snapshot(resource.RUSAGE_CHILDREN)
    parent0=x16.rusage_snapshot(resource.RUSAGE_SELF)
    cmd=[str(DRIVER.resolve()),str(src.resolve()),arm,str(seed),str(SOLVER_CAP),str(cpu0),str(cpu1)]
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                          start_new_session=True,preexec_fn=lambda:os.sched_setaffinity(0,affinity))
    timed_out=False
    try:
        stdout,stderr=proc.communicate(timeout=max(.01,CAP-(time.perf_counter()-start)))
    except subprocess.TimeoutExpired:
        timed_out=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        stdout,stderr=proc.communicate()
    child=x16.counters_diff(ch0,x16.rusage_snapshot(resource.RUSAGE_CHILDREN))
    parent=x16.counters_diff(parent0,x16.rusage_snapshot(resource.RUSAGE_SELF))
    fields={}
    if not timed_out:
        need(proc.returncode==0,'driver failed '+str(proc.returncode)+': '+stderr[-500:])
        status,fields=parse_driver(stdout,src,arm)
    else:status='TIMEOUT'
    elapsed=time.perf_counter()-start
    if elapsed>CAP:status='TIMEOUT'
    return dict(protocol=PROTO,arm=arm,original_sha256=c['sha256'],gbd=c['gbd'],
         tier=c['previous_X15_tier'],rep=rep,seed=seed,status=status,
         SAT_original_witness_verified=status=='SAT',UNSAT_independent_LRAT=False,
         elapsed_s=round(elapsed,6),cap_s=CAP,
         PAR2_s=round(elapsed if status in ('SAT','UNSAT') else CAP*2,6),
         child_cpu_s=child['cpu_s'],parent_cpu_s=parent['cpu_s'],
         child_voluntary_ctx=child['voluntary'],child_involuntary_ctx=child['involuntary'],
         mode='one_logical' if solo_cpu else 'two_distinct_logical',
         cpu_affinity=sorted(affinity),
         exported=fields.get('exported',0),imported=fields.get('imported',0),
         rejected=fields.get('rejected',0),dropped=fields.get('dropped',0),
         windows=fields.get('windows',0),scout_status=fields.get('scout_status',0),
         hard_timeout=timed_out,selected_backend=('cadical' if status!='TIMEOUT' else None),
         scout_status_not_credited=True)

def run_trial(c,rep,arm):
    configure()
    need(arm in ARMS and rep in range(REPS),'invalid arm/rep')
    if arm not in ('native1','kissat1'):return run_driver(c,rep,arm)
    row=x16.run_trial(c,rep,arm)
    row['protocol']=PROTO
    row['mode']='one_logical'
    row['imported']=0;row['exported']=0;row['scout_status']=0
    row['scout_status_not_credited']=True
    return row

def selftest():
    need(EXPECTED==224 and PER_SHARD==28,'protocol count changed')
    configure();need(DRIVER.is_file(),'missing asymmetric driver')
    cp=x16.topology();cpu0,cpu1=cp['first'],cp['second']
    with tempfile.TemporaryDirectory() as td:
        sat=pathlib.Path(td)/'sat.cnf';unsat=pathlib.Path(td)/'unsat.cnf'
        sat.write_text('p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n')
        unsat.write_text('p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n')
        for src,expected in ((sat,'SAT'),(unsat,'UNSAT')):
            for arm in ('cadical1','placebo2','asym2','asym3','asym1'):
                cp=subprocess.run([str(DRIVER.resolve()),str(src),arm,'71','1.0',str(cpu0),str(cpu1)],
                   text=True,capture_output=True,timeout=3,check=True)
                status,_=parse_driver(cp.stdout,src,arm)
                need(status==expected,'selftest invalid result '+arm+': '+cp.stdout)
    print('X17_SELFTEST_PASS',flush=True)

def shard(idx):
    m=verify();need(0<=idx<SHARDS,'bad shard')
    chosen=[c for i,c in enumerate(m['cases']) if i%SHARDS==idx]
    need(len(chosen)==2,'shard source count drift')
    rows=[]
    for c in chosen:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(x11.seed(c,rep)).shuffle(arms)
            for arm in arms:
                row=run_trial(c,rep,arm)
                need(row['seed']==x11.seed(c,rep) and row['original_sha256']==c['sha256'],
                     'unpaired test')
                rows.append(row)
                save(ROOT/f'shard-{idx}.json',rows)
                print('X17_TRIAL',json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==PER_SHARD,'partial shard')
    print('X17_SHARD_PASS',idx,len(rows),flush=True)

def audit():
    m=verify()
    cases={c['sha256']:c for c in m['cases']}
    rows=[]
    for i in range(SHARDS):rows.extend(json.loads((ROOT/f'shard-{i}.json').read_text()))
    expected={(sha,rep,arm) for sha in cases for rep in range(REPS) for arm in ARMS}
    observed={(r['original_sha256'],r['rep'],r['arm']) for r in rows}
    need(len(rows)==len(observed)==EXPECTED and observed==expected,'missing or duplicate trials')
    for sha,c in cases.items():
        group=[r for r in rows if r['original_sha256']==sha]
        decisions={r['status'] for r in group if r['status'] in ('SAT','UNSAT')}
        need(len(decisions)<=1,'contradictory SAT/UNSAT on same original')
        independent={r.get('selected_backend') for r in group
                     if r['status']=='UNSAT' and r['arm'] in ('native1','kissat1','cadical1')}
        independent.discard(None)
        agreement=len(independent)>=2
        for r in group:
            need(r['protocol']==PROTO and r['gbd']==c['gbd'] and r['tier']==c['previous_X15_tier']
                 and r['seed']==x11.seed(c,r['rep']) and r['cap_s']==CAP,'header mismatch')
            need(r['status']!='SAT' or r['SAT_original_witness_verified'],'SAT not verified')
            need(r['status']!='TIMEOUT' or r['PAR2_s']==2*CAP,'incorrect timeout PAR2')
            need(r['status']=='TIMEOUT' or r['PAR2_s']==r['elapsed_s'],'incorrect solved PAR2')
            need(r['child_cpu_s']>=0 and r['parent_cpu_s']>=0,'invalid CPU metric')
            if r['arm'] in ('cadical1','placebo2'):
                need(r['imported']==0,'control contained transfers')
            r['accepted']=r['status']=='SAT' or (r['status']=='UNSAT' and agreement)
            r['audited_PAR2_s']=r['PAR2_s'] if r['accepted'] else 2*CAP
            cores=2 if r['arm'] in ('placebo2','asym2','asym3') else 1
            r['cpu_budget_PAR2_s']=(r['child_cpu_s'] if r['accepted'] else 2*CAP*cores)
    def score(sub):
        out={}
        for arm in ARMS:
            part=[r for r in sub if r['arm']==arm]
            out[arm]=dict(n=len(part),solved=sum(r['accepted'] for r in part),
              SAT_original_verified=sum(r['accepted'] and r['status']=='SAT' for r in part),
              UNSAT_reference_agreed=sum(r['accepted'] and r['status']=='UNSAT' for r in part),
              timeouts=sum(r['status']=='TIMEOUT' for r in part),
              wall_PAR2_s=round(sum(r['audited_PAR2_s'] for r in part),6),
              cpu_budget_PAR2_s=round(sum(r['cpu_budget_PAR2_s'] for r in part),6),
              child_cpu_s=round(sum(r['child_cpu_s'] for r in part),6),
              imported=sum(r['imported'] for r in part),
              exported=sum(r['exported'] for r in part))
        for arm in ARMS:
            for base in ('native1','cadical1','placebo2'):
                v=out[base]['wall_PAR2_s']
                out[arm]['wall_PAR2_change_pct_vs_'+base]=round(100*(1-out[arm]['wall_PAR2_s']/v),4)
                out[arm]['wall_speedup_vs_'+base]=round(v/out[arm]['wall_PAR2_s'],4)
                v=out[base]['cpu_budget_PAR2_s']
                out[arm]['cpu_PAR2_change_pct_vs_'+base]=round(100*(1-out[arm]['cpu_budget_PAR2_s']/v),4)
        return out
    report=dict(protocol=PROTO,case_count=16,trials=EXPECTED,blind_holdout=False,
      one_way_scout_to_leader=True,no_auto_promotion=True,UNSAT_independent_LRAT=False,
      cpu_PAR2_rule='failed: 2*wall_cap*logical_CPU_budget; solved: actual full child CPU',
      overall=score(rows),by_tier={tier:score([r for r in rows if r['tier']==tier]) for tier in ('development','holdout')},
      per_source=[dict(original_sha256=sha,gbd=c['gbd'],score=score([r for r in rows if r['original_sha256']==sha]))
                  for sha,c in cases.items()],rows=rows)
    save(ROOT/'report.json',report)
    print('X17_FINAL',json.dumps({k:v for k,v in report.items() if k not in ('per_source','rows')},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('freeze','verify','selftest','shard','audit'))
    p.add_argument('--shard',type=int,default=0)
    args=p.parse_args()
    if args.action=='freeze':freeze()
    elif args.action=='verify':verify();print('X17_VERIFY_PASS',flush=True)
    elif args.action=='selftest':selftest()
    elif args.action=='shard':shard(args.shard)
    else:audit()
if __name__=='__main__':main()
