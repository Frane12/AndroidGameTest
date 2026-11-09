#!/usr/bin/env python3
"""DRNAS MRE X8: earliest content-identified watched/learnt-clause event.

Native CMS 5.11.15 source instrumentation, no solver-policy intervention.
E2E SAT E2E PAR2 is strictly separate from 500-conflict native causal traces.
X7 native binary is NOT timing-matched against newly built X8 instrumented one.
Four known development CNF sources; no global blind or LRAT claim.
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

PROTO="DRNAS-MRE-X8-CANONICAL-WATCH-LEARN-4SHA-4ARMS-2SEED-12S-v1"
MODES=("original","spread_shifted","front100","spread100")
BUDGETS=(10,25,100,250,1000,5000)
TRACE_CONFLICT_CAP=500
MAX_TRACE_EVENTS=80000
EVENT_RE=re.compile(
    r"^DRNAS_X8_EVENT seq=(\d+) kind=(\w+) conf=(\d+) level=(\d+) lit=(-?\d+) hash=(\d+) a=(\d+) b=(\d+)$",re.M)
STATUS_RE=re.compile(
    r"^R195_RESULT status=(SAT|UNSAT|BUDGET|UNKNOWN) conflicts=(\d+) decisions=(\d+) propagations=(\d+)",re.M)

def install():
    x4.PROTO=PROTO
    x4.OUT=pathlib.Path("mre_x8")
    x4.MODES=MODES
    x4.REPS=2
    x4.BUDGETS=BUDGETS
    x4.REAL_TRIALS=4*x4.REPS*len(MODES)
    x4.BOUNDED_TRIALS=x4.REAL_TRIALS*len(BUDGETS)
    x4.transform=x6.transform

def trace_one(case,mode,binary,enabled):
    seed=base.seed(case,0)
    env=os.environ.copy()
    env["DRNAS_MAX_CONFLICTS"]=str(TRACE_CONFLICT_CAP)
    env.pop("DRNAS_X7_TRACE",None)
    env.pop("DRNAS_X8_TRACE",None)
    if enabled:env["DRNAS_X8_TRACE"]="1"
    start=time.perf_counter()
    p=subprocess.run([str(pathlib.Path(binary).resolve()),
                      str(x4.path(case,mode).resolve()),"x_native",str(seed)],
                     env=env,capture_output=True,text=True,errors="replace",
                     timeout=30,check=False)
    wall=time.perf_counter()-start
    x4.need(p.returncode==0,
            f"X8 native crash {mode} {p.returncode}: {p.stderr[-350:]}")
    m=STATUS_RE.search(p.stdout)
    x4.need(m is not None,"X8 status/metadata missing")
    status=m.group(1)
    stats={"conflicts":int(m.group(2)),"decisions":int(m.group(3)),
           "propagations":int(m.group(4))}
    events=[]
    if enabled:
        for mm in EVENT_RE.finditer(p.stderr):
            events.append(dict(zip(
                ("seq","kind","conf","level","lit","hash","a","b"),
                (int(mm.group(1)),mm.group(2),int(mm.group(3)),
                 int(mm.group(4)),int(mm.group(5)),int(mm.group(6)),
                 int(mm.group(7)),int(mm.group(8))))))
        x4.need(len(events)>0,"no X8 semantic trace events")
        x4.need(len(events)<=MAX_TRACE_EVENTS,"X8 over budget trace")
        x4.need(all(z["seq"]==i for i,z in enumerate(events)),
                "X8 missing or unordered trace events")
        x4.need(any(z["kind"]=="WATCH_BIN" for z in events),
                "no binary watched clause trace")
        x4.need(any(z["kind"]=="DECIDE" for z in events),
                "no decision trace")
    return dict(status=status,stats=stats,wall_s=round(wall,6),
                events=events,event_count=len(events),
                kinds=dict(collections.Counter(z["kind"] for z in events)))

def first_diff(a,b):
    n=min(len(a),len(b))
    attrs=("kind","conf","level","lit","hash","a","b")
    i=next((j for j in range(n) if any(a[j][k]!=b[j][k] for k in attrs)),None)
    if i is None and len(a)!=len(b):i=n
    return {"ordinal":i,
            "reference":a[i] if i is not None and i<len(a) else None,
            "candidate":b[i] if i is not None and i<len(b) else None,
            "compared_events":n,
            "identical_within_recorded_window":i is None,
            "trace_capped":len(a)==MAX_TRACE_EVENTS or len(b)==MAX_TRACE_EVENTS}

def reduce_group(events,kinds):
    return [z for z in events if z["kind"] in kinds]

def analyze(a,b):
    groups={
      "all_events":("WATCH_BIN","WATCH_LONG","DECIDE","IMPLY","ROOT","LEARN"),
      "watch_clause_identity":("WATCH_BIN","WATCH_LONG"),
      "implication_with_semantic_reason":("IMPLY",),
      "decision":("DECIDE",),
      "learnt_content_LBD":("LEARN",),
      "trail":("ROOT","DECIDE","IMPLY")
    }
    return {group:first_diff(reduce_group(a,kinds),reduce_group(b,kinds))
            for group,kinds in groups.items()}

def trace_shard(shard,binary):
    c=x4.sources()[shard]
    out={}
    for mode in MODES:
        off=trace_one(c,mode,binary,False)
        on=trace_one(c,mode,binary,True)
        x4.need(off["status"]==on["status"] and off["stats"]==on["stats"],
                f"X8 instrument on/off semantic parity failed {mode}")
        out[mode]={"status":off["status"],"stats":off["stats"],
                   "plain_wall_s":off["wall_s"],"trace_wall_s":on["wall_s"],
                   "events":on["events"],"event_count":on["event_count"],
                   "kinds":on["kinds"]}
    first={mode:analyze(out["original"]["events"],out[mode]["events"])
           for mode in MODES if mode!="original"}
    result={"protocol":PROTO,"source_sha256":c["sha256"],
            "gbd":c["gbd"],"seed":base.seed(c,0),
            "status":c["reference_status"],
            "actual_native_CMS_trace":True,
            "same_native_binary_on_off":True,
            "max_events":MAX_TRACE_EVENTS,
            "trace_conflict_cap":TRACE_CONFLICT_CAP,
            "trace_is_bounded_not_PAR2":True,
            "semantic_hash_FNV64_not_cryptographic_proof":True,
            "watch_reason_content_signed_by_internal_literal_encoding":True,
            "first_diff":first,"modes":out}
    x4.save(x4.OUT/("trace-%d.json"%shard),result)
    compact={"gbd":c["gbd"],"first":first,
             "counts":{m:{"events":z["event_count"],"kinds":z["kinds"]}
                       for m,z in out.items()}}
    print("MRE_X8_TRACE",json.dumps(compact,sort_keys=True),flush=True)
    print("MRE_X8_TRACE_SHARD_PASS",shard,len(MODES),flush=True)

def audit():
    x4.audit()
    score=json.loads((x4.OUT/"report.json").read_text())
    trace=[]
    for i in range(4):
        f=x4.OUT/("trace-%d.json"%i)
        x4.need(f.is_file(),f"missing real native trace {i}")
        a=json.loads(f.read_text())
        x4.need(a["protocol"]==PROTO and a["same_native_binary_on_off"],
                "X8 native parity missing")
        trace.append({
            "gbd":a["gbd"],"sha256":a["source_sha256"],
            "captured_events":{m:a["modes"][m]["event_count"] for m in MODES},
            "first_diff":a["first_diff"]})
    result={
        "protocol":PROTO,"source_count":4,"real_E2E_trials":score["real_trials"],
        "bounded_diagnostics_not_PAR2":score["bounded_diagnostics"],
        "trace_native_first_causal_events":trace,
        "full_original_SAT_witness_checked":True,
        "UNSAT_reference_only_no_independent_LRAT":True,
        "same_binary_trace_on_off_CDCL_parity":True,
        "known_development_not_blind":True,
        "no_auto_promotion":True,
        "X8_new_build_vs_X7_same_binary":False,
        "PAR2":score["score"],"per_source":score["per_source"]}
    x4.save(x4.OUT/"x8-final.json",result)
    print("MRE_X8_FINAL",json.dumps(result,sort_keys=True),flush=True)

def main():
    install()
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","trace","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="mre_x8/bin/native")
    a=p.parse_args()
    if a.action=="selftest":
        x4.selftest()
        print("MRE_X8_SELFTEST_PASS",flush=True)
    elif a.action=="freeze":
        x4.freeze()
        print("MRE_X8_FREEZE_PASS",flush=True)
    elif a.action=="verify":
        x4.verify()
        print("MRE_X8_VERIFY_PASS",flush=True)
    elif a.action=="shard":
        x4.shard(a.shard,a.native)
        print("MRE_X8_SHARD_PASS",a.shard,flush=True)
    elif a.action=="trace":
        trace_shard(a.shard,a.native)
    else:audit()

if __name__=="__main__":
    main()
