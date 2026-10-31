#!/usr/bin/env python3
"""DRNAS NP v0.7: exact NeuroFlow front-end + REAL CaDiCaL CDCL backend.

The reference baseline and adaptive fallback launch precisely the same CaDiCaL
binary with the same original, canonical DIMACS file. Timings include Python
feature extraction, renamable-Horn checking, CDCL process startup and witness
parsing. No generated learning data enters the policy (frozen v0.6.2).
"""
from __future__ import annotations
from dataclasses import dataclass
import subprocess,time
from pathlib import Path
from drnas_np_lab import read_dimacs,check,solve_horn
from neuroflow_v03 import renamable_horn
from nf_v062_hornfast import first_pass,defect_pass

# FROZEN before external data: result of v0.6.2 train-only selection.
FROZEN_V062=dict(enabled=True,min_n=30,minority_min=.13,
    minority_max=.28,unit_max=0.0,defect_max=.10,pair_budget_ms=12.0)

@dataclass
class Outcome:
    status:str
    milliseconds:float
    route:str
    witness_valid:bool|None
    parse_ms:float=0.
    screen_ms:float=0.
    horn_ms:float=0.
    backend_ms:float=0.
    model:list|None=None

def run_cadical(path,n,timeout):
    """Return status + witness and actual backend process wall time.

    CaDiCaL returns process code 10 for SAT, 20 for UNSAT and 0 for UNKNOWN.
    Witness is read from standard 'v' DIMACS model lines. Unassigned vars
    are false when checking against the original CNF.
    """
    t=time.perf_counter()
    try:
        p=subprocess.run(['cadical','--no-colors',str(path)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            timeout=max(0.001,float(timeout)))
    except subprocess.TimeoutExpired:
        return 'TIMEOUT',None,(time.perf_counter()-t)*1000
    ms=(time.perf_counter()-t)*1000
    s=[line.strip() for line in p.stdout.splitlines() if line.startswith('s ')]
    status=None
    if any(x=='s SATISFIABLE' for x in s):status='SAT'
    if any(x=='s UNSATISFIABLE' for x in s):
        if status is not None:return 'ERROR',None,ms
        status='UNSAT'
    if status=='SAT' and p.returncode!=10:return 'ERROR',None,ms
    if status=='UNSAT' and p.returncode!=20:return 'ERROR',None,ms
    if status is None:return ('UNKNOWN' if p.returncode==0 else 'ERROR'),None,ms
    if status=='UNSAT':return status,None,ms
    assignment=[False]*n
    have=False
    for line in p.stdout.splitlines():
        if not line.startswith('v '):continue
        for value in line[2:].split():
            lit=int(value)
            if lit==0:continue
            if abs(lit)>n:return 'ERROR',None,ms
            assignment[abs(lit)-1]=(lit>0);have=True
    if not have:return 'NO_WITNESS',None,ms
    return status,assignment,ms

def solve(path,mode='base',n_hint=None,budget=1.0,policy=None):
    """Modes: base, neuroflow, force_horn. Hard timeout applies to CDCL invocation.

    For base: no Python CNF parse inside timed path.
    For adaptive: exact original file is passed to CaDiCaL on fallback.
    Horn shortcut allowed only after exact equivalence proof (2-SAT or
    directly verified all-Horn polarity transform). SAT models are checked.
    """
    start=time.perf_counter()
    policy=FROZEN_V062 if policy is None else policy
    path=Path(path)
    if mode not in ('base','neuroflow','force_horn'):
        raise ValueError('unknown mode '+str(mode))
    parsed=None
    parse_ms=screen_ms=horn_ms=0.
    def cdcl(route):
        remain=budget-(time.perf_counter()-start)
        if remain<=0:
            return Outcome('TIMEOUT',(time.perf_counter()-start)*1000,
                    route+'-budget',None,parse_ms,screen_ms,horn_ms,0,None)
        # input n_hint may be taken from validated manifest, else parse
        # *outside* back-end timer only when verification is required.
        n = int(n_hint) if n_hint is not None else read_dimacs(path)[0]
        st,model,backend_ms=run_cadical(path,n,remain)
        valid=None
        if st=='SAT':
            original=parsed if parsed is not None else read_dimacs(path)
            valid=check(original[1],model)
            if not valid:raise AssertionError('CaDiCaL witness FAILED '+str(path))
        return Outcome(st,(time.perf_counter()-start)*1000,route,
                       valid,parse_ms,screen_ms,horn_ms,backend_ms,model)
    if mode=='base':return cdcl('cadical-direct')
    # Stage 0: do literally no work for globally disabled policy or small n.
    if mode=='neuroflow' and (not policy['enabled'] or
        (n_hint is not None and int(n_hint)<policy['min_n'])):
        return cdcl('policy-bypass')
    p0=time.perf_counter()
    n,clauses=read_dimacs(path)
    parsed=(n,clauses)
    parse_ms=(time.perf_counter()-p0)*1000
    if mode=='neuroflow' and n<policy['min_n']:return cdcl('size-bypass')
    p1=time.perf_counter()
    minority,unit,flips,_=first_pass(n,clauses)
    screen_ms=(time.perf_counter()-p1)*1000
    if mode=='neuroflow' and not (
        policy['minority_min']<=minority<=policy['minority_max']
        and unit<=policy['unit_max']):
        return cdcl('stage1-skip')
    p2=time.perf_counter()
    defect,bad,_=defect_pass(clauses,flips)
    screen_ms+=(time.perf_counter()-p2)*1000
    if mode=='neuroflow' and defect>policy['defect_max']:
        return cdcl('stage2-skip')
    p3=time.perf_counter()
    if bad==0:
        transformed=[tuple(-lit if flips[abs(lit)-1] else lit for lit in c)
                     for c in clauses]
        assert all(sum(lit>0 for lit in c)<=1 for c in transformed)
        st,model=solve_horn(n,transformed)
        route='direct-Horn'
    else:
        remaining=budget-(time.perf_counter()-start)
        if remaining<=0:return cdcl('probe-skipped-budget')
        cap=min(float(policy.get('pair_budget_ms',12.0))/1000,remaining)
        candidate,reason,_=renamable_horn(n,clauses,
                                          probe_deadline=time.perf_counter()+cap,
                                          max_pairs=200000)
        if candidate is None:
            horn_ms=(time.perf_counter()-p3)*1000
            return cdcl('unrecognized-'+reason)
        other_flips,transformed=candidate
        st,model=solve_horn(n,transformed)
        flips=other_flips
        route='renamable-Horn'
    horn_ms=(time.perf_counter()-p3)*1000
    if model is not None:
        model=[bool(v)^bool(f) for v,f in zip(model,flips)]
    valid=None
    if st=='SAT':
        valid=bool(model is not None and check(clauses,model))
        if not valid:raise AssertionError('Horn witness FAILED')
    return Outcome(st,(time.perf_counter()-start)*1000,route,
                   valid,parse_ms,screen_ms,horn_ms,0,model)
