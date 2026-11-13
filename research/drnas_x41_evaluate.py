#!/usr/bin/env python3
"""X4.2 *offline-only* cost baseline: no branch policy feedback and no holdout training.

Causal effects of alternative decisions CANNOT be inferred from these records.
Only SAT with an independently checked original witness supplies a duration label.
Each formula contributes at most ONE supervised example to prevent transition
count from creating artificial precision or formula leakage.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import math
from statistics import median

FEATURES=('assigned_fraction','depth_fraction','open_long_fraction',
          'open_binary_fraction','open_unit_fraction','conflict_ratio',
          'learned_ratio','elapsed_log_ms')

def features(x):
    a=x['before'];n=max(1,x['nvars']);z=max(1,a['sampled_total'])
    return [a['assigned']/n,a['level']/n,a['sample_unresolved_long']/z,
            a['sample_open_binary']/z,a['sample_open_unit']/z,
            a['conflicts']/(1+a['decisions']),a['learnt']/(1+a['decisions']),
            math.log1p(max(0,a['elapsed_s'])*1000)]

def load(path):
    chosen={}
    counts=Counter()
    for line in Path(path).open():
        x=json.loads(line);counts[x['split']]+=1
        if x['label_remaining_wall_s'] is None:continue
        if x['result']!='SAT_VERIFIED':raise RuntimeError('unverified duration target')
        sha=x['sha256']
        # Chronological earliest trace; do not choose the best/shortest future.
        if sha not in chosen or x['before']['decisions']<chosen[sha]['before']['decisions']:
            chosen[sha]=x
    examples=defaultdict(list);families=defaultdict(set)
    for x in chosen.values():
        examples[x['split']].append((features(x),x['label_remaining_wall_s'],x['sha256'],x['family']))
        families[x['split']].add(x['family'])
    for split in ('train','validation','holdout'):
        for other in ('train','validation','holdout'):
            if split!=other and families[split]&families[other]:raise RuntimeError('family split leak')
    return examples, counts, families

def score(train,test):
    if not test:return {'n_formulas':0,'status':'no verified SAT labels'}
    trainfeatures=[x for x,_,_,_ in train]
    location=[median(vec[i] for vec in trainfeatures) for i in range(len(FEATURES))]
    scales=[]
    for i in range(len(FEATURES)):
        vals=sorted(vec[i] for vec in trainfeatures)
        q1,q3=vals[len(vals)//4],vals[(3*len(vals))//4]
        scales.append(max(.05,q3-q1))
    baseline=median(y for _,y,_,_ in train)
    def predict(vec):
        ds=[]
        for x,y,sha,fam in train:
            dist=sum(((a-b)/sc)**2 for a,b,sc in zip(vec,x,scales))
            ds.append((dist,math.log1p(y*1000)))
        ds.sort(key=lambda t:t[0])
        # Fixed k=9; no optimization/tuning on validation or holdout.
        return math.expm1(median(t[1] for t in ds[:min(9,len(ds))]))/1000
    base_errors=[]; model_errors=[]
    for v,y,_,_ in test:
        base_errors.append(abs(baseline-y)*1000)
        model_errors.append(abs(predict(v)-y)*1000)
    return {'n_formulas':len(test),'baseline_mae_ms':round(sum(base_errors)/len(base_errors),4),
            'fixed_knn9_mae_ms':round(sum(model_errors)/len(model_errors),4),
            'knn9_better_than_constant_on_this_split':sum(model_errors)<sum(base_errors),
            'status':'diagnostic-only; not policy evaluation'}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--transitions',default='drnas_x41_results/synthetic_controls/transitions.jsonl')
    p.add_argument('--out',default='drnas_x41_results/synthetic_controls/offline_eval.json')
    args=p.parse_args()
    examples,counts,families=load(args.transitions)
    train=examples['train']
    if len(train)<20:out={'status':'insufficient independently verified SAT train targets','train_formulas':len(train)}
    else:
        out={'status':'offline shadow diagnostic; no live branching',
             'train_formulas':len(train),'feature_names':FEATURES,
             'label_definition':'same-policy retrospectively measured remaining SAT wall time, verified original-CNF witness',
             'train_families':sorted(families['train']),
             'validation_families':sorted(families['validation']),
             'holdout_families':sorted(families['holdout']),
             'validation':score(train,examples['validation']),
             'holdout':score(train,examples['holdout']),
             'disclaimer':'Neither estimator measures SAT distance or alternative-decision causal reward; censored/UNSAT excluded.'}
    Path(args.out).parent.mkdir(parents=True,exist_ok=True)
    Path(args.out).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('X41_OFFLINE_EVALUATION '+json.dumps(out,sort_keys=True),flush=True)

if __name__=='__main__':main()