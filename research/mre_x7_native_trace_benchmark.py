#!/usr/bin/env python3
"""X7: instrumented CMS 5.11.15 source-exact causal comparison.

This is explicitly a new CMS build; X6 has a different library binary.
No claim of X6-exact timing parity is made. The uninstrumented and traced
paths use the same freshly built X7 binary; watches, decisions, implications,
and learned LBDs are logged from the native CMS engine itself.
"""
import argparse
import collections
import json
import os
import pathlib
import re
import subprocess
import time

import mre_x4_early_divergence as x4
import mre_x6_shift_dose_causal as x6
import mre_x_benchmark as base

PROTO="DRNAS-MRE-X7-CMS51115-NATIVE-TRACE-6ARM-4SHA-4SEED-v1"
MODES=("original","spread100","spread_shifted","shift1","front100","spread_reverse_copies")
BUDGETS=(10,25,100,250,1000,5000)
TRACE_CAP=100
EVENT_RE=re.compile(r"DRNAS_X7_EVENT seq=(\d+) kind=(\w+) conf=(\d+) level=(\d+) lit=(-?\d+) a=(\d+) b=(\d+)")
STATUS_RE=re.compile(r"^R195_RESULT status=(SAT|UNSAT|BUDGET|UNKNOWN) conflicts=(\d+) decisions=(\d+) propagations=(\d+)",re.M)

def install():
    x4.PROTO=PROTO
    x4.OUT=pathlib.Path("mre_x7")
    x4.MODES=MODES
    x4.BUDGETS=BUDGETS
    x4.REAL_TRIALS=len(x4.CASES)*x4.REPS*len(MODES)
    x4.BOUNDED_TRIALS=x4.REAL_TRIALS*len(BUDGETS)
    x4.transform=x6.transform

def native_trace(case,mode,binary,enabled):
    seed=base.seed(case,0)
    env=os.environ.copy()
    env["DRNAS_MAX_CONFLICTS"]=str(TRACE_CAP)
    env.pop("DRNAS_X7_TRACE",None)
    if enabled:
        env["DRNAS_X7_TRACE"]="1"
    t0=time.perf_counter()
    proc=subprocess.run([str(pathlib.Path(binary).resolve()),
                         str(x4.path(case,mode).resolve()),"x_native",str(seed)],
                        env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        text=True,errors="replace",timeout=25,check=False)
    wall=time.perf_counter()-t0
    x4.need(proc.returncode==0,"trace native exit "+str(proc.returncode)+" "+proc.stderr[-400:])
    m=STATUS_RE.search(proc.stdout)
    x4.need(m is not None,"no X7 native status")
    status=m.group(1)
    stats={"conflicts":int(m.group(2)),"decisions":int(m.group(3)),"propagations":int(m.group(4))}
    events=[]
    if enabled:
        for line in proc.stderr.splitlines():
            v=EVENT_RE.search(line)
            if v:
                events.append({"seq":int(v.group(1)),"kind":v.group(2),
                               "conf":int(v.group(3)),"lev":int(v.group(4)),
                               "lit":int(v.group(5)),"a":int(v.group(6)),
                               "b":int(v.group(7))})
        x4.need(len(events)>0,"trace enabled, zero events")
        x4.need(any(e["kind"].startswith("WATCH") for e in events),
                "trace no watched-clause events")
        x4.need(len({e["seq"] for e in events})==len(events),
                "duplicate event ordinals")
    return {"gbd":case["gbd"],"sha256":case["sha256"],"mode":mode,
            "enabled":enabled,"status":status,"stats":stats,
            "wall_s":round(wall,6),"events":events,
            "event_counts":dict(collections.Counter(e["kind"] for e in events))}

def compare(ref,candidate):
    a=ref["events"]
    b=candidate["events"]
    n=min(len(a),len(b))
    at=next((i for i in range(n)
             if {k:a[i][k] for k in ("kind","conf","lev","lit","a","b")}
             != {k:b[i][k] for k in ("kind","conf","lev","lit","a","b")}),None)
    if at is None and len(a)!=len(b):
        at=n
    return {"compared_events":n,
            "first_different_seq":at,
            "reference_at_difference":a[at] if at is not None and at<len(a) else None,
            "candidate_at_difference":b[at] if at is not None and at<len(b) else None,
            "different_recorded":at is not None}

def run_trace_shard(idx,binary):
    case=x4.sources()[idx]
    out={}
    for mode in MODES:
        plain=native_trace(case,mode,binary,False)
        traced=native_trace(case,mode,binary,True)
        x4.need(plain["status"]==traced["status"] and plain["stats"]==traced["stats"],
                "instrumentation changed CDCL counters, "+mode)
        out[mode]={"plain_status":plain["status"],
                   "plain_stats":plain["stats"],
                   "traced_status":traced["status"],
                   "traced_stats":traced["stats"],
                   "trace_events":traced["events"],
                   "event_counts":traced["event_counts"],
                   "trace_wall_s":traced["wall_s"],
                   "plain_wall_s":plain["wall_s"]}
    ref={"events":out["original"]["trace_events"]}
    first={mode:compare(ref,{"events":out[mode]["trace_events"]})
           for mode in MODES if mode!="original"}
    report={"protocol":PROTO,"source_sha256":case["sha256"],"gbd":case["gbd"],
            "same_native_binary_on_off":True,
            "trace_conflict_cap":TRACE_CAP,
            "trace_not_PAR2":True,
            "event_fields":{"WATCH_BIN":"lit=propagated, a=other literal, b=clause ID",
                            "WATCH_LONG":"lit=propagated, a=blocked literal, b=allocation offset",
                            "DECIDE":"decision literal and trail index",
                            "IMPLY":"implied literal and reason type",
                            "LEARN_LBD":"lit=asserted, a=LBD, b=learnt size"},
            "first_event_differences":first,
            "modes":out}
    x4.save(x4.OUT / ("trace-%d.json"%idx),report)
    # Compact log. Full sequence is retained in artifact, not dumped into Actions log.
    print("MRE_X7_TRACE_SHARD",json.dumps({
        "gbd":case["gbd"],"trace_conflict_cap":TRACE_CAP,
        "counts":{m:v["event_counts"] for m,v in out.items()},
        "first":first
    },sort_keys=True),flush=True)
    print("MRE_X7_TRACE_SHARD_PASS",idx,len(out),flush=True)

def audit():
    x4.audit()
    rep=json.loads((x4.OUT/"report.json").read_text())
    rows=[]
    for i in range(4):
        p=x4.OUT/("trace-%d.json"%i)
        x4.need(p.is_file(),"missing native trace shard")
        t=json.loads(p.read_text())
        x4.need(t["protocol"]==PROTO and t["same_native_binary_on_off"],
                "native-on-off parity missing")
        rows.append({"gbd":t["gbd"],"sha256":t["source_sha256"],
                     "counts":{m:d["event_counts"] for m,d in t["modes"].items()},
                     "first":t["first_event_differences"]})
    final={"protocol":PROTO,"not_globally_blind":True,
           "CMS_build_not_identical_to_X6":True,
           "UNSAT_independent_LRAT":False,"no_auto_promotion":True,
           "real_E2E_trials":rep["real_trials"],
           "bounded_not_PAR2":rep["bounded_diagnostics"],
           "native_trace_source_count":len(rows),
           "trace_on_off_CDCL_counter_parity":True,
           "scores":rep["score"],
           "per_source":rep["per_source"],
           "native_event_first_differences":rows}
    x4.save(x4.OUT/"x7-final.json",final)
    print("MRE_X7_FINAL",json.dumps(final,sort_keys=True),flush=True)

def main():
    install()
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","trace","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="mre_x7/bin/native")
    a=p.parse_args()
    if a.action=="selftest":
        x4.selftest()
        print("MRE_X7_SELFTEST_PASS",flush=True)
    elif a.action=="freeze":
        x4.freeze()
    elif a.action=="verify":
        x4.verify()
    elif a.action=="shard":
        x4.shard(a.shard,a.native)
    elif a.action=="trace":
        run_trace_shard(a.shard,a.native)
    else:
        audit()

if __name__=="__main__":
    main()
