#!/usr/bin/env python3
"""NeuroFlow 0.6 train-only multi-feature net-gain benchmark. Frozen 232/232 split."""
import csv,hashlib,json,random,statistics,subprocess
from pathlib import Path
from drnas_np_lab import check,normalize,read_dimacs
from nf_v06_multifeature import signature,run,build_model,decide
ROOT=Path(__file__).resolve().parent
DEST=ROOT/'nf06_results'
BUDGET=2.5

def controls(phase):
    rngbase=987600 if phase=='train' else 987900
    out=[]
    for n in (30,60,100):
        for kind in ('horn_sat','horn_unsat','near_sat'):
            for j in range(8):
                rng=random.Random(rngbase+n*121+len(kind)*37+j*11)
                flip=[bool(rng.getrandbits(1)) for _ in range(n)]
                clauses=[]
                for _ in range(3*n):
                    vs=rng.sample(range(1,n+1),3)
                    head=rng.randrange(4)
                    clauses.append(tuple(v if idx==head else -v for idx,v in enumerate(vs)))
                if kind=='horn_unsat':
                    clauses.extend([(1,),(-n,)])
                    clauses.extend([(-v,v+1) for v in range(1,n)])
                if kind=='near_sat':
                    for _ in range(n//2):
                        a,b,c=rng.sample(range(1,n+1),3)
                        clauses.append((a,b,-c))
                clauses=normalize(n,[tuple(-l if flip[abs(l)-1] else l for l in c) for c in clauses])
                out.append(dict(id=f'{phase}_{kind}_{n}_{j}',family=kind,source='constructed',
                    n=n,cs=clauses,sha=hashlib.sha256(repr(clauses).encode()).hexdigest(),
                    expected='UNSAT' if kind=='horn_unsat' else 'SAT',file=None))
    return out

def satlib(phase):
    folder=ROOT/f'nf06_{phase}_satlib'
    with (folder/'manifest.csv').open() as f:records=list(csv.DictReader(f))
    out=[]
    for rec in records:
        path=folder/(rec['case_id']+'.cnf')
        n,clauses=read_dimacs(path)
        assert n==int(rec['n']) and len(clauses)==int(rec['m'])
        out.append(dict(id=rec['case_id'],source='SATLIB',family=rec['family'],
            n=n,cs=clauses,sha=rec['original_sha256'],expected=rec['expected'],file=path))
    return out

def verify(x,r):
    assert r.status==x['expected'],(x['id'],r.method,r.status,x['expected'])
    if r.status=='SAT':assert r.assignment is not None and check(x['cs'],r.assignment)

def write(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def learn(train):
    random.Random(29012027).shuffle(train);data=[]
    for i,x in enumerate(train):
        fs=signature(x['n'],x['cs']);samples={'base':[],'always':[]}
        for rep in range(2):
            order=('base','always') if (i+rep)%2==0 else ('always','base')
            for variant in order:
                r=run(x['n'],x['cs'],variant,budget=BUDGET)
                verify(x,r);samples[variant].append(r.ms)
        base=statistics.median(samples['base']);probe=statistics.median(samples['always'])
        data.append(dict(case_id=x['id'],family=x['family'],source=x['source'],
            vector=list(fs.vector),feature_ms=fs.ms,base_ms=base,always_ms=probe,
            gain_ms=base-probe-fs.ms))
        if (i+1)%40==0:print(f'TRAIN {i+1}/{len(train)}',flush=True)
    model=build_model(data)
    (DEST/'frozen_model.json').write_text(json.dumps(model,indent=2))
    write(DEST/'training.csv',[{k:v for k,v in x.items() if k!='vector'} for x in data])
    print('FROZEN TRAIN-ONLY MODEL',model['selection'],flush=True)
    return model

def check_cms(x):
    if x['file'] is None:return
    r=subprocess.run(['cryptominisat5','--verb','0',str(x['file'])],text=True,capture_output=True,timeout=6)
    status='UNSAT' if 's UNSATISFIABLE' in r.stdout else 'SAT' if 's SATISFIABLE' in r.stdout else 'ERROR'
    assert status==x['expected'],(x['id'],status,x['expected'],r.stderr[-250:])

def evaluate(cases,model):
    random.Random(29012028).shuffle(cases);rows=[]
    for i,x in enumerate(cases):
        check_cms(x)
        for rep in range(3):
            methods=('base','always','v05','learned');shift=(i+rep)%4
            order=methods[shift:]+methods[:shift];out={}
            for method in order:
                out[method]=run(x['n'],x['cs'],method,model=model,budget=BUDGET)
                verify(x,out[method])
            fs=signature(x['n'],x['cs']);d=decide(model,fs.vector)
            rows.append(dict(case_id=x['id'],source=x['source'],family=x['family'],repeat=rep,
                status=x['expected'],n=x['n'],m=len(x['cs']),
                base_ms=round(out['base'].ms,5),always_ms=round(out['always'].ms,5),
                previous_v05_ms=round(out['v05'].ms,5),neuro_v06_ms=round(out['learned'].ms,5),
                selected=d['probe'],predicted_net_ms=d['expected_ms'],
                positive_neighbor_fraction=d['confidence'],feature_ms=round(out['learned'].feature_ms,5),
                learned_method=out['learned'].method))
        if (i+1)%40==0:print(f'TEST {i+1}/{len(cases)}',flush=True)
    write(DEST/'heldout.csv',rows)
    groups=sorted(set((r['source'],r['family']) for r in rows))
    groups.extend([('SATLIB','ALL'),('constructed','ALL'),('ALL','ALL')]);summary=[]
    for source,family in groups:
        subset=[r for r in rows if (source=='ALL' or r['source']==source) and
            (family=='ALL' or r['family']==family)]
        if not subset:continue
        gains=[r['base_ms']-r['neuro_v06_ms'] for r in subset]
        summary.append(dict(source=source,family=family,cases=len(subset)//3,
            baseline_median_ms=round(statistics.median(r['base_ms'] for r in subset),4),
            always_median_ms=round(statistics.median(r['always_ms'] for r in subset),4),
            previous_v05_median_ms=round(statistics.median(r['previous_v05_ms'] for r in subset),4),
            neuro_v06_median_ms=round(statistics.median(r['neuro_v06_ms'] for r in subset),4),
            paired_median_gain_ms=round(statistics.median(gains),4),
            paired_mean_gain_ms=round(statistics.mean(gains),4),
            faster_runs=sum(g>0 for g in gains),total_runs=len(gains),
            selected_cases=sum(r['selected'] for r in subset)//3,
            feature_median_ms=round(statistics.median(r['feature_ms'] for r in subset),4)))
    write(DEST/'summary.csv',summary)
    (DEST/'protocol.json').write_text(json.dumps({
        'train_cases':232,'heldout_cases':232,'external_new_cases':160,'synthetic_controls':72,
        'repeats':3,'measures':'in-process paired wall times incl all features and probe costs',
        'frozen_before_heldout':True,'reference':'CryptoMiniSat checks external SAT/UNSAT, NOT speed'},indent=2))
    print('HELDOUT SUMMARY',flush=True)
    for r in summary:print(json.dumps(r),flush=True)

def main():
    DEST.mkdir(exist_ok=True)
    train=satlib('train')+controls('train')
    test=satlib('holdout')+controls('holdout')
    assert len(train)==len(test)==232
    assert {x['sha'] for x in train}.isdisjoint({x['sha'] for x in test})
    evaluate(test,learn(train))
if __name__=='__main__':main()
