#!/usr/bin/env python3
"""Frozen X6 policies, new registry-disjoint inputs, true E2E 8s cap.
Historical registries are explicit, not a claim of complete global history.
No bounded-conflict results enter PAR2. Never select on candidate timing.
"""
import argparse, collections, hashlib, json, os, pathlib, random, re
import subprocess, tempfile, time
import mre_x6_shift_dose_causal as x6
import mre_x2_clause_order_causal as x2
import mre7_extended_easy_freeze as pool
import mre7_reference_easy_freeze as fetch
import mre6b_blind_freeze as prior

ROOT=pathlib.Path('mre_x6fresh')
PROTO='DRNAS-X6-FRESH8-9ARMS-2SEEDS-8S-E2E-20261109-v1'
SALT=PROTO+'-SOURCE-ONLY'
MODES=x6.MODES+('kissat',)
CAP=8.0
REPS=2
TARGET=8
SHARDS=8
YEARS=('2021','2022','2023')
def need(ok,msg):
    if not ok: raise RuntimeError('X6F_FAIL_CLOSED '+msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,v):
    pathlib.Path(p).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(p).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def seed(c,r):return int(sha((PROTO+'|'+c['sha256']+'|'+str(r)).encode())[:8],16) & 0x7fffffff
def freeze():
    ROOT.mkdir(exist_ok=True)
    ids=set();digests=set();registries=[]
    # Include rejected/screened inputs as well as accepted sources.
    def visit(x):
        if isinstance(x,dict):
            for k,v in x.items():visit(v)
        elif isinstance(x,list):
            for v in x:visit(v)
        elif isinstance(x,str):
            if re.fullmatch('[0-9a-f]{32}',x):ids.add(x)
            if re.fullmatch('[0-9a-f]{64}',x):digests.add(x)
    for p in (pathlib.Path('mre7_easy/manifest.json'),pathlib.Path('mre11b_blind/manifest.json'),pathlib.Path('mre_x/manifest.json')):
        need(p.is_file(),'missing prior registry '+str(p))
        visit(json.loads(p.read_text()))
        registries.append(dict(path=str(p),sha256=sha(p.read_bytes())))
    ids.update(x.strip() for x in prior.PRIOR.read_text().splitlines() if re.fullmatch('[0-9a-f]{32}',x.strip()))
    candidates=[];indexes={}
    for year in YEARS:
        allids,h1=pool.getids('track=main_'+year)
        easy,h2=pool.getids('track=main_'+year+' and minisat1m=yes')
        need(len(allids)==400 and set(easy)<=set(allids),'index drift')
        candidates.extend((year,g) for g in allids)
        indexes[year]=dict(all_sha256=h1,easy_sha256=h2,count=len(easy))
    more,ds=prior.inspect_repo_ids({g for _,g in candidates})
    ids.update(more);digests.update(ds)
    candidates=sorted(set(candidates),key=lambda z:sha((SALT+'|'+z[0]+'|'+z[1]).encode()))
    selected=[];trace=[];counts=collections.Counter()
    availability={y:sum(yr==y and g not in ids for yr,g in candidates) for y in YEARS}
    print('X6F_POOL',json.dumps(availability,sort_keys=True),flush=True)
    save(ROOT/'selection-progress.json',dict(eligible_by_year=availability,excluded_ids=len(ids),indexes=indexes))
    fetch.prior.r32p.CNF_LIMIT=12*1024*1024
    tried=set()
    # Two per year then two extra, all source-only.
    ordered=[(0,y,g) for y0 in YEARS for y,g in candidates if y==y0]+[(1,y,g) for y,g in candidates]
    for phase,y,g in ordered:
        if len(selected)==TARGET:break
        if g in ids or g in tried:continue
        if phase==0 and counts[y]>=2:continue
        if phase==1 and min(counts[z] for z in YEARS)<2:continue
        if counts[y]>=4:continue
        tried.add(g)
        need(len(tried)<=180,'source scan budget exhausted')
        p=ROOT/(g+'.cnf');row=dict(gbd=g,year=y)
        try:
            raw=fetch.get('https://benchmark-database.de/file/'+g,12*1024*1024,seconds=20)
            plain,kind=fetch.prior.r32p.decode(raw)
            need(len(plain)<=12*1024*1024,'plain size cap')
            n,m=fetch.prior.r32p.parse_dimacs_metadata(plain)
            need(n<=12000 and m<=85000,'fixed geometry cap')
            d=sha(plain)
            need(d not in digests,'previous source SHA')
            p.write_bytes(plain)
            # Validate complete DIMACS before freezing. No solver screening.
            nn,cc=x2.parse(p);need(nn==n and len(cc)==m,'DIMACS mismatch')
            selected.append(dict(gbd=g,year=y,sha256=d,filename=p.name,bytes=len(plain),vars=n,clauses=m))
            counts[y]+=1;ids.add(g);digests.add(d)
            row.update(selection='FROZEN_BEFORE_SOLVING',sha256=d)
        except Exception as e:
            p.unlink(missing_ok=True)
            row.update(selection='EXCLUDED_SIZE_FETCH_OR_PRIOR',reason=str(e)[:180])
        trace.append(row);print('X6F_SOURCE',json.dumps(row),flush=True)
        save(ROOT/'selection-progress.json',dict(eligible_by_year=availability,selected=selected,trace=trace))
    need(len(selected)==TARGET and min(counts[y] for y in YEARS)>=2,'not eight new sources')
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=selected,modes=MODES,cap_s=CAP,reps=REPS,expected_trials=144,indexes=indexes,prior_registries=registries,source_selection='all official main 2021-2023 sources, salted GBD rank, fixed geometry and year quotas; no solver screening',source_disjoint_declared_registries=True,globally_exhaustive_history_not_guaranteed=True,no_auto_promotion=True,trace=trace))
    print('X6F_FROZEN',len(selected),flush=True)
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
    env=os.environ.copy();env.pop('DRNAS_MAX_CONFLICTS',None)
    status='TIMEOUT';model={};stats=None;prep=0.0
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        start=time.perf_counter();use=src
        if mode not in ('original','kissat'):
            nv,clauses=x2.parse(src)
            changed=x6.transform(clauses,mode)
            # Exact multiset certificate replay is part of E2E preprocessing.
            need(collections.Counter(clauses)==collections.Counter(changed),'multiset changed')
            use=pathlib.Path(td)/'ordered.cnf';x2.write(use,nv,changed)
        prep=time.perf_counter()-start
        p=None;remaining=CAP-prep
        if remaining>0:
            cmd=([str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),'--seed='+str(s),str(use.resolve())] if mode=='kissat' else [str(pathlib.Path('mre_x4/bin/native').resolve()),str(use.resolve()),'x_native',str(s)])
            try:p=subprocess.run(cmd,capture_output=True,text=True,errors='replace',env=env,timeout=remaining)
            except subprocess.TimeoutExpired:pass
        elapsed=time.perf_counter()-start
        if p is not None:
            if mode=='kissat':
                need(p.returncode in (10,20),'Kissat failed '+p.stderr[-300:])
                status='SAT' if p.returncode==10 else 'UNSAT'
                need(('s SATISFIABLE' if status=='SAT' else 's UNSATISFIABLE') in p.stdout,'missing Kissat verdict')
                for line in p.stdout.splitlines():
                    if line.startswith('v '):
                        for l in map(int,line[2:].split()):
                            if l:
                                need(abs(l) not in model or model[abs(l)]==(l>0),'inconsistent model')
                                model[abs(l)]=l>0
            else:
                need(p.returncode==0,'CMS crashed '+p.stderr[-300:])
                gate=x6.x4.base.parse_gate(p.stdout,'x_native')
                need(not gate['applied'],'backend changed CNF')
                status,model,stats=x6.x4.base.cms.parsed_native(p.stdout)
        if elapsed>CAP or status not in ('SAT','UNSAT'):status='TIMEOUT'
        verified=False
        if status=='SAT':x6.x4.base.cms.verify_model(src,model);verified=True
    return dict(protocol=PROTO,gbd=c['gbd'],sha256=c['sha256'],rep=rep,seed=s,seed_policy='sha256_low31_repair_v2',mode=mode,status=status,elapsed_s=round(elapsed,6),preprocessing_s=round(prep,6),PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),SAT_original_verified=verified,UNSAT_independent_LRAT=False,native_stats=stats,binary_sha256=sha(pathlib.Path('built/bin/kissat_4_0_4' if mode=='kissat' else 'mre_x4/bin/native').read_bytes()))
def shard(idx):
    m=verify();need(idx in range(SHARDS),'bad shard');c=m['cases'][idx];rows=[]
    for rep in range(REPS):
        order=list(MODES);random.Random(seed(c,rep)).shuffle(order)
        for mode in order:
            r=trial(c,rep,mode);rows.append(r)
            save(ROOT/('shard-%d.json'%idx),rows)
            print('X6F_TRIAL',json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==18,'short shard');print('X6F_SHARD_PASS',idx,18,flush=True)
def audit():
    m=verify();rows=[];seen=set();bysha={c['sha256']:c for c in m['cases']}
    for i in range(SHARDS):rows+=json.loads((ROOT/('shard-%d.json'%i)).read_text())
    need(len(rows)==144,'missing trials')
    for r in rows:
        c=bysha.get(r['sha256']);need(c and c['gbd']==r['gbd'],'unknown source')
        need(r['protocol']==PROTO and r['rep'] in range(REPS) and r['mode'] in MODES and r['seed']==seed(c,r['rep']),'not paired')
        k=(r['sha256'],r['rep'],r['mode']);need(k not in seen,'duplicate trial');seen.add(k)
        need(r['status'] in ('SAT','UNSAT','TIMEOUT'),'bad verdict')
        need(r['status']!='SAT' or r['SAT_original_verified'],'no witness')
        need(r['status']!='TIMEOUT' or r['PAR2_s']==16,'bad penalty')
        need(r['status']=='TIMEOUT' or (r['elapsed_s']<=CAP and r['PAR2_s']==r['elapsed_s']),'bad solved time')
    per_source=[]
    for c in m['cases']:
        rs=[r for r in rows if r['sha256']==c['sha256']]
        verdicts={r['status'] for r in rs if r['status']!='TIMEOUT'}
        need(len(verdicts)<=1,'SAT/UNSAT contradiction')
        kissat_unsat=any(r['mode']=='kissat' and r['status']=='UNSAT' for r in rs)
        cms_unsat=any(r['mode']!='kissat' and r['status']=='UNSAT' for r in rs)
        for r in rs:
            r['UNSAT_cross_solver_agreement_no_LRAT']=(r['status']=='UNSAT' and kissat_unsat and cms_unsat)
            r['accepted_solved']=r['status']=='SAT' or r['UNSAT_cross_solver_agreement_no_LRAT']
            if not r['accepted_solved']:r['PAR2_s']=16.0
        per_source.append(dict(gbd=c['gbd'],sha256=c['sha256'],PAR2_s={mode:round(sum(r['PAR2_s'] for r in rs if r['mode']==mode),6) for mode in MODES},solved={mode:sum(r['accepted_solved'] for r in rs if r['mode']==mode) for mode in MODES}))
    scores={}
    for mode in MODES:
        rs=[r for r in rows if r['mode']==mode]
        scores[mode]=dict(n=len(rs),solved=sum(r['accepted_solved'] for r in rs),PAR2_s=round(sum(r['PAR2_s'] for r in rs),6))
    for mode,v in scores.items():
        v['speedup_vs_original']=round(scores['original']['PAR2_s']/v['PAR2_s'],6)
        v['speedup_vs_kissat']=round(scores['kissat']['PAR2_s']/v['PAR2_s'],6)
    by_shard=[dict(shard=i,gbd=m['cases'][i]['gbd'],PAR2_s=per_source[i]['PAR2_s'],solved=per_source[i]['solved']) for i in range(SHARDS)]
    out=dict(protocol=PROTO,source_count=8,trials=144,cap_s=CAP,repetitions=REPS,score=scores,per_source=per_source,per_shard=by_shard,preprocessing_included=True,no_bounded_diagnostics=True,UNSAT_independent_LRAT=False,UNSAT_requires_cross_solver_for_scoring=True,globally_exhaustive_history_not_guaranteed=True,no_auto_promotion=True,rows=rows)
    save(ROOT/'report.json',out)
    print('X6F_FINAL',json.dumps({k:v for k,v in out.items() if k not in ('rows','per_source','per_shard')},sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('freeze','verify','shard','audit','selftest'));p.add_argument('--shard',type=int,default=0);a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='verify':verify();print('X6F_VERIFY_PASS',flush=True)
    elif a.action=='shard':shard(a.shard)
    elif a.action=='selftest':x6.install();x6.x4.selftest();print('X6F_SELFTEST_PASS',flush=True)
    else:audit()
if __name__=='__main__':main()
