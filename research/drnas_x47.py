#!/usr/bin/env python3
"""Frozen single-decision policy trained on verified matched-state continuation work.

No oracle/witness/family/SHA enters inference. Synthetic SAT only for performance;
small independently exhaustive UNSAT controls are in tests/test_x47.py.
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
from x47_models import fit,predict,choose,select_threshold,write_model

TRAIN = ('uniform3','dense3','uniform4','xor_mixed','community','color3','local_band','polarity_skew')
VALIDATION = ('uniform5','ring_xor','hub6')
HOLDOUT = ('widthmix','grid_xor','circuit','community_bridge','color4')
FEATURES = ('log_n','log_density','assigned_fraction','depth_fraction','log_conflicts',
            'log_learnt','weighted_flip_minus_base','binary_flip_minus_base',
            'ternary_flip_minus_base','selected_open_fraction','binary_open_fraction',
            'long_open_fraction','initial_phase_balance','learnt_fraction','log_decisions',
            'base_probe_conflict','flip_probe_conflict','base_probe_log_units','flip_probe_log_units',
            'probe_unit_difference','base_probe_complete','flip_probe_complete','base_probe_budget','flip_probe_budget')
POLICIES = ('core','sham','static','fixed','ridge','tree')
WORK_LIMIT=100000
DECISION = 4
SEED = 471311


def emit(tag, x):
    print(tag+' '+json.dumps(x,sort_keys=True,separators=(',',':')),flush=True)


def save(path, data):
    path.write_text(json.dumps(data,indent=2,sort_keys=True,allow_nan=False)+'\n')


def make_case(family, index, namespace='x47-frozen-v1'):
    seed=int.from_bytes(hashlib.sha256(f'{namespace}:{family}:{index}'.encode()).digest()[:8],'big')
    rng=random.Random(seed)
    n=96+6*(index%9)
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
        nodes=30+index%17;n=nodes*colors
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
        inputs=24;n=inputs+60+index%24
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
            side=10;n=side*side;witness=[False]+[bool(rng.getrandbits(1)) for _ in range(n)]
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



def run(binary,path,case,policy,cap,model=None,flip=False,work_limit=0):
    native='learned' if policy in ('ridge','tree') else policy
    cmd=[str(binary),str(path),'--mode','core','--time',str(cap),'--stats','--branch-at',str(DECISION),'--policy',native,'--work-limit',str(work_limit)]
    if model:cmd+=['--model',str(model)]
    if flip:cmd+=['--flip-branch']
    start=time.perf_counter()
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=15 if work_limit else cap+2)
    except subprocess.TimeoutExpired:
        if work_limit:raise RuntimeError('work-limited trial hit emergency wall guard; do not train on timing-dependent labels')
        return dict(status='TIMEOUT',verified=False,within_cap=False,reached=False,PAR2=2*cap,wall_s=time.perf_counter()-start)
    wall=time.perf_counter()-start
    if p.returncode not in (0,10,20):raise RuntimeError(p.stderr)
    if p.returncode==20:raise AssertionError('UNSAT on independently checked planted SAT')
    if p.returncode==10 and not witness_ok(p.stdout,case):raise AssertionError('invalid SAT witness')
    data={line.split(' ',1)[0]:json.loads(line.split(' ',1)[1]) for line in p.stderr.splitlines() if line.startswith(('X41_STATS ','X45_COMPARE ','X47_POLICY '))}
    stats,pre,pol=(data[k] for k in ('X41_STATS','X45_COMPARE','X47_POLICY'))
    verified=p.returncode==10;within=verified and (cap==0 or wall<=cap)
    if work_limit and not verified and not pol['work_limit_hit']:raise AssertionError('unexplained deterministic UNKNOWN')
    return dict(status='SAT_VERIFIED' if verified else 'UNKNOWN',verified=verified,within_cap=within,wall_s=wall,
        PAR2=wall if within else 2*cap,reached=pre['reached'],pre=pre,policy=pol,
        propagations=stats['propagations'],decisions=stats['decisions'],conflicts=stats['conflicts'],
        work_cost=stats['propagations'] if verified else 2*work_limit,
        remaining_propagations=stats['propagations']-pre['prefix_propagations'] if pre['reached'] else None)


def pair(binary,path,case):
    order=[False,True] if case['index']%2 else [True,False]
    rr={f:run(binary,path,case,'collect',0,flip=f,work_limit=WORK_LIMIT) for f in order}
    b,f=rr[False],rr[True];row={k:case[k] for k in ('family','index','sha256','n')}
    row.update(base=b,flip=f,label=None,features=None,exclusion='checkpoint_not_reached')
    assert b['reached']==f['reached']
    if not b['reached']:return row
    for key in ('pre_state_digest','baseline_literal','prefix_conflicts','prefix_learnt','prefix_propagations'):assert b['pre'][key]==f['pre'][key]
    assert b['policy']['features']==f['policy']['features']
    assert b['pre']['actual_literal']==-f['pre']['actual_literal']
    row['features']=b['policy']['features']
    if b['verified'] and f['verified']:
        row['label']=math.log1p(b['remaining_propagations'])-math.log1p(f['remaining_propagations']);row['exclusion']=None
    else:row['exclusion']='work_censored'
    return row


def effect(a,b,draws=6000):
    a=np.asarray(a,float);b=np.asarray(b,float);rng=np.random.default_rng(SEED+99)
    values=[]
    for _ in range(draws):
        idx=rng.integers(len(a),size=len(a));values.append(100*(1-b[idx].sum()/a[idx].sum()))
    return dict(improvement_pct=float(100*(1-b.sum()/a.sum())),
                paired_formula_bootstrap95_pct=np.quantile(values,[.025,.975]).tolist(),
                original_formula_units=len(a),draws=draws)


def discrimination(model,rows):
    rr=[r for r in rows if r['label'] is not None and abs(r['label'])>.1]
    y=np.array([r['label']>0 for r in rr]);s=np.array([predict(model,r['features'])[0] for r in rr])
    preds=np.array([choose(model,r['features']) for r in rr])
    def auc(a,b):
        p=b[a];n=b[~a]
        return float(np.mean((p[:,None]>n).astype(float)+.5*(p[:,None]==n))) if len(p) and len(n) else None
    rng=np.random.default_rng(SEED);bs=[]
    for _ in range(3000):
        ii=rng.integers(len(y),size=len(y));v=auc(y[ii],s[ii])
        if v is not None:bs.append(v)
    return dict(n=len(rr),auc=auc(y,s),auc_formula95=np.quantile(bs,[.025,.975]).tolist() if bs else None,
        balanced_accuracy=float((preds[y].mean()+(~preds[~y]).mean())/2) if y.any() and (~y).any() else None,
        accepted_flips=int(preds.sum()),conditional_on_completed_nontrivial_pairs=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--binary',type=Path,default=Path('build/drnas-x47'))
    ap.add_argument('--out',type=Path,default=Path('x47_results'));ap.add_argument('--per-family',type=int,default=48)
    ap.add_argument('--cap',type=float,default=.8);ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args()
    if args.per_family<16 or args.cap<.1 or args.repeats<2:raise ValueError('insufficient benchmark size')
    args.out.mkdir(parents=True,exist_ok=False);binary=args.binary.resolve()
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    started=time.perf_counter()
    cohorts={split:[make_case(f,i) for f in families for i in range(args.per_family)] for split,families in [('train',TRAIN),('validation',VALIDATION),('holdout',HOLDOUT)]}
    allcases=[c for cases in cohorts.values() for c in cases];assert len({c['sha256'] for c in allcases})==len(allcases)
    save(args.out/'manifest.json',{s:[{k:c[k] for k in ('family','index','n','sha256')} for c in cc] for s,cc in cohorts.items()})
    save(args.out/'protocol.json',dict(features=FEATURES,train=TRAIN,validation=VALIDATION,holdout=HOLDOUT,
        work_limit=WORK_LIMIT,shadow_literal_budget_per_polarity=8192,decision=DECISION,cap=args.cap,repeats=args.repeats,
        primary='validation-selected model vs CORE E2E PAR2, lower95 >10%',
        secondary='RIDGE/TREE/FIXED/STATIC/SHAM comparisons exploratory, not multiplicity-adjusted',
        known_generator_regimes_fresh_SHA=True,training_no_wall_time_cutoff=True))
    cnf=args.out/'current.cnf';pairs={}
    for split in ('train','validation'):
        rows=[]
        with (args.out/f'{split}_pairs.jsonl').open('w') as fd:
            for i,c in enumerate(cohorts[split]):
                cnf.write_text(c['source']);r=pair(binary,cnf,c);rows.append(r);fd.write(json.dumps(r,sort_keys=True)+'\n');fd.flush()
                if (i+1)%48==0:emit('X47_COLLECTION',dict(split=split,done=i+1,total=len(cohorts[split]),labeled=sum(x['label'] is not None for x in rows)))
        pairs[split]=rows
    models={k:select_threshold(m,pairs['validation']) for k,m in fit(pairs['train']).items()}
    winner=min(models,key=lambda k:(models[k]['validation_work_cost'],k!='ridge'))
    paths={k:args.out/f'{k}_model.txt' for k in models}
    save(args.out/'frozen_models.json',dict(models=models,primary=winner))
    for k,m in models.items():write_model(paths[k],m)
    hashes={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()}
    label_digest=hashlib.sha256(json.dumps([(r['sha256'],r['features'],r['label'],r['base']['work_cost'],r['flip']['work_cost']) for split in ('train','validation') for r in pairs[split]],sort_keys=True).encode()).hexdigest()
    emit('X47_FROZEN',dict(primary=winner,model_sha=hashes,label_digest=label_digest,thresholds={k:m['threshold'] for k,m in models.items()},validation_costs={k:m['validation_work_cost'] for k,m in models.items()}))
    trials=[];hp=[]
    with (args.out/'holdout_pairs.jsonl').open('w') as pf,(args.out/'holdout_trials.jsonl').open('w') as tf:
        for i,c in enumerate(cohorts['holdout']):
            cnf.write_text(c['source']);r=pair(binary,cnf,c);hp.append(r);pf.write(json.dumps(r,sort_keys=True)+'\n');pf.flush()
            for rep in range(args.repeats):
                order=list(POLICIES);random.Random(SEED+i*17+rep).shuffle(order)
                arms={k:run(binary,cnf,c,k,args.cap,model=paths[winner] if k=='sham' else paths.get(k)) for k in order}
                if arms['core']['verified'] and arms['sham']['verified']:
                    assert all(arms['core'][k]==arms['sham'][k] for k in ('propagations','conflicts','decisions')),'shadow probes changed core path'
                for k in models:
                    a=arms[k]
                    if a['reached']:
                        score,_=predict(models[k],a['policy']['features'])
                        assert abs(score-a['policy']['score'])<1e-7
                        assert a['policy']['flipped']==choose(models[k],a['policy']['features'])
                row=dict(sha256=c['sha256'],family=c['family'],index=c['index'],repeat=rep,arms=arms)
                trials.append(row);tf.write(json.dumps(row,sort_keys=True)+'\n');tf.flush()
            if (i+1)%24==0:emit('X47_HOLDOUT',dict(done=i+1,total=len(cohorts['holdout'])))
    assert hashes=={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()};cnf.unlink()
    groups=defaultdict(list)
    for r in trials:groups[r['sha256']].append(r)
    totals={k:dict(PAR2_s=sum(r['arms'][k]['PAR2'] for r in trials),SAT_verified=sum(r['arms'][k]['within_cap'] for r in trials),
            trials=len(trials),interventions=sum(r['arms'][k].get('policy',{}).get('flipped',False) for r in trials),
            forced_literal_decisions=sum(r['arms'][k].get('policy',{}).get('forced',False) for r in trials)) for k in POLICIES}
    means={k:[np.mean([r['arms'][k]['PAR2'] for r in rr]) for rr in groups.values()] for k in POLICIES}
    comparisons={k:effect(means['core'],means[k]) for k in POLICIES if k!='core'}
    families={f:{k:sum(r['arms'][k]['PAR2'] for r in trials if r['family']==f) for k in POLICIES} for f in HOLDOUT}
    work={}
    for k in POLICIES:
        rr=[r for r in trials if r['arms']['core']['within_cap'] and r['arms'][k]['within_cap']]
        base=sum(r['arms']['core']['propagations'] for r in rr);actual=sum(r['arms'][k]['propagations'] for r in rr)
        work[k]=dict(both_solved_trials=len(rr),base=base,actual=actual,reduction_pct=100*(1-actual/base) if base else None)
    report=dict(status='COMPLETE',primary_model=winner,primary_success=comparisons[winner]['paired_formula_bootstrap95_pct'][0]>10,
        original_sources=len(allcases),holdout_sources=len(cohorts['holdout']),repeats=args.repeats,cap_s=args.cap,
        training_work_limit=WORK_LIMIT,train_label_digest=label_digest,models_sha=hashes,
        thresholds={k:m['threshold'] for k,m in models.items()},
        exclusions={split:dict(Counter(r['exclusion'] or 'labeled' for r in rows)) for split,rows in {**pairs,'holdout':hp}.items()},
        arms=totals,vs_core=comparisons,primary_vs_sham=effect(means['sham'],means[winner]),
        primary_vs_fixed=effect(means['fixed'],means[winner]),families=families,conditional_search_work=work,
        primary_family_bootstrap=effect([families[f]['core'] for f in HOLDOUT],[families[f][winner] for f in HOLDOUT]),
        prediction={k:discrimination(m,hp) for k,m in models.items()},elapsed_s=time.perf_counter()-started,
        limits=['Generated SAT, no official industrial performance claim or competitor comparison.',
                'Fresh formula SHA, known generator regimes, disjoint train/validation/holdout families within this protocol.',
                'One intervention at decision 4; read-only capped unit propagation is not SAT distance.',
                'Training excludes work-censored pairs; validation penalizes unresolved cases by twice work limit.',
                'E2E test includes every source, timeouts and all model/probe/startup overhead.',
                'Formula-cluster repeats, only five holdout regimes; secondary comparisons exploratory.',
                'Forced failed-literal decisions are reported separately from learned benefit.'])
    save(args.out/'report.json',report);emit('X47_FINAL',report)


if __name__=='__main__':main()


