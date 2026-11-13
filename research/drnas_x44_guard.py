#!/usr/bin/env python3
"""DRNAS X4.4: family-balanced, source-weighted away-risk predictor with abstention.

Offline prediction BEFORE each observed CDCL action. All oracle labels arrive
only AFTER the native solver completes, and are used only in training/validation.
The native solver never acts on this model. Out-of-distribution states abstain.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import math
import random
import statistics

CLASSES=("away","toward")
STRUCTURAL=(0,1,2,3,4,9,10,11,12,15,16,17)
def sigmoid(x):
    if x<0:return math.exp(x)/(1+math.exp(x))
    return 1/(1+math.exp(-x))

def percentile(vals,frac):
    a=sorted(vals)
    if not a:return 0.0
    return a[min(len(a)-1,max(0,int(frac*(len(a)-1))))]

def fit(rows,epochs=65,ridge=.07):
    data=[x for x in rows if x["label"] in CLASSES]
    if not data:raise ValueError("X44 no non-flat training examples")
    groups=defaultdict(list);fam_sources=defaultdict(set)
    for row in data:
        groups[row["source_sha"]].append(row)
        fam_sources[row["family"]].add(row["source_sha"])
    n=len(data[0]["features"])
    if any(len(r["features"])!=n for r in data):
        raise ValueError("feature vector schema inconsistent")
    means=[statistics.mean(x["features"][k] for x in data) for k in range(n)]
    scales=[max(.12,statistics.pstdev(x["features"][k] for x in data)) for k in range(n)]
    transformed=[[1.]+[max(-5.,min(5.,(v-u)/s))
                    for v,u,s in zip(row["features"],means,scales)] for row in data]
    weights=[]
    for row in data:
        weights.append(1/(len(fam_sources[row["family"]])*len(groups[row["source_sha"]])))
    positive=sum(w for w,r in zip(weights,data) if r["label"]=="away")
    negative=sum(w for w,r in zip(weights,data) if r["label"]=="toward")
    if not positive or not negative:raise ValueError("need two classes")
    weights=[w/(2*(positive if r["label"]=="away" else negative))
             for w,r in zip(weights,data)]
    weightsum=sum(weights)
    coef=[0.]*(n+1)
    for epoch in range(epochs):
        grad=[0.]*(n+1)
        for x,row,weight in zip(transformed,data,weights):
            p=sigmoid(sum(w*v for w,v in zip(coef,x)))
            delta=(p-int(row["label"]=="away"))*weight/weightsum
            for j,v in enumerate(x):grad[j]+=delta*v
        learning=.6/(1+.04*epoch)
        for j in range(len(coef)):
            coef[j]-=learning*(grad[j]+(ridge*coef[j] if j else 0))
    def ood(x):
        return statistics.mean(min(10.,abs((x[k]-means[k])/scales[k]))
                               for k in STRUCTURAL)
    score_limit=max(1.6,percentile([ood(r["features"]) for r in data],.985))
    model={"name":"DRNAS_X44_AWAY_GUARD_V1",
        "feature_count":n,"mean":means,"scale":scales,"coefficients":coef,
        "ood_threshold":score_limit,
        "threshold":.5,"margin":.075,
        "training_sources":len(groups),"training_families":sorted(fam_sources),
        "training_nonflat_events":len(data),"training_class_support":dict(Counter(r["label"] for r in data)),
        "epochs":epochs,"ridge":ridge,
        "no_active_solver_control":True,
        "independent_source_weighting":True,
        "training_families_balanced":True}
    return model

def risk(model,features):
    if len(features)!=model["feature_count"]:
        raise ValueError("incorrect X44 feature vector length")
    x=[1.]+[max(-5.,min(5.,(v-u)/s))
             for v,u,s in zip(features,model["mean"],model["scale"])]
    return sigmoid(sum(a*b for a,b in zip(model["coefficients"],x)))

def ood_score(model,features):
    return statistics.mean(min(10.,abs((features[k]-model["mean"][k])/model["scale"][k]))
                           for k in STRUCTURAL)

def predict(model,features):
    p=risk(model,features)
    score=ood_score(model,features)
    if score>model["ood_threshold"]:
        return "abstain_ood",p,score
    if abs(p-model["threshold"])<model["margin"]:
        return "abstain_uncertain",p,score
    return ("away" if p>=model["threshold"] else "toward"),p,score

def assess(model,rows,with_group=False):
    data=[r for r in rows if r["label"] in CLASSES]
    if not data:
        return {"status":"no SAT non-flat direction targets"}
    per_source=defaultdict(list)
    counts=Counter()
    class_n=Counter()
    total_predictions=0
    risk_rows=[]
    for row in data:
        action,p,score=predict(model,row["features"])
        truth=row["label"]
        per_source[row["source_sha"]].append((action,p,truth,row["family"]))
        counts[action]+=1
        class_n[truth]+=1
        risk_rows.append((p,int(truth=="away")))
        if action in CLASSES:
            total_predictions+=1
    accepted=[(act,truth) for group in per_source.values() for act,_,truth,_ in group if act in CLASSES]
    support=Counter(y for _,y in accepted)
    hits=Counter(y for pred,y in accepted if pred==y)
    abstained=len(data)-len(accepted)
    tpr_away=hits["away"]/support["away"] if support["away"] else None
    tpr_toward=hits["toward"]/support["toward"] if support["toward"] else None
    balanced=(tpr_away+tpr_toward)/2 if tpr_away is not None and tpr_toward is not None else None
    accepted_accuracy=sum(p==y for p,y in accepted)/len(accepted) if accepted else None
    majority_acc=(support["toward"]/len(accepted)) if accepted else None
    precision_away=(hits["away"]/counts["away"]) if counts["away"] else None
    # AUC of ranked away score, computed without scipy and with ties.
    risk_rows.sort(key=lambda z:z[0])
    npos=sum(y for _,y in risk_rows)
    nneg=len(risk_rows)-npos
    auc=None
    if npos and nneg:
        rank_sum=0.;j=0
        while j<len(risk_rows):
            k=j+1
            while k<len(risk_rows) and risk_rows[k][0]==risk_rows[j][0]:k+=1
            rank_sum+=(j+1+k)*.5*sum(z[1] for z in risk_rows[j:k])
            j=k
        auc=(rank_sum-npos*(npos+1)/2)/(npos*nneg)
    answer={"original_sources":len(per_source),"nonflat_events":len(data),
        "away_targets":class_n["away"],"toward_targets":class_n["toward"],
        "coverage":round(len(accepted)/len(data),6),
        "abstain_ood":counts["abstain_ood"],
        "abstain_uncertain":counts["abstain_uncertain"],
        "predicted_away":counts["away"],"predicted_toward":counts["toward"],
        "accepted_away_targets":support["away"],"accepted_toward_targets":support["toward"],
        "away_recall_among_accepted":round(tpr_away,6) if tpr_away is not None else None,
        "toward_recall_among_accepted":round(tpr_toward,6) if tpr_toward is not None else None,
        "accepted_balanced_accuracy":round(balanced,6) if balanced is not None else None,
        "accepted_accuracy":round(accepted_accuracy,6) if accepted_accuracy is not None else None,
        "accepted_always_toward_accuracy":round(majority_acc,6) if majority_acc is not None else None,
        "away_precision_among_emitted":round(precision_away,6) if precision_away is not None else None,
        "away_auc_all_nonflat":round(auc,6) if auc is not None else None,
        "abstention_not_solver_action":True}
    if with_group:answer["_sources"]=per_source
    return answer

def tune_validation(model,validation):
    # Hyperparameters calibrated ONLY on distinct validation-family CNFs.
    # Strong abstention is penalized by the objective; reject 100% abstain.
    best=None
    candidates=[]
    for threshold in (.35,.4,.45,.5,.55,.6,.65):
        for margin in (.04,.08,.12):
            m={**model,"threshold":threshold,"margin":margin}
            score=assess(m,validation)
            ba=score.get("accepted_balanced_accuracy")
            coverage=score.get("coverage",0.0)
            away=score.get("predicted_away",0)
            toward=score.get("predicted_toward",0)
            eligible=(ba is not None and coverage>=.15 and away>=10 and toward>=10
                      and score["accepted_away_targets"]>=10 and score["accepted_toward_targets"]>=10)
            # Encourage useful, correctly weighted abstention; do not make
            # improvement artificially large by emitting one easy prediction.
            objective=(ba-.5)*math.sqrt(coverage) if eligible else -1.
            candidates.append({"threshold":threshold,"margin":margin,
                "balanced_accuracy":ba,"coverage":coverage,
                "objective":objective,"eligible":eligible})
            if eligible and (best is None or objective>best[0]):
                best=(objective,threshold,margin)
    if best is None:
        result={**model,"threshold":.5,"margin":.25,"validation_eligible":False,
            "validation_calibrated":True}
    else:
        result={**model,"threshold":best[1],"margin":best[2],
            "validation_eligible":True,"validation_calibrated":True}
    return result,{"chosen_threshold":result["threshold"],"chosen_margin":result["margin"],
                   "eligible":result["validation_eligible"],
                   "validation_summary":assess(result,validation),"candidates":candidates}

def source_cluster_ci(model,rows,draws=2400,seed=20261113):
    # Precision of accepted balanced direction compared to 50%.
    result=assess(model,rows,with_group=True)
    groups=result.pop("_sources",{})
    keys=sorted(groups)
    if len(keys)<3:return {"status":"insufficient original sources"}
    def stats_for(sampled):
        counts=Counter();correct=Counter()
        for k in sampled:
            for act,_,truth,_ in groups[k]:
                if act in CLASSES:
                    counts[truth]+=1;correct[truth]+=int(act==truth)
        if not counts["away"] or not counts["toward"]:return None
        return (correct["away"]/counts["away"]+correct["toward"]/counts["toward"])/2
    rng=random.Random(seed)
    estimates=[]
    for _ in range(draws):
        sample=[keys[rng.randrange(len(keys))] for _ in keys]
        val=stats_for(sample)
        if val is not None:estimates.append(val)
    estimates.sort()
    if not estimates:return {"status":"no bootstrap strata with both directions"}
    return {"balanced_acc_95pct":[round(estimates[int(.025*(len(estimates)-1))],6),
                                  round(estimates[int(.975*(len(estimates)-1))],6)],
        "source_units":len(keys),"replays_are_correlated":True,
        "selection_calibrated_on_other_families_only":True}
