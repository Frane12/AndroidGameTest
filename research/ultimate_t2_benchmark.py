#!/usr/bin/env python3
"""DRNAS Ultimate T phase 1: paired native-CDCL trail-frontier causal experiment.
Exactly the frozen original R2 20-CNF SHA set, NOT blind or final holdout.
Ten modes x two repeats x 20 original sources = 400 trials, five shards.
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import pathlib
import platform
import random
import re
import signal
import subprocess
import time

import ultimate_r2_benchmark as prior

ROOT = pathlib.Path("ultimate_t2")
FROZEN = pathlib.Path("ultimate_r2/frozen")
MANIFEST = FROZEN/"manifest.json"
MODES = ("r153","t_clean","t_shadow","t_source","t_adaptive","t_derived",
         "t2_derived_rows","t2_derived_units","t2_derived_incremental","t2_derived_shadow")
REPS = 2
SHARDS = 5
PROTO = "DRNAS-ULTIMATE-T2-20261107-CAUSAL-ISOLATION-TEN-ARM-PHASE2"
FALLBACK = pathlib.Path("research/ultimate_t2_fallback.py")
T_NATIVE = ROOT/"t-native"

def need(ok, what):
    if not ok:
        raise RuntimeError("ULTIMATE_T2_AUDIT_FAIL_CLOSED " + str(what))

def put(p, payload):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n")

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def cases():
    c=prior.verify()
    need(len(c)==20 and sha(MANIFEST)=="2e6169009e985555e43e81d9b534f3bb307cef93963329694ef42459bef3c2e2",
         "R2 frozen corpus mismatch")
    return c

def cpu():
    try:
        for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":",1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"

def selftest():
    need(len(MODES)==10 and len(cases())==20,"ten-arm protocol")
    need(T_NATIVE.is_file() and FALLBACK.is_file(),"native binary or fallback missing")
    need((ROOT/"empty.tsv").is_file(),"empty control")
    print("ULTIMATE_T2_SELFTEST_PASS",flush=True)

def run_one(src,mode,cap,expected_sha):
    need(sha(src)==expected_sha,"source SHA")
    tool=(prior.KISSAT if mode=="r153" else FALLBACK)
    argv=[str(prior.R153.resolve()),str(src.resolve()),str(tool.resolve())]
    env=os.environ.copy()
    env.update(ULTIMATE_CAP_S=str(cap),ULTIMATE_SEED="11",ULTIMATE_PARITY="0",
               ULTIMATE_T_MODE=mode.removeprefix("t_"),
               ULTIMATE_R2_DEADLINE_NS=str(time.monotonic_ns()+int(cap*1e9)))
    start=time.perf_counter()
    p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       env=env,start_new_session=True)
    killed=False
    try:
        out,err=p.communicate(timeout=cap)
    except subprocess.TimeoutExpired:
        killed=True
        try:
            os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
        out,err=p.communicate()
    elapsed=time.perf_counter()-start
    if not killed and p.returncode not in (0,10,20):
        raise RuntimeError(f"T native failure {mode} rc={p.returncode} "+
                           err[-900:].decode(errors="replace"))
    if killed or elapsed>=cap:
        status="TIMEOUT"
    elif p.returncode==10:
        status="SAT"
    elif p.returncode==20:
        status="UNSAT"
    elif p.returncode==0 and (b"ULTIMATE_T_TIMEOUT" in out or
                               b"R166X_RESULT mode=" in out or
                               b"R182_STATUS status=TIMEOUT" in out):
        status="TIMEOUT"
    else:
        raise RuntimeError(f"T missing terminal status in {mode}: "+
                           err[-900:].decode(errors="replace"))
    gate_match=re.search(rb"ULTIMATE_T_GATE (\{[^\r\n]+\})",out)
    gate=json.loads(gate_match[1]) if gate_match else {}
    if mode!="r153" and b"R28_ROUTE fallback" in out:
        need(bool(gate),"missing T fallback gate")
    if gate:
        need(gate["source_sha256"]==expected_sha,"T source SHA telemetry drift")
    result_match=re.search(rb"R166X_RESULT ([^\r\n]+)",out)
    native={k.decode():v.decode(errors="replace")
            for k,v in re.findall(rb"(\w+)=([^\s]+)",result_match[1])} if result_match else {}
    started=re.search(rb"R166X_START mode=([^\s]+)",out)
    started_mode=started[1].decode() if started else None
    reports=re.findall(rb"R166X_PROGRESS ([^\r\n]+)",out)
    snapshots=[{k.decode():v.decode(errors="replace")
                for k,v in re.findall(rb"(\w+)=([^\s]+)",record)}
               for record in reports]
    if gate:
        expected=gate["native_expected"]
        if started_mode is not None:
            need(started_mode==expected,"T actual native differs from selected route")
        if native.get("mode") is not None:
            need(native["mode"]==expected,"T native mode telemetry disagrees")
        elif status!="TIMEOUT":
            need(False,"T completed native solve missing result telemetry")
    return status,elapsed,out,gate,native,killed,started_mode,snapshots

def trial(c,rep,mode):
    src=FROZEN/(c["id"]+".cnf")
    status,elapsed,out,gate,native,killed,started,reports=run_one(
        src,mode,c["cap_s"],c["sha256"])
    proof="CAP"
    if status=="SAT":
        prior.helper.gf.sat_check(prior.helper.gf.dimacs(src)[1],prior.model(out))
        proof="SAT_WITNESS_CHECKED_ORIGINAL_SHA"
    elif status=="UNSAT":
        if b"R28_ROUTE certified_xor_contradiction" in out:
            need(prior.prior.replay_gf2_unsat(src,out),"R153 GF2 contradiction replay failed")
            proof="GF2_UNSAT_ORIGINAL_REPLAY"
        else:
            proof="NATIVE_UNSAT_NO_INDEPENDENT_LRAT"
    if c["expected"] in ("SAT","UNSAT") and status!="TIMEOUT":
        need(status==c["expected"],"source known result contradicted")
    max_progress=lambda key:max((int(x.get(key,0)) for x in reports),default=0)
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
        family=c["family"],mode=mode,rep=rep,cap_s=c["cap_s"],status=status,
        elapsed_s=round(min(elapsed,c["cap_s"]),6),
        par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
        proof=proof,cpu=cpu(),watchdog=killed,t_gate=gate,
        native_mode=native.get("mode"),native_started=started,
        native_reasons=int(native.get("reason_clauses_completed",0)),
        native_proposals=int(native.get("direct_proposals",0)),
        shadow_candidates=int(native.get("shadow_candidates",0)),
        progress_samples=len(reports),
        progress_reasons=max_progress("completed_reasons"),
        progress_proposals=max_progress("proposals"),
        progress_shadow=max_progress("shadow_candidates"),
        progress_frontier_updates=max_progress("incremental_row_events"),
        progress_avoided_scans=max_progress("avoided_full_scans"))

def shard(i):
    cs=cases()
    need(0<=i<SHARDS,"shard index")
    pin=json.loads((ROOT/"build-pin.json").read_text())
    for p,d in pin["binaries"].items():
        need(sha(p)==d,"binary hash drift "+p)
    need(pin["manifest_sha"]==sha(MANIFEST),"T manifest pin drift")
    if hasattr(os,"sched_getaffinity"):
        affinity=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(affinity)})
    rows=[]
    for c in cs[i::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                r=trial(c,rep,mode)
                rows.append(r)
                put(ROOT/f"shard-{i}.json",rows)
                print("ULTIMATE_T2_TRIAL",json.dumps({
                    k:r[k] for k in ("id","cohort","mode","rep","status","elapsed_s","par2_s",
                       "native_started","native_reasons","progress_reasons","progress_proposals","t_gate")
                },sort_keys=True),flush=True)
    need(len(rows)==len(cs[i::SHARDS])*REPS*len(MODES),"truncated shard")
    print("ULTIMATE_T2_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cs=cases()
    source={c["sha256"]:c for c in cs}
    rows=[]
    for i in range(SHARDS):
        part=json.loads((ROOT/f"shard-{i}.json").read_text())
        need(len(part)==len(cs[i::SHARDS])*REPS*len(MODES),"incomplete shard")
        rows+=part
    need(len(rows)==len(cs)*REPS*len(MODES)==400,"trial count incorrect")
    pairs=collections.defaultdict(dict)
    for r in rows:
        c=source.get(r["sha256"])
        need(c and c["id"]==r["id"] and c["cohort"]==r["cohort"],"original source mismatch")
        need(r["mode"] in MODES and r["mode"] not in pairs[r["sha256"],r["rep"]],
             "duplicate mode in source/rep pair")
        pairs[r["sha256"],r["rep"]][r["mode"]]=r
        need(abs(r["par2_s"]-(r["cap_s"]*2 if r["status"]=="TIMEOUT" else r["elapsed_s"]))<1e-5,
             "PAR2 formula mismatch")
        if r["status"]=="SAT":
            need(r["proof"]=="SAT_WITNESS_CHECKED_ORIGINAL_SHA","unchecked SAT witness")
    for arms in pairs.values():
        need(set(arms)==set(MODES),"missing pair arm")
        need(len({z["cpu"] for z in arms.values()})==1,"CPU model disagreement")
        need(len({z["status"] for z in arms.values() if z["status"]!="TIMEOUT"})<=1,
             "contradictory solved answers")
    results={}
    for cohort in ("all","development","new_to_r1"):
        grp=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
        results[cohort]={}
        for mode in MODES:
            subset=[r for r in grp if r["mode"]==mode]
            results[cohort][mode]=dict(n=len(subset),
                solved=sum(x["status"]!="TIMEOUT" for x in subset),
                sat=sum(x["status"]=="SAT" for x in subset),
                unsat=sum(x["status"]=="UNSAT" for x in subset),
                par2_s=round(sum(x["par2_s"] for x in subset),6),
                selected=sum(bool(x["t_gate"].get("eligible")) for x in subset),
                started=sum(x["native_started"] in ("t_shadow","t_source","t_adaptive","gauss_cooldown",
                                         "t2_derived_rows","t2_derived_units",
                                         "t2_derived_incremental","t2_derived_shadow")
                            for x in subset),
                terminal_missing=sum(x["t_gate"].get("eligible",False) and x["native_mode"] is None
                                     for x in subset),
                completed_reasons=sum(max(x["native_reasons"],x["progress_reasons"]) for x in subset),
                candidate_proposals=sum(max(x["native_proposals"],x["progress_proposals"]) for x in subset),
                shadow_candidates=sum(max(x["shadow_candidates"],x["progress_shadow"]) for x in subset),
                frontier_updates=sum(x["progress_frontier_updates"] for x in subset))
    comparisons={}
    for ref,cand in (("t_clean","t_shadow"),("t_clean","t_source"),
                     ("t_clean","t_adaptive"),("t_clean","t_derived"),
                     ("t_shadow","t_source"),("t_source","t_adaptive"),
                     ("r153","t_clean"),
                     ("t_clean","t2_derived_units"),
                     ("t_clean","t2_derived_rows"),
                     ("t_clean","t2_derived_incremental"),
                     ("t_clean","t2_derived_shadow"),
                     ("t2_derived_rows","t2_derived_incremental"),
                     ("t2_derived_units","t2_derived_incremental"),
                     ("t2_derived_shadow","t2_derived_incremental"),
                     ("t_derived","t2_derived_incremental")):
        deltas=[a[ref]["par2_s"]-a[cand]["par2_s"] for a in pairs.values()]
        comparisons[f"{cand}_vs_{ref}"]=dict(wins=sum(x>0.005 for x in deltas),
            losses=sum(x<-.005 for x in deltas),ties=sum(abs(x)<=.005 for x in deltas),
            par2_gain_s=round(sum(deltas),6))
    report=dict(status="ULTIMATE_T2_PHASE2_AUDIT_PASS_NONBLIND",protocol=PROTO,
        original_manifest_sha=sha(MANIFEST),original_r2_run=42346485260,
        source_count=20,attempts=400,original_cnfs_unchanged=True,
        source_XOR_independently_replayed=True, t1_run_id=42351079758,models_checked_original=True,
        independent_native_LRAT=False,blind_holdout=False,
        runtime_shadow_real=True,results=results,comparisons=comparisons)
    put(ROOT/"report.json",report);put(ROOT/"all-trials.json",rows)
    with (ROOT/"all-trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for v in rows:
            z=dict(v);z["t_gate"]=json.dumps(z["t_gate"],sort_keys=True)
            w.writerow(z)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# Ultimate T2 — controlled XOR row / unit / incremental ablation\n\n")
        f.write("20 previously used original CNFs; ten arms, two reps = 400 attempts. Not blind. Native UNSAT lacks LRAT. Causal factorial isolation.\n\n")
        f.write("| Cohort | Mode | Solved | PAR2 s | Selected | Started | Completed reasons | Shadow opportunities |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|---:|\n")
        for cohort,arms in results.items():
            for mode,z in arms.items():
                f.write(f"| {cohort} | {mode} | {z['solved']}/{z['n']} | {z['par2_s']} | {z['selected']} | {z['started']} | {z['completed_reasons']} | {z['shadow_candidates']} |\n")
        f.write("\n"+json.dumps(comparisons,sort_keys=True,indent=2)+"\n")
    print("ULTIMATE_T2_FINAL",json.dumps(dict(status=report["status"],results=results,
        comparisons=comparisons),sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    actions={"selftest":selftest,"verify":lambda:print("ULTIMATE_T2_VERIFY_PASS",len(cases()),flush=True),
             "shard":lambda:shard(args.shard),"audit":audit}
    actions[args.action]()
