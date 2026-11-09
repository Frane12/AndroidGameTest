#!/usr/bin/env python3
"""DRNAS DECOMP4 / EQUIV8 TRANSFER: source-only gated 4s cold-reseed.
24 immutable original EQUIV2 SHA CNFs, 2 reps, 5 arms, 20s ONE LOGICAL CPU.
Never assume one previously successful EQUIV8 SAT instance generalizes.
Native cold process restart loses learned clauses. Original SAT witnesses verified.
UNSAT is backend-only unless original-input cross-backend agreement; no LRAT.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import random
import subprocess
import tempfile
import time

import decomp2_exact_bench as d2
import dmd1_bench as d1
import drnas_x16_singlecore_dual as x16
import drnas_x14_adaptive_portfolio as x14
import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_decomp4")
SOURCE=pathlib.Path("mre_x20")
SCREEN=pathlib.Path("mre_decomp1/screen.json")
NATIVE=pathlib.Path("mre_x4/bin/native")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
SCANNER=pathlib.Path("mre_decomp1/bin/decomp1_incidence")
ARMS=("native_base","native_altseed","native_split4","native_gate4","kissat_raw")
PROTO="DRNAS-DECOMP4-SEEDHEDGE-EQUIV8-TRANSFER-24SHA-ONECPU-v1"
CAP=20.0
SWITCH=4.0
REPS=2
SHARDS=6
SALT="DECOMP4_SOURCE_SHA_20261110_PREREG"
NEED_SHA="c96ebe32a7e333a02acad462679a0bbfbeeec54a7f9210421c4c0c8d53bbf95f"

def need(ok,reason):
    if not ok:raise RuntimeError("DECOMP4_FAIL_CLOSED "+str(reason))

def sha(p):
    return d1.sha(p)

def save(p,obj):
    p=pathlib.Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def seedpair(h,rep):
    need(0<=rep<REPS,"rep out of range")
    a=int(hashlib.sha256((SALT+"|"+h+"|"+str(rep)+"|base").encode()).hexdigest()[:7],16)+1
    b=int(hashlib.sha256((SALT+"|"+h+"|"+str(rep)+"|alt").encode()).hexdigest()[:7],16)+1
    need(a!=b,"seed collision")
    return a,b

def original():
    manifest=json.loads((SOURCE/"manifest.json").read_text())
    need(len(manifest["cases"])==24,"EQUIV2 24 SHA registry drift")
    screen=json.loads(SCREEN.read_text())
    need(len(screen)==24,"DECOMP1 source screen incomplete")
    byscreen={r["original_sha256"]:r for r in screen}
    need(len(byscreen)==24,"duplicate source SHA screen")
    cases=[]
    for c in sorted(manifest["cases"],key=lambda x:x["sha256"]):
        h=c["sha256"]
        path=SOURCE/c["filename"]
        need(path.is_file() and sha(path)==h,"original source checksum mismatch "+h)
        need(h in byscreen and byscreen[h]["original_SHA_verified"]
          and byscreen[h]["status"]=="OK","source graph screen missing or abstained")
        graph=byscreen[h]["graph"]
        candidate=bool(graph["clause_components"]>1 or
                       graph.get("best_separator_var",0)>0)
        cases.append(dict(sha256=h,path=str(path),filename=c["filename"],
          gbd=c.get("gbd"),graph=graph,structural_candidate=candidate))
    need(len(cases)==24 and len({x["sha256"] for x in cases})==24,
         "24 original SHA mismatch")
    return cases

def freeze():
    ROOT.mkdir(exist_ok=True)
    need(KISSAT.is_file() and sha(KISSAT)==NEED_SHA,"reference Kissat binary drift")
    need(NATIVE.is_file() and SCANNER.is_file(),"native binary or scanner missing")
    cases=original()
    m=dict(protocol=PROTO,cap_s=CAP,switch_s=SWITCH,reps=REPS,shards=SHARDS,
       arms=list(ARMS),source_count=len(cases),
       expected_trials=24*REPS*len(ARMS),cases=cases,
       binary_sha256={str(p):sha(p) for p in (NATIVE,KISSAT,SCANNER)},
       code_sha256=sha(pathlib.Path(__file__)),
       source_sha_locked=True,selection="all existing 24 frozen EQUIV2 original CNFs",
       not_globally_unseen=True,
       source_only_gate="clause_components>1 or best_separator_var>0, from DECOMP1",
       one_logical_cpu_per_solver=True,overlapping_solver_processes=False,
       cold_restart_discards_learnts=True,
       no_independent_UNSAT_LRAT=True,no_auto_promotion=True)
    save(ROOT/"freeze.json",m)
    print("DECOMP4_FREEZE_PASS "+json.dumps(dict(sources=24,trials=m["expected_trials"],
       gated=sum(x["structural_candidate"] for x in cases),
       source_only=True,original_SHA_verified=True),sort_keys=True),flush=True)

def frozen():
    m=json.loads((ROOT/"freeze.json").read_text())
    need(m["protocol"]==PROTO and m["cap_s"]==CAP and
         m["switch_s"]==SWITCH and m["arms"]==list(ARMS) and
         m["expected_trials"]==24*REPS*len(ARMS),"frozen settings drift")
    need(m["binary_sha256"]=={str(p):sha(p) for p in (NATIVE,KISSAT,SCANNER)},
         "backend binaries changed")
    need(m["code_sha256"]==sha(pathlib.Path(__file__)),"bench implementation changed")
    current=original()
    need([c["sha256"] for c in current]==[c["sha256"] for c in m["cases"]],
         "source SHA selection changed")
    return m

def verify_result(backend,entry,source):
    stdout,stderr=x22.read_output(entry)
    return x14.outcome_of(backend,entry["p"].returncode,stdout,stderr,source)

def one_stage(backend,source,seed,cpu,limit,folder,stage):
    # EQUIV8 logic: restart whole process; never run two solver children together.
    begun=time.perf_counter()
    c0=x22.child_cpu()
    status="TIMEOUT"
    if limit<=0.05:
        return dict(stage=stage,seed=seed,budget_s=round(limit,5),
          status=status,SAT_original_witness_verified=False,
          E2E_stage_s=0,child_CPU_stage_s=0)
    cmd=x16.command("native" if backend=="native" else "kissat",source,seed)
    child=x22.launch("s"+str(stage),cmd,cpu,folder)
    try:
        while child["p"].poll() is None and time.perf_counter()-begun<limit-0.018:
            time.sleep(.004)
        if child["p"].poll() is not None:
            status=verify_result(backend,child,source)
    finally:
        x22.cleanup([child])
    elapsed=time.perf_counter()-begun
    if status not in ("SAT","UNSAT") or elapsed>=limit:
        status="TIMEOUT"
    return dict(stage=stage,seed=seed,budget_s=round(limit,5),status=status,
      SAT_original_witness_verified=status=="SAT",
      E2E_stage_s=round(elapsed,6),
      child_CPU_stage_s=round(x22.child_cpu()-c0,6))

def live_scan(case,deadline):
    # Real E2E screening, not free historic features. Verify native output
    # matches precommitted source-only DECOMP1 graph before choosing a route.
    remaining=deadline-time.perf_counter()
    if remaining<0.15:return False,"scan_budget_exhausted"
    try:
        p=subprocess.run([str(SCANNER),case["path"],"2500"],
             capture_output=True,text=True,errors="replace",
             timeout=min(3.2,remaining-.02))
    except subprocess.TimeoutExpired:
        return False,"scanner_timeout_abstain"
    if p.returncode!=0:
        return False,"scanner_nonzero_abstain"
    rows=[s.split(" ",1)[1] for s in p.stdout.splitlines() if s.startswith("DECOMP1_SCAN ")]
    need(len(rows)==1,"ambiguous scan return")
    result=json.loads(rows[0])
    prior=case["graph"]
    need(result["clause_components"]==prior["clause_components"]
       and result["best_separator_var"]==prior["best_separator_var"]
       and result["best_clause_parts"]==prior["best_clause_parts"],
       "dynamic structure mismatch against source-only preselection")
    candidate=bool(result["clause_components"]>1 or result.get("best_separator_var",0)>0)
    need(candidate==case["structural_candidate"],"gate candidate drift")
    return candidate,("native_decomp1_candidate" if candidate else "native_decomp1_abstain")

def trial(case,arm,rep):
    need(arm in ARMS,"unregistered arm")
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    begun=time.perf_counter()
    cpu0=d2.getcpu()
    deadline=begun+CAP
    source=pathlib.Path(case["path"])
    need(sha(source)==case["sha256"],"original SHA changed before run")
    base,alt=seedpair(case["sha256"],rep)
    route=arm
    if arm=="native_gate4":
        gate,reason=live_scan(case,deadline)
        route="gate_split4" if gate else "gate_fallback_raw"
    else:
        gate=False
        reason="not_applicable"
    backend="kissat" if arm=="kissat_raw" else "native"
    plan=[(base,CAP)]
    if arm=="native_altseed":plan=[(alt,CAP)]
    elif arm=="native_split4" or (arm=="native_gate4" and gate):
        plan=[(base,SWITCH),(alt,CAP)]
    stages=[]
    status="TIMEOUT"
    with tempfile.TemporaryDirectory(prefix="decomp4-") as td:
        for i,(seed,target) in enumerate(plan):
            remaining=deadline-time.perf_counter()
            if remaining<0.06:break
            stage=one_stage(backend,source,seed,cpu,
                             min(target,remaining),td,i)
            stages.append(stage)
            if stage["status"] in ("SAT","UNSAT"):
                status=stage["status"]
                break
    elapsed=time.perf_counter()-begun
    if elapsed>=CAP:status="TIMEOUT"
    need(elapsed<=CAP+.20,"wall time limit exceeded")
    need(status!="SAT" or stages[-1]["SAT_original_witness_verified"],
         "SAT original witness not checked")
    need(sha(source)==case["sha256"],"original SHA drift after run")
    return dict(protocol=PROTO,original_sha256=case["sha256"],rep=rep,arm=arm,
       cap_s=CAP,seed_base=base,seed_alt=alt,gate_reason=reason,route=route,
       structural_candidate=case["structural_candidate"],gate_activated=gate,
       one_cpu=True,cpu_affinity=[cpu],status=status,
       SAT_original_witness_verified=status=="SAT",UNSAT_backend_only=status=="UNSAT",
       UNSAT_independent_LRAT=False,
       original_SHA_verified=True,child_starts=len(stages),
       second_seed_solved=status in ("SAT","UNSAT") and len(stages)==2,
       stages=stages,E2E_s=round(min(elapsed,CAP),6),
       CPU_s=round(d2.getcpu()-cpu0,6),
       PAR2_s=round((2*CAP if status=="TIMEOUT" else elapsed),6))

def selftest():
    ROOT.mkdir(exist_ok=True)
    c=seedpair("1"*64,0)
    need(c[0]!=c[1],"seeds not diversified")
    with tempfile.TemporaryDirectory() as td:
        f=pathlib.Path(td)/"simple.cnf"
        f.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n")
        cpu=min(os.sched_getaffinity(0))
        for backend in ("native","kissat"):
            st=one_stage(backend,f,c[0],cpu,2.0,td,0)
            need(st["status"]=="SAT" and st["SAT_original_witness_verified"],
                 "SAT witness original CNF failed for "+backend)
    print("DECOMP4_SELFTEST_PASS "+json.dumps(
       dict(native_original_model=True,kissat_original_model=True,
       cold_restart_two_seeds_distinct=True,single_cpu=True),sort_keys=True),flush=True)

def bench(shard):
    need(0<=shard<SHARDS,"shard out of range")
    m=frozen();rows=[]
    for i,case in enumerate(m["cases"]):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            shuffled=list(ARMS)
            random.Random(case["sha256"]+"|"+str(rep)).shuffle(shuffled)
            for arm in shuffled:
                row=trial(case,arm,rep);row["shard"]=shard
                rows.append(row)
                save(ROOT/("shard-%d.json"%shard),rows)
                print("DECOMP4_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==(24//SHARDS)*REPS*len(ARMS),"incomplete shard")
    print("DECOMP4_SHARD_PASS",shard,len(rows),flush=True)

def summ(a,accepted):
    return dict(n=len(a),SAT_verified=sum(r["status"]=="SAT" for r in a),
       UNSAT_backend_only=sum(r["status"]=="UNSAT" for r in a),
       solved_raw=sum(r["status"]!="TIMEOUT" for r in a),
       solved_audited=sum(accepted(r) for r in a),
       PAR2_s=round(sum(r["E2E_s"] if accepted(r) else 2*CAP for r in a),6),
       E2E_s=round(sum(r["E2E_s"] for r in a),6),
       CPU_s=round(sum(r["CPU_s"] for r in a),6),
       gate_activated=sum(r["gate_activated"] for r in a),
       second_seed_solved=sum(r["second_seed_solved"] for r in a),
       child_starts=sum(r["child_starts"] for r in a))

def audit():
    m=frozen()
    rows=[];shards={}
    for i in range(SHARDS):
        data=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(data)==(24//SHARDS)*REPS*len(ARMS),"bad shard length")
        rows.extend(data)
        shards[str(i)]=data
    expected={(c["sha256"],rep,arm) for c in m["cases"]
              for rep in range(REPS) for arm in ARMS}
    got={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(expected)==len(got)==240 and got==expected,
         "original-SHA paired matrix incomplete")
    for r in rows:
        need(r["protocol"]==PROTO and r["original_SHA_verified"] and
          r["one_cpu"] and len(r["cpu_affinity"])==1 and
          r["cap_s"]==CAP and r["UNSAT_independent_LRAT"]==False and
          (r["status"]!="SAT" or r["SAT_original_witness_verified"]) and
          r["child_starts"]==len(r["stages"]) and r["child_starts"]<=2 and
          abs(r["PAR2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["E2E_s"]))<0.00001
          for r in rows),"invalid provenance/SAT/E2E/PAR2")
    by={}
    for r in rows:
        by.setdefault(r["original_sha256"],[]).append(r)
    cross_unsat={}
    for h,items in by.items():
        states={r["status"] for r in items if r["status"]!="TIMEOUT"}
        need(len(states)<=1,"SAT/UNSAT contradiction in original SHA")
        cross_unsat[h]=(any(r["status"]=="UNSAT" and r["arm"]=="kissat_raw" for r in items)
           and any(r["status"]=="UNSAT" and r["arm"].startswith("native") for r in items))
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and cross_unsat[r["original_sha256"]])
    scores={arm:summ([r for r in rows if r["arm"]==arm],accepted) for arm in ARMS}
    baseline=scores["native_base"]["PAR2_s"]
    for item in scores.values():
        item["speedup_x_vs_native_base"]=round(baseline/item["PAR2_s"],6)
    pairs={}
    indexed={(r["original_sha256"],r["rep"],r["arm"]):r for r in rows}
    for arm in ARMS[1:]:
        diffs=[]
        for c in m["cases"]:
            for rep in range(REPS):
                a=indexed[(c["sha256"],rep,arm)]
                b=indexed[(c["sha256"],rep,"native_base")]
                pa=a["E2E_s"] if accepted(a) else 2*CAP
                pb=b["E2E_s"] if accepted(b) else 2*CAP
                diffs.append(round(pa-pb,6))
        pairs[arm]=dict(wins=sum(d<-.05 for d in diffs),
          losses=sum(d>.05 for d in diffs),ties=sum(abs(d)<=.05 for d in diffs),
          max_regression_s=max(diffs),best_gain_s=min(diffs))
    per_shard={i:{arm:summ([r for r in arr if r["arm"]==arm],accepted)
                       for arm in ARMS} for i,arr in shards.items()}
    report=dict(protocol=PROTO,sources=24,attempts=len(rows),reps=REPS,
       cap_s=CAP,one_cpu=True,not_globally_unseen=True,
       EQUIV8_one_known_source_not_reused=True,
       cold_restart_discards_learnts=True,UNSAT_independent_LRAT=False,
       cross_backend_UNSAT_no_LRAT=sum(cross_unsat.values()),
       source_structural_candidates=sum(c["structural_candidate"] for c in m["cases"]),
       no_auto_promotion=True,scores=scores,per_shard=per_shard,paired=pairs)
    save(ROOT/"audit.json",report)
    print("DECOMP4_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("selftest","freeze","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.mode=="bench":bench(a.shard)
    else:globals()[a.mode]()
