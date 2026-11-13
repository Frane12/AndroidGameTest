#!/usr/bin/env python3
"""DRNAS X4.5: 3x repeated same-state polarity counterfactual experiment.

Only pre-decision, read-only structural/local BCP features enter ranking.
No live policy is changed. Planted SAT instances, not official SAT Competition.
No same-SHA memoization; entire generator families split train/val/holdout.
A completed pair's relative continuation time is a conditional observation,
not proof of a universal distance to SAT or of general causal improvement.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, os, random, statistics, subprocess, sys, time
from pathlib import Path
import drnas_x44_counterfactual as OLD

ROOT=Path('drnas_x45_results')
EXEC=Path('build/drnas-x45')
OLD.G.SAMPLE_HASH='x45-300-repeat-local-v1-20261113'
OLD.ROOT=ROOT
SHARDS=10
CAP=2.5
REPEATS=3
LABELS=('positive','negative')
LEGACY=tuple(OLD.FEATURES)
LOCAL=('local_pos_occ','local_neg_occ','local_pos_bin','local_neg_bin',
       'local_pos_tri','local_neg_tri','local_pos_long','local_neg_long',
       'local_pos_imp_edges','local_neg_imp_edges',
       'probe_pos_implied','probe_neg_implied',
       'probe_pos_conflict','probe_neg_conflict',
       'probe_pos_inspected','probe_neg_inspected',
       'probe_pos_cutoff','probe_neg_cutoff')
VARIANTS={'legacy10':LEGACY,'local18':LOCAL,'combined28':LEGACY+LOCAL}
NONFEATURE={'prefix_elapsed_s','feature_elapsed_s','intervention_sign'}


def emit(event,obj):print(event+' '+json.dumps(obj,sort_keys=True,separators=(',',':')),flush=True)

def manifest():
    return OLD.manifest()

def independent_witness(path,output,n):
    return OLD.check_witness(path,output,n)

def execute(source,cap,checkpoint=-1,polarity=0):
    path=Path(source['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:
        raise RuntimeError('Source changed or incorrect SHA: '+source['formula_id'])
    cmd=[str(EXEC),str(path),'--mode','core','--time',str(cap),'--stats',
         '--checkpoint',str(checkpoint),'--force-polarity',str(polarity)]
    t0=time.monotonic()
    try:out=subprocess.run(cmd,text=True,capture_output=True,timeout=cap+1.5)
    except subprocess.TimeoutExpired:
        return {'status':'UNKNOWN','e2e_s':round(time.monotonic()-t0,6),
                'post_s':None,'checkpoint':None,'process_timeout':True}
    e2e=time.monotonic()-t0
    if out.returncode not in (0,10,20):
        raise RuntimeError(f'X45 failure {source["formula_id"]}: {out.returncode}: {out.stderr[-900:]}')
    if out.returncode==20:
        raise RuntimeError('Native UNSAT contradicts planted SAT ground truth')
    events={}
    for line in out.stderr.splitlines():
        if line.startswith('X45_STATS '):events['stats']=json.loads(line[len('X45_STATS '):])
        if line.startswith('X45_CHECKPOINT '):events['checkpoint']=json.loads(line[len('X45_CHECKPOINT '):])
    if 'stats' not in events:raise RuntimeError('Missing X45_STATS')
    status='UNKNOWN'
    if out.returncode==10:
        if not independent_witness(path,out.stdout,source['nvars']):
            raise RuntimeError('SAT witness INVALID on original source')
        if e2e<=cap:status='SAT_VERIFIED'
    cp=events.get('checkpoint')
    return {'status':status,'e2e_s':round(e2e,6),
            'post_s':round(events['stats']['post_checkpoint_s'],6) if cp else None,
            'checkpoint':cp,'decisions':events['stats']['decisions'],
            'conflicts':events['stats']['conflicts'],'process_timeout':False}

def features(source,checkpoint):
    d={k:float(checkpoint[k]) for k in LEGACY[:8]}
    d.update(nvars_log=math.log1p(source['nvars']),nclauses_log=math.log1p(source['nclauses']))
    for k in LOCAL:d[k]=float(checkpoint[k])
    # Pre-decision context only. No source IDs, labels, or future outcomes.
    # Log scaling helps regularization on heavy-tailed neighborhood sizes.
    for k in LOCAL:
        if k.endswith(('_occ','_bin','_tri','_long','_edges','_implied','_inspected')):
            d[k]=math.log1p(d[k])
    return d

def without_meta(row):return {k:v for k,v in row.items() if k!='checkpoint'}

def assert_same_prestate(ref,other,source):
    exact=('prestate_fingerprint','selected_var','decision_index','default_sign')+LOCAL
    exact+=LEGACY[:8]
    for key in exact:
        if ref[key]!=other[key]:
            raise RuntimeError(f'X45 same-state mismatch on {source["formula_id"]}: {key}: {ref[key]} != {other[key]}')
    if not ref['feature_read_only'] or not other['feature_read_only']:
        raise RuntimeError('Non-read-only features!')

def checkpoints(n):return OLD.checkpoint_indices(n)

def paired(source,baseline,cap):
    indices=checkpoints(baseline.get('decisions') or 0) if baseline['status']=='SAT_VERIFIED' else []
    rows=[]
    for k in indices:
        runs={label:[] for label in LABELS}
        checkpoint_ref=None
        timed=[]
        for rep in range(REPEATS):
            # Alternate ordering over repetitions, checkpoints and sources.
            signs=(1,-1) if (source['global_id']+k+rep)%2==0 else (-1,1)
            for sign in signs:
                result=execute(source,cap,k,sign)
                cp=result.get('checkpoint')
                if cp is not None:
                    if checkpoint_ref is None:checkpoint_ref=cp
                    else:assert_same_prestate(checkpoint_ref,cp,source)
                    timed.append(cp['feature_elapsed_s'])
                runs['positive' if sign==1 else 'negative'].append(without_meta(result))
        matched=bool(checkpoint_ref is not None and len(timed)==2*REPEATS and
                     all(len(runs[side])==REPEATS for side in LABELS))
        row={'sha256':source['sha256'],'formula_id':source['formula_id'],'global_id':source['global_id'],
             'split':source['split'],'family':source['family'],'checkpoint_index':k,
             'match':matched,'positive':runs['positive'],'negative':runs['negative'],
             'repeats':REPEATS}
        if checkpoint_ref:
            row.update(prestate_fingerprint=checkpoint_ref['prestate_fingerprint'],
                       selected_var=checkpoint_ref['selected_var'],
                       default_sign=checkpoint_ref['default_sign'],
                       features=features(source,checkpoint_ref),
                       measured_feature_seconds=statistics.median(timed),
                       prefix_elapsed_reference_s=checkpoint_ref['prefix_elapsed_s'])
        rows.append(row)
    return rows

def run_shard(args):
    sources,sha=manifest()
    if args.manifest_sha and sha!=args.manifest_sha:raise RuntimeError('Frozen manifest mismatch')
    chosen=[s for s in sources if s['global_id']%SHARDS==args.shard]
    if len(chosen)!=30:raise RuntimeError('Expected exactly 30 per shard')
    out=ROOT/f'shard_{args.shard}';out.mkdir(parents=True,exist_ok=False)
    counters=collections.Counter();started=time.monotonic()
    with (out/'baselines.jsonl').open('w') as bf,(out/'pairs.jsonl').open('w') as pf:
        for i,src in enumerate(chosen,1):
            base=execute(src,args.cap)
            bf.write(json.dumps(dict(global_id=src['global_id'],sha256=src['sha256'],
                     split=src['split'],family=src['family'],**without_meta(base)),sort_keys=True)+'\n');bf.flush()
            counters['sources']+=1
            counters['baseline_sat']+=base['status']=='SAT_VERIFIED'
            for row in paired(src,base,args.cap):
                pf.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n')
                counters['states']+=1
                counters['matched']+=row['match']
                counters['replays']+=2*REPEATS
                counters['complete_six']+=comparable(row)
            pf.flush()
            if i%5==0:emit('X45_PROGRESS',dict(shard=args.shard,completed=i,total=len(chosen),**counters))
    report={'shard':args.shard,'manifest_sha256':sha,'sources':len(chosen),
            'repeats':REPEATS,'cap_s':CAP,'duration_s':round(time.monotonic()-started,4),
            'counts':dict(counters)}
    (out/'report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    emit('X45_SHARD_FINAL',report)

def read_shards(path,sha):
    bl=[];pairs=[]
    for sh in range(SHARDS):
        root=Path(path)/f'x45-shard-{sh}'
        report=json.loads((root/'report.json').read_text())
        if report['shard']!=sh or report['manifest_sha256']!=sha:raise RuntimeError('Mismatch shard report')
        bl+=list(map(json.loads,(root/'baselines.jsonl').read_text().splitlines()))
        pairs+=list(map(json.loads,(root/'pairs.jsonl').read_text().splitlines()))
    if len(bl)!=300 or len({x['sha256'] for x in bl})!=300:raise RuntimeError('Bad baseline count/SHA')
    identities=[(p['sha256'],p['checkpoint_index']) for p in pairs]
    if len(set(identities))!=len(identities):raise RuntimeError('Duplicate checkpoints')
    return bl,pairs

def comparable(p):
    return p['match'] and all(len(p[side])==REPEATS and
        all(z['status']=='SAT_VERIFIED' and z['post_s'] is not None for z in p[side]) for side in LABELS)

def median_time(p,side):return statistics.median(z['post_s'] for z in p[side])

def mad(values):
    m=statistics.median(values)
    return statistics.median(abs(x-m) for x in values)

def robust_signal(p):
    if not comparable(p):return False
    pos=[x['post_s'] for x in p['positive']]
    neg=[x['post_s'] for x in p['negative']]
    pm,nm=statistics.median(pos),statistics.median(neg)
    delta=abs(pm-nm)
    threshold=max(.004,.15*min(pm,nm),2*max(mad(pos),mad(neg)))
    if delta<threshold:return False
    votes=sum((a<b)==(pm<nm) for a,b in zip(pos,neg))
    return votes>=2

def solve(A,b):return OLD.linear_solve(A,b)

def train(rows,variant,reg):
    names=VARIANTS[variant];d=len(names)
    med=[statistics.median(p['features'][k] for p in rows) for k in names]
    iqr=[]
    for k in names:
        v=sorted(p['features'][k] for p in rows)
        iqr.append(max(.05,v[(3*len(v))//4]-v[len(v)//4]))
    xx=[];yy=[];ww=[]
    bysha=collections.Counter(p['sha256'] for p in rows)
    for p in rows:
        xx.append([1.]+[max(-5.,min(5.,(p['features'][k]-a)/b)) for k,a,b in zip(names,med,iqr)])
        # A binary ranking target without pretending to know the absolute work.
        # Strong state pairs only, normalized to one formula's weight.
        pos=median_time(p,'positive');neg=median_time(p,'negative')
        yy.append(max(-2.,min(2.,math.log((neg+.002)/(pos+.002)))))
        ww.append(1.0/math.sqrt(bysha[p['sha256']]))
    A=[[0.0]*(d+1) for _ in range(d+1)];B=[0.0]*(d+1)
    for x,y,w in zip(xx,yy,ww):
        for i in range(d+1):
            B[i]+=w*x[i]*y
            for j in range(d+1):A[i][j]+=w*x[i]*x[j]
    for i in range(d+1):A[i][i]+=(.001 if i==0 else reg)
    return dict(kind='x45_ridge_pair_ranking',features=names,centers=med,scales=iqr,
                weights=solve(A,B),lambda_=reg,training_states=len(rows),training_only=True)

def predict(model,p):
    x=[1.]+[max(-5.,min(5.,(p['features'][k]-a)/b))
             for k,a,b in zip(model['features'],model['centers'],model['scales'])]
    score=sum(a*b for a,b in zip(model['weights'],x))
    return 'positive' if score>0 else 'negative'

def metrics(data,model):
    available=[p for p in data if comparable(p)]
    strong=[p for p in available if robust_signal(p)]
    cost=collections.Counter();correct=0
    for p in available:
        pos=median_time(p,'positive');neg=median_time(p,'negative')
        choice=predict(model,p) if isinstance(model,dict) else model(p)
        default='positive' if p['default_sign']>0 else 'negative'
        cost['model_with_features']+=pos if choice=='positive' else neg
        cost['default_with_features']+=pos if default=='positive' else neg
        cost['default_estimated_no_features']+=max(0.,(pos if default=='positive' else neg)-p['measured_feature_seconds'])
        cost['oracle_with_features']+=min(pos,neg)
        cost['always_positive']+=pos;cost['always_negative']+=neg
        cost['feature_measurements']+=p['measured_feature_seconds']
        if robust_signal(p):correct+=int(choice==('positive' if pos<neg else 'negative'))
    return dict(completed_states=len(available),strong_states=len(strong),
                strong_fraction=round(len(strong)/max(1,len(available)),5),
                strong_accuracy=round(correct/max(1,len(strong)),5),
                signed_time_gain_pct=round(100*(1-cost['model_with_features']/max(1e-9,cost['default_with_features'])),4),
                estimated_net_gain_pct=round(100*(1-cost['model_with_features']/max(1e-9,cost['default_estimated_no_features'])),4),
                hypothetical_oracle_gap_pct=round(100*(1-cost['oracle_with_features']/max(1e-9,cost['default_with_features'])),4),
                continuation_time_s={k:round(cost[k],6) for k in ('model_with_features','default_with_features','default_estimated_no_features','oracle_with_features','feature_measurements','always_positive','always_negative')})

def bootstrap_by_formula(data,model,seed=42,n=400):
    bysha=collections.defaultdict(list)
    for p in data:
        if comparable(p):bysha[p['sha256']].append(p)
    sha=sorted(bysha)
    if not sha:return None
    rng=random.Random(seed);gains=[]
    for _ in range(n):
        chosen=[p for __ in range(len(sha)) for p in bysha[rng.choice(sha)]]
        gains.append(metrics(chosen,model)['estimated_net_gain_pct'])
    gains.sort()
    return [round(gains[int(.025*n)],3),round(gains[int(.975*n)-1],3)]

def aggregate(args):
    sources,sha=manifest()
    if args.manifest_sha and args.manifest_sha!=sha:raise RuntimeError('Frozen manifest mismatch')
    baselines,pairs=read_shards(args.shard_dir,sha)
    splitc=collections.Counter(x['split'] for x in baselines)
    if splitc!={'train':180,'validation':60,'holdout':60}:raise RuntimeError('Split mismatch')
    good_sha={s['sha256']:s for s in sources}
    for p in pairs:
        if p['sha256'] not in good_sha or p['split']!=good_sha[p['sha256']]['split']:
            raise RuntimeError('Unknown source or split')
    trainpairs=[p for p in pairs if p['split']=='train' and robust_signal(p)]
    validation=[p for p in pairs if p['split']=='validation']
    holdout=[p for p in pairs if p['split']=='holdout']
    if len(trainpairs)<25:
        outcome={'status':'INSUFFICIENT_ROBUST_TRAIN_PAIRS','train_pairs':len(trainpairs)}
    else:
        candidates=[]
        for variant in ('legacy10','local18','combined28'):
            for reg in (0.1,1.,10.,100.):
                model=train(trainpairs,variant,reg)
                sc=metrics(validation,model)
                candidates.append((sc['continuation_time_s']['model_with_features'],variant,reg,model,sc))
        candidates.sort(key=lambda x:(x[0],x[1],x[2]))
        _,v,reg,model,validation_result=candidates[0]
        # Holdout touched ONLY after freezing selected model by validation.
        hold_result=metrics(holdout,model)
        outcome=dict(status='OFFLINE_SHADOW_ONLY',selected_variant=v,selected_lambda=reg,
                training_only=True,validation_only_model_selection=True,holdout_not_used_to_tune=True,
                model=model,validation=validation_result,holdout=hold_result,
                holdout_95pct_formula_bootstrap_net_gain_ci=bootstrap_by_formula(holdout,model),
                validation_options=[dict(variant=x[1],regularization=x[2],continuation_s=round(x[0],5)) for x in candidates],
                warning='Pair continuation time is conditional and censoring excludes hardest states; no live policy improvement claim.')
    summary={}
    for split in ('train','validation','holdout'):
        b=[x for x in baselines if x['split']==split]
        p=[x for x in pairs if x['split']==split]
        summary[split]=dict(sources=len(b),baseline_verified_sat=sum(x['status']=='SAT_VERIFIED' for x in b),
              states=len(p),matched_states=sum(x['match'] for x in p),
              complete_three_repeats=sum(comparable(x) for x in p),
              robust_differences=sum(robust_signal(x) for x in p),
              censored_or_incomplete=sum(not comparable(x) for x in p),
              repeated_solver_attempts=2*REPEATS*len(p),
              measured_feature_cost_s=round(sum(x.get('measured_feature_seconds',0) for x in p),6))
    report=dict(status='COMPLETE',manifest_sha256=sha,source_count=len(sources),
        unique_SHA=len(good_sha),splits=summary,repeats=REPEATS,
        total_states=len(pairs),total_counterfactual_attempts=2*REPEATS*len(pairs),
        source_type='GENERATED_PLANTED_SAT_NOT_OFFICIAL',
        training_rule='robust paired median differences, consistent 2 of 3 repeats, train-only',
        shadow_learning=outcome,
        limits='Read-only local features; repeated timings but no full saved-state clone; deterministic replay with matched fingerprints. Planted SAT not official. No trained in-solver policy; no causal guarantee or absolute SAT distance. Costs of collecting both counterfactuals excluded from shadow policy, but feature cost included. Censored outcomes kept separate.')
    out=ROOT/'final';out.mkdir(exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    if outcome.get('model'):(out/'frozen_model.json').write_text(json.dumps(outcome['model'],indent=2,sort_keys=True)+'\n')
    emit('X45_FINAL',report)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=('freeze','shard','aggregate'))
    parser.add_argument('--shard',type=int,default=0)
    parser.add_argument('--shards',type=int,default=SHARDS)
    parser.add_argument('--cap',type=float,default=CAP)
    parser.add_argument('--manifest-sha',default='')
    parser.add_argument('--shard-dir',default='x45_shards')
    args=parser.parse_args()
    if args.shards!=SHARDS or not 0<=args.shard<SHARDS or args.cap!=CAP:
        parser.error('Frozen experiment parameters only')
    if args.stage=='freeze':
        sources,sha=manifest()
        emit('X45_MANIFEST_FROZEN',dict(total=len(sources),sha=sha,split=dict(collections.Counter(s['split'] for s in sources)),repeats=REPEATS))
    elif args.stage=='shard':
        if not EXEC.is_file():parser.error('Must compile X45 C++ first')
        if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        run_shard(args)
    else:aggregate(args)

if __name__=='__main__':main()
