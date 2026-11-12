#!/usr/bin/env python3
"""LTM11 REAL1: source-disjoint official SAT2024 structural router benchmark.

Train 60 / validate 20 / frozen holdout 20; verified PAR2 and CPU pinning.
A single job runs solvers serially. 20s deep probing applies to predetermined
high-complexity subsets (8 train, 4 validation) selected using CNF features only.
Native conflict counters are retained only if actually emitted by the solver.
"""
import collections
import hashlib
import json
import os
import pathlib
import time

import drnas_ltm10_real1 as B
import drnas_ltm11_policy as P

ROOT=pathlib.Path("ltm11_real1")
TRAIN_CAP=3.0
DEEP_CAP=20.0
HOLDOUT_CAP=12.0
SEEDS=(17,29)
NATIVE_ARMS=P.ARMS
TEST_ARMS=("LTM11","LTM9_FAST","LTM8_FAST","Kissat","CaDiCaL")
B.ROOT=ROOT
B.SCREEN_CAP=TRAIN_CAP
B.TEST_CAP=HOLDOUT_CAP
B.TRAIN_COUNT=60
B.VALID_COUNT=20
B.TEST_COUNT=20
B.SAMPLE_COUNT=100

# Internal native --time must expire before external subprocess timeout,
# otherwise timeout() erases output and all progress counters.
_ORIGINAL_COMMAND=B.command
def command_with_native_grace(arm,path,seed,cap):
    cmd=_ORIGINAL_COMMAND(arm,path,seed,cap)
    if arm in NATIVE_ARMS and "--time" in cmd:
        t=cmd.index("--time")
        cmd[t+1]=str(max(0.2,cap-0.35))
    return cmd
B.command=command_with_native_grace

def emit(label,obj):
    print(label+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def original_run(arm,source,seed,cap):
    # Small operational slack protects against races at native timeouts.
    # Elapsed spans source verification, subprocess, and certificate validation.
    start=time.monotonic()
    row=B.run_solver(arm,source,seed,max(0.4,cap-0.25))
    row["e2e_s"]=round(time.monotonic()-start,6)
    row["cap_s"]=cap
    row["original_cnf_sha256"]=source["sha256"]
    row["progress_observed"]=(P.progress(row) is not None)
    return B.with_metrics(row,cap)

def prepare():
    ROOT.mkdir(parents=True,exist_ok=True)
    sources=B.collect()
    if len(sources)!=100:
        raise RuntimeError("expected 100 official CNFs")
    families=collections.defaultdict(set)
    for s in sources:
        families[s["split"]].add(s["normalized_name_family"])
    if len(set.union(*families.values()))!=100:
        raise RuntimeError("source-family leakage")
    return sources

def get_features(source):
    start=time.monotonic()
    feat,elapsed=P.extract(source["path"])
    # Return the deterministic bounded-sample overhead measured at call time.
    return feat, max(elapsed,time.monotonic()-start)

def train(sources):
    learned=[]
    features={}
    extraction={}
    for source in sources:
        if source["split"]=="holdout":
            continue
        f,d=get_features(source)
        features[source["id"]]=f
        extraction[source["id"]]=d
    # Blind static-complexity selection: no run result or label used.
    def rank(s):
        f=features[s["id"]]
        return (f["log_clauses"]+f["log_vars"]+0.2*f["hub_ratio"],
                -s["id"])
    train_sources=[s for s in sources if s["split"]=="train"]
    val_sources=[s for s in sources if s["split"]=="validation"]
    deep_train={s["id"] for s in sorted(train_sources,key=rank,reverse=True)[:8]}
    deep_val={s["id"] for s in sorted(val_sources,key=rank,reverse=True)[:4]}
    deep_ids=deep_train|deep_val
    emit("LTM11_SCREEN_PLAN",dict(train=60,validation=20,deep_train=sorted(deep_train),
         deep_validation=sorted(deep_val),short_cap_s=TRAIN_CAP,deep_cap_s=DEEP_CAP,
         feature_sample_bytes=P.SAMPLE_BYTES,feature_sample_clauses=P.SAMPLE_CLAUSES,
         deep_selection="static_complexity_blind_before_solver_results"))
    with (ROOT/"screen.jsonl").open("w") as f:
        for s in sources:
            if s["split"]=="holdout":
                continue
            cap=DEEP_CAP if s["id"] in deep_ids else TRAIN_CAP
            rows={}
            for arm in NATIVE_ARMS:
                row=original_run(arm,s,17,cap)
                row["feature_sample_s"]=round(extraction[s["id"]],6)
                rows[arm]=row
                f.write(json.dumps(row,sort_keys=True)+"\n")
                f.flush()
                emit("LTM11_SCREEN_TRIAL",dict(id=s["id"],arm=arm,
                     status=row["status"],cap_s=cap,
                     PAR2_verified_s=row["PAR2_verified_s"],
                     conflicts=row["conflicts"],decisions=row["decisions"]))
            learned.append((s,features[s["id"]],rows))
    train_pairs=[(feat,rows) for s,feat,rows in learned if s["split"]=="train"]
    validation_pairs=[(feat,rows) for s,feat,rows in learned if s["split"]=="validation"]
    model=P.fit(train_pairs,validation_pairs)
    memory=P.save(model,ROOT/"ltm11_memory.json",
                  [s["sha256"] for s in train_sources],
                  [s["sha256"] for s in val_sources])
    seen=sum(P.progress(row) is not None for _,_,rows in learned
             for row in rows.values())
    unknown=sum(row["status"]=="UNKNOWN" for _,_,rows in learned
                for row in rows.values())
    audit=dict(sources_train=60,sources_validation=20,
               screening_trials=len(learned)*len(NATIVE_ARMS),
               progress_observed_trials=seen,unknown_trials=unknown,
               median_feature_sample_s=round(sorted(extraction.values())[len(extraction)//2],6),
               max_feature_sample_s=round(max(extraction.values()),6),
               model=memory)
    (ROOT/"train.json").write_text(json.dumps(audit,indent=2,sort_keys=True))
    emit("LTM11_TRAIN_FINAL",audit)
    return memory

def test_holdout(sources):
    # Loading the frozen file prevents accidental in-process policy mutation.
    memory=P.load(ROOT/"ltm11_memory.json")
    totals=[]
    routed=collections.Counter()
    extraction_samples=[]
    with (ROOT/"holdout.jsonl").open("w") as f:
        for s in sources:
            if s["split"]!="holdout":
                continue
            for rep,seed in enumerate(SEEDS):
                # Fair order rotation avoids systematic earlier-armed advantage.
                arms=list(TEST_ARMS)
                offset=(s["id"]+rep)%len(arms)
                arms=arms[offset:]+arms[:offset]
                for arm in arms:
                    if arm=="LTM11":
                        start=time.monotonic()
                        feat,ft=get_features(s)
                        selected=P.pick(memory,feat)
                        routed[selected]+=1
                        # Router overhead must consume the same external cap.
                        remaining=max(0.25,HOLDOUT_CAP-ft)
                        row=original_run(selected,s,seed,remaining)
                        row["chosen_native"]=selected
                        row["feature_extract_s"]=round(ft,6)
                        row["e2e_s"]=round(time.monotonic()-start,6)
                        row["arm"]="LTM11"
                        row=B.with_metrics(row,HOLDOUT_CAP)
                        extraction_samples.append(ft)
                    else:
                        row=original_run(arm,s,seed,HOLDOUT_CAP)
                    row["shard"]=(s["id"]-80)//5
                    row["rep"]=rep
                    totals.append(row)
                    f.write(json.dumps(row,sort_keys=True)+"\n")
                    f.flush()
                    emit("LTM11_HOLDOUT_TRIAL",dict(id=s["id"],rep=rep,arm=arm,
                         status=row["status"],e2e_s=row["e2e_s"],
                         verified=row["verified"],PAR2_verified_s=row["PAR2_verified_s"],
                         chosen_native=row.get("chosen_native")))
    if len(totals)!=20*len(SEEDS)*len(TEST_ARMS):
        raise RuntimeError("incomplete holdout")
    B.check_contradictions(totals)
    metrics=B.metrics(totals,HOLDOUT_CAP,TEST_ARMS)
    shards={str(i):B.metrics([r for r in totals if r["shard"]==i],
                            HOLDOUT_CAP,TEST_ARMS) for i in range(4)}
    report=dict(suite="LTM11 REAL1 official SAT2024",
                holdout_source_count=20,holdout_repetitions=2,
                trials_per_solver=40,all_trials=len(totals),
                train_sources=60,validation_sources=20,
                official_original_cnf=True,family_disjoint_heuristic=True,
                holdout_used_for_fit=False,
                one_logical_cpu_per_solver=True,
                max_test_cap_s=HOLDOUT_CAP,
                independently_proven_unsat_only="PHP mathematical certificate; not LRAT",
                unsat_unverified_not_rewarded=True,
                memory_status=memory["status"],
                routing=dict(routed),
                max_feature_extraction_s=round(max(extraction_samples),6),
                avg_feature_extraction_s=round(sum(extraction_samples)/len(extraction_samples),6),
                totals=metrics,shards=shards)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True))
    emit("LTM11_REAL_FINAL",report)
    print("LTM11_REAL_PASS",flush=True)

def main():
    P.selftest()
    sources=prepare()
    train(sources)
    test_holdout(sources)

if __name__=="__main__":
    main()
