#!/usr/bin/env python3
"""CLCF5 REPLAY: repeated 8s proof-verified first deletion ablation on REAL36 #16.

Same exact fixed policy and X5 binary as CLCF5; no parameter search or new
solver edits. Cap increased BEFORE test, 3 repeats, one logical CPU.
This is a retrospective confirmatory test of one selected formula, not a
statistical claim about general SAT performance.
"""
from __future__ import annotations
import json,os,random,statistics,sys,hashlib
from pathlib import Path
import drnas_clause_cf5_real14 as A
import drnas_x55_cpu_real36 as REAL

OUT=Path("clause_cf5_replay")
OUT.mkdir(exist_ok=True)
A.CAP=8.0
ID=16
REPS=3

def emit(tag,obj):print(tag+" "+json.dumps(obj,sort_keys=True),flush=True)

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    all_sources,original=REAL.official_manifest()
    src=next(s for s in all_sources if s["id"]==ID)
    assert src["family"]=="scheduling"
    manifest={
        "status":"FROZEN_BEFORE_EXECUTION",
        "original_REAL36_id":ID,"sha256":src["sha256"],
        "repetitions":REPS,"cap_s":A.CAP,
        "arms":list(A.ARMS),"first_effective_reduction_policy_exactly_CLCF5":True,
        "same_source_manifest_sha256":original["manifest_sha256"],
        "one_logical_cpu":True,"no_training_no_tuning":True,
        "retrospective_selected_source":True,"proofs_original_CNF":True,
        "no_main_changes":True,"not_promoted":True}
    p=OUT/"manifest.json"
    p.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    emit("CLCF5_REPLAY_FROZEN",{"source_id":ID,"source_sha256":src["sha256"],
         "protocol_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
         "repetitions":REPS,"cap_s":A.CAP})
    pairs=[]
    for rep in range(REPS):
        order=list(A.ARMS)
        random.Random(141156+rep).shuffle(order)
        trials={}
        for mode in order:trials[mode]=A.trial(src,mode)
        sig=("first_effective_reduce","first_reduce_conflicts",
             "first_reduce_decisions","candidates","deleted","first_candidate_digest")
        initial=trials["BASE"]["quality"]
        assert initial["first_effective_reduce"] and initial["deleted"]>=128
        for mode in A.ARMS:
            q=trials[mode]["quality"]
            assert all(initial[k]==q[k] for k in sig),(
                "FIRST_REDUCTION_NOT_IDENTICAL",rep,mode)
        ver={trials[m]["status"] for m in A.ARMS if trials[m]["verified"]}
        assert len(ver)<=1,("CONTRADICTORY_COMPLETED_MODELS",rep)
        pairs.append({"rep":rep,"trial":trials})
        emit("CLCF5_REPLAY_PAIR",{"rep":rep,
            "status":{m:trials[m]["status"] for m in A.ARMS},
            "verified":{m:trials[m]["verified"] for m in A.ARMS},
            "cpu_s":{m:round(trials[m]["cpu_s"],4) for m in A.ARMS},
            "conflicts":{m:trials[m]["conflicts"] for m in A.ARMS},
            "PAR2_s":{m:round(trials[m]["PAR2_verified_s"],4) for m in A.ARMS}})
    summary={}
    for m in A.ARMS:
        ls=[r["trial"][m] for r in pairs]
        verified=[x for x in ls if x["verified"]]
        summary[m]={
            "attempts":REPS,"verified":len(verified),
            "PAR2_verified_s":round(sum(x["PAR2_verified_s"] for x in ls),5),
            "median_cpu_s":round(statistics.median(x["cpu_s"] for x in ls),5),
            "median_wall_s":round(statistics.median(x["wall_e2e_s"] for x in ls),5),
            "matched_conflicts":sorted(set(x["conflicts"] for x in ls)),
        }
    report={
        "status":"COMPLETE","source_id":ID,"source_sha256":src["sha256"],
        "repetitions":REPS,"all_first_reduction_signature_matched":True,
        "median_and_PAR2":summary,
        "all_proved_SAT_UNSAT_original_CNF":True,
        "one_cpu":True,"no_training_or_changes":True,
        "not_blind_and_not_general_claim":True,
        "no_main_edits_or_promotion":True}
    (OUT/"pairs.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in pairs))
    (OUT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    emit("CLCF5_REPLAY_FINAL",report)
if __name__=="__main__":main()
