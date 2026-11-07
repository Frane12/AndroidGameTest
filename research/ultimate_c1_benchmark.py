#!/usr/bin/env python3
"""DRNAS C1: source-pinned XOR -> CDCL reason-delivery causal ablation.

50 original CNFs (20 earlier TD, 30 TA source-disjoint from R1/R2/R193);
6 arms x 2 repetitions = 600 paired trials, 10 shards.
These sources have already been used in TD/TA; NOT globally blind.
Original source bytes are never changed. Native UNSAT is NOT independently LRAT certified.
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
import subprocess

import ultimate_t2_benchmark as td

ROOT=pathlib.Path("ultimate_c1")
MODES=("r153","t_clean","td_lazy_source","c1_lazy_shadow",
       "c1_lazy_cooldown","c1_lazy_fastwake")
REPS=2
SHARDS=10
PROTO="DRNAS-C1-20261107-50-SOURCE-SIX-ARM-CAUSAL-v1"
TD_MANIFEST=pathlib.Path("ultimate_r2/frozen/manifest.json")
TA_MANIFEST=pathlib.Path("ultimate_ta/frozen/manifest.json")
TD_SHA="2e6169009e985555e43e81d9b534f3bb307cef93963329694ef42459bef3c2e2"

def need(ok, message):
    if not ok: raise RuntimeError("DRNAS_C1_AUDIT_FAIL_CLOSED "+str(message))

def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def put(p, obj):
    p=pathlib.Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def cases():
    need(TD_MANIFEST.is_file() and TA_MANIFEST.is_file(),"missing original manifests")
    need(sha(TD_MANIFEST)==TD_SHA,"TD original manifest SHA drift")
    td_manifest=json.loads(TD_MANIFEST.read_text())
    ta_manifest=json.loads(TA_MANIFEST.read_text())
    need(len(td_manifest["cases"])==20 and len(ta_manifest["cases"])==30,
         "unexpected original cohort counts")
    need(ta_manifest["source_disjoint_from_R1_R2_R193"] is True,
         "TA source SHA provenance missing")
    need(ta_manifest["selected_without_solver_outcomes"] is True,
         "TA source was selected using outcomes")
    cs=[]
    for cohort,manifest,folder in (
        ("td_reused",td_manifest,"ultimate_r2/frozen"),
        ("ta_source_disjoint_reused",ta_manifest,"ultimate_ta/frozen")):
        for c in manifest["cases"]:
            z=dict(c)
            z["c1_cohort"]=cohort
            z["src"]=str(pathlib.Path(folder)/(c["id"]+".cnf"))
            need(pathlib.Path(z["src"]).is_file(),"missing original "+z["id"])
            need(sha(z["src"])==z["sha256"],"original SHA drift "+z["id"])
            cs.append(z)
    need(len(cs)==50 and len({c["sha256"] for c in cs})==50,
         "source overlap or duplicate original SHA")
    return cs

def cpu():
    if hasattr(os,"sched_getaffinity"):
        return "cpu-affinity-"+str(sorted(os.sched_getaffinity(0)))
    return platform.processor()

def selftest():
    need(len(MODES)==6 and REPS==2 and SHARDS==10,"frozen six-arm protocol")
    need((pathlib.Path("ultimate_t2")/"t-native").is_file(),
         "native C1 binary missing")
    need((pathlib.Path("ultimate_t2")/"empty.tsv").is_file(),
         "empty certificate file missing")
    need(len(cases())==50,"C1 source count")
    print("C1_SELFTEST_PASS 50-originals six-arms 600-tries",flush=True)

def trial(c,rep,mode):
    src=pathlib.Path(c["src"])
    status,elapsed,out,gate,native,killed,started,reports=td.run_one(
        src,mode,c["cap_s"],c["sha256"])
    proof="TIMEOUT"
    if status=="SAT":
        td.prior.helper.gf.sat_check(td.prior.helper.gf.dimacs(src)[1],
                                     td.prior.model(out))
        proof="SAT_MODEL_CHECKED_ORIGINAL_SHA"
    elif status=="UNSAT":
        if b"R28_ROUTE certified_xor_contradiction" in out:
            need(td.prior.prior.replay_gf2_unsat(src,out),
                 "failed source GF2 UNSAT replay")
            proof="GF2_UNSAT_ORIGINAL_REPLAY"
        else:
            proof="NATIVE_UNSAT_NO_INDEPENDENT_LRAT"
    if c.get("expected") in ("SAT","UNSAT") and status!="TIMEOUT":
        need(status==c["expected"],"known original answer contradiction")
    mx=lambda key:max((int(x.get(key,0)) for x in reports),default=0)
    ni=lambda key:int(native.get(key,"0"))
    if mode=="c1_lazy_shadow" and native.get("mode")=="c1_lazy_shadow":
        need(ni("direct_proposals")==0 and ni("reason_clauses_completed")==0,
             "shadow control mutated CDCL")
    return dict(id=c["id"],sha256=c["sha256"],cohort=c["c1_cohort"],
       family=c.get("family","unknown"),rep=rep,mode=mode,cap_s=c["cap_s"],
       cpu=cpu(),status=status,proof=proof,watchdog=killed,
       elapsed_s=round(min(elapsed,c["cap_s"]),6),
       par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else elapsed,6),
       native_started=started,native_mode=native.get("mode"),t_gate=gate,
       native_reasons=max(ni("reason_clauses_completed"),mx("completed_reasons")),
       native_proposals=max(ni("direct_proposals"),mx("proposals")),
       shadow_candidates=max(ni("shadow_candidates"),mx("shadow_candidates")),
       cheap_watch_rejects=ni("cheap_watch_rejects"),
       cooldown_skips=ni("cooldown_skips"),
       cooldown_wakes=ni("cooldown_wakes"),
       propagations=ni("propagate_calls"),
       propagate_ns=ni("propagate_ns"),
       source_rows=ni("source_rows"),
       reason_requests=ni("direct_reason_requests"),
       reason_lits=ni("direct_reason_lits"))

def pinned():
    p=ROOT/"build-pin.json"
    need(p.is_file(),"missing pinned experiment protocol")
    pin=json.loads(p.read_text())
    need(pin["protocol"]==PROTO and pin["attempts"]==600,"protocol mismatch")
    need(pin["td_manifest_sha"]==sha(TD_MANIFEST),"TD SHA drift")
    need(pin["ta_manifest_sha"]==sha(TA_MANIFEST),"TA SHA drift")
    need(pin["source_commit"]==subprocess.check_output(
        ["git","rev-parse","HEAD"],text=True).strip(),"source commit changed")
    for path,d in pin["files"].items():
        need(sha(path)==d,"binary/source SHA drift: "+path)
    return pin

def shard(index):
    need(0<=index<SHARDS,"invalid shard index")
    cs=cases();pinned()
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for c in cs[index::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                row=trial(c,rep,mode)
                rows.append(row)
                put(ROOT/f"shard-{index}.json",rows)
                print("C1_TRIAL",json.dumps({k:row[k] for k in (
                    "id","cohort","rep","mode","status","elapsed_s","par2_s",
                    "native_reasons","native_proposals","shadow_candidates",
                    "cooldown_skips","cooldown_wakes","t_gate")},sort_keys=True),flush=True)
    need(len(rows)==len(cs[index::SHARDS])*REPS*len(MODES),"shard truncated")
    print("C1_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cs=cases();pin=pinned();allrows=[]
    for i in range(SHARDS):
        path=ROOT/f"shard-{i}.json"
        need(path.is_file(),"missing shard "+str(i))
        part=json.loads(path.read_text())
        need(len(part)==len(cs[i::SHARDS])*REPS*len(MODES),
             "incomplete shard "+str(i))
        allrows.extend(part)
    need(len(allrows)==600,"incomplete 600 paired attempts")
    original={c["sha256"]:c for c in cs}
    pairs=collections.defaultdict(dict)
    for x in allrows:
        c=original.get(x["sha256"])
        need(c and x["id"]==c["id"] and x["cohort"]==c["c1_cohort"],
             "original source identity mismatch")
        need(x["mode"] in MODES,"unregistered experimental arm")
        block=pairs[(x["sha256"],x["rep"])]
        need(x["mode"] not in block,"duplicate paired mode")
        block[x["mode"]]=x
        expected=2*x["cap_s"] if x["status"]=="TIMEOUT" else x["elapsed_s"]
        need(abs(x["par2_s"]-expected)<1e-5,"PAR2 arithmetic wrong")
        if x["status"]=="SAT":
            need(x["proof"]=="SAT_MODEL_CHECKED_ORIGINAL_SHA",
                 "unchecked original model")
        if x["proof"]=="GF2_UNSAT_ORIGINAL_REPLAY":
            need(x["status"]=="UNSAT","invalid GF2 proof status")
    need(len(pairs)==100,"missing 100 original-seed pairs")
    for block in pairs.values():
        need(set(block)==set(MODES),"missing causal arm")
        need(len({z["cpu"] for z in block.values()})==1,
             "different pinned CPUs within same pair")
        need(len({z["status"] for z in block.values()
                  if z["status"]!="TIMEOUT"})<=1,
             "contradictory SAT/UNSAT answer on same original")
    summary={}
    for cohort in ("all","td_reused","ta_source_disjoint_reused"):
        rows=[x for x in allrows if cohort=="all" or x["cohort"]==cohort]
        summary[cohort]={}
        for mode in MODES:
            a=[x for x in rows if x["mode"]==mode]
            summary[cohort][mode]=dict(n=len(a),solved=sum(x["status"]!="TIMEOUT" for x in a),
                sat=sum(x["status"]=="SAT" for x in a),
                unsat=sum(x["status"]=="UNSAT" for x in a),
                par2_s=round(sum(x["par2_s"] for x in a),6),
                selected=sum(bool(x["t_gate"].get("eligible")) for x in a),
                native_started=sum(x["native_started"]==mode for x in a),
                reason_clauses=sum(x["native_reasons"] for x in a),
                proposals=sum(x["native_proposals"] for x in a),
                shadow_candidates=sum(x["shadow_candidates"] for x in a),
                cooldown_skips=sum(x["cooldown_skips"] for x in a),
                cooldown_wakes=sum(x["cooldown_wakes"] for x in a),
                no_native_terminal=sum(x["status"]=="TIMEOUT" and
                                       x["native_started"]==mode and x["native_mode"] is None for x in a))
    comparisons={}
    for ref,cand in (
        ("t_clean","td_lazy_source"),
        ("t_clean","c1_lazy_cooldown"),
        ("t_clean","c1_lazy_fastwake"),
        ("t_clean","c1_lazy_shadow"),
        ("td_lazy_source","c1_lazy_cooldown"),
        ("td_lazy_source","c1_lazy_fastwake"),
        ("c1_lazy_shadow","c1_lazy_cooldown"),
        ("c1_lazy_cooldown","c1_lazy_fastwake"),
        ("r153","c1_lazy_cooldown")):
        comparisons[cand+"_vs_"+ref]={}
        for cohort in ("all","td_reused","ta_source_disjoint_reused"):
            blocks=[b for (digest,rep),b in pairs.items()
                    if cohort=="all" or original[digest]["c1_cohort"]==cohort]
            ds=[b[ref]["par2_s"]-b[cand]["par2_s"] for b in blocks]
            comparisons[cand+"_vs_"+ref][cohort]=dict(
                wins=sum(x>0.005 for x in ds),
                losses=sum(x<-.005 for x in ds),
                ties=sum(abs(x)<=.005 for x in ds),
                par2_gain_s=round(sum(ds),6))
    # Conservative post-hoc decision only. The trial suite is NOT global blind.
    def promote(mode):
        a=summary["td_reused"];b=summary["ta_source_disjoint_reused"]
        return (a[mode]["solved"]>=a["t_clean"]["solved"] and
                b[mode]["solved"]>=b["t_clean"]["solved"] and
                a[mode]["par2_s"]<=a["t_clean"]["par2_s"] and
                b[mode]["par2_s"]<=b["t_clean"]["par2_s"] and
                summary["all"][mode]["reason_clauses"]>0)
    decision={mode:("RESEARCH_CANDIDATE_REQUIRES_NEW_BLIND" if promote(mode)
                    else "DO_NOT_PROMOTE") for mode in ("c1_lazy_cooldown","c1_lazy_fastwake")}
    out=dict(status="C1_50_ORIGINAL_600_PAIRED_AUDIT_PASS_NONBLIND",
        protocol=PROTO,source_commit=pin["source_commit"],
        td_manifest_sha=sha(TD_MANIFEST),ta_manifest_sha=sha(TA_MANIFEST),
        attempts=600,original_sources=50,source_sha_disjoint=True,
        source_replay_from_existing_TD=True,models_checked_original=True,
        independent_native_unsat_LRAT=False,globally_blind=False,
        interpretation="Ablation only; no automatic performance claim on all SAT 2026",
        summary=summary,comparisons=comparisons,decision=decision)
    put(ROOT/"report.json",out)
    put(ROOT/"all-trials.json",allrows)
    with (ROOT/"all-trials.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]))
        w.writeheader()
        for row in allrows:
            z=dict(row);z["t_gate"]=json.dumps(z["t_gate"],sort_keys=True)
            w.writerow(z)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS C1 — certified XOR/CDCL direct reason transfer\n\n")
        f.write("600 paired original CNF trials, 50 SHA-disjoint originals, two repeats. ")
        f.write("20 old TD, 30 previously TA-tested (disjoint only from earlier R1/R2/R193). ")
        f.write("**NOT globally blind; native UNSAT lacks independent LRAT.**\n\n")
        f.write("| Cohort | Arm | Solved | PAR2 s | Native reason completions | Shadow opportunities | Cooldown skips/wakes |\n")
        f.write("|---|---|---:|---:|---:|---:|---:|\n")
        for cohort,arms in summary.items():
            for arm,z in arms.items():
                f.write(f"| {cohort} | {arm} | {z['solved']}/{z['n']} | "
                        f"{z['par2_s']} | {z['reason_clauses']} | "
                        f"{z['shadow_candidates']} | {z['cooldown_skips']}/{z['cooldown_wakes']} |\n")
        f.write("\n## Promotion decision\n\n"+json.dumps(decision,indent=2))
        f.write("\n\n## Paired comparisons\n\n"+json.dumps(comparisons,indent=2)+"\n")
    print("C1_FINAL",json.dumps(dict(status=out["status"],summary=summary,
          comparisons=comparisons,decision=decision),sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    actions={"selftest":selftest,"verify":lambda:print("C1_VERIFY_PASS",len(cases()),flush=True),
             "shard":lambda:shard(a.shard),"audit":audit}
    actions[a.action]()
