#!/usr/bin/env python3
"""X4.11 active policy: conservative proxy label, native parity and zero-probe checks.
X4.10 independent truth-table SAT/UNSAT smoke is run separately unchanged.
"""
import argparse
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
import drnas_x410 as B
import drnas_x411 as N
from x410_models import write_model,predict,choose


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cases',type=int,default=24)
    args=ap.parse_args()
    assert args.cases>=16
    assert N.net_label(1000,400)[1]==300
    assert N.net_label(1000,1200)[1]==-500
    assert N.net_label(1000,600)[1]==100
    assert N.net_label(1000,850)[1]==-150
    assert N.net_label(1000,700)[1]==0
    assert N.net_label(1000,400)[0]>0
    assert N.net_label(1000,900)[0]<0

    binary=ROOT/'build/drnas-x410'
    X=N.X
    X.DECISION=32
    X.WORK_LIMIT=250000
    B.NAMESPACE=N.NAMESPACE
    model={'centers':[0.]*30,'scales':[10000.]*30,
           'weights':[[0.]*30+[0.]]*2,
           'threshold':-.5,'ood_limit':8.,
           'kind':'ridge','bias':0.,
           'min_conflicts':0,'min_propagations':0}
    examined=0;reached=0;changed=0;matched=0
    families=('uniform3','dense3','uniform4','xor_mixed','community','circuit')
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        cnf=td/'case.cnf'
        path=td/'active_model.txt'
        write_model(path,model)
        for i in range(args.cases):
            fam=families[i%len(families)]
            c=B.make_case(fam,i,'smoke')
            cnf.write_text(c['source'])
            core=X.run(binary,cnf,c,'core',0,work_limit=250000)
            sham=X.run(binary,cnf,c,'cheap_sham',0,model=path,work_limit=250000)
            active=X.run(binary,cnf,c,'cheap',0,model=path,work_limit=250000)
            forced=X.run(binary,cnf,c,'flip',0,work_limit=250000)
            for a in (core,sham,active,forced):
                assert a['verified'] or a['policy']['work_limit_hit']
                assert a['policy']['probe_inspections']==0
            assert all(core[k]==sham[k] for k in ('propagations','decisions','conflicts'))
            if active['reached']:
                reached+=1
                p=active['policy']
                assert len(p['features'])==30
                score,ood=predict(model,p['features'])
                assert not ood
                assert abs(score-p['score'])<1e-9
                assert choose(model,p['features'])==p['flipped']
                changed+=int(p['flipped'])
                assert forced['policy']['flipped']
            if i<8:
                pair=N.pair(binary,cnf,c)
                assert pair['base']['reached']==pair['flip']['reached']
                if pair['features'] is not None:
                    matched+=1
                    assert len(pair['features'])==30
                    assert pair['base']['pre']['pre_state_digest']==pair['flip']['pre']['pre_state_digest']
                    if pair['label'] is not None:
                        assert pair['net_after_proxy']==(pair['base']['remaining_propagations']-
                                                         pair['flip']['remaining_propagations']-N.OVERHEAD)
            examined+=1
    assert reached>=6,(reached,examined)
    assert changed>=6,(changed,examined)
    assert matched>=2
    print('X411_TEST_PASS '+__import__('json').dumps(dict(
        formulas=examined,checkpoints=reached,active_polarity_changes=changed,
        matched_pairs=matched,zero_shadow_probes=True,
        core_equivalent_to_sham=True,independent_oracle_in_x410_smoke=True)),flush=True)


if __name__=='__main__':
    main()
