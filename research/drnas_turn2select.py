#!/usr/bin/env python3
"""TURN2SELECT: development-only structural gate vs two fixed reference arms.

The eight SHA-frozen SAT2026 originals were already examined in TURN2H.
This is a PRE-REGISTERED REUSED DEVELOPMENT COHORT, not a blind validation.
No timing, model outcome, ID or source hash participates in the gate.
The gate changes only a provably bijective signed representation, never clauses.
This is NOT Satsuma's symmetry-breaking algorithm.
All solver CPU and transformation time are included in the 60s wall clock.
SAT is rechecked on original CNF. UNSAT must be verified by independent DRAT.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time

import drnas_turn2h_holdout as h

ROOT=Path("turn2select")
CAP=60.0
REPS=3
SHARDS=8
MODES=("kissat_plain","kissat_struct_signed","structural_guard")
PROTO="DRNAS-TURN2SELECT-REUSED8-3ARMS-3REPS-60S-v1"
GATE={"min_binary_fraction":0.60,"max_polarity_bias":0.30,
      "max_horn_fraction":0.85,"min_active_variables":2000}

def need(ok,msg):
    if not ok:
        raise RuntimeError("TURN2SELECT_FAIL_CLOSED "+str(msg))

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p,x):
    p=Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def features(source):
    n,clauses=h.turn.t1.parse(source)
    _,_,_,f=h.turn.degree_profile(n,clauses)
    return f

def choose(f):
    return ("kissat_struct_signed"
            if f["binary_fraction"]>=GATE["min_binary_fraction"]
            and f["mean_polarity_bias"]<=GATE["max_polarity_bias"]
            and f["horn_fraction"]<=GATE["max_horn_fraction"]
            and f["active_variables"]>=GATE["min_active_variables"]
            else "kissat_plain")

def frozen_cases():
    cases=h.verify()
    need(len(cases)==SHARDS,"frozen source count")
    for c in cases:
        p=h.turn.SOURCE/(c["id"]+".cnf")
        need(digest(p)==c["sha256"],"original SHA changed")
    return cases

def prepare():
    cases=frozen_cases()
    need(Path("checker/drat-trim").is_file(),"DRAT checker unavailable")
    for c in cases:
        f=features(h.turn.SOURCE/(c["id"]+".cnf"))
        need(choose(f) in MODES[:2],"unsupported route")
    ROOT.mkdir(parents=True,exist_ok=True)
    inputs=[c["sha256"] for c in cases]
    save(ROOT/"manifest.json",{
        "protocol":PROTO,"source_run":42477408128,
        "source_reused_after_results":True,"blind_holdout":False,
        "sources":SHARDS,"reps":REPS,"cap_s":CAP,"modes":list(MODES),
        "gate":GATE,"selection_uses_solver_outcomes":False,
        "selection_uses_case_id_or_sha":False,
        "method":"conservative source-only gate of bijective signed mapping; NOT certified symmetry breaking",
        "source_sha256":inputs,
        "proofs":"SAT original model verified; UNSAT DRAT verified on original or bijectively equivalent signed CNF",
        "promotion_allowed":False})
    tracked=("research/drnas_turn2select.py","research/drnas_turn2h_holdout.py",
        "research/drnas_turn2_structural.py","research/drnas_turn1_representation.py",
        "checker/drat-trim","built/bin/kissat_4_0_4",
        "turn2_holdout/manifest.json","turn2h_holdout/manifest.json",
        ".github/workflows/drnas-turn2select.yml")
    save(ROOT/"pins.json",{p:digest(p) for p in tracked})
    verify()
    print("TURN2SELECT_PREP_PASS",digest(ROOT/"manifest.json"),flush=True)

def verify():
    cases=frozen_cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["gate"]==GATE and
         m["modes"]==list(MODES) and m["source_reused_after_results"] and
         not m["blind_holdout"] and len(m["source_sha256"])==SHARDS and
         m["source_sha256"]==[c["sha256"] for c in cases],"manifest drift")
    for p,sha in json.loads((ROOT/"pins.json").read_text()).items():
        need(digest(p)==sha,"pin drift "+p)
    return cases

def worker(source,mode,directory):
    started=time.perf_counter()
    f=features(source) if mode=="structural_guard" else None
    actual=choose(f) if f is not None else mode
    need(actual in MODES[:2],"bad actual route")
    print(json.dumps({"event":"gate","mode":mode,"actual":actual,
            "features":f,"gate_s":round(time.perf_counter()-started,6)},
            sort_keys=True),flush=True)
    h.worker(source,actual,directory)

def trial(c,mode,rep,shard):
    source=h.turn.SOURCE/(c["id"]+".cnf")
    need(digest(source)==c["sha256"],"input mismatch")
    d=ROOT/"raw"/str(shard)/(str(rep)+"-"+mode)
    d.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    p=subprocess.Popen([sys.executable,__file__,"worker",
            "--source",str(source),"--mode",mode,"--directory",str(d)],
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,start_new_session=True)
    timed_out=False
    try:
        output,_=p.communicate(timeout=max(0.001,CAP-(time.perf_counter()-started)))
    except subprocess.TimeoutExpired:
        timed_out=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        output,_=p.communicate()
    elapsed=min(CAP,time.perf_counter()-started)
    (d/"worker.log").write_text(output[-18000:])
    ev=[]
    for line in output.splitlines():
        try:
            e=json.loads(line)
            if isinstance(e,dict):ev.append(e)
        except ValueError:pass
    g=[e for e in ev if e.get("event")=="gate"]
    ends=[e for e in ev if e.get("event")=="result"]
    status="TIMEOUT"
    proof="WALL_CAP_TIMEOUT"
    reported=None
    actual=None
    fs=None
    gate_s=None
    prep_s=None
    if not timed_out and elapsed<CAP:
        need(p.returncode==0 and len(g)==len(ends)==1,
             "worker fail "+output[-2500:])
        ge,fin=g[0],ends[0]
        actual=ge["actual"];fs=ge["features"];gate_s=ge["gate_s"]
        prep_s=fin["prep_s"];reported=fin["verdict"]
        need(actual in MODES[:2],"invalid route")
        if reported=="SAT":
            model={int(k):v for k,v in json.loads((d/"model.json").read_text()).items()}
            need(h.turn.t1.satisfies(h.turn.t1.parse(source)[1],model),
                 "original SAT model failed")
            status="SAT"
            proof="SAT_ORIGINAL_MODEL_VERIFIED"
        elif reported=="UNSAT":
            proof_file=d/"proof.out"
            proof_cnf=d/"signed.cnf" if actual=="kissat_struct_signed" else source
            if proof_file.is_file() and proof_file.stat().st_size>0:
                try:
                    check=subprocess.run(["checker/drat-trim",str(proof_cnf),str(proof_file)],
                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
                    (d/"proof_validation.log").write_text(check.stdout[-6000:])
                    if check.returncode==0 and "s VERIFIED" in check.stdout:
                        status="UNSAT"
                        proof="UNSAT_DRAT_VERIFIED_ON_EQUIVALENT_CNF"
                    else:
                        proof="UNSAT_UNCERTIFIED_NOT_SCORED"
                except subprocess.TimeoutExpired:
                    (d/"proof_validation.log").write_text("PROOF_CHECK_TIMEOUT")
                    proof="UNSAT_CERT_TIMEOUT_NOT_SCORED"
            else:proof="UNSAT_NO_PROOF_NOT_SCORED"
        else:need(False,"unknown native verdict")
    for rm in ("proof.out","signed.cnf"):
        path=d/rm
        if path.exists():path.unlink()
    row={"protocol":PROTO,"source_sha256":c["sha256"],"id":c["id"],
         "mode":mode,"rep":rep,"shard":shard,"route":actual,
         "features":fs,"gate_s":gate_s,"prep_s":prep_s,
         "status":status,"reported":reported,"proof":proof,
         "elapsed_s":round(elapsed,6),
         "par2_s":round(elapsed if status!="TIMEOUT" else 2*CAP,6)}
    print("TURN2SELECT_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row

def shard(index):
    cases=verify()
    need(0<=index<SHARDS,"shard range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    c=cases[index]
    rows=[]
    for rep in range(REPS):
        order=list(MODES)
        random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
        for mode in order:
            rows.append(trial(c,mode,rep,index))
            save(ROOT/("shard-%d.json"%index),rows)
    need(len(rows)==REPS*len(MODES),"shard incomplete")
    print("TURN2SELECT_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=verify()
    rows=[]
    seen=set()
    for i,c in enumerate(cases):
        subset=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(subset)==len(MODES)*REPS,"incomplete shard")
        for r in subset:
            key=(r["source_sha256"],r["rep"],r["mode"])
            need(key not in seen and r["source_sha256"]==c["sha256"]
                 and r["protocol"]==PROTO and r["shard"]==i
                 and r["mode"] in MODES and r["rep"] in range(REPS),
                 "provenance mismatch")
            seen.add(key)
            need(0<=r["elapsed_s"]<=CAP,"invalid clock")
            need(abs(r["par2_s"]-(r["elapsed_s"] if r["status"]!="TIMEOUT" else 2*CAP))<.00002,"PAR2 mismatch")
            need(r["status"]=="TIMEOUT" or r["proof"] in
                 ("SAT_ORIGINAL_MODEL_VERIFIED","UNSAT_DRAT_VERIFIED_ON_EQUIVALENT_CNF"),
                 "uncertified solution")
            if r["mode"]=="structural_guard" and r["route"] is not None:
                need(choose(r["features"])==r["route"],"gate not deterministic")
            rows.append(r)
    expected={(c["sha256"],rep,mode) for c in cases for rep in range(REPS) for mode in MODES}
    need(seen==expected and len(rows)==SHARDS*REPS*len(MODES),"missing trials")
    metrics={}
    for mode in MODES:
        x=[r for r in rows if r["mode"]==mode]
        metrics[mode]={"attempts":len(x),"solved":sum(r["status"]!="TIMEOUT" for r in x),
                       "sat":sum(r["status"]=="SAT" for r in x),
                       "unsat_verified":sum(r["status"]=="UNSAT" for r in x),
                       "par2_s":round(sum(r["par2_s"] for r in x),6)}
    keys={(r["source_sha256"],r["rep"],r["mode"]):r for r in rows}
    deltas=[]
    for c in cases:
        ref=sum(keys[c["sha256"],rep,"kissat_plain"]["par2_s"] for rep in range(REPS))
        guarded=sum(keys[c["sha256"],rep,"structural_guard"]["par2_s"] for rep in range(REPS))
        deltas.append({"sha256":c["sha256"],"plain_par2_s":round(ref,5),
                       "guarded_par2_s":round(guarded,5),
                       "gain_s":round(ref-guarded,5),
                       "route":[keys[c["sha256"],rep,"structural_guard"]["route"] for rep in range(REPS)]})
    report={"status":"TURN2SELECT_AUDIT_PASS","protocol":PROTO,
            "attempts":len(rows),"formulas":SHARDS,
            "blind_holdout":False,"reused_earlier_result_cohort":True,
            "promotion_allowed":False,"gate":GATE,
            "metrics":metrics,"paired_source_deltas":deltas}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("TURN2SELECT_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","shard","worker","audit"))
    p.add_argument("--source")
    p.add_argument("--mode",choices=MODES)
    p.add_argument("--directory")
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="worker":
        worker(a.source,a.mode,a.directory)
    elif a.action=="shard":
        shard(a.shard)
    else:
        globals()[a.action]()
