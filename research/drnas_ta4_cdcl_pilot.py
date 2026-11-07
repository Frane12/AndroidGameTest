#!/usr/bin/env python3
"""DRNAS TA4: prospective mixed-SAT host selector with bounded early CDCL pilot.

Development basis: TA3's previously analyzed hgen and other source profiles.
Validation: 15 separate original SAT2025 CNFs, SHA-disjoint from R189/R199/TA3.
Eight paired modes x two repeats, 20s full wall-clock cap including feature,
subprocess pilot, CDCL solver, and original SAT witness validation. Generic
CDCL UNSAT is not independently LRAT-certified. R28 is a pinned reference.

The diagnostic pilot is a separately bounded Kissat run with 256 conflicts
and --statistics, not a magical continuation or learned neural model.
If incomplete, restart selected host from scratch and charge the pilot cost.
"""
from __future__ import annotations
import argparse
import collections
import concurrent.futures
import hashlib
import json
import lzma
import pathlib
import random
import re
import statistics
import subprocess
import time
import urllib.request

import drnas_ta3_adaptive_selector as ta3

ROOT=pathlib.Path("ta4")
SOURCE=ROOT/"sources"
PROTO="DRNAS-TA4-SAT2025-15-SOURCE-DISJOINT-EARLY-CDCL-PILOT-v1"
CAP=20.0
PILOT_CAP=0.28
PILOT_CONFLICTS=256
REPS=2
SHARDS=5
MODES=("cms_plain","kissat_plain","cms_r28","kissat_r28",
       "ta3_portfolio","ta4_structural","ta4_pilot","ta4_pilot_shadow")
ta3.previous.certified.CAP=CAP

def need(ok,msg):
    if not ok: raise RuntimeError("TA4_FAIL_CLOSED "+str(msg))

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def get_cases():
    cs=json.loads((ROOT/"candidates.json").read_text())["cases"]
    need(len(cs)==15 and len({c["sha256"] for c in cs})==15,
         "15 unique prospective originals expected")
    need(len({c["family"] for c in cs})==15,"repeat source family")
    prior=[]
    for p in ("r189/frozen/manifest.json","r199/candidates.json",
              "ta3/candidates.json"):
        prior.extend(json.loads(pathlib.Path(p).read_text())["cases"])
    old={c["sha256"] for c in prior}
    need(not old.intersection(c["sha256"] for c in cs),
         "TA4 overlaps R189/R199/TA3 source SHA!")
    need(sum(c["expected"]=="SAT" for c in cs)==10
         and sum(c["expected"]=="UNSAT" for c in cs)==5,
         "SAT/UNSAT balance drift")
    cohorts=("hardware_industrial","graph_puzzles","planning_crafted")
    need(all(sum(c["group"]==g for c in cs)==5 for g in cohorts),
         "not five cases per cohort")
    return cs,cohorts

def fetch():
    cs,_=get_cases();SOURCE.mkdir(parents=True,exist_ok=True)
    def one(c):
        p=SOURCE/(c["id"]+".cnf")
        if p.exists() and sha(p)==c["sha256"]:return
        last=None
        for attempt in range(4):
            try:
                req=urllib.request.Request(c["url"],headers={
                    "User-Agent":"DRNAS-TA4-original-SAT2025-benchmark/1"})
                with urllib.request.urlopen(req,timeout=120) as response:
                    blob=response.read(16_000_001)
                need(len(blob)<16_000_001,"compressed file over limit")
                data=lzma.decompress(blob)
                need(len(data)==c["bytes"],"original byte count drift: "+c["id"])
                need(hashlib.sha256(data).hexdigest()==c["sha256"],
                     "original source SHA drift: "+c["id"])
                need(b"p cnf " in data[:10000],"invalid DIMACS source: "+c["id"])
                p.write_bytes(data)
                return
            except Exception as exc:
                last=exc;time.sleep(2+3*attempt)
        raise RuntimeError("TA4 source restore failed "+c["id"]+" "+str(last))
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(one,cs))
    for c in cs:need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"not SHA pinned")
    save(ROOT/"manifest.json",{"protocol":PROTO,"cases":cs,
         "sha_disjoint_R189_R199_TA3":True})
    print("TA4_HOLDOUT_FROZEN",json.dumps({
        "sources":len(cs),"SAT":10,"UNSAT":5,
        "manifest_sha256":sha(ROOT/"manifest.json")},sort_keys=True),flush=True)

def verify():
    cs,cohorts=get_cases()
    frozen=json.loads((ROOT/"manifest.json").read_text())["cases"]
    need([(c["id"],c["sha256"]) for c in frozen]==
         [(c["id"],c["sha256"]) for c in cs],"prospective manifest drift")
    for file_name,digest in json.loads((ROOT/"pins.json").read_text()).items():
        need(sha(file_name)==digest,"frozen code/binary drift "+file_name)
    for c in cs:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"original CNF SHA drift")
    buckets=[[] for _ in range(SHARDS)]
    ordered=[]
    for g in cohorts:
        ordered.extend(sorted((c for c in cs if c["group"]==g),
                              key=lambda c:c["sha256"]))
    for i,c in enumerate(ordered):buckets[i%SHARDS].append(c)
    need(all(len(x)==3 for x in buckets),"expected 3 cases/shard")
    return cs,buckets,cohorts

def uncertain_gate(f):
    """Fixed development-era TA3 hypothesis: generic small parity-like CNF."""
    return (f["declared_clauses"]<=12000 and
            f["complete_xor3_templates_sample"]==0 and
            f["binary_fraction"]<=0.10 and
            0.30<=f["horn_clause_fraction"]<=0.70 and
            f["long_clause_fraction"]<0.18 and
            f["variable_occurrence_p90_over_median"]<=2.5)

def initial_route(f):
    selected,reason=ta3.decision(f,"ta2_portfolio")
    return selected,reason

def pilot_kissat(source,started):
    """Measure early CDCL conflicts, decisions and propagation on ORIGINAL CNF.

    Kissat stops by conflict limit or subprocess timeout. No SAT/UNSAT label is
    supplied to this diagnostic; result only affects route, never establishes a
    solver answer. Model/proof from pilot is NOT used as a certified result.
    """
    elapsed=time.perf_counter()-started
    budget=min(PILOT_CAP,max(0.0,CAP-elapsed-0.2))
    if budget<.02:
        return {"status":"NOT_RUN","conflicts":0,"decisions":0,
                "propagations":0,"elapsed_s":0.0,"cap_s":budget}
    kissat=str(pathlib.Path("built/bin/kissat_4_0_4").resolve())
    cmd=[kissat,"--conflicts="+str(PILOT_CONFLICTS),
         "--statistics","--no-witness",str(source.resolve())]
    # '--no-witness' may not be supported by Kissat 4.0.4: use '-n'.
    cmd[3]="-n"
    t0=time.perf_counter()
    raw="";exit_code=None;status="TIME_BUDGET"
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                         timeout=budget,check=False)
        raw=p.stdout+"\n"+p.stderr
        exit_code=p.returncode
        m=re.search(r"^s (SATISFIABLE|UNSATISFIABLE|UNKNOWN)\s*$",raw,re.M)
        status=m.group(1) if m else "NO_STATUS"
    except subprocess.TimeoutExpired as ex:
        # Partial lines are not guaranteed to flush; no progress is inferred.
        raw=((ex.stdout or b"").decode("utf-8","replace")
             if isinstance(ex.stdout,bytes) else ex.stdout or "")
        status="TIME_BUDGET"
    counts={}
    for key in ("conflicts","decisions","propagations"):
        matches=re.findall(r"^c "+key+r":\s+(\d+)",raw,re.M)
        counts[key]=int(matches[-1]) if matches else 0
    return {"status":status,**counts,"elapsed_s":round(
        time.perf_counter()-t0,6),"cap_s":budget,
        "exit_code":exit_code}

def choose(mode,features,pilot):
    base,reason=initial_route(features)
    if mode=="ta3_portfolio":
        return base,"frozen_TA3:"+reason
    if mode=="ta4_structural":
        if base=="cms_plain" and uncertain_gate(features):
            return "kissat_plain","developed_hgen_like_source_rule"
        return base,"TA3_source_fallback:"+reason
    if mode in ("ta4_pilot","ta4_pilot_shadow"):
        if mode=="ta4_pilot_shadow":
            return base,"shadow_paid_pilot_but_kept_TA3:"+reason
        if pilot is not None and (pilot["status"] in
            ("SATISFIABLE","UNSATISFIABLE") or
            (pilot["conflicts"]>=PILOT_CONFLICTS and
             pilot["decisions"]>=pilot["conflicts"] and
             pilot["elapsed_s"]<0.22)):
            return "kissat_plain","early_kissat_CDCL_progress"
        return base,"pilot_abstained_kept_TA3:"+reason
    need(False,"unknown adaptive mode "+mode)

def trial(c,mode,rep,shard):
    source=SOURCE/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"SHA drift before solver")
    started=time.perf_counter()
    features=None;pilot=None;profile_s=0.0;route="fixed_reference"
    selected=mode
    if mode in ("ta3_portfolio","ta4_structural",
                "ta4_pilot","ta4_pilot_shadow"):
        features=ta3.fast_features(source)
        profile_s=time.perf_counter()-started
        if (mode in ("ta4_pilot","ta4_pilot_shadow")
            and initial_route(features)[0]=="cms_plain"
            and uncertain_gate(features)):
            pilot=pilot_kissat(source,started)
        selected,route=choose(mode,features,pilot)
    need(selected in ("cms_plain","kissat_plain","cms_r28","kissat_r28"),
         "unsupported selected backend")
    if time.perf_counter()-started>=CAP-0.12:
        status,model,r28_route="TIMEOUT",{},None
    else:
        status,model,r28_route,_raw,_rc=ta3.previous.certified.timed_command(
            ta3.command(selected,source),started)
    proof="CAP_TIMEOUT"
    if status=="SAT":
        # SAT witnesses are checked on ORIGINAL, not modified CNF.
        _n,original_clauses=ta3.previous.certified.gf_src.gf.dimacs(source)
        ta3.previous.certified.gf_src.gf.sat_check(original_clauses,model)
        proof="SAT_WITNESS_ORIGINAL_VERIFIED"
    elif status=="UNSAT":
        proof=("R28_SOURCE_GF2_CONTRADICTION" if r28_route
               and r28_route.startswith("certified_xor_contradiction")
               else "NO_INDEPENDENT_LRAT")
    elapsed=min(CAP,time.perf_counter()-started)
    if elapsed>=CAP:
        status="TIMEOUT"
        proof="CAP_TIMEOUT"
    need(status in ("SAT","UNSAT","TIMEOUT"),"unsupported final solver status")
    need(status=="TIMEOUT" or status==c["expected"],
         "wrong SAT/UNSAT result "+c["id"])
    row={"id":c["id"],"family":c["family"],"group":c["group"],
         "sha256":c["sha256"],"mode":mode,"selected":selected,
         "route":route,"rep":rep,"shard":shard,"status":status,
         "elapsed_s":round(elapsed,6),"par2_s":round(
            2*CAP if status=="TIMEOUT" else elapsed,6),
         "profile_s":round(profile_s,6),"pilot":pilot,"proof":proof,
         "r28_route":r28_route,"source_sha256":c["sha256"]}
    if features:
        row["features"]={k:features[k] for k in (
            "declared_variables","declared_clauses","sampled_clauses",
            "binary_fraction","horn_clause_fraction","long_clause_fraction",
            "complete_xor3_templates_sample",
            "variable_occurrence_p90_over_median")}
    print("TA4_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row

def shard(index):
    _all,buckets,_groups=verify()
    need(0<=index<SHARDS,"invalid shard")
    rows=[]
    for c in buckets[index]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                rows.append(trial(c,mode,rep,index))
                save(ROOT/("shard-%d.json"%index),rows)
    need(len(rows)==3*REPS*len(MODES),"partial pair shard")
    print("TA4_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cs,buckets,cohorts=verify()
    cases={c["sha256"]:c for c in cs}
    records=[];seen=set()
    for i,group in enumerate(buckets):
        path=ROOT/("shard-%d.json"%i)
        need(path.exists(),"missing shard "+str(i))
        rr=json.loads(path.read_text())
        need(len(rr)==3*REPS*len(MODES),"invalid shard trial count "+str(i))
        need({r["sha256"] for r in rr}=={c["sha256"] for c in group},
             "source shard overlap/drift")
        for r in rr:
            need(r["sha256"] in cases and r["id"]==cases[r["sha256"]]["id"],
                 "source ID drift")
            k=(r["sha256"],r["rep"],r["mode"])
            need(k not in seen,"duplicate paired trial")
            seen.add(k)
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),
                 "invalid status")
            need(r["status"]=="TIMEOUT" or
                 r["status"]==cases[r["sha256"]]["expected"],
                 "wrong solved answer")
            need(r["status"]!="SAT" or
                 r["proof"]=="SAT_WITNESS_ORIGINAL_VERIFIED",
                 "unverified SAT witness")
            need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT"
                 else r["elapsed_s"]))<2e-5,"PAR2 incorrect")
            records.append(r)
    need(len(records)==15*REPS*len(MODES)==240,"not 240 trial records")
    for c in cs:
        for rep in range(REPS):
            rr=[r for r in records if
                r["sha256"]==c["sha256"] and r["rep"]==rep]
            need({r["mode"] for r in rr}==set(MODES),"not source paired")
            need(len({r["status"] for r in rr
                if r["status"]!="TIMEOUT"})<=1,"contradictory results")
    totals={}
    for g in ("all",)+cohorts:
        grp=[r for r in records if g=="all" or r["group"]==g]
        modes={}
        for mode in MODES:
            rr=[r for r in grp if r["mode"]==mode]
            modes[mode]={"attempts":len(rr),
               "solved":sum(r["status"]!="TIMEOUT" for r in rr),
               "PAR2_s":round(sum(r["par2_s"] for r in rr),6),
               "SAT":sum(r["status"]=="SAT" for r in rr),
               "UNSAT":sum(r["status"]=="UNSAT" for r in rr),
               "profile_s":round(sum(r["profile_s"] for r in rr),6),
               "pilots":sum(r["pilot"] is not None for r in rr),
               "pilot_s":round(sum(
                 r["pilot"]["elapsed_s"] for r in rr if r["pilot"]),6),
               "CMS_selections":sum(r["selected"].startswith("cms") for r in rr),
               "Kissat_selections":sum(r["selected"].startswith("kissat") for r in rr)}
        comparisons={}
        for candidate,baseline in (
          ("ta4_structural","ta3_portfolio"),
          ("ta4_pilot","ta3_portfolio"),
          ("ta4_pilot","ta4_pilot_shadow"),
          ("ta4_pilot","cms_plain"),
          ("ta4_pilot","kissat_plain"),
          ("ta3_portfolio","cms_plain"),
          ("ta3_portfolio","kissat_plain"),
        ):
            base={(r["sha256"],r["rep"]):r for r in grp
                  if r["mode"]==baseline}
            selected=[r for r in grp if r["mode"]==candidate]
            wins=losses=ties=0
            for r in selected:
                d=r["par2_s"]-base[(r["sha256"],r["rep"])]["par2_s"]
                if d<-.001:wins+=1
                elif d>.001:losses+=1
                else:ties+=1
            b=modes[baseline]["PAR2_s"];v=modes[candidate]["PAR2_s"]
            comparisons[candidate+"__vs__"+baseline]={
               "wins":wins,"losses":losses,"ties":ties,
               "par2_reduction_pct":round(100*(b-v)/b,3) if b else None,
               "PAR2_delta_s":round(b-v,6)}
        totals[g]={"cases":len(grp)//(REPS*len(MODES)),
                   "modes":modes,"comparisons":comparisons}
    report={"protocol":PROTO,"status":"TA4_AUDIT_PASS",
            "sources":len(cs),"trials":len(records),
            "repetitions":REPS,"cap_s":CAP,"pilot_cap_s":PILOT_CAP,
            "pilot_conflict_cap":PILOT_CONFLICTS,
            "source_disjoint_R189_R199_TA3":True,
            "rules_frozen_before_TA4_results":True,
            "include_profile_and_pilot_in_elapsed":True,
            "SAT_witness_original_verified":True,
            "generic_UNSAT_independent_LRAT":False,
            "results":totals}
    save(ROOT/"report.json",report)
    save(ROOT/"all_trials.json",records)
    lines=["# DRNAS TA4 — prospective 15-original mixed-SAT adaptive CDCL pilot",
      "",
      "15 SAT2025 originals SHA-disjoint from R189/R199/TA3; 10 SAT and 5 UNSAT.",
      "8 modes x 2 paired reps = 240 attempts, 20s wall cap incl. profiling,",
      "early Kissat conflict-limited probe (if eligible) and SAT original witness.",
      "Rules developed from TA3, frozen before TA4 outcomes. Independent generic",
      "CDCL UNSAT LRAT is NOT checked.",
      "",
      "## PAR2 scorecard (negative means regression)",
      "",
      "| TA4 pilot vs TA3 | TA4 pilot vs pilot-shadow | TA4 pilot vs CMS | TA4 pilot vs Kissat |",
      "|---:|---:|---:|---:|"]
    cs2=totals["all"]["comparisons"]
    keys=("ta4_pilot__vs__ta3_portfolio",
          "ta4_pilot__vs__ta4_pilot_shadow",
          "ta4_pilot__vs__cms_plain",
          "ta4_pilot__vs__kissat_plain")
    lines.append("| "+" | ".join(
        "%+.3f%%"%cs2[k]["par2_reduction_pct"] for k in keys)+" |")
    lines+=["","| Cohort | Mode | Solved/attempts | PAR2 s | Profiles s | Pilots | Pilots s |",
            "|---|---|---:|---:|---:|---:|---:|"]
    for group,d in totals.items():
        for k,m in d["modes"].items():
            lines.append("| %s | %s | %d/%d | %.3f | %.3f | %d | %.3f |"%
                (group,k,m["solved"],m["attempts"],m["PAR2_s"],
                 m["profile_s"],m["pilots"],m["pilot_s"]))
    lines+=["","## Paired comparisons","","| Cohort | Variant / baseline | W/L/T | PAR2 improvement |",
            "|---|---|---:|---:|"]
    for group,d in totals.items():
        for key,m in d["comparisons"].items():
            lines.append("| %s | %s | %d/%d/%d | %+.3f%% |"%
                (group,key,m["wins"],m["losses"],m["ties"],
                 m["par2_reduction_pct"]))
    (ROOT/"summary.md").write_text("\n".join(lines)+"\n")
    print("TA4_FINAL",json.dumps({"all":totals["all"],
           "trials":240,"status":"TA4_AUDIT_PASS"},sort_keys=True),flush=True)

def smoke():
    p=ROOT/"smoke.cnf";p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text("p cnf 3 4\n1 2 3 0\n-1 -2 3 0\n1 -2 -3 0\n-1 2 -3 0\n")
    f=ta3.fast_features(p)
    need(f["sampled_clauses"]==4,"failed source feature smoke")
    for mode in ("ta3_portfolio","ta4_structural",
                 "ta4_pilot","ta4_pilot_shadow"):
        selection,reason=choose(mode,f,None)
        need(selection in ("cms_plain","kissat_plain","cms_r28","kissat_r28"),
             "invalid route "+reason)
    # Probe must produce observable conflict/decision telemetry with a short
    # budget or abstain safely on a trivial source, never false proof claims.
    result=pilot_kissat(p,time.perf_counter())
    need(result["status"] in ("SATISFIABLE","UNSATISFIABLE","UNKNOWN",
         "TIME_BUDGET","NO_STATUS","NOT_RUN"),"invalid pilot status")
    need(result["elapsed_s"]<=PILOT_CAP+0.2,"pilot exceeded budget")
    print("TA4_SMOKE_PASS",flush=True)

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("action",choices=("fetch","smoke","shard","audit"))
    cli.add_argument("--shard",type=int,default=0)
    args=cli.parse_args()
    if args.action=="fetch":fetch()
    elif args.action=="smoke":smoke()
    elif args.action=="shard":shard(args.shard)
    else:audit()
