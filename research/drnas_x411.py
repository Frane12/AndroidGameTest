#!/usr/bin/env python3
"""X4.11 controlled active decisions: matched counterfactual gain, E2E validation,
one sealed fresh holdout. CORE never replaced without predeclared acceptance.
The native X4.10 solver is deliberately UNCHANGED to isolate learning policy.
SAT sets use planted witnesses; independent constructive UNSAT is separate.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import time
import numpy as np
import drnas_x410 as B
from x410_models import fit, predict, choose, write_model

X=B.X
NAMESPACE='X411-ACTIVE-CAUSAL-v1'
B.NAMESPACE=NAMESPACE
X.DECISION=32
X.WORK_LIMIT=250000
B.NET_OVERHEAD_PROXY_PROP=300
OVERHEAD=300
ARMS=('core','cheap','cheap_sham','flip')
MIN_ACTIVE=5
QUANTILES=(.10,.30,.55,.80)
GATES=((0,0),(8,2500))
SEED=4111311


def emit(tag,data):
    X.emit('X411_'+tag,data)


def save(path,obj):
    X.save(path,obj)


def net_label(base_remaining, flip_remaining, overhead=OVERHEAD):
    """Prospective saving in propagation units after proxy cost."""
    saving=base_remaining-flip_remaining-overhead
    return float(np.clip(saving/max(1000,base_remaining),-2.,2.)),int(saving)


def pair(binary,cnf,c):
    r=B.pair(binary,cnf,c)
    if r['label'] is not None:
        new,net=net_label(r['base']['remaining_propagations'],
                          r['flip']['remaining_propagations'])
        r['label']=new
        r['net_after_proxy']=net
    else:r['net_after_proxy']=None
    return r


def gather(binary,cnf,cases,path):
    rows=[]
    with path.open('w') as out:
        for i,c in enumerate(cases):
            cnf.write_text(c['source'])
            r=pair(binary,cnf,c)
            rows.append(r)
            out.write(json.dumps(r,sort_keys=True)+'\n')
            if (i+1)%48==0:
                emit('COLLECT',dict(split=c['split'],done=i+1,total=len(cases),
                     labeled=sum(q['label'] is not None for q in rows),
                     positive=sum(q['net_after_proxy'] is not None and q['net_after_proxy']>0 for q in rows)))
    return rows


def model_votes(model,r):
    if r['features'] is None:return False
    pre=r['base']['pre']
    return (pre['prefix_conflicts']>=model['min_conflicts'] and
            pre['prefix_propagations']>=model['min_propagations'] and
            choose(model,r['features']))


def new_candidates(models,train):
    # Thresholds are calculated only from TRAIN scores, never holdout labels.
    pool={}
    for kind,base in models.items():
        scores=[predict(base,r['features'])[0] for r in train
                if r['features'] is not None and not predict(base,r['features'])[1]]
        if not scores:
            continue
        for q in QUANTILES:
            t=float(np.quantile(scores,q))
            for conf,prop in GATES:
                key=f'{kind}_q{int(q*100)}_c{conf}_p{prop}'
                pool[key]={**base,'threshold':t,'min_conflicts':conf,
                           'min_propagations':prop}
    # Deliberately active diagnostic arm; it is NOT automatically deployable.
    # Its in-distribution threshold forces flips for reachable checkpoints.
    first=models['ridge'] if 'ridge' in models else next(iter(models.values()))
    pool['aggressive_diagnostic']={**first,'threshold':-1000000.,
                                   'min_conflicts':0,'min_propagations':0}
    return pool


def screen(model,rows):
    chosen=[r for r in rows if model_votes(model,r)]
    complete=[r for r in chosen if r['net_after_proxy'] is not None]
    censored=len(chosen)-len(complete)
    gain=sum(r['net_after_proxy'] for r in complete)
    loss=sum(-min(0,r['net_after_proxy']) for r in complete)
    # Censored matches cannot be counted as wins; score penalizes them.
    return dict(actions=len(chosen),complete=len(complete),censored=censored,
                net_proxy_prop=gain,loss_prop=loss,
                score=gain-10000*censored)


def auc_diag(model,rows):
    usable=[r for r in rows if r['label'] is not None and abs(r['label'])>.01]
    good=[predict(model,r['features'])[0] for r in usable if r['net_after_proxy']>0]
    bad=[predict(model,r['features'])[0] for r in usable if r['net_after_proxy']<=0]
    val=float(np.mean([(p>b)+.5*(p==b) for p in good for b in bad])) if good and bad else None
    return dict(n=len(usable),positive=len(good),negative=len(bad),auc=val,
                actual_active=sum(model_votes(model,r) for r in usable),
                label='net saved propagations after 300-unit proxy, completed pairs only')


def aggregate(rows,arm):
    return dict(PAR2_s=sum(r['arms'][arm]['PAR2'] for r in rows),
                SAT_verified=sum(r['arms'][arm]['within_cap'] for r in rows),
                propagations=sum(r['arms'][arm]['propagations'] for r in rows),
                conflicts=sum(r['arms'][arm]['conflicts'] for r in rows),
                interventions=sum(bool(r['arms'][arm]['policy']['flipped']) for r in rows),
                gate_skips=sum(bool(r['arms'][arm]['policy'].get('gate_skipped')) for r in rows),
                probe_inspections=sum(r['arms'][arm]['policy']['probe_inspections'] for r in rows),
                trials=len(rows))


def effect(rows,other):
    by_sha=defaultdict(list)
    for row in rows:by_sha[row['sha256']].append(row)
    b=[np.mean([r['arms']['core']['PAR2'] for r in group]) for group in by_sha.values()]
    a=[np.mean([r['arms'][other]['PAR2'] for r in group]) for group in by_sha.values()]
    return X.effect(b,a,draws=4000)


def trial(binary,cnf,c,arm,cap,model=None):
    return X.run(binary,cnf,c,arm,cap,model=model)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,default=Path('build/drnas-x410'))
    ap.add_argument('--out',type=Path,default=Path('x411_results'))
    ap.add_argument('--per-family',type=int,default=48)
    ap.add_argument('--cap',type=float,default=3.0)
    ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args()
    if args.per_family<32 or args.cap<1 or args.repeats<2:raise ValueError('invalid experiment size')
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(__import__('os'),'sched_setaffinity'):
        import os
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    start=time.perf_counter()
    binary=args.binary.resolve()
    cohorts={split:[B.make_case(f,i,split) for f in families
                    for i in range(args.per_family)]
             for split,families in [('train',X.TRAIN),('validation',X.VALIDATION),('holdout',X.HOLDOUT)]}
    assert len({c['sha256'] for cs in cohorts.values() for c in cs})==sum(map(len,cohorts.values()))
    assert not (set(X.TRAIN)&set(X.VALIDATION))
    assert not ((set(X.TRAIN)|set(X.VALIDATION))&set(X.HOLDOUT))
    save(args.out/'manifest.json',{s:[{k:r[k] for k in ('sha256','family','regime','n','index')}
                                   for r in cs] for s,cs in cohorts.items()})
    save(args.out/'protocol.json',dict(namespace=NAMESPACE,per_family=args.per_family,
        cap_s=args.cap,repeats=args.repeats,decision=X.DECISION,
        work_limit=X.WORK_LIMIT,training_overhead_proxy_prop=OVERHEAD,
        quantiles=QUANTILES,gates=GATES,minimum_active=MIN_ACTIVE,
        train=X.TRAIN,validation=X.VALIDATION,holdout=X.HOLDOUT,
        baseline='unaltered native X4.10 CORE',validation_rule='candidate must have >=5 active validation flips; lower95 improvement >2%; no solve regression; fewer propagations; >=2 winning families',
        holdout_rule='single sealed holdout opened only after freeze; active diagnostic always evaluated',
        limitations='Fresh planted SAT synthetic; UNSAT evaluated separately. No official SAT competition claim.'))
    cnf=args.out/'current.cnf'
    train=gather(binary,cnf,cohorts['train'],args.out/'train_pairs.jsonl')
    validation=gather(binary,cnf,cohorts['validation'],args.out/'validation_pairs.jsonl')
    stats={s:dict(Counter(r['exclusion'] or 'labeled' for r in rows))
           for s,rows in [('train',train),('validation',validation)]}
    emit('TRAIN_STATS',dict(**stats))
    good=[r for r in train if r['label'] is not None]
    if len(good)>=80:
        models=fit(train)
        trained=True
    else:
        # No fictitious training when data are insufficient. Still test the
        # explicit active diagnostic and report a non-deployable model.
        fallback=dict(centers=[0.]*30,scales=[1.]*30,threshold=1e9,
                      ood_limit=8.,training_pairs=len(good),bias=0.,kind='ridge',
                      weights=[[0.]*30+[0.]]*2)
        models={'ridge':fallback}
        trained=False
        emit('INSUFFICIENT_TRAIN',dict(usable=len(good),required=80))
    candidates=new_candidates(models,train)
    screening={k:screen(m,validation) for k,m in candidates.items()}
    active=[k for k in candidates if k!='aggressive_diagnostic' and
            screening[k]['actions']>=MIN_ACTIVE]
    active.sort(key=lambda k:(screening[k]['score'],-screening[k]['censored'],k),reverse=True)
    shortlist=active[:3]
    if 'aggressive_diagnostic' not in shortlist:shortlist.append('aggressive_diagnostic')
    assert shortlist
    emit('SHORTLIST',dict(all_candidates=len(candidates),active_candidates=len(active),
                          shortlisted=[{**screening[k],'name':k} for k in shortlist]))
    paths={}
    for k in shortlist:
        path=args.out/(k+'.txt')
        write_model(path,candidates[k])
        paths[k]=path
    val_trials=[]
    with (args.out/'validation_trials.jsonl').open('w') as out:
        for i,c in enumerate(cohorts['validation']):
            cnf.write_text(c['source'])
            names=['core','cheap_sham','flip']+shortlist
            random.Random(SEED+i*31).shuffle(names)
            rr={}
            for arm in names:
                policy='cheap' if arm in shortlist else arm
                model=paths[arm] if arm in shortlist else (paths['aggressive_diagnostic'] if arm=='cheap_sham' else None)
                rr[arm]=trial(binary,cnf,c,policy,args.cap,model)
                assert rr[arm]['policy']['probe_inspections']==0
            val_trials.append(dict(sha256=c['sha256'],family=c['family'],arms=rr))
            out.write(json.dumps(val_trials[-1],sort_keys=True)+'\n')
            if (i+1)%24==0:emit('VALIDATION',dict(done=i+1,total=len(cohorts['validation'])))
    core=aggregate(val_trials,'core')
    reviews={}
    for key in shortlist:
        ar=aggregate(val_trials,key)
        delta=effect(val_trials,key)
        family_delta={}
        for f in X.VALIDATION:
            rows=[r for r in val_trials if r['family']==f]
            family_delta[f]=100*(1-aggregate(rows,key)['PAR2_s']/aggregate(rows,'core')['PAR2_s'])
        # Do not count trivial zero-action or exact CORE parity as learning.
        accepts=(trained and key!='aggressive_diagnostic' and
                 ar['interventions']>=MIN_ACTIVE and
                 delta['paired_formula_bootstrap95_pct'][0]>2 and
                 ar['SAT_verified']>=core['SAT_verified'] and
                 ar['propagations']<core['propagations'] and
                 sum(d>0 for d in family_delta.values())>=2)
        reviews[key]=dict(metrics=ar,effect=delta,by_family=family_delta,
                          eligible_for_deployment=accepts)
    eligible=[key for key in shortlist if reviews[key]['eligible_for_deployment']]
    # Even when no candidate is safe to deploy, freeze the best ACTIVE
    # diagnostic policy and measure its held-out behavior. Deploy CORE.
    ordinary=[k for k in shortlist if k!='aggressive_diagnostic' and
              reviews[k]['metrics']['interventions']>=MIN_ACTIVE]
    winner=min(eligible or ordinary or ['aggressive_diagnostic'],
               key=lambda k:(reviews[k]['metrics']['PAR2_s'],k))
    approved=bool(eligible)
    model=candidates[winner]
    frozen_path=paths[winner]
    frozen_sha=hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    freeze=dict(status='FROZEN',candidate=winner,primary_candidate=winner,
        selected_for='deployment' if approved else 'active_diagnostic_only',
        deploy_policy='cheap' if approved else 'core',
        validation_accepted=approved,model_sha256=frozen_sha,
        validation_core=core,reviews=reviews,trained=trained,
        raw_label_counts=stats,shortlist=shortlist)
    save(args.out/'freeze.json',freeze)
    emit('FROZEN',dict(candidate=winner,deploy_policy=freeze['deploy_policy'],
                       validation_accepted=approved,model_sha256=frozen_sha,
                       actions=reviews[winner]['metrics']['interventions'],
                       effect=reviews[winner]['effect']))
    holdout=[]
    matched=[]
    with (args.out/'holdout_trials.jsonl').open('w') as out, (args.out/'holdout_pairs.jsonl').open('w') as pf:
        for i,c in enumerate(cohorts['holdout']):
            cnf.write_text(c['source'])
            paired=pair(binary,cnf,c)
            matched.append(paired);pf.write(json.dumps(paired,sort_keys=True)+'\n')
            for rep in range(args.repeats):
                arms={}
                order=list(ARMS)
                random.Random(SEED+i*61+rep).shuffle(order)
                for arm in order:
                    m=frozen_path if arm in ('cheap','cheap_sham') else None
                    arms[arm]=trial(binary,cnf,c,arm,args.cap,m)
                    assert arms[arm]['policy']['probe_inspections']==0
                # SHAM must be observational and not change CORE trajectory.
                if arms['core']['verified'] and arms['cheap_sham']['verified']:
                    assert all(arms['core'][k]==arms['cheap_sham'][k]
                               for k in ('propagations','conflicts','decisions'))
                policy=arms['cheap']['policy']
                if arms['cheap']['reached']:
                    if policy['gate_skipped']:
                        assert not policy['features'] and not policy['flipped']
                    else:
                        assert len(policy['features'])==30
                        py_score,_=predict(model,policy['features'])
                        assert abs(py_score-policy['score'])<1e-7
                        assert choose(model,policy['features'])==policy['flipped']
                row=dict(sha256=c['sha256'],family=c['family'],regime=c['regime'],
                         rep=rep,arms=arms)
                holdout.append(row);out.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%24==0:emit('HOLDOUT',dict(done=i+1,total=len(cohorts['holdout'])))
    assert hashlib.sha256(frozen_path.read_bytes()).hexdigest()==frozen_sha
    summary={arm:aggregate(holdout,arm) for arm in ARMS}
    effects={arm:effect(holdout,arm) for arm in ARMS if arm!='core'}
    families={f:{arm:aggregate([r for r in holdout if r['family']==f],arm)['PAR2_s']
                 for arm in ARMS} for f in X.HOLDOUT}
    reported=dict(status='COMPLETE',namespace=NAMESPACE,train=len(train),
        validation=len(validation),holdout=len(cohorts['holdout']),repeats=args.repeats,
        decision=X.DECISION,cap_s=args.cap,source_count=sum(len(v) for v in cohorts.values()),
        model_sha256=frozen_sha,model=winner,
        selected_for=freeze['selected_for'],validation_accepted=approved,
        deploy_policy=freeze['deploy_policy'],arms=summary,
        effects_vs_core=effects,by_family=families,
        holdout_pair_counts=dict(Counter(r['exclusion'] or 'labeled' for r in matched)),
        prediction=auc_diag(model,matched),
        holdout_success=bool(approved and effects['cheap']['paired_formula_bootstrap95_pct'][0]>2 and
                             summary['cheap']['propagations']<summary['core']['propagations'] and
                             summary['cheap']['SAT_verified']>=summary['core']['SAT_verified']),
        elapsed_s=time.perf_counter()-start,
        limits=['Only generated SAT with independently checked witness; original competition CNFs not tested.',
                'Active diagnostic held out even if validation rejected; this is not a production deployment.',
                'One checkpoint and per-formula repeated trials; model comparison exploratory.',
                'UNSAT evaluated separately, constructive PHP without external DRAT proof.',
                'Training data excludes work-censored paired actions.'])
    save(args.out/'report.json',reported)
    cnf.unlink()
    emit('FINAL',reported)


if __name__=='__main__':
    main()
