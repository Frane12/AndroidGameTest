#!/usr/bin/env python3
"""X20: independent source-only transfer test, same unmodified X18 binary.

Freeze 24 official SHA-unique CNF formulas before solving, excluding
all original X15, X6fresh, X18 and X19 frozen CNF SHA. No outcome-based
screening. Prior global registry is NOT exhaustive; do not call this a
guaranteed globally blind holdout.

Compare E2E Native1, Kissat1, CaDiCaL1 (one logical core), placebo2,
asym2, select2 (two logical cores); same 12s cap and SHA/seed pairs.
Bounded 5000-conflict native traces are separately labeled diagnostics.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import subprocess
import tempfile

import drnas_x18_selective as parent
import drnas_x16_singlecore_dual as x16

ROOT=pathlib.Path('mre_x20')
DRIVER=ROOT/'bin'/'selective'
X18_PRIOR=pathlib.Path('mre_x18/manifest.json')
X6_PRIOR=pathlib.Path('mre_x6fresh/manifest.json')
X19_PRIOR=pathlib.Path('mre_x19/manifest.json')
CAP=12.0
SOLVER_CAP=11.55
REPS=2
SHARDS=8
TARGET=24
ARMS=('native1','kissat1','cadical1','placebo2','asym2','select2')
PROTO='DRNAS-X20-SELECT2-TRANSFER-24SHA-6ARM-2REP-12S-v1'
EXPECTED=TARGET*REPS*len(ARMS)
PER_SHARD=EXPECTED//SHARDS
YEARS=('2021','2022','2023')
SALT='DRNAS-X20-20261109-FROZEN-24SOURCE-STRATIFIED-A'
PINNED_X18_RUN=42579485596

def need(ok,msg):
    if not ok:raise RuntimeError('X20_FAIL_CLOSED '+str(msg))

def save(path,obj):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')

def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for data in iter(lambda:f.read(1<<20),b''):h.update(data)
    return h.hexdigest()

def setup():
    # Reuse the EXACT verified X18 runner, seed policy, witness auditor,
    # strict Linux CPU pinning and two-way reference UNSAT checking.
    parent.ROOT=ROOT
    parent.DRIVER=DRIVER
    parent.PROTO=PROTO
    parent.CAP=CAP
    parent.SOLVER_CAP=SOLVER_CAP
    parent.REPS=REPS
    parent.SHARDS=SHARDS
    parent.ARMS=ARMS
    parent.EXPECTED=EXPECTED
    parent.PER_SHARD=PER_SHARD
    parent.configure()

def seed(case,rep):
    return parent.seed(case,rep)

def features(cnf):
    import mre_x2_clause_order_causal as x2
    n,clauses=x2.parse(cnf)
    m=len(clauses)
    counts=collections.Counter(l for clause in clauses for l in clause)
    binary=sum(len(c)==2 for c in clauses)
    horn=sum(sum(lit>0 for lit in c)<=1 for c in clauses)
    unit=sum(len(c)==1 for c in clauses)
    both=sum(counts[v]>0 and counts[-v]>0 for v in range(1,n+1))
    return dict(vars=n,clauses=m,
       mean_clause_width=round(sum(len(c) for c in clauses)/max(1,m),6),
       binary_clause_ratio=round(binary/max(1,m),6),
       horn_clause_ratio=round(horn/max(1,m),6),
       unit_clause_ratio=round(unit/max(1,m),6),
       both_polarity_vars_ratio=round(both/max(1,n),6),
       binary_class='binary_dense' if binary/max(1,m)>=.2 else 'binary_sparse',
       horn_class='horn_dominant' if horn/max(1,m)>=.75 else 'horn_other')

def freeze():
    setup()
    ROOT.mkdir(parents=True,exist_ok=True)
    need(DRIVER.is_file(),'original X18 asymmetric driver missing')
    prior=json.loads(X18_PRIOR.read_text())
    x6=json.loads(X6_PRIOR.read_text())
    prior19=json.loads(X19_PRIOR.read_text())
    need(prior['expected_trials']==336 and len(prior['cases'])==24,
         'X18 original prior roster changed')
    need(len(x6['cases'])==8,'X6 original prior roster changed')
    need(prior19['expected_trials']==144 and len(prior19['cases'])==12,'X19 prior roster changed')
    need(digest(DRIVER)==prior['driver_sha256'],
         'X20 must reuse exact X18 learner binary')
    need(x16.binaries()==prior['backend_sha256'],
         'frozen CMS/Kissat/CaDiCaL binary SHA drift')
    excluded_sha=({c['sha256'] for c in prior['cases']}|
                  {c['sha256'] for c in x6['cases']}|
                  {c['sha256'] for c in prior19['cases']})
    excluded_gbd=({c['gbd'] for c in prior['cases']}|
                  {c['gbd'] for c in x6['cases']}|
                  {c['gbd'] for c in prior19['cases']})
    # This registers X15 too: the X18 manifest includes all 16 X15 originals.
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as fetch
    indexes={}
    candidate=[]
    for year in YEARS:
        ids,mainsha=pool.getids('track=main_'+year)
        easy,sha=pool.getids('track=main_'+year+' and minisat1m=yes')
        need(len(ids)==400 and set(easy)<=set(ids),'official index changed')
        indexes[year]=dict(main_index_sha256=mainsha,
                           easy_index_sha256=sha,eligible_total=len(easy))
        candidate.extend((year,gbd) for gbd in easy if gbd not in excluded_gbd)
    candidate=sorted(set(candidate),
      key=lambda z:hashlib.sha256((SALT+'|'+z[0]+'|'+z[1]).encode()).hexdigest())
    cases=[];trace=[];tried=set()
    binary_quota=collections.Counter()
    year_quota=collections.Counter()
    for year,gbd in candidate:
        if len(cases)==TARGET:break
        if gbd in tried or gbd in excluded_gbd:continue
        tried.add(gbd)
        need(len(tried)<=260,'frozen source scan limit reached before 24 sources')
        path=ROOT/(gbd+'.cnf')
        row=dict(gbd=gbd,year=year)
        try:
            raw=fetch.get('https://benchmark-database.de/file/'+gbd,
                          12*1024*1024,seconds=20)
            plain,_compression=fetch.prior.r32p.decode(raw)
            need(len(plain)<=12*1024*1024,'source byte cap')
            n,k=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(0<n<=12000 and 0<k<=85000,'source geometry cap')
            d=hashlib.sha256(plain).hexdigest()
            need(d not in excluded_sha,'previous CNF SHA registered')
            path.write_bytes(plain)
            f=features(path)
            need(f['vars']==n and f['clauses']==k,'malformed DIMACS')
            need(binary_quota[f['binary_class']]<12,
                 'source-only binary-density stratum full')
            need(year_quota[year]<12,'source-only year quota full')
            entry=dict(filename=path.name,sha256=d,gbd=gbd,year=year,
                cohort='x20_sourceonly_new',structure=f,bytes=len(plain))
            cases.append(entry)
            binary_quota[f['binary_class']]+=1
            year_quota[year]+=1
            excluded_sha.add(d);excluded_gbd.add(gbd)
            row.update(selection='pre_solver_freeze',sha256=d,
                       binary_class=f['binary_class'],
                       binary_ratio=f['binary_clause_ratio'],
                       horn_ratio=f['horn_clause_ratio'])
        except Exception as e:
            path.unlink(missing_ok=True)
            row.update(selection='excluded_source_only_fetch_size_prior',
                       reason=str(e)[:150])
        trace.append(row)
        print('X20_SOURCE',json.dumps(row,sort_keys=True),flush=True)
        save(ROOT/'selection-progress.json',
             dict(salt=SALT,selected=len(cases),trace=trace,indexes=indexes))
    need(len(cases)==TARGET and len({c['sha256'] for c in cases})==TARGET
         and len({c['gbd'] for c in cases})==TARGET,
         'not exactly twenty-four registry-disjoint original CNFs')
    need(binary_quota['binary_dense']==12 and binary_quota['binary_sparse']==12,
         'binary strata must be balanced 12/12')
    manifest=dict(protocol=PROTO,cases=cases,arms=list(ARMS),
       cap_s=CAP,solver_cap_s=SOLVER_CAP,reps=REPS,shards=SHARDS,
       expected_trials=EXPECTED,per_shard=PER_SHARD,
       driver_sha256=digest(DRIVER),
       backend_sha256=prior['backend_sha256'],
       previous_X18_manifest_sha256=digest(X18_PRIOR),
       previous_X6_manifest_sha256=digest(X6_PRIOR),
       previous_X19_manifest_sha256=digest(X19_PRIOR),
       sourceonly_binary_density_quota_per_class=12,
       sourceonly_year_counts=dict(year_quota),
       source_indexes=indexes,selection_salt=SALT,selection_trace=trace,
       source_only_precommitted=True,
       registered_X15_X6_X18_X19_source_SHA_excluded=True,
       global_prior_registry_exhaustive=False,
       blind_holdout=False,
       unchanged_X18_driver_binary=True,
       no_auto_promotion=True,
       UNSAT_independent_LRAT=False,
       cpu_PAR2_failure_budget='2*12s*logical_cpu_count',
       native_probe_is_not_E2E=True)
    save(ROOT/'manifest.json',manifest)
    verify()
    print('X20_FROZEN',json.dumps(
       dict(sources=len(cases),trials=EXPECTED,
            official_years=dict(collections.Counter(c['year'] for c in cases)),
            driver_sha256=manifest['driver_sha256']),sort_keys=True),flush=True)

def verify():
    setup()
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and len(m['cases'])==TARGET
         and m['arms']==list(ARMS) and m['expected_trials']==EXPECTED
         and m['per_shard']==PER_SHARD and m['cap_s']==CAP
         and m['solver_cap_s']==SOLVER_CAP,'manifest protocol drift')
    need(DRIVER.is_file() and digest(DRIVER)==m['driver_sha256'],
         'learned-clause executable changed')
    need(x16.binaries()==m['backend_sha256'],
         'reference backend binary drift')
    need(len({c['sha256'] for c in m['cases']})==TARGET and
         len({c['gbd'] for c in m['cases']})==TARGET,'duplicate original')
    for c in m['cases']:
        path=ROOT/c['filename']
        need(path.is_file() and digest(path)==c['sha256'],'original source SHA drift')
        need(features(path)==c['structure'],'structural feature drift')
    return m

def selftest():
    setup()
    need(EXPECTED==288 and PER_SHARD==36 and SHARDS==8,'trial matrix count')
    need(DRIVER.is_file(),'driver not restored')
    cp=x16.topology()
    with tempfile.TemporaryDirectory() as d:
        sat=pathlib.Path(d)/'sat.cnf'
        unsat=pathlib.Path(d)/'unsat.cnf'
        sat.write_text('p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n')
        unsat.write_text('p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n')
        for cnf,expected in ((sat,'SAT'),(unsat,'UNSAT')):
            for arm in ('cadical1','placebo2','asym2','select2'):
                command=[str(DRIVER.resolve()),str(cnf),arm,'71','1.0',
                          str(cp['first']),str(cp['second'])]
                result=subprocess.run(command,text=True,capture_output=True,
                        timeout=4,check=True,env=parent.environment())
                status,metadata=parent.parse_driver(result.stdout,cnf,arm)
                need(status==expected,'toy '+arm+' result invalid')
                if arm=='placebo2':need(metadata['imported']==0,'placebo imported')
    print('X20_SELFTEST_PASS',flush=True)

def trial(c,rep,arm):
    setup()
    if arm in ('native1','kissat1'):
        return parent.baseline(c,rep,arm)
    return parent.run_driver(c,rep,arm)

def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,'shard index')
    selected=[c for i,c in enumerate(m['cases']) if i%SHARDS==idx]
    need(len(selected)==3,'three source originals per shard')
    rows=[];probes=[]
    for c in selected:
        p=parent.native_probe(c)
        probes.append(p)
        save(ROOT/('probe-shard-%d.json'%idx),probes)
        print('X20_BOUNDED_DIAGNOSTIC_ONLY',json.dumps(p,sort_keys=True),flush=True)
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(seed(c,rep)).shuffle(order)
            for arm in order:
                r=trial(c,rep,arm)
                need(r['protocol']==PROTO and
                     r['original_sha256']==c['sha256'] and
                     r['seed']==seed(c,rep),'paired trial mismatch')
                rows.append(r)
                save(ROOT/('shard-%d.json'%idx),rows)
                print('X20_TRIAL',json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==PER_SHARD and len(probes)==3,'incomplete shard')
    print('X20_SHARD_PASS',idx,PER_SHARD,flush=True)

def audit():
    m=verify()
    bysha={c['sha256']:c for c in m['cases']}
    rows=[];probes=[]
    for i in range(SHARDS):
        rows+=json.loads((ROOT/('shard-%d.json'%i)).read_text())
        pp=json.loads((ROOT/('probe-shard-%d.json'%i)).read_text())
        need(len(pp)==3,'missing source probe')
        probes+=pp
    exp={(s,rep,arm) for s in bysha for rep in range(REPS) for arm in ARMS}
    obs={(r['original_sha256'],r['rep'],r['arm']) for r in rows}
    need(len(rows)==len(obs)==EXPECTED and obs==exp,'missing/duplicate paired E2E trials')
    need(len(probes)==TARGET and
         {p['original_sha256'] for p in probes}==set(bysha),'missing bounded diagnostics')
    for sha,c in bysha.items():
        group=[r for r in rows if r['original_sha256']==sha]
        verdicts={r['status'] for r in group if r['status'] in ('SAT','UNSAT')}
        need(len(verdicts)<=1,'conflicting solver verdicts')
        backs={r['selected_backend'] for r in group
               if r['status']=='UNSAT' and r['arm'] in ('native1','kissat1','cadical1')}
        backs.discard(None)
        independent_unsat=len(backs)>=2
        for r in group:
            need(r['protocol']==PROTO and r['gbd']==c['gbd']
                 and r['cohort']==c['cohort'] and r['seed']==seed(c,r['rep'])
                 and r['cap_s']==CAP and r['status'] in ('SAT','UNSAT','TIMEOUT'),
                 'unpaired or invalid result')
            need(r['status']!='SAT' or r['SAT_original_witness_verified'],
                 'SAT original witness not checked')
            need(r['status']!='TIMEOUT' or r['PAR2_s']==2*CAP,
                 'incorrect timeout PAR2')
            need(r['status']=='TIMEOUT' or r['PAR2_s']==r['elapsed_s'],
                 'incorrect solved PAR2')
            need(r['child_cpu_s']>=0,'negative CPU')
            need(r['arm']!='placebo2' or r['imported']==0,'placebo transferred clauses')
            if r['arm']=='select2':need(r['imported']<=64,'select2 import exceeded')
            cpus=1 if r['arm'] in ('native1','kissat1','cadical1') else 2
            need(len(r['cpu_affinity'])==cpus,'not expected pinned CPU budget')
            r['accepted']=r['status']=='SAT' or (r['status']=='UNSAT' and independent_unsat)
            r['audited_PAR2_s']=r['PAR2_s'] if r['accepted'] else CAP*2
            r['cpu_budget_PAR2_s']=r['child_cpu_s'] if r['accepted'] else 2*CAP*cpus
    def score(sub):
        out={}
        for arm in ARMS:
            g=[r for r in sub if r['arm']==arm]
            out[arm]=dict(n=len(g),
                solved=sum(bool(r['accepted']) for r in g),
                SAT_verified=sum(bool(r['accepted']) and r['status']=='SAT' for r in g),
                UNSAT_backend_agreement=sum(bool(r['accepted']) and r['status']=='UNSAT' for r in g),
                unverified_UNSAT=sum(r['status']=='UNSAT' and not r['accepted'] for r in g),
                timeouts=sum(r['status']=='TIMEOUT' for r in g),
                wall_PAR2_s=round(sum(r['audited_PAR2_s'] for r in g),6),
                cpu_budget_PAR2_s=round(sum(r['cpu_budget_PAR2_s'] for r in g),6),
                actual_child_cpu_s=round(sum(r['child_cpu_s'] for r in g),6),
                imported=sum(r.get('imported',0) for r in g),
                exported=sum(r.get('exported',0) for r in g))
        for arm in ARMS:
            for ref in ('placebo2','asym2','native1','kissat1'):
                for name in ('wall_PAR2_s','cpu_budget_PAR2_s'):
                    refv=out[ref][name];v=out[arm][name]
                    out[arm][name+'_pct_lower_vs_'+ref]=round(100*(1-v/refv),4) if refv else None
                    out[arm][name+'_ratio_vs_'+ref]=round(refv/v,5) if v else None
        return out
    report=dict(protocol=PROTO,sources=TARGET,trials=EXPECTED,blind_holdout=False,
        sourceonly_new_X19=True,not_in_X15_X6_X18_X19=True,
        not_full_global_history=True,strict_no_auto_promotion=True,
        UNSAT_independent_LRAT=False,
        cross_solver_UNSAT_agreement_required=True,
        outcome_of_scout_never_credited=True,
        baseline_one_logical_core_vs_portfolio_two_logical_cores=True,
        CPU_PAR2_unaccepted_penalty='2*12s*logical_cpu_budget',
        native_bounded_probe_not_PAR2=True,
        overall=score(rows),
        by_binary_class={name:score([r for r in rows
           if bysha[r['original_sha256']]['structure']['binary_class']==name])
           for name in ('binary_dense','binary_sparse')},
        by_horn_class={name:score([r for r in rows
           if bysha[r['original_sha256']]['structure']['horn_class']==name])
           for name in ('horn_dominant','horn_other')},
        by_year={year:score([r for r in rows
           if bysha[r['original_sha256']]['year']==year]) for year in YEARS},
        per_source=[dict(sha256=sha,gbd=c['gbd'],year=c['year'],
          features=c['structure'],
          score=score([r for r in rows if r['original_sha256']==sha]))
          for sha,c in bysha.items()],
        probes=probes,rows=rows)
    save(ROOT/'report.json',report)
    print('X20_FINAL',json.dumps({k:v for k,v in report.items()
         if k not in ('per_source','probes','rows')},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('selftest','freeze','verify','shard','audit'))
    p.add_argument('--shard',type=int,default=0)
    args=p.parse_args()
    if args.action=='selftest':selftest()
    elif args.action=='freeze':freeze()
    elif args.action=='verify':verify();print('X20_VERIFY_PASS',flush=True)
    elif args.action=='shard':shard(args.shard)
    else:audit()

if __name__=='__main__':main()
