#!/usr/bin/env python3
"""X16A: four concurrently benchmarked asymmetric single-vCPU dual-CDCL races.

95:5, 90:10, 80:20, 70:30 native:Kissat scheduling, each with its own
paired native, Kissat, and enforced 50:50 control on the same runner.
Fixed 100 ms cycle, process-group SIGSTOP/SIGCONT, one Linux logical CPU.
All 16 original SHA from prior X16 re-used (NOT new blind formulas).
Full original-model SAT verification; UNSAT reference agreement only, no LRAT.
No changes to stable solver or any auto-promotion.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,resource,signal,tempfile,time

import drnas_x16_singlecore_dual as x16

ROOT=pathlib.Path("mre_x16a")
SOURCE=x16.ROOT
PROTO="DRNAS-X16A-4ASYM-95-90-80-70-16SHA-2REP-12S-PAIRED-CPU-PAR2-v1"
CAP=12.0
REPS=2
RATIOS=(95,90,80,70)
ARMS=("native","kissat","balanced50","asym")
PER_JOB=16*REPS*len(ARMS)
EXPECTED=4*PER_JOB
TICK_SECONDS=.100

def need(ok,message):
    if not ok:raise RuntimeError("X16A_FAIL_CLOSED "+str(message))

def write(path,value):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")

def digest(path):
    return x16.digest(path)

def freeze():
    src=x16.verify()
    need(src["protocol"]==x16.PROTO and len(src["cases"])==16,
         "X16 official frozen source protocol changed")
    cases=src["cases"]
    need(len({c["sha256"] for c in cases})==16,"duplicate original SHA")
    manifest=dict(protocol=PROTO,
        source_x16_manifest_sha256=digest(SOURCE/"manifest.json"),
        source_x16_run_id=42574891889,
        original_source_sha=[c["sha256"] for c in cases],
        source_count=16,ratios_native_pct=RATIOS,
        control_arms=ARMS,cap_s=CAP,reps=REPS,
        per_parallel_job_trials=PER_JOB,total_trials=EXPECTED,
        cycle_ms=100,
        time_share_one_logical_cpu=True,
        allocated_guest_logical_cpu_not_proof_of_physical_core=True,
        source_reuse_not_blind=True,
        original_SAT_witness_verified=True,
        independent_UNSAT_LRAT=False,
        UNSAT_cross_solver_agreement_for_scoring=True,
        randomized_arm_order_within_each_source_seed=True,
        cpu_metric="total summed child user+sys CPU; parent control CPU separate",
        wall_metric="full E2E wall PAR2 including process startup and cleanup",
        no_auto_promotion=True,binary_sha256=x16.binaries())
    write(ROOT/"manifest.json",manifest)
    verify()
    print("X16A_FROZEN",json.dumps(dict(cases=16,
          variants=RATIOS,arms=ARMS,
          total_trials=EXPECTED,per_job=PER_JOB,
          cpu=x16.topology()),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    src=x16.verify()
    need(m["protocol"]==PROTO and
         m["source_x16_manifest_sha256"]==digest(SOURCE/"manifest.json") and
         m["original_source_sha"]==[c["sha256"] for c in src["cases"]] and
         m["binary_sha256"]==x16.binaries() and
         m["ratios_native_pct"]==list(RATIOS) and
         m["control_arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["reps"]==REPS and
         m["per_parallel_job_trials"]==PER_JOB and
         m["total_trials"]==EXPECTED,
         "X16A immutable source/control protocol drift")
    return src["cases"]

def run_trial(c,rep,arm,ratio):
    need(ratio in RATIOS and arm in ARMS and rep in range(REPS),
         "unregistered paired arm")
    p=SOURCE/c["filename"]
    need(p.is_file() and digest(p)==c["sha256"],"original CNF SHA changed")
    seed=x16.x11.seed(c,rep)
    topology=x16.topology()
    cpu=topology["first"]
    child_before=x16.rusage_snapshot(resource.RUSAGE_CHILDREN)
    parent_before=x16.rusage_snapshot(resource.RUSAGE_SELF)
    t0=time.perf_counter()
    winner=None;status="TIMEOUT";observations=[]
    switches=0;raw_affinity={}
    stop_ms=(ratio if arm=="asym" else 50) if arm in ("asym","balanced50") else None
    entries=[]
    with tempfile.TemporaryDirectory(prefix="x16a-",dir=ROOT) as directory:
        try:
            backends=["native"] if arm=="native" else (
                     ["kissat"] if arm=="kissat" else ["native","kissat"])
            for backend in backends:
                if time.perf_counter()-t0>=CAP:break
                e=x16.launch(backend,p,seed,cpu,directory)
                entries.append(e)
                try:aff=sorted(os.sched_getaffinity(e["p"].pid))
                except ProcessLookupError:aff=[cpu]
                need(aff==[cpu],"two solver processes not pinned to one logical CPU")
                raw_affinity[backend]=aff

            # Ensure the reference scout is stopped before the native slice.
            if stop_ms is not None and len(entries)==2:
                x16.signal_entry(entries[1],signal.SIGSTOP)
                active="native"
                next_switch=time.perf_counter()+stop_ms/1000
            else:
                active="native";next_switch=None

            while time.perf_counter()-t0<CAP and winner is None:
                running=[]
                for e in entries:
                    if e["read"]:continue
                    if e["p"].poll() is None:
                        running.append(e)
                    else:
                        observed=x16.completed_result(e,p)
                        observations.append(dict(backend=e["name"],status=observed))
                        if observed in ("SAT","UNSAT"):
                            status=observed;winner=e["name"];break
                if winner is not None or not running:break
                now=time.perf_counter()
                if next_switch is not None and now>=next_switch:
                    if len(running)==2:
                        prev=next(e for e in entries if e["name"]==active)
                        nxt=next(e for e in entries if e["name"]!=active)
                        x16.signal_entry(prev,signal.SIGSTOP)
                        x16.signal_entry(nxt,signal.SIGCONT)
                        active=nxt["name"];switches+=1
                        current_slice_ms=100-stop_ms if active=="kissat" else stop_ms
                        next_switch=now+current_slice_ms/1000
                    else:
                        # Once one solver has exited, survivor inherits 100% CPU.
                        x16.signal_entry(running[0],signal.SIGCONT)
                        next_switch=None
                delay=min(.0015,max(0,CAP-(time.perf_counter()-t0)))
                if next_switch is not None:
                    delay=min(delay,max(0,next_switch-time.perf_counter()))
                if delay>0:time.sleep(delay)
        finally:
            x16.cleanup(entries)
    elapsed=time.perf_counter()-t0
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None
    child=x16.counters_diff(child_before,x16.rusage_snapshot(resource.RUSAGE_CHILDREN))
    parent=x16.counters_diff(parent_before,x16.rusage_snapshot(resource.RUSAGE_SELF))
    return dict(protocol=PROTO, ratio_native_pct=ratio,
        ratio_kissat_pct=100-ratio,cycle_ms=100,
        arm=arm,original_sha256=c["sha256"],gbd=c["gbd"],
        tier=c.get("previous_X15_tier","historical"),
        rep=rep,seed=seed,cap_s=CAP,
        status=status,selected_backend=winner,
        SAT_original_witness_verified=(status=="SAT"),
        independent_UNSAT_LRAT=False,
        elapsed_s=round(elapsed,6),
        PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
        child_cpu_s=child["cpu_s"],parent_cpu_s=parent["cpu_s"],
        child_voluntary_ctx=child["voluntary"],
        child_involuntary_ctx=child["involuntary"],
        parent_voluntary_ctx=parent["voluntary"],
        parent_involuntary_ctx=parent["involuntary"],
        cpu_affinity=raw_affinity,
        scheduled_transitions=switches,completed_outcomes=observations,
        requested_native_cpu_share_pct=stop_ms if stop_ms is not None else
                                       (100 if arm=="native" else 0 if arm=="kissat" else None),
        all_solver_children_pinned_same_logical_cpu=True)

def run_ratio(ratio):
    cases=verify()
    need(ratio in RATIOS,"unexpected scheduling allocation")
    rows=[]
    for c in cases:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(x16.x11.seed(c,rep)^ratio).shuffle(order)
            for arm in order:
                row=run_trial(c,rep,arm,ratio)
                need(row["original_sha256"]==c["sha256"] and
                     row["seed"]==x16.x11.seed(c,rep),
                     "paired source/seed drift")
                rows.append(row)
                write(ROOT/("ratio-%d.json"%ratio),rows)
                print("X16A_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==PER_JOB,"incomplete variant")
    print("X16A_VARIANT_PASS",ratio,len(rows),flush=True)

def score(rows):
    out={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        out[arm]=dict(n=len(a),
            PAR2_s=round(sum(r["audited_PAR2_s"] for r in a),6),
            solved=sum(r["accepted"] for r in a),
            SAT_original_witness_verified=sum(
                r["accepted"] and r["status"]=="SAT" for r in a),
            UNSAT_crosschecked_no_LRAT=sum(
                r["accepted"] and r["status"]=="UNSAT" for r in a),
            child_cpu_s=round(sum(r["child_cpu_s"] for r in a),6),
            parent_cpu_s=round(sum(r["parent_cpu_s"] for r in a),6),
            voluntary_ctx=sum(r["child_voluntary_ctx"] for r in a),
            involuntary_ctx=sum(r["child_involuntary_ctx"] for r in a),
            scheduled_transitions=sum(r["scheduled_transitions"] for r in a),
            timed_out=sum(r["status"]=="TIMEOUT" for r in a))
    for arm in out:
        out[arm]["PAR2_change_vs_paired_native_pct"]=round(
            100*(1-out[arm]["PAR2_s"]/out["native"]["PAR2_s"]),4)
        out[arm]["CPU_multiple_vs_paired_native"]=round(
            out[arm]["child_cpu_s"]/max(out["native"]["child_cpu_s"],1e-8),5)
    return out

def audit():
    cases=verify()
    roster={c["sha256"]:c for c in cases}
    rows=[]
    for ratio in RATIOS:
        f=ROOT/("ratio-%d.json"%ratio)
        need(f.is_file(),"variant output missing: "+str(ratio))
        subset=json.loads(f.read_text())
        need(len(subset)==PER_JOB,"incomplete variant "+str(ratio))
        rows+=subset
    expected={(c,rep,arm,ratio) for c in roster for rep in range(REPS)
                for arm in ARMS for ratio in RATIOS}
    actual={(r["original_sha256"],r["rep"],r["arm"],
             r["ratio_native_pct"]) for r in rows}
    need(len(rows)==len(actual)==EXPECTED and actual==expected,
         "missing or duplicated variant trials")
    for sha,c in roster.items():
        subset=[r for r in rows if r["original_sha256"]==sha]
        decided={r["status"] for r in subset if r["status"] in ("SAT","UNSAT")}
        need(len(decided)<=1,"contradictory SAT/UNSAT results")
        native_unsat=any(r["status"]=="UNSAT" and
                         r["selected_backend"]=="native" for r in subset)
        kissat_unsat=any(r["status"]=="UNSAT" and
                         r["selected_backend"]=="kissat" for r in subset)
        cross= native_unsat and kissat_unsat
        for r in subset:
            need(r["protocol"]==PROTO and r["gbd"]==c["gbd"] and
                 r["seed"]==x16.x11.seed(c,r["rep"]) and r["cap_s"]==CAP,
                 "trial source/seed mismatch")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "SAT model not verified on original")
            need(r["status"]!="TIMEOUT" or r["PAR2_s"]==2*CAP,
                 "PAR2 timeout penalty drift")
            need(r["status"]=="TIMEOUT" or
                 (r["elapsed_s"]<=CAP and r["PAR2_s"]==r["elapsed_s"]),
                 "solved PAR2 not actual wall E2E")
            need(r["all_solver_children_pinned_same_logical_cpu"] and
                 all(z==[x16.topology()["first"]]
                     for z in r["cpu_affinity"].values()),
                 "single-vCPU constraint broken")
            need(r["child_cpu_s"]>=0 and r["parent_cpu_s"]>=0,
                 "negative resource accounting")
            r["accepted"]=r["status"]=="SAT" or (r["status"]=="UNSAT" and cross)
            r["audited_PAR2_s"]=r["PAR2_s"] if r["accepted"] else 2*CAP
    by_ratio={}
    for ratio in RATIOS:
        chunk=[r for r in rows if r["ratio_native_pct"]==ratio]
        by_ratio[str(ratio)]=dict(
            all=score(chunk),
            development=score([r for r in chunk if r["tier"]=="development"]),
            prior_X15_holdout_replay=score([r for r in chunk if r["tier"]=="holdout"]))
    report=dict(protocol=PROTO,source_count=16,trials=EXPECTED,
        no_auto_promotion=True,not_blind_X16_replay=True,
        four_ratios_in_independent_parallel_GitHub_jobs=True,
        results=by_ratio,rows=rows)
    write(ROOT/"report.json",report)
    print("X16A_FINAL",json.dumps({k:v for k,v in report.items() if k!="rows"},
        sort_keys=True),flush=True)

def selftest():
    need(RATIOS==(95,90,80,70),"four ratio protocol drift")
    need(len(ARMS)==4 and EXPECTED==512 and PER_JOB==128,"trial count drift")
    need(all(0<100-r<r<100 for r in RATIOS),"bad asymmetric policy")
    x16.selftest()
    print("X16A_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","ratio","audit"))
    p.add_argument("--ratio",type=int,default=90)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":verify();print("X16A_VERIFY_PASS",flush=True)
    elif a.action=="ratio":run_ratio(a.ratio)
    else:audit()

if __name__=="__main__":main()
