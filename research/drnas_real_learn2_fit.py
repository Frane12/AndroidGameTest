#!/usr/bin/env python3
"""REAL-LEARN2 cumulative native policy fit from strictly compatible train-only pairs.

Never use retrospective historical benchmark outcomes or validation/holdout as
training labels. New validation is a one-time gate; prior validation never trains.
This is not source-level clause transfer and never modifies native executables.
"""
import argparse
import collections
import gzip
import hashlib
import json
import math
import statistics
from pathlib import Path
import drnas_real_learn1 as L

MODEL_VERSION="DRNAS-REAL-LEARN2-v1"
CAP_S=15.0

def load_prior(root, current_sources, catalog, cap):
    if not root or not root.exists():
        return [],0
    rows=[];sha=set();count=0
    allowed={r["sha256"]:r["split"] for r in catalog.get("sources",[])}
    for path in sorted(root.glob("*/train.jsonl.gz")):
        run=path.parent
        audit=json.loads((run/"training_audit.json").read_text())
        if audit["protocol"]!=MODEL_VERSION or audit["cap_s"]!=cap:
            raise RuntimeError("incompatible prior training source")
        with gzip.open(path,"rt",encoding="utf-8") as fd:
            data=[json.loads(line) for line in fd if line.strip()]
        for item in data:
            if item["split"]!="train" or item["sha256"] not in allowed or allowed[item["sha256"]]!="train":
                raise RuntimeError("prior data not explicitly assigned train")
            if not item.get("features") or item["sha256"] in current_sources:
                raise RuntimeError("cross-cycle overlap or missing features")
            if item["sha256"] not in sha:sha.add(item["sha256"])
            if item["PAR2"]!=(item["e2e_s"] if item["accepted"] else cap*2):
                raise RuntimeError("prior PAR2 mismatch")
            if item["accepted"] and not item["verified"]:
                raise RuntimeError("prior unverified trial")
            rows.append(item)
        count+=1
    return rows,count

def make_metrics(data,rule):
    out=L.rule_score(data,rule)
    by_family=collections.defaultdict(list)
    for s in data.values():by_family[s["family"]].append(s)
    gross_regressed=0
    for fam,cases in by_family.items():
        core=sum(r["cost"]["CORE"] for r in cases)
        candidate=sum(r["cost"][L.choose({"active_rule":rule},r["features"])] for r in cases)
        if core>0 and candidate>core*1.10:
            gross_regressed+=1
    out["families_regressed_gt10pct"]=gross_regressed
    return out

def bootstrap(data,rule,reps=3000):
    import random
    keys=sorted(data)
    a=[data[k]["cost"]["CORE"] for k in keys]
    b=[data[k]["cost"][L.choose({"active_rule":rule},data[k]["features"])] for k in keys]
    rng=random.Random(112617)
    scores=[]
    for _ in range(reps):
        ids=[rng.randrange(len(keys)) for _ in keys]
        core=sum(a[i] for i in ids)
        scores.append((core-sum(b[i] for i in ids))/core if core else 0.)
    scores.sort()
    return {"lower95":scores[int(.025*(reps-1))],
            "upper95":scores[int(.975*(reps-1))],
            "independent_sources":len(keys)}

def fit(args):
    m, splits=L.checked_manifest(args.split_manifest)
    rows,manifests=L.load_trials(args.train_data)
    if any(x["stage"]!="train" or x["cap"]!=CAP_S or
           tuple(x["arms"])!=L.TRAIN_ARMS or x["repeats"]!=1 for x in manifests):
        raise RuntimeError("training protocol or matched cap changed")
    current={r["sha256"] for r in splits["train"]+splits["validation"]}
    if {r["sha256"] for r in rows}!=current:
        raise RuntimeError("training missing sources or contains holdout")
    current_train=L.source_metrics(rows,"train")
    fresh_validation=L.source_metrics(rows,"validation")
    if set(current_train)!={r["sha256"] for r in splits["train"]}:
        raise RuntimeError("training split corrupted")
    if set(fresh_validation)!={r["sha256"] for r in splits["validation"]}:
        raise RuntimeError("validation split corrupted")
    catalog=json.loads(args.catalog.read_text()) if args.catalog and args.catalog.exists() else {"sources":[]}
    prior_rows, cycles=load_prior(args.prior,current,catalog,CAP_S)
    prior=L.source_metrics(prior_rows,"train") if prior_rows else {}
    if set(prior)&set(current_train):
        raise RuntimeError("previous/current SHA overlap")
    if {r["family"] for r in splits["holdout"]} & {r["family"] for r in splits["train"]}:
        raise RuntimeError("family leakage")
    training={**prior,**current_train}
    informative=sum(any(r["solved"][a] for a in L.TRAIN_ARMS) for r in training.values())
    fresh_info=sum(any(r["solved"][a] for a in L.TRAIN_ARMS) for r in fresh_validation.values())
    scored=[]
    for rule in L.candidate_rules(training):
        stats=make_metrics(training,rule)
        if stats["acted_sources"]<8 or stats["acted_families"]<4:continue
        if stats["relative_gain"]<=0 or stats["candidate_solved"]<stats["core_solved"]:
            continue
        # Avoid train wins caused by a single large source.
        if stats["families_regressed_gt10pct"]>max(1,len({r["family"] for r in training.values()})//10):
            continue
        scored.append((stats["relative_gain"],rule,stats))
    scored.sort(key=lambda x:(-x[0],json.dumps(x[1],sort_keys=True)))
    proposed=scored[0][1] if scored else None
    val=make_metrics(fresh_validation,proposed) if proposed else {}
    ci=bootstrap(fresh_validation,proposed) if proposed else {}
    reasons=[]
    if informative<25:reasons.append("fewer_than_25_verified_training_sources")
    if fresh_info<8:reasons.append("fewer_than_8_verified_fresh_validation_sources")
    if not proposed:reasons.append("no_positive_cost_safe_train_rule")
    if proposed:
        if val["relative_gain"]<.03:reasons.append("fresh_validation_gain_under_3_percent")
        if ci["lower95"]<=0:reasons.append("fresh_validation_95CI_not_positive")
        if val["candidate_solved"]<val["core_solved"]:reasons.append("fresh_validation_solved_regression")
        if val["acted_sources"]<6:reasons.append("too_few_fresh_validation_actions")
        if val["families_regressed_gt10pct"]>0:reasons.append("fresh_validation_family_regression")
    policy={
        "protocol":"DRNAS-REAL-LEARN1-v1",
        "extension":MODEL_VERSION,"model_type":"full-CNF family-isolated cumulative cost rule",
        "source_count":m["source_count"],"train_sources":len(training),
        "fresh_train_sources":len(current_train),"prior_train_sources":len(prior),
        "prior_cycles":cycles,"validation_sources":len(fresh_validation),
        "informative_train_sources":informative,"informative_validation_sources":fresh_info,
        "proposed_rule":proposed,"active_rule":proposed if not reasons else None,
        "model_activated":not reasons,"training_best":scored[0][2] if scored else {},
        "validation_proposed":val,"validation_confidence":ci,
        "reasons":reasons,"holdout_seen_at_training":False,
        "promoted":False,"no_production_changes":True,
        "cap_s":CAP_S}
    L.save_json(args.out,policy)
    L.emit("REAL2_FIT",{"new_training_sources":len(current_train),
        "cumulative_training_sources":len(training),
        "informative_train":informative,"informative_fresh_validation":fresh_info,
        "model_activated":policy["model_activated"],"rule":policy["active_rule"],
        "validation":val,"confidence":ci,"reasons":reasons})
    return policy

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--split-manifest",type=Path,required=True)
    p.add_argument("--train-data",type=Path,required=True)
    p.add_argument("--prior",type=Path)
    p.add_argument("--catalog",type=Path)
    p.add_argument("--out",type=Path,required=True)
    fit(p.parse_args())
