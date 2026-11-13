#!/usr/bin/env python3
"""X4.4 controlled first-polarity interventions from a deterministic replay.

300 DISTINCT deterministic planted SAT CNFs; 10 families, 30 each; 180/60/60
family-disjoint TRAIN/VALIDATION/HOLDOUT. Never select an instance by outcome.
An identical prestate fingerprint is required for paired runs. Both branches
continue a complete CDCL solver, with full backtracking, not SAT under a
permanent assumption. Hard time limits create censored outcomes, not labels.
No claim of true SAT distance or causal effect beyond this controlled policy.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, os, pathlib, statistics, subprocess, sys, time
from pathlib import Path
import drnas_x42_1000 as G

ROOT=Path('drnas_x44_results')
EXEC=Path('build/drnas-x44')
SHARDS=10
CAP=2.5
N_PER_FAMILY=30
N_SOURCES=300
G.SAMPLE_HASH='x44-300-paired-polarity-v1-20261113'
LABELS=('positive','negative')
FEATURES=('assigned_fraction','depth_fraction','conflict_ratio','learned_ratio',
          'open_long_fraction','positive_fraction','binary_fraction','phase_is_positive',
          'nvars_log','nclauses_log')

def emit(tag,obj):print(tag+' '+json.dumps(obj,sort_keys=True,separators=(',',':')),flush=True)

def manifest():
    sources=[]
    for split,fs in G.SPLITS.items():
        for family in fs:
            for rep in range(N_PER_FAMILY):
                s=G.gen_source(family,rep,ROOT/'generated')
                s['global_id']=len(sources)
                assert s['split']==split
                sources.append(s)
    assert len(sources)==N_SOURCES
    assert len({s['sha256'] for s in sources})==N_SOURCES
    fields=('global_id','formula_id','family','split','sha256','nvars','nclauses','source_kind')
    frozen=[{k:s[k] for k in fields} for s in sources]
    frozen_json=json.dumps(frozen,sort_keys=True,separators=(',',':'))+'\n'
    sha=hashlib.sha256(frozen_json.encode()).hexdigest()
    ROOT.mkdir(exist_ok=True)
    (ROOT/'manifest.json').write_text(frozen_json)
    return sources,sha

def check_witness(path,output,nvars):
    assign={}
    for line in output.splitlines():
        if line.startswith('v '):
            for item in line[2:].split():
                lit=int(item)
                if lit:
                    if abs(lit)>nvars or abs(lit) in assign:return False
                    assign[abs(lit)]=(lit>0)
    if len(assign)!=nvars:return False
    clause=[];seen=0
    for line in path.read_text().splitlines():
        if not line or line.startswith(('p ','c','%')):continue
        for token in line.split():
            lit=int(token)
            if lit:clause.append(lit)
            else:
                if not any(assign[abs(l)]==(l>0) for l in clause):return False
                seen+=1;clause=[]
    return seen>0 and not clause

def execute(src,cap,checkpoint=-1,polarity=0):
    path=Path(src['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=src['sha256']:
        raise RuntimeError('source SHA changed before solve')
    command=[str(EXEC),str(path),'--mode','core','--time',str(cap),'--stats',
             '--checkpoint',str(checkpoint),'--force-polarity',str(polarity)]
    start=time.monotonic()
    try:result=subprocess.run(command,text=True,capture_output=True,timeout=cap+1.0)
    except subprocess.TimeoutExpired:
        return {'status':'UNKNOWN','e2e_s':round(time.monotonic()-start,6),
                'post_s':None,'checkpoint':None,'decisions':None,'process_timeout':True}
    elapsed=time.monotonic()-start
    if result.returncode not in (0,10,20):
        raise RuntimeError(f'Native process failure {src["formula_id"]} {result.returncode}: {result.stderr[-1200:]}')
    # All generated sources have a planted satisfying assignment; a native UNSAT
    # answer here is a correctness failure, not a permissible incomplete label.
    if result.returncode==20:
        raise RuntimeError('Native UNSAT contradicts independently planted SAT oracle')
    events={}
    for line in result.stderr.splitlines():
        if line.startswith('X44_STATS '):events['stats']=json.loads(line[10:])
        elif line.startswith('X44_CHECKPOINT '):events['checkpoint']=json.loads(line[15:])
    if 'stats' not in events:raise RuntimeError('missing native X44_STATS')
    status='UNKNOWN'
    if result.returncode==10:
        if not check_witness(path,result.stdout,src['nvars']):raise RuntimeError('invalid original-CNF witness')
        if elapsed<=cap:status='SAT_VERIFIED'
    return {'status':status,'e2e_s':round(elapsed,6),'post_s':(
            round(events['stats']['post_checkpoint_s'],6) if events.get('checkpoint') else None),
            'checkpoint':events.get('checkpoint'),'decisions':events['stats']['decisions'],
            'conflicts':events['stats']['conflicts'],'process_timeout':False}

def checkpoint_indices(decisions):
    if decisions<=0:return []
    return sorted(set([0,(decisions-1)//4,(decisions-1)//2,(3*(decisions-1))//4,decisions-1]))

def paired(src,baseline,cap):
    indices=checkpoint_indices(baseline.get('decisions') or 0) if baseline['status']=='SAT_VERIFIED' else []
    rows=[]
    for k in indices:
        # Reverse ordering across checkpoint / source to mitigate warm-cache bias.
        order=(1,-1) if (src['global_id']+k)%2==0 else (-1,1)
        by_sign={sign:execute(src,cap,k,sign) for sign in order}
        pos,neg=by_sign[1],by_sign[-1]
        a,b=pos['checkpoint'],neg['checkpoint']
        if a is None or b is None:
            # Unexpected checkpoint expiry is visible, but not a learnable pair.
            rows.append({'sha256':src['sha256'],'formula_id':src['formula_id'],
                'global_id':src['global_id'],'split':src['split'],'family':src['family'],
                'checkpoint_index':k,'match':False,'positive':without_meta(pos),
                'negative':without_meta(neg),'reason':'missing_checkpoint'})
            continue
        for field in ('prestate_fingerprint','selected_var','decision_index','default_sign'):
            if a[field]!=b[field]:
                raise RuntimeError('COUNTERFACTUAL STATE MISMATCH '+field+' '+src['formula_id'])
        row={'sha256':src['sha256'],'formula_id':src['formula_id'],'global_id':src['global_id'],
             'split':src['split'],'family':src['family'],'checkpoint_index':k,
             'match':True,'prestate_fingerprint':a['prestate_fingerprint'],
             'selected_var':a['selected_var'],'default_sign':a['default_sign'],
             'features':extract_features(src,a),
             'prefix_elapsed_s':round((a['prefix_elapsed_s']+b['prefix_elapsed_s'])/2,6),
             'positive':without_meta(pos),'negative':without_meta(neg)}
        rows.append(row)
    return rows

def without_meta(x):
    return {k:v for k,v in x.items() if k!='checkpoint'}

def extract_features(src,event):
    return [float(event[k]) for k in FEATURES[:8]]+[
         math.log1p(src['nvars']),math.log1p(src['nclauses'])]

def run_shard(args):
    sources,sha=manifest()
    if args.manifest_sha and sha!=args.manifest_sha:raise RuntimeError('frozen manifest SHA mismatch')
    chosen=[s for s in sources if s['global_id']%args.shards==args.shard]
    if len(chosen)!=30:raise RuntimeError('expected 30 cases in every shard')
    directory=ROOT/f'shard_{args.shard}';directory.mkdir(parents=True,exist_ok=True)
    cnt=collections.Counter(); start=time.monotonic()
    with (directory/'baselines.jsonl').open('w') as bf,(directory/'pairs.jsonl').open('w') as pf:
        for i,src in enumerate(chosen,1):
            base=execute(src,args.cap)
            bf.write(json.dumps({'global_id':src['global_id'],'sha256':src['sha256'],
                 'split':src['split'],'family':src['family'],**base},sort_keys=True)+'\n');bf.flush()
            cnt['baseline_total']+=1
            cnt['baseline_sat']+=base['status']=='SAT_VERIFIED'
            pairs=paired(src,base,args.cap)
            for p in pairs:
                pf.write(json.dumps(p,sort_keys=True,separators=(',',':'))+'\n');
                cnt['pairs']+=1
                cnt['state_matched']+=p['match']
                if p['match']:
                    cnt['both_sat']+=(p['positive']['status']=='SAT_VERIFIED' and p['negative']['status']=='SAT_VERIFIED')
            pf.flush()
            if i%5==0:emit('X44_PROGRESS',{'shard':args.shard,'completed':i,'total':len(chosen),**cnt})
    summary={'shard':args.shard,'shards':args.shards,'manifest_sha256':sha,
             'source_count':len(chosen),'cap_s':args.cap,'elapsed_wall_s':round(time.monotonic()-start,4),
             'counts':dict(cnt),'description':'same exact CDCL prefix, two first-polarity interventions; complete SAT search afterward'}
    (directory/'report.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
    emit('X44_SHARD_FINAL',summary)

def read_shards(folder,sha,shards):
    bl=[];pairs=[]
    for sh in range(shards):
        d=Path(folder)/f'x44-shard-{sh}'
        rep=json.loads((d/'report.json').read_text())
        if rep['manifest_sha256']!=sha or rep['shard']!=sh:raise RuntimeError('bad shard metadata')
        bl.extend(json.loads(s) for s in (d/'baselines.jsonl').read_text().splitlines())
        pairs.extend(json.loads(s) for s in (d/'pairs.jsonl').read_text().splitlines())
    if len(bl)!=300 or len({x['sha256'] for x in bl})!=300:
        raise RuntimeError('incomplete or duplicate baseline SHA')
    seen=set()
    for p in pairs:
        key=(p['sha256'],p['checkpoint_index'])
        if key in seen:raise RuntimeError('duplicate state pair')
        seen.add(key)
    return bl,pairs

def linear_solve(A,b):
    n=len(b);M=[list(row)+[v] for row,v in zip(A,b)]
    for i in range(n):
        pivot=max(range(i,n),key=lambda j:abs(M[j][i]))
        if abs(M[pivot][i])<1e-9:raise RuntimeError('singular matrix')
        M[i],M[pivot]=M[pivot],M[i]
        scale=M[i][i]
        for k in range(i,n+1):M[i][k]/=scale
        for j in range(n):
            if i==j:continue
            z=M[j][i]
            for k in range(i,n+1):M[j][k]-=z*M[i][k]
    return [M[i][-1] for i in range(n)]

def comparable(pair):
    return pair['match'] and all(pair[arm]['status']=='SAT_VERIFIED' and pair[arm]['post_s'] is not None for arm in LABELS)

def model_ready(pair):
    if not comparable(pair):return False
    a=pair['positive']['post_s'];b=pair['negative']['post_s']
    return abs(a-b)>=max(0.002,0.10*min(a,b))

def train(train,reg):
    d=len(FEATURES)
    norm_rows=[p['features'] for p in train]
    centers=[statistics.median(x[i] for x in norm_rows) for i in range(d)]
    scales=[max(.05,statistics.quantiles([x[i] for x in norm_rows],n=4)[2]-statistics.quantiles([x[i] for x in norm_rows],n=4)[0]) for i in range(d)]
    XX=[[1.]+[max(-5.,min(5.,(a-c)/s)) for a,c,s in zip(p['features'],centers,scales)] for p in train]
    Y=[max(-3.0,min(3.0,math.log((p['negative']['post_s']+.002)/(p['positive']['post_s']+.002)))) for p in train]
    cols=d+1
    A=[[0.0]*cols for _ in range(cols)];B=[0.0]*cols
    for x,y in zip(XX,Y):
        for i in range(cols):
            B[i]+=x[i]*y
            for j in range(cols):A[i][j]+=x[i]*x[j]
    for i in range(cols):A[i][i]+=reg if i else .001
    return {'version':1,'features':FEATURES,'centers':centers,'scales':scales,'weights':linear_solve(A,B),
            'lambda':reg,'n_training_states':len(train),'training_only':True}

def predict(model,p):
    x=[1.]+[max(-5.,min(5.,(a-c)/s)) for a,c,s in zip(p['features'],model['centers'],model['scales'])]
    score=sum(a*b for a,b in zip(x,model['weights']))
    return 'positive' if score>0 else 'negative'

def score(data,model):
    matched=[p for p in data if comparable(p)]
    strong=[p for p in matched if model_ready(p)]
    selected=[]
    outcomes={x:0. for x in ('default_phase','model','oracle','always_positive','always_negative')}
    won=0;correct=0
    for p in matched:
        pos=p['positive']['post_s'];neg=p['negative']['post_s']
        sign=model(p) if callable(model) else predict(model,p)
        phase='positive' if p['default_sign']>0 else 'negative'
        outcomes['default_phase']+=pos if phase=='positive' else neg
        outcomes['model']+=pos if sign=='positive' else neg
        outcomes['oracle']+=min(pos,neg)
        outcomes['always_positive']+=pos
        outcomes['always_negative']+=neg
        if model_ready(p):
            correct+=(sign==('positive' if pos<neg else 'negative'))
    return {'matched_pair_states':len(matched),'strong_signals':len(strong),
            'strong_fraction':round(len(strong)/max(1,len(matched)),5),
            'correct_strong':correct,'strong_accuracy':round(correct/max(1,len(strong)),5),
            'sum_continuation_wall_s':{k:round(v,6) for k,v in outcomes.items()},
            'model_improvement_over_default_pct':round(100*(1-outcomes['model']/max(1e-9,outcomes['default_phase'])),3) if matched else None,
            'oracle_gap_over_default_pct':round(100*(1-outcomes['oracle']/max(1e-9,outcomes['default_phase'])),3) if matched else None}

def bootstrap_formula_ci(data,model,seed=119,n=500):
    import random
    bysha=collections.defaultdict(list)
    for p in data:
        if comparable(p):bysha[p['sha256']].append(p)
    ids=sorted(bysha)
    if not ids:return None
    rng=random.Random(seed); gains=[]
    for _ in range(n):
        sampled=[p for _i in range(len(ids)) for p in bysha[rng.choice(ids)]]
        sums=score(sampled,model)['sum_continuation_wall_s']
        gains.append(100*(1-sums['model']/max(1e-9,sums['default_phase'])))
    gains.sort()
    return [round(gains[int(.025*len(gains))],3),round(gains[int(.975*len(gains))-1],3)]

def aggregate(args):
    sources,sha=manifest()
    if args.manifest_sha and sha!=args.manifest_sha:
        raise RuntimeError('aggregate frozen manifest SHA mismatch')
    baseline,pairs=read_shards(args.shard_dir,sha,args.shards)
    splitcounts=collections.Counter(x['split'] for x in baseline)
    if splitcounts!={'train':180,'validation':60,'holdout':60}:raise RuntimeError('split counts mismatch')
    expected={s['sha256']:s for s in sources}
    for b in baseline:
        if b['sha256'] not in expected or b['split']!=expected[b['sha256']]['split']:raise RuntimeError('unrecognized source')
    for p in pairs:
        if p['sha256'] not in expected or p['split']!=expected[p['sha256']]['split']:raise RuntimeError('unrecognized paired source')
    train_pairs=[p for p in pairs if p['split']=='train' and model_ready(p)]
    val_pairs=[p for p in pairs if p['split']=='validation']
    hold_pairs=[p for p in pairs if p['split']=='holdout']
    if len(train_pairs)<20:
        outcome={'status':'INSUFFICIENT_COMPLETE_PAIRS','n_training_pairs':len(train_pairs)}
    else:
        candidates=[]
        for reg in (.1,1.,10.,100.):
            model=train(train_pairs,reg)
            metrics=score(val_pairs,model)
            candidates.append((metrics['sum_continuation_wall_s']['model'],reg,model,metrics))
        _loss,chosen_reg,model,_metrics=min(candidates,key=lambda c:(c[0],c[1]))
        val=score(val_pairs,model)
        # ONLY NOW evaluate holdout with the frozen selected model.
        hold=score(hold_pairs,model)
        outcome={'status':'OFFLINE_SHADOW_ONLY','fit_only_train_sources':True,
                 'selection_only_validation_sources':True,'holdout_not_used_to_tune':True,
                 'model':model,'validation':val,'holdout':hold,
                 'holdout_formula_bootstrap_95pct_improvement_ci':bootstrap_formula_ci(hold_pairs,model),
                 'validation_candidates':[
                     {'regularization':reg,'continuation_s':round(v,5)} for v,reg,_,_ in candidates]}
    breakdown={}
    for split in ('train','validation','holdout'):
        sub_b=[b for b in baseline if b['split']==split]
        sub_p=[p for p in pairs if p['split']==split]
        strong=[p for p in sub_p if model_ready(p)]
        completed=[p for p in sub_p if comparable(p)]
        bshot=sum(b['status']=='SAT_VERIFIED' for b in sub_b)
        both_p=collections.Counter()
        for p in sub_p:
            if not p['match'] :both_p['not_matched']+=1;continue
            pa=p['positive']['status'];na=p['negative']['status']
            both_p[pa+'/'+na]+=1
        breakdown[split]={'source_count':len(sub_b),'baseline_sat_verified':bshot,
            'checkpoint_states_attempted':len(sub_p),
            'identical_prefix_verified':sum(p['match'] for p in sub_p),
            'both_sat_verified':len(completed),'strong_absolute_and_relative_signal':len(strong),
            'statuses':dict(both_p)}
    report={'status':'COMPLETE','manifest_sha256':sha,'source_count':300,'source_sha_unique_count':300,
         'selected_states':len(pairs),'total_counterfactual_solver_attempts':2*len(pairs),
         'source_type':'GENERATED_PLANTED_SAT_NOT_OFFICIAL',
         'checkpoint_policy':'five quantiles of ordinary baseline decision count, up to 5 per completed formula',
         'control':'same-state fingerprint; same chosen variable, opposite first polarity, full CDCL search after intervention',
         'cap_s':args.cap,'splits':breakdown,'shadow_learning':outcome,
         'limitations':'No claim of exact SAT distance. Only both-SAT pairs have duration labels; censored excluded. Single pair timings need repetition. Offline shadow model not deployed, no online speedup claim. Formula split by generator family.'}
    out=ROOT/'final';out.mkdir(exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    if outcome.get('model'):(out/'model_frozen.json').write_text(json.dumps(outcome['model'],indent=2,sort_keys=True)+'\n')
    emit('X44_FINAL',report)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=['freeze','shard','aggregate'])
    p.add_argument('--shard',type=int,default=0)
    p.add_argument('--shards',type=int,default=SHARDS)
    p.add_argument('--cap',type=float,default=CAP)
    p.add_argument('--manifest-sha',default='')
    p.add_argument('--shard-dir',default='x44_shards')
    args=p.parse_args()
    if args.shards!=SHARDS or args.shard not in range(SHARDS) or args.cap!=CAP:
        p.error('fixed experiment parameters only')
    if hasattr(os,'sched_setaffinity') and args.stage=='shard':
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    if args.stage=='freeze':
        sources,sha=manifest()
        emit('X44_MANIFEST_FROZEN',{'count':len(sources),'sha256':sha,'splits':dict(collections.Counter(s['split'] for s in sources))})
    elif args.stage=='shard':
        if not EXEC.is_file():p.error('native X44 executable not compiled')
        run_shard(args)
    else:aggregate(args)

if __name__=='__main__':main()