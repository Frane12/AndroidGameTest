#!/usr/bin/env python3
"""Train-and-FREEZE a conservative one-rule native NeuroFlow phase selector.

TRAIN contains 60 previously tested third-party CNFs + old 20 v0.9.1 CNFs.
New 20 v1.0 CNFs are NOT read by this module; the workflow only downloads
them AFTER frozen policy has been written. All SAT models verified in native.
"""
import csv,hashlib,json,random,statistics,subprocess
from pathlib import Path
from drnas_np_lab import read_dimacs
ROOT=Path(__file__).resolve().parent
BIN=ROOT/'native_v100/drnas_nf100'
OUT=ROOT/'native_v100/training'
RUN_BUDGET_MS=2300
RUNS=2
MODES=('base','phase-majority','phase-selective')

def save_csv(path,records):
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)

def load_train():
    with (ROOT/'nf063_external/manifest.csv').open(encoding='utf-8') as f:old60=list(csv.DictReader(f))
    with (ROOT/'nf091_holdout/manifest.csv').open(encoding='utf-8') as f:old20=list(csv.DictReader(f))
    assert len(old60)==60 and len(old20)==20
    samples=[]
    for row in old60:
        assert row['fetch_status']=='READY'
        p=ROOT/'nf063_external'/(row['case_id']+'.cnf')
        assert hashlib.sha256(p.read_bytes()).hexdigest()==row['canonical_sha256']
        samples.append(dict(id=row['case_id'],group=row['source_group'],path=p,sha=row['source_sha256']))
    for row in old20:
        p=ROOT/'nf091_holdout'/(row['id']+'.cnf')
        assert hashlib.sha256(p.read_bytes()).hexdigest()==row['canonical_sha256']
        samples.append(dict(id='prior091_'+row['id'],group='PriorBytWyze',path=p,sha=row['source_sha256']))
    assert len({s['sha'] for s in samples})==80
    return samples

def features(path):
    n,cnf=read_dimacs(path)
    pos=[0]*n;neg=[0]*n
    for cl in cnf:
        for l in cl:
            if l>0:pos[l-1]+=1
            else:neg[-l-1]+=1
    lit=sum(pos)+sum(neg)
    return dict(n=n, density=len(cnf)/max(1,n),
        minority=sum(min(p,q) for p,q in zip(pos,neg))/max(1,lit),
        long=sum(len(cl)>=4 for cl in cnf)/max(1,len(cnf)))

def invoke(path,mode):
    p=subprocess.run([str(BIN),'--input',str(path),'--mode',mode,
            '--budget-ms',str(RUN_BUDGET_MS)],
          capture_output=True,text=True,timeout=RUN_BUDGET_MS/1000+4)
    if p.returncode:raise RuntimeError(f'{mode} native error {path}: {p.stderr[-750:]}')
    r=json.loads(p.stdout.strip())
    if r['status']=='SAT':assert r['witness_valid'] is True
    return r

def utility(a,b):
    """Bound single-case influence. Missing solves penalized symmetrically."""
    completed=lambda x:x['status'] in ('SAT','UNSAT')
    if completed(a) and completed(b):
        assert a['status']==b['status']
        return max(-250.,min(250.,a['total_ms']-b['total_ms']))
    if completed(a) and not completed(b):return -250.
    if completed(b) and not completed(a):return +250.
    return 0.

def matching(f,rule):
    mode,min_n,max_n,min_density,max_density,min_minor,max_minor,min_long,max_long=rule
    return (min_n<=f['n']<=max_n and
        min_density<=f['density']<=max_density and
        min_minor<=f['minority']<=max_minor and
        min_long<=f['long']<=max_long)

def score_rule(rows,rule):
    mode=rule[0]
    vals=[r['gain_'+mode] for r in rows if matching(r,rule)]
    if not vals:return dict(gain=0., selected=0,up=0,down=0,mean=0.)
    gains=sum(vals)/len(rows)  # routing OFF on other cases: zero effect
    return dict(gain=gains,selected=len(vals),up=sum(v>0 for v in vals),
                down=sum(v<0 for v in vals),mean=statistics.mean(vals))

def candidates():
    for mode in ('majority','selective'):
        # Very short, interpretable rule, no learned labels.
        for min_n in (0,100,300,600):
          for min_density in (0.,3.,5.,8.):
            for max_minor in (.22,.30,.38,.50):
              for min_long in (0.,.10,.30):
                yield (mode,min_n,2000000,min_density,1e20,
                       0.,max_minor,min_long,1.)

def train():
    OUT.mkdir(parents=True,exist_ok=True)
    corpus=load_train()
    random.Random(20261031011).shuffle(corpus)
    measured=[]
    for i,x in enumerate(corpus):
        fx=features(x['path'])
        times={m:[] for m in MODES}
        for rep in range(RUNS):
            rotation=(i+rep)%3
            methods=MODES[rotation:]+MODES[:rotation]
            for m in methods:times[m].append(invoke(x['path'],m))
        reference=times['base'][0]['status']
        for m in MODES:
            outcomes={t['status'] for t in times[m] if t['status'] in ('SAT','UNSAT')}
            if reference in ('SAT','UNSAT'):assert not outcomes or outcomes=={reference}
        ms={}
        for arm,key in (('phase-majority','majority'),('phase-selective','selective')):
            ms[key]=statistics.mean(utility(a,b) for a,b in zip(times['base'],times[arm]))
        measured.append(dict(id=x['id'],group=x['group'],sha=x['sha'],
                             **fx,gain_majority=ms['majority'],gain_selective=ms['selective'],
                             base_completed=sum(t['status'] in ('SAT','UNSAT') for t in times['base']),
                             majority_completed=sum(t['status'] in ('SAT','UNSAT') for t in times['phase-majority']),
                             selective_completed=sum(t['status'] in ('SAT','UNSAT') for t in times['phase-selective'])))
        if (i+1)%10==0:print(f'TRAIN {i+1}/80',flush=True)
    save_csv(OUT/'training_measurements.csv',measured)
    # Deterministic split, stratified by source family, all still TRAIN.
    grouped={}
    for x in measured:grouped.setdefault(x['group'],[]).append(x)
    tune=[];val=[]
    for group,values in grouped.items():
        r=random.Random(20261031012+len(group));r.shuffle(values)
        count=max(2,len(values)//4)
        val.extend(values[:count]);tune.extend(values[count:])
    assert len(val)>=16 and len(tune)>=50
    fit=[]
    for rule in candidates():
        s=score_rule(tune,rule)
        if s['selected']<6:continue
        # Require at least one-third of selected have positive benefit,
        # and conservative 1ms average cost reserve.
        if s['up']<max(2,s['selected']//3):continue
        fit.append((s['gain']-1.0,rule,s))
    fit.sort(key=lambda x:x[0],reverse=True)
    best=fit[0] if fit else (-float('inf'),None,None)
    validation=score_rule(val,best[1]) if best[1] else dict(gain=0.,selected=0,up=0,down=0)
    # Safe choice: refuse to enable without adequate validation coverage,
    # positive average net gain, and no repeated timeout regressions.
    def completion_loss(subset,rule):
        return sum(max(0,r['base_completed']-r[rule[0]+'_completed'])
                   for r in subset if matching(r,rule))
    enabled=bool(best[1] and best[0]>1. and validation['selected']>=3
         and validation['gain']>1. and completion_loss(val,best[1])==0)
    chosen=best[1] if enabled else ('base',0,2000000,0.,1e20,0.,1.,0.,1.)
    text_policy='DRNAS_V100_POLICY %s %d %d %.6f %.6f %.6f %.6f %.6f %.6f\n'%(
        chosen[0],chosen[1],chosen[2],chosen[3],chosen[4],
        chosen[5],chosen[6],chosen[7],chosen[8])
    (OUT/'frozen_policy.txt').write_text(text_policy)
    decision=dict(version='v1.0',enabled=enabled,
        policy_fields=['engine','min_n','max_n','min_density','max_density',
                       'min_minority','max_minority','min_long','max_long'],
        chosen=list(chosen),validation=validation,
        tune_examples=len(tune),validation_examples=len(val),
        total_training_examples=len(measured),
        tuning_score=best[0] if best[1] else None,
        tuning_stats=best[2],
        policy_line=text_policy.strip(),
        no_holdout_access=True,
        objective='capped mean casewise paired gain, +/−250ms; validation gate; do not worsen completion',
        source_note='80 previously tested third-party files, 60 old external +20 v091')
    (OUT/'frozen_decision.json').write_text(json.dumps(decision,indent=2))
    print('FROZEN BEFORE UNSEEN TEST:',json.dumps(decision),flush=True)

if __name__=='__main__':train()
