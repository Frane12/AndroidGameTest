#!/usr/bin/env python3
"""R30: original-CNF profiling, correct sub-0.5s timing and nested counters.

Only profile equally instrumented native variants; this is not a direct
speedup measurement against uninstrumented R29. UNSAT without independently
checked original-CNF PHP certification gets no verified PAR2 credit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

import drnas_native_r29_diagnostics as R

P, B = R.P, R.B
ARMS = P.ARMS
ROOT = Path("drnas_native_r30")
PROFILE_KEYS = ("bcp_s","xor_s","analyze_s","select_s","update_s",
                "clock_probe_s","clock_samples","measured_s",
                "profile_overhead_lower_bound_s")

def emit(tag, data):
    print(tag+" "+json.dumps(data,sort_keys=True,separators=(",",":")),flush=True)

def watch_process(proc, started, cap):
    """Collect periodic /proc snapshots without delaying finished processes.

    communicate() can be retried after TimeoutExpired, while draining the
    pipes so that a solver does not deadlock when it writes output.
    """
    samples=[]
    for moment in R.SAMPLE_AT:
        if moment>=cap-.01:break
        delay=max(.0001,moment-(time.monotonic()-started))
        try:
            out,err=proc.communicate(timeout=delay)
            return out,err,proc.returncode,samples
        except subprocess.TimeoutExpired:
            if proc.poll() is None:
                samples.append(R.snapshot(proc.pid,time.monotonic()-started))
    delay=max(.0001,cap-(time.monotonic()-started)-.005)
    try:
        out,err=proc.communicate(timeout=delay)
        return out,err,proc.returncode,samples
    except subprocess.TimeoutExpired:
        proc.kill()
        out,err=proc.communicate()
        return out,err,124,samples

def parse_floats(line, label):
    result={}
    for token in line[len(label):].split():
        if "=" not in token:continue
        key,value=token.split("=",1)
        try:result[key]=float(value)
        except ValueError:pass
    return result

def run(arm,source,cap):
    started=time.monotonic()
    original=Path(source["path"])
    if hashlib.sha256(original.read_bytes()).hexdigest()!=source["sha256"]:
        raise RuntimeError("original SAT2024 CNF checksum mismatch")
    command=B.command(arm,original,17,max(.1,cap-.08))
    command[0]="mre_atlas23/bin/"+(
        "drnas_r30_ltm9_profile" if arm=="LTM9_FAST"
        else "drnas_r30_ltm8_profile")
    env=dict(os.environ,DRNAS_LTM8_MEMORY="",OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
    def memory_limit():
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,env=env,preexec_fn=memory_limit) as process:
        stdout,stderr,rc,samples=watch_process(process,started,cap)
    solver_wall=time.monotonic()-started
    counters,profile={},{}
    for line in stdout.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            values=parse_floats(line,"ATLAS13_TRIAL ")
            for key in ("decisions","conflicts","propagations","watch_visits",
                        "learned_clauses","restarts"):
                if key in values:counters[key]=int(values[key])
        elif line.startswith("DRNAS_PROFILE "):
            profile=parse_floats(line,"DRNAS_PROFILE ")
    certified=False
    if rc==10:
        status=("SAT_VERIFIED" if B.sat_witness_valid(
            original,B.nvars(original),stdout) else "INVALID_SAT")
    elif rc==20:
        if arm=="LTM9_FAST":
            try:
                witness=B.certificate_from_stdout(stdout)
                if witness is not None:
                    certified=bool(B.verify_php_certificate(
                        B.parse_dimacs(original),witness))
            except B.CertificateError as exc:
                raise RuntimeError("invalid original CNF PHP certificate") from exc
        status="UNSAT_MATH_CERTIFIED" if certified else "UNSAT_UNVERIFIED"
    elif rc in (0,124):
        status="UNKNOWN"
    else:
        status="ERROR"
    if status in ("INVALID_SAT","ERROR"):
        raise RuntimeError("R30 invalid result arm={} case={} rc={} {}".format(
            arm,source["id"],rc,stderr[-350:]))
    e2e=time.monotonic()-started
    if e2e>cap:
        status="UNKNOWN"
        certified=False
    result=dict(
        id=source["id"],arm=arm,group=source["group"],cap_s=cap,
        status=status,e2e_s=round(e2e,6),solver_wall_s=round(solver_wall,6),
        verified=status in ("SAT_VERIFIED","UNSAT_MATH_CERTIFIED"),
        php_math_certified=certified,split=source["split"],
        seed=17,sha256=source["sha256"],source_file=source["source_file"],
        nvars=source["nvars"],counters=counters,profile=profile,
        process_samples=samples,
        timeout_internal_counters_available=bool(counters) and status=="UNKNOWN",
    )
    return B.with_metrics(result,cap)

def selection(sources,limit):
    if not (2<=limit<=100 and limit%2==0):
        raise ValueError("--limit must be even and between 2 and 100")
    if limit==100:return sources
    selected=[]
    part=limit//2
    # Deterministic spread in 3s and 5s strata, no outcome-based selection.
    for group in (sources[:50],sources[50:]):
        for j in range(part):
            selected.append(group[min(49,((2*j+1)*50)//(2*part))])
    assert len({s["sha256"] for s in selected})==limit
    return selected

def selftest():
    test=[dict(id=1,arm=arm,verified=False,status="UNKNOWN",
        PAR2_verified_s=6,PAR2_reported_s=6,e2e_s=3,
        counters={"decisions":7,"conflicts":3}) for arm in ARMS]
    totals=P.compare(test)["totals"]
    for arm in ARMS:
        assert totals[arm]["decisions_sum"]==7
        assert totals[arm]["conflicts_sum"]==3
    start=time.monotonic()
    with subprocess.Popen([sys.executable,"-c","print('R30_FAST_OK')"],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True) as process:
        stdout,stderr,rc,samples=watch_process(process,start,1.)
    assert rc==0 and "R30_FAST_OK" in stdout,(rc,stderr)
    assert time.monotonic()-start<.48,"fast processes were forced to 0.5s"
    assert not samples
    emit("R30_SELFTEST_PASS",dict(nested_counters=True,fast_exit_timing=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--limit",type=int,default=12)
    args=parser.parse_args()
    if args.selftest:selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=False)
    B.ROOT=ROOT/"source_archive"
    sources=selection(P.prepare(B.collect()),args.limit)
    (ROOT/"selection.json").write_text(json.dumps(dict(
        count=len(sources),source_archive=B.ARCHIVE,
        original_CNF_SHA256=[s["sha256"] for s in sources],
        outcome_free=True,globally_blind=False,
        one_logical_cpu=True,pure_native=True),indent=2)+"\n")
    rows=[]
    with (ROOT/"trials.jsonl").open("w") as output:
        for i,source in enumerate(sources):
            order=list(ARMS);shift=i%len(ARMS)
            for arm in order[shift:]+order[:shift]:
                row=run(arm,source,source["cap_s"])
                rows.append(row)
                output.write(json.dumps(row,sort_keys=True)+"\n");output.flush()
                emit("R30_TRIAL",dict(
                    id=row["id"],arm=arm,status=row["status"],
                    PAR2_verified_s=row["PAR2_verified_s"],
                    e2e_s=row["e2e_s"],counters=row["counters"],
                    profile=row["profile"]))
            if (i+1)%4==0:emit("R30_PROGRESS",dict(completed=i+1,total=len(sources)))
    B.check_contradictions(rows)
    report=P.compare(rows)
    report["profiles"]={}
    for arm in ARMS:
        arm_rows=[r for r in rows if r["arm"]==arm]
        report["profiles"][arm]=dict(
            trials_with_profile=sum(bool(r["profile"]) for r in arm_rows),
            timeout_counter_rows=sum(r["timeout_internal_counters_available"] for r in arm_rows),
            totals_s={k:round(sum(r["profile"].get(k,0) for r in arm_rows),6)
                      for k in PROFILE_KEYS})
    report.update(original_CNF=True,source_count=len(sources),trials=len(rows),
                  single_cpu=True,no_external_fallback=True,globally_blind=False,
                  accurate_early_exit_timing=True,nested_counter_fix=True,
                  limitation=("Profiler timing probes have overhead; only "
                  "compare equally instrumented arms. External kills can "
                  "lose internal counters. No unverified UNSAT credit."))
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("R30_FINAL",report)

if __name__=="__main__":main()
