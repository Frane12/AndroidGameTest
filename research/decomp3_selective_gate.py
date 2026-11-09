#!/usr/bin/env python3
"""DRNAS DECOMP3-GATE: source-only selective exact decomposition E2E validation.

Reuses immutable DECOMP2 8 original SHA candidates and pinned Kissat.
No outcome-based routing. One logical CPU; SAT witnesses checked on original
CNF; UNSAT backend-only, NOT independently LRAT verified.
"""
from __future__ import annotations
import argparse
import collections
import itertools
import json
import pathlib
import random
import tempfile
import time
import os

import decomp2_exact_bench as d2
import dmd1_bench as d1

ROOT=pathlib.Path("mre_decomp3_gate")
PROTO="DRNAS-DECOMP3-SELECTIVE-DECOMP-PROBE-8SHA-ONECPU-v1"
ARMS=("kissat_raw","selective_components","selective_probe")
REPS=2
SHARDS=4
CAP=12.0
PROBE_S=0.08

def need(condition,message):
    if not condition:
        raise RuntimeError("DECOMP3_GATE_FAIL_CLOSED "+str(message))

def freeze():
    original=d2.frozen()
    need(len(original["cases"])==8,"DECOMP2 selection drift")
    m=dict(protocol=PROTO,cases=original["cases"],arms=list(ARMS),
      reps=REPS,shards=SHARDS,cap_s=CAP,probe_s=PROBE_S,
      source_set="DECOMP2 EQUIV2 frozen 8 (reused, not unseen)",
      source_selection="same SHA, no post-outcome filtering",
      router="only disconnected (2..8 components), largest <= 80%, second >= 5% and 8 clauses; otherwise raw",
      single_logical_cpu=True,independent_UNSAT_LRAT=False,
      no_automatic_promotion=True,
      solver_sha256=d1.sha(d2.KISSAT),
      prior_protocol=original["protocol"])
    ROOT.mkdir(exist_ok=True)
    (ROOT/"freeze.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    print("DECOMP3_GATE_FREEZE_PASS "+json.dumps(dict(sources=8,trials=8*REPS*len(ARMS),reps=REPS),sort_keys=True),flush=True)

def frozen():
    m=json.loads((ROOT/"freeze.json").read_text())
    d2.frozen()
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and len(m["cases"])==8
       and m["solver_sha256"]==d1.sha(d2.KISSAT),"frozen metadata / solver drift")
    for c in m["cases"]:
        need(d1.sha(pathlib.Path(c["path"]))==c["sha256"],"source SHA drift")
    return m

def inspect(clauses,graph):
    """Outcome-independent incidence screen; no solver/probe ever influences gate."""
    parts=d2.components(clauses)
    lens=sorted((len(x) for x in parts),reverse=True)
    total=len(clauses)
    # Recheck frozen source-only graph to guard against accidental drift.
    need(len(parts)==graph["clause_components"],"component structure changed")
    largest=lens[0] if lens else 0
    second=lens[1] if len(lens)>1 else 0
    eligible=(2<=len(parts)<=8 and largest<=.80*total
              and second>=max(8,.05*total))
    reason=("balanced_disconnected" if eligible else
       "connected" if len(parts)<2 else
       "too_many_parts" if len(parts)>8 else
       "unbalanced_or_tiny_secondary")
    return dict(eligible=eligible,reason=reason,component_count=len(parts),
                largest_clauses=largest,second_clauses=second,total_clauses=total,
                largest_fraction=round(largest/max(1,total),6)),parts

def probe_one(clauses,parts,seed,deadline,cpu,tmp):
    """Short exact UNSAT test of a truly disjoint component.
    A local UNSAT entails original UNSAT. SAT is never enough for full SAT."""
    component=min(parts,key=lambda p:(len(p),min(p)))
    local=[clauses[i] for i in component]
    dest=tmp/"probe.cnf"
    _,compact=d2.write_compact(dest,local)
    remaining=min(PROBE_S,deadline-time.monotonic())
    if remaining<=0.003:return "SKIP",0
    rc,out,err,_,_,timed=d1.run_process([d2.KISSAT,"--seed="+str(seed),dest],
                                          remaining,cpu)
    if timed:return "TIMEOUT",1
    status,_=d1.outcome(rc,out,compact)
    return status,1

def trial(case,arm,rep):
    need(arm in ARMS,"unregistered arm")
    cpu=d2.pin()
    start=time.monotonic()
    cpu0=d2.getcpu()
    deadline=start+CAP
    source=pathlib.Path(case["path"])
    need(d1.sha(source)==case["sha256"],"original CNF modified")
    n,original=d1.read_cnf(source)
    seed=1001+rep
    route="raw";calls=0;solved_parts=0;model={}
    gate={"eligible":False,"reason":"baseline_skipped","component_count":0,
          "largest_clauses":0,"second_clauses":0,"total_clauses":len(original),
          "largest_fraction":1.0}
    probe_result="NOT_RUN";status="TIMEOUT"
    with tempfile.TemporaryDirectory(prefix="decomp3-gate-") as td:
        tmp=pathlib.Path(td)
        if arm!="kissat_raw":
            gate,parts=inspect(original,case["graph"])
        prep_s=time.monotonic()-start
        if arm=="selective_components" and gate["eligible"]:
            route="exact_disconnected"
            status,model,calls,solved_parts=d2.solve_parts(original,tmp,seed,deadline,cpu,True)
        elif arm=="selective_probe" and gate["eligible"]:
            route="probe_then_raw"
            probe_result,pcalls=probe_one(original,parts,seed,deadline,cpu,tmp)
            calls+=pcalls
            if probe_result=="UNSAT":
                status="UNSAT"
                solved_parts=1
            else:
                status,model,rawcalls,_=d2.solve_raw(source,original,seed,deadline,cpu)
                calls+=rawcalls
        else:
            if arm!="kissat_raw":route="gate_abstain_to_raw"
            status,model,calls,_=d2.solve_raw(source,original,seed,deadline,cpu)
    wall=min(CAP,time.monotonic()-start) if status=="TIMEOUT" else time.monotonic()-start
    need(wall<=CAP+.12,"E2E overcap")
    if status=="SAT":
        model={**{v:False for v in range(1,n+1)},**model}
        need(d1.holds(original,model),"SAT model failed original CNF")
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid solver outcome")
    need(d1.sha(source)==case["sha256"],"source SHA post-trial drift")
    return dict(protocol=PROTO,original_sha256=case["sha256"],arm=arm,rep=rep,
       one_cpu=True,cpu_affinity=[cpu],cap_s=CAP,status=status,
       SAT_original_witness_verified=status=="SAT",
       UNSAT_backend_only=status=="UNSAT",UNSAT_independent_LRAT=False,
       original_SHA_verified=True,route=route,gate=gate,
       probe_result=probe_result,solver_calls=calls,components_solved=solved_parts,
       preprocess_wall_s=round(prep_s,6),E2E_s=round(wall,6),
       CPU_s=round(d2.getcpu()-cpu0,6),
       PAR2_s=round(2*CAP if status=="TIMEOUT" else wall,6))

def bench(shard):
    need(0<=shard<SHARDS,"invalid shard")
    f=frozen()
    rows=[]
    for i,c in enumerate(f["cases"]):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                row=trial(c,arm,rep)
                row["shard"]=shard
                rows.append(row)
                (ROOT/("shard-%d.json"%shard)).write_text(
                   json.dumps(rows,sort_keys=True,indent=2)+"\n")
                print("DECOMP3_GATE_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==8//SHARDS*REPS*len(ARMS),"missing trials")
    print("DECOMP3_GATE_SHARD_PASS",shard,len(rows),flush=True)

def selftest():
    # The gate MUST never invoke decomposition on connected, one-component CNF.
    test=[(1,2),(-2,3),(2,-3)]
    g={"clause_components":1}
    decision,_=inspect(test,g)
    need(not decision["eligible"] and decision["reason"]=="connected","connected gate")
    # Positive disconnected, balanced graph exactly testable by enumeration.
    sample=[(1,),(2,),(-1,3),(-2,4)]
    choice,parts=inspect(sample,{"clause_components":2})
    need(choice["eligible"] and len(parts)==2,"balanced gate")
    for bits in itertools.product((False,True),repeat=4):
        assignment=dict(zip(range(1,5),bits))
        exact=d1.holds(sample,assignment)
        decomposed=all(d1.holds([sample[i] for i in part],assignment)
                       for part in parts)
        need(exact==decomposed,"partition semantic mismatch")
    # Unbalanced articulation is intentionally NOT treated as unconditional split.
    need(not inspect([(1,2),(2,3),(1,-3)],{"clause_components":1})[0]["eligible"],
       "invalid articulation gate")
    print("DECOMP3_GATE_SELFTEST_PASS "+json.dumps(
       {"balanced_disconnected":True,"connected_abstain":True,
        "model_equivalence_assignments":16,"no_outcome_selection":True}),flush=True)

def summarize(rows):
    return dict(n=len(rows),solved=sum(x["status"]!="TIMEOUT" for x in rows),
       SAT_verified=sum(x["status"]=="SAT" for x in rows),
       UNSAT_backend_only=sum(x["status"]=="UNSAT" for x in rows),
       PAR2_s=round(sum(x["PAR2_s"] for x in rows),6),
       E2E_s=round(sum(x["E2E_s"] for x in rows),6),
       CPU_s=round(sum(x["CPU_s"] for x in rows),6),
       routed=sum(x["route"] in ("exact_disconnected","probe_then_raw") for x in rows),
       abstained=sum(x["route"]=="gate_abstain_to_raw" for x in rows),
       calls=sum(x["solver_calls"] for x in rows))

def audit():
    m=frozen()
    rows=[];byshard={}
    for i in range(SHARDS):
        data=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(data)==8//SHARDS*REPS*len(ARMS),"shard missing %d"%i)
        rows.extend(data)
        byshard[str(i)]={a:summarize([r for r in data if r["arm"]==a]) for a in ARMS}
    need(len(rows)==8*REPS*len(ARMS),"incomplete trial matrix")
    expected={(c["sha256"],r,a) for c in m["cases"] for r in range(REPS) for a in ARMS}
    got={(x["original_sha256"],x["rep"],x["arm"]) for x in rows}
    need(len(got)==len(rows) and got==expected,"original SHA paired matrix failure")
    for r in rows:
        need(r["one_cpu"] and r["original_SHA_verified"] and r["protocol"]==PROTO
          and r["UNSAT_independent_LRAT"]==False
          and (r["status"]!="SAT" or r["SAT_original_witness_verified"])
          and abs(r["PAR2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["E2E_s"]))<.000001,
             "row provenance invalid")
    for c in m["cases"]:
        outcomes={r["status"] for r in rows if
          r["original_sha256"]==c["sha256"] and r["status"]!="TIMEOUT"}
        need(len(outcomes)<=1,"SAT/UNSAT contradiction")
    scores={a:summarize([r for r in rows if r["arm"]==a]) for a in ARMS}
    base=scores["kissat_raw"]["PAR2_s"]
    for a in scores:scores[a]["speedup_x_vs_kissat"]=round(base/scores[a]["PAR2_s"],6)
    by={(r["original_sha256"],r["rep"],r["arm"]):r for r in rows}
    paired={}
    for arm in ARMS[1:]:
        diff=[round(by[(c["sha256"],rep,arm)]["PAR2_s"]-
                    by[(c["sha256"],rep,"kissat_raw")]["PAR2_s"],6)
              for c in m["cases"] for rep in range(REPS)]
        paired[arm]=dict(wins=sum(d<-.02 for d in diff),
           losses=sum(d>.02 for d in diff),
           ties=sum(abs(d)<=.02 for d in diff),
           max_regression_s=max(diff),best_gain_s=min(diff))
    report=dict(protocol=PROTO,source_count=8,trials=len(rows),reps=REPS,
       independent_UNSAT_LRAT=False,not_globally_unseen=True,
       source_only_preregistered_gate=True,no_automatic_promotion=True,
       total_gate_eligible=sum(x["gate"]["eligible"] for x in rows if x["arm"]=="selective_probe"),
       scores=scores,per_shard=byshard,paired=paired)
    (ROOT/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DECOMP3_GATE_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=("selftest","freeze","bench","audit"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    if args.mode=="bench":bench(args.shard)
    else:globals()[args.mode]()
