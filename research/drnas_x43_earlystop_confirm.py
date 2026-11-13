#!/usr/bin/env python3
"""X4.3.1 prospective test: did early stopping fix training-cycle3 regression?

Frozen before new outcome inspection:
  A = 192-source cycle2 / 90 optimization epochs.
  B = 288-source cycle3 / 90 epochs (previous overfit setting).
  C = 288-source cycle3 / 20 epochs (selected using separate validation).
Optional D = 288-source cycle3 / strong L2 90 epochs, secondary.
All sign thresholds tuned on old sparse4 VALIDATION family before unseen data.
Test once on new families never before used in this project.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import tempfile
from collections import Counter,defaultdict
import statistics

import drnas_x43_preaction_bench as X43
import drnas_x43_premodel as MODEL
import drnas_x43_diagnostics as D
import drnas_x42_convergence_cycles as X42

NEW_FAMILIES=("planted4_dense","xor_bridge","mixed_sparse_23")
EXPECTED_ARMS=("CYCLE2_90","CYCLE3_90","CYCLE3_EARLY20","CYCLE3_RIDGE010")

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def train_and_validation(binary,root,cap):
    validation=[]
    for i in range(40000,40024):
        validation.extend(X43.execute_case(
            X43.unique_source("sparse4",i),binary,3,cap,root)["records"])
    train=[]
    frozen_two=None
    for cyc in range(3):
        for fam in X43.TRAIN:
            for i in range(30000+24*cyc,30000+24*(cyc+1)):
                train.extend(X43.execute_case(
                    X43.unique_source(fam,i),binary,3,cap,root)["records"])
        if cyc==1:
            frozen_two=list(train)
        emit("X43_EARLY_TRAIN_PROGRESS",{"cycle":cyc+1,
            "distinct_sources":len({x["source_sha"] for x in train}),
            "rows":len(train)})
    assert frozen_two is not None and len({x["source_sha"] for x in frozen_two})==192
    assert len({x["source_sha"] for x in train})==288
    return frozen_two,train,validation

def get_models(train2,train3,val):
    specs={"CYCLE2_90":(train2,90,.014),
           "CYCLE3_90":(train3,90,.014),
           "CYCLE3_EARLY20":(train3,20,.014),
           "CYCLE3_RIDGE010":(train3,90,.1)}
    models={}
    for name,(rows,epochs,ridge) in specs.items():
        model=MODEL.fit(rows,epochs=epochs,ridge=ridge)
        # Sign threshold calibrated only on an unrelated but PREVIOUSLY used
        # validation family, never on this new holdout. No tuning after test.
        selected=D.choose_threshold(model,val)["best"]
        val_summary=MODEL.evaluate(model,val)
        models[name]={"model":model,"threshold":selected["threshold"],
            "validation_sign_accuracy":selected,
            "validation_logloss":val_summary["model_logloss_formula_mean"]}
        emit("X43_EARLY_FROZEN",{"arm":name,"epochs":epochs,
            "ridge":ridge,"threshold":selected["threshold"],
            "validation_logloss":val_summary["model_logloss_formula_mean"],
            "validation_balanced_sign":selected["balanced_accuracy"]})
    return models

def losses(model,rows):
    by_source=defaultdict(list)
    for row in rows:
        y=MODEL.CLASSES.index(row["label"])
        p=MODEL.infer(model,row["features"])[y]
        by_source[row["source_sha"]].append(-math.log(max(1e-12,p)))
    return {s:statistics.mean(v) for s,v in by_source.items()}

def paired_ci(a,b,source_family,draws=4000,seed=1947):
    # Positive means model b has lower loss than model a.
    ids=sorted(a)
    if set(ids)!=set(b):raise AssertionError("unbalanced source predictions")
    diff={s:a[s]-b[s] for s in ids}
    rng=random.Random(seed)
    series=[]
    for _ in range(draws):
        sampled=[ids[rng.randrange(len(ids))] for _ in ids]
        series.append(statistics.mean(diff[s] for s in sampled))
    series.sort()
    byfam=defaultdict(list)
    for s in ids:byfam[source_family[s]].append(s)
    fams=sorted(byfam)
    clustered=[]
    for _ in range(draws):
        units=[byfam[fams[rng.randrange(len(fams))]] for _ in fams]
        ss=[s for unit in units for s in unit]
        clustered.append(statistics.mean(diff[s] for s in ss))
    clustered.sort()
    return {"improvement_mean":round(statistics.mean(diff.values()),6),
            "formula_cluster_95pct":[round(series[int(.025*(draws-1))],6),
                                     round(series[int(.975*(draws-1))],6)],
            "family_cluster_95pct":[round(clustered[int(.025*(draws-1))],6),
                                    round(clustered[int(.975*(draws-1))],6)],
            "unique_source_units":len(ids),"heldout_families":len(fams),
            "family_ci_only_three_clusters_very_uncertain":True}

def sign_audit(models,rows):
    ids=sorted({x["source_sha"] for x in rows})
    support=Counter(x["label"] for x in rows if x["label"]!="flat")
    if not support["away"] or not support["toward"]:
        return {"status":"one-sided holdout: cannot establish balanced sign accuracy"}
    per={}
    for name,m in models.items():
        stats=D.sign_scores(m["model"],rows,m["threshold"])
        perf=MODEL.evaluate(m["model"],rows)
        per[name]={**stats,
            "threeclass_model_accuracy":perf["model_accuracy"],
            "away_auc":D.away_auc(m["model"],rows)}
    rng=random.Random(20261113001)
    groups=defaultdict(list)
    for row in rows:
        if row["label"]=="flat":continue
        groups[row["source_sha"]].append(row)
    def balanced(grouped,name):
        hit=Counter();count=Counter();m=models[name]
        for row in grouped:
            pred=MODEL.infer(m["model"],row["features"])
            ratio=pred[0]/max(1e-9,pred[0]+pred[2])
            guess="away" if ratio>=m["threshold"] else "toward"
            count[row["label"]]+=1;hit[row["label"]]+=int(guess==row["label"])
        if min(count.values())==0 or len(count)!=2:return None
        return .5*(hit["away"]/count["away"]+hit["toward"]/count["toward"])
    diffs=[]
    for _ in range(2200):
        sample_ids=[ids[rng.randrange(len(ids))] for _ in ids]
        sampled=[row for sid in sample_ids for row in groups[sid]]
        x=balanced(sampled,"CYCLE3_EARLY20")
        y=balanced(sampled,"CYCLE3_90")
        if x is not None and y is not None:diffs.append(x-y)
    diffs.sort()
    return {"by_arm":per,"holdout_support":dict(support),
        "early20_minus_90_balanced_sign_accuracy_formula95pct":[
            round(diffs[int(.025*(len(diffs)-1))],5),
            round(diffs[int(.975*(len(diffs)-1))],5)] if diffs else None,
        "n_distinct_SAT_sources":len(ids),"replays_not_independent":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,default=Path("build/drnas-x41"))
    p.add_argument("--out",type=Path,default=Path("x43_early_fresh"))
    p.add_argument("--per-test-family",type=int,default=36)
    p.add_argument("--cap",type=float,default=1.5)
    args=p.parse_args()
    if args.per_test_family<20:raise ValueError("fresh holdout too small")
    binary=args.binary.resolve()
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    with tempfile.TemporaryDirectory(prefix="x43-early-test-") as td:
        root=Path(td)
        train2,train3,val=train_and_validation(binary,root,args.cap)
        models=get_models(train2,train3,val)
        frozen=args.out/"frozen_models.json"
        frozen.write_text(json.dumps({name:obj for name,obj in models.items()},
                                     indent=2,sort_keys=True)+"\n")
        digest=hashlib.sha256(frozen.read_bytes()).hexdigest()
        old_shas=X43.prior_sha_coverage()
        old_shas.update(x["source_sha"] for x in train3+val)
        new_sources=[]
        for family in NEW_FAMILIES:
            for idx in range(60000,60000+args.per_test_family):
                case=X43.unique_source(family,idx)
                if case["source_sha"] in old_shas:
                    raise AssertionError("heldout formula already seen")
                old_shas.add(case["source_sha"])
                new_sources.append(case)
        holdout=[]; replay_shas=set()
        for i,case in enumerate(new_sources):
            x=X43.execute_case(case,binary,3,args.cap,root)
            for sha in x["replay_shas"]:
                if sha in replay_shas:raise AssertionError("replay SHA duplicated")
                replay_shas.add(sha)
            holdout.extend(x["records"])
            if (i+1)%18==0:
                emit("X43_EARLY_PROGRESS",{"completed":i+1,"total":len(new_sources),
                    "labeled_events":len(holdout)})
        if hashlib.sha256(frozen.read_bytes()).hexdigest()!=digest:
            raise AssertionError("holdout influenced trained model")
    assert len({x["source_sha"] for x in holdout})==len(new_sources)
    per_arm={}
    source_fam={x["source_sha"]:x["family"] for x in holdout}
    for name,obj in models.items():
        model=obj["model"]
        score=MODEL.evaluate(model,holdout)
        byfam={}
        for family in NEW_FAMILIES:
            subset=[x for x in holdout if x["family"]==family]
            byfam[family]=MODEL.summarized(MODEL.evaluate(model,subset))
        per_arm[name]={"validation_loss":obj["validation_logloss"],
            "validation_calibrated_threshold":obj["threshold"],
            "new_holdout":MODEL.summarized(score),
            "by_family":byfam}
    early=models["CYCLE3_EARLY20"]["model"]
    long=models["CYCLE3_90"]["model"]
    losses_early=losses(early,holdout)
    losses_long=losses(long,holdout)
    comparison=paired_ci(losses_long,losses_early,source_fam)
    report={"protocol":"new never-used SAT families; model, epochs and thresholds frozen before labels",
        "new_holdout_sources":len(new_sources),"new_holdout_families":NEW_FAMILIES,
        "holdout_events":len(holdout),"all_source_sha_unique":True,
        "holdout_model_sha_unchanged":True,
        "pretrained_model_categories":EXPECTED_ARMS,
        "original_CNF_evidence_source":len(new_sources),
        "replay_cycles":3,
        "trained_on_288_or_192_original_sources":True,
        "previous_X43_holdout_not_reused_for_model_selection":True,
        "primary_comparison":"CYCLE3_EARLY20 vs CYCLE3_90",
        "early_stop_vs_overtrained":comparison,
        "sign_direction":sign_audit(models,holdout),
        "arms":per_arm,
        "limits":[
            "Never-use-after feature labels derive from exhaustive n<=18 SAT oracle.",
            "New holdout families are synthetic, only three family clusters.",
            "Predictive quality is not solver runtime, proof complexity or causal utility.",
            "Threshold selected on prior sparse4 validation; no holdout retuning."
        ]}
    (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    with (args.out/"holdout_decisions.jsonl").open("w") as f:
        for row in holdout:
            f.write(json.dumps({
                "source_sha":row["source_sha"],"family":row["family"],"cycle":row["cycle"],
                "decision":row["decision"],"actual_direction":row["label"],
                "pred_early20":MODEL.infer(early,row["features"]),
                "pred_long90":MODEL.infer(long,row["features"])
            },sort_keys=True)+"\n")
    emit("X43_EARLY_FINAL",{"n_heldout_originals":len(new_sources),
        "heldout_families":NEW_FAMILIES,
        "early_loss":per_arm["CYCLE3_EARLY20"]["new_holdout"]["model_logloss_formula_mean"],
        "overtrained_loss":per_arm["CYCLE3_90"]["new_holdout"]["model_logloss_formula_mean"],
        "cycle2_loss":per_arm["CYCLE2_90"]["new_holdout"]["model_logloss_formula_mean"],
        "loss_improvement_95CI":comparison["formula_cluster_95pct"],
        "family_95CI":comparison["family_cluster_95pct"],
        "early_sign":report["sign_direction"].get("by_arm",{}).get("CYCLE3_EARLY20"),
        "overtrain_sign":report["sign_direction"].get("by_arm",{}).get("CYCLE3_90")})

if __name__=="__main__":main()
