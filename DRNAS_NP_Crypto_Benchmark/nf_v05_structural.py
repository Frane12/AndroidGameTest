#!/usr/bin/env python3
"""DRNAS NeuroFlow v0.5: train-only selection by cheap sign-oriented Horn defect.
Exact solving only: policy influences method choice, not SAT/UNSAT correctness.
"""
from dataclasses import dataclass
import time
from collections import defaultdict
from drnas_np_lab import solve as baseline_solve, solve_horn, check
from neuroflow_v03 import renamable_horn

@dataclass
class Features:
    defect: float
    defect_count: int
    majority_flips: list
    feature_ms: float
    bucket: str

@dataclass
class Outcome:
    status: str
    ms: float
    path: str
    feature_ms: float
    probe_ms: float
    defect: float
    model: list | None

def features(n, clauses):
    start=time.perf_counter()
    pos=[0]*n
    neg=[0]*n
    for clause in clauses:
        for lit in clause:
            if lit>0:pos[lit-1]+=1
            else:neg[-lit-1]+=1
    flips=[p>q for p,q in zip(pos,neg)]
    bad=sum(sum(bool(lit>0)^flips[abs(lit)-1] for lit in c)>1 for c in clauses)
    size='small' if n<45 else ('medium' if n<90 else 'large')
    return Features(bad/max(1,len(clauses)),bad,flips,(time.perf_counter()-start)*1000,size)

def solve_strategy(n, clauses, variant='base', threshold=-1.0, budget=1.8, cap_ms=22.0):
    start=time.perf_counter()
    if variant not in ('base','always','learned'):raise ValueError(variant)
    feat=features(n,clauses) if variant=='learned' else None
    feature_ms=feat.feature_ms if feat else 0.0
    probe_ms=0.0
    if variant=='learned' and threshold>=0 and feat.defect_count==0:
        t=time.perf_counter()
        transformed=[tuple(-lit if feat.majority_flips[abs(lit)-1] else lit for lit in c) for c in clauses]
        assert all(sum(l>0 for l in c)<=1 for c in transformed)
        status,model=solve_horn(n,transformed)
        if model is not None:
            model=[bool(v)^bool(f) for v,f in zip(model,feat.majority_flips)]
        if status=='SAT':assert model is not None and check(clauses,model)
        return Outcome(status,(time.perf_counter()-start)*1000,'direct-majority-Horn',feature_ms,
                       (time.perf_counter()-t)*1000,feat.defect,model)
    probe=variant=='always' or (variant=='learned' and threshold>=0 and feat.defect<=threshold)
    if probe:
        t=time.perf_counter()
        end=min(t+cap_ms/1000,start+budget)
        candidate,reason,_=renamable_horn(n,clauses,probe_deadline=end)
        probe_ms=(time.perf_counter()-t)*1000
        if candidate is not None:
            flips,transformed=candidate
            status,model=solve_horn(n,transformed)
            if model is not None:model=[bool(v)^bool(f) for v,f in zip(model,flips)]
            if status=='SAT':assert model is not None and check(clauses,model)
            return Outcome(status,(time.perf_counter()-start)*1000,'exact-renamable-Horn',
                           feature_ms,probe_ms,feat.defect if feat else -1.0,model)
        path='probe-failed:'+reason
    else:path='base'
    remaining=max(.0001,budget-(time.perf_counter()-start))
    result=baseline_solve(n,clauses,budget=remaining)
    if result.status=='SAT':assert result.assignment is not None and check(clauses,result.assignment)
    return Outcome(result.status,(time.perf_counter()-start)*1000,path,feature_ms,probe_ms,
                   feat.defect if feat else -1.0,result.assignment)

THRESHOLDS=(-1.0,0.0,0.01,0.03,0.06,0.10,0.18,0.30)

def fit(rows,penalty_ms=0.10,minimum_cases=12):
    grouped=defaultdict(list)
    for x in rows:grouped[x['bucket']].append(x)
    table={}
    for bucket,group in sorted(grouped.items()):
        grid=[]
        for threshold in THRESHOLDS:
            gains=[]
            for x in group:
                use=(threshold>=0 and x['defect']<=threshold)
                actual=x['candidate_ms'] if use else x['base_ms']+x['feature_ms']
                gains.append(x['base_ms']-actual)
            mean=sum(max(-50,min(50,g)) for g in gains)/len(gains)
            utility=mean-(penalty_ms if threshold>=0 else 0)
            grid.append({'threshold':threshold,'mean_gain_ms':round(mean,4),'utility':round(utility,4),
                         'chosen':sum(threshold>=0 and x['defect']<=threshold for x in group),'count':len(group)})
        best=max(grid,key=lambda x:(x['utility'],-x['threshold']))
        threshold=best['threshold'] if len(group)>=minimum_cases and best['utility']>0.08 else -1.0
        table[bucket]={'threshold':threshold,'train_cases':len(group),
                       'best_train_utility':best['utility'],'grid':grid}
    return {'version':'v0.5','frozen':True,'table':table,'no_holdout_updates':True,
            'features':'majority-polarity Horn defect','penalty_ms':penalty_ms}

def decision(model,n,clauses):
    key='small' if n<45 else ('medium' if n<90 else 'large')
    return float(model['table'].get(key,{'threshold':-1})['threshold'])
