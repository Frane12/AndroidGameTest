#!/usr/bin/env python3
"""X4.12 two-stage contextual diagnostic with constructive independent pigeonhole UNSAT holdout.

Every generated CNF says H+1 pigeons occupy H holes, and no hole has two
pigeons. This is UNSAT by the pigeonhole principle (not a DRAT certificate).
No optimization or model selection uses these formulas; compare CORE vs CONTEXTUAL and forced polarity flip.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time

import numpy as np
import drnas_x47 as X

ARMS=('core','contextual','contextual_sham','flip')


def pigeonhole(index, namespace='X412-CONTEXT-PHP-v1'):
    holes=4+index%5
    pigeons=holes+1
    count=holes*pigeons
    rng=random.Random(int.from_bytes(hashlib.sha256(f'{namespace}:{index}'.encode()).digest()[:8],'big'))
    perm=list(range(1,count+1))
    rng.shuffle(perm)
    def v(p,h):return perm[p*holes+h]
    clauses=[]
    for p in range(pigeons):
        clauses.append([v(p,h) for h in range(holes)])
    for h in range(holes):
        for p in range(pigeons):
            for q in range(p+1,pigeons):
                clauses.append([-v(p,h),-v(q,h)])
    rng.shuffle(clauses)
    content=f'p cnf {count} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
    return {'family':'pigeonhole_unsat','holes':holes,'pigeons':pigeons,
            'index':index,'n':count,'sha256':hashlib.sha256(content.encode()).hexdigest(),
            'source':content,'certificate':'pigeonhole(H+1,H) with pairwise at-most-one per hole'}


def run(binary,cnf,policy,cap,model=None):
    cmd=[str(binary),str(cnf),'--mode','core','--time',str(cap),'--stats',
         '--branch-at','32','--policy',policy]
    if model is not None:cmd+=['--model',str(model)]
    t=time.perf_counter()
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+3)
    wall=time.perf_counter()-t
    if p.returncode not in (0,10,20):raise RuntimeError(p.stderr[-3000:])
    if p.returncode==10:raise AssertionError('SAT on analytically UNSAT pigeonhole formula')
    meta={line.split(' ',1)[0]:json.loads(line.split(' ',1)[1])
          for line in p.stderr.splitlines() if line.startswith(('X41_STATS ','X47_POLICY '))}
    assert 'X41_STATS' in meta and 'X47_POLICY' in meta
    solved=p.returncode==20 and wall<=cap
    return dict(status='UNSAT_ANALYTIC' if solved else 'UNKNOWN',
                verified=solved,wall_s=wall,PAR2=wall if solved else 2*cap,
                propagations=meta['X41_STATS']['propagations'],
                conflicts=meta['X41_STATS']['conflicts'],
                decisions=meta['X41_STATS']['decisions'],
                policy=meta['X47_POLICY'])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,default=Path('build/drnas-x412'))
    ap.add_argument('--frozen',type=Path,default=Path('x412_results/freeze.json'))
    ap.add_argument('--out',type=Path,default=Path('x412_unsat_results'))
    ap.add_argument('--count',type=int,default=32)
    ap.add_argument('--cap',type=float,default=3.0)
    ap.add_argument('--repeats',type=int,default=3)
    args=ap.parse_args()
    if args.count<24 or args.repeats<2 or args.cap<=0:raise ValueError('insufficient UNSAT test')
    args.out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    frozen=json.loads(args.frozen.read_text())
    model=args.frozen.parent/(frozen['primary_candidate']+'.txt')
    if hashlib.sha256(model.read_bytes()).hexdigest()!=frozen['model_sha256']:
        raise AssertionError('model changed after pre-UNSAT freeze')
    cases=[pigeonhole(i) for i in range(args.count)]
    assert len({c['sha256'] for c in cases})==len(cases)
    (args.out/'manifest.json').write_text(json.dumps(
        [{k:c[k] for k in ('sha256','family','holes','pigeons','n','certificate')} for c in cases],indent=2)+'\n')
    rows=[]
    cnf=args.out/'current.cnf'
    with (args.out/'trials.jsonl').open('w') as stream:
        for i,c in enumerate(cases):
            cnf.write_text(c['source'])
            for rep in range(args.repeats):
                order=list(ARMS)
                random.Random(49000+i*17+rep).shuffle(order)
                arms={name:run(binary,cnf,name,args.cap,model if name in ('contextual','contextual_sham') else None) for name in order}
                assert all(arm['policy']['probe_inspections']==0 for arm in arms.values())
                if arms['core']['verified'] and arms['contextual_sham']['verified']:
                    assert all(arms['core'][key]==arms['contextual_sham'][key]
                               for key in ('conflicts','decisions','propagations'))
                row={'sha256':c['sha256'],'holes':c['holes'],'rep':rep,'arms':arms}
                rows.append(row);stream.write(json.dumps(row,sort_keys=True)+'\n')
            if (i+1)%6==0:print('X412_UNSAT_PROGRESS '+json.dumps({'done':i+1,'total':len(cases)}),flush=True)
    cnf.unlink()
    by_source=defaultdict(list)
    for r in rows:by_source[r['sha256']].append(r)
    means={a:[float(np.mean([r['arms'][a]['PAR2'] for r in pair])) for pair in by_source.values()] for a in ARMS}
    report={'status':'COMPLETE','scope':'constructive pigeonhole UNSAT, not competition',
            'model_sha256':frozen['model_sha256'],'deploy_policy':frozen['deploy_policy'],
            'source_count':len(cases),'repeats':args.repeats,'cap_s':args.cap,
            'arms':{a:{'PAR2_s':sum(r['arms'][a]['PAR2'] for r in rows),
                       'UNSAT_analytic':sum(r['arms'][a]['verified'] for r in rows),
                       'trials':len(rows),
                       'flips':sum(r['arms'][a]['policy']['flipped'] for r in rows),
                       'probe_inspections':sum(r['arms'][a]['policy']['probe_inspections'] for r in rows)}
                    for a in ARMS},
            'vs_core':{a:X.effect(means['core'],means[a]) for a in ARMS if a!='core'},
            'proof':'H+1 pigeons into H holes; at least one hole per pigeon, at most one pigeon per hole',
            'limits':['Analytic constructed UNSAT, not independent proof format/competition CNF',
                      'No fine tuning on these holdout cases','Small number of structural families.']}
    (args.out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('X412_UNSAT_FINAL '+json.dumps(report,sort_keys=True),flush=True)


if __name__=='__main__':main()
