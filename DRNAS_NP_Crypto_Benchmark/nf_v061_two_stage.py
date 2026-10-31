#!/usr/bin/env python3
"""DRNAS NP Lab NeuroFlow v0.6.1: TWO-STAGE, train-only tuned, exact strategy.

Stage 1: cheap O(literals) sign/size screen.
Stage 2: full 17-dimensional signature ONLY after positive stage-1 gate.
Stage 3: sound renamable Horn proof/solve OR always-safe original solver.
No classification uses or predicts ground-truth SAT/UNSAT during inference.
"""
from __future__ import annotations
import time,statistics
from dataclasses import dataclass
from drnas_np_lab import check,solve as baseline_solve,solve_horn
from neuroflow_v03 import renamable_horn
from nf_v06_multifeature import signature

@dataclass
class Cheap:
    minority:float
    unit_share:float
    ms:float

@dataclass
class Result:
    status:str
    model:list|None
    elapsed_ms:float
    cheap_ms:float
    full_ms:float
    exact_ms:float
    route:str

DEFAULT={'enabled':False,'min_n':90,'max_minority':.26,
         'max_unit_share':.0,'max_defect':.08}

def cheap_scan(n,clauses):
    """One linear scan; NO graph traversal, XOR hashing, sorting or SAT calls."""
    start=time.perf_counter()
    pos=[0]*n;neg=[0]*n;count=0;unit=0
    for c in clauses:
        unit+=(len(c)<=1)
        for lit in c:
            if lit>0:pos[lit-1]+=1
            else:neg[-lit-1]+=1
            count+=1
    return Cheap(sum(min(a,b) for a,b in zip(pos,neg))/max(1,count),
                 unit/max(1,len(clauses)),(time.perf_counter()-start)*1000)

def eligible(n,cheap,model):
    return (model.get('enabled',False)
            and n>=model['min_n']
            and cheap.minority<=model['max_minority']
            and cheap.unit_share<=model['max_unit_share'])

def run(n,clauses,variant,model=None,budget=2.5,probe_cap_ms=22):
    """wall clock in-process includes cheap/full feature computation and solve."""
    begin=time.perf_counter()
    if variant=='base':
        r=baseline_solve(n,clauses,budget=budget)
        return Result(r.status,r.assignment,(time.perf_counter()-begin)*1000,0,0,0,'base')
    if variant not in ('two-stage','force-gates'):
        raise ValueError(variant)
    config=model if model is not None else DEFAULT
    # Globally disabled controller must not compute ANY feature.
    if variant=='two-stage' and not config.get('enabled',False):
        r=baseline_solve(n,clauses,budget=budget)
        return Result(r.status,r.assignment,(time.perf_counter()-begin)*1000,0,0,0,'disabled-zero-overhead')
    q=cheap_scan(n,clauses)
    if variant=='two-stage' and not eligible(n,q,config):
        r=baseline_solve(n,clauses,budget=max(.0001,budget-(time.perf_counter()-begin)))
        return Result(r.status,r.assignment,(time.perf_counter()-begin)*1000,q.ms,0,0,'cheap-gate-skip')
    full_start=time.perf_counter()
    fs=signature(n,clauses)
    full_ms=(time.perf_counter()-full_start)*1000
    if (variant=='two-stage' and fs.numbers['horn_defect']>config['max_defect']):
        r=baseline_solve(n,clauses,budget=max(.0001,budget-(time.perf_counter()-begin)))
        return Result(r.status,r.assignment,(time.perf_counter()-begin)*1000,q.ms,full_ms,0,'full-gate-skip')
    t=time.perf_counter()
    if fs.defect_count==0:
        transformed=[tuple(-lit if fs.majority_flips[abs(lit)-1] else lit for lit in clause)
                     for clause in clauses]
        assert all(sum(lit>0 for lit in c)<=1 for c in transformed)
        status,model_assign=solve_horn(n,transformed)
        if model_assign is not None:
            model_assign=[bool(x)^bool(f) for x,f in zip(model_assign,fs.majority_flips)]
        tag='direct-majority-Horn'
    else:
        stop=min(t+probe_cap_ms/1000,begin+budget)
        candidate,reason,_=renamable_horn(n,clauses,probe_deadline=stop)
        if candidate is not None:
            flips,transformed=candidate
            status,model_assign=solve_horn(n,transformed)
            if model_assign is not None:
                model_assign=[bool(x)^bool(f) for x,f in zip(model_assign,flips)]
            tag='recognized-Horn'
        else:
            status=None;model_assign=None;tag='failed-'+reason
    probe_ms=(time.perf_counter()-t)*1000
    if status is None:
        r=baseline_solve(n,clauses,budget=max(.0001,budget-(time.perf_counter()-begin)))
        status,model_assign=r.status,r.assignment
        tag+='->base'
    if status=='SAT':
        assert model_assign is not None and check(clauses,model_assign),tag
    return Result(status,model_assign,(time.perf_counter()-begin)*1000,
                  q.ms,full_ms,probe_ms,tag)

def choose_model(data):
    """Training-only empirical utility selection of the BOTH gate thresholds.

    Uses matched per-instance timings including cheap/full feature costs.
    Conservative 1/3 penalty on training optimism; chooses OFF if no gain.
    No holdout data is accessed.
    """
    candidates=[]
    for min_n in (45,75,90):
        for minority in (.22,.26,.30,.34):
            for unit in (0.,.035):
                for defect in (.03,.07,.12,.18):
                    gains=[];used=0;attempted=0
                    for r in data:
                        stage1=(r['n']>=min_n and r['minority']<=minority
                                and r['unit_share']<=unit)
                        if stage1:
                            used+=1
                            stage2=(r['defect']<=defect)
                            if stage2:
                                attempted+=1
                                gain=r['baseline_ms']-r['probe_ms']-r['cheap_ms']-r['full_ms']
                            else:
                                gain=-r['cheap_ms']-r['full_ms']
                        else:
                            gain=-r['cheap_ms']
                        gains.append(max(-30.,min(30.,gain)))
                    average=statistics.mean(gains)
                    # Restrict degenerate single-case fits; explicit cost margin.
                    score=average-.05-(.08 if attempted<3 else 0)
                    candidates.append((score,average,used,attempted,min_n,minority,unit,defect))
    best=max(candidates)
    score,mean,used,attempted,min_n,minority,unit,defect=best
    enabled=score>.08 and attempted>=3
    return dict(version='v0.6.1',frozen=True,enabled=enabled,
                min_n=min_n,max_minority=minority,max_unit_share=unit,
                max_defect=defect,train_mean_gain_ms=round(mean,4),
                train_utility_ms=round(score,4),train_gate_hits=used,
                train_probe_attempts=attempted,train_records=len(data),
                selection='training-only grid; heldout untouched',
                cost='cheap + full + exact probe included')
