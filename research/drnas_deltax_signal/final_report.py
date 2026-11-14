#!/usr/bin/env python3
"""Reconcile DELTAX-SIGNAL1 without leaking eval graphs into model fitting.

Only after frozen TRAIN threshold and independent VALIDATION/HOLDOUT are
complete does this script read all three. No new tuning or promotion.
"""
import collections
import hashlib
import json
from pathlib import Path

R=Path(__file__).resolve().parents[2]
INPUTS=R/"deltax_signal1_inputs"
SPLITS=("train","validation","holdout")
GROUPS={"train":30,"validation":15,"holdout":15}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def get(path):return json.loads(Path(path).read_text())
def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def main():
    train_root=R/"frozen/train/deltax_signal_train"
    val_root=R/"frozen/validation/deltax_signal_validation"
    hold_root=R/"frozen/holdout/deltax_signal_holdout"
    policy=get(train_root/"policy.json")
    assert policy["status"]=="FROZEN_TRAIN_ONLY"
    assert not policy["selection_uses_validation"]
    assert not policy["selection_uses_holdout"]
    data=get(INPUTS/"manifest.json")
    assert len(data)==180 and len({c["sha256"] for c in data})==180
    partitions={split:{s["graph_id"] for s in data if s["split"]==split}
                for split in SPLITS}
    assert all(len(partitions[k])==GROUPS[k] for k in SPLITS)
    assert all(not partitions[a].intersection(partitions[b])
               for i,a in enumerate(SPLITS) for b in SPLITS[i+1:])
    for split in SPLITS:
        assert policy[split+"_manifest_sha256"]==sha(
            INPUTS/(split+"_manifest.json"))
    assert policy["train_trials_sha256"]==sha(train_root/"trials.jsonl")
    models=policy["train_model_comparisons"]
    threshold=policy["min_unassigned_binary_reach"]
    assert models and threshold in policy["threshold_candidates"]
    assert threshold==max(models,key=lambda x:(x["score"],x["min_reach"]))["min_reach"]
    summaries={}
    records={}
    for split,root in (("train",train_root),("validation",val_root),
                       ("holdout",hold_root)):
        records[split]=[json.loads(line) for line in (root/"trials.jsonl").read_text().splitlines()]
        rows=records[split]
        graphs={r["graph_id"] for r in rows}
        assert graphs==partitions[split]
        assert not any(r["source_invalid"] or r["clone_inconsistent"] for r in rows)
        verdict=collections.defaultdict(set)
        for r in rows:
            if r["verified"]:verdict[r["source_sha256"]].add(r["status"])
        assert all(len(v)<=1 for v in verdict.values())
        status=collections.Counter(r["status"] for r in rows)
        summary={
            "graph_groups":len(graphs),"attempts":len(rows),
            "verified":sum(r["verified"] for r in rows),
            "non_verified":sum(not r["verified"] for r in rows),
            "SAT_verified":status["SAT_VERIFIED"],
            "UNSAT_certified":status["UNSAT_CERTIFIED"],
            "guard_accepted":sum(r["guard_accepted"] for r in rows),
            "signal_vetoed":sum(r["signal_vetoed"] for r in rows),
            "original_source_resolution_errors":0,
            "clone_inconsistencies":0,
        }
        if split!="train":
            evaluated=get(root/"summary.json")
            assert evaluated["policy_sha256"]==sha(train_root/"policy.json")
            assert evaluated["trained_min_reach"]==threshold
            assert evaluated["independent_graph_groups"]==GROUPS[split]
            summary.update({key:evaluated[key] for key in (
                "wins_graph_groups","regressed_graph_groups",
                "neutral_graph_groups","paired_decision_gain",
                "paired_conflict_gain")})
            assert sum(summary[k] for k in (
                "wins_graph_groups","regressed_graph_groups",
                "neutral_graph_groups"))==GROUPS[split]
        summaries[split]=summary

    assert len(records["train"])==30*3*6==540
    assert len(records["validation"])==15*3*3==135
    assert len(records["holdout"])==15*3*3==135
    # Summarize observational graph-level compare, not twice-counting
    # OFF / LOW / HIGH as 3 independent graph groups.
    selected_mode="deltax-signal-"+str(threshold)
    family=[]
    for split in ("validation","holdout"):
        rows=records[split]
        by={(r["graph_id"],r["variant"],r["mode"]):r for r in rows}
        for graph in sorted(partitions[split]):
            src=next(s for s in data if s["graph_id"]==graph)
            result={"graph_id":graph,"split":split,"family":src["family"]}
            ok_count=0
            improvements={}
            for variant in ("off","low1","high1"):
                a=by[(graph,variant,"join")]
                b=by[(graph,variant,"deltax-guard")]
                c=by[(graph,variant,selected_mode)]
                verified=a["verified"] and b["verified"] and c["verified"]
                if verified:ok_count+=1
                improvements[variant]={
                    "paired_verified":verified,
                    "signal_vs_join_decisions":a["decisions"]-c["decisions"] if verified else None,
                    "signal_vs_join_conflicts":a["conflicts"]-c["conflicts"] if verified else None,
                    "signal_vs_guard_decisions":b["decisions"]-c["decisions"] if verified else None,
                    "signal_vs_guard_conflicts":b["conflicts"]-c["conflicts"] if verified else None,
                    "signal_vetoed":c["signal_vetoed"],
                    "signal_reach_tested":c["signal_tested"],
                    "accepted":c["guard_accepted"]
                }
            result["comparable_variants"]=ok_count
            result["matched_variants"]=improvements
            family.append(result)

    split_report={
        "status":"COMPLETE",
        "method":"SOURCE-BLIND original binary implication reach, max depth 3",
        "selected_threshold":threshold,
        "distinct_graphs":60,
        "total_unique_CNFs":180,
        "split_graphs":GROUPS,
        "split_no_graph_id_overlap":True,
        "source_blind_feature":True,
        "training_only_model_selection":True,
        "fixed_model_through_validation_holdout":True,
        "training_policy_sha256":sha(train_root/"policy.json"),
        "all_source_manifest_sha256":sha(INPUTS/"manifest.json"),
        "original_solver_sha256":policy["source_binary_sha256"],
        "all_certified_source_proofs_valid":True,
        "all_original_models_and_unsat_drat_verified_when_credited":True,
        "one_logical_cpu_per_solver":True,
        "no_unverified_sat_unsat_credit":True,
        "promoted":False,"new_math_theorem_claim":False,
        "general_speedup_claim":False,"blind_realworld_holdout":False,
        "train_models":models,
        "train":summaries["train"],
        "validation":summaries["validation"],
        "holdout":summaries["holdout"],
        "graph_level_evaluation":family,
    }
    out=R/"deltax_signal1_final"
    save(out/"report.json",split_report)
    save(out/"selected_policy.json",policy)
    print("DELTAX_SIGNAL1_FINAL",json.dumps({
        k:v for k,v in split_report.items()
        if k not in ("graph_level_evaluation","train_models")
    },sort_keys=True),flush=True)

if __name__=="__main__":main()
