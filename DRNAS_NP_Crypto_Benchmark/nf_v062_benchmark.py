#!/usr/bin/env python3
"""Train-only NeuroFlow v0.6.2 gates vs matched unseen SATLIB and constructed Horn controls."""
import csv,hashlib,json,random,statistics,subprocess
from pathlib import Path
from drnas_np_lab import normalize,read_dimacs,check
from nf_v062_hornfast import run,fit
from nf_v06_multifeature import run as old_v06
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'nf062_results'
BUDGET=2.5

def controls(phase):
    arr=[]
    base=145310 if phase=='train' else 451310
    for n in (30,60,100):
        for kind in ('horn_sat','horn_unsat','near_sat'):
            for j in range(8):
                rng=random.Random(base+125*n+13*j+len(kind)*301)
                flips=[bool(rng.getrandbits(1)) for _ in range(n)]
                clauses=[]
                for _ in range(3*n):
                    vars3=rng.sample(range(1,n+1),3);head=rng.randrange(4)
                    clauses.append(tuple(v if i==head else -v for i,v in enumerate(vars3)))
                if kind=='horn_unsat':
                    clauses.extend([(1,),(-n,)])
                    clauses.extend([(-v,v+1) for v in range(1,n)])
                if kind=='near_sat':
                    for _ in range(n//2):
                        a,b,c=rng.sample(range(1,n+1),3);clauses.append((a,b,-c))
                clauses=normalize(n,[tuple(-l if flips[abs(l)-1] else l for l in c) for c in clauses])
                arr.append(dict(id=f'{phase}_{kind}_{n}_{j}',source='constructed',family=kind,
                    n=n,clauses=clauses,expected='UNSAT' if kind=='horn_unsat' else 'SAT',
                    fingerprint=hashlib.sha256(repr(clauses).encode()).hexdigest(),path=None))
    return arr

def satlib(phase):
    folder=ROOT/('nf062_'+phase+'_satlib')
    with (folder/'manifest.csv').open() as f:records=list(csv.DictReader(f))
    arr=[]
    for r in records:
        path=folder/(r['case_id']+'.cnf')
        n,clauses=read_dimacs(path)
        assert n==int(r['n'])
        arr.append(dict(id=r['case_id'],source='SATLIB',family=r['family'],
            n=n,clauses=clauses,expected=r['expected'],path=path,
            fingerprint=r['original_sha256']))
    return arr

def valid(x,res):
    assert res.status==x['expected'],(x['id'],x['expected'],res.status,res.route)
    if res.status=='SAT':assert res.model is not None and check(x['clauses'],res.model)

def csv_write(path,rows):
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)

def training(cases):
    random.Random(20501201).shuffle(cases)
    data=[]
    for i,x in enumerate(cases):
        n,clauses=x['n'],x['clauses']
        measures={}
        for v in (('base','force') if i%2==0 else ('force','base')):
            r=run(n,clauses,v,budget=BUDGET)
            valid(x,r)
            measures[v]=r
        base,force=measures['base'],measures['force']
        data.append(dict(id=x['id'],source=x['source'],family=x['family'],n=n,
            minority=force.minority,unit_share=force.unit_share,defect=force.defect,
            first_ms=force.first_ms,defect_ms=force.defect_ms,
            base_ms=base.ms,force_ms=force.ms,exact_ms=force.exact_ms,
            probe_route=force.route))
        if (i+1)%35==0:print('TRAIN',i+1,'/',len(cases),flush=True)
    model=fit(data)
    csv_write(OUT/'training.csv',data)
    (OUT/'frozen_policy.json').write_text(json.dumps(model,indent=2))
    print('FROZEN POLICY',json.dumps(model),flush=True)
    return model

def crypto_verify(x):
    if x['path'] is None:return
    proc=subprocess.run(['cryptominisat5','--verb','0',str(x['path'])],
       text=True,capture_output=True,timeout=8)
    status='UNSAT' if 's UNSATISFIABLE' in proc.stdout else 'SAT' if 's SATISFIABLE' in proc.stdout else 'ERROR'
    assert status==x['expected'],(x['id'],status,x['expected'],proc.stderr[-400:])

def benchmark(cases,policy):
    random.Random(20501202).shuffle(cases)
    rows=[]
    for i,x in enumerate(cases):
        crypto_verify(x)
        for rep in range(3):
            methods=['base','adaptive','force','old-v06']
            k=(i+rep)%4;ordered=methods[k:]+methods[:k]
            measurements={}
            for method in ordered:
                if method=='old-v06':
                    m=old_v06(x['n'],x['clauses'],'learned',
                        {'selection':{'disabled':True}},budget=BUDGET)
                    assert m.status==x['expected'],(x['id'],method,m.status)
                    if m.status=='SAT':assert m.assignment is not None and check(x['clauses'],m.assignment)
                    measurements[method]=(m.ms,'old-v06-disabled',m.feature_ms)
                else:
                    m=run(x['n'],x['clauses'],method,policy=policy,budget=BUDGET)
                    valid(x,m)
                    measurements[method]=(m.ms,m.route,m.first_ms+m.defect_ms)
            rows.append(dict(id=x['id'],source=x['source'],family=x['family'],rep=rep,
                status=x['expected'],n=x['n'],base_ms=round(measurements['base'][0],4),
                adaptive_ms=round(measurements['adaptive'][0],4),
                force_ms=round(measurements['force'][0],4),
                old_v06_ms=round(measurements['old-v06'][0],4),
                route=measurements['adaptive'][1],
                gate_ms=round(measurements['adaptive'][2],4)))
        if (i+1)%35==0:print('TEST',i+1,'/',len(cases),flush=True)
    csv_write(OUT/'heldout.csv',rows)
    groups=sorted(set((r['source'],r['family']) for r in rows))
    groups.extend([('SATLIB','ALL'),('constructed','ALL'),('ALL','ALL')])
    summary=[]
    for source,family in groups:
        rs=[r for r in rows if (source=='ALL' or r['source']==source)
            and (family=='ALL' or r['family']==family)]
        gain=[r['base_ms']-r['adaptive_ms'] for r in rs]
        summary.append(dict(source=source,family=family,cases=len(rs)//3,
            base_median_ms=round(statistics.median(r['base_ms'] for r in rs),4),
            adaptive_median_ms=round(statistics.median(r['adaptive_ms'] for r in rs),4),
            force_median_ms=round(statistics.median(r['force_ms'] for r in rs),4),
            old_v06_median_ms=round(statistics.median(r['old_v06_ms'] for r in rs),4),
            paired_mean_gain_ms=round(statistics.mean(gain),4),
            paired_median_gain_ms=round(statistics.median(gain),4),
            faster_runs=sum(g>0 for g in gain),total_runs=len(rs),
            stage1_skips=sum(r['route']=='skip-first' for r in rs)//3,
            stage2_skips=sum(r['route']=='skip-defect' for r in rs)//3,
            recognized=sum('Horn' in r['route'] for r in rs)//3,
            disabled=sum(r['route']=='disabled-no-features' for r in rs)//3,
            gate_median_ms=round(statistics.median(r['gate_ms'] for r in rs),4)))
    csv_write(OUT/'summary.csv',summary)
    (OUT/'protocol.json').write_text(json.dumps(dict(
         train=len(training_cases),heldout=len(cases),
         external_holdout=sum(x['source']=='SATLIB' for x in cases),
         repetitions=3,original_sha256_disjoint=True,
         training_only_frozen=True,status_and_sat_models_verified=True,
         time='in-process real wall time includes all gating and processing'),indent=2))
    print('HELDOUT SUMMARY',flush=True)
    for x in summary:print(json.dumps(x),flush=True)

def main():
    global training_cases
    OUT.mkdir(exist_ok=True)
    training_cases=satlib('train')+controls('train')
    test=satlib('holdout')+controls('holdout')
    assert len(training_cases)==len(test) and len(test)>=192
    assert {x['fingerprint'] for x in training_cases}.isdisjoint(
           x['fingerprint'] for x in test)
    model=training(training_cases)
    benchmark(test,model)
if __name__=='__main__':main()
