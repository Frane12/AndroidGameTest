#!/usr/bin/env python3
"""X4.3 audit: why did validation degrade when adding third training cohort?

Reproduce the original source cohorts and exact oracle labels, compare training
distributions, in-sample and independent-family scores, learning epoch/ridge
ablations and away-recall. The 64-source old holdout is NEVER used here.
No active branch policy; no retrospective labels enter inference features.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
from collections import defaultdict,Counter
import statistics
import tempfile

import drnas_x42_convergence_cycles as X42
import drnas_x43_premodel as MODEL
import drnas_x43_preaction_bench as X43

def emit(tag,row):
    print(tag+" "+json.dumps(row,sort_keys=True,separators=(",",":")),flush=True)

def distribution(data):
    if not data:return {}
    raw=Counter(x["label"] for x in data)
    per_source=defaultdict(list)
    per_family=defaultdict(list)
    for x in data:
        per_source[x["source_sha"]].append(x)
        per_family[x["family"]].append(x)
    formula_weight=Counter()
    for rows in per_source.values():
        for x in rows:formula_weight[x["label"]]+=1/len(rows)
    n=len(per_source)
    return {"distinct_sources":n,"rows":len(data),"count_by_class":dict(raw),
        "row_fraction":{c:round(raw[c]/len(data),5) for c in MODEL.CLASSES},
        "formula_weighted_class_fraction":{c:round(formula_weight[c]/n,5) for c in MODEL.CLASSES},
        "families":{fam:{"sources":len({x["source_sha"] for x in rows}),
                         "rows":len(rows),"classes":dict(Counter(x["label"] for x in rows))}
                    for fam,rows in sorted(per_family.items())}}

def away_auc(model,records):
    # Tie-safe ROC-AUC, for using class likelihood as a RANKING, not a label.
    ranked=sorted((MODEL.infer(model,row["features"])[0],
                   int(row["label"]=="away")) for row in records)
    n_pos=sum(y for _,y in ranked);n_neg=len(ranked)-n_pos
    if n_pos==0 or n_neg==0:return None
    rank=1;ranks_pos=0.
    while rank<=len(ranked):
        end=rank
        while end<len(ranked) and ranked[end][0]==ranked[rank-1][0]:end+=1
        average=(rank+end)/2
        ranks_pos+=average*sum(y for _,y in ranked[rank-1:end])
        rank=end+1
    return round((ranks_pos-n_pos*(n_pos+1)/2)/(n_pos*n_neg),6)

def sign_scores(model,records,threshold):
    cnt=Counter();hit=Counter()
    per_source=defaultdict(list)
    for x in records:
        if x["label"]=="flat":continue
        p=MODEL.infer(model,x["features"])
        ratio=p[0]/max(1e-9,p[0]+p[2])
        predicted="away" if ratio>=threshold else "toward"
        cnt[x["label"]]+=1
        if predicted==x["label"]:hit[x["label"]]+=1
        per_source[x["source_sha"]].append(int(predicted==x["label"]))
    if not cnt["away"] or not cnt["toward"]:
        return {}
    balanced=(hit["away"]/cnt["away"]+hit["toward"]/cnt["toward"])/2
    return {"threshold":threshold,"balanced_accuracy":round(balanced,6),
            "accuracy":round((hit["away"]+hit["toward"])/(cnt["away"]+cnt["toward"]),6),
            "away_recall":round(hit["away"]/cnt["away"],6),
            "toward_recall":round(hit["toward"]/cnt["toward"],6),
            "nonflat":cnt["away"]+cnt["toward"],
            "source_count":len(per_source)}

def choose_threshold(model,validation):
    grid=[i/100 for i in range(5,71,5)]
    scored=[sign_scores(model,validation,t) for t in grid]
    best=sorted(scored,key=lambda x:(-x["balanced_accuracy"],abs(x["threshold"]-.5)))[0]
    return {"best":best,"grid":scored}

def summarize(model,train,val):
    tr=MODEL.evaluate(model,train)
    va=MODEL.evaluate(model,val)
    return {"train":{**MODEL.summarized(tr),"away_auc":away_auc(model,train)},
            "validation":{**MODEL.summarized(va),
                "away_auc":away_auc(model,val),
                "original_sign_threshold_0_50":sign_scores(model,val,.5)},
            "weight_l2":[round(math.sqrt(sum(v*v for v in k)),5)
                         for k in model["coefficients"]],
            "scaler":{ "mean_first6":[round(x,5) for x in model["feature_mean"][:6]],
                        "elapsed_log_mean":round(model["feature_mean"][14],5)},
            "best_validation_sign_calibration":choose_threshold(model,val)["best"]}

def covariate_shift(train,val):
    n=len(train[0]["features"])
    result=[]
    for j in range(n):
        xs=[r["features"][j] for r in train]
        ys=[r["features"][j] for r in val]
        mu1=statistics.mean(xs);mu2=statistics.mean(ys)
        scale=max(.12,statistics.pstdev(xs))
        result.append({"feature_index":j,"train_mean":round(mu1,5),
            "validation_mean":round(mu2,5),
            "abs_shift_train_sd":round(abs(mu1-mu2)/scale,5)})
    return sorted(result,key=lambda x:-x["abs_shift_train_sd"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,default=Path("build/drnas-x41"))
    ap.add_argument("--out",type=Path,default=Path("x43_diagnose"))
    ap.add_argument("--per-family-per-cycle",type=int,default=24)
    ap.add_argument("--validation-per-family",type=int,default=24)
    ap.add_argument("--cap",type=float,default=1.5)
    args=ap.parse_args()
    binary=args.binary.resolve()
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    if args.per_family_per_cycle<8:raise ValueError("too few")
    train_records=[];by_cycle=[]
    with tempfile.TemporaryDirectory(prefix="x43-audit-") as td:
        tmp=Path(td)
        val_records=[]
        for fam in X43.VALID:
            for i in range(40000,40000+args.validation_per_family):
                src=X43.unique_source(fam,i)
                val_records+=X43.execute_case(src,binary,3,args.cap,tmp)["records"]
        for cycle in range(3):
            new_records=[]
            for fam in X43.TRAIN:
                for i in range(30000+cycle*args.per_family_per_cycle,
                               30000+(cycle+1)*args.per_family_per_cycle):
                    src=X43.unique_source(fam,i)
                    new_records+=X43.execute_case(src,binary,3,args.cap,tmp)["records"]
            train_records+=new_records
            standard=MODEL.fit(train_records,epochs=90,ridge=.014)
            entry={"cycle":cycle+1,
                "cohort":distribution(new_records),
                "cumulative":distribution(train_records),
                "fixed_model":summarize(standard,train_records,val_records),
                "validation_label_distribution":distribution(val_records)}
            by_cycle.append(entry)
            emit("X43_DIAG_CYCLE",{"cycle":cycle+1,
                "train_sources":entry["cumulative"]["distinct_sources"],
                "new_row_class_fraction":entry["cohort"]["row_fraction"],
                "train_logloss":entry["fixed_model"]["train"]["model_logloss_formula_mean"],
                "validation_logloss":entry["fixed_model"]["validation"]["model_logloss_formula_mean"],
                "val_away_auc":entry["fixed_model"]["validation"]["away_auc"],
                "val_best_sign":entry["fixed_model"]["best_validation_sign_calibration"]})
        experiments=[]
        for name,epochs,ridge in [
            ("baseline_90",90,.014),
            ("early_20",20,.014),("early_45",45,.014),("early_60",60,.014),
            ("long_180",180,.014),("long_360",360,.014),
            ("ridge_006",90,.06),("ridge_010",90,.1)]:
            model=MODEL.fit(train_records,epochs=epochs,ridge=ridge)
            train=MODEL.evaluate(model,train_records)
            val=MODEL.evaluate(model,val_records)
            sign=choose_threshold(model,val_records)
            row={"name":name,"epochs":epochs,"ridge":ridge,
                "train_logloss":train["model_logloss_formula_mean"],
                "validation_logloss":val["model_logloss_formula_mean"],
                "val_away_auc":away_auc(model,val_records),
                "val_away_recall_argmax":(
                   val["confusion_actual_to_predicted"]["away"]["away"]/
                   max(1,val["class_support"]["away"])),
                "sign_threshold_validation_only":sign["best"]}
            experiments.append(row)
            emit("X43_DIAG_ABLATION",row)
    report={"protocol":"repeat identical original X4.3 training and validation formula sources",
            "training_diagnosis_only":True,
            "prior_holdout_not_evaluated":True,
            "no_model_intervention":True,
            "three_cycles":by_cycle,
            "final_train_vs_validation_feature_shift":covariate_shift(train_records,val_records)[:12],
            "third_cycle_ablations":experiments,
            "key_limits":[
               "Validation used to select sign threshold, requires fresh untouched holdout for confirmation.",
               "Retrospective SAT direction is not causal alternative-decision utility.",
               "Rows from same source are correlated: original SHA is statistical unit."
            ]}
    (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    (args.out/"validation_labeled.jsonl").write_text("".join(
        json.dumps(r,sort_keys=True)+"\n" for r in val_records))
    # Archive labeled TRAIN transitions to allow exact ablations without
    # repeated SAT-solving and prevent accidental use of old holdout to tune.
    (args.out/"train_labeled.jsonl").write_text("".join(
        json.dumps(r,sort_keys=True)+"\n" for r in train_records))
    emit("X43_DIAG_FINAL",{"n_train_sources":by_cycle[-1]["cumulative"]["distinct_sources"],
       "n_validation_sources":len({r["source_sha"] for r in val_records}),
       "fixed_validation_loss":[round(x["fixed_model"]["validation"]["model_logloss_formula_mean"],6) for x in by_cycle],
       "third_cycle_best_by_validation_logloss":min(experiments,key=lambda x:x["validation_logloss"]),
       "class_distributions":[x["cohort"]["row_fraction"] for x in by_cycle],
       "feature_shifts_top5":report["final_train_vs_validation_feature_shift"][:5]})

if __name__=="__main__":
    main()
