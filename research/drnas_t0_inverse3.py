#!/usr/bin/env python3
"""T0-INVERSE3 preregistered validation of the inverse INTERACTION2 score.

No selection/tuning on this evaluation cohort; use published SATLIB entries
14..21, completely disjoint from T0-FRONTIER1 entries 0..5 and INTERACTION2
entries 6..13. The tested rule is exactly negative of the frozen
INTERACTION2 recommendation (larger score = predicted WORSE, not better).
This is exploratory retrospective non-industrial transfer, not a blind
real-world benchmark. Original models and DRAT are independently checked.
"""
from __future__ import annotations
import collections,json,os,random,time
from pathlib import Path
import drnas_t0_frontier1 as F
import drnas_t0_interaction2 as I

ROOT=Path("t0_interaction3")
ROOT.mkdir(exist_ok=True)
I.START=14
I.ROOT=ROOT
I.PER_FAMILY=8

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    assert F.BIN.is_file() and F.DRAT.is_file()
    rows=[]
    for family in F.SETS:rows.extend(I.new_sources(family))
    assert len(rows)==48 and len({x["sha256"] for x in rows})==48
    manifest={
        "status":"FROZEN_BEFORE_SOLVER","n":len(rows),
        "cohort":"SATLIB_SHA_sorted_positions_14_to_21",
        "source_disjoint_from_FRONTIER1_and_INTERACTION2":True,
        "hypothesis":"NEGATE_INTERACTION2_FIXED_PREDICTION",
        "score":"same_direct_forced_plus_positive_second_order_synergy_plus_2_failed_pair_fraction",
        "interpretation":"larger_score_is_worse_direction",
        "success_target_exploratory":"correct>=65percent_of_informative_and_at_least_30_informative",
        "no_fitting":True,"one_logical_cpu":True,
        "proofs_checked_original_CNF":True,"not_new_industrial_holdout":True,
        "source_rows":rows}
    p=ROOT/"manifest.json"
    p.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    emit("T0_INVERSE3_FROZEN",{"sources":len(rows),"sha256":F.sha(p.read_bytes()),
        "selection":"positions_14_through_21","rule":"inverse_INTERACTION2"})
    random.Random(141127).shuffle(rows)
    cases=[]
    for src in rows:
        raw=Path(src["path"]).read_bytes()
        assert F.sha(raw)==src["sha256"]
        n,clauses=F.parse(raw)
        order=[False,True]
        random.Random(int(src["sha256"][:10],16)).shuffle(order)
        result={}
        for flip in order:result[flip]=F.native(src,flip,n,clauses)
        a,b=result[False],result[True]
        assert a["verified"] and b["verified"],("UNVERIFIED",src["name"])
        assert a["reached_first_branch"] and b["reached_first_branch"],(
            "FIRST_BRANCH_NOT_REACHED",src["name"])
        assert a["pre_state_digest"]==b["pre_state_digest"] and (
            a["baseline_literal"]==b["baseline_literal"]!=0),(
            "NOT_IDENTICAL_T0",src["name"])
        assert a["actual_literal"]==a["baseline_literal"]
        assert b["actual_literal"]==-a["actual_literal"]
        start=time.perf_counter()
        diagnostics=I.signal(n,clauses,a["baseline_literal"])
        cpu_ms=1000.*(time.perf_counter()-start)
        predicted=-diagnostics["recommendation"]  # PRE-REGISTERED INVERSION
        actual=F.compare(a,b)
        entry={"name":src["name"],"family":src["family"],"sha256":src["sha256"],
            "first_literal":a["baseline_literal"],"predictor":diagnostics,
            "predicted_inverse":predicted,"observed_better":actual,
            "baseline":a,"flip":b,"feature_python_ms":cpu_ms}
        cases.append(entry)
        emit("T0_INVERSE3_PAIR",{"family":src["family"],"name":src["name"],
             "prediction":predicted,"observed":actual,
             "base_conflicts":a["conflicts"],"flip_conflicts":b["conflicts"],
             "feature_python_ms":round(cpu_ms,3)})
    picked=[x for x in cases if x["predicted_inverse"]]
    informative=[x for x in picked if x["observed_better"]]
    flipped=[x for x in cases if x["predicted_inverse"]==1]
    correct=sum(x["predicted_inverse"]==x["observed_better"] for x in informative)
    wrong=sum(x["predicted_inverse"]!=x["observed_better"] for x in informative)
    baseline_better=sum(x["observed_better"]==-1 for x in cases)
    flip_better=sum(x["observed_better"]==1 for x in cases)
    totals={"base_conflicts":sum(x["baseline"]["conflicts"] for x in cases),
            "flip_conflicts":sum(x["flip"]["conflicts"] for x in cases),
            "base_decisions":sum(x["baseline"]["decisions"] for x in cases),
            "flip_decisions":sum(x["flip"]["decisions"] for x in cases)}
    final={
        "status":"COMPLETE","sources":len(cases),"both_verified":len(cases),
        "matched_first_branch_state":len(cases),
        "non_abstaining":len(picked),"abstaining":len(cases)-len(picked),
        "informative":len(informative),"correct":correct,"wrong":wrong,
        "accuracy_informative":correct/max(1,len(informative)),
        "pre_registered_target_met":len(informative)>=30 and correct*100>=65*len(informative),
        "inverted_predicted_flip_count":len(flipped),
        "inverted_flip_wins":sum(x["observed_better"]==1 for x in flipped),
        "inverted_flip_losses":sum(x["observed_better"]==-1 for x in flipped),
        "baseline_better":baseline_better,"flip_better":flip_better,
        "totals":totals,"median_python_feature_ms":sorted(
            x["feature_python_ms"] for x in cases)[len(cases)//2],
        "families":dict(collections.Counter(x["family"] for x in cases)),
        "one_logical_cpu":True,"all_original_proofs_or_models_verified":True,
        "source_disjoint":True,"not_realworld_holdout":True,
        "solver_promoted":False,"main_modified":False,
        "fixed_policy_no_refit":True,"manifest_sha256":F.sha(p.read_bytes())
    }
    (ROOT/"rows.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in cases))
    (ROOT/"report.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    emit("T0_INVERSE3_FINAL",final)

if __name__=="__main__":main()
