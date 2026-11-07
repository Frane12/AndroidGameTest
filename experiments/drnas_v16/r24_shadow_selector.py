#!/usr/bin/env python3
"""Freeze a small diagnostic selector on R24 dev; evaluate fresh paired runs.

Shadow replay is not an in-process policy and excludes extraction overhead.
"""
import argparse, hashlib, json, math, random, statistics
from pathlib import Path

MODEL=Path('drnas-r24-pilot/frozen_shadow_model.json')

def feature(row):
    t=next((x for x in row['traces'] if x['mark']==1024 and 1024<=x['conflict']<2048),None)
    if not t or t['reason_overflow']:
        return None
    return [t['revisits']/max(1,t['calls']), t['crosslevel']/max(1,t['calls']),
            t['reason_reused']/max(1,t['long']),t['binary']/max(1,t['pivots']),
            t['mature_low']/max(1,t['antecedent'])]

def assemble(path):
    rows=[json.loads(x) for x in Path(path).read_text().splitlines()]
    cases=[]
    for name in sorted({x['formula'] for x in rows}):
        r=[x for x in rows if x['formula']==name]
        if len(r)!=4 or {x['mode'] for x in r}!={'monitor','forced'}:
            raise RuntimeError('incomplete paired records '+name)
        m=[x for x in r if x['mode']=='monitor']; f=[x for x in r if x['mode']=='forced']
        if len(m)!=2 or len(f)!=2:raise RuntimeError('invalid repeats')
        a=statistics.median(x['par2'] for x in m);b=statistics.median(x['par2'] for x in f)
        cases.append(dict(formula=name,sha=r[0]['sha256'],family=r[0]['family'],fold=r[0]['fold'],
                    x=feature(next(x for x in m if x['repeat']==0)), monitor=a,forced=b,
                    switch=all(x['switched'] for x in f),gain=(a-b)/a))
    return cases

def train():
    cases=[x for x in assemble('drnas-r24-pilot/measurements.jsonl') if x['fold']=='development']
    model={'version':'R24-shadow-knn3-v1','k':3,'min_wins':2,'mean_gain_min':.05,
           'train_scope':'R24 development only; exploratory',
           'features':['revisit_per_call','crosslevel_per_call','reuse_per_long',
                       'binary_per_pivot','maturelow_per_antecedent'], 'groups':{}}
    for family in ('random3','community3'):
        eligible=[x for x in cases if x['family']==family and x['x'] is not None and x['switch']]
        sd=[max(statistics.pstdev(x['x'][i] for x in eligible),.001) for i in range(5)] if len(eligible)>=3 else []
        model['groups'][family]={'training':eligible,'scale':sd}
    MODEL.write_text(json.dumps(model,sort_keys=True,indent=2)+'\n')
    print('FROZEN_MODEL',hashlib.sha256(MODEL.read_bytes()).hexdigest(),
          {k:len(v['training']) for k,v in model['groups'].items()},flush=True)

def predict(model, x):
    if x['x'] is None:return False,'no_1024_checkpoint'
    group=model['groups'][x['family']];train=group['training'];scale=group['scale']
    if len(train)<model['k']:return False,'insufficient_training'
    def dist(y):return sum(((a-b)/s)**2 for a,b,s in zip(x['x'],y['x'],scale))
    near=sorted(train,key=lambda y:(dist(y),y['sha']))[:model['k']]
    wins=sum(z['gain']>=.05 for z in near)
    safe=all(z['forced']<=2*z['monitor'] for z in near)
    mean=statistics.mean(z['gain'] for z in near)
    return (wins>=2 and safe and mean>=.05),f'wins={wins},safe={safe},mean={mean:.5f}'

def evaluate():
    model=json.loads(MODEL.read_text());cases=assemble('drnas-r24-fresh/measurements.jsonl')
    old=assemble('drnas-r24-pilot/measurements.jsonl')
    if {x['sha'] for x in cases}&{x['sha'] for x in old}:raise RuntimeError('R24 history SHA collision')
    results=[]
    for x in cases:
        choice,reason=predict(model,x)
        x.update(choose_forced=choice,reason=reason,shadow=x['forced'] if choice else x['monitor'])
        results.append(x)
    summary={}
    for family in ('random3','community3'):
        group=[x for x in results if x['family']==family]
        base=sum(x['monitor'] for x in group);shadow=sum(x['shadow'] for x in group)
        summary[family]={'formulas':len(group),'choices':sum(x['choose_forced'] for x in group),
            'monitor':base,'shadow':shadow,'shadow_gain_pct':100*(base-shadow)/base,
            'forced_regressions_gt2x':sum(x['forced']>2*x['monitor'] for x in group),
            'shadow_regressions_gt2x':sum(x['shadow']>2*x['monitor'] for x in group),
            'selected_wins':sum(x['choose_forced'] and x['forced']<x['monitor'] for x in group),
            'selected_losses':sum(x['choose_forced'] and x['forced']>x['monitor'] for x in group),
            'no_trace':sum(x['x'] is None for x in group)}
    report={'model_sha256':hashlib.sha256(MODEL.read_bytes()).hexdigest(),
            'scope':'fresh SHA-distinct from local R24 pilot, offline paired shadow replay; no online action or overhead',
            'summary':summary,'cases':results}
    Path('drnas-r24-fresh/shadow_results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R24_FRESH_SHADOW',json.dumps(summary),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['train','evaluate']);a=p.parse_args()
    train() if a.mode=='train' else evaluate()
