#!/usr/bin/env python3
"""DRNAS NeuroFlow v0.6: exact SAT strategy selection from cheap structural features.

The policy predicts *net* benefit using TRAIN-ONLY paired measurements. The
underlying SAT algorithms remain exact and independently validate SAT models.
No neural network or private GPU NeuroFlow driver code is used.
"""
from __future__ import annotations
import math, statistics, time
from dataclasses import dataclass
from collections import defaultdict,Counter
from drnas_np_lab import check, normalize, solve as solve_original
from nf_v05_structural import solve_strategy as previous_strategy

FEATURE_NAMES=(
    'log_variables','clauses_per_variable','mean_clause_len','unit_share',
    'binary_share','ternary_share','long_clause_share','pos_literal_share',
    'horn_defect','minority_sign_share','mean_sign_imbalance','pure_var_share',
    'degree_cv','top_degree_share','components_per_variable','largest_component_share',
    'xor_quartet_density'
)
# Strong weights for signs and Horn cost, weaker weights for problem scale.
FEATURE_WEIGHTS=(0.75,0.85,0.6,1.3,0.55,0.45,0.45,0.65,
                 3.2,1.2,1.35,1.1,0.9,0.8,0.65,0.65,1.0)

@dataclass
class Signature:
    vector:tuple[float,...]
    numbers:dict
    majority_flips:list[bool]
    defect_count:int
    ms:float

@dataclass
class SolveResult:
    status:str
    method:str
    ms:float
    feature_ms:float
    probe_ms:float
    assignment:list|None
    confidence:float=0.0
    predicted_gain_ms:float=0.0


def signature(n, clauses):
    """All O(sum clause lengths) or O(n log n); never invokes SAT solver.

    Graph 'components' computed from the primal-graph union-find (not treewidth).
    XOR quartet signature is an indicator, not an unverified replacement rule.
    """
    started=time.perf_counter(); m=len(clauses)
    pos=[0]*n; neg=[0]*n; degree=[0]*n
    length_hist=[0,0,0,0]; total_len=0; positive_count=0
    parent=list(range(n)); count=n
    xor_masks=defaultdict(set)
    def root(v):
        while parent[v]!=v:
            parent[v]=parent[parent[v]];v=parent[v]
        return v
    for clause in clauses:
        k=len(clause);total_len+=k
        length_hist[0 if k<=1 else 1 if k==2 else 2 if k==3 else 3]+=1
        variables=[]
        for lit in clause:
            v=abs(lit)-1
            if v>=n:raise ValueError('DIMACS variable exceeds n')
            degree[v]+=1;variables.append(v)
            if lit>0:pos[v]+=1;positive_count+=1
            else:neg[v]+=1
        if variables:
            p0=root(variables[0])
            for v in variables[1:]:
                r=root(v)
                if r!=p0:parent[r]=p0;count-=1
        if k==3 and len(set(variables))==3:
            vs=tuple(sorted(v+1 for v in variables))
            mask=sum(1<<j for j,var in enumerate(vs) if -var in clause)
            xor_masks[vs].add(mask)
    flips=[p>q for p,q in zip(pos,neg)]
    violation=sum(sum((lit>0)^flips[abs(lit)-1] for lit in clause)>1 for clause in clauses)
    used=[p+q for p,q in zip(pos,neg) if p+q]
    mean_degree=total_len/max(n,1)
    cv=(math.sqrt(sum((d-mean_degree)**2 for d in degree)/max(1,n))/max(mean_degree,1e-12))
    top_count=max(1,n//10)
    top_share=sum(sorted(degree,reverse=True)[:top_count])/max(1,total_len)
    pure=sum((p==0 or q==0) and (p+q>0) for p,q in zip(pos,neg))/max(1,n)
    sign_minority=sum(min(p,q) for p,q in zip(pos,neg))/max(1,total_len)
    imbalance=sum(abs(p-q)/max(1,p+q) for p,q in zip(pos,neg))/max(1,n)
    components=Counter(root(i) for i in range(n))
    giant=max(components.values(),default=0)/max(1,n)
    xor_detectable=0
    for masks in xor_masks.values():
        for parity in (0,1):
            if all(mask in masks for mask in range(8) if mask.bit_count()%2==parity):
                xor_detectable+=1
    stats={
        'log_variables':math.log1p(n),
        'clauses_per_variable':m/max(n,1),
        'mean_clause_len':total_len/max(m,1),
        'unit_share':length_hist[0]/max(m,1),
        'binary_share':length_hist[1]/max(m,1),
        'ternary_share':length_hist[2]/max(m,1),
        'long_clause_share':length_hist[3]/max(m,1),
        'pos_literal_share':positive_count/max(total_len,1),
        'horn_defect':violation/max(m,1),
        'minority_sign_share':sign_minority,
        'mean_sign_imbalance':imbalance,
        'pure_var_share':pure,
        'degree_cv':cv,
        'top_degree_share':top_share,
        'components_per_variable':count/max(n,1),
        'largest_component_share':giant,
        'xor_quartet_density':xor_detectable/max(1,m)
    }
    return Signature(tuple(stats[k] for k in FEATURE_NAMES),stats,flips,violation,
                     (time.perf_counter()-started)*1000)


def run(n, clauses, variant, model=None, budget=2.0, probe_cap_ms=22):
    """Measure total strategy time including signature, prediction and fallback."""
    t0=time.perf_counter(); feature_ms=0.; predicted_gain=0.;conf=0.
    if variant=='base':
        r=solve_original(n,clauses,budget=budget)
        return SolveResult(r.status,r.method,(time.perf_counter()-t0)*1000,0,0,r.assignment)
    if variant=='always':
        r=previous_strategy(n,clauses,variant='always',budget=budget,cap_ms=probe_cap_ms)
        return SolveResult(r.status,r.path,(time.perf_counter()-t0)*1000,0,r.probe_ms,r.model)
    if variant=='v05':
        threshold=0.06 if n>=90 else -1.0  # Previously published frozen v0.5 rule.
        r=previous_strategy(n,clauses,variant='learned',threshold=threshold,budget=budget,cap_ms=probe_cap_ms)
        return SolveResult(r.status,r.path,(time.perf_counter()-t0)*1000,r.feature_ms,r.probe_ms,r.model)
    if variant!='learned' or model is None:raise ValueError('learned requires frozen model')
    fs=signature(n,clauses);feature_ms=fs.ms
    d=decide(model,fs.vector)
    predicted_gain=d['expected_ms']; conf=d['confidence']
    # Choice affects only where *sound* independent solver runs.
    if d['probe']:
        # Exact renamable-Horn 2-SAT probe; if unsuccessful, original exact solver.
        rem=max(.0001,budget-(time.perf_counter()-t0))
        r=previous_strategy(n,clauses,variant='always',budget=rem,cap_ms=probe_cap_ms)
    else:
        rem=max(.0001,budget-(time.perf_counter()-t0))
        r=previous_strategy(n,clauses,variant='base',budget=rem,cap_ms=probe_cap_ms)
    total=(time.perf_counter()-t0)*1000
    if r.status=='SAT':assert r.model is not None and check(clauses,r.model)
    return SolveResult(r.status,'learned:' + r.path if d['probe'] else 'learned:skip',
                       total,feature_ms,r.probe_ms,r.model,conf,predicted_gain)


def _distance(a,b,scale):
    return sum(w*((x-y)/s)**2 for x,y,s,w in zip(a,b,scale,FEATURE_WEIGHTS))


def build_model(records, min_train=40):
    """Fit TRAIN ONLY 1NN-like conservative contextual expected-gain estimator.

    One train record per formula, paired baseline and forced-probe timings.
    Output is JSON data with frozen rows, scales and selected parameters.
    """
    assert len(records)>=min_train
    raw=[list(r['vector']) for r in records]
    mu=[statistics.mean(v[j] for v in raw) for j in range(len(FEATURE_NAMES))]
    sd=[max(.05,statistics.pstdev(v[j] for v in raw)) for j in range(len(FEATURE_NAMES))]
    # Target already includes the cost of extracting the features + forced probe.
    targets=[max(-60,min(60,float(r['gain_ms']))) for r in records]
    model={'version':'0.6','frozen':True,'names':FEATURE_NAMES,'scale':sd,
           'train_rows':[{'vec':v,'gain_ms':g} for v,g in zip(raw,targets)],
           'selection':{},'method':'weighted kNN mean & hit-rate; conservative train-only CV'}
    # Tune k and decision margin exclusively with leave-one-out TRAIN predictions.
    parameters=[]
    for k in (9,15,23,35):
        for margin in (.25,.6,1.2):
            for min_hit in (.6,.7):
                saved=0.; decisions=0
                for i,r in enumerate(records):
                    d=decide(model,r['vector'],params={'k':k,'margin_ms':margin,'min_hit_rate':min_hit},excluded=i)
                    if d['probe']:
                        decisions+=1
                        saved+=max(-60,min(60,targets[i]))
                    else:
                        saved-=max(0,float(r['feature_ms']))
                # Penalize complexity and low evidence; keep conservative no-probe option.
                score=saved/len(records)-.01*decisions/max(1,len(records))
                parameters.append((score,-decisions,k,margin,min_hit))
    best=max(parameters)
    model['selection']={'k':best[2],'margin_ms':best[3],'min_hit_rate':best[4],
                       'train_crossval_avg_gain_ms':round(best[0],4),
                       'train_cv_selected':-best[1]}
    # No-probe is always an admissible choice.
    if best[0] <= 0:
        model['selection']['disabled']=True
    return model


def decide(model,vec,params=None,excluded=None):
    p=params if params is not None else model['selection']
    if p.get('disabled'):
        return dict(probe=False,expected_ms=0.,confidence=0.)
    candidates=sorted((( _distance(vec,x['vec'],model['scale']),i,x['gain_ms'])
                       for i,x in enumerate(model['train_rows']) if i!=excluded),key=lambda x:x[0])
    k=min(int(p['k']),len(candidates)); near=candidates[:k]
    if not near:return dict(probe=False,expected_ms=0.,confidence=0.)
    # Distances weight local neighbours, but do not let one outlier dominate.
    weights=[1/(.5+math.sqrt(max(0,d))) for d,i,g in near]
    sw=sum(weights)
    expected=sum(g*w for (_,i,g),w in zip(near,weights))/sw
    hit=sum(w for (_,i,g),w in zip(near,weights) if g>0)/sw
    uncertainty=math.sqrt(sum(w*(g-expected)**2 for (_,i,g),w in zip(near,weights))/sw)
    # Learned from data; no SAT outcome used at inference.
    yes=(expected>p['margin_ms'] and hit>=p['min_hit_rate'] and
         expected>.20*uncertainty)
    return dict(probe=bool(yes),expected_ms=round(expected,4),confidence=round(hit,4))