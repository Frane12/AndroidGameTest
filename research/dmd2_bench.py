#!/usr/bin/env python3
"""DRNAS DMD2: conservative UP-novelty gate for DMD1 local ANF lemmas.

The unchanged DMD1 generator produces source-bag-exhaustively proved lemmas;
an independent Python replay checks those proofs BEFORE gating; a native
two-watched-literal UP gate compares propagation on the ORIGINAL CNF before
selectively appending a subset. One pinned logical CPU. 6s full wall cap.
Diagnostic DEVELOPMENT cohort: 24 reused EQUIV7 originals + 4 synthetic toys.
"""
from __future__ import annotations
import argparse, collections, json, os, pathlib, random, resource
import tempfile, time
import dmd1_bench as d1

PROTO="DRNAS-DMD2-ANF-UP-NOVELTY-24SEEN-4TOY-5ARM-2REP-6S-v1"
ARMS=("kissat_original","dmd1_shadow","dmd1_active",
      "dmd2_gate_shadow","dmd2_gate_active")
REPS=2; SHARDS=4; CAP=6.0
ROOT=pathlib.Path("mre_dmd2")
BIN=pathlib.Path("mre_dmd2/bin/dmd1_anf")
GATE=pathlib.Path("mre_dmd2/bin/dmd2_gate")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
DMD1_BUDGET_MS=15
GATE_BUDGET_MS=60
d1.ROOT=ROOT
def need(ok,reason):
    if not ok:raise RuntimeError("DMD2_FAIL_CLOSED "+str(reason))
def cputime(which):
    u=resource.getrusage(which)
    return u.ru_utime+u.ru_stime
def src_cases():
    a=d1.cases()
    need(len(a)==28 and
         sum(c["cohort"]=="reused_equiv7_original" for c in a)==24 and
         sum(c["cohort"]=="synthetic_toy" for c in a)==4,
         "development cohort drift")
    return a
def default_gate():
    return dict(considered=0,candidates=0,selected=0,
       novel_directions=0,timed_out=False,budget_ms=GATE_BUDGET_MS,
       wall_s=0,seen_types={},selected_types={},selected_indices=[])
def trial(case,arm,rep):
    need(arm in ARMS and 0<=rep<REPS,"invalid arm/repetition")
    cpu=min(os.sched_getaffinity(0))
    original=pathlib.Path(case["path"])
    need(original.is_file() and d1.sha(original)==case["sha256"],
         "original input SHA mutated")
    begin=time.monotonic()
    self_before=cputime(resource.RUSAGE_SELF)
    child_before=cputime(resource.RUSAGE_CHILDREN)
    pre_cpu=0.
    proof=dict(groups=0,nonlinear_relations=0,lemmas=[],
               tested_assignments=0,abstain=False,timed_out=False)
    gate=default_gate()
    gate_status="NOT_APPLICABLE"
    status="TIMEOUT";verified=False
    solver_cpu=0.;target=original
    with tempfile.TemporaryDirectory(prefix="dmd2-") as td:
        tmp=pathlib.Path(td)
        n,clauses=d1.read_cnf(original)
        if arm!="kissat_original":
            augmented=tmp/"dmd1_augmented.cnf"
            proof_path=tmp/"dmd1_proof.json"
            remaining=max(0.001,CAP-(time.monotonic()-begin))
            rc,out,err,elapsed,cpu_use,timed=d1.run_process(
               [BIN,original,augmented,proof_path,DMD1_BUDGET_MS,48],
               remaining,cpu)
            pre_cpu+=cpu_use
            need(not timed and rc==0 and proof_path.is_file(),
                 "legacy DMD1 local proof discovery failed: "+err[-400:])
            proof=json.loads(proof_path.read_text())
            nn,original_clauses=d1.proof_replay(original,augmented,proof)
            need(nn==n and original_clauses==clauses,"proof replay original drift")
            lemmas=proof["lemmas"]
            if arm=="dmd1_active" and lemmas:
                target=augmented
            if arm.startswith("dmd2_gate"):
                if lemmas:
                    selected=tmp/"gated.cnf"
                    remaining=max(0.001,CAP-(time.monotonic()-begin))
                    rc,out,err,elapsed,cpu_use,timed=d1.run_process(
                       [GATE,original,augmented,selected,GATE_BUDGET_MS],
                       min(remaining,1.0),cpu)
                    pre_cpu+=cpu_use
                    if timed or rc!=0:
                        gate_status="ABSTAIN_NO_MODIFICATIONS"
                        need(not selected.exists(),
                             "partial output from failed propagation gate")
                    else:
                        records=[z[len("DMD2_GATE "):]
                          for z in out.splitlines() if z.startswith("DMD2_GATE ")]
                        need(len(records)==1,"missing native propagation-gate statistics")
                        gate=json.loads(records[0])
                        ids=gate["selected_indices"]
                        need(len(ids)==gate["selected"] and
                             len(set(ids))==len(ids) and
                             all(type(i)==int and 0<=i<len(lemmas) for i in ids),
                             "selected lemma indices mismatch")
                        need(gate["considered"]<=gate["candidates"]==len(lemmas),
                             "candidate coverage mismatch")
                        if ids:
                            need(selected.is_file(),"gate selected clauses but omitted output")
                            nn,output=d1.read_cnf(selected)
                            need(nn==n and output[:len(clauses)]==clauses,
                                 "original CNF prefix modified")
                            expected=[tuple(lemmas[i]["clause"]) for i in ids]
                            need(output[len(clauses):]==expected,
                                 "selected lemma subset mismatch")
                        else:
                            need(not selected.exists(),"gate emitted empty copied output")
                        gate_status="OK_TIMED" if gate["timed_out"] else "OK"
                        if arm=="dmd2_gate_active" and ids:
                            target=selected
                else: gate_status="NO_CANDIDATES"
        remaining=CAP-(time.monotonic()-begin)
        if remaining>0.001:
            rc,out,err,elapsed,solver_cpu,timed=d1.run_process(
              [KISSAT,target],max(0.001,remaining),cpu)
            if not timed:
                status,verified=d1.outcome(rc,out,clauses)
            else:status="TIMEOUT";verified=False
    e2e=time.monotonic()-begin
    if status=="TIMEOUT" and e2e>=CAP:e2e=CAP
    need(status!="SAT" or verified,"SAT original model failed")
    return dict(protocol=PROTO,arm=arm,rep=rep,cohort=case["cohort"],
        source_sha256=case["sha256"],original_file=case["filename"],
        status=status,SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,
        e2e_s=round(e2e,6),
        PAR2_s=round(e2e if status!="TIMEOUT" else 2*CAP,6),
        cpu=[cpu],solver_CPU_s=round(solver_cpu,6),
        prep_child_CPU_s=round(pre_cpu,6),
        full_process_CPU_s=round(
          cputime(resource.RUSAGE_SELF)-self_before+
          cputime(resource.RUSAGE_CHILDREN)-child_before,6),
        lemmas=len(proof["lemmas"]),
        nonlinear_relations=proof["nonlinear_relations"],groups=proof["groups"],
        proof_replayed=(arm!="kissat_original"),
        dmd1_discovery_timeout=proof["timed_out"],
        gate_status=gate_status,
        gated_lemmas=gate["selected"],gate_novel_directions=gate["novel_directions"],
        gate_candidates=gate["candidates"],
        gate_considered=gate["considered"],
        gate_timed_out=gate["timed_out"],
        gate_types_seen=gate["seen_types"],
        gate_types_selected=gate["selected_types"],
        cap_s=CAP)
def selftest():
    need(BIN.is_file() and GATE.is_file() and KISSAT.is_file(),"missing binaries")
    a=src_cases()
    need(len(a)==28 and len(ARMS)==5 and CAP==6,"protocol mismatch")
    # The DMD1 42-case proof replay runs as an independent exercise too.
    original=d1.BIN;d1.BIN=BIN
    try:d1.selftest()
    finally:d1.BIN=original
    # Non-solver gate smoke-test on one synthetic toy, with exact proof replay.
    toy=next(c for c in a if c["cohort"]=="synthetic_toy")
    r=trial(toy,"dmd2_gate_active",0)
    need(r["status"]=="SAT" and r["SAT_original_witness_verified"],
         "toy original SAT witness failed")
    need(r["gate_status"].startswith("OK") and r["gate_candidates"]>=1,
         "gate not exercised on synthetic toy")
    print("DMD2_SELFTEST_PASS",json.dumps(dict(legacy_proofs=42,gate_toy=r["gate_types_selected"],
       toy_verified=r["SAT_original_witness_verified"],all_one_cpu=True)),flush=True)
def bench(shard):
    need(0<=shard<SHARDS,"invalid shard")
    cs=src_cases();ROOT.mkdir(exist_ok=True)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for i,case in enumerate(cs):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(int(case["sha256"][:7],16)+rep).shuffle(arms)
            for arm in arms:
                result=trial(case,arm,rep)
                rows.append(result)
                print("DMD2_TRIAL",json.dumps(result,sort_keys=True),flush=True)
    need(len(rows)==70,"incomplete shard")
    (ROOT/f"shard-{shard}.json").write_text(json.dumps(rows,sort_keys=True))
    print("DMD2_SHARD_PASS",shard,len(rows),flush=True)
def audit():
    cs=src_cases()
    rows=[]
    for shard in range(SHARDS):
        p=ROOT/f"shard-{shard}.json"
        need(p.is_file(),"missing shard artifact "+str(p))
        a=json.loads(p.read_text())
        need(len(a)==70,"shard count mismatch")
        rows+=a
    expected={(c["sha256"],rep,arm) for c in cs
              for rep in range(REPS) for arm in ARMS}
    keys={(r["source_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(expected)==len(keys)==280 and keys==expected,
         "missing/duplicate original SHA paired trial")
    for r in rows:
        need(r["protocol"]==PROTO and len(r["cpu"])==1 and r["cap_s"]==CAP,
             "protocol or CPU drift")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "unverified SAT original witness")
        need(r["arm"].startswith("dmd2_gate") or r["gated_lemmas"]==0,
             "non-gate variant applied gate")
        need(r["gated_lemmas"]<=r["lemmas"],"selected more than proved")
    scores={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        bycohort={}
        for cohort in ("reused_equiv7_original","synthetic_toy"):
            b=[r for r in a if r["cohort"]==cohort]
            bycohort[cohort]=dict(trials=len(b),
               solved=sum(r["status"]!="TIMEOUT" for r in b),
               PAR2_s=round(sum(r["PAR2_s"] for r in b),5))
        seen=collections.Counter()
        selected=collections.Counter()
        for r in a:
            seen.update(r["gate_types_seen"])
            selected.update(r["gate_types_selected"])
        scores[arm]=dict(trials=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
             SAT_verified=sum(r["status"]=="SAT" for r in a),
             UNSAT_backend_no_LRAT=sum(r["status"]=="UNSAT" for r in a),
             PAR2_s=round(sum(r["PAR2_s"] for r in a),6),
             E2E_s=round(sum(r["e2e_s"] for r in a),6),
             full_CPU_s=round(sum(r["full_process_CPU_s"] for r in a),6),
             proved_lemmas=sum(r["lemmas"] for r in a),
             discovered_nonlinear=sum(r["nonlinear_relations"] for r in a),
             gate_considered=sum(r["gate_considered"] for r in a),
             gate_selected=sum(r["gated_lemmas"] for r in a),
             gate_novel_directions=sum(r["gate_novel_directions"] for r in a),
             gate_fallback=sum(r["gate_status"]=="ABSTAIN_NO_MODIFICATIONS" for r in a),
             gate_types_seen=dict(seen),gate_types_selected=dict(selected),
             cohorts=bycohort)
    for a in scores.values():
        a["PAR2_vs_Kissat_pct"]=round(100*(a["PAR2_s"]/scores["kissat_original"]["PAR2_s"]-1),5)
    paired={}
    for arm in ARMS:
        if arm=="kissat_original":continue
        wins=losses=ties=0
        for source in cs:
            data=[r for r in rows if r["source_sha256"]==source["sha256"]]
            b=sum(r["PAR2_s"] for r in data if r["arm"]=="kissat_original")
            t=sum(r["PAR2_s"] for r in data if r["arm"]==arm)
            if t<b-.05:wins+=1
            elif b<t-.05:losses+=1
            else:ties+=1
        paired[arm]=dict(wins_vs_original=wins,losses_vs_original=losses,ties=ties)
    result=dict(protocol=PROTO,original_sources=24,synthetic_toys=4,
       total_trials=280,reps=REPS,cap_s=CAP,
       single_logical_cpu_pinned=True,
       not_blind=True,not_new_original_sources=True,
       local_implication_proofs_replayed=True,
       UNSAT_independent_LRAT=False,
       no_auto_promotion=True,
       score_definition="potential propagation novelty under sampled assumptions, not CDCL trail improvement",
       scores=scores,paired=paired)
    (ROOT/"report.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("DMD2_FINAL",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="bench":bench(a.shard)
    else:audit()
