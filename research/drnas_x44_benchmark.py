#!/usr/bin/env python3
"""DRNAS X4.4: source/family-balanced, persistent, abstaining away-risk learner.

OFFLINE shadow only. A model prediction cannot change the native CDCL branch.
Train/validation/test original CNFs come from disjoint generators with
non-overlapping source indices and an independent exact n<=18 truth oracle.
Replays of the same source do not multiply independent statistical N.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import tempfile

import drnas_x42_convergence_cycles as X42
import drnas_x43_preaction_bench as X43
import drnas_x43_premodel as M3
import drnas_x44_guard as G

TRAIN=("planted3","planted_2sat","planted_xor","community3","sparse3","xor_ring")
VALID=("sparse4","planted4_dense","xor_bridge","mixed_sparse_23")
HOLDOUT=("hub4_planted","modular2_3","ring3_planted","xor_fan")
UNSAT=("php_unsat","graph_k4_unsat")
assert len(set(TRAIN+VALID+HOLDOUT+UNSAT))==16

def emit(label,x):
    print(label+" "+json.dumps(x,sort_keys=True,separators=(",",":")),flush=True)

def unique_case(fam,idx):
    item=X43.unique_source(fam,idx)
    if item["family"]!=fam:raise AssertionError("source family changed")
    return item

def collect(families,n,offset):
    return {fam:[unique_case(fam,offset+i) for i in range(n)] for fam in families}

def data_check(cohorts):
    seen=set()
    for fam,items in cohorts.items():
        for x in items:
            if x["source_sha"] in seen:raise AssertionError("source SHA duplicated")
            seen.add(x["source_sha"])
    return seen

def auc_threeclass_away(model,data):
    scores=[]
    for row in data:
        if row["label"] not in ("toward","away"):continue
        p=M3.infer(model,row["features"])
        scores.append((p[0]/max(1e-10,p[0]+p[2]),int(row["label"]=="away")))
    scores.sort()
    n1=sum(y for _,y in scores);n0=len(scores)-n1
    if not n1 or not n0:return None
    total=0.;pos=0
    while pos<len(scores):
        j=pos+1
        while j<len(scores) and scores[j][0]==scores[pos][0]:j+=1
        total+=(pos+1+j)/2*sum(v for _,v in scores[pos:j])
        pos=j
    return (total-n1*(n1+1)/2)/(n1*n0)

def choose_checkpoint(records,validation,candidates):
    # All checkpoint calibration and selection ONLY uses validation sources.
    best=None
    evaluations=[]
    for stage,model in candidates:
        calibrated,cal=G.tune_validation(model,validation)
        v=cal["validation_summary"]
        ba=v.get("accepted_balanced_accuracy")
        coverage=v.get("coverage",0)
        signal=(ba-.5)*math.sqrt(coverage) if ba is not None and cal["eligible"] else -1.0
        row={"stage":stage,"model":calibrated,"calibration":cal,"score":signal}
        evaluations.append({"stage":stage,"source_count":model["training_sources"],
            "threshold":cal["chosen_threshold"],"margin":cal["chosen_margin"],
            "val_away_auc":v.get("away_auc_all_nonflat"),
            "val_coverage":coverage,"val_away_recall":v.get("away_recall_among_accepted"),
            "val_balanced_accuracy":ba,"score":signal,
            "ood_threshold":model["ood_threshold"]})
        if best is None or signal>best["score"]:best=row
    return best,evaluations

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--binary",type=Path,default=Path("build/drnas-x41"))
    parser.add_argument("--out",type=Path,default=Path("x44_guard"))
    parser.add_argument("--train-per-family",type=int,default=48)
    parser.add_argument("--validation-per-family",type=int,default=16)
    parser.add_argument("--holdout-per-family",type=int,default=32)
    parser.add_argument("--unsat-per-family",type=int,default=8)
    parser.add_argument("--cap",type=float,default=1.5)
    args=parser.parse_args()
    if args.train_per_family<24 or args.train_per_family%3 or args.holdout_per_family<16:
        raise ValueError("insufficient or unbalanced X44 cohort")
    args.out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cohorts={}
    cohorts.update(collect(TRAIN,args.train_per_family,71000))
    cohorts.update(collect(VALID,args.validation_per_family,76000))
    cohorts.update(collect(HOLDOUT,args.holdout_per_family,82000))
    cohorts.update(collect(UNSAT,args.unsat_per_family,87000))
    distinct=data_check(cohorts)
    manifest={
        "source_count":len(distinct),"train_families":TRAIN,"validation_families":VALID,
        "holdout_families":HOLDOUT,"unsat_families":UNSAT,
        "source_indices":{"train_start":71000,"validation_start":76000,
            "holdout_start":82000,"unsat_start":87000},
        "new_heldout_family_generators":True,
        "SHA_distinct":True,
        "independent_sampling_unit":"one original mathematical CNF (not 3 replays or transitions)",
        "no_active_policy":True,
        "generator_created_SAT_witness_is_not_used_as_predictor_feature":True,
        "oracle":"separate exhaustive n<=18 SAT enumeration after solve",
        "sources":[{"family":x["family"],"source_sha":x["source_sha"],
                    "nvars":x["n"],"clauses":len(x["clauses"]),"id":x["base_id"]}
                   for fam in TRAIN+VALID+HOLDOUT+UNSAT for x in cohorts[fam]]
    }
    (args.out/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    train=[];validation=[];held=[];unsat_results=[]
    replay_set=set()
    def process(x,tmp):
        output=X43.execute_case(x,binary,3,args.cap,tmp)
        for sha in output["replay_shas"]:
            if sha in replay_set:raise RuntimeError("duplicate replay CNF SHA")
            replay_set.add(sha)
        return output
    cycles=[];candidates=[]
    with tempfile.TemporaryDirectory(prefix="x44-guard-") as d:
        tmp=Path(d)
        # Validation features and exact labels are only for calibration and
        # checkpoint selection; never included in fitted parameters.
        for family in VALID:
            for case in cohorts[family]:
                validation.extend(process(case,tmp)["records"])
        warm_model=None
        for cycle in range(3):
            for family in TRAIN:
                width=args.train_per_family//3
                subset=cohorts[family][cycle*width:(cycle+1)*width]
                for case in subset:
                    train.extend(process(case,tmp)["records"])
            # Persistent warm start with training-only scaler reparameterization.
            warm_model=G.fit(train,epochs=50 if cycle==0 else 20,
                             ridge=.07,warm_model=warm_model)
            candidate=(f"CONTINUAL_CYCLE_{cycle+1}",warm_model)
            candidates.append(candidate)
            base=G.assess(warm_model,validation)
            cycle_row={"cycle":cycle+1,
                "training_distinct_sources":warm_model["training_sources"],
                "training_nonflat_rows":warm_model["training_nonflat_events"],
                "validation_away_auc":base.get("away_auc_all_nonflat"),
                "training_class_support":warm_model["training_class_support"],
                "training_ood_threshold":round(warm_model["ood_threshold"],6),
                "warm_started":warm_model["warm_started"]}
            cycles.append(cycle_row)
            emit("X44_LEARNING_CYCLE",cycle_row)
        # Controls matched to the same TRAIN sources. Two variants of X4.3
        # are frozen now, before any unseen holdout outcomes are inspected.
        softmax20=M3.fit(train,epochs=20,ridge=.014)
        softmax_regularized=M3.fit(train,epochs=90,ridge=.1)
        champion,checkpoint_summary=choose_checkpoint(train,validation,candidates)
        if champion is None:raise AssertionError("no learned X44 checkpoint")
        guard=champion["model"]
        frozen_obj={"guard":guard,"selected_checkpoint":champion["stage"],
                    "checkpoint_table":checkpoint_summary,
                    "softmax_early20":softmax20,
                    "softmax_ridge010":softmax_regularized,
                    "training_sources":len({r["source_sha"] for r in train})}
        frozen=args.out/"frozen_models.json"
        frozen.write_text(json.dumps(frozen_obj,sort_keys=True,indent=2)+"\n")
        sha=hashlib.sha256(frozen.read_bytes()).hexdigest()
        emit("X44_GUARD_FROZEN",{
            "checkpoint":champion["stage"],
            "confidence_threshold":guard["threshold"],
            "abstention_margin":guard["margin"],
            "validation_eligible":guard["validation_eligible"],
            "validation_summary":champion["calibration"]["validation_summary"]})
        for family in HOLDOUT:
            for i,x in enumerate(cohorts[family]):
                held.extend(process(x,tmp)["records"])
                if (i+1)%16==0:emit("X44_HOLDOUT_PROGRESS",{"family":family,"completed":i+1})
        for family in UNSAT:
            for x in cohorts[family]:
                o=process(x,tmp)
                if o["SAT_models"]!=0 or o["records"] or o["status"].get("UNSAT")!=3:
                    raise AssertionError("UNSAT control failed independent enumeration")
                unsat_results.append({"family":family,"source_sha":x["source_sha"],"oracle":"UNSAT"})
        if hashlib.sha256(frozen.read_bytes()).hexdigest()!=sha:
            raise AssertionError("holdout altered trained model")
    n_held=len({r["source_sha"] for r in held})
    if n_held!=len(HOLDOUT)*args.holdout_per_family:
        raise AssertionError("unbalanced unseen holdout")
    summary=G.assess(guard,held)
    family_scores={}
    for family in HOLDOUT:
        part=[x for x in held if x["family"]==family]
        family_scores[family]=G.assess(guard,part)
    original_baselines={
        "SOFTMAX20_3CLASS":M3.summarized(M3.evaluate(softmax20,held)),
        "SOFTMAX90_RIDGE010_3CLASS":M3.summarized(M3.evaluate(softmax_regularized,held)),
        "SOFTMAX20_AWAY_AUC":round(auc_threeclass_away(softmax20,held),6),
        "SOFTMAX90_RIDGE010_AWAY_AUC":round(auc_threeclass_away(softmax_regularized,held),6)
    }
    # No held-out label may select a checkpoint or threshold.
    ci=G.source_cluster_ci(guard,held,draws=3000,seed=44120261113)
    ok=(summary["coverage"]>=.15 and
        summary["accepted_balanced_accuracy"] is not None and
        ci.get("balanced_acc_95pct",[0])[0]>.5)
    report={"protocol":"X4.4 guarded before-action shadow prediction",
        "status":"EXPLORATORY_PREDICTIVE_SIGNAL" if ok else "NO_CONFIRMED_ACTIONABLE_DIRECTION_SIGNAL",
        "source_count":len(distinct),"training_sources":len({r["source_sha"] for r in train}),
        "validation_sources":len({r["source_sha"] for r in validation}),
        "holdout_original_sources":n_held,"holdout_replay_count":n_held*3,
        "all_native_original_runs":len(replay_set),
        "unsat_exhaustive_sources":len(unsat_results),
        "source_SHA_unique":True,"holdout_model_frozen":True,
        "selected_continual_checkpoint":champion["stage"],
        "cycles":cycles,"validation_checkpoint_selection":checkpoint_summary,
        "new_holdout":summary,"holdout_families":family_scores,
        "formula_cluster_ci":ci,"comparison_to_3class_baselines":original_baselines,
        "original_CNF_proof":"SAT verified against original CNF; UNSAT controls exhaustive",
        "no_solver_speedup_claim":True,
        "no_active_policy":True,
        "no_causal_counterfactual":True,
        "genuine_blind_official_benchmark":False,
        "limits":[
            "A predicted risk score is not mathematically certified closeness to SAT.",
            "Abstention is measured on observed actions; controller did not make decisions.",
            "The 4 heldout types are newly generated synthetic families, not official benchmarks.",
            "Nonflat labels require exponential enumeration and are not available at runtime."
        ]}
    (args.out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    with (args.out/"holdout_predictions.jsonl").open("w") as f:
        for row in held:
            action,risk,ood=G.predict(guard,row["features"])
            f.write(json.dumps({"source_sha":row["source_sha"],"family":row["family"],
                "cycle":row["cycle"],"decision":row["decision"],"actual":row["label"],
                "prediction":action,"away_probability":round(risk,8),
                "ood_score":round(ood,7)},sort_keys=True)+"\n")
    emit("X44_FINAL",{"status":report["status"],"train":report["training_sources"],
        "validation":report["validation_sources"],
        "new_holdout":n_held,"unseen_family_count":len(HOLDOUT),
        "test_nonflat_events":summary["nonflat_events"],
        "risk_away_AUC":summary["away_auc_all_nonflat"],
        "coverage":summary["coverage"],
        "accepted_balanced_accuracy":summary["accepted_balanced_accuracy"],
        "away_recall":summary["away_recall_among_accepted"],
        "toward_recall":summary["toward_recall_among_accepted"],
        "away_precision":summary["away_precision_among_emitted"],
        "abstention_counts":[summary["abstain_ood"],summary["abstain_uncertain"]],
        "formula_CI":ci.get("balanced_acc_95pct"),
        "checkpoint":champion["stage"],
        "threeclass_awayAUC_controls":[original_baselines["SOFTMAX20_AWAY_AUC"],
              original_baselines["SOFTMAX90_RIDGE010_AWAY_AUC"]],
        "UNSAT_controls":len(unsat_results),"native_replays":len(replay_set)})

if __name__=="__main__":main()
