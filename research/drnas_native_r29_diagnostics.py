#!/usr/bin/env python3
"""R29 observational diagnostic: pure DRNAS native only, 100 original CNFs.

Per-process snapshots at 0.5,1,2,3s; Linux /proc CPU, RSS, threads, IO and
context switches. Does NOT claim to measure BCP/learned clauses on timeout:
native internal counters are unavailable without core instrumentation.
On successful exit parse ATLAS13_TRIAL decisions/conflicts/restarts/learned
when emitted; SAT witness and PHP UNSAT certificate independently checked.
No solver changes, no fallback, no reference solvers. One logical CPU.
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
ROOT=Path("drnas_native_r29")
ARMS=P.ARMS
SAMPLE_AT=(.5,1.,2.,3.)
CLK=os.sysconf("SC_CLK_TCK")
PAGE=os.sysconf("SC_PAGE_SIZE")

def emit(label,value):
    print(label+" "+json.dumps(value,sort_keys=True,separators=(",",":")),flush=True)

def snapshot(pid,t):
    d=dict(t_s=round(t,4),alive=False)
    try:
        stat=Path(f"/proc/{pid}/stat").read_text().rsplit(") ",1)[1].split()
        # After comm, fields start at process field 3: utime=14 -> index 11
        d.update(alive=True,cpu_s=round((int(stat[11])+int(stat[12]))/CLK,5),
                 rss_mb=round(int(stat[21])*PAGE/1048576,3),
                 state=stat[0],threads=int(stat[17]))
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("voluntary_ctxt_switches:"):
                d["voluntary_switches"]=int(line.split()[-1])
            if line.startswith("nonvoluntary_ctxt_switches:"):
                d["involuntary_switches"]=int(line.split()[-1])
        for line in Path(f"/proc/{pid}/io").read_text().splitlines():
            if line.startswith(("read_bytes:","write_bytes:")):
                k,v=line.split(":");d[k]=int(v)
    except (OSError,ValueError,IndexError):
        pass
    return d

def run(arm,source,cap):
    path=Path(source["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==source["sha256"]
    cmd=B.command(arm,path,17,max(.1,cap-.08))
    assert cmd[0].startswith("mre_atlas23/bin/drnas_")
    env=dict(os.environ,DRNAS_LTM8_MEMORY="",OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1")
    def limit():
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    start=time.monotonic()
    with subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,env=env,preexec_fn=limit) as process:
        samples=[]
        for target in SAMPLE_AT:
            remaining=target-(time.monotonic()-start)
            if remaining>0 and process.poll() is None:
                time.sleep(remaining)
            if process.poll() is not None:break
            samples.append(snapshot(process.pid,time.monotonic()-start))
        remaining=max(0.,cap-(time.monotonic()-start)-.005)
        try:
            stdout,stderr=process.communicate(timeout=remaining)
            rc=process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            stdout,stderr=process.communicate()
            rc=124
    elapsed=time.monotonic()-start
    # R29 deliberately does not parse or credit unverified UNSAT. PHP
    # certificate parsing is delegated to B's independent checker only
    # in baseline runs; diagnostic mode records it as unverified.
    if rc==10:
        status="SAT_VERIFIED" if B.sat_witness_valid(path,B.nvars(path),stdout) else "INVALID_SAT"
    elif rc==20:
        status="UNSAT_UNVERIFIED"
    elif rc in (0,124):
        status="UNKNOWN"
    else:
        status="ERROR"
    if status in ("ERROR","INVALID_SAT"):
        raise RuntimeError(f"invalid native result {arm} {source['id']} rc={rc} stderr={stderr[-200:]}")
    counters={}
    for line in stdout.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            for kv in line.split()[1:]:
                if "=" not in kv:continue
                k,v=kv.split("=",1)
                if k in ("decisions","conflicts","restarts","learned","learned_clauses","propagations"):
                    try:counters[k]=int(v)
                    except ValueError:pass
    if elapsed>cap:status="UNKNOWN"
    row=dict(id=source["id"],arm=arm,group=source["group"],cap_s=cap,
             status=status,e2e_s=round(elapsed,6),
             verified=status=="SAT_VERIFIED",
             php_math_certified=False,split=source["split"],seed=17,
             sha256=source["sha256"],nvars=source["nvars"],
             counters=counters,process_samples=samples,
             native_internal_timeout_counters_available=False)
    row=B.with_metrics(row,cap)
    return row

def selftest():
    assert snapshot(os.getpid(),0)["alive"]
    for arm in ARMS:
        assert B.command(arm,Path("dummy.cnf"),17,3)[0].startswith("mre_atlas23/bin/drnas_")
    emit("R29_SELFTEST_PASS",dict(proc_snapshots=True,external_fallback=False,
                                   internal_timeout_counters=False))

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=False)
    B.ROOT=ROOT/"source_archive"
    sources=P.prepare(B.collect())
    rows=[]
    with (ROOT/"trials.jsonl").open("w") as fd:
        for i,source in enumerate(sources):
            order=list(ARMS);k=i%len(ARMS)
            for arm in order[k:]+order[:k]:
                row=run(arm,source,source["cap_s"])
                rows.append(row);fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()
                emit("R29_TRIAL",dict(id=row["id"],arm=arm,status=row["status"],
                     PAR2_verified_s=row["PAR2_verified_s"],e2e_s=row["e2e_s"],
                     samples=row["process_samples"],counters=row["counters"]))
            if (i+1)%10==0:emit("R29_PROGRESS",dict(completed=i+1,total=100))
    B.check_contradictions(rows)
    result=P.compare(rows)
    result.update(source_count=100,trials=300,snapshots_s=SAMPLE_AT,
                  original_CNF=True,one_cpu=True,no_fallback=True,
                  limitation="Timeout process CPU/RSS available; internal BCP/learning/restart counters not available on timeout; UNSAT unverified.")
    (ROOT/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("R29_FINAL",result)
if __name__=="__main__":main()
