#!/usr/bin/env python3
"""DMD3X: frozen source-paired single-core E2E structural ANF / full-BCP audit."""
import argparse
import hashlib
import json
import os
import pathlib
import random
import sys
import tempfile
import time

import dmd1_bench as d1
import dmd2_bench as d2

PROTO="DRNAS-DMD3X-NATIVE-STRUCTURE-ROOTBCP-28SOURCE-7ARM-392-E2E-v1"
ARMS=("kissat_original","dmd1_15_active","dmd2_20_active",
      "dmd3x_20_gate","dmd3x_60_shadow","dmd3x_60_gate","dmd3x_60_all")
REPS=2
SHARDS=4
CAP=6.0
ROOT=pathlib.Path("mre_dmd3x")
BIN=ROOT/"bin/dmd3x_native"

def need(condition,message):
    if not condition:raise RuntimeError("DMD3X_AUDIT_REFUSED "+message)
def cases():
    d1.ROOT=ROOT
    cs=d1.cases()
    need(len(cs)==28 and
         sum(x["cohort"]=="reused_equiv7_original" for x in cs)==24 and
         len({x["sha256"] for x in cs})==28,"source freeze drift")
    return cs

def process_proof(original, aug, cert, expected_mode):
    p=json.loads(cert.read_text())
    need(p["dmd3x_protocol"]=="DMD3X-NATIVE-STRUCTURE-ROOT-BCP-v1",
         "DMD3X version drift")
    need(p["gate_mode"]==expected_mode,"wrong gate mode")
    need(p["selected_lemmas"]==len(p["lemmas"]),"selected count mismatch")
    need(p["selected_lemmas"]<=p["candidate_lemmas"]<=24,
         "invalid candidate count")
    need(p["full_formula_clauses"]==len(d1.read_cnf(original)[1]),
         "source length mismatch")
    need(p["root_BCP_new_units"]>=0,"invalid BCP count")
    if expected_mode=="gate":
        if p["selection_reason"]=="full_bcp_new_propagation":
            need(p["full_BCP_probed"] and
                 (p["root_BCP_new_units"]>0 or p["root_BCP_new_conflict"]),
                 "gated without BCP novelty")
        else:
            need(not p["lemmas"],"gate accepts non-novel lemma")
    d1.proof_replay(original,aug,p)
    return p

def trial(case,arm,rep):
    cpu=sorted(os.sched_getaffinity(0))[0]
    start=time.monotonic()
    with tempfile.TemporaryDirectory(prefix="dmd3x-") as td:
        temp=pathlib.Path(td)
        source=pathlib.Path(case["path"])
        n,original=d1.read_cnf(source)
        target=source
        metrics=dict(prep_wall_s=0.0,candidate_lemmas=0,added=0,
            groups=0,nonlinear_relations=0,BCP_new_units=0,
            BCP_new_conflict=False,BCP_probed=False,
            selection_reason="not_applicable",seed_probes=0,
            skipped_bags=0,parse_ms=0.0,mining_ms=0.0,
            proof_checked=False,original_sha256=case["sha256"])
        if arm in ("kissat_original","dmd1_15_active","dmd2_20_active"):
            # Exact DMD2 frozen baseline harness, same core/pinned Kissat,
            # same 6s cap and independent DMD1/DMD2 proof replay.
            original_arm="kissat_original" if arm=="kissat_original" else arm
            row=d2.run_trial(case,original_arm,rep)
            result=dict(protocol=PROTO,arm=arm,rep=rep,
                source_sha256=case["sha256"],cohort=case["cohort"],
                filename=case["filename"],cap_s=CAP,
                cpu_affinity=row["cpu_affinity"],allocated_logical_cpus=1,
                status=row["status"],E2E_s=row["E2E_s"],
                PAR2_s=row["PAR2_s"],
                SAT_original_witness_verified=row["SAT_original_witness_verified"],
                UNSAT_independent_LRAT=False,
                prep_wall_s=row["prep_wall_s"],
                candidate_lemmas=row["added"],added=row["added"],
                groups=0,nonlinear_relations=row["nonlinear_relations"],
                BCP_new_units=row["new_bcp_units"],
                BCP_new_conflict=False,BCP_probed=False,
                selection_reason="legacy_control",seed_probes=0,
                skipped_bags=0,parse_ms=0.0,mining_ms=0.0,
                proof_checked=row["proof_checked"] or arm=="kissat_original",
                original_sha256=case["sha256"],
                legacy_steps=row["steps_executed"],
                legacy_cycles=row["cycles_pruned"])
            return result
        mode="all" if arm=="dmd3x_60_all" else "gate"
        budget=20 if arm=="dmd3x_20_gate" else 60
        augmented=temp/"dmd3x_aug.cnf"
        cert=temp/"dmd3x_proof.json"
        rc,out,err,_,_,timed=d1.run_process(
            [BIN,source,augmented,cert,budget,64,mode],CAP,cpu)
        need(not timed and rc==0 and cert.is_file(),
             "native DMD3X failure "+err[-600:])
        p=process_proof(source,augmented,cert,mode)
        if p["lemmas"] and arm!="dmd3x_60_shadow":target=augmented
        metrics.update(prep_wall_s=round(time.monotonic()-start,6),
            candidate_lemmas=p["candidate_lemmas"],
            added=len(p["lemmas"]),groups=p["groups"],
            nonlinear_relations=p["nonlinear_relations"],
            BCP_new_units=p["root_BCP_new_units"],
            BCP_new_conflict=p["root_BCP_new_conflict"],
            BCP_probed=p["full_BCP_probed"],
            selection_reason=p["selection_reason"],
            seed_probes=p["seed_probes"],
            skipped_bags=p["skipped_bags"],
            parse_ms=p["native_parse_ms"],mining_ms=p["native_mining_ms"],
            proof_checked=True)
        remain=CAP-(time.monotonic()-start)
        if remain<=0:
            status,witness="TIMEOUT",False
        else:
            rc,out,err,_,_,timed=d1.run_process(
                [d1.KISSAT,target],remain,cpu)
            if timed: status,witness="TIMEOUT",False
            else:status,witness=d1.outcome(rc,out,original)
        elapsed=time.monotonic()-start
        return dict(protocol=PROTO,arm=arm,rep=rep,cohort=case["cohort"],
            filename=case["filename"],source_sha256=case["sha256"],
            cap_s=CAP,cpu_affinity=[cpu],allocated_logical_cpus=1,
            status=status,E2E_s=round(elapsed,6),
            PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
            SAT_original_witness_verified=witness,
            UNSAT_independent_LRAT=False,**metrics)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    rnd=random.Random(3019)
    tests=[]
    with tempfile.TemporaryDirectory(prefix="dmd3x-selftest-") as td:
        temp=pathlib.Path(td)
        tests.append([(1,-2,3),(1,2,-3),(2,3),(-2,-3)])
        tests.append([(1,2),(1,-2),(-1,3),(-1,-3)])
        for i in range(50):
            n=rnd.randint(2,7)
            clauses=[]
            for j in range(rnd.randint(4,18)):
                k=rnd.randint(1,min(n,4))
                vars=rnd.sample(range(1,n+1),k)
                clauses.append(tuple(v if rnd.randrange(2) else -v for v in vars))
            tests.append(clauses)
        passes=0;total_candidates=0,;total_selected=0
        for i,clauses in enumerate(tests):
            n=max(abs(x) for c in clauses for x in c)
            original=temp/"source.cnf"
            original.write_text("p cnf %d %d\n"%(n,len(clauses))+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            for mode in ("gate","all"):
                augmented=temp/"aug.cnf";cert=temp/"proof.json"
                augmented.unlink(missing_ok=True)
                rc,out,err,elapsed,_,timed=d1.run_process([
                    BIN,original,augmented,cert,120,64,mode],4,
                    sorted(os.sched_getaffinity(0))[0])
                need(not timed and rc==0,
                     "native test failed: "+err[-400:])
                p=process_proof(original,augmented,cert,mode)
                result=d1.read_cnf(augmented)[1] if augmented.exists() else clauses
                for bits in range(1<<n):
                    model={v+1:bool(bits & (1<<v)) for v in range(n)}
                    need(d1.holds(clauses,model)==d1.holds(result,model),
                         "semantic mismatch case %d/%s"%(i,mode))
                total_candidates+=p["candidate_lemmas"]
                total_selected+=p["selected_lemmas"]
                passes+=1
        print("DMD3X_SELFTEST_PASS",json.dumps(dict(
            cases=len(tests),mode_trials=passes,candidate_lemmas=total_candidates,
            selected_lemmas=total_selected,exhaustive_semantic_match=True)),flush=True)

def bench(shard):
    need(0<=shard<SHARDS,"invalid shard")
    c=cases();ROOT.mkdir(exist_ok=True)
    cpu=sorted(os.sched_getaffinity(0))[0]
    os.sched_setaffinity(0,{cpu})
    rows=[]
    for i,case in enumerate(c):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(int(case["sha256"][:12],16)+rep).shuffle(arms)
            for arm in arms:
                row=trial(case,arm,rep)
                rows.append(row)
                print("DMD3X_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==(len(c)//SHARDS)*REPS*len(ARMS),
         "missing trials")
    (ROOT/("shard-%d.json"%shard)).write_text(json.dumps(rows,sort_keys=True))
    print("DMD3X_SHARD_PASS",shard,len(rows),flush=True)

def summary(rows):
    return dict(trials=len(rows),
        solved=sum(x["status"]!="TIMEOUT" for x in rows),
        SAT_verified=sum(x["status"]=="SAT" and x["SAT_original_witness_verified"] for x in rows),
        UNSAT_backend_no_LRAT=sum(x["status"]=="UNSAT" for x in rows),
        PAR2_s=round(sum(x["PAR2_s"] for x in rows),5),
        E2E_s=round(sum(x["E2E_s"] for x in rows),5),
        prep_s=round(sum(x["prep_wall_s"] for x in rows),5),
        candidates=sum(x["candidate_lemmas"] for x in rows),
        added=sum(x["added"] for x in rows),
        full_BCP_novel_units=sum(x["BCP_new_units"] for x in rows),
        global_BCP_probes=sum(bool(x["BCP_probed"]) for x in rows),
        selection_reasons=dict(
            sorted((k,sum(x["selection_reason"]==k for x in rows))
            for k in {x["selection_reason"] for x in rows})))

def audit():
    cs=cases()
    expected={(x["sha256"],rep,arm) for x in cs
              for rep in range(REPS) for arm in ARMS}
    rows=[];per_shard={}
    for shard in range(SHARDS):
        p=ROOT/("shard-%d.json"%shard)
        need(p.is_file(),"missing shard")
        sample=json.loads(p.read_text())
        need(len(sample)==(len(cs)//SHARDS)*REPS*len(ARMS),
             "shard length")
        rows.extend(sample)
        per_shard[str(shard)]={arm:summary([x for x in sample if x["arm"]==arm])
                               for arm in ARMS}
    keys={(x["source_sha256"],x["rep"],x["arm"]) for x in rows}
    need(len(rows)==392 and len(keys)==392 and keys==expected,
         "not complete 392 exact source SHA pairs")
    by_sha={x["sha256"]:x for x in cs}
    for x in rows:
        need(x["protocol"]==PROTO and x["allocated_logical_cpus"]==1 and
             len(x["cpu_affinity"])==1 and
             x["cohort"]==by_sha[x["source_sha256"]]["cohort"],
             "metadata drift")
        need(x["status"]!="SAT" or x["SAT_original_witness_verified"],
             "unverified SAT on original")
        need(x["proof_checked"],"missing independent proof replay")
        need(abs(x["PAR2_s"]-(12 if x["status"]=="TIMEOUT" else x["E2E_s"]))<.0001,
             "PAR2 mismatch")
    for c in cs:
        for rep in range(REPS):
            valid={x["status"] for x in rows
                   if x["source_sha256"]==c["sha256"] and x["rep"]==rep
                   and x["status"]!="TIMEOUT"}
            need(len(valid)<=1,"contradictory SAT and UNSAT outcomes")
    scores={arm:summary([x for x in rows if x["arm"]==arm]) for arm in ARMS}
    per_cohort={cohort:{arm:summary([x for x in rows
                      if x["arm"]==arm and x["cohort"]==cohort])
                      for arm in ARMS}
                for cohort in sorted({x["cohort"] for x in rows})}
    k=scores["kissat_original"]["PAR2_s"]
    base={(x["source_sha256"],x["rep"]):x for x in rows if x["arm"]=="kissat_original"}
    paired={}
    for arm in ARMS:
        if arm=="kissat_original":continue
        deltas=[x["PAR2_s"]-base[(x["source_sha256"],x["rep"])]["PAR2_s"]
                for x in rows if x["arm"]==arm]
        paired[arm]=dict(wins=sum(d<-.01 for d in deltas),
                         ties=sum(abs(d)<=.01 for d in deltas),
                         losses=sum(d>.01 for d in deltas),
                         best_gain_s=round(min(deltas),5),
                         worst_regression_s=round(max(deltas),5))
    result=dict(protocol=PROTO,total_trials=len(rows),
        original_sources=24,synthetic_controls=4,
        frozen_source_selection="DMD1 EQUIV7 first24 SHA; used development sources",
        not_blind=True,one_logical_cpu_per_trial=True,
        cap_s=CAP,independent_local_clause_proofs=True,
        SAT_original_witness_verified=True,
        UNSAT_independent_LRAT=False,
        no_auto_promotion=True,scores=scores,
        per_cohort=per_cohort,per_shard=per_shard,paired=paired,
        PAR2_speedup_vs_original_kissat={
            arm:round(k/v["PAR2_s"],5) for arm,v in scores.items()})
    (ROOT/"audit.json").write_text(json.dumps(result,sort_keys=True,indent=2))
    print("DMD3X_FINAL",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    try:
        if a.action=="selftest":selftest()
        elif a.action=="bench":bench(a.shard)
        else:audit()
    except Exception as e:
        print("DMD3X_FATAL",str(e),file=sys.stderr,flush=True)
        raise
