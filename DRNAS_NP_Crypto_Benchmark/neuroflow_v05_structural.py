"""DRNAS NeuroFlow v0.5: structural Horn-defect gate with frozen training policy."""
from collections import defaultdict
from drnas_np_lab import solve, solve_horn, check
from neuroflow_v03 import renamable_horn
import time, statistics, json

THRESHOLDS=(-1.0,0.0,.01,.03,.06,.10,.18,.30)

def structure(n,clauses):
    t=time.perf_counter()
    positive=[0]*n;negative=[0]*n
    for clause in clauses:
        for lit in clause:
            if lit>0:positive[lit-1]+=1
            else:negative[-lit-1]+=1
    flips=[a>b for a,b in zip(positive,negative)]
    bad=sum(sum(((lit>0)^flips[abs(lit)-1]) for lit in c)>1 for c in clauses)
    tier='small' if n<45 else ('medium' if n<90 else 'large')
    return {'defect':bad/max(1,len(clauses)),'bad':bad,'flips':flips,
            'tier':tier,'feature_ms':(time.perf_counter()-t)*1000}

def execute(n,clauses,mode='base',threshold=-1,budget=1.8):
    assert mode in ('base','always','learned')
    t0=time.perf_counter(); info=None;probe_ms=0.0
    if mode=='learned':
        info=structure(n,clauses)
        if threshold>=0 and info['bad']==0:
            flipped=[tuple(-lit if info['flips'][abs(lit)-1] else lit for lit in c) for c in clauses]
            assert all(sum(lit>0 for lit in c)<=1 for c in flipped)
            status,model=solve_horn(n,flipped)
            if model is not None:model=[bool(x)^bool(f) for x,f in zip(model,info['flips'])]
            path='direct-majority-Horn'
            if status=='SAT':assert check(clauses,model)
            return dict(status=status,ms=(time.perf_counter()-t0)*1000,path=path,
                        model=model,probe_ms=0,feature_ms=info['feature_ms'])
        probe=threshold>=0 and info['defect']<=threshold
    else: probe=(mode=='always')
    if probe:
        tp=time.perf_counter()
        candidate,reason,_=renamable_horn(n,clauses,
            probe_deadline=min(tp+.022,t0+budget))
        probe_ms=(time.perf_counter()-tp)*1000
        if candidate:
            flips,newcnf=candidate
            status,model=solve_horn(n,newcnf)
            if model is not None:model=[bool(x)^bool(f) for x,f in zip(model,flips)]
            if status=='SAT':assert check(clauses,model)
            return dict(status=status,ms=(time.perf_counter()-t0)*1000,
                        path='renamable-Horn',model=model,probe_ms=probe_ms,
                        feature_ms=info['feature_ms'] if info else 0.0)
    remaining=max(.00001,budget-(time.perf_counter()-t0))
    r=solve(n,clauses,budget=remaining)
    if r.status=='SAT':assert check(clauses,r.assignment)
    return dict(status=r.status,ms=(time.perf_counter()-t0)*1000,
                path='fallback' if probe else 'baseline',model=r.assignment,
                probe_ms=probe_ms,feature_ms=info['feature_ms'] if info else 0.0)

def fit_training(records):
    groups=defaultdict(list)
    for r in records:groups[r['tier']].append(r)
    table={}
    for tier,rs in sorted(groups.items()):
        candidates=[]
        for threshold in THRESHOLDS:
            gains=[];selected=0
            for r in rs:
                selected_here=threshold>=0 and r['defect']<=threshold
                selected+=int(selected_here)
                alt=r['candidate_ms'] if selected_here else r['base_ms']+r['feature_ms']
                gains.append(max(-50,min(50,r['base_ms']-alt)))
            avg=sum(gains)/len(gains)
            score=avg-(.10 if threshold>=0 else 0)
            candidates.append((score,threshold,avg,selected))
        candidates.sort(reverse=True)
        best=candidates[0]
        threshold=best[1] if len(rs)>=12 and best[0]>.08 else -1.0
        table[tier]={'threshold':threshold,'samples':len(rs),
                     'net_gain_training_ms':round(best[2],4),
                     'selected_on_training':best[3]}
    return {'version':'v0.5','frozen':True,'table':table,
            'learned_from':'train_only','updated_on_holdout':False}

def choose(model,n):
    tier='small' if n<45 else ('medium' if n<90 else 'large')
    return model['table'].get(tier,{'threshold':-1})['threshold']
