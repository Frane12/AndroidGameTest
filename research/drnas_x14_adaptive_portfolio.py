#!/usr/bin/env python3
"""X14: preregistered cheap source gate vs Kissat, CaDiCaL, CMS, front100, and 2-core race.
DEVELOPMENT REPLAY: 32 SHA-locked X11 originals; not an unseen/global holdout.
Full original CNF witness replay, independently cross-checked UNSAT scoring, wall PAR2,
child CPU accounting, time-boxed feature collection, and no modification to main.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random
import resource, signal, subprocess, tempfile, time
import mre_x13b_sample_gate as b
import mre_x11_placebo_causal as x11

ROOT = pathlib.Path("mre_x14")
PROTO = "DRNAS-X14-32SHA-DEVELOPMENT-6ARM-2SEED-15S-E2E-CPU-v1"
CAP, REPS, SHARDS = 15.0, 2, 8
ARMS = ("original", "kissat", "cadical", "front100", "parallel2", "x14_gate")
EXPECTED = 32 * REPS * len(ARMS)
THRESH_DUP, THRESH_BYTES, THRESH_SAMPLE_LINES = 2, 262144, 300

def need(ok,why):
    if not ok: raise RuntimeError("X14_FAIL_CLOSED " + why)

def write(path,data):
    p=pathlib.Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def digest(path):
    return b.sha(path)

def configure():
    b.ROOT=ROOT
    b.CAP=CAP
    b.PROTO=PROTO
    x11.ROOT=pathlib.Path("mre_x11")

def choose(signal_data):
    if signal_data["duplicates"] >= THRESH_DUP:
        return "front100", "sample_duplicate_gte_2"
    if signal_data["size_bytes"] >= THRESH_BYTES and signal_data["lines"] >= THRESH_SAMPLE_LINES:
        return "parallel2", "large_no_sample_duplicate"
    return "kissat", "cheap_fallback_reference"

def binary_hashes():
    return dict(native=digest("mre_x4/bin/native"),
                kissat=digest("built/bin/kissat_4_0_4"),
                cadical=digest("/usr/bin/cadical"),
                cms_shared_lib=digest("mre5/lib/libcryptominisat5.so.5.11"))

def freeze():
    configure()
    m=x11.verify()
    need(len(m["cases"])==32, "unexpected historical X11 source count")
    ROOT.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for c in m["cases"]:
        src=x11.ROOT/c["filename"]
        need(src.is_file() and digest(src)==c["sha256"], "original source SHA mismatch")
        sampled=b.cheap_duplicate_signal(src)
        decision,why=choose(sampled)
        manifest.append(dict(c,cheap_sample=sampled,frozen_gate_route=decision,
                             frozen_gate_reason=why))
    need(len({c["sha256"] for c in manifest})==32,"duplicate source SHA")
    write(ROOT/"manifest.json",dict(protocol=PROTO,cases=manifest,
        parent_x11_manifest_sha256=digest(x11.ROOT/"manifest.json"),
        binary_sha256=binary_hashes(),arms=ARMS,cap_s=CAP,reps=REPS,
        expected_trials=EXPECTED,shards=SHARDS,
        thresholds=dict(duplicates_min=THRESH_DUP,
                        large_bytes_min=THRESH_BYTES,
                        sample_lines_min=THRESH_SAMPLE_LINES),
        source_selection="unchanged frozen historical X11 originals",
        source_cohort_historical_not_blind=True,not_prospective_holdout=True,
        gate_features_precommitted_before_new_X14_results=True,
        SAT_original_witness_required=True,
        UNSAT_independent_LRAT=False,UNSAT_cross_solver_scoring_required=True,
        no_auto_promotion=True,policy_fixed_before_trial=True))
    verify()
    print("X14_FROZEN",json.dumps(dict(count=32,trials=EXPECTED,
          routes=dict(collections.Counter(c["frozen_gate_route"] for c in manifest)),
          binary_sha256=binary_hashes()),sort_keys=True),flush=True)

def verify():
    configure()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["expected_trials"]==EXPECTED and m["cap_s"]==CAP and
         m["reps"]==REPS and len(m["cases"])==32,"protocol drift")
    need(digest(x11.ROOT/"manifest.json")==m["parent_x11_manifest_sha256"],
         "parent original SHA manifest changed")
    need(binary_hashes()==m["binary_sha256"],"backend binary changed")
    seen=set()
    for c in m["cases"]:
        src=x11.ROOT/c["filename"]
        need(src.is_file() and digest(src)==c["sha256"] and
             c["sha256"] not in seen,"original SHA lost, duplicated or changed")
        seen.add(c["sha256"])
        sig=b.cheap_duplicate_signal(src)
        policy,reason=choose(sig)
        need(sig==c["cheap_sample"] and
             (policy,reason)==(c["frozen_gate_route"],c["frozen_gate_reason"]),
             "gate feature or frozen decision drift")
    return m

def child_cpu(before):
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    return (after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime)

def stop(proc):
    if proc.poll() is None:
        try: os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError: pass
    try: proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)

def outcome_of(backend,returncode,stdout,stderr,src):
    if backend=="native":
        need(returncode==0,"native exited unexpectedly "+stderr[-150:])
        gate=x11.x9.x6.x4.base.parse_gate(stdout,"x_native")
        need(not gate["applied"],"native unexpectedly transformed original CNF")
        status,model,_=x11.x9.x6.x4.base.cms.parsed_native(stdout)
        need(status in ("SAT","UNSAT","TIMEOUT","UNKNOWN","BUDGET"),
             "unrecognized native status")
    else:
        need(returncode in (10,20),"Kissat exited unexpectedly "+str(returncode)+stderr[-150:])
        status="SAT" if returncode==10 else "UNSAT"
        need(("s SATISFIABLE" if status=="SAT" else "s UNSATISFIABLE") in stdout,
             "reference verdict and status mismatch")
        model={}
        if status=="SAT":
            for line in stdout.splitlines():
                if line.startswith("v "):
                    for lit in map(int,line[2:].split()):
                        if lit:
                            need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                                 "reference model inconsistent")
                            model[abs(lit)]=lit>0
    if status=="SAT":
        x11.x9.x6.x4.base.cms.verify_model(src,model)
    return status

def parallel(c,rep,begin):
    src=x11.ROOT/c["filename"]
    seed=x11.seed(c,rep)
    outcome="TIMEOUT"
    winner=None
    statuses=[]
    handles=[]
    running=[]
    env=os.environ.copy()
    for key in ("DRNAS_MAX_CONFLICTS","DRNAS_X7_TRACE","DRNAS_X8_TRACE"):
        env.pop(key,None)
    with tempfile.TemporaryDirectory() as d:
        try:
            commands=[
                ("native",[str(pathlib.Path("mre_x4/bin/native").resolve()),
                           str(src.resolve()),"x_native",str(seed)]),
                ("kissat",[str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),
                           "--seed="+str(seed),str(src.resolve())])
            ]
            for backend,cmd in commands:
                if time.perf_counter()-begin >= CAP: break
                out=open(pathlib.Path(d)/(backend+".stdout"),"w+t")
                err=open(pathlib.Path(d)/(backend+".stderr"),"w+t")
                handles.extend((out,err))
                proc=subprocess.Popen(cmd,env=env,stdout=out,stderr=err,
                    text=True,start_new_session=True)
                running.append(dict(name=backend,p=proc,out=out,err=err,read=False))
            while time.perf_counter()-begin < CAP and winner is None:
                active=False
                for entry in running:
                    if entry["read"]: continue
                    code=entry["p"].poll()
                    if code is None:
                        active=True
                        continue
                    entry["read"]=True
                    entry["out"].flush();entry["err"].flush()
                    entry["out"].seek(0);entry["err"].seek(0)
                    status=outcome_of(entry["name"],code,
                         entry["out"].read(),entry["err"].read(),src)
                    statuses.append(dict(backend=entry["name"],status=status))
                    if status in ("SAT","UNSAT"):
                        winner=entry["name"];outcome=status
                        break
                if winner is None and active:
                    time.sleep(min(.005,max(0,CAP-(time.perf_counter()-begin))))
                if winner is None and not active: break
        finally:
            for entry in running: stop(entry["p"])
            for handle in handles: handle.close()
    return outcome,winner,statuses

def trial(c,rep,arm):
    need(rep in range(REPS) and arm in ARMS,"invalid trial")
    src=x11.ROOT/c["filename"]
    need(digest(src)==c["sha256"],"SHA drift before trial")
    start=time.perf_counter()
    cpu_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    profile_s=0.
    route=arm
    reason="explicit_arm"
    native=None
    statuses=[]
    preprocess_s=0.
    if arm=="x14_gate":
        sig=b.cheap_duplicate_signal(src)
        route,reason=choose(sig)
        need(sig==c["cheap_sample"] and route==c["frozen_gate_route"],
             "live gate disagrees with committed source-only decision")
        profile_s=time.perf_counter()-start
    if route=="parallel2":
        status,winner,statuses=parallel(c,rep,start)
        preprocess_s=profile_s
    else:
        need(route in ("original","kissat","cadical","front100"),
             "invalid routed solver")
        budget=CAP-(time.perf_counter()-start)
        if budget<=0.05:
            status="TIMEOUT";winner=None
        else:
            old_cap=b.CAP
            try:
                b.CAP=budget
                native=b.trial(c,rep,route)
            finally:
                b.CAP=old_cap
            status=native["status"]
            winner=("native" if route in ("original","front100") else route) \
                if status in ("SAT","UNSAT") else None
            preprocess_s=profile_s+native["preprocess_s"]
    elapsed=time.perf_counter()-start
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None
    cpu=child_cpu(cpu_before)
    return dict(protocol=PROTO,arm=arm,route=route,gate_reason=reason,
        original_sha256=c["sha256"],gbd=c["gbd"],cohort=c["cohort"],
        rep=rep,seed=x11.seed(c,rep),status=status,
        selected_backend=winner,source_SHA_verified=True,
        SAT_original_witness_verified=status=="SAT",
        UNSAT_independent_LRAT=False,
        cap_s=CAP,elapsed_s=round(elapsed,6),
        PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
        child_cpu_s=round(cpu,6),preprocess_s=round(preprocess_s,6),
        profile_s=round(profile_s,6),parallel_statuses=statuses,
        source_only_precommitted=True,
        two_core_race=route=="parallel2")

def selftest():
    configure()
    b.selftest()
    need(choose(dict(duplicates=2,lines=1,size_bytes=1))[0]=="front100",
         "duplicate choice mismatch")
    need(choose(dict(duplicates=0,lines=1000,size_bytes=262144))[0]=="parallel2",
         "large choice mismatch")
    need(choose(dict(duplicates=0,lines=2,size_bytes=10))[0]=="kissat",
         "fallback mismatch")
    print("X14_SELFTEST_PASS",flush=True)

def shard(idx):
    m=verify()
    need(idx in range(SHARDS),"bad shard index")
    chosen=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
    need(len(chosen)==4,"wrong shard cardinality")
    rows=[]
    for c in chosen:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(x11.seed(c,rep)).shuffle(order)
            for arm in order:
                r=trial(c,rep,arm)
                rows.append(r)
                write(ROOT/("shard-%d.json"%idx),rows)
                print("X14_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==48,"incomplete shard")
    print("X14_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    cases={c["sha256"]:c for c in m["cases"]}
    rows=[]
    for idx in range(SHARDS):
        rows+=json.loads((ROOT/("shard-%d.json"%idx)).read_text())
    expected={(c,rep,arm) for c in cases for rep in range(REPS) for arm in ARMS}
    actual={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(actual)==EXPECTED and actual==expected,
         "missing or duplicate source-seed-arm paired trials")
    for srcsha,c in cases.items():
        part=[r for r in rows if r["original_sha256"]==srcsha]
        statuses={r["status"] for r in part if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT/UNSAT disagreement on original CNF")
        native_unsat=any(r["status"]=="UNSAT" and
            r["selected_backend"]=="native" for r in part)
        kissat_unsat=any(r["status"]=="UNSAT" and
            r["selected_backend"]=="kissat" for r in part)
        cadical_unsat=any(r["status"]=="UNSAT" and
            r["selected_backend"]=="cadical" for r in part)
        cross=(native_unsat and (kissat_unsat or cadical_unsat)) or \
              (kissat_unsat and cadical_unsat)
        for r in part:
            need(r["protocol"]==PROTO and r["gbd"]==c["gbd"] and
                 r["cap_s"]==CAP and r["seed"]==x11.seed(c,r["rep"]),
                 "source/seed/protocol drift")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "SAT original model not verified")
            need(r["status"]!="TIMEOUT" or r["PAR2_s"]==2*CAP,
                 "incorrect timeout PAR2")
            need(r["status"]=="TIMEOUT" or
                 (r["elapsed_s"]<=CAP and r["PAR2_s"]==r["elapsed_s"]),
                 "incorrect solved E2E PAR2")
            r["accepted"]=r["status"]=="SAT" or (r["status"]=="UNSAT" and cross)
            r["audited_PAR2_s"]=r["PAR2_s"] if r["accepted"] else 2*CAP
    score={}
    for arm in ARMS:
        part=[r for r in rows if r["arm"]==arm]
        score[arm]=dict(n=len(part),
            solved=sum(r["accepted"] for r in part),
            SAT_verified=sum(r["accepted"] and r["status"]=="SAT" for r in part),
            UNSAT_crosschecked=sum(r["accepted"] and r["status"]=="UNSAT" for r in part),
            raw_timeouts=sum(r["status"]=="TIMEOUT" for r in part),
            PAR2_s=round(sum(r["audited_PAR2_s"] for r in part),6),
            child_cpu_s=round(sum(r["child_cpu_s"] for r in part),6),
            preprocessing_s=round(sum(r["preprocess_s"] for r in part),6),
            profile_s=round(sum(r["profile_s"] for r in part),6))
    for arm,row in score.items():
        for base in ("kissat","cadical","original","front100"):
            v=score[base]["PAR2_s"]
            row["pct_less_PAR2_vs_"+base]=round(100*(1-row["PAR2_s"]/v),4)
            row["speedup_vs_"+base]=round(v/row["PAR2_s"],5)
        row["CPU_cost_multiple_vs_Kissat"]=round(
           row["child_cpu_s"]/max(.0001,score["kissat"]["child_cpu_s"]),4)
    out=dict(protocol=PROTO,source_count=32,trials=len(rows),
        cohort="historical_X11_development_replay_not_blind",
        no_auto_promotion=True,UNSAT_independent_LRAT=False,
        cost_metric="total child user+sys CPU; wall PAR2 includes gate, preprocessing and process teardown",
        gate_routes=dict(collections.Counter(r["route"] for r in rows
                                              if r["arm"]=="x14_gate")),
        score=score,rows=rows)
    write(ROOT/"report.json",out)
    print("X14_FINAL",json.dumps({k:v for k,v in out.items() if k!="rows"},
        sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    configure()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":
        verify()
        print("X14_VERIFY_PASS",flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()

if __name__=="__main__":main()
