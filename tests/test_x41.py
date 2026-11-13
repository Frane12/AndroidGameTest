#!/usr/bin/env python3
"""X4.1 truth-table oracle; verify trace is observational and schema meaningful."""
import argparse
import itertools
import json
import random
import subprocess
import tempfile
import time
from pathlib import Path

BIN=Path(__file__).resolve().parents[1]/'build'/'drnas-x41'

def oracle(n,clauses):
    return any(all(any((bool(bits[abs(l)-1])==(l>0)) for l in c) for c in clauses)
               for bits in itertools.product((False,True),repeat=n))

def check_model(text,n,cnf):
    literals=[]
    for line in text.splitlines():
        if line.startswith('v '):literals.extend(int(x) for x in line[2:].split() if x!='0')
    if len(literals)!=n or set(abs(v) for v in literals)!=set(range(1,n+1)):return False
    assignment={abs(x):x>0 for x in literals}
    return all(any(assignment[abs(x)]==(x>0) for x in clause) for clause in cnf)

def run(path,mode,trace_path=None):
    cmd=[str(BIN),str(path),'--mode',mode,'--time','3','--stats']
    if trace_path:cmd.extend(['--transitions',str(trace_path)])
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
    record=[json.loads(x[len('X41_STATS '):]) for x in r.stderr.splitlines() if x.startswith('X41_STATS ')]
    if len(record)!=1:raise AssertionError(('stats',mode,r.stderr))
    return r,record[0]

def one(path,n,clauses,stats,trace_path):
    with open(path,'w') as f:
        f.write(f'p cnf {n} {len(clauses)}\n')
        for i,c in enumerate(clauses):
            if len(c)>1 and i%3==0:
                f.write(str(c[0])+'\n'+' '.join(map(str,c[1:]))+' 0\n')
            else:f.write(' '.join(map(str,c))+' 0\n')
    truth=oracle(n,clauses)
    core,core_stats=run(path,'core')
    trace,trace_stats=run(path,'trace',trace_path)
    for mode,cp in [('core',core),('trace',trace)]:
        actual=cp.returncode==10
        if cp.returncode not in (10,20) or actual!=truth or (actual and not check_model(cp.stdout,n,clauses)):
            raise AssertionError(dict(mode=mode,n=n,cnf=clauses,expected=truth,returncode=cp.returncode,stderr=cp.stderr))
    # Instrumentation must have *zero* influence on deterministic solver choices.
    keys=('decisions','conflicts','learnt','propagations','restarts','reduce_removed')
    if any(core_stats[k]!=trace_stats[k] for k in keys):
        raise AssertionError(dict(case=clauses,core={k:core_stats[k] for k in keys},trace={k:trace_stats[k] for k in keys}))
    if core.stdout!=trace.stdout:
        raise AssertionError('observer changed SAT witness or reported result')
    rows=[json.loads(x) for x in Path(trace_path).read_text().splitlines()]
    assert rows[0]['type']=='meta' and rows[0]['observational_only'] is True
    assert rows[0]['version']==2
    assert rows[0]['retained']==trace_stats['trace_samples_retained']
    if core.returncode==10:assert rows[0]['result']=='SAT_INTERNAL_WITNESS_VERIFIED'
    if core.returncode==20:assert rows[0]['result']=='UNSAT_INTERNAL_ONLY'
    transitions=rows[1:]
    assert len(transitions)==trace_stats['trace_samples_retained']
    for step in transitions:
        assert step['type']=='transition'
        a,b=step['before'],step['after']
        assert b['decisions']==a['decisions']
        assert a['level']>=0 and b['level']==a['level']+1
        assert b['assigned']>=a['assigned']+1
        assert b['conflicts']==a['conflicts']
        assert b['learnt']==a['learnt']
        assert b['elapsed_s']>=a['elapsed_s']
        logic=step['logic']; structure=step['structure']; future=step['future']
        assert logic['unit_propagations_under_assumptions']==b['assigned']-a['assigned']-1
        assert logic['conflict_under_assumptions']==step['propagation_conflict']
        assert logic['global_unsat_certificate'] is False
        assert structure['sample_original_clauses']==a['sampled_total']==b['sampled_total']
        assert structure['delta_open_long']==a['sample_unresolved_long']-b['sample_unresolved_long']
        assert structure['delta_satisfied']==b['sample_satisfied']-a['sample_satisfied']
        for z in (a,b):
            counts=z['sample_open_unit']+z['sample_open_binary']+z['sample_unresolved_long']+z['sample_satisfied']+z['sample_falsified']
            assert counts==z['sampled_total']
        assert future['causal_effect_known'] is False
        if core.returncode==10:
            assert step['remaining_finish_wall_s'] is not None
            assert future['label_origin']=='internal_verified_sat'
        else:
            assert step['remaining_finish_wall_s'] is None
        assert step['decision_literal']!=0
    stats['sources']+=1
    stats['checked']+=2
    stats['records']+=len(transitions)
    stats['trace_conflicts']+=trace_stats['trace_conflicts']


def main():
    p=argparse.ArgumentParser();p.add_argument('--cases',type=int,default=2500)
    args=p.parse_args()
    rng=random.Random(624261114)
    stats={'sources':0,'checked':0,'records':0,'trace_conflicts':0,'seed':624261114}
    start=time.monotonic()
    with tempfile.TemporaryDirectory() as td:
        cnf=Path(td)/'f.cnf'; trace=Path(td)/'trace.jsonl'
        for n in range(0,12):
            one(cnf,n,[],stats,trace)
        for n in range(1,12):
            one(cnf,n,[[1,-1]],stats,trace)
            one(cnf,n,[[]],stats,trace)
        for _ in range(args.cases):
            n=rng.randint(0,10)
            clauses=[]
            for _ in range(rng.randrange(0,36)):
                width=rng.randrange(0,7) if n else 0
                clauses.append([rng.choice([-1,1])*rng.randint(1,n) for _ in range(width)])
            one(cnf,n,clauses,stats,trace)
        # Force many search decisions for sampled transitions.
        for n in (3,4):
            m=n-1; clauses=[]
            for pigeon in range(n):clauses.append([pigeon*m+h+1 for h in range(m)])
            for h in range(m):
                for p1 in range(n):
                    for p2 in range(p1+1,n):
                        clauses.append([-(p1*m+h+1),-(p2*m+h+1)])
            one(cnf,n*m,clauses,stats,trace)
    stats['duration_s']=round(time.monotonic()-start,3)
    assert stats['records']>0
    print('X41_DIFFERENTIAL_PASS '+json.dumps(stats,sort_keys=True),flush=True)

if __name__=='__main__':main()