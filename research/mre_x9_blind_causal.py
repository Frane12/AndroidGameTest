#!/usr/bin/env python3
"""DRNAS X9 prospective clause-order causal validation.
30 source-only frozen 2021-23 originals; never select on solver timing.
Native CMS uses fixed binary and original clause multiset; 5 arms and 2 reps.
CaDiCaL has no per-rep solver seed; report that explicitly.
No bounded-only measurements enter PAR2; UNSAT without LRAT needs cross-solver agreement.
"""
import argparse, collections, hashlib, json, os, pathlib, random, re
import subprocess, tempfile, time
import mre_x6_shift_dose_causal as x6
import mre_x2_clause_order_causal as x2
import mre7_extended_easy_freeze as pool
import mre7_reference_easy_freeze as fetch
import mre6b_blind_freeze as prior

ROOT=pathlib.Path('mre_x9')
PROTO='DRNAS-X9-BLIND30-5ARMS-2REPS-15S-E2E-20261109-v1'
SALT=PROTO+'-SOURCE-ONLY'
MODES=('original','front100','spread_shifted','kissat','cadical')
CAP=15.0
REPS=2
TARGET=30
SHARDS=10
YEARS=('2021','2022','2023')
STRATA=('minisat1m_yes','minisat1m_other')
PER_STRATUM=5
def need(ok,msg):
    if not ok: raise RuntimeError('X9_FAIL_CLOSED '+msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):
    pathlib.Path(p).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def seed(c,r):return int(sha((PROTO+'|'+c['sha256']+'|'+str(r)).encode())[:8],16) & 0x7fffffff
def freeze():
    ROOT.mkdir(exist_ok=True)
    ids=set();digests=set();registries=[]
    def visit(obj):
        if isinstance(obj,dict):
            for v in obj.values():visit(v)
        elif isinstance(obj,list):
            for v in obj:visit(v)
        elif isinstance(obj,str):
            if re.fullmatch('[0-9a-f]{32}',obj):ids.add(obj)
            if re.fullmatch('[0-9a-f]{64}',obj):digests.add(obj)
    registry_paths=(
        pathlib.Path('mre7_easy/manifest.json'),
        pathlib.Path('mre11b_blind/manifest.json'),
        pathlib.Path('mre_x/manifest.json'),
        pathlib.Path('mre_x6fresh/manifest.json'),
        pathlib.Path('mre_x6easy/manifest.json'),
    )
    for p in registry_paths:
        need(p.is_file(),'missing prior registry '+str(p))
        visit(json.loads(p.read_text()))
        registries.append(dict(path=str(p),sha256=sha(p.read_bytes())))
    need(prior.PRIOR.is_file(),'missing historical registry')
    ids.update(x.strip() for x in prior.PRIOR.read_text().splitlines()
               if re.fullmatch('[0-9a-f]{32}',x.strip()))
    strata={};indexes={};candidate_ids=set()
    for year in YEARS:
        allids,h_all=pool.getids('track=main_'+year)
        mini,h_mini=pool.getids('track=main_'+year+' and minisat1m=yes')
        need(len(allids)==400 and set(mini)<=set(allids),'published index drift')
        for stratum, subset in (('minisat1m_yes',set(mini)),
                                ('minisat1m_other',set(allids)-set(mini))):
            strata[(year,stratum)]=sorted(subset,key=lambda g:sha(
                (SALT+'|'+year+'|'+stratum+'|'+g).encode()))
        candidate_ids.update(allids)
        indexes[year]=dict(all_sha256=h_all,mini_sha256=h_mini,
                           mini_count=len(mini),all_count=len(allids))
    more,ds=prior.inspect_repo_ids(candidate_ids)
    ids.update(more);digests.update(ds)
    selected=[];trace=[];counts=collections.Counter();tried=set()
    fetch.prior.r32p.CNF_LIMIT=12*1024*1024
    # Fixed geometry bounds are a size proxy, NEVER a measured hardness filter.
    for year in YEARS:
        for stratum in STRATA:
            for g in strata[(year,stratum)]:
                if counts[(year,stratum)]==PER_STRATUM:break
                if g in ids or g in tried:continue
                tried.add(g)
                need(len(tried)<=650,'predeclared source scan budget exhausted')
                p=ROOT/(g+'.cnf')
                item=dict(gbd=g,year=year,stratum=stratum)
                try:
                    raw=fetch.get('https://benchmark-database.de/file/'+g,
                                  12*1024*1024,seconds=20)
                    plain,_=fetch.prior.r32p.decode(raw)
                    need(len(plain)<=12*1024*1024,'source uncompressed size cap')
                    n,m=fetch.prior.r32p.parse_dimacs_metadata(plain)
                    need(150<=n<=20000 and 500<=m<=150000,
                         'geometry cap')
                    d=sha(plain)
                    need(d not in digests,'previous source SHA')
                    p.write_bytes(plain)
                    nn,cc=x2.parse(p)
                    need(nn==n and len(cc)==m,'DIMACS mismatch')
                    selected.append(dict(gbd=g,year=year,stratum=stratum,
                        sha256=d,filename=p.name,bytes=len(plain),
                        vars=n,clauses=m))
                    ids.add(g);digests.add(d);counts[(year,stratum)]+=1
                    item.update(selection='FROZEN_BEFORE_SOLVING',
                                sha256=d,vars=n,clauses=m)
                except Exception as e:
                    p.unlink(missing_ok=True)
                    item.update(selection='EXCLUDED_GEOMETRY_FETCH_OR_REGISTRY',
                                reason=str(e)[:170])
                trace.append(item)
                print('X9_SOURCE',json.dumps(item,sort_keys=True),flush=True)
                save(ROOT/'selection-progress.json',dict(
                    selected=selected,trace=trace,indexes=indexes,
                    counts={y+'_'+z:counts[(y,z)] for y in YEARS for z in STRATA}))
            need(counts[(year,stratum)]==PER_STRATUM,
                 'insufficient new sources in '+year+' '+stratum)
    need(len(selected)==TARGET and len({c['sha256'] for c in selected})==TARGET,
         'not 30 unique frozen originals')
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=selected,
        modes=MODES,cap_s=CAP,reps=REPS,expected_trials=TARGET*REPS*len(MODES),
        indexes=indexes,prior_registries=registries,
        source_selection='salted per-year per-MiniSat1m-metadata stratum original official SAT 2021-2023; fixed geometry only, no DRNAS or reference timing screening',
        metadata_is_not_proof_of_medium_difficulty=True,
        source_disjoint_declared_registries=True,
        globally_exhaustive_history_not_guaranteed=True,
        mixed_public_metadata_strata=True,no_auto_promotion=True,trace=trace))
    print('X9_FROZEN',len(selected),flush=True)

def verify():
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and m['cap_s']==CAP and m['reps']==REPS and m['modes']==list(MODES),'protocol drift')
    need(len(m['cases'])==TARGET and len({c['sha256'] for c in m['cases']})==TARGET,'source cardinality')
    for c in m['cases']:
        b=(ROOT/c['filename']).read_bytes()
        need(len(b)==c['bytes'] and sha(b)==c['sha256'],'source drift')
    return m
def trial(c,rep,mode):
    src=ROOT/c['filename'];s=seed(c,rep)
    need(mode in MODES,'unknown mode')
    env=os.environ.copy();env.pop('DRNAS_MAX_CONFLICTS',None)
    status='TIMEOUT';model={};stats=None;prep=0.0;raw_status='TIMEOUT'
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        start=time.perf_counter();use=src
        if mode not in ('original','kissat','cadical'):
            nv,clauses=x2.parse(src)
            changed=x6.transform(clauses,mode)
            need(collections.Counter(clauses)==collections.Counter(changed),
                 'exact original clause multiset changed')
            use=pathlib.Path(td)/'ordered.cnf';x2.write(use,nv,changed)
        prep=time.perf_counter()-start
        p=None;remaining=CAP-prep
        if remaining>0:
            if mode=='kissat':
                cmd=[str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),
                     '--seed='+str(s),str(use.resolve())]
            elif mode=='cadical':
                # Package CLI does not expose independently applied paired seed.
                cmd=['/usr/bin/cadical',str(use.resolve())]
            else:
                cmd=[str(pathlib.Path('mre_x4/bin/native').resolve()),
                     str(use.resolve()),'x_native',str(s)]
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,
                                 errors='replace',env=env,timeout=remaining)
            except subprocess.TimeoutExpired:
                pass
        elapsed=time.perf_counter()-start
        if p is not None:
            if mode in ('kissat','cadical'):
                need(p.returncode in (10,20),
                     'reference solver error '+mode+': '+p.stderr[-300:])
                status='SAT' if p.returncode==10 else 'UNSAT'
                need(('s SATISFIABLE' if status=='SAT' else 's UNSATISFIABLE')
                     in p.stdout,'reference verdict text conflict')
                for line in p.stdout.splitlines():
                    if line.startswith('v '):
                        for l in map(int,line[2:].split()):
                            if l:
                                need(abs(l) not in model or
                                     model[abs(l)]==(l>0),
                                     'inconsistent SAT witness')
                                model[abs(l)]=l>0
            else:
                need(p.returncode==0,'CMS crashed: '+p.stderr[-300:])
                gate=x6.x4.base.parse_gate(p.stdout,'x_native')
                need(not gate['applied'],'native changed CNF')
                status,model,stats=x6.x4.base.cms.parsed_native(p.stdout)
        raw_status=status
        if elapsed>CAP or status not in ('SAT','UNSAT'):
            status='TIMEOUT'
        verified=False
        if status=='SAT':
            x6.x4.base.cms.verify_model(src,model)
            verified=True
    binary=('/usr/bin/cadical' if mode=='cadical'
            else 'built/bin/kissat_4_0_4' if mode=='kissat'
            else 'mre_x4/bin/native')
    return dict(protocol=PROTO,gbd=c['gbd'],year=c['year'],
        stratum=c['stratum'],sha256=c['sha256'],rep=rep,seed=s,
        seed_policy='sha256_low31_v2',
        independent_seed_applied=(mode!='cadical'),
        mode=mode,status=status,raw_status=raw_status,
        elapsed_s=round(elapsed,6),preprocessing_s=round(prep,6),
        PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),
        SAT_original_verified=verified,UNSAT_independent_LRAT=False,
        native_stats=stats,binary_sha256=sha(pathlib.Path(binary).read_bytes()))

def shard(idx):
    m=verify();need(idx in range(SHARDS),'bad shard')
    cases=[c for i,c in enumerate(m['cases']) if i%SHARDS==idx]
    need(len(cases)==3,'wrong shard distribution')
    rows=[]
    for c in cases:
        for rep in range(REPS):
            order=list(MODES);random.Random(seed(c,rep)).shuffle(order)
            for mode in order:
                row=trial(c,rep,mode);rows.append(row)
                save(ROOT/('shard-%d.json'%idx),rows)
                print('X9_TRIAL',json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==30,'short shard')
    print('X9_SHARD_PASS',idx,30,flush=True)

def audit():
    m=verify();rows=[];seen=set();bysha={c['sha256']:c for c in m['cases']}
    for i in range(SHARDS):
        rows+=json.loads((ROOT/('shard-%d.json'%i)).read_text())
    need(len(rows)==m['expected_trials']==300,'missing trials')
    for r in rows:
        c=bysha.get(r['sha256'])
        need(c and c['gbd']==r['gbd'],'unknown source')
        need(r['protocol']==PROTO and r['rep'] in range(REPS)
             and r['mode'] in MODES and r['seed']==seed(c,r['rep']),
             'source, protocol or seed mismatch')
        k=(r['sha256'],r['rep'],r['mode'])
        need(k not in seen,'duplicate trial');seen.add(k)
        need(r['status'] in ('SAT','UNSAT','TIMEOUT'),'bad verdict')
        need(r['status']!='SAT' or r['SAT_original_verified'],
             'unchecked original SAT witness')
        need(r['status']!='TIMEOUT' or r['PAR2_s']==2*CAP,
             'bad timeout penalty')
        need(r['status']=='TIMEOUT' or
             (r['elapsed_s']<=CAP and r['PAR2_s']==r['elapsed_s']),
             'bad solved time')
        need(r['independent_seed_applied']==(r['mode']!='cadical'),
             'seed disclosure mismatch')
    per_source=[]
    for c in m['cases']:
        rs=[r for r in rows if r['sha256']==c['sha256']]
        verdicts={r['status'] for r in rs if r['status']!='TIMEOUT'}
        need(len(verdicts)<=1,'SAT/UNSAT contradiction')
        reference_unsat=any(r['mode'] in ('kissat','cadical')
                            and r['status']=='UNSAT' for r in rs)
        cms_unsat=any(r['mode'] in ('original','front100','spread_shifted')
                      and r['status']=='UNSAT' for r in rs)
        for r in rs:
            r['UNSAT_cross_solver_agreement_no_LRAT']=(
                r['status']=='UNSAT' and reference_unsat and cms_unsat)
            r['accepted_solved']=(r['status']=='SAT' or
                                  r['UNSAT_cross_solver_agreement_no_LRAT'])
            r['audited_PAR2_s']=(r['PAR2_s'] if r['accepted_solved']
                                  else 2*CAP)
        per_source.append(dict(gbd=c['gbd'],sha256=c['sha256'],
            year=c['year'],stratum=c['stratum'],
            PAR2_s={mode:round(sum(r['audited_PAR2_s'] for r in rs
                                  if r['mode']==mode),6) for mode in MODES},
            solved={mode:sum(r['accepted_solved'] for r in rs
                             if r['mode']==mode) for mode in MODES}))
    scores={}
    for mode in MODES:
        rs=[r for r in rows if r['mode']==mode]
        scores[mode]=dict(n=len(rs),
            solved=sum(r['accepted_solved'] for r in rs),
            timeouts=sum(r['status']=='TIMEOUT' for r in rs),
            PAR2_s=round(sum(r['audited_PAR2_s'] for r in rs),6))
    for mode,v in scores.items():
        for base in ('original','kissat','cadical'):
            v['speedup_vs_'+base]=round(scores[base]['PAR2_s']/v['PAR2_s'],6)
    regression_counts={}
    for mode in ('front100','spread_shifted'):
        wins=losses=ties=0
        for c in m['cases']:
            row=next(p for p in per_source if p['sha256']==c['sha256'])
            a=row['PAR2_s'][mode];b=row['PAR2_s']['original']
            if a<b-0.000001:wins+=1
            elif a>b+0.000001:losses+=1
            else:ties+=1
        regression_counts[mode]=dict(wins=wins,losses=losses,ties=ties)
    out=dict(protocol=PROTO,source_count=TARGET,trials=len(rows),
        cap_s=CAP,repetitions=REPS,score=scores,per_source=per_source,
        regressions_vs_original=regression_counts,
        preprocessing_included=True,no_bounded_diagnostics=True,
        UNSAT_independent_LRAT=False,
        UNSAT_requires_cross_solver_for_scoring=True,
        cadical_is_unseeded_fixed_baseline=True,
        native_binary_frozen=True,
        source_selection_before_solver_timings=True,
        development_not_seen_in_declared_registry=True,
        globally_exhaustive_history_not_guaranteed=True,
        no_auto_promotion=True,rows=rows)
    save(ROOT/'report.json',out)
    print('X9_FINAL',json.dumps({k:v for k,v in out.items()
        if k not in ('rows','per_source')},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('freeze','verify','shard','audit','selftest'));p.add_argument('--shard',type=int,default=0);a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='verify':verify();print('X9_VERIFY_PASS',flush=True)
    elif a.action=='shard':shard(a.shard)
    elif a.action=='selftest':x6.install();x6.x4.selftest();print('X9_SELFTEST_PASS',flush=True)
    else:audit()
if __name__=='__main__':main()
