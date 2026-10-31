#!/usr/bin/env python3
"""NeuroFlow v0.6.1 benchmark: train 232, freeze; holdout 232 unseen, 3 repeats.

Compare base DRNAS, always-Horn, disabled v0.6 (pays full features) and
two-stage v0.6.1, preserving exact mathematical SAT/UNSAT and models.
No heldout examples enter the training stage.
"""
import csv,hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from drnas_np_lab import normalize,read_dimacs,check
from nf_v061_two_stage import cheap_scan,run,choose_model
from nf_v06_multifeature import signature,run as old_run
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'nf061_results';BUDGET=2.5

def controls(which):
    # Original construction method, NEW seeds distinct from previous v0.3-0.6.
    out=[];base=443210 if which=='train' else 592710
    for n in (30,60,100):
        for kind in ('horn_sat','horn_unsat','near_sat'):
            for j in range(8):
                rng=random.Random(base+n*123+len(kind)*71+j*101)
                flips=[bool(rng.getrandbits(1)) for _ in range(n)]
                cnf=[]
                for _ in range(n*3):
                    vs=rng.sample(range(1,n+1),3)
                    head=rng.randrange(4)
                    cnf.append(tuple(v if idx==head else -v for idx,v in enumerate(vs)))
                if kind=='horn_unsat':
                    cnf.extend([(1,),(-n,)])
                    cnf.extend([(-v,v+1) for v in range(1,n)])
                if kind=='near_sat':
                    for _ in range(n//2):
                        a,b,c=rng.sample(range(1,n+1),3)
                        cnf.append((a,b,-c))
                cnf=normalize(n,[tuple(-lit if flips[abs(lit)-1] else lit for lit in c) for c in cnf])
                expected='UNSAT' if kind=='horn_unsat' else 'SAT'
                out.append(dict(id=f'{which}_{kind}_{n}_{j}',family=kind,source='constructed',
                    n=n,cnf=cnf,expected=expected,origsha=hashlib.sha256(repr(cnf).encode()).hexdigest(),path=None))
    return out

def satlib(which):
    directory=ROOT/('nf061_'+which+'_satlib')
    with (directory/'manifest.csv').open() as f:manifest=list(csv.DictReader(f))
    out=[]
    for rec in manifest:
        path=directory/(rec['case_id']+'.cnf')
        n,cnf=read_dimacs(path)
        out.append(dict(id=rec['case_id'],family=rec['family'],source='SATLIB',n=n,
            cnf=cnf,expected=rec['expected'],origsha=rec['original_sha256'],path=path))
    return out

def verify(x,status,model):
    assert status==x['expected'],(x['id'],x['expected'],status)
    if status=='SAT':assert model is not None and check(x['cnf'],model),x['id']

def save(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def train(cases):
    random.Random(202703101).shuffle(cases)
    data=[]
    for i,x in enumerate(cases):
        n,cnf=x['n'],x['cnf']
        q=cheap_scan(n,cnf);fs=signature(n,cnf)
        baselines=[];forced=[]
        for rep in range(2):
            order=('base','force-gates') if (rep+i)%2==0 else ('force-gates','base')
            for variant in order:
                r=run(n,cnf,variant,budget=BUDGET)
                verify(x,r.status,r.model)
                if variant=='base':baselines.append(r.elapsed_ms)
                else:forced.append(r)
        base_ms=statistics.median(baselines)
        observed_probe=statistics.median(r.elapsed_ms-r.cheap_ms-r.full_ms for r in forced)
        data.append(dict(case_id=x['id'],family=x['family'],source=x['source'],n=n,
            minority=q.minority,unit_share=q.unit_share,defect=fs.numbers['horn_defect'],
            cheap_ms=q.ms,full_ms=fs.ms,baseline_ms=base_ms,probe_ms=observed_probe,
            actual_full_probe_wins=sum(r.elapsed_ms<base_ms for r in forced)))
        if (i+1)%40==0:print(f'TRAIN {i+1}/{len(cases)}',flush=True)
    policy=choose_model(data)
    save(OUT/'training.csv',data)
    (OUT/'frozen_policy.json').write_text(json.dumps(policy,indent=2))
    print('FROZEN TRAIN MODEL',json.dumps(policy),flush=True)
    return policy

def cms_check(x):
    if x['path'] is None:return
    r=subprocess.run(['cryptominisat5','--verb','0',str(x['path'])],
          capture_output=True,text=True,timeout=8)
    result='UNSAT' if 's UNSATISFIABLE' in r.stdout else 'SAT' if 's SATISFIABLE' in r.stdout else 'ERROR'
    assert result==x['expected'],(x['id'],result,x['expected'],r.stderr[-500:])

def evaluate(cases,policy,repeats=3):
    random.Random(202703102).shuffle(cases)
    rows=[];old_model={'selection':{'disabled':True}}
    for i,x in enumerate(cases):
        cms_check(x)
        n,cnf=x['n'],x['cnf']
        for rep in range(repeats):
            order=('base','always','old-v06','two-stage')
            j=(i+rep)%4;order=order[j:]+order[:j];runs={}
            for variant in order:
                if variant in ('base','two-stage'):
                    r=run(n,cnf,variant,policy,budget=BUDGET)
                    verify(x,r.status,r.model)
                    runs[variant]=(r.elapsed_ms,r.route,r.cheap_ms,r.full_ms)
                elif variant=='old-v06':
                    r=old_run(n,cnf,'learned',old_model,budget=BUDGET)
                    verify(x,r.status,r.assignment)
                    runs[variant]=(r.ms,r.method,r.feature_ms,0)
                else:
                    r=old_run(n,cnf,'always',budget=BUDGET)
                    verify(x,r.status,r.assignment)
                    runs[variant]=(r.ms,r.method,0,0)
            rows.append(dict(case_id=x['id'],source=x['source'],family=x['family'],
                n=n,m=len(cnf),rep=rep,base_ms=round(runs['base'][0],5),
                always_ms=round(runs['always'][0],5),old_v06_ms=round(runs['old-v06'][0],5),
                two_stage_ms=round(runs['two-stage'][0],5),route=runs['two-stage'][1],
                cheap_ms=round(runs['two-stage'][2],5),full_ms=round(runs['two-stage'][3],5)))
        if (i+1)%40==0:print(f'TEST {i+1}/{len(cases)}',flush=True)
    save(OUT/'holdout.csv',rows)
    groups=sorted(set((r['source'],r['family']) for r in rows))
    groups += [('SATLIB','ALL'),('constructed','ALL'),('ALL','ALL')]
    summary=[]
    for source,family in groups:
        part=[r for r in rows if (source=='ALL' or r['source']==source) and
             (family=='ALL' or r['family']==family)]
        gain=[r['base_ms']-r['two_stage_ms'] for r in part]
        summary.append(dict(source=source,family=family,cases=len(part)//repeats,
            baseline_median_ms=round(statistics.median(r['base_ms'] for r in part),4),
            always_median_ms=round(statistics.median(r['always_ms'] for r in part),4),
            old_v06_median_ms=round(statistics.median(r['old_v06_ms'] for r in part),4),
            two_stage_median_ms=round(statistics.median(r['two_stage_ms'] for r in part),4),
            mean_paired_gain_ms=round(statistics.mean(gain),4),
            median_paired_gain_ms=round(statistics.median(gain),4),
            wins=sum(g>0 for g in gain),total=len(part),
            skipped=sum('skip' in r['route'] or 'disabled' in r['route'] for r in part)//repeats,
            probed=sum('Horn' in r['route'] for r in part)//repeats,
            expensive_full=sum(r['full_ms']>0 for r in part)//repeats,
            cheap_median_ms=round(statistics.median(r['cheap_ms'] for r in part),4)))
    save(OUT/'summary.csv',summary)
    (OUT/'protocol.json').write_text(json.dumps(dict(train=232,heldout=232,
        source_holdout=160,constructed_heldout=72,repeats=repeats,
        original_source_sha256_disjoint=True,train_frozen=True,
        timing='in-process including all feature extraction',
        reference='CryptoMiniSat checked all SATLIB outcomes',
        previous_v06_measured_disabled=True),indent=2))
    print('HELDOUT SUMMARY',flush=True)
    for rec in summary:print(json.dumps(rec),flush=True)

def main():
    OUT.mkdir(exist_ok=True)
    tr=satlib('train')+controls('train')
    ts=satlib('holdout')+controls('holdout')
    assert len(tr)==len(ts)==232
    assert {x['origsha'] for x in tr}.isdisjoint({x['origsha'] for x in ts})
    p=train(tr);evaluate(ts,p)
if __name__=='__main__':main()
