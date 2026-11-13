#!/usr/bin/env python3
"""X4.10 truth-table SAT/UNSAT, passive cheap policy, and native/model parity."""
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
from x410_models import NF,predict,choose,write_model
from drnas_x410_unsat import pigeonhole
from drnas_x410 import make_case as medium_case


def oracle(n, clauses):
    return any(all(any(bool(bits[abs(l)-1])==(l>0) for l in c) for c in clauses)
               for bits in itertools.product((0,1),repeat=n))


def call(binary,cnf,policy,model=None,decision=16,work_limit=0):
    cmd=[str(binary),str(cnf),'--mode','core','--time','0' if work_limit else '2',
         '--stats','--branch-at',str(decision),'--policy',policy]
    if work_limit:cmd+=['--work-limit',str(work_limit)]
    if model is not None:cmd+=['--model',str(model)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
    data={}
    for l in p.stderr.splitlines():
        if l.startswith(('X41_STATS ','X45_COMPARE ','X47_POLICY ')):
            k,v=l.split(' ',1)
            data[k]=json.loads(v)
    if p.returncode not in (0,10,20):raise AssertionError((p.stderr,p.returncode))
    for tag in ('X41_STATS','X45_COMPARE','X47_POLICY'):
        assert tag in data,(tag,p.stderr)
    return p,data


def stats_equal(a,b):
    return all(a['X41_STATS'][k]==b['X41_STATS'][k]
               for k in ('decisions','conflicts','propagations','learnt','restarts'))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cases',type=int,default=100)
    args=ap.parse_args()
    old=ROOT/'build/drnas-x49'
    new=ROOT/'build/drnas-x410'
    rng=random.Random(4101314)
    checked=0;reached=0
    with tempfile.TemporaryDirectory() as folder:
        folder=Path(folder)
        cnf=folder/'case.cnf'
        model=folder/'model.txt'
        mock={'centers':[0.]*NF,'scales':[100.]*NF,'weights':[[0.]*NF+[1.]]*2,
              'threshold':.5,'ood_limit':8.,'kind':'ridge','bias':0.,
              'min_conflicts':100000,'min_propagations':100000000}
        write_model(model,mock)
        cases=[(0,[]),(0,[[]]),(1,[[1],[-1]]),(3,[[1,2],[-1,3],[-2,-3]])]
        for _ in range(args.cases):
            n=rng.randrange(1,9)
            clauses=[[rng.choice((-1,1))*v
                      for v in rng.sample(range(1,n+1),rng.randrange(1,min(4,n)+1))]
                     for _ in range(rng.randrange(1,6*n+1))]
            cases.append((n,clauses))
        for n,clauses in cases:
            cnf.write_text(f'p cnf {n} {len(clauses)}\n'+
                           ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
            truth=oracle(n,clauses)
            prior,a=call(old,cnf,'core')
            core,b=call(new,cnf,'core')
            no_action,c=call(new,cnf,'cheap_sham',model)
            expected=10 if truth else 20
            assert prior.returncode==core.returncode==no_action.returncode==expected
            if truth:assert X.witness_ok(core.stdout,{'n':n,'clauses':clauses})
            assert stats_equal(a,b) and stats_equal(b,c)
            assert prior.stdout==core.stdout==no_action.stdout
            checked+=3
        for family in X.TRAIN+X.VALIDATION+X.HOLDOUT:
            for i in range(3):
                case=X.make_case(family,i,'x410-independent-smoke')
                cnf.write_text(case['source'])
                prior,a=call(old,cnf,'core',work_limit=100000)
                core,b=call(new,cnf,'core',work_limit=100000)
                skip,c=call(new,cnf,'cheap_sham',model,work_limit=100000)
                assert prior.returncode==core.returncode==skip.returncode
                if core.returncode==10:assert X.witness_ok(core.stdout,case)
                assert stats_equal(a,b) and stats_equal(b,c)
                if c['X45_COMPARE']['reached']:
                    assert c['X47_POLICY']['gate_skipped']
                    assert c['X47_POLICY']['features']==[]
                    assert c['X47_POLICY']['probe_inspections']==0
                    reached+=1
                checked+=3
        # Independent mathematical UNSAT category, not merely planted SAT.
        for i in range(8):
            unsat=pigeonhole(i,'X410-SMOKE-PHP')
            cnf.write_text(unsat['source'])
            prior,a=call(old,cnf,'core',work_limit=100000)
            core,b=call(new,cnf,'core',work_limit=100000)
            skip,c=call(new,cnf,'cheap_sham',model,work_limit=100000)
            assert prior.returncode==core.returncode==skip.returncode and core.returncode in (0,20)
            assert stats_equal(a,b) and stats_equal(b,c)
            checked+=3
        mock['min_conflicts']=0
        mock['min_propagations']=0
        write_model(model,mock)
        X.DECISION=32
        X.WORK_LIMIT=100000
        for family in ('uniform3','dense3','grid_xor','community_bridge','color4'):
            for i in range(6):
                case=X.make_case(family,i,'X410-LEARNED-SMOKE')
                cnf.write_text(case['source'])
                r=X.run(new,cnf,case,'cheap',0,model=model,work_limit=100000)
                assert r['verified'] or r['policy']['work_limit_hit']
                pol=r['policy']
                assert pol['probe_inspections']==0
                if r['reached']:
                    assert len(pol['features'])==NF
                    score,_=predict(mock,pol['features'])
                    assert abs(score-pol['score'])<1e-8
                    assert pol['flipped']==choose(mock,pol['features'])
                    reached+=1
                checked+=1
        # Exercise actual medium generator, including the planted3 composition.
        for fam in ('uniform3','grid_xor','circuit'):
            case=medium_case(fam,3,'smoke')
            assert case['n']>=150 and len(case['sha256'])==64
            cnf.write_text(case['source'])
            trial=X.run(new,cnf,case,'core',0,work_limit=100000)
            assert trial['verified'] or trial['policy']['work_limit_hit']
            assert trial['policy']['probe_inspections']==0
            checked+=1
        for bad in ('garbage','X491 30 2 0 8 ridge 0 0','X4101 30 2 nan 8 ridge 0 0 0','X4101 30 2 0 8 ridge 0 -2 0','X4101 30 2 0 8 ridge 0 0 -3'):
            model.write_text(bad)
            p=subprocess.run([str(new),str(cnf),'--mode','core','--branch-at','16',
                              '--policy','cheap','--model',str(model)],capture_output=True,text=True)
            assert p.returncode==1
            checked+=1
    assert reached>=5,('checkpoint coverage',reached)
    print('X410_TEST_PASS '+json.dumps({'truth_table_sources':len(cases),
           'native_runs':checked,'decision_checkpoint_reached':reached,
           'core_equivalent_to_x49':True,'zero_probe':True,
           'analytic_unsat_smoke':8,'fail_closed':True}),flush=True)


if __name__=='__main__':main()
