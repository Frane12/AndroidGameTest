#!/usr/bin/env python3
"""DRNAS X12: source-verified adaptive and concurrent SAT solver portfolios.

X12 tests a fresh-to-this-policy 32-SHA historical cohort from the immutable
X11 GitHub Actions artifact (not a genuinely blind or new official corpus).
Parallel Kissat/CMS and Kissat/CMS/CaDiCaL portfolios compete against standalone
Kissat/CMS/CaDiCaL and the frozen X10 source-only structural selector.
25? No: exact E2E 15 second cap, including feature collection, process startup,
SAT witness checking on original CNF and process cleanup. All process CPU is
reported, preventing claims that two-core racing is free acceleration.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import resource
import shutil
import signal
import subprocess
import tempfile
import time

import drnas_x10_structural_profile as profile
import drnas_x10_structural_benchmark as x10

ROOT=pathlib.Path("x12_sources")
OUT=pathlib.Path("x12_out")
PRIOR_X11=pathlib.Path("x12_prior_x11/mre_x11")
PRIOR_X10=pathlib.Path("x10_sources")
PROTO="DRNAS-X12-32SHA-7ARM-2SEED-15S-E2E-DUAL-TRIPLE-PORTFOLIO-v1"
SHARDS=8
REPS=2
CAP=15.0
ARMS=("kissat_404","cms_orig","cadical_173","x10_structural",
      "x12_parallel2","x12_gate2","x12_parallel3")
BIN={"kissat_404":pathlib.Path("built/bin/kissat_4_0_4"),
     "cms_orig":pathlib.Path("x10_bin/mre_x8/bin/native"),
     "cadical_173":pathlib.Path("c8c/bin/plain")}
NO_SCORE_ON_FAILED=True

def need(condition,message):
    if not condition:
        raise RuntimeError("X12_FAIL_CLOSED "+message)

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def save(path,data):
    p=pathlib.Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")

def seed(case,rep):
    v=hashlib.sha256((case["sha256"]+":x12:"+str(rep)).encode()).hexdigest()
    return max(1,int(v[:8],16)&0x7fffffff)

def gate(f):
    """Frozen exploratory risk trigger. No test-time solver probing or tuning."""
    risk=(f["sample_binary_ratio"]>=0.85 or
          (f["sample_binary_ratio"]<=0.03 and
           f["sample_ternary_ratio"]<=0.10) or
          f["xor4_groups"]>=2 or
          f["occurrence_degree_cv"]>=1.80 or
          f["sample_ternary_ratio"]>=0.80)
    if risk:
        return ["kissat_404","cms_orig"],"structural_ambiguity_two_core_race"
    target,reason=profile.route(f,True)
    return [target],"frozen_X10_"+reason

def starts(arm,f):
    if arm in BIN:
        return [arm],"single_reference"
    if arm=="x10_structural":
        backend,reason=profile.route(f,True)
        return [backend],reason
    if arm=="x12_parallel2":
        return ["kissat_404","cms_orig"],"parallel_two_core"
    if arm=="x12_parallel3":
        return ["kissat_404","cms_orig","cadical_173"],"parallel_three_core"
    need(arm=="x12_gate2","invalid arm")
    return gate(f)

def freeze():
    need((PRIOR_X11/"manifest.json").is_file(),"missing X11 snapshot")
    need((PRIOR_X10/"manifest.json").is_file(),"missing X10 snapshot")
    m=json.loads((PRIOR_X11/"manifest.json").read_text())
    need(len(m["cases"])==32 and m["expected_trials"]==448,
         "X11 immutable original source manifest mismatch")
    x10m=json.loads((PRIOR_X10/"manifest.json").read_text())
    prior_sha={c["sha256"] for c in x10m["cases"]}
    need(len(prior_sha)==24,"X10 SHA set drift")
    ROOT.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    records=[]
    seen=set()
    for item in m["cases"]:
        inputpath=PRIOR_X11/item["filename"]
        need(inputpath.is_file() and sha(inputpath)==item["sha256"],
             "original X11 SHA mismatch")
        need(item["sha256"] not in seen,"duplicate original source")
        seen.add(item["sha256"])
        cp=ROOT/(item["sha256"]+".cnf")
        shutil.copyfile(inputpath,cp)
        nv=int(item["vars"])
        nc=int(item["clauses"])
        f,sec=profile.probe(cp,nv,nc)
        x10_route,why=profile.route(f,True)
        targets,gate_why=gate(f)
        r=dict(filename=cp.name,sha256=item["sha256"],gbd=item["gbd"],
            cohort=item["cohort"],nvars=nv,nclauses=nc,
            bytes=cp.stat().st_size,source_origin="X11 immutable 32 SHA",
            known_prior_X10_SHA=item["sha256"] in prior_sha,
            known_prior_X11_timings=True,
            features=f,predicted_x10=x10_route,x10_reason=why,
            predicted_gate=targets,gate_reason=gate_why,
            source_profile_s_freeze=sec)
        records.append(r)
        print("X12_FEATURE",json.dumps({
             "gbd":r["gbd"],"cohort":r["cohort"],"X10":x10_route,
             "gate":targets,"risk":gate_why,
             "profile_ms":round(sec*1000,3),
             "sample_binary":f["sample_binary_ratio"],
             "sample_ternary":f["sample_ternary_ratio"],
             "sample_scc":f["implication_largest_scc_fraction"]},sort_keys=True),
             flush=True)
    need(len(records)==32,"unexpected X11 source set size")
    registry=dict(protocol=PROTO,cases=records,source_count=len(records),
        n_shards=SHARDS,seed_repeats=REPS,cap_s=CAP,arms=list(ARMS),
        expected_trials=32*REPS*len(ARMS),
        original_X11_artifact_run=42563452186,
        original_X10_artifact_run=42563492221,
        original_X11_manifest_sha256=sha(PRIOR_X11/"manifest.json"),
        original_X10_manifest_sha256=sha(PRIOR_X10/"manifest.json"),
        known_X10_overlap=sum(c["known_prior_X10_SHA"] for c in records),
        source_only_precommitted_features=True,
        physical_parallelism_measured_cpu_seconds=True,
        no_runtime_solver_lookahead=True,
        SAT_recheck_original=True,
        UNSAT_independent_LRAT=False,
        retrospective_X11_benchmark_not_blind=True,
        static_risk_gate_exploratory_post_X10=True,
        no_auto_promotion=True,not_official_ranking=True)
    save(ROOT/"manifest.json",registry)
    (ROOT/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in records))
    print("X12_FROZEN",json.dumps({
        "sources":32,"trials":registry["expected_trials"],
        "overlap_X10":registry["known_X10_overlap"],
        "gate_race_sources":sum(len(c["predicted_gate"])>1 for c in records),
        "SHA":sha(ROOT/"manifest.json")},sort_keys=True),flush=True)

def cases():
    manifest=json.loads((ROOT/"manifest.json").read_text())
    need(manifest["protocol"]==PROTO and
         manifest["expected_trials"]==32*REPS*len(ARMS) and
         manifest["arms"]==list(ARMS) and
         len(manifest["cases"])==32,"frozen protocol drift")
    for c in manifest["cases"]:
        p=ROOT/c["filename"]
        need(p.is_file() and sha(p)==c["sha256"],"source drift")
        need(profile.route(c["features"],True)[0]==c["predicted_x10"],
             "precommitted X10 route drift")
        need(gate(c["features"])[0]==c["predicted_gate"],
             "precommitted gate drift")
    return manifest["cases"]

def backend_cmd(backend,cnf,sd):
    exe=str(BIN[backend].resolve())
    if backend=="cms_orig":
        return [exe,str(cnf.resolve()),"x_native",str(sd)]
    if backend=="kissat_404":
        return [exe,"--seed="+str(sd),str(cnf.resolve())]
    return [exe,str(cnf.resolve())]

def parse_completed(backend,cmd,returncode,stdout,stderr,cnf):
    if backend=="cms_orig":
        need(returncode==0,"native crash "+stderr[-200:])
        status,model,stats=x10.w.base.cms.parsed_native(stdout)
        trace=x10.w.base.parse_gate(stdout,"x_native")
        need(not trace["applied"] and trace["clauses_removed"]==0,
             "CMS unexpectedly rewrote original CNF")
    else:
        need(returncode in (10,20),
             "reference abnormal exit "+backend+" "+str(returncode)+stderr[-200:])
        cp=subprocess.CompletedProcess(cmd,returncode,stdout,stderr)
        status,model=x10.w.ref.external_parse(cp)
        stats=None
    need(status in ("SAT","UNSAT","UNKNOWN","TIMEOUT","BUDGET"),
         "unrecognized solver outcome "+str(status))
    if status=="SAT":
        x10.w.cms.verify_model(cnf,model)
    return status,stats

def term(proc):
    if proc.poll() is None:
        try:
            os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)

def delta_cpu(before,after):
    return (after.ru_utime+after.ru_stime-
            before.ru_utime-before.ru_stime)

def trial(c,rep,arm,source_override=None):
    need(rep in range(REPS) and arm in ARMS,"invalid trial")
    original=pathlib.Path(source_override) if source_override else ROOT/c["filename"]
    need(sha(original)==c["sha256"],"original source changed")
    begin=time.perf_counter()
    cpu_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    f=c["features"]
    profile_s=0
    if arm in ("x10_structural","x12_gate2"):
        f,profile_s=profile.probe(original,c["nvars"],c["nclauses"])
        need(f==c["features"],"source-only feature drift")
    backends,reason=starts(arm,f)
    need(len(backends)==len(set(backends)) and
         all(b in BIN for b in backends),"invalid simultaneous portfolio")
    start_overhead=time.perf_counter()-begin
    processes=[]
    selected=None
    statuses=[]
    chosen_stats=None
    outcome="TIMEOUT"
    verified=False
    with tempfile.TemporaryDirectory() as td:
        handles=[]
        try:
            env=os.environ.copy()
            for key in ("DRNAS_MAX_CONFLICTS","DRNAS_X7_TRACE",
                        "DRNAS_X8_TRACE","DRNAS_C8I_EARLY_GATE16",
                        "DRNAS_C8I_GATE_TRACE"):
                env.pop(key,None)
            for backend in backends:
                if time.perf_counter()-begin>=CAP:break
                out=open(pathlib.Path(td)/(backend+".stdout"),"w+t")
                err=open(pathlib.Path(td)/(backend+".stderr"),"w+t")
                handles.extend([out,err])
                cmd=backend_cmd(backend,original,seed(c,rep))
                p=subprocess.Popen(cmd,env=env,stdout=out,stderr=err,
                                   text=True,start_new_session=True)
                processes.append(dict(backend=backend,p=p,cmd=cmd,
                                      stdout=out,stderr=err,read=False))
            while (time.perf_counter()-begin)<CAP and selected is None:
                active=False
                for entry in processes:
                    if entry["read"]:continue
                    p=entry["p"]
                    code=p.poll()
                    if code is None:
                        active=True
                        continue
                    entry["read"]=True
                    entry["stdout"].flush()
                    entry["stderr"].flush()
                    entry["stdout"].seek(0)
                    entry["stderr"].seek(0)
                    sout=entry["stdout"].read()
                    serr=entry["stderr"].read()
                    status,stats=parse_completed(entry["backend"],entry["cmd"],
                                                 code,sout,serr,original)
                    statuses.append(dict(backend=entry["backend"],
                        status=status,returncode=code))
                    if status in ("SAT","UNSAT"):
                        selected=entry["backend"]
                        outcome=status
                        chosen_stats=stats
                        verified=status=="SAT"
                        break
                if selected is None and active:
                    time.sleep(min(0.005,max(0.0,CAP-(time.perf_counter()-begin))))
                elif selected is None and not active:
                    break
        finally:
            for entry in processes:
                term(entry["p"])
            for fhandle in handles:
                fhandle.close()
    elapsed=time.perf_counter()-begin
    if elapsed>CAP or outcome not in ("SAT","UNSAT"):
        outcome="TIMEOUT"
        selected=None
        verified=False
    total_cpu=delta_cpu(cpu_before,resource.getrusage(resource.RUSAGE_CHILDREN))
    return dict(protocol=PROTO,gbd=c["gbd"],cohort=c["cohort"],
        source_sha256=c["sha256"],rep=rep,seed=seed(c,rep),arm=arm,
        backends=backends,policy_reason=reason,
        winner=selected,status=outcome,
        original_SHA_verified=True,SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,
        native_stats=chosen_stats,
        elapsed_s=round(elapsed,6),prep_s=round(start_overhead,6),
        profile_ms=round(profile_s*1000,3),
        child_cpu_s=round(total_cpu,6),
        PAR2_s=round(elapsed if outcome!="TIMEOUT" else 2*CAP,6),
        cap_s=CAP,finished_solver_statuses=statuses,
        source_only_route_precommitted=True,
        model_verification_included_in_wall=True,
        original_source_not_rewritten=True,
        no_solver_preview=True,
        retrospective_X11_benchmark=True)

def smoke():
    profile.selftest()
    ROOT.mkdir(exist_ok=True)
    p=ROOT/"x12-smoke-original.cnf"
    p.write_text("p cnf 2 2\n1 2 0\n-1 2 0\n")
    f,_=profile.probe(p,2,2)
    c=dict(filename=p.name,sha256=sha(p),gbd="x12_smoke",
           cohort="synthetic",nvars=2,nclauses=2,features=f)
    try:
        for arm in ARMS:
            a=trial(c,0,arm)
            need(a["status"]=="SAT" and a["SAT_original_witness_verified"],
                 "original SAT witness smoke failed: "+arm+" "+str(a))
            print("X12_SMOKE",arm,a["winner"],a["elapsed_s"],flush=True)
    finally:
        p.unlink(missing_ok=True)
    print("X12_SMOKE_PASS",flush=True)

def shard(index):
    need(index in range(SHARDS),"bad shard number")
    cc=cases()
    assigned=[c for i,c in enumerate(cc) if i%SHARDS==index]
    need(len(assigned)==4,"unbalanced source pairing")
    OUT.mkdir(exist_ok=True)
    trials=[]
    for c in assigned:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(seed(c,rep)).shuffle(arms)
            for arm in arms:
                row=trial(c,rep,arm)
                trials.append(row)
                save(OUT/("shard-%d.json"%index),trials)
                print("X12_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(trials)==56,"incomplete measured shard")
    print("X12_SHARD_PASS",index,len(trials),flush=True)

def scoreboard(rows):
    return {arm:dict(n=len(group),
        solved=sum(x["status"] in ("SAT","UNSAT") for x in group),
        SAT_verified=sum(x["status"]=="SAT" and x["SAT_original_witness_verified"] for x in group),
        UNSAT_reference_only=sum(x["status"]=="UNSAT" for x in group),
        timeouts=sum(x["status"]=="TIMEOUT" for x in group),
        PAR2_s=round(sum(x["PAR2_s"] for x in group),6),
        child_cpu_s=round(sum(x["child_cpu_s"] for x in group),6),
        E2E_wall_s=round(sum(x["elapsed_s"] for x in group),6),
        profile_ms=round(sum(x["profile_ms"] for x in group),3))
        for arm in ARMS
        for group in [[x for x in rows if x["arm"]==arm]]}

def audit():
    cc=cases()
    bysha={c["sha256"]:c for c in cc}
    rows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i)
        need(p.is_file(),"missing result shard")
        batch=json.loads(p.read_text())
        need(len(batch)==56,"short result shard")
        rows.extend(batch)
    expected={(c["sha256"],rep,arm)
              for c in cc for rep in range(REPS) for arm in ARMS}
    seen=set()
    for r in rows:
        key=(r["source_sha256"],r["rep"],r["arm"])
        need(key in expected and key not in seen,
             "invalid/duplicate paired original SHA")
        seen.add(key)
        c=bysha[r["source_sha256"]]
        need(r["gbd"]==c["gbd"] and r["cohort"]==c["cohort"] and
             r["seed"]==seed(c,r["rep"]) and r["protocol"]==PROTO and
             r["original_SHA_verified"],"unexpected protocol or source")
        target,_=starts(r["arm"],c["features"])
        need(target==r["backends"],"test-time policy mutation")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==CAP*2,"bad timeout penalty")
        else:
            need(r["status"] in ("SAT","UNSAT") and
                 abs(r["PAR2_s"]-r["elapsed_s"])<=0.000002,
                 "invalid E2E time/result")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "unverified original model")
    need(len(rows)==len(expected)==len(seen)==448,
         "paired trials incomplete")
    for c in cc:
        results={r["status"] for r in rows if r["source_sha256"]==c["sha256"]
                 and r["status"] in ("SAT","UNSAT")}
        need(len(results)<=1,"contradictory SAT/UNSAT original source")
    summary=scoreboard(rows)
    matched={(r["source_sha256"],r["rep"],r["arm"]):r for r in rows}
    winner_stats=collections.Counter()
    per_source=[]
    for c in cc:
        sample=[]
        for rep in range(REPS):
            get=lambda arm:matched[(c["sha256"],rep,arm)]
            controls={arm:get(arm)["PAR2_s"] for arm in
                      ("kissat_404","cms_orig","cadical_173")}
            oracle=min(controls.values())
            for arm in ("x12_parallel2","x12_gate2","x12_parallel3"):
                r=get(arm)
                winner_stats[(arm,r["winner"] or "timeout")]+=1
            sample.append(dict(rep=rep,
               reference_PAR2=controls,
               hindsight_oracle_PAR2_s=oracle,
               x10_PAR2_s=get("x10_structural")["PAR2_s"],
               double_PAR2_s=get("x12_parallel2")["PAR2_s"],
               gate_PAR2_s=get("x12_gate2")["PAR2_s"],
               triple_PAR2_s=get("x12_parallel3")["PAR2_s"],
               gate_backends=get("x12_gate2")["backends"]))
        per_source.append(dict(gbd=c["gbd"],cohort=c["cohort"],
             sha256=c["sha256"],known_X10=c["known_prior_X10_SHA"],
             features=c["features"],repetitions=sample))
    kissat=summary["kissat_404"]["PAR2_s"]
    for a in summary:
        summary[a]["PAR2_saving_vs_Kissat_pct"]=round(
            100*(kissat-summary[a]["PAR2_s"])/kissat,6)
        summary[a]["CPU_cost_multiple_vs_Kissat"]=round(
            summary[a]["child_cpu_s"]/max(0.000001,summary["kissat_404"]["child_cpu_s"]),4)
    cohorts={cohort:scoreboard([r for r in rows if r["cohort"]==cohort])
             for cohort in sorted({r["cohort"] for r in rows})}
    report=dict(protocol=PROTO,source_count=32,trials=448,cap_s=CAP,
        main_score=summary,by_cohort=cohorts,
        portfolio_winner_counts={a:{w:v for (aa,w),v in winner_stats.items()
             if aa==a} for a in ("x12_parallel2","x12_gate2","x12_parallel3")},
        source_details=per_source,
        UNSAT_independent_LRAT=False,
        SAT_model_original_verified=True,
        CPU_total_measured=True,
        original_source_SHA_verified=True,
        not_blind_historical_X11=True,
        no_auto_promotion=True)
    save(OUT/"report.json",report)
    print("X12_FINAL",json.dumps({k:v for k,v in report.items()
                    if k!="source_details"},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["freeze","smoke","verify","shard","audit"])
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="freeze":
        freeze()
    elif a.action=="smoke":
        smoke()
    elif a.action=="verify":
        print("X12_VERIFY_PASS",len(cases()),flush=True)
    elif a.action=="shard":
        shard(a.shard)
    else:
        audit()

if __name__=="__main__":
    main()
