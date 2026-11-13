#!/usr/bin/env python3
"""X4.3 fixed-feature softmax predictor: pre-action features only, offline training.

The native solver never reads these predictions; this module cannot add clauses
or influence SAT/UNSAT. Only retrospective exhaustive-oracle labels train it.
One original CNF is the independent statistical unit (replays are correlated).
"""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib
import json
import math
import random
import statistics

CLASSES=("away","flat","toward")
NCLASS=3
def probabilities(logits):
    shift=max(logits)
    exps=[math.exp(max(-60.0, x-shift)) for x in logits]
    total=sum(exps)
    return [v/total for v in exps]

def group_data(records):
    by_source=defaultdict(list)
    for row in records:
        assert row["label"] in CLASSES
        by_source[row["source_sha"]].append(row)
    return by_source

def fit(records,epochs=90,ridge=0.014):
    if not records:
        raise ValueError("no training observations")
    lengths={len(r["features"]) for r in records}
    if len(lengths)!=1:
        raise ValueError("inconsistent pre-action feature vector length")
    n=next(iter(lengths))
    groups=group_data(records)
    counts=Counter(r["label"] for r in records)
    # Estimate scaler on TRAINING records only. Clip outliers to limit influence.
    means=[statistics.mean(r["features"][j] for r in records) for j in range(n)]
    stds=[max(0.12,statistics.pstdev(r["features"][j] for r in records)) for j in range(n)]
    xs=[[1.0]+[max(-5.,min(5.,(v-a)/s))
                 for v,a,s in zip(r["features"],means,stds)] for r in records]
    ys=[CLASSES.index(r["label"]) for r in records]
    weights_by_sample=[1.0/len(groups[r["source_sha"]]) for r in records]
    sum_w=sum(weights_by_sample)
    w=[[0.0]*(n+1) for _ in CLASSES]
    for epoch in range(epochs):
        lr=0.85/(1+0.06*epoch)
        grads=[[0.]*(n+1) for _ in CLASSES]
        for x,y,importance in zip(xs,ys,weights_by_sample):
            p=probabilities([sum(a*b for a,b in zip(row,x)) for row in w])
            for k in range(NCLASS):
                error=(p[k]-int(k==y))*importance/sum_w
                for j,val in enumerate(x):
                    grads[k][j]+=error*val
        for k in range(NCLASS):
            for j in range(n+1):
                penalty=ridge*w[k][j] if j else 0.0
                w[k][j]-=lr*(grads[k][j]+penalty)
    # Dirichlet-smoothed reference predictor is fitted solely to TRAIN.
    base=[(counts[name]+1)/(len(records)+NCLASS) for name in CLASSES]
    return {"version":"X43_SOFTMAX_PREACTION_V1","feature_count":n,
            "feature_mean":means,"feature_scale":stds,"coefficients":w,
            "baseline_probabilities":base,"trained_source_count":len(groups),
            "trained_events":len(records),"learning_algorithm":"fixed 90-epoch ridge softmax",
            "model_trained_on_outcome":"exhaustively checked SAT search steps only",
            "trained_source_sha256_digest":hashlib.sha256(
                "\n".join(sorted(groups)).encode()).hexdigest()}

def infer(model,features):
    if len(features)!=model["feature_count"]:
        raise ValueError("predictor received unexpected feature count")
    x=[1.0]+[max(-5.,min(5.,(v-a)/s))
               for v,a,s in zip(features,model["feature_mean"],model["feature_scale"])]
    return probabilities([sum(a*b for a,b in zip(row,x))
                          for row in model["coefficients"]])

def evaluate(model,records):
    if not records:
        return {"status":"no available pre-action-labelled transitions"}
    by_source=group_data(records)
    correct=0;naive_correct=0;total=0
    per_source=[]
    confusion={y:{guess:0 for guess in CLASSES} for y in CLASSES}
    class_totals=Counter()
    class_hits=Counter()
    nonflat_total=0;nonflat_hit=0;nonflat_naive_hit=0
    base=model["baseline_probabilities"]
    naive_idx=max(range(NCLASS),key=lambda j:base[j])
    for source,samples in sorted(by_source.items()):
        ll_model=0.0;ll_baseline=0.0
        for row in samples:
            y=CLASSES.index(row["label"])
            pred=infer(model,row["features"])
            guess=max(range(NCLASS),key=lambda j:pred[j])
            ll_model-=math.log(max(1e-12,pred[y]))
            ll_baseline-=math.log(max(1e-12,base[y]))
            total+=1
            correct+=int(guess==y)
            naive_correct+=int(naive_idx==y)
            class_totals[row["label"]]+=1
            class_hits[row["label"]]+=int(guess==y)
            confusion[row["label"]][CLASSES[guess]]+=1
            if row["label"]!="flat":
                nonflat_total+=1
                sg=2 if pred[2]>=pred[0] else 0
                sb=2 if base[2]>=base[0] else 0
                nonflat_hit+=int(sg==y)
                nonflat_naive_hit+=int(sb==y)
        per_source.append({"source_sha":source,"family":samples[0]["family"],
            "n":len(samples),"model_logloss":ll_model/len(samples),
            "constant_logloss":ll_baseline/len(samples)})
    result={"source_count":len(per_source),"event_count":total,
            "model_logloss_formula_mean":statistics.mean(x["model_logloss"] for x in per_source),
            "constant_logloss_formula_mean":statistics.mean(x["constant_logloss"] for x in per_source),
            "logloss_improvement":statistics.mean(x["constant_logloss"]-x["model_logloss"] for x in per_source),
            "model_accuracy":correct/total,"constant_accuracy":naive_correct/total,
            "nonflat_events":nonflat_total,
            "nonflat_model_sign_accuracy":nonflat_hit/nonflat_total if nonflat_total else None,
            "nonflat_always_majority_sign_accuracy":nonflat_naive_hit/nonflat_total if nonflat_total else None,
            "class_support":dict(class_totals),"confusion_actual_to_predicted":confusion,
            "source_contributions":per_source}
    return result

def cluster_confidence(evaluation,draws=2500,seed=20261113):
    items=evaluation.get("source_contributions",[])
    if not items:return {"status":"no source observations"}
    rng=random.Random(seed)
    delta=[x["constant_logloss"]-x["model_logloss"] for x in items]
    res=[]
    for _ in range(draws):
        res.append(sum(delta[rng.randrange(len(delta))] for _ in delta)/len(delta))
    res.sort()
    return {"formula_cluster_bootstrap95_logloss_improvement":[res[round(.025*(draws-1))],
                                                                res[round(.975*(draws-1))]],
            "sample_unit":"original CNF, not decision and not replay",
            "test_sources":len(items)}

def summarized(result):
    return {key:val for key,val in result.items() if key!="source_contributions"}
