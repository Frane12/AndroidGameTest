#!/usr/bin/env python3
"""Frozen single-decision policy trained on verified matched-state continuation work.

No oracle/witness/family/SHA enters inference. Synthetic SAT only for performance;
small independently exhaustive UNSAT controls are in tests/test_x45a.py.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import time

import numpy as np

TRAIN = ('uniform3','dense3','uniform4','xor_mixed','community','color3','local_band','polarity_skew')
VALIDATION = ('uniform5','ring_xor','hub6')
HOLDOUT = ('widthmix','grid_xor','circuit','community_bridge','color4')
FEATURES = ('log_n','log_density','assigned_fraction','depth_fraction','log_conflicts',
            'log_learnt','weighted_flip_minus_base','binary_flip_minus_base',
            'ternary_flip_minus_base','selected_open_fraction','binary_open_fraction',
            'long_open_fraction','initial_phase_balance','learnt_fraction','log_decisions')
POLICIES = ('core','sham','fixed','flip','learned')
DECISION = 4
SEED = 451311


def emit(tag, x):
    print(tag+' '+json.dumps(x,sort_keys=True,separators=(',',':')),flush=True)


def save(path, data):
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')


def make_case(family, index, namespace='x45a-frozen-v1'):
    seed=int.from_bytes(hashlib.sha256(f'{namespace}:{family}:{index}'.encode()).digest()[:8],'big')
    rng=random.Random(seed)
    n=64+4*(index%9)
    witness=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
    clauses=[]

    def add_planted(vs):
        c=[v*(1 if rng.random() < (.75 if family=='polarity_skew' else .5) else -1) for v in vs]
        if not any(witness[abs(l)]==(l>0) for l in c):c[rng.randrange(len(c))]*=-1
        clauses.append(c)

    def parity(vs):
        target=sum(witness[v] for v in vs)%2
        for bits in itertools.product((0,1),repeat=len(vs)):
            if sum(bits)%2!=target:clauses.append([-v if b else v for v,b in zip(vs,bits)])

    if family in ('color3','color4'):
        colors=3 if family=='color3' else 4
        nodes=20+index%13;n=nodes*colors
        planted=[rng.randrange(colors) for _ in range(nodes)]
        witness=[False]+[planted[v]==c for v in range(nodes) for c in range(colors)]
        var=lambda v,c:colors*v+c+1
        for v in range(nodes):
            cols=[var(v,c) for c in range(colors)];clauses.append(cols)
            clauses.extend([[-a,-b] for a,b in itertools.combinations(cols,2)])
        for u,v in itertools.combinations(range(nodes),2):
            if planted[u]!=planted[v] and rng.random()<.48:
                clauses.extend([[-var(u,c),-var(v,c)] for c in range(colors)])
    elif family=='circuit':
        # Random acyclic AND/XOR circuit, some outputs fixed to a valid witness.
        inputs=16;n=inputs+40+index%24
        witness=[False]+[bool(rng.getrandbits(1)) for _ in range(inputs)]
        for out in range(inputs+1,n+1):
            a,b=rng.sample(range(1,out),2)
            if out%3==0:
                witness.append(witness[a]!=witness[b]);parity([a,b,out])
            else:
                witness.append(witness[a] and witness[b])
                clauses.extend([[-a,-b,out],[a,-out],[b,-out]])
        for out in range(n-7,n+1):clauses.append([out if witness[out] else -out])
    elif family in ('xor_mixed','ring_xor','grid_xor'):
        if family=='xor_mixed':
            for _ in range(int(.8*n)):parity(rng.sample(range(1,n+1),3))
        elif family=='ring_xor':
            for i in range(1,n+1):parity([i,i%n+1,(i+2)%n+1])
        else:
            side=8;n=side*side;witness=witness[:n+1]
            for row in range(side-1):
                for col in range(side-1):
                    a=row*side+col+1;parity([a,a+1,a+side,a+side+1])
        for _ in range(n):add_planted(rng.sample(range(1,n+1),3))
    else:
        width={'uniform4':4,'uniform5':5}.get(family,3)
        density={'dense3':5.2,'uniform4':9.5,'uniform5':17.0}.get(family,4.4)
        for _ in range(round(n*density)):
            k=width
            if family=='widthmix':k=rng.choices([2,3,4,5],[.08,.55,.30,.07])[0]
            vs=None
            if family in ('community','community_bridge') and rng.random()<(.85 if family=='community' else .65):
                size=16 if family=='community' else 24
                start=rng.randrange((n+size-1)//size)*size+1
                group=list(range(start,min(start+size,n+1)))
                if len(group)>=k:vs=rng.sample(group,k)
            elif family=='local_band':
                start=rng.randrange(n);vs=rng.sample([(start+i)%n+1 for i in range(20)],k)
            elif family=='hub6' and rng.random()<.6:
                h=rng.randrange(1,7);vs=[h]+rng.sample([v for v in range(1,n+1) if v!=h],k-1)
            add_planted(vs or rng.sample(range(1,n+1),k))
    clauses=sorted(set(tuple(sorted(set(c),key=lambda x:(abs(x),x))) for c in clauses))
    assert all(any(witness[abs(l)]==(l>0) for l in c) for c in clauses)
    content=f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
    return dict(family=family,index=index,n=n,clauses=clauses,source=content,
                sha256=hashlib.sha256(content.encode()).hexdigest())


def witness_ok(stdout, case):
    values={}
    for line in stdout.splitlines():
        if line.startswith('v '):
            for token in line[2:].split():
                lit=int(token)
                if not lit:continue
                if abs(lit) in values or not 1<=abs(lit)<=case['n']:return False
                values[abs(lit)]=lit>0
    return len(values)==case['n'] and all(any(values[abs(x)]==(x>0) for x in c) for c in case['clauses'])


def run(binary, path, case, policy, cap, model=None, flip=False):
    cmd=[str(binary),str(path),'--mode','core','--time',str(cap),'--stats',
         '--branch-at',str(DECISION),'--policy',policy]
    if model:cmd+=['--model',str(model)]
    if flip:cmd+=['--flip-branch']
    start=time.perf_counter()
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+2)
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',verified=False,within_cap=False,PAR2=2*cap,wall_s=time.perf_counter()-start,reached=False)
    wall=time.perf_counter()-start
    if p.returncode not in (0,10,20):raise RuntimeError(p.stderr)
    if p.returncode==20:raise AssertionError('UNSAT on independently checked planted SAT')
    if p.returncode==10 and not witness_ok(p.stdout,case):raise AssertionError('invalid SAT witness')
    telemetry={}
    for line in p.stderr.splitlines():
        for tag in ('X41_STATS','X45_COMPARE','X45A_POLICY'):
            if line.startswith(tag+' '):telemetry[tag]=json.loads(line[len(tag)+1:])
    if set(telemetry)!=set(('X41_STATS','X45_COMPARE','X45A_POLICY')):raise AssertionError('missing telemetry')
    stats,pre,pol=(telemetry[t] for t in ('X41_STATS','X45_COMPARE','X45A_POLICY'))
    verified=p.returncode==10
    reached=pre['reached']
    return dict(status='SAT_VERIFIED' if verified else 'UNKNOWN',verified=verified,
                within_cap=verified and wall<=cap,PAR2=wall if verified and wall<=cap else 2*cap,
                wall_s=wall,reached=reached,pre=pre,policy=pol,
                propagations=stats['propagations'],conflicts=stats['conflicts'],decisions=stats['decisions'],
                remaining_propagations=stats['propagations']-pre['prefix_propagations'] if reached else None,
                remaining_conflicts=stats['conflicts']-pre['prefix_conflicts'] if reached else None)


def pair(binary,path,case,cap):
    order=[False,True] if case['index']%2 else [True,False]
    rr={flip:run(binary,path,case,'collect',cap,flip=flip) for flip in order}
    b,f=rr[False],rr[True]
    row={k:case[k] for k in ('family','index','sha256','n')}
    row.update(base=b,flip=f,label=None,features=None)
    if not b['reached'] or not f['reached']:
        row['exclusion']='checkpoint_not_reached_or_timeout';return row
    for key in ('pre_state_digest','baseline_literal','prefix_conflicts','prefix_learnt','prefix_propagations'):
        assert b['pre'][key]==f['pre'][key],('prefix mismatch',key)
    assert b['policy']['features']==f['policy']['features']
    assert b['pre']['actual_literal']==-f['pre']['actual_literal']
    row['features']=b['policy']['features']
    if b['within_cap'] and f['within_cap']:
        row['label']=math.log1p(b['remaining_propagations'])-math.log1p(f['remaining_propagations'])
        row['exclusion']=None
    else:row['exclusion']='censored_continuation_not_training_label'
    return row


def fit(train):
    rows=[r for r in train if r['label'] is not None]
    if len(rows)<80:raise RuntimeError('insufficient verified matched training pairs')
    x=np.array([r['features'] for r in rows]);y=np.clip([r['label'] for r in rows],-4,4)
    centers=x.mean(axis=0);scales=np.maximum(x.std(axis=0),.05)
    z=np.clip((x-centers)/scales,-8,8);z=np.column_stack((z,np.ones(len(z))))
    rng=np.random.default_rng(SEED)
    families=sorted(set(r['family'] for r in rows));models=[]
    for member in range(9):
        picked=families if member==0 else rng.choice(families,size=len(families),replace=True)
        ids=[i for family in picked for i,r in enumerate(rows) if r['family']==family]
        a=z[ids];b=y[ids]
        reg=np.eye(z.shape[1])*8.0;reg[-1,-1]=.01
        models.append(np.linalg.solve(a.T@a+reg,a.T@b).tolist())
    return dict(schema=1,features=FEATURES,centers=centers.tolist(),scales=scales.tolist(),
                weights=models,threshold=1e9,ood_limit=8.0,training_pairs=len(rows),
                target='log1p(base_remaining_propagations)-log1p(flip_remaining_propagations)',
                uncertainty='family-bootstrap ensemble mean minus SD; not a calibrated confidence bound',
                training_label_clipped=[-4,4],decision_index=DECISION)


def predict(model, features):
    if features is None:return 0.0,True
    z=(np.array(features)-model['centers'])/model['scales']
    ood=bool(np.max(np.abs(z))>model['ood_limit'])
    ys=np.array(model['weights'])@np.append(np.clip(z,-8,8),1)
    return float(ys.mean()-ys.std()),ood


def write_model(path,model):
    lines=[f"X45A1 {len(FEATURES)} {len(model['weights'])} {model['threshold']:.17g} {model['ood_limit']}"]
    for row in [model['centers'],model['scales'],*model['weights']]:lines.append(' '.join(format(x,'.17g') for x in row))
    path.write_text('\n'.join(lines)+'\n')


def select_threshold(model, validation):
    # Fixed candidate grid; no holdout access. Conservative default on ties.
    results=[]
    for threshold in (1e9,1.0,.5,.25,.10,0.0):
        selected=[];flips=0
        for r in validation:
            score,ood=predict(model,r['features']);flip=not ood and score>threshold
            selected.append(r['flip' if flip else 'base']['PAR2']);flips+=flip
        results.append(dict(threshold=threshold,PAR2=sum(selected),flips=flips))
    best=min(results,key=lambda r:(r['PAR2'],-r['threshold']))
    model['threshold']=best['threshold'];model['validation_candidates']=results
    model['validation_selection']='min paired measured PAR2; conservative threshold on exact ties; no inference overhead credit'
    return model


def effect(a,b,draws=6000):
    a=np.asarray(a,float);b=np.asarray(b,float);rng=np.random.default_rng(SEED+99)
    values=[]
    for _ in range(draws):
        idx=rng.integers(len(a),size=len(a));values.append(100*(1-b[idx].sum()/a[idx].sum()))
    return dict(improvement_pct=float(100*(1-b.sum()/a.sum())),
                paired_formula_bootstrap95_pct=np.quantile(values,[.025,.975]).tolist(),
                original_formula_units=len(a),draws=draws)


def prediction_report(model, pairs):
    valid=[r for r in pairs if r['label'] is not None and abs(r['label'])>.10]
    pred=[];truth=[]
    for r in valid:
        score,ood=predict(model,r['features']);pred.append(not ood and score>model['threshold']);truth.append(r['label']>0)
    truth=np.array(truth,bool);pred=np.array(pred,bool)
    def ba(ids):
        y=truth[ids];p=pred[ids]
        if not y.any() or y.all():return None
        return float(((p[y]).mean()+(~p[~y]).mean())/2)
    if not valid:return dict(evaluable=0)
    point=ba(np.arange(len(valid)));rng=np.random.default_rng(SEED+88);bs=[]
    for _ in range(6000):
        v=ba(rng.integers(len(valid),size=len(valid)))
        if v is not None:bs.append(v)
    return dict(evaluable=len(valid),label='verified nontrivial remaining-propagation advantage abs(log-ratio)>0.10',
                conditional_on_both_continuations_finishing=True,flip_better=int(truth.sum()),
                base_better=int((~truth).sum()),predicted_flips=int(pred.sum()),
                accuracy=float((pred==truth).mean()),always_base_accuracy=float((~truth).mean()),
                balanced_accuracy=point,balanced_accuracy_formula_bootstrap95=np.quantile(bs,[.025,.975]).tolist() if bs else None,
                flip_precision=float(truth[pred].mean()) if pred.any() else None)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,default=Path('build/drnas-x45a'))
    ap.add_argument('--out',type=Path,default=Path('x45a_results'))
    ap.add_argument('--per-family',type=int,default=48)
    ap.add_argument('--cap',type=float,default=.4)
    ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args()
    if args.per_family<16 or args.cap<.1 or args.repeats<2:raise ValueError('benchmark too small')
    args.out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    started=time.perf_counter()
    cohorts={split:[make_case(f,i) for f in families for i in range(args.per_family)]
             for split,families in [('train',TRAIN),('validation',VALIDATION),('holdout',HOLDOUT)]}
    cases=[c for cc in cohorts.values() for c in cc]
    assert len({c['sha256'] for c in cases})==len(cases)
    manifest={split:[{k:c[k] for k in ('family','index','sha256','n')} for c in cc] for split,cc in cohorts.items()}
    save(args.out/'manifest.json',manifest)
    save(args.out/'protocol.json',dict(families=dict(train=TRAIN,validation=VALIDATION,holdout=HOLDOUT),
         features=FEATURES,decision_index=DECISION,per_family=args.per_family,cap=args.cap,repeats=args.repeats,
         primary_comparison='LEARNED vs CORE paired holdout E2E PAR2; success lower95>10%',
         mandatory_controls=POLICIES,training_target='verified continuation propagation work',
         no_holdout_tuning=True,synthetic_SAT_only=True,seed=SEED))
    cnf=args.out/'current.cnf'
    pairs={}
    for split in ('train','validation'):
        rows=[]
        with (args.out/f'{split}_pairs.jsonl').open('w') as fd:
            for i,c in enumerate(cohorts[split]):
                cnf.write_text(c['source']);r=pair(binary,cnf,c,args.cap);rows.append(r)
                fd.write(json.dumps(r,sort_keys=True)+'\n');fd.flush()
                if (i+1)%48==0:emit('X45A_COLLECTION',dict(split=split,done=i+1,total=len(cohorts[split]),labeled=sum(x['label'] is not None for x in rows)))
        pairs[split]=rows
    model=select_threshold(fit(pairs['train']),pairs['validation'])
    save(args.out/'frozen_model.json',model);mp=args.out/'frozen_model.txt';write_model(mp,model)
    frozen_sha=hashlib.sha256(mp.read_bytes()).hexdigest()
    emit('X45A_FROZEN',dict(threshold=model['threshold'],training_pairs=model['training_pairs'],sha256=frozen_sha,validation=model['validation_candidates']))
    trials=[];hp=[]
    with (args.out/'holdout_pairs.jsonl').open('w') as pf,(args.out/'holdout_trials.jsonl').open('w') as tf:
        for i,c in enumerate(cohorts['holdout']):
            cnf.write_text(c['source'])
            # Outcomes are recorded only after model freeze and never used for updates.
            pairrow=pair(binary,cnf,c,args.cap);hp.append(pairrow);pf.write(json.dumps(pairrow,sort_keys=True)+'\n');pf.flush()
            for rep in range(args.repeats):
                order=list(POLICIES);random.Random(SEED+i*17+rep).shuffle(order)
                arms={p:run(binary,cnf,c,p,args.cap,model=mp if p in ('sham','learned') else None) for p in order}
                if all(arms[p]['verified'] for p in ('core','sham')):
                    assert all(arms['core'][k]==arms['sham'][k] for k in ('propagations','conflicts','decisions')), 'SHAM changed search'
                learned=arms['learned']
                if learned['reached']:
                    score,ood=predict(model,learned['policy']['features'])
                    assert abs(score-learned['policy']['score'])<1e-7
                    assert learned['policy']['flipped']==(not ood and score>model['threshold'])
                row=dict(sha256=c['sha256'],family=c['family'],index=c['index'],repeat=rep,arms=arms)
                trials.append(row);tf.write(json.dumps(row,sort_keys=True)+'\n');tf.flush()
            if (i+1)%24==0:emit('X45A_HOLDOUT',dict(done=i+1,total=len(cohorts['holdout'])))
    assert hashlib.sha256(mp.read_bytes()).hexdigest()==frozen_sha
    cnf.unlink()
    groups=defaultdict(list)
    for r in trials:groups[r['sha256']].append(r)
    aggregates={p:dict(PAR2_s=sum(r['arms'][p]['PAR2'] for r in trials),
                SAT_verified=sum(r['arms'][p]['within_cap'] for r in trials),
                trials=len(trials),interventions=sum(r['arms'][p].get('policy',{}).get('flipped',False) for r in trials),
                E2E_s=sum(r['arms'][p]['wall_s'] for r in trials)) for p in POLICIES}
    means={p:[np.mean([r['arms'][p]['PAR2'] for r in rr]) for rr in groups.values()] for p in POLICIES}
    comparisons={base:effect(means[base],means['learned']) for base in ('core','sham','fixed','flip')}
    family_results={f:{p:dict(PAR2_s=sum(r['arms'][p]['PAR2'] for r in trials if r['family']==f),
                    SAT_verified=sum(r['arms'][p]['within_cap'] for r in trials if r['family']==f)) for p in POLICIES} for f in HOLDOUT}
    family_ci=effect([family_results[f]['core']['PAR2_s'] for f in HOLDOUT],
                     [family_results[f]['learned']['PAR2_s'] for f in HOLDOUT])
    # Work comparison only on matched sources solved by both arms, clearly conditional.
    work={}
    for base in ('core','fixed','sham','flip'):
        eligible=[r for r in trials if r['arms'][base]['within_cap'] and r['arms']['learned']['within_cap']]
        a=sum(r['arms'][base]['propagations'] for r in eligible);b=sum(r['arms']['learned']['propagations'] for r in eligible)
        work[base]=dict(both_solved_trials=len(eligible),base_propagations=a,learned_propagations=b,
                        reduction_pct=100*(1-b/a) if a else None,conditional_on_both_solved=True)
    report=dict(status='COMPLETE',original_sources=len(cases),split_sizes={k:len(v) for k,v in cohorts.items()},
        generated_family_regimes=16,holdout_family_count=5,cap_s=args.cap,repeats=args.repeats,
        one_logical_CPU=True,model_frozen_sha256=frozen_sha,selected_threshold=model['threshold'],
        train_exclusions=dict(Counter(r['exclusion'] or 'labeled' for r in pairs['train'])),
        validation_exclusions=dict(Counter(r['exclusion'] or 'labeled' for r in pairs['validation'])),
        holdout_exclusions=dict(Counter(r['exclusion'] or 'labeled' for r in hp)),
        arms=aggregates,learned_vs=comparisons,families=family_results,
        family_cluster_exploratory=family_ci,conditional_search_work=work,
        direction_prediction=prediction_report(model,hp),
        primary_success=comparisons['core']['paired_formula_bootstrap95_pct'][0]>10,
        training_and_evaluation_wall_s=time.perf_counter()-started,
        limits=['Synthetic SAT with verified witnesses, not official or industrial benchmark.',
                '16 generator regimes are not 16 independent mathematical problem classes.',
                'Only one polarity at decision 4 is changed; no general multi-step controller claim.',
                'Training labels exclude censored runs; prediction accuracy conditional on both finishing.',
                'Runtime PAR2 includes every holdout source, timeouts and startup/model/feature cost.',
                'Repeat timings clustered by original formula; only five holdout family regimes.',
                'Ensemble score is not a calibrated probability or confidence bound.',
                'Training cost is reported separately and not amortized into individual solve speed.',
                'No Kissat/CaDiCaL/CryptoMiniSat performance comparison in this mechanism experiment.'])
    save(args.out/'report.json',report);emit('X45A_FINAL',report)


if __name__=='__main__':main()
