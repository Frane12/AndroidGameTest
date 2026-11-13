#!/usr/bin/env python3
"""X4.8 exhaustive correctness, X4.7 CORE equivalence, gating and inference parity."""
import argparse
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
import drnas_x47 as X
from x48_models import NF, predict, choose, write_model

X.DECISION=16
X.WORK_LIMIT=100000


def oracle(n, clauses):
    return any(all(any(bool(bits[abs(l)-1]) == (l>0) for l in c) for c in clauses)
               for bits in itertools.product((0,1), repeat=n))


def call(binary, cnf, policy, model=None, decision=16):
    cmd=[str(binary),str(cnf),'--mode','core','--time','2',
         '--branch-at',str(decision),'--stats','--policy',policy]
    if model is not None:cmd+=['--model',str(model)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
    data={}
    for line in p.stderr.splitlines():
        if line.startswith(('X41_STATS ','X45_COMPARE ','X47_POLICY ')):
            k,v=line.split(' ',1)
            data[k]=json.loads(v)
    return p,data


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cases',type=int,default=100)
    args=ap.parse_args()
    x47=ROOT/'build/drnas-x47'
    x48=ROOT/'build/drnas-x48'
    rng=random.Random(480213)
    checked=0
    reached=0
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        cnf=td/'source.cnf'
        model=td/'frozen.txt'
        mock={'centers':[0.]*NF,'scales':[100.]*NF,
              'weights':[[0.]*NF+[1.]]*2,'threshold':.5,
              'ood_limit':8.,'kind':'ridge','bias':0.,
              'min_conflicts':100000}
        write_model(model,mock)
        cases=[(0,[]),(0,[[]]),(1,[[1],[-1]]),
               (3,[[1,2],[-1,3],[-2,-3]])]
        for _ in range(args.cases):
            n=rng.randrange(1,9)
            clauses=[[rng.choice((-1,1))*v for v in rng.sample(range(1,n+1),
                      rng.randrange(1,min(4,n)+1))]
                     for _ in range(rng.randrange(1,6*n+1))]
            cases.append((n,clauses))
        for n,clauses in cases:
            cnf.write_text(f'p cnf {n} {len(clauses)}\n'+
                           ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
            truth=oracle(n,clauses)
            old,a=call(x47,cnf,'core')
            core,b=call(x48,cnf,'core')
            skip,c=call(x48,cnf,'gated',model)
            expected=10 if truth else 20
            assert old.returncode==core.returncode==skip.returncode==expected, (clauses,old.stderr,core.stderr,skip.stderr)
            if truth:
                assert X.witness_ok(core.stdout,{'n':n,'clauses':clauses})
                assert X.witness_ok(skip.stdout,{'n':n,'clauses':clauses})
            for k in ('decisions','conflicts','propagations','learnt','restarts'):
                assert a['X41_STATS'][k]==b['X41_STATS'][k]==c['X41_STATS'][k]
            assert core.stdout==old.stdout==skip.stdout
            checked+=3
        for family in X.TRAIN+X.VALIDATION+X.HOLDOUT:
            for i in range(8):
                case=X.make_case(family,i,'x48-exhaustive-sample')
                cnf.write_text(case['source'])
                old,a=call(x47,cnf,'core')
                core,b=call(x48,cnf,'core')
                skip,c=call(x48,cnf,'gated',model)
                assert old.returncode==core.returncode==skip.returncode==10
                assert X.witness_ok(core.stdout,case)
                for k in ('decisions','conflicts','propagations','learnt','restarts'):
                    assert a['X41_STATS'][k]==b['X41_STATS'][k]==c['X41_STATS'][k]
                assert old.stdout==core.stdout==skip.stdout
                policy=c['X47_POLICY']
                if c['X45_COMPARE']['reached']:
                    reached+=1
                    assert policy['gate_skipped'] and policy['probe_inspections']==0
                    assert not policy['flipped'] and policy['features']==[]
                checked+=3
        # Enabling a confident gate must match the Python frozen predictor.
        mock['min_conflicts']=0
        write_model(model,mock)
        for family in ('uniform3','dense3','grid_xor','community_bridge','color4'):
            for i in range(8):
                case=X.make_case(family,i,'x48-inference-test')
                cnf.write_text(case['source'])
                result=X.run(x48,cnf,case,'gated',2,model=model)
                assert result['verified']
                p=result['policy']
                if result['reached']:
                    assert not p['gate_skipped'] and len(p['features'])==NF
                    score,_=predict(mock,p['features'])
                    assert abs(score-p['score'])<1e-8
                    assert p['flipped']==choose(mock,p['features'])
                checked+=1
        # Invalid model must refuse to run, not silently choose a branch.
        for bad in ('garbage','X471 24 2 0 8 ridge 0',
                    'X481 30 2 nan 8 ridge 0 0','X481 30 2 0 8 ridge 0 -2'):
            model.write_text(bad)
            p=subprocess.run([str(x48),str(cnf),'--mode','core','--branch-at','16',
                 '--policy','gated','--model',str(model)],capture_output=True,text=True)
            assert p.returncode==1
            checked+=1
        assert reached>=5, ('checkpoint rarely reached',reached)
    print('X48_TEST_PASS '+json.dumps({'independent_exhaustive_sources':len(cases),
          'native_runs':checked,'checkpoint_reached':reached,
          'core_unchanged':True,'fail_closed_gate':True}))


if __name__=='__main__':
    main()
