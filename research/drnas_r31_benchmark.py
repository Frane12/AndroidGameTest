#!/usr/bin/env python3
"""R31 controlled BCP comparison on identical SHA-frozen SAT2024 instances.

20 outcome-free stratified instances plus 4 explicitly outcome-informed R29
positive calibration replays (never pool them into a blind claim).
Three isolated native builds: BASE, BLOCKER and BINFAST. Two seeds, serial on
one logical CPU per shard. End-to-end verified SAT; unverified UNSAT is penalized
at 2*cap. No external solver, fallback, profiling or persistent memory.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

import drnas_native_pure100 as P

B=P.B
ARMS=("BASE","BLOCKER","BINFAST")
ROOT=Path("drnas_native_r31")
SHARD=int(os.environ.get("R31_SHARD","0"))
assert SHARD in (0,1)

def emit(tag,record):
    print(tag+" "+json.dumps(record,sort_keys=True,separators=(",",":")),flush=True)

def select_sources(sources):
    assert len(sources)==100
    replay_ids={11,37,62,64} # explicitly from R29 positive calibration
    # Existing R29 original-CNF family/prefix locks, no source duplicates.
    selected=[]
    for group in (sources[:50],sources[50:]):
        eligible=[x for x in group if x["id"] not in replay_ids]
        for i in range(10):
            selected.append(dict(eligible[((2*i+1)*len(eligible))//20],
                                 cohort="outcome_free_stratified"))
    selected.extend(dict(s,cohort="r29_known_solved_replay")
                    for s in sources if s["id"] in replay_ids)
    selected=sorted(selected,key=lambda s:(s["cohort"]=="r29_known_solved_replay",s["nvars"],s["id"]))
    assert len(selected)==24 and len({s["sha256"] for s in selected})==24
    assert sum(s["cohort"]=="r29_known_solved_replay" for s in selected)==4
    return selected

def run(arm,source,seed):
    original=Path(source["path"])
    cap=source["cap_s"]
    cmd=B.command("LTM8_FAST",original,seed,max(.1,cap-.08))
    cmd[0]="mre_atlas23/bin/drnas_r31_"+arm.lower()
    env=dict(os.environ,DRNAS_LTM8_MEMORY="",OMP_NUM_THREADS="1",
             OPENBLAS_NUM_THREADS="1")
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    started=time.monotonic()
    try:
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,timeout=cap,env=env,preexec_fn=limits)
        stdout,stderr,rc=proc.stdout,proc.stderr,proc.returncode
    except subprocess.TimeoutExpired:
        stdout,stderr,rc="","wall_timeout",124
    runtime=time.monotonic()-started
    if rc==10:
        status=("SAT_VERIFIED" if B.sat_witness_valid(
                original,B.nvars(original),stdout) else "INVALID_SAT")
    elif rc==20:status="UNSAT_UNVERIFIED"
    elif rc in (0,124):status="UNKNOWN"
    else:status="ERROR"
    if status in ("ERROR","INVALID_SAT"):
        raise RuntimeError("R31 invalid native result id={} arm={} rc={} error={}".format(
            source["id"],arm,rc,stderr[-300:]))
    e2e=time.monotonic()-started
    if e2e>cap:status="UNKNOWN"
    counters={}
    for line in stdout.splitlines():
        if not line.startswith("ATLAS13_TRIAL "):continue
        for token in line.split()[1:]:
            if "=" not in token:continue
            k,v=token.split("=",1)
            if k in ("conflicts","decisions","propagations",
                     "watch_visits","learned_clauses","restarts"):
                try:counters[k]=int(v)
                except ValueError:pass
    result=dict(
        arm=arm,id=source["id"],cohort=source["cohort"],
        original_cnf_sha256=source["sha256"],
        source_file=source["source_file"],nvars=source["nvars"],
        cap_s=cap,seed=seed,status=status,verified=status=="SAT_VERIFIED",
        e2e_s=round(e2e,6),solver_wall_s=round(runtime,6),
        counters=counters,one_logical_cpu=True,external_fallback=False)
    return B.with_metrics(result,cap)

def summarize(rows):
    totals={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        totals[arm]=dict(
            trials=len(a),SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in a),
            UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in a),
            UNKNOWN=sum(r["status"]=="UNKNOWN" for r in a),
            PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in a),6),
            e2e_s=round(sum(r["e2e_s"] for r in a),6),
            counter_trials=sum(bool(r["counters"]) for r in a),
            decisions_sum=sum(r["counters"].get("decisions",0) for r in a),
            conflicts_sum=sum(r["counters"].get("conflicts",0) for r in a),
            watch_visits_sum=sum(r["counters"].get("watch_visits",0) for r in a),
        )
    pairs=collections.defaultdict(dict)
    for r in rows:
        key=(r["original_cnf_sha256"],r["seed"])
        pairs[key][r["arm"]]=r
    gains={}
    for arm in ("BLOCKER","BINFAST"):
        before=totals["BASE"]["PAR2_verified_s"]
        after=totals[arm]["PAR2_verified_s"]
        wins=losses=ties=0
        for x in pairs.values():
            if "BASE" not in x or arm not in x:continue
            reference=x["BASE"]["PAR2_verified_s"]
            candidate=x[arm]["PAR2_verified_s"]
            if candidate+0.002<reference:wins+=1
            elif reference+0.002<candidate:losses+=1
            else:ties+=1
        gains[arm]=dict(speedup_PAR2_x=round(before/max(1e-9,after),6),
                        paired_wins=wins,paired_losses=losses,paired_ties=ties)
    return dict(totals=totals,relative_to_BASE=gains)

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=False)
    B.ROOT=ROOT/"source_archive"
    sources=select_sources(P.prepare(B.collect()))
    chosen=[s for i,s in enumerate(sources) if i%2==SHARD]
    assert len(chosen)==12
    for s in chosen:
        assert hashlib.sha256(Path(s["path"]).read_bytes()).hexdigest()==s["sha256"]
    frozen=[dict(id=s["id"],sha256=s["sha256"],cohort=s["cohort"],
                 source_file=s["source_file"],cap_s=s["cap_s"],
                 nvars=s["nvars"]) for s in chosen]
    (ROOT/"selection.json").write_text(json.dumps(dict(
        shard=SHARD,all_selected=24,selection=frozen,reference_sha_r30="dac568fbe062f91e93c07266969964c40bbb1ddf",
        outcome_aware_replay=4,globally_blind=False,
        no_external_solver=True,no_persistent_memory=True,one_cpu=True,
        repeats=2,seeds=[17,29]),indent=2)+"\n")
    emit("R31_SELECTION",dict(shard=SHARD,selected=len(chosen),
                             replay=sum(s["cohort"]=="r29_known_solved_replay"
                                        for s in chosen)))
    rows=[]
    with (ROOT/"trials.jsonl").open("w") as output:
        for i,source in enumerate(chosen):
            for rep,seed in enumerate((17,29)):
                order=list(ARMS)
                offset=(i+rep)%len(ARMS)
                for arm in order[offset:]+order[:offset]:
                    result=run(arm,source,seed)
                    rows.append(result)
                    output.write(json.dumps(result,sort_keys=True)+"\n")
                    output.flush()
                    emit("R31_TRIAL",dict(
                        id=result["id"],arm=arm,seed=seed,
                        cohort=result["cohort"],status=result["status"],
                        e2e_s=result["e2e_s"],
                        PAR2_verified_s=result["PAR2_verified_s"],
                        counters=result["counters"]))
            if (i+1)%3==0:emit("R31_PROGRESS",dict(shard=SHARD,
                      completed=i+1,total=len(chosen),partial=summarize(rows)))
    B.check_contradictions(rows)
    report=summarize(rows)
    report["cohorts"]={cohort:summarize([r for r in rows if r["cohort"]==cohort])
             for cohort in ("outcome_free_stratified","r29_known_solved_replay")}
    report.update(shard=SHARD,sources=len(chosen),trials=len(rows),
        original_CNF=True,one_cpu=True,repeats=2,
        no_fallback=True,globally_blind=False,
        independent_UNSAT_proof=False,checksum_locked=True,
        optimized_only_BCP=True,
        qualification=("No LTM8 persistent memory. Each variant uses the same "
        "source and seed. Diagnostic replays were preselected for earlier solves "
        "and are excluded from outcome-free cohort. UNSAT not independently "
        "certified receives PAR2 timeout penalty."))
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("R31_FINAL",report)

if __name__=="__main__":main()
