#!/usr/bin/env python3
"""X4.10 medium run: passive cost-aware CDCL gate on larger fresh SAT CNFs.

All training labels come from matched-state counterfactuals, not SAT witnesses or
formula identifiers. A separate validation set selects and accepts a model by
true end-to-end PAR2. The holdout is used once AFTER freezing. Constructed
UNSAT is measured by a separate script; no industrial performance claim.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import time

import numpy as np
import drnas_x47 as X
from x410_models import NF,fit,predict,choose,write_model

NAMESPACE='X410-PASSIVE-MEDIUM-v1'
DEFAULT_DECISION=32
WORK_LIMIT=250000
NET_OVERHEAD_PROXY_PROP=300  # training-only conservative proxy; E2E validates actual cost
THRESHOLDS=(-0.10,0.0,0.15,0.35)
CONFLICT_FLOORS=(0,8)
PROP_FLOORS=(0,2500)
ARMS=('core','cheap','cheap_sham')
X.DECISION=DEFAULT_DECISION
X.WORK_LIMIT=WORK_LIMIT


def emit(tag,data):
    X.emit('X410_'+tag,data)


def save(path,data):
    X.save(path,data)


def planted_component(family,index,namespace):
    seed=int.from_bytes(hashlib.sha256(f'{namespace}:{family}:{index}:planted3'.encode()).digest()[:8],'big')
    rng=random.Random(seed)
    n=150+20*(index%4)
    witness=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
    clauses=[]
    # Near transition density; conditioning on a known witness guarantees SAT.
    for _ in range(int(n*4.28)):
        vs=rng.sample(range(1,n+1),3)
        c=[v if rng.getrandbits(1) else -v for v in vs]
        if not any(witness[abs(x)]==(x>0) for x in c):
            q=rng.randrange(3);c[q]=-c[q]
        clauses.append(c)
    return dict(n=n,clauses=clauses)


def make_case(family,index,split):
    # Four regimes: one, two, three independently planted structural blocks,
    # and two structural blocks plus a harder planted-3SAT component.
    # Independent blocks preserve satisfiability without cross-block witnesses.
    namespace=NAMESPACE+':'+split
    mode=index%4
    blocks=1 if mode==0 else (3 if mode==2 else 2)
    parts=[X.make_case(family,index*11+j,namespace+':block'+str(j))
           for j in range(blocks)]
    if mode==3:
        parts.append(planted_component(family,index,namespace))
    clauses=[];offset=0
    for part in parts:
        for clause in part['clauses']:
            clauses.append([int(math.copysign(abs(x)+offset,x)) for x in clause])
        offset+=part['n']
    content=f'p cnf {offset} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
    return dict(family=family,index=index,split=split,n=offset,clauses=clauses,
                sha256=hashlib.sha256(content.encode()).hexdigest(),source=content,
                regime=['single','double','triple','double_plus_planted3'][mode])


def pair(binary,path,case):
    order=(False,True) if case['index']%2 else (True,False)
    tests={fl:X.run(binary,path,case,'collect_cheap',0,flip=fl,work_limit=WORK_LIMIT) for fl in order}
    b,f=tests[False],tests[True]
    r={k:case[k] for k in ('family','index','sha256','n','regime')}
    r.update(base=b,flip=f,label=None,features=None,exclusion='checkpoint_not_reached',
             saved_propagations=None)
    assert b['reached']==f['reached']
    if not b['reached']:return r
    for k in ('pre_state_digest','baseline_literal','prefix_conflicts','prefix_learnt','prefix_propagations'):
        assert b['pre'][k]==f['pre'][k],('state mismatch',case['sha256'],k)
    assert b['pre']['actual_literal']==-f['pre']['actual_literal']
    assert b['policy']['features']==f['policy']['features']
    assert b['policy']['probe_inspections']==f['policy']['probe_inspections']==0
    r['features']=b['policy']['features']
    assert len(r['features'])==NF
    if b['verified'] and f['verified']:
        gain=b['remaining_propagations']-f['remaining_propagations']
        r['saved_propagations']=gain
        # The learner targets benefit after a fixed work-equivalent overhead
        # proxy, instead of predicting a raw (and possibly tiny) improvement.
        r['label']=float(np.clip((gain-NET_OVERHEAD_PROXY_PROP)/
                                 max(1000,b['remaining_propagations']),-2,2))
        r['exclusion']=None
    else:r['exclusion']='work_censored'
    return r


def gather(binary,cases,cnf,path):
    rows=[]
    with path.open('w') as out:
        for i,case in enumerate(cases):
            cnf.write_text(case['source'])
            r=pair(binary,cnf,case)
            rows.append(r)
            out.write(json.dumps(r,sort_keys=True)+'\n')
            if (i+1)%48==0:
                emit('COLLECT',dict(split=case['split'],done=i+1,total=len(cases),
                                    labeled=sum(x['label'] is not None for x in rows)))
    return rows


def bootstrap(core,candidate,draws=2500):
    return X.effect(np.asarray(core,dtype=float),np.asarray(candidate,dtype=float),draws=draws)


def auc_report(model,rows):
    rr=[r for r in rows if r['label'] is not None and abs(r['label'])>.1]
    pos=[r for r in rr if r['saved_propagations']>NET_OVERHEAD_PROXY_PROP]
    neg=[r for r in rr if r['saved_propagations']<=NET_OVERHEAD_PROXY_PROP]
    p=[predict(model,r['features'])[0] for r in pos]
    n=[predict(model,r['features'])[0] for r in neg]
    if not p or not n:return dict(n=len(rr),auc=None)
    a=float(np.mean([(x>y)+.5*(x==y) for x in p for y in n]))
    return dict(n=len(rr),positive=len(p),negative=len(n),auc=a,
                label='gain exceeds fixed 300-propagation proxy; conditional on completed matched pairs')


def effective(model,row):
    if not row['features']:return False
    pre=row['base']['pre']
    if pre['prefix_conflicts']<model['min_conflicts']:return False
    if pre['prefix_propagations']<model['min_propagations']:return False
    return choose(model,row['features'])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,default=Path('build/drnas-x410'))
    ap.add_argument('--out',type=Path,default=Path('x410_results'))
    ap.add_argument('--per-family',type=int,default=48)
    ap.add_argument('--cap',type=float,default=2.5)
    ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args()
    if args.per_family<24 or args.cap<.5 or args.repeats<2:raise ValueError('invalid benchmark configuration')
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(__import__('os'),'sched_setaffinity'):
        import os
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    started=time.perf_counter()
    binary=args.binary.resolve()
    cohorts={s:[make_case(f,i,s) for f in fam for i in range(args.per_family)]
             for s,fam in [('train',X.TRAIN),('validation',X.VALIDATION),('holdout',X.HOLDOUT)]}
    allcases=[r for rr in cohorts.values() for r in rr]
    assert len(set(r['sha256'] for r in allcases))==len(allcases)
    assert not(set(X.TRAIN)&set(X.VALIDATION))
    assert not(set(X.TRAIN+X.VALIDATION)&set(X.HOLDOUT))
    save(args.out/'manifest.json',{s:[{k:r[k] for k in ('sha256','family','regime','n','index')}
                                   for r in rows] for s,rows in cohorts.items()})
    proto=dict(namespace=NAMESPACE,decision=DEFAULT_DECISION,cap_s=args.cap,repeats=args.repeats,
               work_limit=WORK_LIMIT,net_overhead_proxy_propagations=NET_OVERHEAD_PROXY_PROP,
               train=X.TRAIN,validation=X.VALIDATION,holdout=X.HOLDOUT,
               family_disjoint=True,thresholds=THRESHOLDS,conflict_floors=CONFLICT_FLOORS,
               propagation_floors=PROP_FLOORS,
               benchmark_type='fresh combined synthetic planted SAT, not original official CNF',
               model_choice='train-only weights and validation-only selection, freeze before holdout',
               acceptance='validation formula-bootstrap lower95 > 2% and fewer total propagations, solved >= CORE and 2/3 families improved',
               deployment='CORE unless validation accepts model')
    save(args.out/'protocol.json',proto)
    cnf=args.out/'current.cnf'
    train=gather(binary,cohorts['train'],cnf,args.out/'train_pairs.jsonl')
    labeled=sum(r['label'] is not None for r in train)
    if labeled<80:
        # Predetermined training-only checkpoint fallback; no validation/holdout peeking.
        X.DECISION=16
        emit('CHECKPOINT_TRAIN_ONLY',dict(old=DEFAULT_DECISION,new=16,labeled_at_old=labeled))
        train=gather(binary,cohorts['train'],cnf,args.out/'train_pairs.jsonl')
        proto['decision']=16
        save(args.out/'protocol.json',proto)
    valid=gather(binary,cohorts['validation'],cnf,args.out/'validation_pairs.jsonl')
    emit('TRAIN_STATS',dict(train=dict(Counter(r['exclusion'] or 'labeled' for r in train)),
                           validation=dict(Counter(r['exclusion'] or 'labeled' for r in valid)),
                           decision=X.DECISION))
    models=fit(train)
    candidates={}
    for kind,base in models.items():
        for threshold in THRESHOLDS:
            for conflicts in CONFLICT_FLOORS:
                for propagation in PROP_FLOORS:
                    key=f'{kind}_t{threshold}_c{conflicts}_p{propagation}'
                    candidates[key]={**base,'threshold':threshold,'min_conflicts':conflicts,
                                     'min_propagations':propagation}
    # Screen candidates on validation matched-state work; then ACTUAL end-to-end
    # validation determines selection. The untouched holdout is never consulted.
    offline={}
    for key,model in candidates.items():
        flip=[r for r in valid if effective(model,r)]
        gain=sum((r['base']['work_cost']-r['flip']['work_cost']-NET_OVERHEAD_PROXY_PROP) for r in flip)
        censored=sum(r['label'] is None for r in flip)
        offline[key]=dict(gain_after_proxy=gain,flips=len(flip),censored=censored,
                          screening_score=gain-10000*censored)
    ranking=sorted(candidates,key=lambda k:(offline[k]['screening_score'],
                                              -offline[k]['censored'],k),reverse=True)
    selected=ranking[:3]
    most_active=max(candidates,key=lambda k:(offline[k]['flips'],offline[k]['screening_score']))
    if most_active not in selected:selected.append(most_active)
    emit('SHORTLIST',dict(candidates=len(candidates),selected=selected,
                          telemetry=[{**offline[k],'name':k} for k in selected]))
    paths={}
    for key in selected:
        f=args.out/(key+'.txt')
        write_model(f,candidates[key])
        paths[key]=f
    validation_trials=[]
    with (args.out/'validation_trials.jsonl').open('w') as fd:
        for i,c in enumerate(cohorts['validation']):
            cnf.write_text(c['source'])
            names=['core','cheap_sham']+selected
            random.Random(41010+i).shuffle(names)
            arms={k:X.run(binary,cnf,c,k if k in ARMS else 'cheap',args.cap,
                          model=paths[k] if k in selected else (paths[selected[0]] if k=='cheap_sham' else None))
                  for k in names}
            row=dict(sha256=c['sha256'],family=c['family'],regime=c['regime'],arms=arms)
            validation_trials.append(row)
            fd.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%24==0:emit('VALIDATE',dict(done=i+1,total=len(cohorts['validation'])))
    def metrics(arm,rows):
        return dict(PAR2=sum(r['arms'][arm]['PAR2'] for r in rows),
                    solved=sum(r['arms'][arm]['within_cap'] for r in rows),
                    propagations=sum(r['arms'][arm]['propagations'] for r in rows),
                    flips=sum(bool(r['arms'][arm]['policy']['flipped']) for r in rows))
    reference=metrics('core',validation_trials)
    evaluations={}
    for key in selected:
        m=metrics(key,validation_trials)
        delta=bootstrap([r['arms']['core']['PAR2'] for r in validation_trials],
                        [r['arms'][key]['PAR2'] for r in validation_trials])
        family_gain={f:100*(1-sum(r['arms'][key]['PAR2'] for r in validation_trials if r['family']==f)/
                              sum(r['arms']['core']['PAR2'] for r in validation_trials if r['family']==f))
                     for f in X.VALIDATION}
        accept=(delta['paired_formula_bootstrap95_pct'][0]>2 and
                m['solved']>=reference['solved'] and
                m['propagations']<reference['propagations'] and
                sum(v>0 for v in family_gain.values())>=2)
        evaluations[key]=dict(holdout_accessed=False,metrics=m,effect=delta,
                              family_gain=family_gain,eligible_for_deployment=accept)
    winner=min(selected,key=lambda k:(evaluations[k]['metrics']['PAR2'],k))
    accepted=evaluations[winner]['eligible_for_deployment']
    frozen=candidates[winner]
    frozen_path=paths[winner]
    frozen_sha=hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    freeze=dict(candidate=winner,primary_candidate=winner,model_sha256=frozen_sha,
                validation_accepted=accepted,deploy_policy='cheap' if accepted else 'core',
                benchmark_type='synthetic planted SAT',
                validation_core=reference,
                evaluations=evaluations,selected=selected,
                offline_screen_top4={k:offline[k] for k in selected})
    save(args.out/'freeze.json',freeze)
    emit('FROZEN',dict(candidate=winner,validation_accepted=accepted,
                       deployment=freeze['deploy_policy'],
                       effect=evaluations[winner]['effect'],sha256=frozen_sha))
    # Audit holdout is now opened; freeze and model are immutable.
    trials=[];holdout_pairs=[]
    with (args.out/'holdout_trials.jsonl').open('w') as tf,(args.out/'holdout_pairs.jsonl').open('w') as pf:
        for i,c in enumerate(cohorts['holdout']):
            cnf.write_text(c['source'])
            matched=pair(binary,cnf,c)
            holdout_pairs.append(matched)
            pf.write(json.dumps(matched,sort_keys=True)+'\n')
            for rep in range(args.repeats):
                order=list(ARMS)
                random.Random(410110+i*17+rep).shuffle(order)
                arms={k:X.run(binary,cnf,c,k,args.cap,model=frozen_path if k!='core' else None)
                      for k in order}
                assert all(arms[k]['policy']['probe_inspections']==0 for k in ARMS)
                if arms['core']['verified'] and arms['cheap_sham']['verified']:
                    assert all(arms['core'][k]==arms['cheap_sham'][k]
                               for k in ('propagations','conflicts','decisions'))
                pol=arms['cheap']['policy']
                if arms['cheap']['reached']:
                    if pol['gate_skipped']:
                        assert pol['features']==[] and not pol['flipped']
                        if arms['core']['verified'] and arms['cheap']['verified']:
                            assert all(arms['core'][k]==arms['cheap'][k]
                                       for k in ('propagations','conflicts','decisions'))
                    else:
                        assert len(pol['features'])==NF
                        score,_=predict(frozen,pol['features'])
                        assert abs(score-pol['score'])<1e-7
                        assert pol['flipped']==choose(frozen,pol['features'])
                row=dict(sha256=c['sha256'],family=c['family'],regime=c['regime'],rep=rep,arms=arms)
                trials.append(row)
                tf.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%24==0:emit('HOLDOUT',dict(done=i+1,total=len(cohorts['holdout'])))
    assert hashlib.sha256(frozen_path.read_bytes()).hexdigest()==frozen_sha
    bysha=defaultdict(list)
    for r in trials:bysha[r['sha256']].append(r)
    means={arm:[float(np.mean([rr['arms'][arm]['PAR2'] for rr in group]))
                for group in bysha.values()] for arm in ARMS}
    comparisons={k:bootstrap(means['core'],means[k],draws=6000) for k in ARMS if k!='core'}
    totals={k:metrics(k,trials) for k in ARMS}
    families={f:{k:sum(r['arms'][k]['PAR2'] for r in trials if r['family']==f) for k in ARMS}
              for f in X.HOLDOUT}
    report=dict(status='COMPLETE',namespace=NAMESPACE,source_count=len(allcases),
                train=len(train),validation=len(valid),holdout=len(cohorts['holdout']),
                repeats=args.repeats,cap_s=args.cap,decision=X.DECISION,
                candidate=winner,model_sha256=frozen_sha,validation_accepted=accepted,
                deploy_policy=freeze['deploy_policy'],arms=totals,
                holdout_effects_vs_core=comparisons,families=families,
                holdout_primary_success=bool(accepted and comparisons['cheap']['paired_formula_bootstrap95_pct'][0]>2
                                            and totals['cheap']['propagations']<totals['core']['propagations']
                                            and totals['cheap']['solved']>=totals['core']['solved']),
                prediction=auc_report(frozen,holdout_pairs),
                holdout_pair_exclusions=dict(Counter(r['exclusion'] or 'labeled' for r in holdout_pairs)),
                elapsed_s=time.perf_counter()-started,
                limits=['Only fresh generated SAT for primary train/validation/holdout, not official original CNFs.',
                        'Analytic UNSAT is separate and does not train the model.',
                        'Multiple candidate screening/selection on validation is exploratory; only untouched holdout confirms.',
                        'Single selected decision checkpoint; no online model updates.',
                        'Repeated trials are not independent formulas; family diversity limited.'])
    save(args.out/'report.json',report)
    cnf.unlink()
    emit('FINAL',report)


if __name__=='__main__':
    main()
