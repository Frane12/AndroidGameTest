#!/usr/bin/env python3
"""DRNAS NP v0.7.1: bounded prefix screening before unchanged v0.7 CaDiCaL.

This is a conservative *heuristic routing filter*, not a SAT proof. An early
reject always gives the ORIGINAL file to the same exact CaDiCaL backend.
An early accept still undergoes the proven v0.7 full Horn analysis; no false
SAT/UNSAT conclusions can be introduced by the prefix classifier.
"""
from __future__ import annotations
import time
from dataclasses import dataclass,replace
from pathlib import Path
from nf_v07_cadical_adapter import solve as v07_solve,FROZEN_V062,Outcome

# Frozen before evaluating existing external corpus. No test-time training.
PREFIX_BYTES=32768
PREFIX_CLAUSES=160
MIN_COMPLETE_CLAUSES=48
MIN_LITERALS=128
# v0.6.2's globally trained minority limit is .28; prefix is noisier,
# so early rejection uses a deliberately wider high-confidence margin.
MAX_SAMPLE_MINORITY=.335

@dataclass
class PrefixResult:
    decision:str
    ms:float
    clauses:int
    minority:float|None
    unit_found:bool
    coverage:float
    reason:str

def sample_prefix(path,n,cap_bytes=PREFIX_BYTES,max_clauses=PREFIX_CLAUSES):
    """Bounded byte read. Only a complete terminated DIMACS clause is counted.

    We do not infer an answer or rewrite formula. When syntax looks unusual,
    fail OPEN to full v0.7 exact preprocessing, not a false negative claim.
    """
    start=time.perf_counter()
    raw=Path(path).open('rb')
    with raw as stream:
        fragment=stream.read(cap_bytes+1)
    clipped=len(fragment)>cap_bytes
    if clipped:fragment=fragment[:cap_bytes]
    if clipped and b'\n' in fragment:
        fragment=fragment[:fragment.rfind(b'\n')+1]
    try:
        decoded=fragment.decode('ascii')
    except UnicodeDecodeError:
        return PrefixResult('uncertain',(time.perf_counter()-start)*1000,0,None,False,0,'nonascii')
    pos=[0]*n;neg=[0]*n;count=0;units=0;clauses=0
    seen_header=False;term_count=0;broken=False
    for line in decoded.splitlines():
        line=line.strip()
        if not line or line.startswith('c'):continue
        if line.startswith('p '):
            header=line.split()
            if len(header)<4 or header[1]!='cnf' or int(header[2])!=n:
                broken=True;break
            seen_header=True
            continue
        if line.startswith('%'):break
        if not seen_header:broken=True;break
        for word in line.split():
            try:v=int(word)
            except ValueError:
                broken=True;break
            if v==0:
                clauses+=1
                units+=(term_count==1)
                term_count=0
                if clauses>=max_clauses:break
            else:
                i=abs(v)-1
                if i<0 or i>=n:
                    broken=True;break
                count+=1;term_count+=1
                if v>0:pos[i]+=1
                else:neg[i]+=1
        if broken or clauses>=max_clauses:break
    ms=(time.perf_counter()-start)*1000
    observed=sum(bool(a+b) for a,b in zip(pos,neg))/max(n,1)
    if broken or not seen_header or clauses<MIN_COMPLETE_CLAUSES or count<MIN_LITERALS:
        return PrefixResult('uncertain',ms,clauses,None,bool(units),observed,'insufficient-or-unusual')
    if units:
        return PrefixResult('reject',ms,clauses,None,True,observed,'sampled-unit')
    minority=sum(min(a,b) for a,b in zip(pos,neg))/max(count,1)
    # Avoid conclusions from under-covered massive-variable problems.
    if observed>=.65 and minority>MAX_SAMPLE_MINORITY:
        return PrefixResult('reject',ms,clauses,minority,False,observed,'high-minority')
    return PrefixResult('candidate',ms,clauses,minority,False,observed,'candidate')

def solve(path,mode='base',n_hint=None,budget=1.0,policy=None):
    policy=FROZEN_V062 if policy is None else policy
    if mode not in ('base','v07','prefix','force_horn'):
        raise ValueError(mode)
    if mode=='base':
        return v07_solve(path,'base',n_hint=n_hint,budget=budget,policy=policy)
    if mode=='v07':
        return v07_solve(path,'neuroflow',n_hint=n_hint,budget=budget,policy=policy)
    if mode=='force_horn':
        return v07_solve(path,'force_horn',n_hint=n_hint,budget=budget,policy=policy)
    t=time.perf_counter()
    # Dynamic policy OFF and known tiny formulas have literally no extra read.
    if not policy.get('enabled',False) or (n_hint is not None and n_hint<policy['min_n']):
        r=v07_solve(path,'base',n_hint=n_hint,budget=budget,policy=policy)
        return replace(r,milliseconds=(time.perf_counter()-t)*1000,route='prefix-disabled->cadical')
    # Header-only read if caller did not supply the original variable count.
    n=n_hint
    if n is None:
        with open(path,'rb') as fd:
            for line in fd:
                if line.startswith(b'p '):
                    fields=line.split()
                    n=int(fields[2]);break
        if n is None:
            # Let CaDiCaL be the sole authority on unparseable input.
            r=v07_solve(path,'base',budget=max(.001,budget-(time.perf_counter()-t)),policy=policy)
            return replace(r,milliseconds=(time.perf_counter()-t)*1000,route='prefix-missing-header->cadical')
    if n<policy['min_n']:
        r=v07_solve(path,'base',n_hint=n,budget=max(.001,budget-(time.perf_counter()-t)),policy=policy)
        return replace(r,milliseconds=(time.perf_counter()-t)*1000,route='prefix-size->cadical')
    q=sample_prefix(path,int(n))
    remaining=max(.001,budget-(time.perf_counter()-t))
    if q.decision=='reject':
        r=v07_solve(path,'base',n_hint=int(n),budget=remaining,policy=policy)
        return replace(r,milliseconds=(time.perf_counter()-t)*1000,
            route='prefix-'+q.reason+'->cadical',screen_ms=q.ms)
    r=v07_solve(path,'neuroflow',n_hint=int(n),budget=remaining,policy=policy)
    return replace(r,milliseconds=(time.perf_counter()-t)*1000,
          route='prefix-'+q.decision+'->'+r.route,
          screen_ms=q.ms+r.screen_ms)
