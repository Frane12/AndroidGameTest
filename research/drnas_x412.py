#!/usr/bin/env python3
"""X4.12 two-stage contextual CDCL decision, with frozen/verified E2E holdout.

Only 30 predecision cheap features are visible to the frozen model.
Stage 1 estimates whether polarity reversal is useful in this context.
Stage 2 estimates net work saved after a fixed training-time overhead proxy.
Compare native X4.12 CORE, CONTEXTUAL, CONTEXTUAL_SHAM and FORCED FLIP serially.
Synthetic SAT train/validation/holdout families are disjoint; fresh source hashes.
No unsupervised tuning on sealed holdout, and no claim about industrial UNSAT.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import random
import time

import numpy as np
import drnas_x410 as B
from x412_models import NF, PROXY, fit, scores, choose, write_model

X=B.X
NAMESPACE='X412-TWO-STAGE-NEW-SOURCES-v1'
B.NAMESPACE=NAMESPACE
B.NET_OVERHEAD_PROXY_PROP=PROXY
X.DECISION=32
X.WORK_LIMIT=250000
ARMS=('core','contextual','contextual_sham','flip')
SEED=4121311
GATE_THRESHOLDS=(.20,.35,.50,.65)
GAIN_THRESHOLDS=(-.15,-.04,0.,.05)
CONFLICT_FLOORS=(0,8)
MIN_ACTIVE=5


def emit(tag,value):
    X.emit('X412_'+tag,value)


def save(path,value):
    X.save(path,value)


def read_pair(binary,cnf,c):
    r=B.pair(binary,cnf,c)
    if r['features'] is not None:
        assert len(r['features'])==NF
    if r['label'] is not None:
        r['net_after_proxy']=int(r['base']['remaining_propagations']-
                                 r['flip']['remaining_propagations']-PROXY)
        r['net_normalized']=float(np.clip(
            r['net_after_proxy']/max(1000.,r['base']['remaining_propagations']),-2,2))
    else:
        r['net_after_proxy']=None
        r['net_normalized']=None
    assert r['base']['policy']['probe_inspections']==r['flip']['policy']['probe_inspections']==0
    return r


def collect(binary,cnf,cases,out):
    rr=[]
    with out.open('w') as stream:
        for i,c in enumerate(cases):
            cnf.write_text(c['source'])
            row=read_pair(binary,cnf,c)
            rr.append(row)
            stream.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%48==0:
                emit('COLLECT',dict(split=c['split'],done=i+1,total=len(cases),
                                    labeled=sum(r['label'] is not None for r in rr),
                                    positive=sum(r['net_after_proxy'] is not None and r['net_after_proxy']>0 for r in rr)))
    return rr


def eligible_context(model,row):
    if row['features'] is None:return False
    pre=row['base']['pre']
    return choose(model,row['features'],
                  pre['prefix_conflicts'],pre['prefix_propagations'])


def train_screen(model,rows):
    chosen=[r for r in rows if eligible_context(model,r)]
    complete=[r for r in chosen if r['net_after_proxy'] is not None]
    censored=len(chosen)-len(complete)
    gains=sum(r['net_after_proxy'] for r in complete)
    losses=sum(-min(0,r['net_after_proxy']) for r in complete)
    # No treating censored continuations as solved wins.
    return dict(actions=len(chosen),complete=len(complete),censored=censored,
                summed_net_prop=gains,negative_loss_prop=losses,
                ranking_score=gains-20000*censored)


def make_candidates(base):
    out={}
    for gate in GATE_THRESHOLDS:
        for gain in GAIN_THRESHOLDS:
            for conf in CONFLICT_FLOORS:
                key=f'g{int(round(gate*100))}_net{int(round(gain*100))}_c{conf}'
                out[key]={**base,'gate_threshold':gate,'gain_threshold':gain,
                          'min_conflicts':conf,'min_propagations':0}
    # Explicit stress candidate probes whether context gate could work at all.
    out['wide_diagnostic']={**base,'gate_threshold':0.01,'gain_threshold':-1.0,
                             'min_conflicts':0,'min_propagations':0}
    return out


def shortlist_candidates(candidates,train_rows):
    stat={k:train_screen(m,train_rows) for k,m in candidates.items()}
    # Pick candidates from TRAIN ONLY, including both permissive and selective.
    active=[k for k in candidates if k!='wide_diagnostic' and stat[k]['actions']>=MIN_ACTIVE]
    active.sort(key=lambda k:(stat[k]['ranking_score'],-stat[k]['censored'],k),reverse=True)
    shortlist=active[:3]
    diverse=sorted(active,key=lambda k:(stat[k]['actions'],-stat[k]['censored']),reverse=True)
    if diverse and diverse[0] not in shortlist:shortlist.append(diverse[0])
    if 'wide_diagnostic' not in shortlist:shortlist.append('wide_diagnostic')
    return shortlist,stat


def score_e2e(rows,arm):
    return dict(PAR2_s=sum(r['arms'][arm]['PAR2'] for r in rows),
                solved=sum(r['arms'][arm]['within_cap'] for r in rows),
                conflicts=sum(r['arms'][arm]['conflicts'] for r in rows),
                propagations=sum(r['arms'][arm]['propagations'] for r in rows),
                interventions=sum(bool(r['arms'][arm]['policy']['flipped']) for r in rows),
                gate_skips=sum(bool(r['arms'][arm]['policy'].get('gate_skipped',False)) for r in rows),
                stage1_pass=sum(bool(r['arms'][arm]['policy'].get('stage1_pass',False)) for r in rows),
                stage2_pass=sum(bool(r['arms'][arm]['policy'].get('stage2_pass',False)) for r in rows),
                probe_inspections=sum(r['arms'][arm]['policy']['probe_inspections'] for r in rows),
                trials=len(rows))


def effect(rows,arm,draws=4000):
    groups=defaultdict(list)
    for r in rows:groups[r['sha256']].append(r)
    baseline=[np.mean([r['arms']['core']['PAR2'] for r in group]) for group in groups.values()]
    candidate=[np.mean([r['arms'][arm]['PAR2'] for r in group]) for group in groups.values()]
    return X.effect(baseline,candidate,draws=draws)


def verify_prediction(row,model,policy):
    if not row['reached']:return
    stats=row['policy']
    pre=row['pre']
    assert stats['probe_inspections']==0
    if stats['gate_skipped']:
        assert stats['features']==[] and not stats['flipped']
        return
    features=stats['features']
    assert len(features)==NF
    prediction=scores(model,features)
    assert abs(prediction['gate']-stats['gate_probability'])<1e-8
    expect_stage1=not prediction['ood'] and prediction['gate']>=model['gate_threshold']
    assert stats['stage1_pass']==expect_stage1
    if expect_stage1:assert abs(prediction['gain']-stats['gain_score'])<1e-8
    else:assert stats['gain_score']==0
    expect_stage2=expect_stage1 and prediction['gain']>model['gain_threshold']
    assert stats['stage2_pass']==expect_stage2
    should_change=choose(model,features,pre['prefix_conflicts'],pre['prefix_propagations'])
    if policy=='contextual':assert stats['flipped']==should_change
    else:assert policy=='contextual_sham' and not stats['flipped']


def auc_diag(model,rows):
    complete=[r for r in rows if r['net_after_proxy'] is not None]
    pos=[scores(model,r['features'])['gate'] for r in complete if r['net_after_proxy']>0]
    neg=[scores(model,r['features'])['gate'] for r in complete if r['net_after_proxy']<=0]
    auc=float(np.mean([(a>b)+.5*(a==b) for a in pos for b in neg])) if pos and neg else None
    return dict(completed=len(complete),positive=len(pos),negative=len(neg),context_auc=auc,
                predicted_interventions=sum(eligible_context(model,r) for r in complete),
                selection_bias='complete matched counterfactuals; work-censored excluded')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,default=Path('build/drnas-x412'))
    ap.add_argument('--out',type=Path,default=Path('x412_results'))
    ap.add_argument('--per-family',type=int,default=48)
    ap.add_argument('--cap',type=float,default=3.0)
    ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args()
    if args.per_family<32 or args.cap<1 or args.repeats<2:
        raise ValueError('invalid X412 protocol size')
    args.out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    if hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    started=time.perf_counter()
    cohorts={s:[B.make_case(f,i,s) for f in fam for i in range(args.per_family)]
             for s,fam in [('train',X.TRAIN),('validation',X.VALIDATION),('holdout',X.HOLDOUT)]}
    hashes=[c['sha256'] for cc in cohorts.values() for c in cc]
    assert len(hashes)==len(set(hashes))
    assert not(set(X.TRAIN)&set(X.VALIDATION))
    assert not((set(X.TRAIN)|set(X.VALIDATION))&set(X.HOLDOUT))
    save(args.out/'manifest.json',{s:[{k:c[k] for k in ('sha256','family','regime','n','index')}
                                   for c in cc] for s,cc in cohorts.items()})
    save(args.out/'protocol.json',dict(namespace=NAMESPACE,engine='DRNAS native X412 (unchanged CORE)',
         inference='only CDCL predecision features, no family ID/witness/answer, two-stage',
         train=X.TRAIN,validation=X.VALIDATION,holdout=X.HOLDOUT,
         per_family=args.per_family,cap_s=args.cap,repeats=args.repeats,decision=X.DECISION,
         work_limit=X.WORK_LIMIT,overhead_proxy_prop=PROXY,
         gate_thresholds=GATE_THRESHOLDS,gain_thresholds=GAIN_THRESHOLDS,conflict_floors=CONFLICT_FLOORS,
         validation_acceptance='at least 5 real flips and >= CORE solved, fewer total propagations, >=2 families improve, paired formula bootstrap lower95 >2%',
         holdout='open once after freeze, no retraining',
         evidence='generated synthetic SAT with independently checked witness; constructed UNSAT separate'))
    cnf=args.out/'current.cnf'
    train=collect(binary,cnf,cohorts['train'],args.out/'train_pairs.jsonl')
    validation=collect(binary,cnf,cohorts['validation'],args.out/'validation_pairs.jsonl')
    traincounts=dict(Counter(r['exclusion'] or 'labeled' for r in train))
    valcounts=dict(Counter(r['exclusion'] or 'labeled' for r in validation))
    positives=sum(r['net_after_proxy'] is not None and r['net_after_proxy']>0 for r in train)
    trained=traincounts.get('labeled',0)>=80 and positives>=5
    if trained:
        baseline_model=fit(train)
    else:
        emit('INSUFFICIENT_DATA',dict(train_counts=traincounts,positives=positives,
                                      minimum_pairs=80,minimum_positives=5))
        baseline_model=dict(centers=[0.]*NF,scales=[1.]*NF,
                            gate_weights=[0.]*NF+[-10.],
                            gain_weights=[0.]*NF+[0.],
                            ood_limit=8.,gate_threshold=1.,gain_threshold=0.,
                            min_conflicts=0,min_propagations=0,
                            train_pairs=traincounts.get('labeled',0),positive_train=positives)
    candidates=make_candidates(baseline_model)
    selected,training_screen=shortlist_candidates(candidates,train)
    emit('TRAIN_STATS',dict(train=traincounts,validation=valcounts,positives=positives,
                            trained=trained,candidates=len(candidates)))
    emit('SHORTLIST',dict(selected=[{**training_screen[k],'name':k} for k in selected],
                          gates=GATE_THRESHOLDS,benefit_thresholds=GAIN_THRESHOLDS))
    model_paths={}
    for name in selected:
        path=args.out/(name+'.txt')
        write_model(path,candidates[name])
        model_paths[name]=path
    validation_trials=[]
    with (args.out/'validation_trials.jsonl').open('w') as stream:
        for i,c in enumerate(cohorts['validation']):
            cnf.write_text(c['source'])
            names=['core','flip','contextual_sham']+selected
            random.Random(SEED+i*37).shuffle(names)
            arms={}
            for name in names:
                policy='contextual' if name in selected else name
                model=model_paths[name] if name in selected else (model_paths['wide_diagnostic'] if name=='contextual_sham' else None)
                arms[name]=X.run(binary,cnf,c,policy,args.cap,model=model)
                assert arms[name]['policy']['probe_inspections']==0
                if name in selected:
                    verify_prediction(arms[name],candidates[name],'contextual')
                if name=='contextual_sham':
                    verify_prediction(arms[name],candidates['wide_diagnostic'],'contextual_sham')
            row=dict(sha256=c['sha256'],family=c['family'],regime=c['regime'],arms=arms)
            validation_trials.append(row)
            stream.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%24==0:emit('VALIDATION',dict(done=i+1,total=len(cohorts['validation'])))
    reference=score_e2e(validation_trials,'core')
    val_models={}
    for name in selected:
        metrics=score_e2e(validation_trials,name)
        change=effect(validation_trials,name)
        family={f:100*(1-score_e2e([r for r in validation_trials if r['family']==f],name)['PAR2_s']/
                        score_e2e([r for r in validation_trials if r['family']==f],'core')['PAR2_s'])
                for f in X.VALIDATION}
        eligible=bool(trained and name!='wide_diagnostic' and
                      metrics['interventions']>=MIN_ACTIVE and
                      metrics['solved']>=reference['solved'] and
                      metrics['propagations']<reference['propagations'] and
                      sum(d>0 for d in family.values())>=2 and
                      change['paired_formula_bootstrap95_pct'][0]>2)
        val_models[name]=dict(metrics=metrics,effect=change,by_family=family,
                              eligible_for_deployment=eligible)
    deploy_candidates=[k for k in selected if val_models[k]['eligible_for_deployment']]
    active_models=[k for k in selected if val_models[k]['metrics']['interventions']>=MIN_ACTIVE]
    # Never choose a no-action model as "successful" learning. Freeze a real
    # active diagnostic even when it fails the deployment acceptance gate.
    winner=min(deploy_candidates or active_models or ['wide_diagnostic'],
               key=lambda k:(val_models[k]['metrics']['PAR2_s'],k))
    accepted=bool(deploy_candidates)
    frozen=candidates[winner]
    frozen_file=model_paths[winner]
    frozen_hash=hashlib.sha256(frozen_file.read_bytes()).hexdigest()
    frozen_data=dict(status='FROZEN',namespace=NAMESPACE,candidate=winner,
         primary_candidate=winner,deploy_policy='contextual' if accepted else 'core',
         selected_for='deployment' if accepted else 'active_diagnostic_only',
         validation_accepted=accepted,model_sha256=frozen_hash,
         all_val_models=val_models,train_counts=traincounts,validation_counts=valcounts,
         active_validation=val_models[winner]['metrics']['interventions'])
    save(args.out/'freeze.json',frozen_data)
    emit('FROZEN',dict(candidate=winner,deploy_policy=frozen_data['deploy_policy'],
         validation_accepted=accepted,selected_for=frozen_data['selected_for'],
         active_validation=frozen_data['active_validation'],
         validation_effect=val_models[winner]['effect'],sha256=frozen_hash))
    # Holdout is opened only AFTER freeze; no update from these results.
    holdout_trials=[]
    holdout_pairs=[]
    with (args.out/'holdout_trials.jsonl').open('w') as stream, (args.out/'holdout_pairs.jsonl').open('w') as pair_stream:
        for i,c in enumerate(cohorts['holdout']):
            cnf.write_text(c['source'])
            matched=read_pair(binary,cnf,c)
            holdout_pairs.append(matched)
            pair_stream.write(json.dumps(matched,sort_keys=True)+'\n')
            for rep in range(args.repeats):
                order=list(ARMS)
                random.Random(SEED+i*61+rep).shuffle(order)
                arms={}
                for name in order:
                    model=frozen_file if name in ('contextual','contextual_sham') else None
                    arms[name]=X.run(binary,cnf,c,name,args.cap,model=model)
                    assert arms[name]['policy']['probe_inspections']==0
                    if name in ('contextual','contextual_sham'):
                        verify_prediction(arms[name],frozen,name)
                if arms['core']['verified'] and arms['contextual_sham']['verified']:
                    assert all(arms['core'][k]==arms['contextual_sham'][k]
                               for k in ('propagations','decisions','conflicts'))
                row=dict(sha256=c['sha256'],family=c['family'],regime=c['regime'],rep=rep,arms=arms)
                holdout_trials.append(row)
                stream.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%24==0:emit('HOLDOUT',dict(done=i+1,total=len(cohorts['holdout'])))
    assert hashlib.sha256(frozen_file.read_bytes()).hexdigest()==frozen_hash
    summary={name:score_e2e(holdout_trials,name) for name in ARMS}
    changes={name:effect(holdout_trials,name,6000) for name in ARMS if name!='core'}
    families={f:{name:score_e2e([r for r in holdout_trials if r['family']==f],name)['PAR2_s']
                 for name in ARMS} for f in X.HOLDOUT}
    performance_success=bool(accepted and changes['contextual']['paired_formula_bootstrap95_pct'][0]>2 and
          summary['contextual']['propagations']<summary['core']['propagations'] and
          summary['contextual']['solved']>=summary['core']['solved'])
    report=dict(status='COMPLETE',namespace=NAMESPACE,
        source_count=len(hashes),train=len(train),validation=len(validation),
        holdout=len(cohorts['holdout']),repeats=args.repeats,cap_s=args.cap,
        model_sha256=frozen_hash,candidate=winner,
        validation_accepted=accepted,deploy_policy=frozen_data['deploy_policy'],
        selected_for=frozen_data['selected_for'],holdout_success=performance_success,
        arms=summary,effects_vs_core=changes,by_family=families,
        prediction=auc_diag(frozen,holdout_pairs),
        holdout_pair_exclusions=dict(Counter(r['exclusion'] or 'labeled' for r in holdout_pairs)),
        elapsed_s=time.perf_counter()-started,
        limits=['Only fresh synthetic SAT in primary benchmark; no official real-CNF speed claims.',
                'Validation-selected thresholds are frozen before opening holdout.',
                'Context score is NOT a calibrated posterior on unseen CNF families.',
                'Completed paired examples are selection-biased; timeouts cannot count as wins.',
                'Single decision checkpoint only; no online learning.',
                'Constructive Pigeonhole UNSAT tested separately without DRAT/LRAT proof.'])
    save(args.out/'report.json',report)
    cnf.unlink()
    emit('FINAL',report)


if __name__=='__main__':
    main()
