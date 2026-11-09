#!/usr/bin/env python3
"""DRNAS X16: real Linux one-logical-CPU time sharing of two SAT processes.

The two CDCL processes use the same source SHA, seed, original CNF and one
CPU affinity for the entire solve. Compare OS-scheduled pair, explicit
SIGSTOP/SIGCONT alternation at 5,20,100 ms, genuine two-vCPU race, original
native, Kissat and native front100. We compare wall PAR2 and total child CPU.
This is NOT two simultaneous computations on one core. GitHub's virtualized
runner cannot establish an underlying physical core identity.

Replays X15's 16 frozen sources (including formerly new examples): NOT BLIND.
SAT models replayed on original CNF; UNSAT scored only after independent
backend cross-agreement, NOT independent LRAT proof.
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
import signal
import subprocess
import tempfile
import time
import shutil
import sys

import mre_x11_placebo_causal as x11
import mre_x13b_sample_gate as b
import drnas_x14_adaptive_portfolio as x14

ROOT=pathlib.Path("mre_x16")
X15=pathlib.Path("mre_x15")
PROTO="DRNAS-X16-SINGLE-VCPU-DUAL-CDCL-16SHA-8ARM-2REP-12S-E2E-v1"
CAP=12.0
REPS=2
SHARDS=8
ARMS=("native1","front100_1","kissat1","os_share1",
      "slice5_1","slice20_1","slice100_1","race2")
EXPECTED=16*REPS*len(ARMS)
PER_SHARD=2*REPS*len(ARMS)
SLICES={"slice5_1":0.005,"slice20_1":0.020,"slice100_1":0.100}


def need(ok, msg):
    if not ok: raise RuntimeError("X16_FAIL_CLOSED "+str(msg))


def save(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")


def digest(path):
    return b.sha(path)


def configure():
    x11.ROOT=ROOT


def rusage_snapshot(kind):
    v=resource.getrusage(kind)
    return (v.ru_utime+v.ru_stime,v.ru_nvcsw,v.ru_nivcsw)


def counters_diff(before,after):
    return dict(cpu_s=round(max(0,after[0]-before[0]),6),
                voluntary=max(0,after[1]-before[1]),
                involuntary=max(0,after[2]-before[2]))


def topology():
    allowed=sorted(os.sched_getaffinity(0))
    need(len(allowed)>=2,"two allowed logical CPUs required for 2-vCPU reference")
    # Select different physical core if the guest exposes reliable topology.
    def physical_key(cpu):
        p=pathlib.Path("/sys/devices/system/cpu/cpu%d/topology"%cpu)
        try:
            return ((p/"physical_package_id").read_text().strip(),
                    (p/"core_id").read_text().strip())
        except OSError:
            return None
    a=allowed[0]
    distinct=next((v for v in allowed[1:] if physical_key(v)!=physical_key(a)),None)
    second=distinct if distinct is not None else allowed[1]
    return dict(allowed=allowed,first=a,second=second,
                exposed_physical_distinction=bool(distinct is not None
                    and physical_key(a) is not None and physical_key(second) is not None),
                runner_is_virtualized=True)


def binaries():
    return x14.binary_hashes()


def freeze():
    configure()
    ROOT.mkdir(exist_ok=True)
    old=json.loads((X15/"manifest.json").read_text())
    need(len(old["cases"])==16 and old["expected_trials"]==192,
         "X15 frozen source roster drift")
    h=binaries()
    need(old["binary_sha256"]==h,"X15 pinned backend binary sha mismatch")
    cases=[]
    for c in old["cases"]:
        src=X15/c["filename"]; target=ROOT/c["filename"]
        need(src.is_file() and digest(src)==c["sha256"],"X15 source SHA drift")
        shutil.copyfile(src,target)
        entry=dict(c)
        entry["cohort"]="X15_historical_replay_not_blind"
        entry["previous_X15_tier"]=c["tier"]
        entry["x16_status"]="frozen_before_X16_runtime"
        cases.append(entry)
    need(len(set(c["sha256"] for c in cases))==16 and
         len(set(c["gbd"] for c in cases))==16,"source duplicates")
    top=topology()
    m=dict(protocol=PROTO,cap_s=CAP,reps=REPS,shards=SHARDS,
           arms=ARMS,expected_trials=EXPECTED,cases=cases,
           x15_source_manifest_sha256=digest(X15/"manifest.json"),
           x15_run_id=42573523992,
           source_replay_not_blind=True,
           previous_holdout_is_now_reused=True,
           historical_global_exclusions_not_guaranteed=True,
           no_auto_promotion=True,
           UNSAT_independent_LRAT=False,
           SAT_original_model_verification=True,
           UNSAT_independent_backend_agreement_required=True,
           cpu_semantics="Linux sched_setaffinity exactly one logical vCPU for both processes; guest topology not physical proof",
           topology_at_freeze=top,
           slice_s=SLICES,backend_sha256=h,
           trial_costs="wall E2E including rewriting/launch/teardown/model replay; total child CPU; parent CPU; child context switches")
    save(ROOT/"manifest.json",m)
    verify()
    print("X16_FROZEN",json.dumps(dict(sources=len(cases),trials=EXPECTED,
          cpu_selection=top,arms=ARMS),sort_keys=True),flush=True)


def verify():
    configure()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["cap_s"]==CAP and m["reps"]==REPS
         and m["arms"]==list(ARMS) and m["expected_trials"]==EXPECTED
         and len(m["cases"])==16,"protocol drift")
    need(m["backend_sha256"]==binaries(),"binary drift between jobs")
    seen=set()
    for c in m["cases"]:
        src=ROOT/c["filename"]
        need(src.is_file() and digest(src)==c["sha256"] and
             c["sha256"] not in seen,"original CNF hash changed")
        seen.add(c["sha256"])
    need(len(topology()["allowed"])>=2,"unavailable CPU pair")
    return m


def command(which,src,seed):
    path=pathlib.Path(src).resolve()
    if which=="native":
        return [str(pathlib.Path("mre_x4/bin/native").resolve()),
                str(path),"x_native",str(seed)]
    if which=="kissat":
        return [str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),
                "--seed="+str(seed),str(path)]
    need(False,"invalid backend")


def launch(which,src,seed,cpu,temp):
    out=open(pathlib.Path(temp)/(which+".stdout"),"w+t")
    err=open(pathlib.Path(temp)/(which+".stderr"),"w+t")
    try:
        # Affinity is set in child BEFORE exec, no unpinned solve window.
        child=subprocess.Popen(command(which,src,seed),
              stdout=out,stderr=err,close_fds=True,start_new_session=True,
              preexec_fn=lambda:os.sched_setaffinity(0,{cpu}))
    except Exception:
        out.close();err.close();raise
    return dict(name=which,p=child,out=out,err=err,read=False,cpu=cpu)


def signal_entry(entry,sig):
    if entry["p"].poll() is not None:return False
    try:
        os.killpg(entry["p"].pid,sig)
        return True
    except ProcessLookupError:
        return False


def cleanup(entries):
    for e in entries:
        if e["p"].poll() is None:
            try:os.killpg(e["p"].pid,signal.SIGKILL)
            except ProcessLookupError:pass
        try:e["p"].wait(timeout=2)
        except subprocess.TimeoutExpired:
            e["p"].kill();e["p"].wait(timeout=2)
        e["out"].close();e["err"].close()


def completed_result(entry,original):
    rc=entry["p"].poll()
    if rc is None:return None
    entry["read"]=True
    entry["out"].flush();entry["err"].flush()
    entry["out"].seek(0);entry["err"].seek(0)
    output=entry["out"].read();errors=entry["err"].read()
    return x14.outcome_of(entry["name"],rc,output,errors,original)


def run_trial(c,rep,arm):
    need(rep in range(REPS) and arm in ARMS,"bad arm/rep")
    original=ROOT/c["filename"]
    need(digest(original)==c["sha256"],"input SHA drift")
    seed=x11.seed(c,rep)
    available=topology()
    first,second=available["first"],available["second"]
    before_child=rusage_snapshot(resource.RUSAGE_CHILDREN)
    before_parent=rusage_snapshot(resource.RUSAGE_SELF)
    begin=time.perf_counter()
    used=original
    prep_s=0.0
    switches=0
    active="native"
    statuses=[]
    winner=None
    status="TIMEOUT"
    observed_affinities={}
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        if arm=="front100_1":
            nv,clauses=x11.x9.x2.parse(original)
            changed=x11.transform(clauses,"front100")
            need(collections.Counter(map(tuple,changed))==
                 collections.Counter(map(tuple,clauses)),
                 "front100 mutated exact original clause multiset")
            used=pathlib.Path(td)/"front100.cnf"
            x11.x9.x2.write(used,nv,changed)
        prep_s=time.perf_counter()-begin
        entries=[]
        try:
            backends=(["native"] if arm in ("native1","front100_1") else
                      ["kissat"] if arm=="kissat1" else ["native","kissat"])
            for backend in backends:
                if time.perf_counter()-begin>=CAP:break
                cpu=(second if backend=="kissat" and arm=="race2" else first)
                e=launch(backend,used,seed,cpu,td)
                entries.append(e)
                try:aff=sorted(os.sched_getaffinity(e["p"].pid))
                except ProcessLookupError:aff=[cpu]
                need(aff==[cpu],"child affinity violates pinned logical CPU")
                observed_affinities[backend]=aff
            slice_s=SLICES.get(arm)
            if slice_s is not None and len(entries)==2:
                # Both processes are pinned to one logical CPU, and then
                # execution is explicitly alternated by OS stop/continue.
                signal_entry(entries[1],signal.SIGSTOP)
                next_slice=time.perf_counter()+slice_s
                active="native"
            else:next_slice=None
            while time.perf_counter()-begin<CAP and winner is None:
                any_running=False
                for e in entries:
                    if e["read"]:continue
                    if e["p"].poll() is None:
                        any_running=True
                        continue
                    result=completed_result(e,original)
                    statuses.append(dict(backend=e["name"],status=result))
                    if result in ("SAT","UNSAT"):
                        winner=e["name"];status=result;break
                if winner is not None:break
                if not any_running:break
                now=time.perf_counter()
                if next_slice is not None and now>=next_slice:
                    live=[e for e in entries if e["p"].poll() is None]
                    if len(live)==2:
                        previous=next(e for e in entries if e["name"]==active)
                        following=next(e for e in entries if e["name"]!=active)
                        signal_entry(previous,signal.SIGSTOP)
                        signal_entry(following,signal.SIGCONT)
                        active=following["name"]
                        switches+=1
                    elif len(live)==1:
                        signal_entry(live[0],signal.SIGCONT)
                    next_slice=now+slice_s
                pause=(min(.0015,slice_s/4) if slice_s is not None else .003)
                time.sleep(min(pause,max(0,CAP-(time.perf_counter()-begin))))
        finally:
            cleanup(entries)
    elapsed=time.perf_counter()-begin
    if status not in ("SAT","UNSAT") or elapsed>CAP:
        status="TIMEOUT";winner=None
    child=counters_diff(before_child,rusage_snapshot(resource.RUSAGE_CHILDREN))
    parent=counters_diff(before_parent,rusage_snapshot(resource.RUSAGE_SELF))
    return dict(protocol=PROTO,arm=arm,original_sha256=c["sha256"],
       gbd=c["gbd"],tier=c["previous_X15_tier"],rep=rep,seed=seed,
       status=status,selected_backend=winner,
       SAT_original_witness_verified=status=="SAT",
       UNSAT_independent_LRAT=False,
       elapsed_s=round(elapsed,6),cap_s=CAP,
       PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
       prep_s=round(prep_s,6),child_cpu_s=child["cpu_s"],
       parent_cpu_s=parent["cpu_s"],
       child_voluntary_ctx=child["voluntary"],
       child_involuntary_ctx=child["involuntary"],
       parent_voluntary_ctx=parent["voluntary"],
       parent_involuntary_ctx=parent["involuntary"],
       cpu_affinity=observed_affinities,
       sched_switches=switches,requested_slice_ms=round(1000*SLICES[arm])
          if arm in SLICES else None,
       logical_cpu_mode=("two_distinct_logical" if arm=="race2" else "one_logical"),
       parallel_statuses=statuses,
       cpu_available_count=len(available["allowed"]))


def selftest():
    b.selftest()
    need(EXPECTED==256 and len(ARMS)==8 and SHARDS==8,"locked trial count")
    x=topology()
    need(x["first"]!=x["second"],"two-core reference invalid")
    for arm in SLICES:need(SLICES[arm]>0,"invalid time slice")
    # Prove a child executes with an actual one-CPU affinity.
    cmd=[sys.executable,"-c","import os;print(','.join(map(str,sorted(os.sched_getaffinity(0)))))"]
    result=subprocess.run(cmd,text=True,capture_output=True,
            preexec_fn=lambda:os.sched_setaffinity(0,{x["first"]}),timeout=5,
            check=True)
    need(result.stdout.strip()==str(x["first"]),"child one-vCPU selftest failed")
    print("X16_SELFTEST_PASS",json.dumps(x,sort_keys=True),flush=True)


def shard(idx):
    m=verify()
    need(0<=idx<SHARDS,"bad shard index")
    selected=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
    need(len(selected)==2,"shard source count")
    rows=[]
    for c in selected:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(x11.seed(c,rep)).shuffle(arms)
            for arm in arms:
                r=run_trial(c,rep,arm)
                need(r["original_sha256"]==c["sha256"] and
                     r["seed"]==x11.seed(c,rep),"source/seed pairing drift")
                rows.append(r)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("X16_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==PER_SHARD,"short shard")
    print("X16_SHARD_PASS",idx,len(rows),flush=True)


def audit():
    m=verify()
    roster={c["sha256"]:c for c in m["cases"]}
    rows=[]
    for i in range(SHARDS):
        rows+=json.loads((ROOT/("shard-%d.json"%i)).read_text())
    expected={(sha,rep,arm) for sha in roster for rep in range(REPS) for arm in ARMS}
    observed={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(observed)==EXPECTED and observed==expected,
         "missing or duplicated paired original SHA tests")
    for sha,c in roster.items():
        group=[r for r in rows if r["original_sha256"]==sha]
        verdicts={r["status"] for r in group if r["status"] in ("SAT","UNSAT")}
        need(len(verdicts)<=1,"cross-solver contradictory result")
        unsat_native=any(r["status"]=="UNSAT" and
                         r["selected_backend"]=="native" for r in group)
        unsat_kissat=any(r["status"]=="UNSAT" and
                         r["selected_backend"]=="kissat" for r in group)
        agreement=unsat_native and unsat_kissat
        for r in group:
            need(r["protocol"]==PROTO and r["gbd"]==c["gbd"] and
                 r["seed"]==x11.seed(c,r["rep"]) and
                 r["cap_s"]==CAP and r["tier"]==c["previous_X15_tier"],
                 "trial header mismatch")
            need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
                 "SAT witness missing")
            need(r["status"]!="TIMEOUT" or r["PAR2_s"]==2*CAP,
                 "wrong timeout PAR2")
            need(r["status"]=="TIMEOUT" or
                 (r["elapsed_s"]<=CAP and r["PAR2_s"]==r["elapsed_s"]),
                 "wrong E2E solved PAR2")
            need(len(r["cpu_affinity"]) in (1,2) and
                 all(len(z)==1 for z in r["cpu_affinity"].values()),
                 "unpinned logical CPU")
            if r["arm"]=="race2":
                if len(r["cpu_affinity"])==2:
                    need(r["cpu_affinity"]["native"]!=r["cpu_affinity"]["kissat"],
                         "two-core reference ran on same CPU")
            else:
                need(len({z[0] for z in r["cpu_affinity"].values()})<=1,
                     "one-core experiment used two logical CPUs")
            need(r["child_cpu_s"]>=0 and r["parent_cpu_s"]>=0 and
                 r["sched_switches"]>=0,"bad resource measurements")
            r["accepted"]=r["status"]=="SAT" or (
                r["status"]=="UNSAT" and agreement)
            r["audited_PAR2_s"]=r["PAR2_s"] if r["accepted"] else 2*CAP
    def score(sub):
        scores={}
        for arm in ARMS:
            part=[r for r in sub if r["arm"]==arm]
            scores[arm]=dict(n=len(part),
              solved=sum(r["accepted"] for r in part),
              SAT_original_verified=sum(r["accepted"] and r["status"]=="SAT" for r in part),
              UNSAT_reference_agreed=sum(r["accepted"] and r["status"]=="UNSAT" for r in part),
              timeouts=sum(r["status"]=="TIMEOUT" for r in part),
              PAR2_s=round(sum(r["audited_PAR2_s"] for r in part),6),
              child_cpu_s=round(sum(r["child_cpu_s"] for r in part),6),
              parent_cpu_s=round(sum(r["parent_cpu_s"] for r in part),6),
              child_voluntary_ctx=sum(r["child_voluntary_ctx"] for r in part),
              child_involuntary_ctx=sum(r["child_involuntary_ctx"] for r in part),
              switches=sum(r["sched_switches"] for r in part))
        for arm,item in scores.items():
            for base in ("native1","kissat1","os_share1","race2"):
                v=scores[base]["PAR2_s"]
                item["pct_less_PAR2_vs_"+base]=round(100*(1-item["PAR2_s"]/v),4)
                item["speedup_vs_"+base]=round(v/item["PAR2_s"],5)
            item["CPU_multiple_vs_native1"]=round(item["child_cpu_s"]/
                max(scores["native1"]["child_cpu_s"],1e-6),4)
        return scores
    report=dict(protocol=PROTO,sources=16,trials=EXPECTED,
        not_blind_X15_source_reuse=True,no_auto_promotion=True,
        one_logical_cpu_not_physical_proof=True,
        UNSAT_independent_LRAT=False,
        score=score(rows),
        by_original_X15_tier={tier:score([r for r in rows if r["tier"]==tier])
                 for tier in ("development","holdout")},
        per_source=[dict(sha256=c["sha256"],gbd=c["gbd"],
                 original_X15_tier=c["previous_X15_tier"],
                 score=score([r for r in rows if r["original_sha256"]==c["sha256"]]))
                 for c in m["cases"]],rows=rows)
    save(ROOT/"report.json",report)
    print("X16_FINAL",json.dumps({k:v for k,v in report.items()
        if k not in ("per_source","rows")},sort_keys=True),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":
        verify();print("X16_VERIFY_PASS",flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()


if __name__=="__main__":main()
