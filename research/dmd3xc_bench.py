#!/usr/bin/env python3
"""DMD3X-C: conditional branch-UP novelty versus whole-CNF root-UP and shadow.

All selected clauses are independently exhaustive-replay certified from
their original CNF sources. Conditional UP novelty is HEURISTIC ONLY;
the witness/different-solver path establishes no formal CDCL cost guarantee.
"""
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
import dmd3x_bench as d3

PROTO="DRNAS-DMD3XC-CONDITIONAL-PROGRESS-28SHA-7ARM-2REP-392-E2E-v1"
GATE_PROTOCOL="DMD3XC-CONDITIONAL-UP-v1"
ROOT=pathlib.Path("mre_dmd3xc")
GATE=ROOT/"bin/dmd3xc_gate"
DMD3X=pathlib.Path("mre_dmd3x/bin/dmd3x_native")
ARMS=("kissat_original","dmd1_15_active","dmd3x_60_gate",
      "dmd3x_60_all","dmd3xc_8_active","dmd3xc_16_shadow",
      "dmd3xc_16_active")
REPS=2
SHARDS=4
CAP=6.0

def need(ok,message):
    if not ok:
        raise RuntimeError("DMD3XC_FAIL_CLOSED "+str(message))

def cases():
    d1.ROOT=ROOT
    cs=d1.cases()
    need(len(cs)==28 and sum(x["cohort"]=="reused_equiv7_original"
        for x in cs)==24 and len({x["sha256"] for x in cs})==28,
        "frozen original CNF cohort drift")
    return cs

def signature(lemmas):
    return hashlib.sha256(json.dumps(
        [p["clause"] for p in lemmas],sort_keys=True,
        separators=(",",":")).encode()).hexdigest()

def run_trial(case,arm,rep):
    cpu=sorted(os.sched_getaffinity(0))[0]
    start=time.monotonic()
    original=pathlib.Path(case["path"])
    need(original.is_file() and d1.sha(original)==case["sha256"],
         "original SHA drift")
    if arm in ("kissat_original","dmd1_15_active",
               "dmd3x_60_gate","dmd3x_60_all"):
        # Same frozen reference backend and protocol as DMD3X.
        row=d3.trial(case,arm,rep)
        return dict(protocol=PROTO,arm=arm,rep=rep,
            source_sha256=case["sha256"],cohort=case["cohort"],
            filename=case["filename"],cap_s=CAP,
            cpu_affinity=row["cpu_affinity"],allocated_logical_cpus=1,
            status=row["status"],E2E_s=row["E2E_s"],
            PAR2_s=row["PAR2_s"],
            SAT_original_witness_verified=row["SAT_original_witness_verified"],
            UNSAT_independent_LRAT=False,
            prep_wall_s=row["prep_wall_s"],
            candidate_lemmas=row["candidate_lemmas"],
            added=row["added"],
            conditional_directions=0,selected_directions=0,
            branch_candidates_positive=0,gate_considered=0,
            gate_budget_exhausted=False,
            active=(arm not in ("kissat_original",)),
            selection_reason="unchanged_baseline",
            candidate_signature=None,selection_signature=None,
            proof_checked=True)
    with tempfile.TemporaryDirectory(prefix="dmd3xc-") as td:
        temp=pathlib.Path(td)
        _,clauses=d1.read_cnf(original)
        all_aug=temp/"all_aug.cnf"
        proof_path=temp/"all_proof.json"
        rc,out,err,dt,_,timed=d1.run_process(
            [DMD3X,original,all_aug,proof_path,60,64,"all"],
            CAP,cpu)
        need(not timed and rc==0 and proof_path.is_file(),
             "native source-wide derivation failed: "+err[-500:])
        candidates=all_aug if all_aug.is_file() else original
        proof=d3.process_proof(original,all_aug,proof_path,"all")
        need(len(proof["lemmas"])<=24,"too many original-source lemmas")
        chosen_8=(arm=="dmd3xc_8_active")
        max_selected=8 if chosen_8 else 16
        selected_aug=temp/"conditional_aug.cnf"
        gate_path=temp/"gate.json"
        # Entire gate including source parsing and watched UP on ONE pinned
        # CPU is charged to E2E. This is controlled branch-UP, not live CDCL.
        rc,out,err,dt,_,timed=d1.run_process(
            [GATE,original,candidates,selected_aug,gate_path,
             250,max_selected],CAP,cpu)
        if rc==75 and not timed:
            # Explicit fail-closed soft cap for very large original sources.
            gate=dict(protocol=GATE_PROTOCOL,
                candidates=len(proof["lemmas"]),selected=0,
                selected_indices=[],considered=0,positive_candidates=0,
                novel_directions_total=0,selected_directions=0,
                budget_exhausted=True,selection_reason="abstain_budget")
        else:
            need(not timed and rc==0 and gate_path.is_file(),
                 "native conditional UP gate error: "+err[-500:])
            gate=json.loads(gate_path.read_text())
        need(gate["protocol"]==GATE_PROTOCOL and
             gate["candidates"]==len(proof["lemmas"]) and
             gate["selected"]==len(gate["selected_indices"]) and
             gate["selected"]<=max_selected,"gate metadata corruption")
        indices=gate["selected_indices"]
        need(len(set(indices))==len(indices) and
             all(type(i)==int and 0<=i<len(proof["lemmas"]) for i in indices),
             "index mismatch or repeated lemma")
        subset=[proof["lemmas"][i] for i in indices]
        need((selected_aug.is_file()) == bool(subset),"select output mismatch")
        subset_proof=dict(protocol="DMD1-ANF-LOCAL-EXHAUSTIVE-v1",
                          lemmas=subset)
        d1.proof_replay(original,selected_aug,subset_proof)
        active=arm!="dmd3xc_16_shadow"
        target=selected_aug if active and subset else original
        elapsed_prep=time.monotonic()-start
        left=CAP-elapsed_prep
        if left<=0:
            status,verified,solver_cpu="TIMEOUT",False,0.0
        else:
            rc,out,err,dt,solver_cpu,timed=d1.run_process(
                [d1.KISSAT,target],left,cpu)
            if timed:status,verified="TIMEOUT",False
            else:status,verified=d1.outcome(rc,out,clauses)
        elapsed=time.monotonic()-start
        return dict(protocol=PROTO,arm=arm,rep=rep,
            source_sha256=case["sha256"],cohort=case["cohort"],
            filename=case["filename"],cap_s=CAP,
            cpu_affinity=[cpu],allocated_logical_cpus=1,
            status=status,E2E_s=round(elapsed,6),
            PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
            SAT_original_witness_verified=verified,
            UNSAT_independent_LRAT=False,
            prep_wall_s=round(elapsed_prep,6),
            candidate_lemmas=len(proof["lemmas"]),added=len(subset),
            conditional_directions=gate["novel_directions_total"],
            selected_directions=gate["selected_directions"],
            branch_candidates_positive=gate["positive_candidates"],
            gate_considered=gate["considered"],
            gate_budget_exhausted=gate["budget_exhausted"],
            selection_reason=gate["selection_reason"],
            active=active,
            candidate_signature=signature(proof["lemmas"]),
            selection_signature=signature(subset),
            proof_checked=True)

def write_dimacs(p,n,clauses):
    p.write_text("p cnf %d %d\n"%(n,len(clauses))+
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses))

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    cpu=sorted(os.sched_getaffinity(0))[0]
    rc,out,err,_,_,timed=d1.run_process([GATE,"selftest"],4,cpu)
    need(rc==0 and not timed and "DMD3XC_SELFTEST_PASS" in out,
         "native conditional propagation selftest failed "+err[-500:])
    randomizer=random.Random(32971)
    with tempfile.TemporaryDirectory(prefix="dmd3xc-proof-") as td:
        temp=pathlib.Path(td)
        samples=[([(1,2,3),(1,2,-3)],3),(
            [(1,-2,3),(1,2,-3),(2,3),(-2,-3)],3)]
        for idx in range(30):
            n=randomizer.randint(2,7)
            clauses=[]
            for j in range(randomizer.randint(3,17)):
                k=randomizer.randint(1,min(4,n))
                chosen=randomizer.sample(range(1,n+1),k)
                clauses.append(tuple(v if randomizer.getrandbits(1) else -v
                                     for v in chosen))
            samples.append((clauses,n))
        checked=0;candidates=0;selected=0;novel=0
        for i,(clauses,n) in enumerate(samples):
            original=temp/"source.cnf"
            write_dimacs(original,n,clauses)
            all_aug=temp/"all.cnf";all_aug.unlink(missing_ok=True)
            cert=temp/"proof.json"
            rc,out,err,_,_,timed=d1.run_process(
                [DMD3X,original,all_aug,cert,100,64,"all"],4,cpu)
            need(not timed and rc==0,"ANF selftest derive failed "+err[-400:])
            p=d3.process_proof(original,all_aug,cert,"all")
            cand=all_aug if all_aug.is_file() else original
            filtered=temp/"conditional.cnf";filtered.unlink(missing_ok=True)
            gate=temp/"metrics.json"
            rc,out,err,_,_,timed=d1.run_process(
                [GATE,original,cand,filtered,gate,1000,16],4,cpu)
            need(not timed and rc==0,"conditional test failed "+err[-400:])
            met=json.loads(gate.read_text())
            subset=[p["lemmas"][j] for j in met["selected_indices"]]
            d1.proof_replay(original,filtered,
                dict(protocol="DMD1-ANF-LOCAL-EXHAUSTIVE-v1",lemmas=subset))
            final=d1.read_cnf(filtered)[1] if filtered.is_file() else clauses
            for bits in range(1<<n):
                model={v+1:bool(bits&(1<<v)) for v in range(n)}
                need(d1.holds(clauses,model)==d1.holds(final,model),
                    "exhaustive original semantic change in test %d"%i)
            checked+=1
            candidates+=len(p["lemmas"])
            selected+=len(subset)
            novel+=met["novel_directions_total"]
        print("DMD3XC_PYTHON_SELFTEST_PASS",json.dumps(
            dict(cases=checked,candidates=candidates,selected=selected,
                 controlled_conditional_novelty=novel,
                 all_original_models_preserved=True)),flush=True)

def bench(shard):
    cs=cases();need(0<=shard<SHARDS,"bad shard")
    ROOT.mkdir(exist_ok=True)
    cpu=sorted(os.sched_getaffinity(0))[0]
    os.sched_setaffinity(0,{cpu})
    rows=[]
    for i,case in enumerate(cs):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(int(case["sha256"][:12],16)+rep).shuffle(arms)
            for arm in arms:
                row=run_trial(case,arm,rep)
                rows.append(row)
                print("DMD3XC_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==98,"missing paired shard rows")
    (ROOT/("shard-%d.json"%shard)).write_text(json.dumps(rows,sort_keys=True))
    print("DMD3XC_SHARD_PASS",shard,len(rows),flush=True)

def aggregate(rows):
    return dict(n=len(rows),
        solved=sum(r["status"]!="TIMEOUT" for r in rows),
        verified_SAT=sum(r["SAT_original_witness_verified"] for r in rows),
        UNSAT_backend_no_LRAT=sum(r["status"]=="UNSAT" for r in rows),
        PAR2_s=round(sum(r["PAR2_s"] for r in rows),5),
        E2E_s=round(sum(r["E2E_s"] for r in rows),5),
        preprocessing_s=round(sum(r["prep_wall_s"] for r in rows),5),
        candidate_lemmas=sum(r["candidate_lemmas"] for r in rows),
        selected_lemmas=sum(r["added"] for r in rows),
        novel_branch_directions=sum(r["conditional_directions"] for r in rows),
        selected_branch_directions=sum(r["selected_directions"] for r in rows),
        soft_gate_timeouts=sum(r["gate_budget_exhausted"] for r in rows))

def audit():
    cs=cases()
    rows=[];per_shard={}
    for shard in range(SHARDS):
        p=ROOT/("shard-%d.json"%shard)
        need(p.is_file(),"missing shard "+str(shard))
        data=json.loads(p.read_text())
        need(len(data)==98,"invalid trial count per shard")
        rows+=data
        per_shard[str(shard)]={
            arm:aggregate([r for r in data if r["arm"]==arm])
            for arm in ARMS}
    expected={(c["sha256"],rep,arm) for c in cs
        for rep in range(REPS) for arm in ARMS}
    actual={(r["source_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==392 and len(actual)==392 and actual==expected,
         "392 frozen original SHA source matches missing")
    sources={c["sha256"]:c for c in cs}
    for r in rows:
        need(r["protocol"]==PROTO and
             r["cohort"]==sources[r["source_sha256"]]["cohort"] and
             r["allocated_logical_cpus"]==1 and len(r["cpu_affinity"])==1,
             "invalid cohort/protocol/core")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "SAT witness not checked on original")
        need(r["proof_checked"],"missing exhaustive source proof")
        need(abs(r["PAR2_s"]-(12.0 if r["status"]=="TIMEOUT" else r["E2E_s"]))<.0001,
             "incorrect PAR2")
    for c in cs:
        for rep in range(REPS):
            rs=[r for r in rows if r["source_sha256"]==c["sha256"]
                and r["rep"]==rep]
            results={r["status"] for r in rs if r["status"]!="TIMEOUT"}
            need(len(results)<=1,"conflicting SAT and UNSAT result")
            active=next(r for r in rs if r["arm"]=="dmd3xc_16_active")
            shadow=next(r for r in rs if r["arm"]=="dmd3xc_16_shadow")
            need(active["candidate_signature"]==shadow["candidate_signature"]
                 and active["selection_signature"]==shadow["selection_signature"]
                 and active["added"]==shadow["added"],
                 "active/shadow algebra candidate mismatch")
    scores={arm:aggregate([r for r in rows if r["arm"]==arm])
            for arm in ARMS}
    per_cohort={cohort:{
        arm:aggregate([r for r in rows if r["cohort"]==cohort
            and r["arm"]==arm]) for arm in ARMS}
        for cohort in sorted(set(r["cohort"] for r in rows))}
    k=scores["kissat_original"]["PAR2_s"]
    baseline={(r["source_sha256"],r["rep"]):r for r in rows
        if r["arm"]=="kissat_original"}
    pairs={}
    for arm in ARMS:
        if arm=="kissat_original":continue
        delta=[r["PAR2_s"]-baseline[(r["source_sha256"],r["rep"])]["PAR2_s"]
               for r in rows if r["arm"]==arm]
        pairs[arm]=dict(wins=sum(d<-.01 for d in delta),
            losses=sum(d>.01 for d in delta),
            ties=sum(abs(d)<=.01 for d in delta),
            best_PAR2_gain_s=round(min(delta),5),
            worst_PAR2_regression_s=round(max(delta),5))
    result=dict(protocol=PROTO,total_trials=len(rows),sources=28,
        reused_original_SHA=24,synthetic_controls=4,
        cap_s=CAP,one_logical_cpu_per_child=True,not_blind=True,
        all_source_local_certificates_independently_replayed=True,
        conditional_UP_is_controlled_not_live_CDCL=True,
        independent_UNSAT_LRAT=False,
        no_auto_promotion=True,scores=scores,per_shard=per_shard,
        per_cohort=per_cohort,paired=pairs,
        PAR2_speedup_vs_kissat={
            arm:round(k/score["PAR2_s"],6) for arm,score in scores.items()})
    (ROOT/"audit.json").write_text(json.dumps(result,sort_keys=True,indent=2))
    print("DMD3XC_FINAL",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","bench","audit"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    try:
        if args.action=="selftest":selftest()
        elif args.action=="bench":bench(args.shard)
        else:audit()
    except Exception as exc:
        print("DMD3XC_FATAL",str(exc),file=sys.stderr,flush=True)
        raise
