#!/usr/bin/env python3
"""DRNAS NP Lab v0.6.2 — fast, targeted renamable-Horn policy.

This is an exact solver-selector, not a new SAT proof system.
All acceptance is backed by sound 2SAT Horn-renaming and model verification.
"""
import statistics,time
from dataclasses import dataclass
from drnas_np_lab import solve as base_solve,solve_horn,check
from neuroflow_v03 import renamable_horn

@dataclass
class Result:
    status:str
    model:list|None
    ms:float
    route:str
    first_ms:float=0.
    defect_ms:float=0.
    exact_ms:float=0.
    minority:float=0.
    unit_share:float=0.
    defect:float=0.

DEFAULT={'enabled':False,'min_n':30,'minority_min':.18,'minority_max':.33,
         'unit_max':0.0,'defect_max':.10,'pair_budget_ms':12.0}

def first_pass(n,clauses):
    start=time.perf_counter()
    pos=[0]*n;neg=[0]*n;literal_count=0;units=0
    for c in clauses:
        units+=(len(c)==1)
        for lit in c:
            idx=abs(lit)-1
            if idx<0 or idx>=n:raise ValueError('Invalid literal')
            if lit>0:pos[idx]+=1
            else:neg[idx]+=1
            literal_count+=1
    minority=sum(min(a,b) for a,b in zip(pos,neg))/max(1,literal_count)
    return (minority,units/max(1,len(clauses)),
            [a>b for a,b in zip(pos,neg)],
            (time.perf_counter()-start)*1000)

def defect_pass(clauses,flips):
    t=time.perf_counter()
    bad=0
    for c in clauses:
        positives=0
        for lit in c:
            if (lit>0)^flips[abs(lit)-1]:
                positives+=1
                if positives>=2:
                    bad+=1
                    break
    return bad/max(1,len(clauses)),bad,(time.perf_counter()-t)*1000

def run(n,clauses,variant='adaptive',policy=None,budget=2.5):
    if variant not in ('adaptive','force','base'):raise ValueError(variant)
    policy=DEFAULT if policy is None else policy
    t0=time.perf_counter()
    def finish_base(route,first_ms=0,defect_ms=0,exact_ms=0,minority=0,unit=0,defect=0):
        remain=max(.0001,budget-(time.perf_counter()-t0))
        r=base_solve(n,clauses,budget=remain)
        if r.status=='SAT':assert r.assignment is not None and check(clauses,r.assignment)
        return Result(r.status,r.assignment,(time.perf_counter()-t0)*1000,route,first_ms,
                      defect_ms,exact_ms,minority,unit,defect)
    # Actual zero-overhead disabled path (including before minimum-size check).
    if variant=='base' or (variant=='adaptive' and not policy['enabled']):
        return finish_base('base' if variant=='base' else 'disabled-no-features')
    if variant=='adaptive' and n<policy['min_n']:
        return finish_base('skip-size')
    minority,unit,flips,first_ms=first_pass(n,clauses)
    if variant=='adaptive' and not (policy['minority_min']<=minority<=policy['minority_max']
                                   and unit<=policy['unit_max']):
        return finish_base('skip-first',first_ms,minority=minority,unit=unit)
    defect,bad,defect_ms=defect_pass(clauses,flips)
    if variant=='adaptive' and defect>policy['defect_max']:
        return finish_base('skip-defect',first_ms,defect_ms,minority=minority,unit=unit,defect=defect)
    exact_start=time.perf_counter()
    if bad==0:
        transformed=[tuple(-l if flips[abs(l)-1] else l for l in c) for c in clauses]
        assert all(sum(l>0 for l in c)<=1 for c in transformed)
        status,model=solve_horn(n,transformed)
        route='direct-Horn'
    else:
        limit=max(.0001,min(float(policy.get('pair_budget_ms',12.0))/1000,
                       budget-(time.perf_counter()-t0)))
        candidate,reason,_=renamable_horn(n,clauses,probe_deadline=time.perf_counter()+limit)
        if candidate is None:
            exact_ms=(time.perf_counter()-exact_start)*1000
            return finish_base('unrecognized-'+reason,first_ms,defect_ms,exact_ms,minority,unit,defect)
        found_flips,transformed=candidate
        status,model=solve_horn(n,transformed)
        flips=found_flips
        route='exact-renamable-Horn'
    if model is not None:
        model=[bool(v)^bool(f) for v,f in zip(model,flips)]
    if status=='SAT':assert model is not None and check(clauses,model)
    return Result(status,model,(time.perf_counter()-t0)*1000,route,
                  first_ms,defect_ms,(time.perf_counter()-exact_start)*1000,minority,unit,defect)

def fit(records):
    """Training-only constrained grid; calculates total real net benefit of each gate.

    The force path measures exact probe. For rejections, account for the
    first/defect scan overhead and the baseline time; no status label used.
    """
    options=[]
    for min_n in (30,50):
      for lo in (.13,.18,.21):
       for hi in (.28,.33,.36):
        for unit_max in (0.,.02):
         for defect_max in (.06,.10,.14):
          savings=[];probes=0
          for r in records:
            if r['n']<min_n:
                gain=0.
            else:
                gain=-r['first_ms']
                if lo<=r['minority']<=hi and r['unit_share']<=unit_max:
                    gain-=r['defect_ms']
                    if r['defect']<=defect_max:
                        probes+=1
                        # Real forced measured time already includes its two scans.
                        gain=r['base_ms']-r['force_ms']
            savings.append(max(-100.,min(100.,gain)))
          mean=statistics.mean(savings)
          score=mean-.04- (0.10 if probes<6 else 0)
          options.append((score,mean,probes,min_n,lo,hi,unit_max,defect_max))
    best=max(options,key=lambda r:(r[0],-r[2]))
    score,mean,probes,min_n,lo,hi,unit_max,defect_max=best
    return dict(version='v0.6.2',frozen=True,enabled=score>.03 and probes>=6,
          min_n=min_n,minority_min=lo,minority_max=hi,unit_max=unit_max,
          defect_max=defect_max,pair_budget_ms=12.,
          train_expected_gain_ms=round(mean,4),train_score_ms=round(score,4),
          train_selected=probes,train_total=len(records),
          method='cheap 1-pass sign gate then Horn-defect scan then exact renaming',
          no_holdout_updates=True)
