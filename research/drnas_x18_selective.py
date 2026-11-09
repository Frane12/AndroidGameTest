#!/usr/bin/env python3
"""DRNAS X18: native CDCL phase forensics + one-way selective learned-clause tests.

X15 frozen replays (16) and eight new source-only official CNFs with explicit
X6fresh exclusion. Not globally blind (prior registry incomplete). Same CNFs,
two formula-paired seeds, capped E2E with model replay, strict PAR2 accounting.
Native 5000-conflict probes are separate bounded diagnostics, NEVER E2E scores.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import re
import resource
import signal
import subprocess
import tempfile
import time

import drnas_x16_singlecore_dual as x16
import drnas_x17_asymmetric as x17
import mre_x11_placebo_causal as x11

ROOT=pathlib.Path('mre_x18')
X6=pathlib.Path('mre_x6fresh')
DRIVER=ROOT/'bin'/'selective'
REPS=2
SHARDS=8
CAP=12.0
SOLVER_CAP=11.55
ARMS=('native1','kissat1','cadical1','placebo2','asym2','select2','select3')
PROTO='DRNAS-X18-SELECTIVE-LEARNER-24SHA-7ARM-2REP-12S-v1'
EXPECTED=24*REPS*len(ARMS)
PER_SHARD=EXPECTED//SHARDS

def need(ok,message):
    if not ok:raise RuntimeError('X18_FAIL_CLOSED '+str(message))

def save(p,object):
    p=pathlib.Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(object,sort_keys=True,indent=2)+'\n')

def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def configure():
    x16.ROOT=ROOT
    x17.ROOT=ROOT
    x17.DRIVER=DRIVER
    x11.ROOT=ROOT

def seed(c,rep):
    # Retain X17 paired seed on X15 and apply same deterministic map to X6.
    return x11.seed(c,rep)

def freeze():
    configure()
    need(DRIVER.is_file(),'X18 driver not built')
    # X17 freeze verifies and copies original X15 cohort and pinned binaries.
    x17.freeze()
    m=json.loads((ROOT/'manifest.json').read_text())
    need(len(m['cases'])==16 and m['expected_trials']==224,'X17 source freeze changed')
    # X6fresh is an EXCLUSION registry, not eight new sources:
    # X15 and X6fresh were observed to overlap in the first X18 attempt.
    m0=json.loads((X6/'manifest.json').read_text())
    need(len(m0['cases'])==8,'X6fresh registry source manifest changed')
    allcases=[]
    for c in m['cases']:
        entry=dict(c)
        entry['cohort']='x15_previous_'+c['previous_X15_tier']+'_reused'
        allcases.append(entry)
    excluded_sha={c['sha256'] for c in allcases}
    excluded_gbd={c['gbd'] for c in allcases}
    excluded_sha.update(c['sha256'] for c in m0['cases'])
    excluded_gbd.update(c['gbd'] for c in m0['cases'])
    # Deterministic, source-only selection from official Benchmark Database.
    # No solving, no outcome labels, no runtimes used for selection.
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as fetch
    import mre_x2_clause_order_causal as x2
    import hashlib
    years=('2021','2022','2023')
    salt='DRNAS-X18-SOURCE-ONLY-PRECOMMIT-20261109-v1'
    candidates=[]
    indexes={}
    for year in years:
        all_ids,sha_all=pool.getids('track=main_'+year)
        easy_ids,sha_easy=pool.getids('track=main_'+year+' and minisat1m=yes')
        need(len(all_ids)==400 and set(easy_ids)<=set(all_ids),
             'official source index invalid')
        indexes[year]=dict(all_sha256=sha_all,easy_sha256=sha_easy)
        candidates.extend((year,g) for g in easy_ids if g not in excluded_gbd)
    candidates=sorted(set(candidates),
        key=lambda x:hashlib.sha256((salt+'|'+x[0]+'|'+x[1]).encode()).hexdigest())
    trace=[]
    fetched=set()
    for year,gbd in candidates:
        if len(allcases)==24:break
        if gbd in excluded_gbd or gbd in fetched:continue
        fetched.add(gbd)
        need(len(fetched)<=100,'frozen source fetch budget exhausted')
        row=dict(gbd=gbd,year=year,selection='reject')
        dest=ROOT/(gbd+'.cnf')
        try:
            raw=fetch.get('https://benchmark-database.de/file/'+gbd,
                          12*1024*1024,seconds=20)
            plain,kind=fetch.prior.r32p.decode(raw)
            need(len(plain)<=12*1024*1024,'original CNF too large')
            nv,nc=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(nv<=12000 and nc<=85000 and nc>0,'source geometry cap')
            sha=hashlib.sha256(plain).hexdigest()
            need(sha not in excluded_sha,'prior original SHA excluded')
            dest.write_bytes(plain)
            n,clauses=x2.parse(dest)
            need(n==nv and len(clauses)==nc,'DIMACS parse mismatch')
            allcases.append(dict(filename=dest.name,sha256=sha,gbd=gbd,
              previous_X15_tier='new_sourceonly',cohort='x18_sourceonly_official_not_global_blind',
              x18_year=year,vars=nv,clauses=nc,bytes=len(plain)))
            excluded_sha.add(sha);excluded_gbd.add(gbd)
            row.update(selection='frozen_before_solver',sha256=sha,vars=nv,clauses=nc)
        except Exception as e:
            dest.unlink(missing_ok=True)
            row.update(selection='exclude_fetch_size_or_prior',reason=str(e)[:150])
        trace.append(row)
        print('X18_SOURCE',json.dumps(row,sort_keys=True),flush=True)
        save(ROOT/'source-selection-progress.json',dict(selected=len(allcases)-16,trace=trace,indexes=indexes))
    need(len(allcases)==24 and len({c['sha256'] for c in allcases})==24
         and len({c['gbd'] for c in allcases})==24,
         'not eight distinct new original sources')
    m.update(protocol=PROTO,arms=list(ARMS),cap_s=CAP,reps=REPS,
        per_shard=PER_SHARD,shards=SHARDS,expected_trials=EXPECTED,
        cases=allcases,solver_cap_s=SOLVER_CAP,
        driver_sha256=digest(DRIVER),
        x6_fresh_manifest_sha256=digest(X6/'manifest.json'),
        x6_fresh_run_id=42557116984,
        x18_sourceonly_selection_trace=trace,
        x18_indexes=indexes,
        x18_sourceonly_salt=salt,
        x18_prior_registries_nonexhaustive=True,
        source_replay_not_blind=True,
        blind_holdout=False,
        genuine_clause_transfer=True,
        policy='source-only opposite-polarity occurrence ranking; 64 total, 8 per round; select2 binary score>=14; select3 <=3 score>=22',
        original_x15_reused=16,new_sourceonly_official=8,
        native_probe='DRNAS_MAX_CONFLICTS=5000, diagnostic only, never PAR2',
        cpu_par2_failure_policy='2*12s*logical_cpu_budget',
        UNSAT_independent_LRAT=False,
        no_auto_promotion=True)
    save(ROOT/'manifest.json',m)
    verify()
    print('X18_FROZEN',json.dumps(dict(sources=len(allcases),trials=EXPECTED,
         driver_sha256=m['driver_sha256'],origin_counts=dict(x15_reused=16,x18_sourceonly_new=8)),sort_keys=True),flush=True)

def verify():
    configure()
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and m['arms']==list(ARMS) and m['reps']==REPS
         and m['cap_s']==CAP and m['solver_cap_s']==SOLVER_CAP
         and m['expected_trials']==EXPECTED and m['per_shard']==PER_SHARD
         and len(m['cases'])==24,'X18 protocol drift')
    need(DRIVER.is_file() and digest(DRIVER)==m['driver_sha256'],'X18 compiled binary SHA drift')
    need(x16.binaries()==m['backend_sha256'],'pinned CMS/Kissat baseline changed')
    need(len({c['gbd'] for c in m['cases']})==24 and
         len({c['sha256'] for c in m['cases']})==24,'source duplicates')
    for c in m['cases']:
        need((ROOT/c['filename']).is_file() and
             digest(ROOT/c['filename'])==c['sha256'],'frozen original CNF changed')
    need(len(x16.topology()['allowed'])>=2,'two logical CPUs unavailable')
    return m

def extra_native(stdout):
    detail={}
    for line in stdout.splitlines():
        if line.startswith('R195_RESULT '):
            for k,v in re.findall(r'([a-z_]+)=([A-Za-z0-9_]+)',line):
                if k in ('conflicts','decisions','propagations'):detail[k]=int(v)
                if k=='status':detail['reported_status']=v
        elif line.startswith('MRE_X3_STAGE '):
            detail['stage']=json.loads(line.split(' ',1)[1])
        elif line.startswith('MRE10_GATE '):
            gate=json.loads(line.split(' ',1)[1])
            need(gate['mode']=='x_native' and gate['applied'] is False,'CMS native CNF transformed')
            detail['gate']=gate
    return detail

def environment():
    env=os.environ.copy()
    for k in ('DRNAS_MAX_CONFLICTS','DRNAS_X7_TRACE','DRNAS_X8_TRACE'):
        env.pop(k,None)
    return env

def baseline(c,rep,arm):
    configure()
    src=ROOT/c['filename']
    need(digest(src)==c['sha256'],'source SHA mismatch before trial')
    backend='native' if arm=='native1' else 'kissat'
    top=x16.topology()
    begin=time.perf_counter()
    before=x16.rusage_snapshot(resource.RUSAGE_CHILDREN)
    pbefore=x16.rusage_snapshot(resource.RUSAGE_SELF)
    cmd=x16.command(backend,src,seed(c,rep))
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
          text=True,errors='replace',start_new_session=True,env=environment(),
          preexec_fn=lambda:os.sched_setaffinity(0,{top['first']}))
    hard_timeout=False
    try:out,err=proc.communicate(timeout=max(.01,CAP-(time.perf_counter()-begin)-.02))
    except subprocess.TimeoutExpired:
        hard_timeout=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,err=proc.communicate()
    status='TIMEOUT'
    stats={}
    if not hard_timeout:
        status=x16.x14.outcome_of(backend,proc.returncode,out,err,src)
        if backend=='native':
            stats=extra_native(out)
            need(stats.get('reported_status')==status,'CMS status/stats mismatch')
    elapsed=time.perf_counter()-begin
    if elapsed>CAP or status not in ('SAT','UNSAT'):status='TIMEOUT'
    child=x16.counters_diff(before,x16.rusage_snapshot(resource.RUSAGE_CHILDREN))
    parent=x16.counters_diff(pbefore,x16.rusage_snapshot(resource.RUSAGE_SELF))
    return dict(protocol=PROTO,original_sha256=c['sha256'],gbd=c['gbd'],
      cohort=c['cohort'],rep=rep,seed=seed(c,rep),arm=arm,status=status,
      selected_backend=backend if status in ('SAT','UNSAT') else None,
      SAT_original_witness_verified=status=='SAT',
      UNSAT_independent_LRAT=False,elapsed_s=round(elapsed,6),
      cap_s=CAP,PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),
      child_cpu_s=child['cpu_s'],parent_cpu_s=parent['cpu_s'],
      child_voluntary_ctx=child['voluntary'],child_involuntary_ctx=child['involuntary'],
      cpu_affinity=[top['first']],mode='one_logical',
      native_mechanism=stats,hard_timeout=hard_timeout,
      imported=0,exported=0,scout_status=0,scout_status_not_credited=True)

def parse_driver(raw,src,arm):
    # Reuse X17's SAT original-CNF model replayer, with X18's independent tag.
    lines=raw.splitlines()
    need(sum(line.startswith('X18_RESULT ') for line in lines)==1,'not exactly one driver result')
    legacy=raw.replace('X18_RESULT ','X17_RESULT ',1)
    status,fields=x17.parse_driver(legacy,src,arm)
    if arm in ('select2','select3'):
        need(fields['imported']<=64,'selective max 64 imports')
    return status,fields

def run_driver(c,rep,arm):
    configure()
    src=ROOT/c['filename']
    need(digest(src)==c['sha256'],'source SHA mismatch before driver trial')
    cp=x16.topology();cpu0,cpu1=cp['first'],cp['second']
    affinity={cpu0} if arm=='cadical1' else {cpu0,cpu1}
    before=x16.rusage_snapshot(resource.RUSAGE_CHILDREN)
    pbefore=x16.rusage_snapshot(resource.RUSAGE_SELF)
    start=time.perf_counter()
    cmd=[str(DRIVER.resolve()),str(src.resolve()),arm,str(seed(c,rep)),
         str(SOLVER_CAP),str(cpu0),str(cpu1)]
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
              text=True,errors='replace',env=environment(),start_new_session=True,
              preexec_fn=lambda:os.sched_setaffinity(0,affinity))
    hard_timeout=False
    try:out,err=proc.communicate(timeout=max(.01,CAP-(time.perf_counter()-start)-.02))
    except subprocess.TimeoutExpired:
        hard_timeout=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,err=proc.communicate()
    fields={}
    status='TIMEOUT'
    if not hard_timeout:
        need(proc.returncode==0,'X18 driver failed: '+err[-500:])
        status,fields=parse_driver(out,src,arm)
    elapsed=time.perf_counter()-start
    if elapsed>CAP:status='TIMEOUT'
    child=x16.counters_diff(before,x16.rusage_snapshot(resource.RUSAGE_CHILDREN))
    parent=x16.counters_diff(pbefore,x16.rusage_snapshot(resource.RUSAGE_SELF))
    return dict(protocol=PROTO,original_sha256=c['sha256'],gbd=c['gbd'],
      cohort=c['cohort'],rep=rep,seed=seed(c,rep),arm=arm,status=status,
      selected_backend='cadical' if status in ('SAT','UNSAT') else None,
      SAT_original_witness_verified=status=='SAT',UNSAT_independent_LRAT=False,
      elapsed_s=round(elapsed,6),cap_s=CAP,
      PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),
      child_cpu_s=child['cpu_s'],parent_cpu_s=parent['cpu_s'],
      child_voluntary_ctx=child['voluntary'],child_involuntary_ctx=child['involuntary'],
      cpu_affinity=sorted(affinity),mode='one_logical' if arm=='cadical1' else 'two_distinct_logical',
      imported=fields.get('imported',0),exported=fields.get('exported',0),
      rejected=fields.get('rejected',0),dropped=fields.get('dropped',0),
      windows=fields.get('windows',0),scout_status=fields.get('scout_status',0),
      hard_timeout=hard_timeout,scout_status_not_credited=True)

def native_probe(c):
    # Causal hypothesis diagnostic, NOT an E2E trial and never scored as one.
    configure();src=ROOT/c['filename']
    need(digest(src)==c['sha256'],'probe source SHA drift')
    top=x16.topology()
    env=environment();env['DRNAS_MAX_CONFLICTS']='5000'
    start=time.perf_counter()
    cmd=x16.command('native',src,seed(c,0))
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
          errors='replace',env=env,start_new_session=True,
          preexec_fn=lambda:os.sched_setaffinity(0,{top['first']}))
    try:out,err=proc.communicate(timeout=3.0);hard_timeout=False
    except subprocess.TimeoutExpired:
        hard_timeout=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,err=proc.communicate()
    stats=extra_native(out) if not hard_timeout and proc.returncode==0 else {}
    return dict(original_sha256=c['sha256'],gbd=c['gbd'],cohort=c['cohort'],
        diagnostic_only=True,conflict_cap=5000,wall_s=round(time.perf_counter()-start,6),
        timeout=hard_timeout,stats=stats)

def selftest():
    configure()
    need(EXPECTED==336 and PER_SHARD==42 and SHARDS==8,'matrix dimensions drift')
    need(DRIVER.is_file(),'missing compiled X18 driver')
    topo=x16.topology()
    with tempfile.TemporaryDirectory() as td:
        sat=pathlib.Path(td)/'sat.cnf'
        unsat=pathlib.Path(td)/'unsat.cnf'
        sat.write_text('p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n')
        unsat.write_text('p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n')
        for src,expected in ((sat,'SAT'),(unsat,'UNSAT')):
            for arm in ('cadical1','placebo2','asym2','select2','select3'):
                cmd=[str(DRIVER.resolve()),str(src),arm,'71','1.0',str(topo['first']),str(topo['second'])]
                r=subprocess.run(cmd,capture_output=True,text=True,timeout=4,check=True,env=environment())
                status,fields=parse_driver(r.stdout,src,arm)
                need(status==expected,'solver selftest wrong: '+arm)
                if arm=='placebo2':need(fields['imported']==0,'placebo import in selftest')
    print('X18_SELFTEST_PASS',flush=True)

def shard(index):
    m=verify();need(0<=index<SHARDS,'shard index out of range')
    chosen=[c for i,c in enumerate(m['cases']) if i%SHARDS==index]
    need(len(chosen)==3,'expected three sources per shard')
    rows=[];probes=[]
    for c in chosen:
        probe=native_probe(c)
        probes.append(probe)
        save(ROOT/f'probe-shard-{index}.json',probes)
        print('X18_BOUNDED_DIAGNOSTIC_ONLY',json.dumps(probe,sort_keys=True),flush=True)
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(seed(c,rep)).shuffle(order)
            for arm in order:
                row=(baseline(c,rep,arm) if arm in ('native1','kissat1')
                     else run_driver(c,rep,arm))
                need(row['original_sha256']==c['sha256'] and row['seed']==seed(c,rep),
                     'source/seed pairing mismatch')
                rows.append(row)
                save(ROOT/f'shard-{index}.json',rows)
                print('X18_TRIAL',json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==PER_SHARD and len(probes)==3,'incomplete shard')
    print('X18_SHARD_PASS',index,PER_SHARD,flush=True)

def audit():
    m=verify()
    cases={c['sha256']:c for c in m['cases']}
    rows=[];probes=[]
    for i in range(SHARDS):
        rows.extend(json.loads((ROOT/f'shard-{i}.json').read_text()))
        p=json.loads((ROOT/f'probe-shard-{i}.json').read_text())
        need(len(p)==3,'missing bounded diagnostic')
        probes+=p
    expected={(sha,rep,arm) for sha in cases for rep in range(REPS) for arm in ARMS}
    observed={(r['original_sha256'],r['rep'],r['arm']) for r in rows}
    need(len(rows)==EXPECTED and len(observed)==EXPECTED and observed==expected,
         'missing, duplicated or unmatched trials')
    need(len(probes)==24 and {p['original_sha256'] for p in probes}==set(cases),
         'diagnostic per-source roster mismatch')
    for sha,c in cases.items():
        group=[r for r in rows if r['original_sha256']==sha]
        verdicts={r['status'] for r in group if r['status'] in ('SAT','UNSAT')}
        need(len(verdicts)<=1,'cross-solver SAT/UNSAT contradiction')
        independent={r['selected_backend'] for r in group
          if r['status']=='UNSAT' and r['arm'] in ('native1','kissat1','cadical1')}
        independent.discard(None)
        agreement=len(independent)>=2
        for r in group:
            need(r['protocol']==PROTO and r['gbd']==c['gbd'] and r['cohort']==c['cohort']
               and r['seed']==seed(c,r['rep']) and r['cap_s']==CAP,'trial header/seed mismatch')
            need(r['status']!='SAT' or r['SAT_original_witness_verified'],
                 'SAT witness invalid or unverified')
            need(r['status']!='TIMEOUT' or r['PAR2_s']==CAP*2,
                 'wrong PAR2 on timeout')
            need(r['status']=='TIMEOUT' or r['PAR2_s']==r['elapsed_s'],
                 'wrong PAR2 on success')
            need(r['child_cpu_s']>=0 and r['parent_cpu_s']>=0,'negative CPU resource')
            if r['arm']=='placebo2':need(r['imported']==0,'placebo imported clauses')
            if r['arm'].startswith('select'):need(r['imported']<=64,
                 'selective exceeded import limit')
            if r['arm'] in ('native1','kissat1','cadical1'):
                need(len(r['cpu_affinity'])==1,'single core CPU affinity violated')
            else:need(len(r['cpu_affinity'])==2,'two core CPU affinity violated')
            r['accepted']=r['status']=='SAT' or (r['status']=='UNSAT' and agreement)
            r['audited_PAR2_s']=r['PAR2_s'] if r['accepted'] else 2*CAP
            logical=1 if r['arm'] in ('native1','kissat1','cadical1') else 2
            r['cpu_budget_PAR2_s']=r['child_cpu_s'] if r['accepted'] else 2*CAP*logical
    def score(sub):
        out={}
        for arm in ARMS:
            g=[r for r in sub if r['arm']==arm]
            out[arm]=dict(n=len(g),solved=sum(r['accepted'] for r in g),
              SAT_original_verified=sum(r['accepted'] and r['status']=='SAT' for r in g),
              UNSAT_reference_agreed=sum(r['accepted'] and r['status']=='UNSAT' for r in g),
              timeouts=sum(r['status']=='TIMEOUT' for r in g),
              wall_PAR2_s=round(sum(r['audited_PAR2_s'] for r in g),6),
              cpu_budget_PAR2_s=round(sum(r['cpu_budget_PAR2_s'] for r in g),6),
              child_cpu_s=round(sum(r['child_cpu_s'] for r in g),6),
              imported=sum(r['imported'] for r in g),exported=sum(r['exported'] for r in g))
        for arm in ARMS:
            for base in ('native1','cadical1','placebo2','asym2'):
                for key,prefix in (('wall_PAR2_s','wall'),('cpu_budget_PAR2_s','cpu')):
                    num=out[base][key];den=out[arm][key]
                    out[arm][prefix+'_speedup_vs_'+base]=round(num/den,5) if den else None
                    out[arm][prefix+'_pct_lower_vs_'+base]=round(100*(1-den/num),4) if num else None
        return out
    cohorts=sorted({c['cohort'] for c in m['cases']})
    report=dict(protocol=PROTO,sources=24,trials=EXPECTED,
      blind_holdout=False,no_auto_promotion=True,
      UNSAT_independent_LRAT=False,scout_outcomes_never_credited=True,
      native_bounded_probes_not_PAR2=True,
      cpu_PAR2_rule='solved: actual child CPU; unaccepted: 2*12s*allowed_logical_cores',
      overall=score(rows),by_cohort={co:score([r for r in rows if r['cohort']==co]) for co in cohorts},
      per_source=[dict(sha256=sha,gbd=c['gbd'],cohort=c['cohort'],
         score=score([r for r in rows if r['original_sha256']==sha]))
         for sha,c in cases.items()],
      probes=probes,rows=rows)
    save(ROOT/'report.json',report)
    print('X18_FINAL',json.dumps({k:v for k,v in report.items()
           if k not in ('per_source','probes','rows')},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('selftest','freeze','verify','shard','audit'))
    p.add_argument('--shard',type=int,default=0)
    args=p.parse_args()
    if args.action=='selftest':selftest()
    elif args.action=='freeze':freeze()
    elif args.action=='verify':verify();print('X18_VERIFY_PASS',flush=True)
    elif args.action=='shard':shard(args.shard)
    else:audit()

if __name__=='__main__':main()
