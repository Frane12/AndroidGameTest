#!/usr/bin/env python3
"""DRNAS XX: source-only duplicate gate, matched original SHA E2E experiment.

12 frozen XX-only fresh official 2024-25 Main Track sources are selected
by metadata/size and SHA salt ONLY, with no XX solver runtime prescreening.
Six X11 duplicate-positive and six duplicate-zero sources are separate
predeclared DEVELOPMENT replay controls; never count them as fresh.
7 arms x 2 paired seeds x 24 sources = 336 E2E trials (10s cap).
SAT witnesses verified against original CNF; UNSAT needs independent solver
agreement for scoring (not an independently verified LRAT proof).
All measured preprocessing and verification overhead is included in PAR2.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,re,subprocess,tempfile,time
import urllib.parse,urllib.request
import mre_x11_placebo_causal as x11
import mre6b_blind_freeze as prior

ROOT=pathlib.Path('mre_xx')
PROTO='DRNAS-XX-SOURCE-GATE-12FRESH-12REPLAY-7ARM-2SEED-10S-E2E-20261109-v1'
SALT='DRNAS-XX-20261109-SOURCE-ONLY-SALT-FROZEN-v1'
YEARS=('2024','2025')
MODES=('original','scan_placebo','rewrite_identity','front100',
       'gated_dup','kissat','cadical')
CAP=10.0
REPS=2
FRESH_PER_YEAR=6
FRESH=12
REPLAY_POS=6
REPLAY_ZERO=6
TARGET=24
SHARDS=8
MAX_FETCH_PER_YEAR=100
MAX_RAW=6*1024*1024
MAX_PLAIN=9*1024*1024
MAX_VARS=30000
MAX_CLAUSES=85000

def need(ok,msg):
    if not ok:raise RuntimeError('XX_FAIL_CLOSED '+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def save(path,val):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(val,indent=2,sort_keys=True)+'\n')
def seed(c,rep):return x11.seed(c,rep)

def get(url,limit,seconds=35):
    q=urllib.request.Request(url,headers={'User-Agent':'DRNAS-XX-Research-Original-SHA/1.0'})
    with urllib.request.urlopen(q,timeout=seconds) as f:data=f.read(limit+1)
    need(len(data)<=limit,'metadata or CNF download exceeds hard limit')
    return data

def get_index(year):
    if year=='2024':
        url='https://raw.githubusercontent.com/satcompetition/2024/main/downloads/meta.csv'
        raw=get(url,150000,35)
        ids=[line.split()[0] for line in raw.decode().splitlines()[1:] if line.split()]
    else:
        need(year=='2025','unsupported frozen competition year')
        url='https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri'
        raw=get(url,150000,35)
        ids=[line.rsplit('/',1)[-1].strip() for line in raw.decode().splitlines() if line.strip()]
    need(len(ids)>=350 and all(re.fullmatch('[a-f0-9]{32}',g) for g in ids),
         'official original GBD source index unexpected '+year)
    need(len(ids)==len(set(ids)),'GBD duplicate in official index '+year)
    return ids,dict(index_url=url,index_sha256=sha(raw),source_count=len(ids))

def full_structure(path,n,m):
    return x11.full_structure(path,n,m)

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    oldm=json.loads(pathlib.Path('mre_x11/manifest.json').read_text())
    olds=json.loads(pathlib.Path('mre_x11/structure.json').read_text())['sources']
    need(len(oldm['cases'])==32 and len(olds)==32,'X11 original source inventory missing')
    case_by_sha={c['sha256']:c for c in oldm['cases']}
    need(len(case_by_sha)==32,'duplicate X11 original SHA')
    need({x['sha256'] for x in olds}==set(case_by_sha),'X11 structure pairing drift')
    pos=sorted((s for s in olds if s['duplicate_count']>0),
               key=lambda s:sha((SALT+'|replay-positive|'+s['sha256']).encode()))
    neg=sorted((s for s in olds if s['duplicate_count']==0),
               key=lambda s:sha((SALT+'|replay-zero|'+s['sha256']).encode()))
    need(len(pos)==REPLAY_POS and len(neg)>=REPLAY_ZERO,
         'unexpected X11 positive/negative control cohort')
    selected=[]; seen_sha=set(); seen_gbd=set();structures=[]
    for cohort,pool,quota in (('x11_dup_replay',pos,REPLAY_POS),
                              ('x11_zero_replay',neg,REPLAY_ZERO)):
        for s in pool[:quota]:
            c=case_by_sha[s['sha256']]
            raw=(pathlib.Path('mre_x11')/c['filename']).read_bytes()
            need(sha(raw)==c['sha256'],'X11 original SHA changed')
            dst=ROOT/(c['gbd']+'.cnf');dst.write_bytes(raw)
            rec=dict(gbd=c['gbd'],sha256=c['sha256'],filename=dst.name,
                     vars=c['vars'],clauses=c['clauses'],bytes=len(raw),
                     cohort=cohort,source='X11 original prepared development replay',
                     screen_by_XX_runtime=False)
            selected.append(rec);structures.append(dict(
                gbd=c['gbd'],sha256=c['sha256'],cohort=cohort,**full_structure(
                    dst,c['vars'],c['clauses'])))
            seen_sha.add(c['sha256']);seen_gbd.add(c['gbd'])
    indexes={};ranked={};allids=set()
    for year in YEARS:
        ids,meta=get_index(year)
        indexes[year]=meta
        ranked[year]=ids;allids.update(ids)
    repo_ids,old_repo_sha=prior.inspect_repo_ids(allids)
    history=set(s.strip() for s in prior.PRIOR.read_text().splitlines()
                if re.fullmatch('[a-f0-9]{32}',s.strip()))
    # Precommit exclusion of all 2025 R82 top-220 candidates, including failed fetches.
    r82=set(sorted(ranked['2025'],key=lambda g:sha(
        ('DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2025/'+g).encode()))[:220])
    exclude=seen_gbd|history|repo_ids|r82
    # Exclude prior R82 precommit block (regardless of whether downloaded).
    for year in YEARS:
        ranked[year]=sorted((g for g in ranked[year] if g not in exclude),
            key=lambda g:sha((SALT+'|'+year+'|'+g).encode()))
    trace=[];fresh_count=collections.Counter()
    prior.r32p.CNF_LIMIT=MAX_PLAIN
    for year in YEARS:
        for rank,gbd in enumerate(ranked[year][:MAX_FETCH_PER_YEAR]):
            if fresh_count[year]>=FRESH_PER_YEAR:break
            item=dict(year=year,rank=rank,gbd=gbd)
            dst=ROOT/(gbd+'.cnf')
            try:
                packed=get('https://benchmark-database.de/file/'+gbd,
                           MAX_RAW,seconds=30)
                plain,encoding=prior.r32p.decode(packed)
                need(len(plain)<=MAX_PLAIN,'decompressed CNF size')
                n,m=prior.r32p.parse_dimacs_metadata(plain)
                need(0<n<=MAX_VARS and 0<m<=MAX_CLAUSES,
                     'resource geometry limit')
                digest=sha(plain)
                need(digest not in seen_sha and digest not in old_repo_sha,
                     'historical source SHA overlap')
                dst.write_bytes(plain)
                stats=full_structure(dst,n,m)
                selected.append(dict(gbd=gbd,sha256=digest,filename=dst.name,
                     vars=n,clauses=m,bytes=len(plain),year=year,
                     cohort='fresh_official_'+year,
                     source='https://benchmark-database.de/file/'+gbd,
                     historical_exclusion_not_exhaustive=True,
                     no_runtime_screen=True,compression=encoding))
                structures.append(dict(gbd=gbd,sha256=digest,
                     cohort='fresh_official_'+year,**stats))
                seen_sha.add(digest);seen_gbd.add(gbd);fresh_count[year]+=1
                item.update(action='frozen_before_solver',sha256=digest,
                            vars=n,clauses=m,bytes=len(plain),
                            duplicate_count=stats['duplicate_count'])
            except Exception as ex:
                dst.unlink(missing_ok=True)
                item.update(action='input_unavailable_or_out_of_precommitted_bounds',
                            error=(type(ex).__name__+': '+str(ex))[:180])
            trace.append(item)
            print('XX_SOURCE_SCAN',json.dumps(item,sort_keys=True),flush=True)
        need(fresh_count[year]==FRESH_PER_YEAR,
             'insufficient untested original sources for '+year)
    need(len(selected)==TARGET and len(seen_sha)==TARGET,
         'XX source cardinality or SHA collision')
    # Precommitted decision: structural feature only; never source name/GBD/score.
    decisions=[]
    for c,s in zip(selected,structures):
        need(c['sha256']==s['sha256'],'feature pairing incorrect')
        decisions.append(dict(gbd=c['gbd'],sha256=c['sha256'],
            cohort=c['cohort'],select='front100' if s['duplicate_count'] else 'original',
            duplicates=s['duplicate_count']))
    save(ROOT/'structure.json',dict(protocol=PROTO,sources=structures))
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=selected,
         modes=MODES,reps=REPS,cap_s=CAP,
         expected_trials=TARGET*REPS*len(MODES),expected_sources=TARGET,
         x11_original_run=42563452186,development_replay_sources=12,
         new_official_2024_2025_originals=12,source_index=indexes,
         declared_exclusion_count=len(exclude),
         source_selection='salted official GBD + independent minisat1m metadata; resource-size bounds only; never XX runtimes or gate features',
         no_runtime_prescreen=True,not_globally_blind=True,
         no_independent_unsat_LRAT=True,no_auto_promotion=True,
         gate_policy='full original CNF canonical duplicate_count > 0 => front100; otherwise native original',
         decisions=decisions,scan_log=trace))
    print('XX_FROZEN',len(selected),'FRESH',sum(
        c['cohort'].startswith('fresh_official') for c in selected),
        'DUPLICATE_POSITIVE',sum(s['duplicate_count']>0 for s in structures),
        flush=True)

def verify():
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and m['reps']==REPS and m['cap_s']==CAP and
         m['modes']==list(MODES) and m['expected_trials']==336 and
         len(m['cases'])==TARGET,'XX protocol drift')
    for c in m['cases']:
        need(sha((ROOT/c['filename']).read_bytes())==c['sha256'],
             'frozen original source drift '+c['gbd'])
    return m

def select(clauses):
    return 'front100' if x11.x9.x6.x3.duplicates(clauses) else 'original'

def trial(c,rep,mode):
    need(rep in range(REPS) and mode in MODES,'unexpected trial')
    src=ROOT/c['filename'];s=seed(c,rep)
    env=os.environ.copy();env.pop('DRNAS_MAX_CONFLICTS',None)
    status='TIMEOUT';raw='TIMEOUT';model={};stats=None;verified=False
    choice=mode;duplicate_count=None
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        start=time.perf_counter(); use=src
        if mode in ('scan_placebo','gated_dup'):
            nv,clauses=x11.x9.x2.parse(src)
            duplicate_count=len(x11.x9.x6.x3.duplicates(clauses))
            choice='front100' if duplicate_count else 'original'
            if mode=='scan_placebo':choice='original'
            if choice=='front100':
                transformed=x11.transform(clauses,'front100')
                need(collections.Counter(clauses)==collections.Counter(transformed),
                     'gate mutated raw clause multiset')
                use=pathlib.Path(td)/'ordered.cnf'
                x11.x9.x2.write(use,nv,transformed)
        elif mode in ('front100','rewrite_identity'):
            nv,clauses=x11.x9.x2.parse(src)
            transformed=x11.transform(clauses,mode)
            need(collections.Counter(clauses)==collections.Counter(transformed),
                 'raw clause multiset changed')
            if mode=='rewrite_identity':
                need(transformed==clauses,'placebo identity ordering changed')
            use=pathlib.Path(td)/'ordered.cnf'
            x11.x9.x2.write(use,nv,transformed)
        prep=time.perf_counter()-start
        if CAP-prep>0:
            if mode=='kissat':
                cmd=[str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),
                     '--seed='+str(s),str(use.resolve())]
            elif mode=='cadical':
                cmd=['/usr/bin/cadical',str(use.resolve())]
            else:
                cmd=[str(pathlib.Path('mre_x4/bin/native').resolve()),
                     str(use.resolve()),'x_native',str(s)]
            try:
                p=subprocess.run(cmd,capture_output=True,text=True,
                                 errors='replace',env=env,timeout=CAP-prep)
            except subprocess.TimeoutExpired:p=None
            if p is not None:
                if mode in ('kissat','cadical'):
                    need(p.returncode in (10,20),
                         'reference exit code '+mode+' '+p.stderr[-350:])
                    status='SAT' if p.returncode==10 else 'UNSAT'
                    need(('s SATISFIABLE' if status=='SAT' else 's UNSATISFIABLE') in p.stdout,
                         'solver status-output mismatch')
                    for line in p.stdout.splitlines():
                        if line.startswith('v '):
                            for lit in map(int,line[2:].split()):
                                if lit:
                                    need(abs(lit) not in model or
                                         model[abs(lit)]==(lit>0),
                                         'SAT model contradictory literals')
                                    model[abs(lit)]=lit>0
                else:
                    need(p.returncode==0,'native exit '+p.stderr[-350:])
                    g=x11.x9.x6.x4.base.parse_gate(p.stdout,'x_native')
                    need(not g['applied'],'backend unexpectedly changed CNF')
                    status,model,stats=x11.x9.x6.x4.base.cms.parsed_native(p.stdout)
                if status=='SAT':
                    x11.x9.x6.x4.base.cms.verify_model(src,model)
                    verified=True
        elapsed=time.perf_counter()-start
        raw=status
        if elapsed>CAP or status not in ('SAT','UNSAT'):status='TIMEOUT'
    binary=('/usr/bin/cadical' if mode=='cadical'
        else 'built/bin/kissat_4_0_4' if mode=='kissat'
        else 'mre_x4/bin/native')
    return dict(protocol=PROTO,gbd=c['gbd'],sha256=c['sha256'],
       cohort=c['cohort'],rep=rep,seed=s,mode=mode,selected=choice,
       duplicate_count=duplicate_count,
       status=status,raw_status=raw,elapsed_s=round(elapsed,6),
       preprocessing_s=round(prep,6),
       PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),
       SAT_original_verified=verified,UNSAT_independent_LRAT=False,
       native_stats=stats,binary_sha256=sha(pathlib.Path(binary).read_bytes()),
       independent_seed_applied=(mode!='cadical'))

def shard(idx):
    m=verify();need(idx in range(SHARDS),'shard index invalid')
    cases=[c for i,c in enumerate(m['cases']) if i%SHARDS==idx]
    need(len(cases)==3,'expected three distinct originals per shard')
    rows=[]
    for c in cases:
        for rep in range(REPS):
            arms=list(MODES);random.Random(seed(c,rep)).shuffle(arms)
            for mode in arms:
                row=trial(c,rep,mode)
                rows.append(row);save(ROOT/('shard-%d.json'%idx),rows)
                print('XX_TRIAL',json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==42,'XX shard truncated')
    print('XX_SHARD_PASS',idx,42,flush=True)

def audit():
    m=verify();rows=[];seen=set();bysha={c['sha256']:c for c in m['cases']}
    structure={c['sha256']:c for c in json.loads((ROOT/'structure.json').read_text())['sources']}
    for i in range(SHARDS):
        rows+=json.loads((ROOT/('shard-%d.json'%i)).read_text())
    need(len(rows)==m['expected_trials']==336,'not 336 complete E2E rows')
    for row in rows:
        c=bysha.get(row['sha256'])
        need(c and c['gbd']==row['gbd'] and row['protocol']==PROTO and
             row['mode'] in MODES and row['rep'] in range(REPS) and
             row['seed']==seed(c,row['rep']),'SHA/GBD/seed pair invalid')
        key=(row['sha256'],row['mode'],row['rep'])
        need(key not in seen,'duplicate source-arm-seed');seen.add(key)
        need(row['status'] in ('SAT','UNSAT','TIMEOUT'),'invalid status')
        need(row['status']!='SAT' or row['SAT_original_verified'],
             'SAT original witness not checked')
        need(row['status']!='TIMEOUT' or row['PAR2_s']==2*CAP,
             'incorrect PAR2 timeout')
        need(row['status']=='TIMEOUT' or
             (row['elapsed_s']<=CAP and row['PAR2_s']==row['elapsed_s']),
             'incorrect E2E elapsed time or cap')
        if row['mode'] in ('gated_dup','scan_placebo'):
            count=structure[c['sha256']]['duplicate_count']
            need(row['duplicate_count']==count,'gate structural feature drift')
            choice=('front100' if count else 'original') if row['mode']=='gated_dup' else 'original'
            need(row['selected']==choice,'gate policy changed')
    per_source=[]
    for c in m['cases']:
        rr=[r for r in rows if r['sha256']==c['sha256']]
        verdicts={r['status'] for r in rr if r['status']!='TIMEOUT'}
        need(len(verdicts)<=1,'SAT UNSAT contradiction on original CNF')
        cms_unsat=any(r['mode'] not in ('kissat','cadical') and r['status']=='UNSAT' for r in rr)
        ref_unsat=any(r['mode'] in ('kissat','cadical') and r['status']=='UNSAT' for r in rr)
        for r in rr:
            r['UNSAT_cross_solver_agreement_no_LRAT']=(
                r['status']=='UNSAT' and cms_unsat and ref_unsat)
            r['accepted_solved']=(r['status']=='SAT' or
                                  r['UNSAT_cross_solver_agreement_no_LRAT'])
            r['audited_PAR2_s']=r['PAR2_s'] if r['accepted_solved'] else 2*CAP
        scores={mode:round(sum(r['audited_PAR2_s'] for r in rr
                             if r['mode']==mode),6) for mode in MODES}
        per_source.append(dict(gbd=c['gbd'],sha256=c['sha256'],cohort=c['cohort'],
            duplicates=structure[c['sha256']]['duplicate_count'],
            PAR2_s=scores,gain_gate_vs_original=round(scores['original']-scores['gated_dup'],6)))
    cohorts={'all':lambda r:True,
             'fresh_only':lambda r:r['cohort'].startswith('fresh_official_'),
             'x11_dup_replay':lambda r:r['cohort']=='x11_dup_replay',
             'x11_zero_replay':lambda r:r['cohort']=='x11_zero_replay'}
    score={}
    for cohort,pred in cohorts.items():
        d={}
        for mode in MODES:
            a=[r for r in rows if r['mode']==mode and pred(r)]
            d[mode]=dict(n=len(a),PAR2_s=round(sum(r['audited_PAR2_s'] for r in a),6),
                solved=sum(r['accepted_solved'] for r in a),
                timeouts=sum(r['status']=='TIMEOUT' for r in a),
                preprocessing_s=round(sum(r['preprocessing_s'] for r in a),6))
        for mode in MODES:
            for baseline in ('original','kissat','cadical','scan_placebo'):
                total=d[baseline]['PAR2_s'];act=d[mode]['PAR2_s']
                d[mode]['speedup_vs_'+baseline]=round(total/act,6) if act else 1
                d[mode]['pct_less_PAR2_vs_'+baseline]=round(
                    100*(1-act/total),5) if total else 0
        score[cohort]=d
    gains=sorted((p['gain_gate_vs_original'] for p in per_source),reverse=True)
    winners={}
    for mode in ('scan_placebo','rewrite_identity','front100','gated_dup'):
        ct=collections.Counter()
        for p in per_source:
            a=p['PAR2_s'][mode];b=p['PAR2_s']['original']
            ct['wins' if a<b-0.001 else 'losses' if a>b+0.001 else 'ties']+=1
        winners[mode]=dict(ct)
    result=dict(protocol=PROTO,trials=len(rows),sources=len(m['cases']),
       score=score,wins_vs_original=winners,
       gate_applied_source_count=sum(p['duplicates']>0 for p in per_source),
       fresh_gate_applied_count=sum(p['duplicates']>0 and
           p['cohort'].startswith('fresh_official_') for p in per_source),
       gate_gain_without_best_single_source_s=round(sum(gains[1:]),6),
       gate_gain_without_best_two_sources_s=round(sum(gains[2:]),6),
       exact_original_clause_multiset_preserved=True,
       full_source_scan_and_verification_timed=True,
       SAT_witness_on_original_verified=True,UNSAT_independent_LRAT=False,
       development_replay_vs_fresh_separate=True,
       not_globally_blind=True,no_auto_promotion=True)
    save(ROOT/'report.json',dict(result,per_source=per_source,rows=rows))
    print('XX_FINAL',json.dumps(result,sort_keys=True),flush=True)

def selftest():
    src=[(1,2),(1,2),(-1,3),(4,),(-1,3),(2,3)]
    no=[(1,2),(-1,3),(4,)]
    need(select(src)=='front100' and select(no)=='original',
         'duplicate selector truth table')
    need(collections.Counter(x11.transform(src,'front100'))==collections.Counter(src),
         'duplicate-front multiset identity')
    need(collections.Counter(x11.transform(no,'front100'))==collections.Counter(no),
         'no-duplicate multiset identity')
    need(len(MODES)==7 and TARGET*REPS*len(MODES)==336,'frozen protocol size')
    print('XX_SELFTEST_PASS',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('freeze','verify','shard','audit','selftest'))
    p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='verify':verify();print('XX_VERIFY_PASS',flush=True)
    elif a.action=='shard':shard(a.shard)
    elif a.action=='audit':audit()
    else:selftest()
if __name__=='__main__':main()
