#!/usr/bin/env python3
"""DRNAS X4.3: THREE genuine training cycles, then fresh out-of-family prediction.

The native X4.2 SAT solver is unmodified, its decision policy never reads this
model. All features exist at the moment of the recorded decision. AFTER solving,
a logically separate small-n exhaustive oracle determines whether the decision
increased, decreased, or did not change SAT-completion probability.

Three formula-balanced training cycles, family-disjoint validation and held-out
SAT families. Distinct original CNFs, not replayed trajectories, are the
independence unit. UNSAT is checked by enumeration but never labelled toward.
This is a predictor study, not a new SAT solver speedup claim.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
from collections import Counter,defaultdict

import drnas_x43_premodel as MODEL
import drnas_x42_convergence_cycles as X42

TRAIN=("planted3","planted_2sat","community3","planted_xor")
VALID=("sparse4",)
HOLDOUT=("sparse3","xor_ring")
UNSAT=("php_unsat","graph_k4_unsat")
assert len(set(TRAIN+VALID+HOLDOUT+UNSAT))==9

def emit(tag,data):
    print(tag+" "+json.dumps(data,sort_keys=True,separators=(",",":")),flush=True)

def unique_source(family,index):
    case=X42.build_case(family,index)
    case["source_sha"]=X42.cnf_digest(case["n"],case["clauses"])
    return case

def pre_features(rec,n,clauses,stats,previous,previous2):
    a=rec["before"]
    lit=rec["decision_literal"]
    v=abs(lit)
    if not (1<=v<=n):
        raise AssertionError("bad native decision variable")
    lengths=stats["lengths"]
    occurrence=stats["incidences"][v]
    mean_degree=stats["literal_total"]/max(1,n)
    z=max(1,a["sampled_total"])
    d=max(1,a["decisions"])
    p0=previous or {}
    q0=previous2 or {}
    bprev=p0.get("after",{})
    cprev=p0.get("before",{})
    units=p0.get("logic",{}).get("unit_propagations_under_assumptions",0)
    conflict=p0.get("logic",{}).get("conflict_under_assumptions",False)
    prev_delta=p0.get("structure",{}).get("delta_satisfied",0)
    prev_open=p0.get("structure",{}).get("delta_open_long",0)
    prior_signed=p0.get("decision_literal",0)
    q_units=q0.get("logic",{}).get("unit_propagations_under_assumptions",0)
    # Everything below is available BEFORE propagation of the CURRENT action.
    # No after-state, future runtime, oracle result, SAT label or family name.
    return [
        n/18.0, len(clauses)/(8.0*max(1,n)), stats["literal_total"]/(6*max(1,len(clauses))),
        a["assigned"]/max(1,n),a["level"]/max(1,n),
        math.log1p(a["decisions"])/6.0,
        a["conflicts"]/d,a["learnt"]/d,
        a["propagations"]/(8.0*d),
        a["sample_unresolved_long"]/z,a["sample_open_binary"]/z,
        a["sample_open_unit"]/z,a["sample_satisfied"]/z,a["sample_falsified"]/z,
        math.log1p(max(0,a["elapsed_s"])*1000.0)/7,
        occurrence[0]/max(1.0,mean_degree),occurrence[1]/max(1.0,mean_degree),
        occurrence[2]/(occurrence[0]+occurrence[1]+1.0),
        (occurrence[0]-occurrence[1])/(occurrence[0]+occurrence[1]+1.0),
        float(lit>0),
        float(lit>0)*2-1,
        units/max(1,n),float(conflict),prev_delta/z,prev_open/z,
        float(prior_signed>0) if previous else 0.,
        max(0,a["decisions"]-bprev.get("decisions",a["decisions"]))/16,
        q_units/max(1,n),
    ]

def formula_stats(n,clauses):
    incidence=[[0,0,0] for _ in range(n+1)]
    literal_total=0
    for c in clauses:
        for lit in c:
            incidence[abs(lit)][int(lit<0)]+=1
            if len(c)==2:incidence[abs(lit)][2]+=1
            literal_total+=1
    return {"incidences":incidence,"literal_total":literal_total,
            "lengths":Counter(len(c) for c in clauses)}

def execute_case(case,binary,cycles,cap,tmp,save_dir=None):
    n,clauses=case["n"],case["clauses"]
    models=X42.exact_models(n,clauses)
    if case["has_planted_witness"] and not models:
        raise AssertionError("planted SAT has no satisfying completion")
    if case["family"] in UNSAT and models:
        raise AssertionError("independently enumerated UNSAT control is SAT")
    records=[]
    replay_shas=[]
    status_count=Counter()
    for cycle in range(cycles):
        rng=random.Random(9900+case["base_id"]*71+
                          X42.FAMILIES.index(case["family"])*13+cycle*147)
        clauses_p,permutation=X42.permute(n,clauses,rng,cycle)
        models_p=[X42.transform_model(x,permutation) for x in models]
        cnf=tmp/"case.cnf";trace=tmp/"transition.jsonl"
        sha=X42.write_dimacs(cnf,n,clauses_p)
        replay_shas.append(sha)
        command=[str(binary),str(cnf),"--mode","trace",
                 "--time",str(cap),"--stats","--transitions",
                 str(trace),"--trace-trail"]
        try:
            p=subprocess.run(command,capture_output=True,text=True,timeout=cap+1.0)
        except subprocess.TimeoutExpired:
            raise AssertionError("native diagnostic exceeded cap")
        if p.returncode not in (10,20):
            raise AssertionError("solver failed or returned UNKNOWN "+str(p.returncode)+" "+p.stderr[-800:])
        status={10:"SAT",20:"UNSAT"}[p.returncode]
        if models_p and (status!="SAT" or not X42.external_model_ok(n,clauses_p,p.stdout)):
            raise AssertionError("unverified original-CNF SAT answer")
        if not models_p and status!="UNSAT":
            raise AssertionError("native SAT conflicts with exhaustive oracle")
        status_count[status]+=1
        if save_dir is not None and case["base_id"]%11==0 and cycle==0:
            d=save_dir/f"{case['family']}-{case['base_id']}.jsonl"
            d.write_text(trace.read_text())
        events=[json.loads(x) for x in trace.read_text().splitlines()]
        if not events or events[0]["type"]!="meta" or not events[0]["observational_only"]:
            raise AssertionError("not an observational-only trace")
        entries=[x for x in events[1:] if x["type"]=="transition"]
        if len(entries)>128:raise AssertionError("unexpected long trace")
        stats=formula_stats(n,clauses_p)
        previous=None;previous2=None
        for rec in entries:
            before=rec["before"];after=rec["after"]
            t0=rec["trail_before"];t1=rec["trail_after"]
            if len(t0)!=before["assigned"] or len(t1)!=after["assigned"]:
                raise AssertionError("trace trail length mismatch")
            # Critical: generate the decision features WITHOUT inspecting after.
            feat=pre_features(rec,n,clauses_p,stats,previous,previous2)
            if models_p:
                a=X42.measure(n,models_p,t0)
                b=X42.measure(n,models_p,t1)
                dp=b["conditional_completion_probability"]-a["conditional_completion_probability"]
                label="toward" if dp>1e-12 else "away" if dp< -1e-12 else "flat"
                records.append({"source_sha":case["source_sha"],
                    "replay_sha":sha,"family":case["family"],"source_index":case["base_id"],
                    "cycle":cycle,"decision":after["decisions"],"features":feat,
                    "label":label,"oracle_delta":round(dp,12),
                    "before_fraction":a["conditional_completion_probability"],
                    "after_fraction":b["conditional_completion_probability"]})
            previous2,previous=previous,rec
    return {"records":records,"replay_shas":replay_shas,
            "status":dict(status_count),"SAT_models":len(models)}

def create_cohorts(per_train=24,per_valid=24,per_holdout=32,per_unsat=8):
    cohorts={}
    for family in TRAIN:
        cohorts[family]=[unique_source(family,30000+j) for j in range(3*per_train)]
    for family in VALID:
        cohorts[family]=[unique_source(family,40000+j) for j in range(per_valid)]
    for family in HOLDOUT:
        cohorts[family]=[unique_source(family,50000+j) for j in range(per_holdout)]
    for family in UNSAT:
        cohorts[family]=[unique_source(family,55000+j) for j in range(per_unsat)]
    sources=[v for data in cohorts.values() for v in data]
    hashes=[x["source_sha"] for x in sources]
    if len(set(hashes))!=len(hashes):
        raise RuntimeError("duplicate original formula source")
    return cohorts,sources

def prior_sha_coverage():
    # Exact old generator source indices on the previous X4.2 runs (3 replays).
    old=set()
    for family in X42.FAMILIES:
        for idx in list(range(8))+list(range(10000,10016)):
            source=X42.build_case(family,idx)
            for cycle in range(3):
                cp,_=X42.permute(source["n"],source["clauses"],
                  random.Random(9900+idx*71+X42.FAMILIES.index(family)*13+cycle*147),cycle)
                old.add(X42.cnf_digest(source["n"],cp))
    return old

def compact_eval(x):
    return MODEL.summarized(x)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,default=Path("build/drnas-x41"))
    ap.add_argument("--out",type=Path,default=Path("x43_preact"))
    ap.add_argument("--train-per-family-per-cycle",type=int,default=24)
    ap.add_argument("--valid-per-family",type=int,default=24)
    ap.add_argument("--test-per-family",type=int,default=32)
    ap.add_argument("--unsat-per-family",type=int,default=8)
    ap.add_argument("--cap",type=float,default=1.5)
    args=ap.parse_args()
    if args.train_per_family_per_cycle<5 or args.test_per_family<8 or args.cap<0.3:
        raise ValueError("underpowered requested experiment")
    per=args.train_per_family_per_cycle
    binary=args.binary.resolve()
    args.out.mkdir(parents=True,exist_ok=False)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cohorts,all_sources=create_cohorts(per,args.valid_per_family,
                                        args.test_per_family,args.unsat_per_family)
    earlier=prior_sha_coverage()
    if earlier & {x["source_sha"] for x in all_sources}:
        raise AssertionError("fresh formula overlaps old cohort")
    manifest={"new_unique_source_formulas":len(all_sources),"training_families":TRAIN,
        "validation_families":VALID,"holdout_families":HOLDOUT,"unsat_controls":UNSAT,
        "train_cumulative_cycles":3,"variable_permutation_replays":3,
        "prior_cohort_source_sha_overlap":0,
        "original_CNF_unit_of_independence":True,"no_global_novelty_claim":True,
        "no_SAT_training_from_UNSAT":True,
        "feature_policy":"pre-decision state, original structure and previous recorded events only",
        "model_policy":"offline only, never changes solver branch choices",
        "sources":[{"family":x["family"],"index":x["base_id"],"sha256":x["source_sha"],
                    "nvars":x["n"],"clauses":len(x["clauses"])}
                   for x in all_sources]}
    (args.out/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    training=[];validation=[];holdout=[];control=[]
    replay_hashes=set()
    all_replay_count=0
    def process(case,group,root):
        nonlocal all_replay_count
        output=execute_case(case,binary,3,args.cap,root)
        for sha in output["replay_shas"]:
            if sha in replay_hashes or sha in earlier:
                raise AssertionError("repeated replay CNF SHA (or seen prior cohort)")
            replay_hashes.add(sha)
        all_replay_count+=len(output["replay_shas"])
        return output
    milestones=[]
    with tempfile.TemporaryDirectory(prefix="x43-preaction-") as td:
        root=Path(td)
        for case in cohorts[VALID[0]]:
            validation.extend(process(case,"validation",root)["records"])
        for learning_cycle in range(3):
            for fam in TRAIN:
                batch=cohorts[fam][learning_cycle*per:(learning_cycle+1)*per]
                for case in batch:
                    training.extend(process(case,"train",root)["records"])
            model=MODEL.fit(training)
            score=MODEL.evaluate(model,validation)
            stat=MODEL.cluster_confidence(score,draws=1500,seed=222+learning_cycle)
            row={"learning_cycle":learning_cycle+1,
                 "trained_distinct_formulas":model["trained_source_count"],
                 "training_events":model["trained_events"],
                 "validation":compact_eval(score),"validation_cluster_ci":stat}
            milestones.append(row)
            emit("X43_LEARNING_CYCLE",row)
        model_path=args.out/"frozen_predictor.json"
        model_path.write_text(json.dumps(model,sort_keys=True,indent=2)+"\n")
        digest=hashlib.sha256(model_path.read_bytes()).hexdigest()
        # Never evaluate or inspect holdout before all training/validation cycles finish.
        for fam in HOLDOUT:
            for case in cohorts[fam]:
                holdout.extend(process(case,"holdout",root)["records"])
        for fam in UNSAT:
            for case in cohorts[fam]:
                result=process(case,"unsat_control",root)
                if result["SAT_models"]!=0 or len(result["records"])!=0:
                    raise AssertionError("UNSAT control was given an invented SAT direction")
                control.append({"family":fam,"source_sha":case["source_sha"],
                                "outcome":result["status"],"oracle_model_count":0})
        if hashlib.sha256(model_path.read_bytes()).hexdigest()!=digest:
            raise AssertionError("held-out outcome was able to change model")
    eval_holdout=MODEL.evaluate(model,holdout)
    holdout_ci=MODEL.cluster_confidence(eval_holdout,draws=3500,seed=20261113)
    by_family={}
    for family in HOLDOUT:
        score=MODEL.evaluate(model,[e for e in holdout if e["family"]==family])
        by_family[family]={"score":compact_eval(score),
                           "cluster_bootstrap":MODEL.cluster_confidence(score)}
    for family in UNSAT:
        if sum(1 for r in control if r["family"]==family)!=args.unsat_per_family:
            raise AssertionError("missing UNSAT control coverage")
    fixed_baseline=eval_holdout["constant_logloss_formula_mean"]
    performance=eval_holdout["model_logloss_formula_mean"]
    conclusion=("PREDICTIVE_SIGNAL_VALIDATED" if
                holdout_ci["formula_cluster_bootstrap95_logloss_improvement"][0]>0 and
                performance<fixed_baseline else "NO_CONFIRMED_PREDICTIVE_GAIN")
    report={"status":conclusion,"learning_cycles":milestones,
        "holdout":compact_eval(eval_holdout),"holdout_formula_ci":holdout_ci,
        "holdout_families":by_family,"unsat_controls":{
            "independently_exhaustive_checked_count":len(control),
            "never_assigned_SAT_direction":True,
        },"original_formula_count":len(all_sources),
        "all_observed_solver_replays":all_replay_count,
        "verified_SAT_model_original_CNF":True,
        "original_sha_overlap":0,"replay_sha_overlap":0,
        "frozen_model_sha256":digest,
        "n_independent_holdout_formulas":len({x["source_sha"] for x in holdout}),
        "replays_are_correlated":True,
        "no_active_policy_intervention":True,
        "no_mathematical_distance_or_causal_claim":True,
        "input_available_before_action_only":True,
        "metric":"3-class formula-weighted log loss vs training-frequency constant baseline"}
    (args.out/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    with (args.out/"holdout_predictions.jsonl").open("w") as f:
        for row in holdout:
            p=MODEL.infer(model,row["features"])
            output={k:row[k] for k in ("source_sha","replay_sha","family",
                "source_index","cycle","decision","label","oracle_delta")}
            output["predicted_probs"]=dict(zip(MODEL.CLASSES,[round(x,7) for x in p]))
            f.write(json.dumps(output,sort_keys=True)+"\n")
    emit("X43_FINAL",{
        "status":conclusion,"train_formulas":model["trained_source_count"],
        "validation_formulas":len({r["source_sha"] for r in validation}),
        "holdout_formulas":report["n_independent_holdout_formulas"],
        "holdout_events":eval_holdout["event_count"],
        "holdout_logloss":performance,"baseline_logloss":fixed_baseline,
        "logloss_improvement":eval_holdout["logloss_improvement"],
        "formula_cluster_ci":holdout_ci["formula_cluster_bootstrap95_logloss_improvement"],
        "nonflat_sign_accuracy":eval_holdout["nonflat_model_sign_accuracy"],
        "nonflat_always_majority":eval_holdout["nonflat_always_majority_sign_accuracy"],
        "three_training_cycles":len(milestones),
        "independent_unsat_controls":len(control),
        "all_replays":all_replay_count})

if __name__=="__main__":
    main()
