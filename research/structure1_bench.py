#!/usr/bin/env python3
"""Reproducible bounded STRUCTURE-1 fixture and forgery audit; one CPU core."""
import copy
import itertools
import json
import os
import random
import sys
from pathlib import Path
from structure1_prover import prove
from structure1_checker import check

ROOT=Path('results/structure1')
RNG=random.Random(20261116)


def encode(nvars,clauses,name):
    return (f'c {name} generated test, not official SAT Competition\n'
            f'p cnf {nvars} {len(clauses)}\n'
            + ''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode('ascii')


def assignment(n,r,denied=(),missing_mutex=None):
    denied=set(denied)
    lit=lambda j,s:j*r+s+1
    clauses=[tuple(lit(j,s) for s in range(r)) for j in range(n)]
    for j in range(n):
        for a,b in itertools.combinations(range(r),2):
            clauses.append((-lit(j,a),-lit(j,b)))
    for s in range(r):
        for i,j in itertools.combinations(range(n),2):
            if (i,j,s)!=missing_mutex:
                clauses.append((-lit(i,s),-lit(j,s)))
    for j,s in sorted(denied):
        clauses.append((-lit(j,s),))
    return n*r,clauses


def parity(n,blocked_parity):
    clauses=[tuple(range(1,n+1))]
    clauses.extend((-u,-v) for u,v in itertools.combinations(range(1,n+1),2))
    for bits in range(1<<n):
        if bits.bit_count()%2==blocked_parity:
            clauses.append(tuple(-i if bits & (1<<(i-1)) else i for i in range(1,n+1)))
    return n,clauses


def exact_small(n,clauses):
    """Separate complete DPLL oracle; handles only small generated instances."""
    def recurse(formula,env):
        while True:
            new=[];unit=None
            for clause in formula:
                if any((abs(l) in env and env[abs(l)]==(l>0)) for l in clause):
                    continue
                rest=[l for l in clause if abs(l) not in env]
                if not rest:
                    return False
                if len(rest)==1:
                    unit=rest[0];break
                new.append(tuple(rest))
            if unit is None:
                formula=new;break
            v=abs(unit);state=(unit>0)
            if v in env and env[v]!=state:
                return False
            env=env|{v:state}
        if not formula:
            return True
        var=abs(min(formula,key=len)[0])
        return recurse(formula,env|{var:True}) or recurse(formula,env|{var:False})
    return 'SAT' if recurse(clauses,{}) else 'UNSAT'


def trial(name,spec,expected,method=None):
    n,cs=spec
    raw=encode(n,cs,name)
    cert=prove(raw)
    (ROOT/(name+'.cnf')).write_bytes(raw)
    (ROOT/(name+'.certificate.json')).write_text(json.dumps(cert,sort_keys=True,indent=2)+'\n')
    claimed=cert['status']=='UNSAT_UNCHECKED'
    if expected=='UNSAT' and not claimed:
        raise AssertionError(name+' expected UNSAT missing')
    if expected=='UNKNOWN' and claimed:
        raise AssertionError(name+' false UNSAT')
    if method and claimed and cert['method']!=method:
        raise AssertionError(name+' incorrect source method')
    verified=None
    if claimed:
        verified=check(raw,cert)
        if not verified['status'].endswith('VERIFIED'):
            raise AssertionError('independent verifier rejected claim')
    verdict=exact_small(n,cs)
    if expected=='UNSAT' and verdict!='UNSAT':
        raise AssertionError(name+' exact DPLL finds SAT!')
    if expected=='UNKNOWN' and verdict!='SAT':
        raise AssertionError(name+' SAT control wrongly UNSAT')
    return {'name':name,'claim':cert['status'],'method':cert['method'],
            'independent':verified['status'] if verified else 'NO_CLAIM','oracle':verdict}


def run():
    ROOT.mkdir(parents=True,exist_ok=True)
    rows=[]
    denied={(j,s) for j in range(3) for s in (2,3)}
    rows.append(trial('match_hall_subset_unsat',assignment(4,4,denied),'UNSAT','MATCH-1'))
    rows.append(trial('match_pigeonhole_unsat',assignment(5,4),'UNSAT','MATCH-1'))
    rows.append(trial('match_sat_exact_assignment',
                      assignment(3,4,{(j,s) for j in range(3) for s in range(4) if s!=j}),'UNKNOWN'))
    rows.append(trial('match_missing_mutex',assignment(3,3,missing_mutex=(0,1,0)),'UNKNOWN'))
    rows.append(trial('match_repaired_hall',assignment(4,4,denied-{(0,2)}),'UNKNOWN'))
    for i in range(5):
        n,cs=assignment(4,4,denied)
        mapping=list(range(1,n+1));RNG.shuffle(mapping)
        remapped=[tuple((1 if x>0 else -1)*mapping[abs(x)-1] for x in c) for c in cs]
        RNG.shuffle(remapped)
        rows.append(trial(f'match_relabel_{i}',(n,remapped),'UNSAT','MATCH-1'))
    for k in (3,4,5):
        rows.append(trial(f'parity_even_xor_unsat_k{k}',parity(k,1),'UNSAT','INTEGER-PARITY-1'))
        rows.append(trial(f'parity_odd_xor_sat_k{k}',parity(k,0),'UNKNOWN'))
    n,cs=parity(4,1)
    cs=[c for c in cs if c!=(-1,2,3,4)]
    rows.append(trial('parity_missing_odd_clause',(n,cs),'UNKNOWN'))
    n,cs=parity(4,1)
    for i in range(5):
        ids=list(range(1,n+1));RNG.shuffle(ids)
        perm=[tuple((1 if x>0 else -1)*ids[abs(x)-1] for x in cl) for cl in cs]
        RNG.shuffle(perm)
        rows.append(trial(f'parity_relabel_{i}',(n,perm),'UNSAT','INTEGER-PARITY-1'))
    tamper_rejected=0
    for name in ('match_hall_subset_unsat','parity_even_xor_unsat_k4'):
        raw=(ROOT/(name+'.cnf')).read_bytes()
        cert=json.loads((ROOT/(name+'.certificate.json')).read_text())
        changes=[dict(cert,source_sha256='0'*64),dict(cert,status='UNKNOWN')]
        bad=copy.deepcopy(cert)
        if cert['method']=='MATCH-1':
            bad['hall_neighbors']=[0,1,2,3]
        else:
            bad['blocked_odd_patterns']=0
        changes.append(bad)
        for forged in changes:
            try:
                check(raw,forged)
            except (ValueError,TypeError,KeyError,IndexError):
                tamper_rejected+=1
            else:
                raise AssertionError(name+' accepted forged certificate')
        try:
            check(raw+b'c changed source\n',cert)
        except ValueError:
            tamper_rejected+=1
        else:
            raise AssertionError(name+' accepted changed source')
    s={'status':'PASS','cases':len(rows),
       'unsat_certified':sum(r['claim']=='UNSAT_UNCHECKED' for r in rows),
       'sat_controls':sum(r['oracle']=='SAT' for r in rows),
       'independent_oracle_checked':len(rows),
       'forged_certificates_rejected':tamper_rejected,
       'known_limitations':['matching positional slots only',
            'parity complete explicit odd blockers only',
            'no mixed cross-module conflict derivation','no C++ integration',
            'no DRAT/LRAT/VeriPB source certificate']}
    (ROOT/'summary.json').write_text(json.dumps(s,sort_keys=True,indent=2)+'\n')
    (ROOT/'trials.json').write_text(json.dumps(rows,sort_keys=True,indent=2)+'\n')
    print('STRUCTURE1_FINAL '+json.dumps(s,sort_keys=True))
    return 0


if __name__=='__main__':
    if hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    sys.exit(run())
