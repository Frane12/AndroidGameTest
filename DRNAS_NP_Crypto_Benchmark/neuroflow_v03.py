#!/usr/bin/env python3
"""DRNAS NP Lab: NeuroFlow-inspired adaptive policy; not neural-net/NPU code.

Bounded representation probes, confidence cooldown, decision debt and safe
fallback. No code from private GPU NeuroFlow repository is copied.
"""
from dataclasses import dataclass
from collections import defaultdict
import json
import time
from drnas_np_lab import normalize, solve_2sat, solve_horn, solve as baseline_solve, check

@dataclass
class PolicyResult:
    status: str
    method: str
    seconds: float
    prep_ms: float
    solver_ms: float
    cache_bucket: str
    probe_status: str
    skipped_reason: str
    assignment: list | None = None
    fallback_used: bool = False
    model_valid: bool = True

def profile(n, clauses):
    m=len(clauses)
    positive=sum(l>0 for c in clauses for l in c)
    literal_count=sum(len(c) for c in clauses)
    signed_bucket=int(4*positive/max(1,literal_count))
    lengths=(sum(len(c)==2 for c in clauses),sum(len(c)==3 for c in clauses),sum(len(c)>3 for c in clauses))
    dom=lengths.index(max(lengths))
    return f"d{int(m/max(n,1)>=3)}-k{dom}-p{signed_bucket}"

def renamable_horn(n, clauses, probe_deadline=None, max_pairs=200000):
    """Exact polynomial 2-SAT recognition of Horn after variable polarity flips.

    To prevent any pair of literals from both becoming positive, impose
    (f_i if original literal positive else NOT f_i) OR
    (f_j if original literal positive else NOT f_j).
    Original signs are exactly 2-SAT literals over flip variables f.
    """
    clauses=normalize(n,clauses)
    count=sum(len(c)*(len(c)-1)//2 for c in clauses)
    if count>max_pairs:return None,'pair_limit',count
    formula=[]
    for i,c in enumerate(clauses):
        if probe_deadline and (i&15)==0 and time.perf_counter()>probe_deadline:
            return None,'probe_deadline',count
        for p in range(len(c)):
            for q in range(p+1,len(c)):
                formula.append((c[p],c[q]))
    if probe_deadline and time.perf_counter()>probe_deadline:
        return None,'probe_deadline',count
    status,flips=solve_2sat(n,formula)
    if status!='SAT':return None,'not_renamable_horn',count
    if probe_deadline and time.perf_counter()>probe_deadline:
        return None,'probe_deadline',count
    transformed=[tuple(-l if flips[abs(l)-1] else l for l in c) for c in clauses]
    if not all(sum(l>0 for l in c)<=1 for c in transformed):
        raise AssertionError('Unsound Horn renaming')
    return (flips,transformed),'recognized',count

class NeuroFlowPolicy:
    """NeuroFlow design principles: low-cost decisions, hysteresis, memory, rollback.

    Memory is per running process. Every accepted result remains mathematically
    exact; policies affect only computational work, never truth values.
    """
    def __init__(self,mode='adaptive',probe_cap_ms=8.0,recheck_every=5):
        assert mode in ('adaptive','shadow','off')
        self.mode=mode
        self.probe_cap_ms=float(probe_cap_ms)
        self.recheck_every=int(recheck_every)
        self.history=defaultdict(lambda:{'attempts':0,'hits':0,'misses':0,'cost_ms':0.0,'debt_ms':0.0,'skips':0,'cooldown':0,'observed_net_ms':0.0,'paired':0,'loss_streak':0})
    def should_probe(self,key):
        h=self.history[key]
        if self.mode=='off':return False,'disabled'
        if self.mode=='shadow':return True,''
        if h['cooldown']>0:
            h['cooldown']-=1;h['skips']+=1
            return False,'cooldown'
        return True,''
    def observe(self,key,reason,ms):
        h=self.history[key]
        h['attempts']+=1;h['cost_ms']+=ms
        if reason=='recognized':
            h['hits']+=1;h['misses']=0
            h['debt_ms']=max(0.0,h['debt_ms']-ms)
        else:
            h['misses']+=1;h['debt_ms']+=ms
            if h['misses']>=2 and self.mode=='adaptive':
                h['cooldown']=max(h['cooldown'],self.recheck_every);h['misses']=0
    def solve(self,n,input_clauses,budget=1.5):
        t0=time.perf_counter()
        clauses=normalize(n,input_clauses)
        deadline=t0+budget if budget else None
        key=profile(n,clauses)
        enabled,reason=self.should_probe(key)
        prep_ms=0.0
        if enabled:
            start=time.perf_counter()
            stop=start+self.probe_cap_ms/1000
            if deadline:stop=min(deadline,stop)
            candidate,reason,pairs=renamable_horn(n,clauses,probe_deadline=stop)
            prep_ms=(time.perf_counter()-start)*1000
            self.observe(key,reason,prep_ms)
            if candidate is not None and self.mode=='adaptive':
                flips,transformed=candidate
                before=time.perf_counter()
                status,model=solve_horn(n,transformed)
                model=[bool(x)^bool(f) for x,f in zip(model,flips)] if status=='SAT' else None
                if status=='SAT' and not check(clauses,model):
                    raise AssertionError('Renamable Horn model validation FAILED')
                return PolicyResult(status,'renamable Horn + 2-SAT flips',time.perf_counter()-t0,
                    prep_ms,(time.perf_counter()-before)*1000,key,'recognized','',model,False,True)
        remaining=max(0.0001,deadline-time.perf_counter()) if deadline else None
        before=time.perf_counter()
        base=baseline_solve(n,clauses,budget=remaining)
        return PolicyResult(base.status,base.method,time.perf_counter()-t0,
            prep_ms,(time.perf_counter()-before)*1000,key,
            reason if enabled else 'skipped',reason if not enabled else '',
            base.assignment,True,base.status!='SAT' or check(clauses,base.assignment))
    def record_paired_gain(self,key,baseline_ms,adaptive_ms):
        """Offline A/B result: true net decision debt. Never compute baseline
        in the critical solving path; only future policy adapts to measurements.
        """
        h=self.history[key]
        gain=baseline_ms-adaptive_ms
        h['paired']+=1
        h['observed_net_ms']+=gain
        if gain<0:
            h['debt_ms']+=-gain
            h['loss_streak']+=1
            if h['loss_streak']>=2 and self.mode=='adaptive':
                h['cooldown']=max(h['cooldown'],self.recheck_every)
                h['loss_streak']=0
        else:
            h['debt_ms']=max(0.0,h['debt_ms']-gain)
            h['loss_streak']=0

    def save(self,path):
        # No instance content or private data, only counters.
        with open(path,'w',encoding='utf-8') as f:
            json.dump({'mode':self.mode,'probe_cap_ms':self.probe_cap_ms,'history':dict(self.history)},f,indent=2)
