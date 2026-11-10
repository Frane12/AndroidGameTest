#!/usr/bin/env python3
"""DRNAS SEEDGATE1: fixed cheap source-only seed routing and 1s cold hedge.
Compare on all 12 already-observed EQUIV9 holdout SHA (TRANSFER, NOT blind).
Thresholds are precommitted, do not use EQUIV9 solved status, and are never
changed after this run begins. All solvers run one pinned logical CPU, no
parallel child solver. Native SAT model replayed on ORIGINAL SHA; UNSAT is
accepted for strict PAR2 only when original-input Kissat + CaDiCaL agree.
No LRAT is generated. E2E includes original CNF SHA, parse, source features,
launch, process and witness check in every mode, unlike older EQUIV9 wall clock.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import tempfile
import time

import drnas_equiv9_prospective_seed_holdout as e9

PROTO="DRNAS-SEEDGATE1-EQUIV9-TRANSFER-12SHA-8ARM-2REP-20S-v1"
ROOT=pathlib.Path("mre_seedgate1")
ARMS=("native1","native_altseed","native_split4",
      "native_shape_gate","native_hash_placebo","native_probe1",
      "kissat1","cadical301_default")
CAP=20.0
REPS=2
SHARDS=6
COUNT=12
# These are frozen BEFORE new measurements. No training/tuning on the
# EQUIV9 transfer cohort; the EQUIV10M5 5-SHA results motivated the study.
# The shape rule is intentionally cheap and simple, not ML fitted:
GATE_VARS=2000
GATE_CLAUSES=15000
PROBE_S=1.0

def need(ok,why):
    if not ok:
        raise RuntimeError("SEEDGATE1_FAIL_CLOSED "+str(why))

def save(path,obj):
    path=pathlib.Path(path)
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def source_features(n,clauses):
    # Based on original CNF only, BEFORE any solver is run.
    k=len(clauses)
    num_binary=sum(len(c)==2 for c in clauses)
    return dict(variables=n,clauses=k,binary_clauses=num_binary,
                binary_fraction=round(num_binary/max(1,k),6),
                clauses_per_var=round(k/max(1,n),6))

def seed_choice(arm,sha,features):
    if arm=="native_altseed":
        return "alt"
    if arm=="native_shape_gate":
        return "alt" if (
            features["variables"]>=GATE_VARS or
            features["clauses"]>=GATE_CLAUSES) else "base"
    if arm=="native_hash_placebo":
        # Frozen SHA-only negative control, independent of native outcome.
        k=int(hashlib.sha256(("SEEDGATE1-PLACEBO|"+sha).encode()).hexdigest()[:8],16)
        return "alt" if k&1 else "base"
    return "base"

def freeze():
    old=e9.verify()
    cohort=[c for c in old["cases"] if c["cohort"]=="holdout"]
    need(len(cohort)==COUNT and len({c["sha256"] for c in cohort})==COUNT,
         "not the entire original EQUIV9 holdout")
    m=dict(protocol=PROTO,source_protocol=e9.PROTO,
        source_manifest_sha256=e9.digest(e9.ROOT/"manifest.json"),
        frozen_source_SAT2021_to_2023=True,
        source_selection="entire previously seen EQUIV9 holdout; NO reselection",
        sources_seen_before_this_experiment=True,
        not_blind_transfer=True,
        seed_rule_not_fitted=True,
        rule=dict(vars_threshold=GATE_VARS,clauses_threshold=GATE_CLAUSES,
                  cold_probe_time_s=PROBE_S,
                  hash_placebo_salt="SEEDGATE1-PLACEBO",
                  alt_choice_is_or_of_thresholds=True),
        code_sha256=e9.digest(__file__),
        binaries_sha256={str(p):e9.digest(p) for p in e9.BINARIES},
        selected_cases=cohort,arms=list(ARMS),cap_s=CAP,reps=REPS,
        shards=SHARDS,total_trials=COUNT*len(ARMS)*REPS,
        one_logical_cpu_per_arm=True,no_parallel_children=True,
        original_SAT_model_verified=True,
        UNSAT_requires_Kissat_and_CaDiCaL_original_agreement=True,
        independent_UNSAT_LRAT=False, no_auto_promotion=True,
        E2E_includes_source_SHA_and_parse=True)
    save(ROOT/"manifest.json",m)
    verify()
    print("SEEDGATE1_FROZEN "+json.dumps(dict(source_count=COUNT,
        trial_count=m["total_trials"],arms=list(ARMS),
        cap_s=CAP,transfer_not_blind=True,
        source_sha_locked=True,rule=m["rule"]),sort_keys=True),flush=True)

def verify():
    old=e9.verify()
    m=json.loads((ROOT/"manifest.json").read_text())
    cohort=[c for c in old["cases"] if c["cohort"]=="holdout"]
    need(m["protocol"]==PROTO and m["source_protocol"]==e9.PROTO and
         m["selected_cases"]==cohort and len(cohort)==COUNT and
         m["arms"]==list(ARMS) and m["total_trials"]==COUNT*REPS*len(ARMS) and
         m["cap_s"]==CAP and m["shards"]==SHARDS and
         m["code_sha256"]==e9.digest(__file__) and
         m["source_manifest_sha256"]==e9.digest(e9.ROOT/"manifest.json") and
         m["binaries_sha256"]=={str(p):e9.digest(p) for p in e9.BINARIES},
         "frozen sources/rules/code/solver SHA drift")
    for c in cohort:
        src=e9.SOURCE/c["filename"]
        need(e9.digest(src)==c["sha256"],"original CNF SHA drift")
    return m

def trial(case,rep,arm,toy=False):
    need(arm in ARMS and 0<=rep<REPS,"unsupported arm/rep")
    src=pathlib.Path(case["filename"]) if toy else e9.SOURCE/case["filename"]
    # Include input checking and feature generation in E2E, for ALL arms.
    begin=time.perf_counter()
    before=e9.x22.child_cpu()
    need(e9.digest(src)==case["sha256"],"exact original SHA mismatch")
    n,clauses=e9.x22.read_cnf(src)
    need(n>0 and len(clauses)>0,"empty or incorrect DIMACS")
    features=source_features(n,clauses)
    base,alt=e9.seedpair(case["sha256"],rep)
    choice=seed_choice(arm,case["sha256"],features)
    cpu=min(os.sched_getaffinity(0))
    # No child processes overlap. A cold restart discards learnt clauses.
    plan=[(arm,base,CAP)]
    if arm in ("native_altseed","native_shape_gate","native_hash_placebo"):
        plan=[("native1",alt if choice=="alt" else base,CAP)]
    elif arm=="native_split4":
        plan=[("native1",base,4.0),("native1",alt,CAP)]
    elif arm=="native_probe1":
        plan=[("native1",base,PROBE_S),("native1",alt,CAP)]
    status="TIMEOUT"
    stages=[]
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        for i,(run_arm,seed,limit) in enumerate(plan):
            remaining=CAP-(time.perf_counter()-begin)
            if remaining<0.07:
                break
            stage=e9.e8.one_stage(run_arm,src,clauses,seed,cpu,
                                  min(remaining,limit),td,i)
            stages.append(stage)
            if stage["status"] in ("SAT","UNSAT"):
                status=stage["status"]
                break
    elapsed=time.perf_counter()-begin
    if elapsed>=CAP:
        status="TIMEOUT"
    verified=(status=="SAT" and
        any(s["status"]=="SAT" and s["SAT_original_witness_verified"]
            for s in stages))
    need(status!="SAT" or verified,"bad original SAT witness")
    return dict(protocol=PROTO,source_sha256=case["sha256"],gbd=case["gbd"],
        arm=arm,rep=rep,cohort="EQUIV9_seen_transfer",cap_s=CAP,
        seed_base=base,seed_alt=alt,seed_choice=choice,
        seed_used=alt if choice=="alt" else base,
        features=features,child_starts=len(stages),stages=stages,
        pinned_logical_cpu=cpu,original_sha256_verified=True,
        SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,
        wall_E2E_s=round(elapsed,6),
        child_CPU_s=round(e9.x22.child_cpu()-before,6),
        status=status)

def selftest():
    need(len(ARMS)==8 and len(set(ARMS))==8,"bad arms")
    need(seed_choice("native_shape_gate","x",dict(variables=1999,clauses=14999))=="base",
         "lower shape gate boundary")
    need(seed_choice("native_shape_gate","x",dict(variables=2000,clauses=1))=="alt",
         "variable threshold")
    need(seed_choice("native_shape_gate","x",dict(variables=2,clauses=15000))=="alt",
         "clause threshold")
    need(seed_choice("native_hash_placebo","abc",{})==
         seed_choice("native_hash_placebo","abc",{}),"placebo not deterministic")
    ROOT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        src=pathlib.Path(td)/"toy.cnf"
        src.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n")
        c=dict(filename=str(src),sha256=e9.digest(src),gbd="toy")
        for arm in ARMS:
            t=trial(c,0,arm,toy=True)
            need(t["status"]=="SAT" and t["SAT_original_witness_verified"],
                 "selftest failed for "+arm)
    print("SEEDGATE1_SELFTEST_PASS "+json.dumps(dict(
        arms=len(ARMS),original_SAT_witnesses_checked=len(ARMS),
        source_gate_boundary_tests_passed=True),sort_keys=True),flush=True)

def shard(idx):
    need(0<=idx<SHARDS,"invalid shard")
    m=verify()
    cases=[c for i,c in enumerate(m["selected_cases"]) if i%SHARDS==idx]
    need(len(cases)==2,"expected 2 entire disjoint SHA per shard")
    rows=[]
    for c in cases:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+"|"+str(rep)+"|"+PROTO).shuffle(arms)
            for arm in arms:
                r=trial(c,rep,arm)
                r["shard"]=idx
                rows.append(r)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("SEEDGATE1_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==2*REPS*len(ARMS),"incomplete shard")
    print("SEEDGATE1_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for i in range(SHARDS):
        shardrows=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(shardrows)==2*REPS*len(ARMS),"incomplete shard "+str(i))
        rows+=shardrows
    expected={(c["sha256"],rep,arm) for c in m["selected_cases"]
              for rep in range(REPS) for arm in ARMS}
    seen={(r["source_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(seen)==len(expected)==m["total_trials"] and
         seen==expected,"incomplete paired 192-trial matrix")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             r["original_sha256_verified"] and r["child_starts"]==len(r["stages"]) and
             r["child_starts"]<=2 and r["wall_E2E_s"]<=CAP+.1 and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "original SHA/trial verification failed")
        bysha[r["source_sha256"]].append(r)
    agree=set()
    for sha,rr in bysha.items():
        need(len({r["status"] for r in rr if r["status"]!="TIMEOUT"})<=1,
             "SAT/UNSAT solver contradiction "+sha)
        if (any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr)
                and any(r["arm"]=="cadical301_default" and r["status"]=="UNSAT" for r in rr)):
            agree.add(sha)
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["source_sha256"] in agree)
    def score(vals):
        return dict(n=len(vals),solved=sum(accepted(r) for r in vals),
            SAT_original_verified=sum(r["status"]=="SAT" for r in vals),
            UNSAT_reference_agreement_no_LRAT=sum(r["status"]=="UNSAT" and r["source_sha256"] in agree for r in vals),
            UNSAT_not_verified=sum(r["status"]=="UNSAT" and r["source_sha256"] not in agree for r in vals),
            timeouts=sum(r["status"]=="TIMEOUT" for r in vals),
            PAR2_s=round(sum(r["wall_E2E_s"] if accepted(r) else 2*CAP for r in vals),6),
            child_CPU_s=round(sum(r["child_CPU_s"] for r in vals),6),
            second_seed_solves=sum(r["status"]=="SAT" and len(r["stages"])==2 for r in vals))
    scores={a:score([r for r in rows if r["arm"]==a]) for a in ARMS}
    kiss=scores["kissat1"]["PAR2_s"]
    native=scores["native1"]["PAR2_s"]
    alt=scores["native_altseed"]["PAR2_s"]
    for v in scores.values():
        v["PAR2_speedup_vs_kissat_x"]=round(kiss/v["PAR2_s"],6)
        v["PAR2_speedup_vs_native_x"]=round(native/v["PAR2_s"],6)
        v["PAR2_speedup_vs_alt_x"]=round(alt/v["PAR2_s"],6)
    per_shard={str(i):{a:score([r for r in rows if r["arm"]==a and r["shard"]==i])
             for a in ARMS} for i in range(SHARDS)}
    choices={sha:next(r for r in rr if r["arm"]=="native_shape_gate")["seed_choice"]
             for sha,rr in bysha.items()}
    samples={sha:dict(shape_gate_seed=choices[sha],features=rr[0]["features"],
        per_arm={a:[dict(rep=r["rep"],status=r["status"],E2E_s=r["wall_E2E_s"])
                    for r in rr if r["arm"]==a] for a in ARMS})
        for sha,rr in bysha.items()}
    paired={}
    lookup={(r["source_sha256"],r["rep"],r["arm"]):r for r in rows}
    for arm in ARMS:
        if arm=="native_altseed":continue
        d=[]
        for c in m["selected_cases"]:
            for rep in range(REPS):
                a=lookup[(c["sha256"],rep,arm)]
                b=lookup[(c["sha256"],rep,"native_altseed")]
                d.append((a["wall_E2E_s"] if accepted(a) else 2*CAP)-
                         (b["wall_E2E_s"] if accepted(b) else 2*CAP))
        paired[arm]=dict(wins=sum(x<-.02 for x in d),
            losses=sum(x>.02 for x in d),ties=sum(abs(x)<=.02 for x in d),
            max_gain_s=round(min(d),6),max_regression_s=round(max(d),6))
    report=dict(protocol=PROTO,source_count=COUNT,total_trials=len(rows),
       one_logical_CPU_per_arm=True,no_parallel_children=True,
       original_sha_verified=True,not_blind=True,
       original_sha_previously_used_by_equiv9=True,
       selection_no_reselection=True,sourceonly_frozen_shape_gate=True,
       shape_gate_alt_formulas=sum(x=="alt" for x in choices.values()),
       shape_gate_base_formulas=sum(x=="base" for x in choices.values()),
       original_SAT_witness_verified=True,
       UNSAT_agreement_SHA=sorted(agree),
       no_independent_UNSAT_LRAT=True,
       no_auto_promotion=True,E2E_includes_SHA_and_parse=True,
       scores=scores,paired_vs_alt=paired,per_shard=per_shard,per_SHA=samples)
    save(ROOT/"report.json",report)
    print("SEEDGATE1_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="shard":shard(a.shard)
    else:
        globals()[a.action]()
        if a.action=="verify":print("SEEDGATE1_VERIFY_PASS",flush=True)
