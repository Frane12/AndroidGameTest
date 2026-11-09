#!/usr/bin/env python3
"""DRNAS X11. A causal placebo/control test of exact CNF clause ordering.
32 unchanged previously prepared original SAT formulas, frozen SHA and binary,
7 arms x 2 seeds, 15s end-to-end PAR2 including preprocessing and model check.

The identity rewrite arm is critical: it parses and re-emits exactly the same
ordered clause sequence. Differences between front100 and identity rewrite
isolate changed clause order instead of accidentally rewarding DIMACS rewrite.
Not blind: 30 formulas already in X9; 2 reserved originals timeout in X10.
No auto-promotion, no independent UNSAT LRAT, cross-solver scoring mandatory.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,os,pathlib,random,subprocess,tempfile,time
import mre_x9_blind_causal as x9

ROOT=pathlib.Path('mre_x11')
SOURCE=pathlib.Path('priorx10/mre_x10')
PROTO='DRNAS-X11-PLACEBO-32SHA-7ARM-2SEED-15S-E2E-20261109-v1'
MODES=('original','rewrite_identity','front50','front100',
       'spread_shifted','kissat','cadical')
CAP=15.0
REPS=2
TARGET=32
SHARDS=8
def need(ok,msg):
    if not ok:raise RuntimeError('X11_FAIL_CLOSED '+msg)
def sha(v):return hashlib.sha256(v).hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
def seed(c,rep):return x9.seed(c,rep)

def full_structure(src,n,m):
    nv,clauses=x9.x2.parse(src)
    need(nv==n and len(clauses)==m,'source geometry mismatch')
    idx=x9.x6.x3.duplicates(clauses)
    all_count=len(idx)
    avg_len=sum(len(c) for c in clauses)/max(1,len(clauses))
    dist=[0]*10
    for i in idx:dist[min(9,int(10*i/max(1,m)))]+=1
    widths=collections.Counter(len(clauses[i]) for i in idx)
    front_frac=sum(i<max(1,len(clauses)//4) for i in idx)/max(1,len(idx))
    return dict(duplicate_count=all_count,
       duplicate_ratio=round(all_count/max(1,len(clauses)),7),
       duplicate_decile_counts=dist,
       duplicate_front_quarter_fraction=round(front_frac,7),
       duplicate_binary_count=widths[2],
       duplicate_ternary_count=widths[3],
       mean_clause_width=round(avg_len,5),
       vars=nv,clauses=len(clauses))

def transform(clauses,mode):
    if mode=='rewrite_identity':return list(clauses)
    if mode in ('front100','spread_shifted'):
        return x9.x6.transform(clauses,mode)
    need(mode=='front50','not a transform mode')
    idx=x9.x6.x3.duplicates(clauses)
    count=(len(idx)+1)//2
    selected=set(idx[:count])
    out=[clauses[i] for i in idx[:count]]
    out.extend(c for i,c in enumerate(clauses) if i not in selected)
    need(collections.Counter(out)==collections.Counter(clauses),
         'front50 changed multiset')
    return out

def freeze():
    ROOT.mkdir(exist_ok=True)
    p=SOURCE/'manifest.json'
    need(p.is_file(),'missing X10 prepared source manifest')
    m=json.loads(p.read_text())
    need(m['source_count'] if 'source_count' in m else len(m['cases'])==TARGET,
         'missing X10 sources')
    need(len(m['cases'])==TARGET and m['expected_trials']==384,
         'unexpected X10 source count/protocol')
    source_rows=[];structure=[];seen=set()
    for c in m['cases']:
        raw=(SOURCE/c['filename']).read_bytes()
        need(sha(raw)==c['sha256'] and c['sha256'] not in seen,
             'prepared source not SHA-frozen')
        seen.add(c['sha256'])
        dst=ROOT/c['filename'];dst.write_bytes(raw)
        source_rows.append(dict(c))
        stats=full_structure(dst,c['vars'],c['clauses'])
        structure.append(dict(gbd=c['gbd'],sha256=c['sha256'],
                              cohort=c['cohort'],**stats))
    need(len(source_rows)==TARGET,'source mismatch')
    save(ROOT/'structure.json',dict(protocol=PROTO,sources=structure))
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=source_rows,
      modes=MODES,cap_s=CAP,reps=REPS,expected_trials=TARGET*REPS*len(MODES),
      predecessor_X10=42561615100,predecessor_X9=42559879920,
      prior_X10_manifest_sha256=sha(p.read_bytes()),
      expected_sha_sources=TARGET,already_known_replay=True,not_blind=True,
      source_sha_locked=True,
      causal_question='Order vs identical DIMACS rewrite placebo',
      no_auto_promotion=True))
    print('X11_FROZEN',len(source_rows),flush=True)
    print('X11_STRUCTURE',json.dumps(dict(
      duplicate_positive=sum(x['duplicate_count']>0 for x in structure),
      zero_duplicate=sum(x['duplicate_count']==0 for x in structure),
      duplicate_density_top=sorted([{
        'gbd':x['gbd'],'duplicate_count':x['duplicate_count'],
        'ratio':x['duplicate_ratio']} for x in structure],
        key=lambda v:-v['ratio'])[:8]),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/'manifest.json').read_text())
    need(m['protocol']==PROTO and m['modes']==list(MODES) and
         m['expected_trials']==448 and m['cap_s']==CAP and
         m['reps']==REPS and len(m['cases'])==TARGET,'protocol drift')
    for c in m['cases']:
        need(sha((ROOT/c['filename']).read_bytes())==c['sha256'],
             'original CNF SHA drift')
    return m

def trial(c,rep,mode):
    need(mode in MODES and rep in range(REPS),'unexpected trial arm')
    src=ROOT/c['filename'];s=seed(c,rep)
    env=os.environ.copy();env.pop('DRNAS_MAX_CONFLICTS',None)
    status='TIMEOUT';raw_status='TIMEOUT';model={};stats=None
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        start=time.perf_counter();use=src
        if mode in ('rewrite_identity','front50','front100','spread_shifted'):
            n,clauses=x9.x2.parse(src)
            changed=transform(clauses,mode)
            need(collections.Counter(clauses)==collections.Counter(changed),
                 'literal+clause multiset changed')
            if mode=='rewrite_identity':
                need(changed==clauses,'identity placebo changed ordering')
            use=pathlib.Path(td)/'rewritten.cnf'
            x9.x2.write(use,n,changed)
        prep=time.perf_counter()-start
        p=None;remaining=CAP-prep
        if remaining>0:
            if mode=='kissat':
                cmd=[str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),
                     '--seed='+str(s),str(use.resolve())]
            elif mode=='cadical':cmd=['/usr/bin/cadical',str(use.resolve())]
            else:cmd=[str(pathlib.Path('mre_x4/bin/native').resolve()),
                      str(use.resolve()),'x_native',str(s)]
            try:p=subprocess.run(cmd,capture_output=True,text=True,
                                 errors='replace',env=env,timeout=remaining)
            except subprocess.TimeoutExpired:pass
        elapsed=time.perf_counter()-start
        if p is not None:
            if mode in ('kissat','cadical'):
                need(p.returncode in (10,20),
                     'reference failed '+mode+' '+p.stderr[-300:])
                status='SAT' if p.returncode==10 else 'UNSAT'
                need(('s SATISFIABLE' if status=='SAT' else 's UNSATISFIABLE')
                     in p.stdout,'reference verdict mismatch')
                for line in p.stdout.splitlines():
                    if line.startswith('v '):
                        for lit in map(int,line[2:].split()):
                            if lit:
                                need(abs(lit) not in model or
                                     model[abs(lit)]==(lit>0),
                                     'inconsistent reference model')
                                model[abs(lit)]=lit>0
            else:
                need(p.returncode==0,'native crash '+p.stderr[-300:])
                gate=x9.x6.x4.base.parse_gate(p.stdout,'x_native')
                need(not gate['applied'],'native backend unexpectedly changed CNF')
                status,model,stats=x9.x6.x4.base.cms.parsed_native(p.stdout)
        raw_status=status
        if elapsed>CAP or status not in ('SAT','UNSAT'):status='TIMEOUT'
        verified=False
        if status=='SAT':
            x9.x6.x4.base.cms.verify_model(src,model);verified=True
    binary=('/usr/bin/cadical' if mode=='cadical'
            else 'built/bin/kissat_4_0_4' if mode=='kissat'
            else 'mre_x4/bin/native')
    return dict(protocol=PROTO,gbd=c['gbd'],sha256=c['sha256'],
       cohort=c['cohort'],rep=rep,seed=s,mode=mode,status=status,
       raw_status=raw_status,elapsed_s=round(elapsed,6),
       preprocessing_s=round(prep,6),
       PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),
       SAT_original_verified=verified,UNSAT_independent_LRAT=False,
       native_stats=stats,binary_sha256=sha(pathlib.Path(binary).read_bytes()),
       independent_seed_applied=(mode!='cadical'))

def shard(idx):
    m=verify();need(idx in range(SHARDS),'invalid shard')
    cases=[c for i,c in enumerate(m['cases']) if i%SHARDS==idx]
    need(len(cases)==4,'case sharding drift')
    rows=[]
    for c in cases:
        for rep in range(REPS):
            arms=list(MODES);random.Random(seed(c,rep)).shuffle(arms)
            for mode in arms:
                row=trial(c,rep,mode);rows.append(row)
                save(ROOT/('shard-%d.json'%idx),rows)
                print('X11_TRIAL',json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==56,'short shard')
    print('X11_SHARD_PASS',idx,56,flush=True)

def audit():
    m=verify();rows=[];seen=set();bysha={c['sha256']:c for c in m['cases']}
    for i in range(SHARDS):
        rows+=json.loads((ROOT/('shard-%d.json'%i)).read_text())
    need(len(rows)==m['expected_trials']==448,'missing end-to-end rows')
    for r in rows:
        c=bysha.get(r['sha256'])
        need(c and r['gbd']==c['gbd'] and r['mode'] in MODES and
             r['protocol']==PROTO and r['rep'] in range(REPS) and
             r['seed']==seed(c,r['rep']),'unmatched SHA seed or protocol')
        key=(r['sha256'],r['mode'],r['rep'])
        need(key not in seen,'duplicate measurement');seen.add(key)
        need(r['status'] in ('SAT','UNSAT','TIMEOUT'),'unknown verdict')
        need(r['status']!='SAT' or r['SAT_original_verified'],
             'missing original SAT witness')
        need(r['status']!='TIMEOUT' or r['PAR2_s']==2*CAP,
             'wrong timeout PAR2 penalty')
        need(r['status']=='TIMEOUT' or
             (r['elapsed_s']<=CAP and r['PAR2_s']==r['elapsed_s']),
             'invalid E2E solved PAR2')
    per_source=[];features={x['sha256']:x for x in
        json.loads((ROOT/'structure.json').read_text())['sources']}
    for c in m['cases']:
        rs=[r for r in rows if r['sha256']==c['sha256']]
        verdicts={r['status'] for r in rs if r['status']!='TIMEOUT'}
        need(len(verdicts)<=1,'SAT/UNSAT contradiction')
        cmsunsat=any(r['mode'] not in ('kissat','cadical') and
                     r['status']=='UNSAT' for r in rs)
        refunsat=any(r['mode'] in ('kissat','cadical') and
                     r['status']=='UNSAT' for r in rs)
        for r in rs:
            r['UNSAT_cross_solver_agreement_no_LRAT']=(
              r['status']=='UNSAT' and cmsunsat and refunsat)
            r['accepted_solved']=(r['status']=='SAT' or
                                  r['UNSAT_cross_solver_agreement_no_LRAT'])
            r['audited_PAR2_s']=(r['PAR2_s'] if r['accepted_solved'] else 2*CAP)
        times={mode:round(sum(r['audited_PAR2_s'] for r in rs if
                               r['mode']==mode),6) for mode in MODES}
        per_source.append(dict(gbd=c['gbd'],sha256=c['sha256'],
                               cohort=c['cohort'],structure=features[c['sha256']],
                               PAR2_s=times,
                               gain_front_vs_original=round(
                                  times['original']-times['front100'],6),
                               gain_front_vs_rewrite=round(
                                  times['rewrite_identity']-times['front100'],6)))
    scores={}
    for cohort in ('all','x9_replay','x6_reserved'):
        subset=[r for r in rows if cohort=='all' or r['cohort']==cohort]
        obj={}
        for mode in MODES:
            rs=[r for r in subset if r['mode']==mode]
            obj[mode]=dict(n=len(rs),solved=sum(r['accepted_solved'] for r in rs),
              timeouts=sum(r['status']=='TIMEOUT' for r in rs),
              PAR2_s=round(sum(r['audited_PAR2_s'] for r in rs),6),
              preprocessing_s=round(sum(r['preprocessing_s'] for r in rs),6))
        for mode,v in obj.items():
            for reference in ('original','rewrite_identity','kissat','cadical'):
                b=obj[reference]['PAR2_s'];a=v['PAR2_s']
                v['speedup_vs_'+reference]=round(b/a,6) if a else 1
                v['pct_less_PAR2_vs_'+reference]=round(
                   100*(1-a/b),5) if b else 0
        scores[cohort]=obj
    wins={}
    for mode in ('rewrite_identity','front50','front100','spread_shifted'):
        d=collections.Counter()
        for row in per_source:
            a=row['PAR2_s'][mode];b=row['PAR2_s']['original']
            d['wins' if a<b-0.001 else 'losses' if a>b+0.001 else 'ties']+=1
        wins[mode]=dict(d)
    dups0=[p for p in per_source if
           p['structure']['duplicate_count']==0]
    out=dict(protocol=PROTO,source_count=TARGET,trials=len(rows),
       cap_s=CAP,score=scores,wins_vs_original=wins,
       exact_clause_multiset_preserved=True,
       placebo_identity_rewrite_includes_preprocessing=True,
       source_duplicate_none=len(dups0),
       no_bounded_diagnostics=True,
       SAT_original_witness_replayed=True,
       UNSAT_independent_LRAT=False,
       UNSAT_requires_cross_solver_for_scoring=True,
       x9_x10_prepared_development_not_blind=True,
       no_auto_promotion=True,
       per_source=per_source,rows=rows)
    save(ROOT/'report.json',out)
    print('X11_FINAL',json.dumps({k:v for k,v in out.items()
       if k not in ('per_source','rows')},sort_keys=True),flush=True)

def selftest():
    x9.x6.install();x9.x6.x4.selftest()
    test=[(1,2),(1,2),(-1,3),(-1,3),(1,2),(4,),(-3,4)]
    a=transform(test,'rewrite_identity')
    b=transform(test,'front50')
    c=transform(test,'front100')
    need(a==test,'identity test failed')
    need(collections.Counter(b)==collections.Counter(a) and
         collections.Counter(c)==collections.Counter(a),
         'causal controls changed truth')
    print('X11_SELFTEST_PASS',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('freeze','verify','shard','audit','selftest'))
    p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='verify':verify();print('X11_VERIFY_PASS',flush=True)
    elif a.action=='shard':shard(a.shard)
    elif a.action=='audit':audit()
    else:selftest()
if __name__=='__main__':main()
