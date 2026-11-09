#!/usr/bin/env python3
"""X10: source-only structural early-duplicate gate with X9-out-of-fold training.
30 X9 replay sources: each prediction excludes that source's X9 outcomes.
Two X6-fresh prepared sources excluded from X9: full X9 training, limited holdout.
No source SHA or filename is used as a positive signal. The LOO/exclusion uses
SHA only to prevent leakage, not for prediction.
E2E times include detection, CNF rewrite, model verification and process launch.
This is DEVELOPMENT / prepared source replay, never a globally blind claim.
"""
import argparse, collections, hashlib, json, math, os, pathlib, random
import subprocess, tempfile, time
import mre_x9_blind_causal as x9

ROOT=pathlib.Path('mre_x10')
PROTO='DRNAS-X10-SOURCE-STRUCT-GATE-32SHA-6ARM-2REP-15S-v1'
MODES=('original','front100','spread_shifted','adaptive','kissat','cadical')
CAP=15.0
REPS=2
TARGET=32
SHARDS=8
TRAIN=30
X9_ROOT=pathlib.Path('priorx9/mre_x9')
X9_REPORT=pathlib.Path('priorx9report/mre_x9/report.json')
X6_ROOT=pathlib.Path('priorx6/mre_x6fresh')
FEATURES=('log_vars','log_clauses','log_bytes','clauses_per_var',
          'sample_duplicate_rate','early_duplicate_fraction','binary_rate',
          'ternary_rate','long_rate','mean_width','sample_var_coverage')
def need(v,msg):
    if not v:raise RuntimeError('X10_FAIL_CLOSED '+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def save(path,v):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,sort_keys=True,indent=2)+'\n')
def seed(c,rep):
    return x9.seed(c,rep)  # preserve matched native/Kissat X9 seed policy

def features(src,n,m):
    """Cheap, bounded source-only detector; at most first 48 KiB and 700 clauses."""
    with open(src,'rb') as f:head=f.read(49152)
    seen=set();dups=0;early=0;binary=0;ternary=0;long=0
    total=0;sum_width=0;vars_seen=set();current=[]
    for line in head.splitlines():
        line=line.strip()
        if not line or line.startswith((b'c',b'p',b'%')):continue
        for tok in line.split():
            try:lit=int(tok)
            except ValueError:continue
            if lit==0:
                if not current:continue
                key=tuple(sorted(set(current)))
                width=len(key)
                if key in seen:
                    dups+=1
                    if total<233:early+=1
                seen.add(key)
                binary+=(width==2);ternary+=(width==3);long+=(width>=4)
                sum_width+=width;total+=1
                for v in key:vars_seen.add(abs(v))
                current=[]
                if total>=700:break
            else:current.append(lit)
        if total>=700:break
    need(total>=1,'no valid clauses in bounded structural sample')
    return [math.log1p(n),math.log1p(m),math.log1p(src.stat().st_size),
        min(100.0,m/max(1,n))/100.0,
        dups/total,early/max(1,dups),binary/total,ternary/total,
        long/total,sum_width/total/20.0,min(1.,len(vars_seen)/max(1,n))]

def choose(feat,training,exclude_sha=None):
    """Deterministic k-nearest-source gate. Source's own outcome is excluded."""
    pool=[x for x in training if x['sha256']!=exclude_sha]
    need(len(pool) in (29,30),'training cohort exclusion invalid')
    means=[sum(x['features'][j] for x in pool)/len(pool)
           for j in range(len(FEATURES))]
    std=[max(0.07,(sum((x['features'][j]-means[j])**2 for x in pool)/
                  len(pool))**0.5)
         for j in range(len(FEATURES))]
    neighbors=[]
    for x in pool:
        dist=math.sqrt(sum(((a-b)/scale)**2
                           for a,b,scale in zip(feat,x['features'],std)))
        neighbors.append((dist,x))
    neighbors.sort(key=lambda pair:(pair[0],pair[1]['sha256']))
    five=neighbors[:5]
    weights=[1/(0.5+d) for d,_ in five]
    denom=sum(weights)
    expected={}
    positives={}
    for mode in ('front100','spread_shifted'):
        expected[mode]=sum(w*x['gain_s'][mode] for w,(_,x)
                           in zip(weights,five))/denom
        positives[mode]=sum(x['label']==mode for _,x in five)
    proposed=max(expected,key=lambda k:expected[k])
    accepted=(expected[proposed]>0.60 and positives[proposed]>=2)
    return (proposed if accepted else 'original',
        dict(expected_gain_s={k:round(v,5) for k,v in expected.items()},
             positive_neighbors=positives,nearest_dist=round(five[0][0],5),
             gate_version='bounded48KiB_loso_knn5_conservative_v1'))

def freeze():
    ROOT.mkdir(exist_ok=True)
    manifest=json.loads((X9_ROOT/'manifest.json').read_text())
    report=json.loads(X9_REPORT.read_text())
    need(manifest['protocol']==x9.PROTO and len(manifest['cases'])==TRAIN,
         'prior X9 freeze not same protocol')
    need(report['protocol']==x9.PROTO and report['trials']==300 and
         report['source_count']==30,'prior X9 report not audited')
    bysha={p['sha256']:p for p in report['per_source']}
    need(len(bysha)==TRAIN,'X9 per-source report incomplete')
    originals=[]
    for c in manifest['cases']:
        need(c['sha256'] in bysha,'X9 source missing from report')
        src=X9_ROOT/c['filename'];raw=src.read_bytes()
        need(sha(raw)==c['sha256'],'X9 source SHA mismatch')
        dst=ROOT/(c['gbd']+'.cnf');dst.write_bytes(raw)
        originals.append(dict(c,filename=dst.name,cohort='x9_replay',
                              x9_prior_training=True))
    other=json.loads((X6_ROOT/'manifest.json').read_text())
    need(len(other['cases'])==8,'unexpected X6 frozen cohort count')
    hold=[c for c in other['cases']
          if c['sha256'] not in bysha]
    need(len(hold)==2,'expected exactly two X6 fresh X9-held-out originals')
    for c in hold:
        src=X6_ROOT/c['filename'];raw=src.read_bytes()
        need(sha(raw)==c['sha256'],'X6 source SHA mismatch')
        dst=ROOT/(c['gbd']+'.cnf');dst.write_bytes(raw)
        originals.append(dict(c,filename=dst.name,cohort='x6_reserved',
                              x9_prior_training=False))
    need(len(originals)==TARGET and
         len({c['sha256'] for c in originals})==TARGET,
         'source uniqueness')
    training=[]
    for c in originals[:TRAIN]:
        score=bysha[c['sha256']]['PAR2_s']
        base=score['original']
        gains={mode:round(base-score[mode],6)
               for mode in ('front100','spread_shifted')}
        best=max(gains,key=lambda k:gains[k])
        label=(best if gains[best]>0.4 and
               gains[best]>0.08*max(0.01,base) else 'original')
        src=ROOT/c['filename']
        training.append(dict(sha256=c['sha256'],features=features(
            src,c['vars'],c['clauses']),gain_s=gains,label=label))
    need(len(training)==TRAIN,'training incomplete')
    save(ROOT/'train_model.json',dict(protocol=PROTO,features=FEATURES,
        trained_from_x9_audited_timings=True,source_only_features=True,
        predictor='kNN5 with source-excluded leave-one-out',
        excluded_source_outcomes_for_x9_replay=True,
        prepared_X6_reserved_holdout_count=2,
        rows=training))
    predictions=[]
    for c in originals:
        f=features(ROOT/c['filename'],c['vars'],c['clauses'])
        choice,info=choose(f,training,c['sha256'])
        predictions.append(dict(gbd=c['gbd'],sha256=c['sha256'],
            cohort=c['cohort'],choice=choice,**info))
    save(ROOT/'manifest.json',dict(protocol=PROTO,cases=originals,
        modes=MODES,cap_s=CAP,reps=REPS,expected_trials=TARGET*REPS*len(MODES),
        x9_training_run=42559879920,x9_prior_not_blind=True,
        x6_two_reserved_sources_not_in_x9=True,
        x10_live_run_uses_fixed_source_only_model=True,
        no_auto_promotion=True,
        declaration='All 30 X9 originals previously measured; 2 held out from X9 but not globally blind',
        predictions=predictions))
    print('X10_FROZEN',len(originals),
          'policy',collections.Counter(x['choice'] for x in predictions),
          flush=True)
    print('X10_PREDICTIONS',json.dumps(predictions,sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/'manifest.json').read_text())
    model=json.loads((ROOT/'train_model.json').read_text())
    need(m['protocol']==PROTO and m['cap_s']==CAP and
         m['modes']==list(MODES) and m['reps']==REPS and
         len(m['cases'])==TARGET and m['expected_trials']==384,
         'protocol drift')
    need(model['protocol']==PROTO and len(model['rows'])==TRAIN,
         'training drift')
    for c in m['cases']:
        src=ROOT/c['filename']
        need(sha(src.read_bytes())==c['sha256'],'source drift')
    return m,model['rows']

def trial(c,rep,mode,training):
    src=ROOT/c['filename'];s=seed(c,rep)
    env=os.environ.copy();env.pop('DRNAS_MAX_CONFLICTS',None)
    status='TIMEOUT';raw_status='TIMEOUT';model={};stats=None
    gate=dict(choice=mode)
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        start=time.perf_counter()
        use=src;selected=mode
        if mode=='adaptive':
            f=features(src,c['vars'],c['clauses'])
            selected,detail=choose(f,training,c['sha256'])
            gate=dict(choice=selected,**detail)
        if selected in ('front100','spread_shifted'):
            n,clauses=x9.x2.parse(src)
            changed=x9.x6.transform(clauses,selected)
            need(collections.Counter(clauses)==collections.Counter(changed),
                 'source clause multiset changed')
            use=pathlib.Path(td)/'ordered.cnf'
            x9.x2.write(use,n,changed)
        elif selected not in ('original','kissat','cadical'):
            raise RuntimeError('X10 illegal arm '+selected)
        prep=time.perf_counter()-start
        p=None;remaining=CAP-prep
        if remaining>0:
            if selected=='kissat':
                cmd=[str(pathlib.Path('built/bin/kissat_4_0_4').resolve()),
                     '--seed='+str(s),str(use.resolve())]
            elif selected=='cadical':
                cmd=['/usr/bin/cadical',str(use.resolve())]
            else:
                cmd=[str(pathlib.Path('mre_x4/bin/native').resolve()),
                     str(use.resolve()),'x_native',str(s)]
            try:p=subprocess.run(cmd,capture_output=True,text=True,
                                 errors='replace',env=env,timeout=remaining)
            except subprocess.TimeoutExpired:pass
        elapsed=time.perf_counter()-start
        if p is not None:
            if selected in ('kissat','cadical'):
                need(p.returncode in (10,20),
                     selected+' reference error '+p.stderr[-300:])
                status='SAT' if p.returncode==10 else 'UNSAT'
                need(('s SATISFIABLE' if status=='SAT' else
                      's UNSATISFIABLE') in p.stdout,'reference verdict mismatch')
                for line in p.stdout.splitlines():
                    if line.startswith('v '):
                        for v in map(int,line[2:].split()):
                            if v:
                                need(abs(v) not in model or
                                     model[abs(v)]==(v>0),'conflicting witness')
                                model[abs(v)]=v>0
            else:
                need(p.returncode==0,'native CMS crash '+p.stderr[-300:])
                reason=x9.x6.x4.base.parse_gate(p.stdout,'x_native')
                need(not reason['applied'],'backend unexpectedly altered CNF')
                status,model,stats=x9.x6.x4.base.cms.parsed_native(p.stdout)
        raw_status=status
        if elapsed>CAP or status not in ('SAT','UNSAT'):status='TIMEOUT'
        verified=False
        if status=='SAT':
            x9.x6.x4.base.cms.verify_model(src,model);verified=True
    binary=('/usr/bin/cadical' if selected=='cadical'
            else 'built/bin/kissat_4_0_4' if selected=='kissat'
            else 'mre_x4/bin/native')
    return dict(protocol=PROTO,sha256=c['sha256'],gbd=c['gbd'],
        cohort=c['cohort'],rep=rep,seed=s,mode=mode,selected=selected,
        gate=gate,status=status,raw_status=raw_status,
        elapsed_s=round(elapsed,6),preprocessing_s=round(prep,6),
        PAR2_s=round(elapsed if status in ('SAT','UNSAT') else 2*CAP,6),
        SAT_original_verified=verified,UNSAT_independent_LRAT=False,
        native_stats=stats,independent_seed_applied=selected!='cadical',
        binary_sha256=sha(pathlib.Path(binary).read_bytes()))

def shard(idx):
    m,training=verify();need(idx in range(SHARDS),'bad shard')
    cases=[c for i,c in enumerate(m['cases']) if i%SHARDS==idx]
    need(len(cases)==4,'unexpected cases per shard')
    rows=[]
    for c in cases:
        for rep in range(REPS):
            order=list(MODES);random.Random(seed(c,rep)).shuffle(order)
            for mode in order:
                row=trial(c,rep,mode,training)
                rows.append(row)
                save(ROOT/('shard-%d.json'%idx),rows)
                print('X10_TRIAL',json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==48,'shard count')
    print('X10_SHARD_PASS',idx,48,flush=True)

def audit():
    m,train=verify();rows=[];seen=set()
    cases={c['sha256']:c for c in m['cases']}
    for idx in range(SHARDS):
        rows+=json.loads((ROOT/('shard-%d.json'%idx)).read_text())
    need(len(rows)==384,'not 384 complete trials')
    for r in rows:
        c=cases.get(r['sha256'])
        need(c is not None and c['gbd']==r['gbd'],'source changed')
        need(r['protocol']==PROTO and r['mode'] in MODES and
             r['rep'] in range(REPS) and r['seed']==seed(c,r['rep']),
             'paired source/seed invalid')
        if r['mode']=='adaptive':
            expected,_=choose(features(ROOT/c['filename'],
                                       c['vars'],c['clauses']),
                              train,c['sha256'])
            need(r['selected']==expected and r['gate']['choice']==expected,
                 'adaptive gate mismatch')
        else:need(r['selected']==r['mode'],'nonadaptive changed arm')
        key=(r['sha256'],r['rep'],r['mode'])
        need(key not in seen,'duplicate');seen.add(key)
        need(r['status'] in ('SAT','UNSAT','TIMEOUT'),'invalid result')
        need(r['status']!='SAT' or r['SAT_original_verified'],
             'no original SAT witness')
        need(r['status']!='TIMEOUT' or r['PAR2_s']==2*CAP,
             'wrong timeout penalty')
        need(r['status']=='TIMEOUT' or
             (r['elapsed_s']<=CAP and r['PAR2_s']==r['elapsed_s']),
             'invalid solved PAR2')
    for c in m['cases']:
        rs=[r for r in rows if r['sha256']==c['sha256']]
        verdicts={r['status'] for r in rs if r['status']!='TIMEOUT'}
        need(len(verdicts)<=1,'SAT UNSAT contradiction')
        native_unsat=any(r['mode'] in ('original','front100',
                                      'spread_shifted','adaptive')
                         and r['status']=='UNSAT' for r in rs)
        ref_unsat=any(r['mode'] in ('kissat','cadical') and
                      r['status']=='UNSAT' for r in rs)
        for r in rs:
            r['UNSAT_cross_solver_agreement_no_LRAT']=(
                r['status']=='UNSAT' and native_unsat and ref_unsat)
            r['accepted_solved']=(r['status']=='SAT' or
                                  r['UNSAT_cross_solver_agreement_no_LRAT'])
            r['audited_PAR2_s']=r['PAR2_s'] if r['accepted_solved'] else 2*CAP
    scores={}
    for cohort in ('all','x9_replay','x6_reserved'):
        sub=[r for r in rows if cohort=='all' or r['cohort']==cohort]
        d={}
        for mode in MODES:
            a=[r for r in sub if r['mode']==mode]
            d[mode]=dict(n=len(a),
                solved=sum(r['accepted_solved'] for r in a),
                timeouts=sum(r['status']=='TIMEOUT' for r in a),
                PAR2_s=round(sum(r['audited_PAR2_s'] for r in a),6))
        for mode in MODES:
            for base in ('original','kissat','cadical'):
                d[mode]['speedup_vs_'+base]=round(
                    d[base]['PAR2_s']/max(0.000001,d[mode]['PAR2_s']),6)
                d[mode]['percent_faster_vs_'+base]=round(
                    100*(1-d[mode]['PAR2_s']/max(0.000001,d[base]['PAR2_s'])),3)
        scores[cohort]=d
    wins={}
    for mode in ('adaptive','front100','spread_shifted'):
        counts=collections.Counter()
        for c in m['cases']:
            a=sum(r['audited_PAR2_s'] for r in rows
                  if r['sha256']==c['sha256'] and r['mode']==mode)
            b=sum(r['audited_PAR2_s'] for r in rows
                  if r['sha256']==c['sha256'] and r['mode']=='original')
            counts['wins' if a<b-0.001 else
                   'losses' if a>b+0.001 else 'ties']+=1
        wins[mode]=dict(counts)
    gate=collections.Counter(r['selected'] for r in rows
                              if r['mode']=='adaptive')
    out=dict(protocol=PROTO,source_count=TARGET,trials=len(rows),
        cap_s=CAP,score=scores,wins_vs_original=wins,
        gate_choices=dict(gate),preprocessing_included=True,
        x9_replay_30_known=True,x6_reserved_2_not_in_X9=True,
        x6_sources_not_globally_blind=True,
        X9_source_predictions_are_loo=True,
        UNSAT_independent_LRAT=False,
        UNSAT_requires_cross_solver_for_scoring=True,
        no_auto_promotion=True,rows=rows)
    save(ROOT/'report.json',out)
    print('X10_FINAL',json.dumps({k:v for k,v in out.items() if k!='rows'},
                                sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('freeze','verify','shard','audit','selftest'))
    p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.action=='freeze':freeze()
    elif a.action=='verify':
        verify();print('X10_VERIFY_PASS',flush=True)
    elif a.action=='shard':shard(a.shard)
    elif a.action=='selftest':
        x9.x6.install();x9.x6.x4.selftest()
        tiny=ROOT/'tiny-selftest.cnf';ROOT.mkdir(exist_ok=True)
        tiny.write_text('p cnf 3 4\n1 2 0\n1 2 0\n-1 3 0\n2 -3 0\n')
        f=features(tiny,3,4)
        need(len(f)==len(FEATURES),'feature cardinality')
        tiny.unlink(missing_ok=True)
        print('X10_SELFTEST_PASS',flush=True)
    else:audit()
if __name__=='__main__':main()
