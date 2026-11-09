#!/usr/bin/env python3
"""Preregistered competition-style mini benchmark; not an official competition.
Fresh relative to frozen SQL and declared artifact/source registries. No claim
of exhaustive global blindness. SAT witnesses replayed; UNSAT agreement is not LRAT.
"""
import argparse, collections, hashlib, json, os, pathlib, random, re, resource
import signal, subprocess, tempfile, time
import drnas_x16_singlecore_dual as x16
import drnas_x16a_asymmetric_timeshare as x16a
import drnas_x18_selective as x18
import drnas_x15_selector_holdout as x15
import drnas_x19_transfer as x19
import mre7_extended_easy_freeze as pool
import mre7_reference_easy_freeze as fetch

ROOT=pathlib.Path('mre_x21')
DRIVER=ROOT/'bin/selective'
CAP=30.0
REPS=2
SHARDS=8
TARGET=24
ARMS=('x15_gate','x16_race2','x16a_balanced50','front100','select2','native1','kissat1','cadical1','x21_delay025')
PROTO='DRNAS-X21-COMPETITION-MINI-24NEW-9ARM-2REP-30S-v1'
SALT=PROTO+'-PRECOMMIT-20261109'
QUOTAS={'2021':4,'2022':4,'2023':4,'2024':6,'2025':6}
EXPECTED=TARGET*REPS*len(ARMS)
need=x19.need
save=x19.save
digest=x19.digest

def setup():
    ROOT.mkdir(exist_ok=True)
    x16.ROOT=ROOT;x16.CAP=CAP;x16.REPS=REPS
    x16a.ROOT=ROOT;x16a.SOURCE=ROOT;x16a.CAP=CAP;x16a.REPS=REPS
    x18.ROOT=ROOT;x18.DRIVER=DRIVER;x18.CAP=CAP;x18.SOLVER_CAP=CAP-.45
    x18.PROTO=PROTO;x18.REPS=REPS;x18.configure()
    for k in ('DRNAS_MAX_CONFLICTS','DRNAS_X7_TRACE','DRNAS_X8_TRACE'):os.environ.pop(k,None)

def exclusions():
    registry=json.loads(pathlib.Path('research/x21_sql_exclusions.json').read_text())
    hashes=set(registry['hashes']);sources=[]
    # Frozen manifests from latest source-only runs supplement aggregate-only SQL.
    for base in (pathlib.Path('prior'),pathlib.Path('research'),pathlib.Path('experiments')):
        if not base.exists():continue
        for p in base.rglob('*'):
            if p.is_file() and p.suffix in ('.json','.csv','.txt','.tsv','.md','.py') and p.stat().st_size<8*1024*1024:
                txt=p.read_text(errors='replace')
                hashes.update(re.findall(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])|(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])',txt))
                if p.name=='manifest.json':sources.append({'path':str(p),'sha256':digest(p)})
    need(len(sources)>=4,'latest exclusion manifests missing')
    return hashes,dict(sql_sha256=registry['sql_sha256'],hash_count=len(hashes),manifests=sources,
        scope='SQL all text fields, branch research/experiments, X18 X19 X19B X6 manifests; global history incomplete')

def freeze():
    setup();excluded,meta=exclusions()
    prior=json.loads(pathlib.Path('prior/x18/mre_x18/manifest.json').read_text())
    need(digest(DRIVER)==prior['driver_sha256'],'X18 driver changed')
    need(x16.binaries()==prior['backend_sha256'],'pinned backend changed')
    cases=[];trace=[];indexes={};seen=set(excluded)
    for year,quota in QUOTAS.items():
        ids,idxsha=pool.getids('track=main_'+year)
        need(len(ids)==400,'official source index drift '+year)
        indexes[year]=idxsha
        ranked=sorted(set(ids)-seen,key=lambda g:hashlib.sha256((SALT+'|'+year+'|'+g).encode()).hexdigest())
        count=0
        for g in ranked[:160]:
            if count==quota:break
            p=ROOT/(g+'.cnf');row=dict(year=year,gbd=g)
            try:
                raw=fetch.get('https://benchmark-database.de/file/'+g,20*1024*1024,seconds=20)
                plain,compression=fetch.prior.r32p.decode(raw)
                need(len(plain)<=20*1024*1024,'fixed size stratum')
                n,m=fetch.prior.r32p.parse_dimacs_metadata(plain)
                need(0<n<=100000 and 0<m<=500000,'fixed geometry stratum')
                sha=hashlib.sha256(plain).hexdigest()
                need(sha not in seen,'previous original SHA')
                p.write_bytes(plain)
                f=x19.features(p)
                need((f['vars'],f['clauses'])==(n,m),'invalid DIMACS')
                sig=x15.b.cheap_duplicate_signal(p)
                cases.append(dict(filename=p.name,sha256=sha,gbd=g,year=year,cohort='registry_unseen',
                    previous_X15_tier='new',structure=f,cheap_sample=sig,vars=n,clauses=m,bytes=len(plain)))
                seen.update((g,sha));count+=1;row.update(selected=True,sha256=sha)
            except Exception as e:
                p.unlink(missing_ok=True);row.update(selected=False,reason=str(e)[:200])
            trace.append(row);save(ROOT/'selection-progress.json',dict(cases=cases,trace=trace))
            print('X21_SOURCE',json.dumps(row),flush=True)
        need(count==quota,'insufficient unseen sources in fixed year '+year)
    m=dict(protocol=PROTO,cases=cases,arms=ARMS,cap_s=CAP,reps=REPS,expected_trials=EXPECTED,
        source_indexes=indexes,exclusions=meta,selection_salt=SALT,source_only_no_solver_screen=True,
        global_blind_claim=False,registry_disjoint=True,not_official_competition=True,
        independent_UNSAT_LRAT=False,backend_sha256=x16.binaries(),driver_sha256=digest(DRIVER),
        code_sha256=digest(__file__),max_logical_cpus=2,delay_s=.25,
        policy_locked_before_holdout=True,no_auto_promotion=True)
    save(ROOT/'manifest.json',m);verify()
    print('X21_FROZEN',json.dumps(dict(sources=len(cases),trials=EXPECTED,excluded_hashes=len(excluded))),flush=True)

def verify():
    setup();m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and m['arms']==list(ARMS) and m['expected_trials']==EXPECTED
         and m['cap_s']==CAP and m['reps']==REPS,'protocol drift')
    need(m['code_sha256']==digest(__file__) and m['backend_sha256']==x16.binaries()
         and m['driver_sha256']==digest(DRIVER),'code/binary drift')
    need(len(m['cases'])==TARGET and len({c['sha256'] for c in m['cases']})==TARGET,'duplicate/missing SHA')
    for c in m['cases']:need(digest(ROOT/c['filename'])==c['sha256'],'source drift')
    return m

def delayed(c,rep):
    """Kissat keeps all its state; native starts only if no answer after 250 ms."""
    src=ROOT/c['filename'];top=x16.topology();sd=x18.seed(c,rep)
    before=x16.rusage_snapshot(resource.RUSAGE_CHILDREN)
    pb=x16.rusage_snapshot(resource.RUSAGE_SELF);start=time.perf_counter()
    entries=[];winner=None;status='TIMEOUT';launched=False
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        try:
            entries.append(x16.launch('kissat',src,sd,top['first'],td))
            while time.perf_counter()-start<CAP and winner is None:
                for e in entries:
                    if e['read'] or e['p'].poll() is None:continue
                    result=x16.completed_result(e,src)
                    if result in ('SAT','UNSAT'):status=result;winner=e['name'];break
                if winner is not None:break
                if not launched and time.perf_counter()-start>=.25:
                    entries.append(x16.launch('native',src,sd,top['second'],td));launched=True
                if launched and all(e['read'] for e in entries):break
                time.sleep(.0015)
        finally:x16.cleanup(entries)
    elapsed=time.perf_counter()-start
    if elapsed>CAP:status='TIMEOUT';winner=None
    return dict(status=status,selected_backend=winner,elapsed_s=elapsed,
        SAT_original_witness_verified=status=='SAT',
        child_cpu_s=x16.counters_diff(before,x16.rusage_snapshot(resource.RUSAGE_CHILDREN))['cpu_s'],
        parent_cpu_s=x16.counters_diff(pb,x16.rusage_snapshot(resource.RUSAGE_SELF))['cpu_s'],
        native_launched=launched,cpu_affinity={'kissat':[top['first']],**({'native':[top['second']]} if launched else {})})

def trial(c,rep,arm):
    setup();need(arm in ARMS,'bad arm');need(digest(ROOT/c['filename'])==c['sha256'],'source drift')
    start=time.perf_counter();pb=x16.rusage_snapshot(resource.RUSAGE_SELF)
    route=arm
    if arm=='x15_gate':
        sig=x15.b.cheap_duplicate_signal(ROOT/c['filename'])
        route={'front100':'front100','parallel2':'x16_race2','original':'native1'}[x15.choose(sig)[0]]
    allocated=2 if route in ('x16_race2','select2','x21_delay025') else 1
    remaining=max(.001,CAP-(time.perf_counter()-start))
    x16.CAP=x16a.CAP=x18.CAP=remaining;x18.SOLVER_CAP=max(.001,remaining-.45)
    if route in ('native1','kissat1','front100','x16_race2'):
        r=x16.run_trial(c,rep,{'front100':'front100_1','x16_race2':'race2'}.get(route,route))
    elif route=='x16a_balanced50':r=x16a.run_trial(c,rep,'balanced50',80)
    elif route in ('select2','cadical1'):r=x18.run_driver(c,rep,route)
    else:r=delayed(c,rep)
    elapsed=time.perf_counter()-start
    if elapsed>CAP or r['status'] not in ('SAT','UNSAT'):
        r.update(status='TIMEOUT',selected_backend=None,SAT_original_witness_verified=False)
    r.update(protocol=PROTO,arm=arm,route=route,original_sha256=c['sha256'],gbd=c['gbd'],
        year=c['year'],rep=rep,seed=x18.seed(c,rep),cap_s=CAP,elapsed_s=round(elapsed,6),
        PAR2_s=round(elapsed if r['status'] in ('SAT','UNSAT') else 2*CAP,6),
        allocated_logical_cpus=allocated,max_allowed_logical_cpus=2,
        parent_cpu_s=x16.counters_diff(pb,x16.rusage_snapshot(resource.RUSAGE_SELF))['cpu_s'],
        original_source_SHA_verified=True,UNSAT_independent_LRAT=False)
    return r

def shard(i):
    m=verify();need(0<=i<SHARDS,'shard index');rows=[]
    for c in m['cases'][i::SHARDS]:
        for rep in range(REPS):
            order=list(ARMS);random.Random(x18.seed(c,rep)).shuffle(order)
            for arm in order:
                r=trial(c,rep,arm);rows.append(r);save(ROOT/f'shard-{i}.json',rows)
                print('X21_TRIAL',json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==54,'incomplete shard');print('X21_SHARD_PASS',i,len(rows),flush=True)

def score(rows):
    out={}
    for arm in ARMS:
        a=[r for r in rows if r['arm']==arm]
        out[arm]=dict(n=len(a),solved=sum(r['accepted'] for r in a),
            SAT_verified=sum(r['accepted'] and r['status']=='SAT' for r in a),
            UNSAT_agreement_no_LRAT=sum(r['accepted'] and r['status']=='UNSAT' for r in a),
            timeouts=sum(r['status']=='TIMEOUT' for r in a),
            unconfirmed_UNSAT=sum(r['status']=='UNSAT' and not r['accepted'] for r in a),
            PAR2_s=round(sum(r['audited_PAR2_s'] for r in a),6),
            total_elapsed_s=round(sum(r['elapsed_s'] for r in a),6),
            child_cpu_s=round(sum(r['child_cpu_s'] for r in a),6),
            parent_cpu_s=round(sum(r['parent_cpu_s'] for r in a),6),
            CPU_PAR2_s=round(sum(r['child_cpu_s']+r['parent_cpu_s'] if r['accepted']
                else 2*CAP*r['allocated_logical_cpus'] for r in a),6))
    for arm,v in out.items():
        base=out['kissat1']['PAR2_s'];v['speedup_vs_kissat']=round(base/max(v['PAR2_s'],1e-9),6)
        v['pct_less_PAR2_vs_kissat']=round(100*(1-v['PAR2_s']/base),4) if base else None
    return out

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):rows+=json.loads((ROOT/f'shard-{i}.json').read_text())
    expected={(c['sha256'],rep,a) for c in m['cases'] for rep in range(REPS) for a in ARMS}
    need(len(rows)==EXPECTED and {(r['original_sha256'],r['rep'],r['arm']) for r in rows}==expected,'missing/duplicate pair')
    for c in m['cases']:
        g=[r for r in rows if r['original_sha256']==c['sha256']]
        need(len({r['status'] for r in g if r['status']!='TIMEOUT'})<=1,'SAT/UNSAT contradiction')
        backends={r['selected_backend'] for r in g if r['status']=='UNSAT' and r['arm'] in ('native1','kissat1','cadical1')}
        backends.discard(None);confirmed=len(backends)>=2
        for r in g:
            need(r['protocol']==PROTO and r['cap_s']==CAP and r['seed']==x18.seed(c,r['rep']),'protocol/seed drift')
            need(r['status']!='SAT' or r['SAT_original_witness_verified'],'SAT not replayed')
            need(r['PAR2_s']==(2*CAP if r['status']=='TIMEOUT' else r['elapsed_s']),'bad PAR2')
            need(r['status']=='TIMEOUT' or r['elapsed_s']<=CAP,'deadline violation')
            r['accepted']=r['status']=='SAT' or (r['status']=='UNSAT' and confirmed)
            r['audited_PAR2_s']=r['PAR2_s'] if r['accepted'] else 2*CAP
    report=dict(protocol=PROTO,sources=TARGET,trials=EXPECTED,overall=score(rows),
        by_shard={str(i):score([r for r in rows if r['original_sha256'] in {c['sha256'] for c in m['cases'][i::SHARDS]}]) for i in range(SHARDS)},
        by_year={y:score([r for r in rows if r['year']==y]) for y in QUOTAS},
        per_source=[dict(sha256=c['sha256'],gbd=c['gbd'],scores=score([r for r in rows if r['original_sha256']==c['sha256']])) for c in m['cases']],
        rows=rows,not_official_competition=True,global_blind_claim=False,registry_disjoint=True,
        UNSAT_independent_LRAT=False,no_auto_promotion=True)
    save(ROOT/'report.json',report)
    print('X21_FINAL',json.dumps({k:v for k,v in report.items() if k not in ('rows','per_source','by_shard','by_year')},sort_keys=True),flush=True)

def selftest():
    setup()
    for text,status in [('p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n','SAT'),('p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n','UNSAT')]:
        p=ROOT/'toy.cnf';p.write_text(text)
        c=dict(filename=p.name,sha256=digest(p),gbd='toy',year='toy',cohort='selftest',previous_X15_tier='new')
        for arm in ARMS:need(trial(c,0,arm)['status']==status,'toy failure '+arm)
    # Exercise delayed launch and process cleanup, which instant toy answers skip.
    old_command=x16.command
    with tempfile.TemporaryDirectory() as td:
        fake=pathlib.Path(td)/'slow.py'
        fake.write_text('import time; time.sleep(.35); print("s SATISFIABLE\\n v 1 2 3 0".replace("\\n v","\\nv")); raise SystemExit(10)')
        p=ROOT/'toy.cnf';p.write_text('p cnf 3 1\n1 2 3 0\n')
        c=dict(filename=p.name,sha256=digest(p),gbd='toy',year='toy',cohort='selftest',previous_X15_tier='new')
        import sys
        try:
            # Both use reference syntax, but only the first (Kissat) can finish first.
            x16.command=lambda backend,src,sd:[sys.executable,str(fake)]
            r=delayed(c,0)
            need(r['status']=='SAT' and r['native_launched'] and r['selected_backend']=='kissat','delayed path failure')
        finally:x16.command=old_command
    (ROOT/'toy.cnf').unlink();print('X21_SELFTEST_PASS',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('freeze','verify','shard','audit','selftest'));p.add_argument('--shard',type=int,default=0);a=p.parse_args()
    if a.action=='shard':shard(a.shard)
    else:globals()[a.action]()
if __name__=='__main__':main()
