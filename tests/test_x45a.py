#!/usr/bin/env python3
"""Independent truth-table, real policy paths, matched-state and parser checks."""
import argparse
import importlib.util
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
import drnas_x45a as X


def oracle(n, clauses):
    return any(all(any(bool(bits[abs(l)-1])==(l>0) for l in c) for c in clauses)
               for bits in itertools.product((0,1),repeat=n))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cases',type=int,default=400);args=ap.parse_args()
    binary=ROOT/'build/drnas-x45a';baseline=ROOT/'build/drnas-x41'
    rng=random.Random(451314);checked=0;matched=0;reached=0
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);cnf=td/'case.cnf';model=td/'model.txt'
        # Force positive score, so LEARNED must have exactly FLIP's search path.
        fake=dict(centers=[0.0]*15,scales=[100.0]*15,weights=[[0.0]*15+[1.0]]*2,
                  threshold=0.0,ood_limit=8.0)
        X.write_model(model,fake)
        cases=[(0,[]),(0,[[]]),(1,[[1],[-1]]),(3,[[1,2],[-1,3],[-2,-3]])]
        for _ in range(args.cases):
            n=rng.randrange(1,10)
            cs=[[rng.choice((-1,1))*v for v in rng.sample(range(1,n+1),rng.randrange(1,min(4,n)+1))]
                for _ in range(rng.randrange(1,7*n+1))]
            cases.append((n,cs))
        for idx,(n,clauses) in enumerate(cases):
            cnf.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
            truth=oracle(n,clauses);results={};at=1 if idx%2 else 4
            for policy in ('core','sham','fixed','flip','learned','collect','collect_flip','original'):
                cmd=[str(baseline if policy=='original' else binary),str(cnf),'--mode','core','--time','2','--stats','--branch-at',str(at)]
                if policy!='original':cmd+=['--policy','collect' if policy=='collect_flip' else policy]
                if policy in ('learned','sham'):cmd+=['--model',str(model)]
                if policy=='collect_flip':cmd+=['--flip-branch']
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
                assert p.returncode==(10 if truth else 20),(policy,clauses,p.stderr)
                if truth:assert X.witness_ok(p.stdout,dict(n=n,clauses=clauses))
                stats=json.loads(next(l[len('X41_STATS '):] for l in p.stderr.splitlines() if l.startswith('X41_STATS ')))
                pre=json.loads(next(l[len('X45_COMPARE '):] for l in p.stderr.splitlines() if l.startswith('X45_COMPARE ')))
                results[policy]=(stats,pre,p.stdout)
                checked+=1
            keys=('decisions','conflicts','propagations','learnt','restarts')
            for a,b in [('core','original'),('core','sham'),('core','collect'),('flip','learned'),('flip','collect_flip')]:
                assert all(results[a][0][k]==results[b][0][k] for k in keys),(a,b,'search changed')
                assert results[a][2]==results[b][2]
            a,b=results['collect'][1],results['collect_flip'][1]
            assert a['reached']==b['reached']
            if a['reached']:
                reached+=1
                assert a['pre_state_digest']==b['pre_state_digest']
                assert a['actual_literal']==-b['actual_literal']
                matched+=1
        # Correctness beyond tiny random CNFs, all planned generated regimes.
        for family in X.TRAIN+X.VALIDATION+X.HOLDOUT:
            for i in range(2):
                c=X.make_case(family,i,'x45a-tests-disjoint');cnf.write_text(c['source'])
                p=X.pair(binary,cnf,c,2)
                assert p['base']['verified'] and p['flip']['verified']
                if p['features'] is not None:assert len(p['features'])==15
                checked+=2
        # Invalid models must fail closed.
        for bad in ('garbage','X45A1 15 2 nan 8','X45A1 14 2 0 8'):
            model.write_text(bad)
            p=subprocess.run([str(binary),str(cnf),'--mode','core','--branch-at','4','--policy','learned','--model',str(model)],capture_output=True,text=True)
            assert p.returncode==1
        # No held-out family can enter any fitting split.
        assert not set(X.TRAIN)&set(X.VALIDATION)
        assert not set(X.TRAIN+X.VALIDATION)&set(X.HOLDOUT)
        assert reached>10
    print('X45A_TEST_PASS',json.dumps(dict(sources=len(cases)+32,solver_runs=checked,matched_interventions=matched,
           independent_exhaustive_sources=len(cases),all_policy_paths_verified=True,original_core_unchanged=True)))


if __name__=='__main__':main()
