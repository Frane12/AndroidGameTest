"""Paired native decision experiment; learned gate frozen before holdout.

Forced LTM_NATIVE demonstrates causality, not learned usefulness. Only the
separate LTM_NATIVE_GATE may claim a training-selected intervention. All
timing includes routing, CNF I/O, process startup and native setup/solve.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import experiment as bench
from design import FAMILIES, cohort, digest_manifest, opportunity_key
from policy import TrainingMemory


def effect(rows, arm):
    base={(r["sha256"],r["rep"]):r for r in rows if r["arm"]=="BASE"}
    candidates=[r for r in rows if r["arm"]==arm]
    changed=0
    regressions=0
    unavailable=0
    for r in candidates:
        b=base[r["sha256"],r["rep"]]
        if b["decision_hash"] is None or r["decision_hash"] is None:
            if b["solved"] and r["solved"]:
                raise AssertionError("Missing native decision telemetry on completed solve")
            unavailable+=1
        else:
            changed += r["decision_hash"] != b["decision_hash"]
        regressions += b["solved"] and not r["solved"]
    return dict(pairs=len(candidates),changed_decision_traces=changed,
                unavailable_trace_pairs=unavailable,
                solved_regressions=regressions,
                branch_overrides=sum(r["native_branch_overrides"] for r in candidates))


def run(generation, smoke=False):
    if hasattr(os,"sched_getaffinity") and len(os.sched_getaffinity(0)) != 1:
        raise RuntimeError("Run this benchmark under taskset with one logical CPU")
    bench.BIN=bench.ROOT/"mre_ltm3/bin/drnas_ltm3"
    cases=cohort(training_generation=generation)
    if smoke:
        cases=[next(c for c in cases if c["family"]==f and c["split"]==s)
               for f in FAMILIES for s in ("train","holdout")]
    for c in cases:
        c["feature_key"]=opportunity_key(c["clauses"],c["n"])
    train=[c for c in cases if c["split"]=="train"]
    holdout=[c for c in cases if c["split"]=="holdout"]
    holdout_shas={c["sha"] for c in holdout}
    db=bench.OUT/("native_smoke.sqlite" if smoke else "native_training.sqlite")
    memory=TrainingMemory(db)
    trials=[]
    with TemporaryDirectory() as td:
        for i,c in enumerate(train,1):
            for rep in range(bench.REPS):
                rows={}
                arms=("BASE","LTM_NATIVE") if (i+rep)%2 else ("LTM_NATIVE","BASE")
                for arm in arms:
                    rows[arm]=bench.run_arm(c,arm,rep,None,Path(td))
                    trials.append(rows[arm])
                memory.insert_pair(sha=c["sha"],rep=rep,generation=generation,
                                   family=c["family"],key=c["feature_key"],
                                   base=rows["BASE"],force=rows["LTM_NATIVE"])
            if i%24==0: print("LTM3_NATIVE_TRAIN",i,len(train),flush=True)
        frozen=memory.freeze(holdout_shas,candidate_action="LTM_NATIVE")
        memory.close()
        before=hashlib.sha256(db.read_bytes()).hexdigest()
        readonly=TrainingMemory(db,readonly=True)
        assert readonly.freeze(holdout_shas,candidate_action="LTM_NATIVE")==frozen
        readonly.close()
        for i,c in enumerate(holdout,1):
            for rep in range(bench.REPS):
                arms=["BASE","LTM_NATIVE","LTM_NATIVE_GATE"]
                shift=(i+rep)%len(arms)
                arms=arms[shift:]+arms[:shift]
                for arm in arms:
                    trials.append(bench.run_arm(c,arm,rep,frozen,Path(td)))
            if i%24==0: print("LTM3_NATIVE_HOLDOUT",i,len(holdout),flush=True)
        assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    held=[r for r in trials if r["split"]=="holdout"]
    digest,manifest=digest_manifest(cases)
    report=dict(project="LTM3 native decision fix",training_generation=generation,
                formula_manifest_sha=digest,manifest=manifest,
                one_logical_cpu=True,cap_s=bench.CAP_S,repeats=bench.REPS,
                train_cases=len(train),holdout_cases=len(holdout),policy=frozen,
                policy_frozen_before_holdout=True,holdout_never_writes_memory=True,
                repeated_holdout_is_nonblind=True,independent_LRAT=False,
                note="Generated CNF diagnostic. Repeats measure timing; A/native deterministic and do not use seed. Forced changes are not evidence of learned benefit.",
                train=bench.summary([r for r in trials if r["split"]=="train"]),
                holdout=bench.summary(held),
                by_family={f:bench.summary([r for r in held if r["family"]==f]) for f in FAMILIES},
                effects={a:effect(held,a) for a in ("LTM_NATIVE","LTM_NATIVE_GATE")},
                paired={a:bench.paired_wins(held,"BASE",a) for a in ("LTM_NATIVE","LTM_NATIVE_GATE")},
                trials=trials)
    suffix="SMOKE" if smoke else "FINAL"
    (bench.ROOT/("MI_LTM3_NATIVE_%s.json"%suffix)).write_text(json.dumps(report,indent=2,sort_keys=True))
    print("LTM3_NATIVE_FINAL",json.dumps({k:report[k] for k in
          ("train_cases","holdout_cases","holdout","effects","paired")},sort_keys=True),flush=True)
    print("LTM3_NATIVE_POLICY",len(frozen["positive_classes"]),"positive classes",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--generation",type=int,default=1)
    parser.add_argument("--smoke",action="store_true")
    args=parser.parse_args()
    if args.generation < 1: raise ValueError("generation must be positive")
    run(args.generation,args.smoke)
