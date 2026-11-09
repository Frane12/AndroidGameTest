#!/usr/bin/env python3
"""DRNAS DMD5-LIVE: proof-first conditional UP preselection plus real CaDiCaL trail.

24 original EQUIV7 SHA in unused second half of previous DMD3X development
sample + 4 synthetic controls, two repeats, eight arms. ALL statistics measured
on full original CNF, one logical CPU per trial, 8s E2E, PAR2. The holdout is
disjoint from DMD3X-C's 24 originals but is NOT fresh to the wider project.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import re
import resource
import sys
import tempfile
import time

import dmd1_bench as d1
import dmd3x_bench as d3

PROTO="DRNAS-DMD5-LIVE-COND-BRANCH-UP-DISJOINT24-4TOY-448-E2E-v1"
ARMS=("kissat_original","cadical_clean","cadical_observer_control",
      "dmd5_8_shadow","dmd5_8_active",
      "dmd5_16_shadow","dmd5_16_active","dmd5_all_active")
ROOT=pathlib.Path("mre_dmd5")
NATIVE=ROOT/"bin/dmd5_live_cdcl"
DMD3X=pathlib.Path("mre_dmd3x/bin/dmd3x_native")
COND=ROOT/"bin/dmd3xc_gate"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CAP=8.0
REPS=2
SHARDS=4

def need(ok,reason):
    if not ok:raise RuntimeError("DMD5_FAIL_CLOSED "+str(reason))

def signature(seq):
    return hashlib.sha256(json.dumps(seq,sort_keys=True,
        separators=(",",":")).encode()).hexdigest()

def cases():
    manifest=json.loads((d1.SOURCE/"manifest.json").read_text())
    need(len(manifest["cases"])==48 and
         manifest["sample_policy"].startswith("SHA-salted official"),
         "original SHA-frozen input cohort drift")
    ordered=sorted(manifest["cases"],key=lambda x:x["sha256"])
    old={x["sha256"] for x in ordered[:24]}
    new=ordered[24:]
    need(len(new)==24 and not old.intersection(x["sha256"] for x in new),
         "DMD3X-C training/holdout source overlap")
    result=[]
    for c in new:
        p=d1.SOURCE/"cases"/c["filename"]
        need(p.is_file() and d1.sha(p)==c["sha256"],
             "original CNF byte SHA changed: "+c["filename"])
        result.append(dict(cohort="DMD5_disjoint_E7_second_half",
            filename=c["filename"],sha256=c["sha256"],path=str(p)))
    result+=d1.toy_cases(ROOT/"toy")
    need(len(result)==28 and len({x["sha256"] for x in result})==28,
         "source sample collision")
    return result

def cpu_rusage(which):
    r=resource.getrusage(which)
    return r.ru_utime+r.ru_stime

def stats(stdout):
    data={}
    for line in stdout.splitlines():
        for key in ("decisions","conflicts","propagations","learned"):
            m=re.search(r"\b"+key+r"\s*:\s*([0-9][0-9,]*)",line)
            if m:data[key]=int(m.group(1).replace(",",""))
    return data

def verify_sat(stdout,clauses):
    assignment={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for part in line.split()[1:]:
            lit=int(part)
            if lit==0:continue
            need(abs(lit) not in assignment or assignment[abs(lit)]==(lit>0),
                 "conflicting native SAT assignment")
            assignment[abs(lit)]=lit>0
    need(bool(assignment) and all(
        any(assignment.get(abs(lit),None)==(lit>0) for lit in clause)
        for clause in clauses),"CaDiCaL SAT model fails original CNF")
    return True

def early_route(source,original_clause_count):
    # Source-only, precommitted conservative abstention. No outcome labels,
    # historical speed or hidden benchmark result is used.
    size=source.stat().st_size
    if size>12_000_000 or original_clause_count>125000:
        return "abstain_source_size"
    return "eligible"

def trial(case,arm,rep):
    need(arm in ARMS and rep in (0,1),"unregistered arm/rep")
    pinned=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{pinned})
    source=pathlib.Path(case["path"])
    need(source.is_file() and d1.sha(source)==case["sha256"],
         "original CNF sha mismatch")
    start=time.monotonic()
    pcpu0=cpu_rusage(resource.RUSAGE_SELF)+cpu_rusage(resource.RUSAGE_CHILDREN)
    n,original=d1.read_cnf(source)
    route="reference_no_preprocessing"
    status="TIMEOUT";sat_witness=False
    live={};cdcl={};candidate_count=0;selected_count=0
    positive_count=0;novel_directions=0;budget_expired=False
    selected_signature=signature([])
    source_signature=signature([])
    preprocessing_s=0.0
    with tempfile.TemporaryDirectory(prefix="dmd5-") as td:
        temp=pathlib.Path(td)
        candidates=source
        selected=source
        items=[]
        if arm not in ("kissat_original","cadical_clean"):
            route=early_route(source,len(original))
            if route=="eligible":
                augmented=temp/"all.cnf"
                cert=temp/"dmd3x.json"
                remain=CAP-(time.monotonic()-start)
                need(remain>.1,"preparation cap exhausted before DMD3X")
                rc,out,err,_,_,timed=d1.run_process(
                    [DMD3X,source,augmented,cert,60,64,"all"],
                    max(.1,remain),pinned)
                need(not timed and rc==0 and cert.is_file(),
                     "source-wide DMD3X failed "+err[-450:])
                proof=d3.process_proof(source,augmented,cert,"all")
                items=proof["lemmas"]
                candidate_count=len(items)
                candidates=augmented if augmented.is_file() else source
                source_signature=signature([x["clause"] for x in items])
                gate=temp/"gate.json"
                condensed=temp/"condensed.cnf"
                remain=CAP-(time.monotonic()-start)
                need(remain>.2,"preparation cap exhausted before conditional gate")
                # Single deterministic candidate list: same SHA/rep arm gives
                # the same list; signature is separately checked during audit.
                rc,out,err,_,_,timed=d1.run_process(
                    [COND,source,candidates,condensed,gate,250,16],
                    min(1.0,max(.1,remain)),pinned)
                if rc==75 and not timed:
                    # Budget fail-closed: source unchanged. A true 75 is
                    # explicit source-size parser deadline, not a solver SAT.
                    route="conditional_gate_timeout_abstain"
                    budget_expired=True
                    chosen=[]
                else:
                    need(rc==0 and not timed and gate.is_file(),
                         "conditional gate failed: "+err[-450:])
                    met=json.loads(gate.read_text())
                    need(met["protocol"]=="DMD3XC-CONDITIONAL-UP-v1" and
                         met["candidates"]==len(items) and
                         met["selected"]==len(met["selected_indices"]),
                         "gate counts mismatch")
                    chosen=met["selected_indices"]
                    need(len(set(chosen))==len(chosen) and
                         all(type(i)==int and 0<=i<len(items) for i in chosen),
                         "gate index outside independent source proofs")
                    positive_count=met["positive_candidates"]
                    novel_directions=met["novel_directions_total"]
                    budget_expired=met["budget_exhausted"]
                    if budget_expired:route="conditional_gate_budget_abstain"
                    elif not chosen:route="conditional_no_novelty"
                    else:route="conditional_positive"
                if chosen:
                    need(condensed.is_file(),"selected source-prefix CNF missing")
                    subset=[items[i] for i in chosen]
                    d1.proof_replay(source,condensed,dict(
                        protocol="DMD1-ANF-LOCAL-EXHAUSTIVE-v1",lemmas=subset))
                else:
                    need(not condensed.is_file(),"gate emitted output despite abstention")
            else:
                chosen=[]
            if arm=="dmd5_all_active":
                # Exactly all original-source locally proven lemmas. The
                # selector's work is *still charged to E2E* for comparability.
                selected=candidates
                selected_clauses=[x["clause"] for x in items]
            else:
                k=8 if arm in ("dmd5_8_active","dmd5_8_shadow") else 16
                keep=chosen[:k]
                if len(keep)<len(chosen):
                    # Rewrite precise selected subset, never blindly use 16
                    # when benchmarking an 8-clause dose.
                    target=temp/"top8.cnf"
                    with target.open("w") as f:
                        f.write("p cnf %d %d\n"%(n,len(original)+len(keep)))
                        for clause in original:
                            f.write(" ".join(map(str,clause))+" 0\n")
                        for j in keep:
                            f.write(" ".join(map(str,items[j]["clause"]))+" 0\n")
                    d1.proof_replay(source,target,dict(
                        protocol="DMD1-ANF-LOCAL-EXHAUSTIVE-v1",
                        lemmas=[items[j] for j in keep]))
                    selected=target
                elif keep and route=="conditional_positive":
                    selected=condensed
                selected_clauses=[items[j]["clause"] for j in keep]
            selected_count=len(selected_clauses)
            selected_signature=signature(selected_clauses)
            # For observer-only, identical selected candidates are passed
            # to native but callback counts no lemma evaluations.
        preprocessing_s=time.monotonic()-start
        remaining=CAP-preprocessing_s
        if remaining>.2:
            if arm=="kissat_original":
                rc,out,err,_,solver_cpu,timed=d1.run_process(
                    [KISSAT,source],remaining,pinned)
                if not timed:status,sat_witness=d1.outcome(rc,out,original)
            else:
                mode=("clean" if arm=="cadical_clean" else
                      "observer_control" if arm=="cadical_observer_control" else
                      "all_active" if arm.endswith("_active") else "shadow")
                native_cap=max(.2,remaining-.18)
                rc,out,err,_,_,timed=d1.run_process(
                    [NATIVE,source,selected,mode,f"{native_cap:.6f}"],
                    remaining,pinned)
                if not timed:
                    need(rc in (0,10,20),"native live CDCL error "+err[-500:])
                    body=[v.split("DMD5_RESULT ",1)[1] for v in out.splitlines()
                          if v.startswith("DMD5_RESULT ")]
                    need(len(body)==1,"missing native DMD5 metrics")
                    live=json.loads(body[0])
                    need(live["candidate_lemmas"]==selected_count and
                         live["mode"]==mode and not live["callback_error"] and
                         len(live["per_lemma_unit_events"])==
                           (0 if mode=="observer_control" else selected_count),
                         "DMD5 live observer vector integrity")
                    status=live["status"]
                    if rc==10:
                        need(status=="SAT" and live["model_original_verified"],
                             "native SAT result mismatch")
                        sat_witness=verify_sat(out,original)
                    elif rc==20:need(status=="UNSAT","native UNSAT result mismatch")
                    else:need(status=="TIMEOUT","native UNKNOWN result mismatch")
                    cdcl=stats(out)
    e2e=time.monotonic()-start
    if status=="TIMEOUT" and e2e>=CAP:e2e=CAP
    need(status!="SAT" or sat_witness,"unverified original SAT model")
    return dict(protocol=PROTO,cohort=case["cohort"],arm=arm,
        original_file=case["filename"],original_sha256=case["sha256"],
        rep=rep,status=status,cap_s=CAP,
        E2E_s=round(e2e,6),PAR2_s=round(e2e if status!="TIMEOUT" else 2*CAP,6),
        SAT_original_witness_verified=sat_witness,
        UNSAT_independent_LRAT=False,
        allocated_logical_cpus=1,cpu_affinity=[pinned],
        proof_checked=True,route=route,
        candidate_count=candidate_count,selected_count=selected_count,
        positive_count=positive_count,conditional_directions=novel_directions,
        conditional_budget_expired=budget_expired,
        prep_s=round(preprocessing_s,6),
        total_CPU_s=round(cpu_rusage(resource.RUSAGE_SELF)+
                          cpu_rusage(resource.RUSAGE_CHILDREN)-pcpu0,6),
        source_signature=source_signature,selected_signature=selected_signature,
        live=live,cdcl_stats=cdcl)

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    cs=cases()
    need(len(cs)==28 and len(ARMS)==8,"sample/arm preregistered drift")
    c=next(x for x in cs if x["cohort"]=="synthetic_toy")
    a=trial(c,"dmd5_16_active",0)
    s=trial(c,"dmd5_16_shadow",0)
    p=trial(c,"cadical_observer_control",0)
    need(a["status"]==s["status"]==p["status"]=="SAT" and
         a["SAT_original_witness_verified"] and
         a["selected_signature"]==s["selected_signature"]==
         p["selected_signature"] and
         a["source_signature"]==s["source_signature"]==
         p["source_signature"] and
         p["live"]["live_unit_opportunities"]==0,
         "active-shadow-CPCL placebo soundness mismatch")
    print("DMD5_SELFTEST_PASS",json.dumps(dict(
        selected=a["selected_count"],candidate_signature=a["selected_signature"],
        live_units=a["live"]["live_unit_opportunities"],
        shadow_units=s["live"]["live_unit_opportunities"],
        observer_placebo_units=p["live"]["live_unit_opportunities"],
        SAT_original_verified=True)),flush=True)

def bench(shard):
    cs=cases()
    need(0<=shard<SHARDS,"invalid shard")
    ROOT.mkdir(exist_ok=True)
    pin=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{pin})
    rows=[]
    for i,c in enumerate(cs):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                row=trial(c,arm,rep)
                rows.append(row)
                (ROOT/("shard-%d.json"%shard)).write_text(
                    json.dumps(rows,sort_keys=True))
                print("DMD5_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==112,"incomplete shard 112")
    print("DMD5_SHARD_PASS",shard,len(rows),flush=True)

def summarize(rows):
    return dict(trials=len(rows),
        solved=sum(r["status"]!="TIMEOUT" for r in rows),
        SAT_original_verified=sum(r["status"]=="SAT" and
            r["SAT_original_witness_verified"] for r in rows),
        UNSAT_backend_no_LRAT=sum(r["status"]=="UNSAT" for r in rows),
        PAR2_s=round(sum(r["PAR2_s"] for r in rows),6),
        E2E_s=round(sum(r["E2E_s"] for r in rows),6),
        total_CPU_s=round(sum(r["total_CPU_s"] for r in rows),6),
        prep_s=round(sum(r["prep_s"] for r in rows),6),
        candidates=sum(r["candidate_count"] for r in rows),
        selected=sum(r["selected_count"] for r in rows),
        branch_directions=sum(r["conditional_directions"] for r in rows),
        early_abstains=sum(r["route"]!="conditional_positive" and
            r["arm"] not in ("kissat_original","cadical_clean") for r in rows),
        live_unit_events=sum(r["live"].get("live_unit_opportunities",0) for r in rows),
        live_unique_lemmas=sum(r["live"].get("unique_lemmas_activated",0) for r in rows),
        counted_decisions=sum(r["cdcl_stats"].get("decisions",0) for r in rows),
        counted_conflicts=sum(r["cdcl_stats"].get("conflicts",0) for r in rows),
        cdcl_decision_rows=sum("decisions" in r["cdcl_stats"] for r in rows),
        cdcl_conflict_rows=sum("conflicts" in r["cdcl_stats"] for r in rows))

def audit():
    cs=cases()
    rows=[];per_shard={}
    for shard in range(SHARDS):
        p=ROOT/("shard-%d.json"%shard)
        need(p.is_file(),"missing shard "+str(shard))
        z=json.loads(p.read_text())
        need(len(z)==112,"incomplete shard "+str(shard))
        rows+=z
        per_shard[str(shard)]={
            arm:summarize([r for r in z if r["arm"]==arm]) for arm in ARMS}
    expected={(c["sha256"],rep,arm)
              for c in cs for rep in range(REPS) for arm in ARMS}
    got={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(got)==len(expected)==448 and got==expected,
         "448 SHA-matched original source trials missing")
    indexed={(r["original_sha256"],r["rep"],r["arm"]):r for r in rows}
    for r in rows:
        need(r["protocol"]==PROTO and r["allocated_logical_cpus"]==1 and
             len(r["cpu_affinity"])==1 and r["proof_checked"] and
             r["status"] in ("SAT","UNSAT","TIMEOUT"),
             "original CNF provenance/pinning/outcome drift")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "SAT original model not verified")
        need(abs(r["PAR2_s"]-(2*CAP if r["status"]=="TIMEOUT"
            else r["E2E_s"]))<.00001,"incorrect PAR2 penalty")
        if r["live"]:
            need(not r["live"]["callback_error"],"live callback error")
    pairs={}
    for a,b,name in [
        ("dmd5_16_active","dmd5_16_shadow","conditional16_active_vs_shadow"),
        ("dmd5_8_active","dmd5_8_shadow","conditional8_active_vs_shadow"),
        ("dmd5_16_active","cadical_clean","conditional16_active_vs_clean"),
        ("dmd5_16_active","kissat_original","conditional16_active_vs_kissat"),
        ("dmd5_all_active","cadical_clean","all_active_vs_clean")]:
        details=[]
        for c in cs:
            for rep in range(REPS):
                x=indexed[(c["sha256"],rep,a)]
                y=indexed[(c["sha256"],rep,b)]
                signature_match=x["selected_signature"]==y["selected_signature"] if \
                    b in ("dmd5_16_shadow","dmd5_8_shadow") else True
                need(signature_match,"active shadow selected candidates differ")
                same_verdict=(x["status"]==y["status"] and
                              x["status"] in ("SAT","UNSAT"))
                if signature_match:
                    details.append(dict(sha256=c["sha256"],rep=rep,
                       cohort=c["cohort"],selected=x["selected_count"],
                       status_active=x["status"],status_control=y["status"],
                       PAR2_delta_s=round(x["PAR2_s"]-y["PAR2_s"],6),
                       live_unit_events=x["live"].get("live_unit_opportunities",0),
                       first_live_at=x["live"].get("first_unit_assignment_index",-1),
                       comparable_decisions=same_verdict and
                          "decisions" in x["cdcl_stats"] and
                          "decisions" in y["cdcl_stats"],
                       comparable_conflicts=same_verdict and
                          "conflicts" in x["cdcl_stats"] and
                          "conflicts" in y["cdcl_stats"],
                       decisions_active=x["cdcl_stats"].get("decisions"),
                       decisions_control=y["cdcl_stats"].get("decisions"),
                       conflicts_active=x["cdcl_stats"].get("conflicts"),
                       conflicts_control=y["cdcl_stats"].get("conflicts")))
        def trend(key):
            vals=[(x[key+"_active"]-x[key+"_control"])
                for x in details if x["selected"]>0 and
                x["comparable_"+key] and x[key+"_active"] is not None]
            return dict(comparable_pairs=len(vals),
                lower=sum(d<0 for d in vals),higher=sum(d>0 for d in vals),
                ties=sum(d==0 for d in vals),total_delta=sum(vals))
        pairs[name]=dict(pairs=len(details),
            selected_nonempty=sum(x["selected"]>0 for x in details),
            active_only_solved=sum(x["status_active"]!="TIMEOUT" and
                                   x["status_control"]=="TIMEOUT" for x in details),
            control_only_solved=sum(x["status_control"]!="TIMEOUT" and
                                   x["status_active"]=="TIMEOUT" for x in details),
            wins=sum(x["PAR2_delta_s"]<-.01 for x in details),
            losses=sum(x["PAR2_delta_s"]>.01 for x in details),
            ties=sum(abs(x["PAR2_delta_s"])<=.01 for x in details),
            PAR2_benefit_s=round(-sum(x["PAR2_delta_s"] for x in details),6),
            cdcl_decisions=trend("decisions"),cdcl_conflicts=trend("conflicts"),
            best=sorted(details,key=lambda x:x["PAR2_delta_s"])[:4],
            worst=sorted(details,key=lambda x:x["PAR2_delta_s"],reverse=True)[:4])
    scores={arm:summarize([r for r in rows if r["arm"]==arm]) for arm in ARMS}
    source_scores={cohort:{
        arm:summarize([r for r in rows if r["arm"]==arm and
                       r["cohort"]==cohort]) for arm in ARMS}
        for cohort in sorted({r["cohort"] for r in rows})}
    k=scores["kissat_original"]["PAR2_s"]
    report=dict(protocol=PROTO,
        samples=28,disjoint_original_SHA_from_DMD3X_C=24,
        synthetic_controls=4,not_globally_blind=True,
        one_logical_cpu_per_solver=True,cap_s=CAP,
        independent_local_lemma_proof_replay=True,
        UNSAT_independent_LRAT=False,no_automatic_promotion=True,
        live_observed_unit_events_not_proof_of_new_CDCL_propagation=True,
        source_picked_by_SHA_not_solution_outcome=True,
        scores=scores,per_shard=per_shard,per_cohort=source_scores,
        paired=pairs,PAR2_speedup_vs_kissat={
            arm:round(k/z["PAR2_s"],6) for arm,z in scores.items()})
    (ROOT/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True))
    print("DMD5_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","bench","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    try:
        if args.action=="selftest":selftest()
        elif args.action=="bench":bench(args.shard)
        else:audit()
    except Exception as e:
        print("DMD5_FATAL",str(e),file=sys.stderr,flush=True)
        raise
