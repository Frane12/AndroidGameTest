#!/usr/bin/env python3
"""Post-hoc score discrimination and perfect-information work headroom.

Read-only analysis of frozen evidence. Never changes the model or threshold.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import drnas_x45a as X


def auc(labels,scores):
    y=np.asarray(labels,bool);s=np.asarray(scores,float)
    p=s[y];n=s[~y]
    if not len(p) or not len(n):return None
    return float(np.mean((p[:,None]>n).astype(float)+.5*(p[:,None]==n)))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('directory',type=Path);args=ap.parse_args()
    root=args.directory;model=json.loads((root/'frozen_model.json').read_text());out={}
    for split in ('train','validation','holdout'):
        rows=[json.loads(line) for line in (root/f'{split}_pairs.jsonl').read_text().splitlines()]
        valid=[r for r in rows if r['label'] is not None and abs(r['label'])>.10]
        entry={}
        for family in ['ALL']+sorted(set(r['family'] for r in rows)):
            rr=[r for r in valid if family=='ALL' or r['family']==family]
            y=[r['label']>0 for r in rr]
            scores=[X.predict(model,r['features'])[0] for r in rr]
            means=[float(np.mean(np.array(model['weights'])@np.append(np.clip(
                (np.array(r['features'])-model['centers'])/model['scales'],-8,8),1))) for r in rr]
            entry[family]=dict(n=len(rr),score_auc=auc(y,scores),ensemble_mean_auc=auc(y,means),
                              ood=sum(X.predict(model,r['features'])[1] for r in rr))
        if split=='holdout':
            complete=[r for r in rows if r['label'] is not None]
            base=sum(r['base']['propagations'] for r in complete)
            perfect=sum(min(r['base']['propagations'],r['flip']['propagations']) for r in complete)
            entry['oracle_headroom_propagation_reduction_pct']=100*(1-perfect/base)
            y=np.array([r['label']>0 for r in valid]);s=np.array([X.predict(model,r['features'])[0] for r in valid])
            rng=np.random.default_rng(451315);values=[]
            for _ in range(6000):
                ii=rng.integers(len(y),size=len(y));v=auc(y[ii],s[ii])
                if v is not None:values.append(v)
            entry['ALL']['score_auc_formula95']=np.quantile(values,[.025,.975]).tolist() if values else None
        out[split]=entry
    result=dict(no_policy_reselection=True,metrics_are_exploratory=True,
                perfect_information_headroom_is_not_an_achieved_speedup=True,results=out)
    X.save(root/'posthoc_diagnostic.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
