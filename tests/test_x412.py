#!/usr/bin/env python3
"""X4.12: independent truth tables, old CORE equivalence, native/Python two-stage parity."""
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
import drnas_x410 as B
import drnas_x412 as E
from x412_models import NF,choose,scores,write_model
from drnas_x412_unsat import pigeonhole

X=B.X


def oracle(n,clauses):
    return any(all(any(bool(bits[abs(l)-1])==(l>0) for l in c) for c in clauses)
               for bits in itertools.product((0,1),repeat=n))


def call(binary,cnf,policy,model=None,work_limit=0):
    cmd=[str(binary),str(cnf),'--mode','core','--stats','--time','0' if work_limit else '2',
         '--branch-at','32','--policy',policy]
    if work_limit:cmd+=['--work-limit',str(work_limit)]
    if model:cmd+=['--model',str(model)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
    data={}
    for line in p.stderr.splitlines():
        if line.startswith(('X41_STATS ','X45_COMPARE ','X47_POLICY ')):
            tag,body=line.split(' ',1);data[tag]=json.loads(body)
    assert p.returncode in (0,10,20),(p.stderr[-2000:],p.returncode)
    assert all(k in data for k in ('X41_STATS','X45_COMPARE','X47_POLICY'))
    return p,data


def same_search(a,b):
    assert all(a['X41_STATS'][k]==b['X41_STATS'][k]
               for k in ('decisions','conflicts','propagations','learnt','restarts'))


def mock(gate_bias=12.,gain_bias=.5,gate_threshold=.5,gain_threshold=.1,
         min_conflicts=0,min_propagations=0):
    return dict(centers=[0.]*NF,scales=[1000.]*NF,
                gate_weights=[0.]*NF+[gate_bias],gain_weights=[0.]*NF+[gain_bias],
                gate_threshold=gate_threshold,gain_threshold=gain_threshold,
                ood_limit=8.,min_conflicts=min_conflicts,min_propagations=min_propagations)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cases',type=int,default=100)
    args=ap.parse_args()
    old=ROOT/'build/drnas-x410'
    native=ROOT/'build/drnas-x412'
    rng=random.Random(4121311)
    checked=0;reached=0;changes=0
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);cnf=td/'source.cnf';model=td/'model.txt'
        write_model(model,mock())
        tiny=[(0,[]),(0,[[]]),(1,[[1],[-1]]),(3,[[1,2],[-1,3],[-2,-3]])]
        for i in range(args.cases):
            n=rng.randrange(1,9)
            clauses=[[rng.choice((-1,1))*v for v in
                      rng.sample(range(1,n+1),rng.randrange(1,min(4,n)+1))]
                     for _ in range(rng.randrange(1,n*5+1))]
            tiny.append((n,clauses))
        for n,clauses in tiny:
            cnf.write_text(f'p cnf {n} {len(clauses)}\n'+
                           ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
            prior,a=call(old,cnf,'core')
            now,b=call(native,cnf,'core')
            sham,s=call(native,cnf,'contextual_sham',model)
            truth=oracle(n,clauses)
            assert prior.returncode==now.returncode==sham.returncode==(10 if truth else 20)
            if truth:assert X.witness_ok(now.stdout,{'n':n,'clauses':clauses})
            same_search(a,b);same_search(b,s)
            assert prior.stdout==now.stdout==sham.stdout
            assert s['X47_POLICY']['probe_inspections']==0
            checked+=3
        for fam in ('uniform3','dense3','color4','circuit','community_bridge','grid_xor'):
            for i in range(5):
                case=B.make_case(fam,i,'x412-smoke')
                cnf.write_text(case['source'])
                prior,a=call(old,cnf,'core',work_limit=250000)
                now,b=call(native,cnf,'core',work_limit=250000)
                sham,s=call(native,cnf,'contextual_sham',model,work_limit=250000)
                forced,f=call(native,cnf,'flip',work_limit=250000)
                active,x=call(native,cnf,'contextual',model,work_limit=250000)
                assert prior.returncode==now.returncode==sham.returncode
                assert active.returncode in (0,10)
                assert forced.returncode in (0,10)
                if now.returncode==10:assert X.witness_ok(now.stdout,case)
                if active.returncode==10:assert X.witness_ok(active.stdout,case)
                same_search(a,b);same_search(b,s)
                assert all(z['X47_POLICY']['probe_inspections']==0 for z in (b,s,f,x))
                if x['X45_COMPARE']['reached']:
                    reached+=1
                    pol=x['X47_POLICY'];pr=mock()
                    z=scores(pr,pol['features'])
                    assert z['gate']>=.5 and abs(z['gate']-pol['gate_probability'])<1e-8
                    assert abs(z['gain']-pol['gain_score'])<1e-8
                    assert pol['stage1_pass'] and pol['stage2_pass'] and pol['flipped']
                    assert choose(pr,pol['features'],x['X45_COMPARE']['prefix_conflicts'],
                                  x['X45_COMPARE']['prefix_propagations'])
                    same_search(f,x)
                    changes+=1
                checked+=5
        assert reached>=8 and changes>=8,(reached,changes)
        # Force separate rejections by context, estimated gain, and early cheap gate.
        c=B.make_case('color4',8,'x412-negatives')
        cnf.write_text(c['source'])
        core,base=call(native,cnf,'core',work_limit=250000)
        for negative in (mock(gate_bias=-12),mock(gain_bias=-.5),
                         mock(min_conflicts=100000,min_propagations=100000000)):
            write_model(model,negative)
            outcome,d=call(native,cnf,'contextual',model,work_limit=250000)
            assert outcome.returncode==core.returncode
            assert not d['X47_POLICY']['flipped']
            same_search(base,d)
            if d['X47_POLICY']['reached']:
                if negative['min_conflicts']:
                    assert d['X47_POLICY']['gate_skipped'] and not d['X47_POLICY']['features']
                elif negative['gain_weights'][-1]<0:
                    assert d['X47_POLICY']['stage1_pass'] and not d['X47_POLICY']['stage2_pass']
                else:
                    assert not d['X47_POLICY']['stage1_pass']
            checked+=1
        # Constructive nontrivial UNSAT controls: proof by the pigeonhole principle.
        for i in range(5):
            c=pigeonhole(i,'x412-smoke-php')
            cnf.write_text(c['source'])
            prior,a=call(old,cnf,'core',work_limit=250000)
            now,b=call(native,cnf,'core',work_limit=250000)
            assert prior.returncode==now.returncode and now.returncode in (0,20)
            same_search(a,b)
            checked+=2
        for bad in ('garbage','X4101 30 0.5 0 8 0 0',
                    'X4121 30 nan 0 8 0 0','X4121 30 0.5 0 -2 0 0',
                    'X4121 30 0.5 0 8 -2 0'):
            model.write_text(bad)
            p=subprocess.run([str(native),str(cnf),'--mode','core','--branch-at','32',
                              '--policy','contextual','--model',str(model)],
                             capture_output=True,text=True)
            assert p.returncode==1,(bad,p.stderr)
            checked+=1
    print('X412_TEST_PASS '+json.dumps(dict(tiny_truth_table=len(tiny),native_trials=checked,
           checkpoints=reached,active_polarity_changes=changes,
           two_stage_rejections_verified=True,zero_shadow_probes=True,
           old_CORE_identical=True,analytic_unsat_sources=5)),flush=True)


if __name__=='__main__':
    main()
