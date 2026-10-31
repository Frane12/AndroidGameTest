#!/usr/bin/env python3
"""Train on known SATLIB and constructed controls, freeze, evaluate on NEW SATLIB and separate controls.
Compare base vs always-probe vs learned policy with three counterbalanced in-process runs.
"""
import csv,hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from collections import Counter
from drnas_np_lab import read_dimacs,normalize,check
from nf_v05_structural import features,solve_strategy,fit,decision
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'nf05_results'
BUDGET=1.8

def controls(n,seed,kind):
    rng=random.Random(seed);flip=[bool(rng.getrandbits(1)) for _ in range(n)]
    cs=[]
    for _ in range(n*3):
        vs=rng.sample(range(1,n+1),3);head=rng.randrange(4)
        cs.append(tuple(v if j==head else -v for j,v in enumerate(vs)))
    if kind=='horn_unsat':
        cs.extend([(1,),(-n,)])
        cs.extend([(-v,v+1) for v in range(1,n)])
    if kind=='near_sat':
        for _ in range(max(1,n//2)):
            a,b,c=rng.sample(range(1,n+1),3)
            cs.append((a,b,-c))
    return normalize(n,[tuple(-l if flip[abs(l)-1] else l for l in c) for c in cs])

def corpus(folder):
    folder=ROOT/folder
    with (folder/'manifest.csv').open() as f:manifest=list(csv.DictReader(f))
    cases=[]
    for r in manifest:
        path=folder/(r['case_id']+'.cnf')
        n,cs=read_dimacs(path)
        assert n==int(r['n'])
        cases.append(dict(id=r['case_id'],source='SATLIB',family=r['family'],n=n,c=cs,
            sha=r['original_sha256'],expected=r['expected'],path=path))
    return cases

def make_controls(phase):
    arr=[]
    seed_base=654321 if phase=='train' else 765432
    for n in (30,60,100):
        for kind in ('horn_sat','horn_unsat','near_sat'):
            for j in range(8):
                seed=seed_base+1000*n+31*j+len(kind)
                cs=controls(n,seed,kind)
                arr.append(dict(id=f'{phase}_{kind}_{n}_{j:02}',source='constructed',family=kind,
                    n=n,c=cs,sha=hashlib.sha256(repr(cs).encode()).hexdigest(),
                    expected='UNSAT' if kind=='horn_unsat' else 'SAT',path=None))
    return arr

def verify(x,out):
    assert out.status==x['expected'],(x['id'],x['expected'],out.status,out.path)
    if out.status=='SAT': assert out.model is not None and check(x['c'],out.model),x['id']

def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def train(cases):
    random.Random(2026110619).shuffle(cases)
    rows=[]
    for i,x in enumerate(cases):
        n,cs=x['n'],x['c'];feat=features(n,cs)
        order=('base','always') if i%2==0 else ('always','base')
        res={}
        for mode in order:
            res[mode]=solve_strategy(n,cs,mode,budget=BUDGET)
            verify(x,res[mode])
        # direct Horn (zero defects) is exact and cheaper than full 2-SAT probing.
        if feat.defect_count==0:
            direct=solve_strategy(n,cs,'learned',threshold=0,budget=BUDGET)
            verify(x,direct)
            candidate=direct.ms
        else:
            candidate=res['always'].ms+feat.feature_ms
        rows.append(dict(case_id=x['id'],source=x['source'],family=x['family'],n=n,
            bucket=feat.bucket,defect=feat.defect,defect_count=feat.defect_count,
            feature_ms=feat.feature_ms,base_ms=res['base'].ms,candidate_ms=candidate,
            full_probe_ms=res['always'].probe_ms,base_path=res['base'].path,candidate_path=res['always'].path))
        if (i+1)%40==0:print(f'TRAIN {i+1}/{len(cases)}',flush=True)
    write(OUT/'training.csv',rows)
    policy=fit(rows)
    (OUT/'frozen_policy.json').write_text(json.dumps(policy,indent=2))
    print('FROZEN POLICY', {k:v['threshold'] for k,v in policy['table'].items()},flush=True)
    return policy

def check_crypto(case):
    if case['path'] is None:return
    r=subprocess.run(['cryptominisat5','--verb','0',str(case['path'])],text=True,capture_output=True,timeout=3)
    status='UNSAT' if 's UNSATISFIABLE' in r.stdout else 'SAT' if 's SATISFIABLE' in r.stdout else 'ERROR'
    assert status==case['expected'],(case['id'],status,case['expected'],r.stderr[-500:])

def heldout(cases,policy,reps=3):
    random.Random(2026110620).shuffle(cases)
    rows=[]
    for i,x in enumerate(cases):
        check_crypto(x)
        threshold=decision(policy,x['n'],x['c'])
        for rep in range(reps):
            order=('base','always','learned') if (i+rep)%2==0 else ('learned','always','base')
            runs={}
            for name in order:
                r=solve_strategy(x['n'],x['c'],variant=name,threshold=threshold,budget=BUDGET)
                verify(x,r);runs[name]=r
            feat=features(x['n'],x['c'])
            rows.append(dict(case_id=x['id'],source=x['source'],family=x['family'],n=x['n'],
                m=len(x['c']),repeat=rep,threshold=threshold,defect=feat.defect,status=x['expected'],
                base_ms=round(runs['base'].ms,4),always_ms=round(runs['always'].ms,4),
                learned_ms=round(runs['learned'].ms,4),learned_path=runs['learned'].path,
                always_path=runs['always'].path,learned_feature_ms=round(runs['learned'].feature_ms,4),
                learned_probe_ms=round(runs['learned'].probe_ms,4)))
        if (i+1)%40==0:print(f'TEST {i+1}/{len(cases)}',flush=True)
    write(OUT/'heldout_measurements.csv',rows)
    summaries=[]
    for source,family in sorted(set((x['source'],x['family']) for x in rows)):
        rs=[x for x in rows if (x['source'],x['family'])==(source,family)]
        gains=[x['base_ms']-x['learned_ms'] for x in rs]
        summaries.append(dict(source=source,family=family,cases=len(rs)//reps,repetitions=reps,
            base_median_ms=round(statistics.median(x['base_ms'] for x in rs),3),
            always_median_ms=round(statistics.median(x['always_ms'] for x in rs),3),
            learned_median_ms=round(statistics.median(x['learned_ms'] for x in rs),3),
            median_paired_gain_ms=round(statistics.median(gains),3),
            learned_wins=sum(x>0 for x in gains),
            direct_horn=sum(x['learned_path']=='direct-majority-Horn' for x in rs)//reps,
            exact_probe=sum(x['learned_path']=='exact-renamable-Horn' for x in rs)//reps))
    write(OUT/'summary.csv',summaries)
    (OUT/'protocol.json').write_text(json.dumps(dict(
        train_cases=232,test_cases=232,external_test=160,constructed_test=72,
        repeats=reps,budget_seconds=BUDGET,freeze=True,
        timings='in-process wall clock; cost of features included in learned',
        no_holdout_training=True,independent_original_sha256=True,
        no_private_gpu_neuroflow_code=True),indent=2))
    print('HELDOUT SUMMARY',flush=True)
    for line in summaries:print(json.dumps(line),flush=True)

def main():
    OUT.mkdir(exist_ok=True)
    tr=corpus('nf05_train_satlib')+make_controls('train')
    ts=corpus('nf05_holdout_satlib')+make_controls('test')
    assert len(tr)==len(ts)==232
    assert {x['sha'] for x in tr}.isdisjoint({x['sha'] for x in ts})
    policy=train(tr);heldout(ts,policy)
if __name__=='__main__':main()
