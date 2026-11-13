#!/usr/bin/env python3
"""X4.6 counterfactual COST1 learner trained only from matched prefix labels.

Labels: which of two completed, independently certified continuations
caused fewer conflicts after the exact same prefix, not distance-to-SAT.
The training program consumes frozen X46 short-probe records; the live
solver at inference only sees the SHORT probes, never this hindsight label.
Pure stdlib for CI reproducibility. Held-out CNF sources do not select weights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
from collections import Counter,defaultdict

NFEATURES=12
def features(record):
    a,b=record["probe_base"],record["probe_alt"]
    if a is None or b is None:
        raise ValueError("missing costed short-probe features")
    nc,fc=float(a["conflicts"]),float(b["conflicts"])
    nd,fd=float(a["decisions"]),float(b["decisions"])
    np,fp=float(a["propagations"]),float(b["propagations"])
    return [math.log1p(nc),math.log1p(fc),math.log1p(nd),math.log1p(fd),
            math.log1p(np),math.log1p(fp),
            (nc-fc)/(nc+fc+1),(nd-fd)/(nd+fd+1),(np-fp)/(np+fp+1),
            float(a["status"]==10),float(b["status"]==10),
            math.log1p(record["checkpoint"])]

def sigmoid(z):
    z=max(-40.,min(40.,z))
    if z<0:
        x=math.exp(z);return x/(1+x)
    return 1/(1+math.exp(-z))

def extract(trialfile):
    rows=[json.loads(x) for x in Path(trialfile).read_text().splitlines() if x.strip()]
    samples=[]
    all_sources={}
    for row in rows:
        if row["arm"]!="X46_8":continue
        if not row["verified"] or not row["probe_triggered"]:
            continue
        if row["counterfactual_label"] not in ("flip_cheaper","baseline_cheaper","equal_conflicts"):
            raise ValueError("unexpected or unverified full-cost counterfactual label")
        sha=row["sha256"]
        source_id=row["source_id"]
        family=row["family"]
        identity=(source_id,family)
        if sha in all_sources and all_sources[sha]!=identity:
            raise ValueError("source SHA identity changed")
        all_sources[sha]=identity
        samples.append({"source":sha,"family":family,"source_id":source_id,
            "checkpoint":row["checkpoint"],"rep":row["rep"],
            "features":features(row),"label":row["counterfactual_label"],
            "flip_saving":None,"heuristic_recommended":bool(row["recommended_flip"])})
    # The full-counterfactual label in X46 records is based on verified
    # conflict comparison. Grab the actual delta from CORE vs FLIP arms.
    pair_map=defaultdict(dict)
    for row in rows:
        key=(row["sha256"],row["checkpoint"],row["rep"])
        if row["arm"] in ("CORE","FLIP"):
            pair_map[key][row["arm"]]=row
    for item in samples:
        key=(item["source"],item["checkpoint"],item["rep"])
        a=pair_map[key]["CORE"];b=pair_map[key]["FLIP"]
        if not a["verified"] or not b["verified"]:raise ValueError("unverified oracle arms")
        delta=a["continuation_conflicts"]-b["continuation_conflicts"]
        expected="flip_cheaper" if delta>0 else "baseline_cheaper" if delta<0 else "equal_conflicts"
        if item["label"]!=expected:raise ValueError("inconsistent counterfactual cost label")
        item["flip_saving"]=int(delta)
    if not samples:raise RuntimeError("no matched evidence for learning")
    return samples,all_sources

def fit(data,epochs=140,ridge=.06):
    nonflat=[r for r in data if r["label"]!="equal_conflicts"]
    if len({r["source"] for r in nonflat})<15:
        raise RuntimeError("insufficient independent source formulas for cost learner")
    means=[statistics.mean(x["features"][j] for x in nonflat) for j in range(NFEATURES)]
    scales=[max(.09,statistics.pstdev(x["features"][j] for x in nonflat)) for j in range(NFEATURES)]
    sources=Counter(x["source"] for x in nonflat)
    class_mass=Counter()
    weights=[]
    for x in nonflat:
        weight=1/sources[x["source"]]
        weights.append(weight)
        class_mass[x["label"]]+=weight
    weights=[w/(2*class_mass[x["label"]]) for w,x in zip(weights,nonflat)]
    total=sum(weights)
    x_std=[[1.]+[max(-5.,min(5.,(v-u)/s))
               for v,u,s in zip(x["features"],means,scales)] for x in nonflat]
    coef=[0.]*(NFEATURES+1)
    for epoch in range(epochs):
        grad=[0.]*(NFEATURES+1)
        for row,feat,weight in zip(nonflat,x_std,weights):
            y=int(row["label"]=="flip_cheaper")
            p=sigmoid(sum(a*b for a,b in zip(coef,feat)))
            err=weight*(p-y)/total
            for j,val in enumerate(feat):grad[j]+=err*val
        rate=.65/(1+.025*epoch)
        for j in range(len(coef)):
            coef[j]-=rate*(grad[j]+(ridge*coef[j] if j else 0.))
    return {"version":"X46COST1","dimensions":NFEATURES,"means":means,
        "scales":scales,"coefficients":coef[1:],"bias":coef[0],
        "train_nonflat_events":len(nonflat),
        "train_distinct_sources":len(sources),
        "epochs":epochs,"ridge":ridge}

def predict(model,feat):
    z=model["bias"]
    for w,v,mu,scale in zip(model["coefficients"],feat,model["means"],model["scales"]):
        z+=w*max(-5.,min(5.,(v-mu)/scale))
    return sigmoid(z)

def evaluate(model,rows,threshold):
    grouped=defaultdict(list)
    for row in rows:grouped[row["source"]].append(row)
    pos=Counter()
    sum_gain=0;sum_regret=0;deltas=[]
    ll=[]
    all_nonflat=0;class_accuracy=0;heuristic_accuracy=0
    per_family=defaultdict(lambda:{"flips":0,"net_conflict_savings":0,"count":0})
    for sha,samples in grouped.items():
        loss=0;n=0
        for row in samples:
            p=predict(model,row["features"])
            flip=p>threshold
            saving=row["flip_saving"]
            if flip:sum_gain+=saving
            if flip and saving<0:sum_regret+=-saving
            deltas.append(saving if flip else 0)
            per_family[row["family"]]["count"]+=1
            per_family[row["family"]]["net_conflict_savings"]+=saving if flip else 0
            per_family[row["family"]]["flips"]+=int(flip)
            pos["learned_flip"]+=int(flip)
            pos["static_heuristic_flip"]+=int(row["heuristic_recommended"])
            if saving!=0:
                y=int(saving>0)
                loss-=math.log(max(1e-10,p if y else 1-p))
                n+=1;all_nonflat+=1
                class_accuracy+=int(flip==bool(y))
                heuristic_accuracy+=int(row["heuristic_recommended"]==bool(y))
        if n:ll.append(loss/n)
    return {"original_sources":len(grouped),"matched_rows":len(rows),
        "nonflat_rows":all_nonflat,
        "mean_source_logloss":round(statistics.mean(ll),6) if ll else None,
        "accuracy_on_nonflat":round(class_accuracy/all_nonflat,6) if all_nonflat else None,
        "fixed_heuristic_accuracy":round(heuristic_accuracy/all_nonflat,6) if all_nonflat else None,
        "recommended_flips":pos["learned_flip"],
        "fixed_heuristic_flips":pos["static_heuristic_flip"],
        "net_full_continuation_conflicts_saved_vs_CORE_hindsight":sum_gain,
        "negative_regret_from_wrong_flips":sum_regret,
        "by_family":dict(per_family),
        "NOTE":"offline replay using already-completed full paths; DOES NOT include live probe runtime and is not evidence of online speedup"}

def train(split,model_path,report_path):
    data,source_ids=extract(split)
    originals=sorted(source_ids)
    training_sha={sha for sha in originals if source_ids[sha][0]%4!=0}
    validation_sha=set(originals)-training_sha
    if not training_sha or not validation_sha:raise RuntimeError("empty formula-level validation")
    train=[row for row in data if row["source"] in training_sha]
    val=[row for row in data if row["source"] in validation_sha]
    model=fit(train)
    thresholds=(.50,.55,.60,.65,.70,.75,.80,.85,.9)
    scores=[(t,evaluate(model,val,t)) for t in thresholds]
    # Prefer avoiding catastrophic full-cost regressions in validation.
    # The threshold is LOCKED before any new held-out CNF runs.
    scores.sort(key=lambda z:(-z[1]["net_full_continuation_conflicts_saved_vs_CORE_hindsight"],
                                z[1]["negative_regret_from_wrong_flips"],-z[0]))
    best_t,best_report=scores[0]
    model["threshold"]=best_t
    path=Path(model_path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w") as f:
        f.write(f"X46COST1 {NFEATURES}\n")
        f.write(f"{best_t:.17g} {model['bias']:.17g}\n")
        for mu,sc,w in zip(model["means"],model["scales"],model["coefficients"]):
            f.write(f"{mu:.17g} {sc:.17g} {w:.17g}\n")
    jsonmodel=path.with_suffix(".json")
    jsonmodel.write_text(json.dumps(model,indent=2,sort_keys=True)+"\n")
    report={"protocol":"source-disjoint X46 matched-cost supervised training",
        "train_sources":len(training_sha),"validation_sources":len(validation_sha),
        "train_record_count":len(train),"validation_record_count":len(val),
        "train_source_hashes_sha256":hashlib.sha256("\n".join(sorted(training_sha)).encode()).hexdigest(),
        "validation_source_hashes_sha256":hashlib.sha256("\n".join(sorted(validation_sha)).encode()).hexdigest(),
        "frozen_file_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "threshold_selected_before_holdout":best_t,
        "training_score":evaluate(model,train,best_t),
        "validation_score":best_report,
        "all_thresholds_validation":{str(t):report for t,report in scores},
        "source_index_fraction_train":"id mod 4 != 0",
        "model_only_reads_before_action_short_probe_signals":True,
        "labels_from_independently_verified_full_continuation":True,
        "heldout_formula_outcomes_not_seen":True}
    Path(report_path).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("X46_COST_TRAIN_FINAL "+json.dumps({"train_sources":len(training_sha),
        "validation_sources":len(validation_sha),"threshold":best_t,
        "validation_accuracy":best_report["accuracy_on_nonflat"],
        "validation_static_accuracy":best_report["fixed_heuristic_accuracy"],
        "validation_net_conflicts_saved":best_report["net_full_continuation_conflicts_saved_vs_CORE_hindsight"],
        "model_sha":report["frozen_file_sha256"]},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trials",type=Path,required=True)
    p.add_argument("--model",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    train(a.trials,a.model,a.report)

if __name__=="__main__":main()
