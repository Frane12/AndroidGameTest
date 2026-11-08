#!/usr/bin/env python3
"""DRNAS CRR1-B8: source-locked original SAT2025 medium scout + short paired test.

The 24 originals come from the previously benchmarked TA3 source archive,
not a blind holdout. The frozen SHA is independently verified for each CNF.

Scout all 24 with a 5-second original Kissat run, verified SAT witness or
independent DRAT for UNSAT, and separate source-certified GF(2) discovery.
For a MEDIUM eligible case require: verified solve, 0.4-5.0 native seconds,
>=1 original source certified GF(2) clause, >=1 CDCL conflict. Only these
undergo 2x three-arm 6-second source-paired full solves. Previously solved
medium hgen is a designated negative control if no qualifying opportunity.
No synthetic formulas and no unverified solved status or benchmark promotion.
Do not upload raw DRAT logs, native solver logs or giant CNF duplicates.
"""
import argparse
import json
import os
from pathlib import Path
import random
import re
import signal
import statistics
import subprocess
import sys
import time

import drnas_crr1a_shadow as a
import drnas_crr1b_active as b
import drnas_crr1b2_telemetry as b2
import drnas_crr1b6_conflict_profile as b6
import drnas_crr1b7b_easy_xor as b7

ROOT=Path("crr1b8")
PROTO="DRNAS-CRR1B8-TA3-24-SCOUT-5S-3ARMS-2REPS-6S-v1"
SCOUT_CAP=5.0
PAIR_CAP=6.0
SHARDS=8
REPS=2
MODES=("kissat_plain","b3_loose8","b5_multi8")
FALLBACK_ID="2d0c041c-hgen"
MIN_MEDIUM=0.4
MAX_MEDIUM=5.0

def need(ok,message):
    if not ok:raise RuntimeError("CRR1B8_FAIL_CLOSED "+message)

def save(path,value):a.save(path,value)

def cases():
    m=json.loads(Path("ta3/manifest.json").read_text())
    cc=sorted(m["cases"],key=lambda x:x["sha256"])
    need(len(cc)==24 and len({r["sha256"] for r in cc})==24,
         "TA3 source set must be 24 distinct originals")
    assert all("id" in r and "sha256" in r for r in cc)
    for c in cc:
        path=Path("ta3/sources")/(c["id"]+".cnf")
        need(path.is_file() and a.sha(path)==c["sha256"],
             "TA3 source mismatch "+c["id"])
    return cc

def split_cases():
    cc=cases()
    buckets=[[] for _ in range(SHARDS)]
    for i,c in enumerate(cc):buckets[i%SHARDS].append(c)
    need(all(len(x)==3 for x in buckets),"TA3 3x8 buckets invalid")
    return buckets

def selftest():
    b2.selftest()
    b7.parent.selftest()
    need(MODES==("kissat_plain","b3_loose8","b5_multi8"),
         "3-arm benchmark drift")
    print("CRR1B8_SELFTEST_PASS",flush=True)

def prepare():
    selftest()
    cc=cases()
    need(a.KISSAT.is_file() and a.CHECKER.is_file(),"pinned solver/checker missing")
    ROOT.mkdir(exist_ok=True)
    m={"protocol":PROTO,"source":"TA3 SAT2025 24 frozen original CNFs",
       "TA3_original_manifest_sha256":a.sha("ta3/manifest.json"),
       "case_ids":[c["id"] for c in cc],
       "source_sha256":[c["sha256"] for c in cc],
       "shards":SHARDS,"cases_per_shard":3,
       "scout_cap_s":SCOUT_CAP,"medium_native_s_interval":[MIN_MEDIUM,MAX_MEDIUM],
       "pair_cap_s":PAIR_CAP,"pair_reps":REPS,"modes":list(MODES),
       "eligibility":"verified SAT original model or UNSAT independent DRAT; medium; conflicts>=1; derived certified XOR clauses>=1",
       "fallback_control":FALLBACK_ID,
       "blind_holdout":False,"promotion_allowed":False,
       "prior_ta3_source_reuse":True,
       "no_synthetic_or_unverified_solves":True,
       "source_proof":"every appended XOR clause replayed from original complete CNF parity masks",
       "stats":"native Kissat conflicts, decisions, propagations, proof-gated results"}
    save(ROOT/"manifest.json",m)
    filenames=[
       "research/drnas_crr1b8_medium_ta3.py",
       "research/drnas_crr1b7b_easy_xor.py",
       "research/drnas_crr1b6_conflict_profile.py",
       "research/drnas_crr1b5_discrimination.py",
       "research/drnas_crr1b4_value.py",
       "research/drnas_crr1b3loose.py",
       "research/drnas_crr1b2_telemetry.py",
       "research/drnas_crr1b_active.py",
       "research/drnas_crr1a_shadow.py",
       ".github/workflows/drnas-crr1b8-medium-ta3.yml",
       "ta3/manifest.json","crr1b8/manifest.json",
       "checker/drat-trim","built/bin/kissat_4_0_4"]
    save(ROOT/"pins.json",{f:a.sha(f) for f in filenames})
    verify()
    print("CRR1B8_PREP_PASS",a.sha(ROOT/"manifest.json"),flush=True)

def verify():
    cc=cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["TA3_original_manifest_sha256"]==
         a.sha("ta3/manifest.json") and m["source_sha256"]==
         [c["sha256"] for c in cc] and m["modes"]==list(MODES),
         "manifest drift")
    for f,digest in json.loads((ROOT/"pins.json").read_text()).items():
        need(a.sha(f)==digest,"pinned source drift "+f)
    return split_cases()

def parse_ta3(path):
    """Validate large TA3 DIMACS sources beyond W4's artificial 180k cap."""
    header=None;clauses=[];pending=[]
    with Path(path).open() as fp:
        for line in fp:
            item=line.strip()
            if not item or item.startswith(("c","%")):continue
            if item.startswith("p "):
                fields=item.split()
                need(header is None and len(fields)==4 and
                     fields[:2]==["p","cnf"],"invalid TA3 DIMACS header")
                n,total=map(int,fields[2:])
                need(1<=n<=2500000 and 0<=total<=3500000,
                     "source exceeds independent TA3 safety bounds")
                header=(n,total)
                continue
            need(header is not None,"DIMACS body before header")
            for word in item.split():
                lit=int(word)
                need(abs(lit)<=header[0],"out of bounds TA3 literal")
                if lit:pending.append(lit)
                else:
                    clauses.append(tuple(pending));pending=[]
                    need(len(clauses)<=header[1],"excess TA3 clauses")
    need(header is not None and not pending and
         len(clauses)==header[1],"incomplete TA3 source DIMACS")
    return header[0],clauses


def scout(c,shard):
    path=Path("ta3/sources")/(c["id"]+".cnf")
    need(a.sha(path)==c["sha256"],"scout original SHA drift")
    n,original=parse_ta3(path)
    t0=time.perf_counter()
    proposed,proofs,discovery=b2.make_bridge(n,original)
    if proposed:
        need(len(proposed)==len(proofs) and
             b.certify_added(original,proofs)==set(proposed),
             "all GF2 candidate certificates must replay from original")
    discovery_s=time.perf_counter()-t0
    proof=ROOT/"raw"/str(shard)/(c["id"]+".scout.drat")
    proof.parent.mkdir(parents=True,exist_ok=True)
    command=[str(a.KISSAT.resolve()),"--statistics",str(path.resolve()),
             str(proof.resolve())]
    start=time.perf_counter()
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                       text=True,start_new_session=True)
    timeout=False
    try:out,_=p.communicate(timeout=SCOUT_CAP)
    except subprocess.TimeoutExpired:
        timeout=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,_=p.communicate()
    native_s=min(SCOUT_CAP,time.perf_counter()-start)
    stats=b6.native_statistics(out) if not timeout else None
    evidence="SCOUT_WALL_TIMEOUT"
    status="TIMEOUT"
    if not timeout:
        matches=re.findall(r"(?m)^s (SATISFIABLE|UNSATISFIABLE|UNKNOWN)\s*$",out)
        need(len(matches)==1,"scout native terminal verdict missing "+out[-1000:])
        native=matches[0]
        if native=="SATISFIABLE":
            need(p.returncode==10,"scout SAT exit")
            b6.witness(out,original,[])
            status="SAT";evidence="SAT_ORIGINAL_MODEL_VERIFIED"
        elif native=="UNSATISFIABLE":
            need(p.returncode==20,"scout UNSAT exit")
            if proof.is_file() and proof.stat().st_size:
                try:
                    q=subprocess.run([str(a.CHECKER.resolve()),str(path.resolve()),
                                      str(proof.resolve())],
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                         timeout=30)
                    if q.returncode==0 and "s VERIFIED" in q.stdout:
                        status="UNSAT";evidence="UNSAT_SOURCE_DRAT_VERIFIED"
                    else:
                        status="UNVERIFIED_UNSAT";evidence="INDEPENDENT_DRAT_FAILED"
                except subprocess.TimeoutExpired:
                    status="UNVERIFIED_UNSAT";evidence="DRAT_CHECK_TIMEOUT"
            else:status="UNVERIFIED_UNSAT";evidence="DRAT_MISSING"
        else:
            need(native=="UNKNOWN" and p.returncode==0,"scout UNKNOWN exit")
            status="UNKNOWN";evidence="NATIVE_UNKNOWN_NOT_SOLVED"
    if proof.exists():proof.unlink()
    eligible=(status in ("SAT","UNSAT") and
       MIN_MEDIUM<=native_s<=MAX_MEDIUM and
       stats is not None and (stats.get("conflicts") or 0)>=1 and len(proposed)>=1
       and n<=200000 and len(original)<=180000)
    result={"id":c["id"],"sha256":c["sha256"],"shard":shard,
         "family":c.get("family"),"cohort":"original_SAT2025_TA3",
         "status":status,"proof":evidence,"native_s":round(native_s,6),
         "discovery_s":round(discovery_s,6),
         "new_certified_clauses":len(proposed),
         "complete_xor_equations":discovery.get("complete_xor_equations"),
         "discovery_status":discovery.get("status"),
         "native":stats,"medium_eligible":bool(eligible),
         "paired_parser_supported":n<=200000 and len(original)<=180000,
         "source_variables":n,"source_clauses":len(original)}
    return result

def shard(i):
    buckets=verify()
    need(0<=i<SHARDS,"invalid original source shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    originals=buckets[i]
    scout_rows=[]
    for c in originals:
        row=scout(c,i)
        scout_rows.append(row)
        save(ROOT/("scout-%d.json"%i),scout_rows)
        print("CRR1B8_SCOUT",json.dumps(row,sort_keys=True),flush=True)
    selected=[c for c in originals if next(r for r in scout_rows
                    if r["sha256"]==c["sha256"])["medium_eligible"]]
    if not selected:
        selected=[c for c in originals if c["id"]==FALLBACK_ID and
                  next(r for r in scout_rows if r["sha256"]==
                       c["sha256"])["status"]=="SAT"]
    selected_ids=[c["id"] for c in selected]
    results=[]
    # Exact same full-solve cap and verifier from B7b, with original TA3 path.
    b7.ROOT=ROOT
    b7.PROTO=PROTO
    b7.CAP=PAIR_CAP
    for c in selected:
        case={"id":c["id"],"sha256":c["sha256"],
              "cohort":"original_SAT2025_TA3",
              "path":str(Path("ta3/sources")/(c["id"]+".cnf"))}
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                r=b7.trial(case,mode,rep,i)
                need(r["protocol"]==PROTO and r["cohort"]==case["cohort"],
                     "paired row trial protocol mismatch")
                r["scout_eligible"]=c["id"]!=FALLBACK_ID or next(
                    x for x in scout_rows if x["id"]==c["id"])["medium_eligible"]
                results.append(r)
                save(ROOT/("paired-%d.json"%i),results)
                print("CRR1B8_PAIRED",json.dumps({k:v for k,v in r.items()
                        if k not in ("selected_clauses","native")},sort_keys=True),
                      flush=True)
    # Files must exist even when no sources qualify.
    save(ROOT/("paired-%d.json"%i),results)
    need(len(scout_rows)==3 and len(results)==len(selected)*REPS*len(MODES),
         "source scout/paired integrity")
    print("CRR1B8_SHARD_PASS",i,"scouted",len(scout_rows),
          "paired",len(results),"selected",json.dumps(selected_ids),flush=True)

def audit():
    buckets=verify()
    scouts=[];paired=[];seen=set();triples=set()
    for i,originals in enumerate(buckets):
        ss=json.loads((ROOT/("scout-%d.json"%i)).read_text())
        pp=json.loads((ROOT/("paired-%d.json"%i)).read_text())
        need(len(ss)==3,"scout coverage incomplete")
        for c,r in zip(originals,ss):
            need(c["id"]==r["id"] and c["sha256"]==r["sha256"] and
                 r["shard"]==i and r["cohort"]=="original_SAT2025_TA3",
                 "scout source order and SHA invalid")
            need(r["sha256"] not in seen,"duplicate source scout")
            seen.add(r["sha256"])
            need(r["status"] not in ("SAT","UNSAT") or
                 r["proof"] in ("SAT_ORIGINAL_MODEL_VERIFIED",
                              "UNSAT_SOURCE_DRAT_VERIFIED"),
                 "unverified scout result")
            scouts.append(r)
        expected_ids={r["id"] for r in ss if r["medium_eligible"]}
        if not expected_ids and FALLBACK_ID in {r["id"] for r in ss}:
            if next(r for r in ss if r["id"]==FALLBACK_ID)["status"]=="SAT":
                expected_ids.add(FALLBACK_ID)
        need(len(pp)==len(expected_ids)*REPS*len(MODES),
             "missing source paired trials")
        for r in pp:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in triples and r["id"] in expected_ids and
                 r["protocol"]==PROTO and r["shard"]==i and
                 r["rep"] in range(REPS) and r["mode"] in MODES and
                 r["cohort"]=="original_SAT2025_TA3",
                 "invalid paired provenance")
            triples.add(key)
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid native status")
            need(r["status"]!="SAT" or
                 r["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED","SAT no source model")
            need(r["status"]!="UNSAT" or
                 r["proof"]=="UNSAT_AUGMENTED_DRAT_AND_SOURCE_GF2_VERIFIED",
                 "UNSAT DRAT/GF2 missing")
            paired.append(r)
    need(len(scouts)==24 and len(seen)==24,"not 24 distinct TA3 originals")
    qual=[r for r in scouts if r["medium_eligible"]]
    def summary_for(id):
        rows=[x for x in paired if x["id"]==id]
        return {"id":id,"eligible":any(r["id"]==id for r in qual),
          "scores":{mode:{
            "attempts":len(z),
            "solved_verified":sum(r["status"] in ("SAT","UNSAT") for r in z),
            "PAR2_s":round(sum(r["par2_s"] for r in z),6),
            "median_total_wall_s":round(statistics.median(
                              r["elapsed_s"] for r in z),6) if z else None,
            "median_native_s":round(statistics.median(
               r["native_s"] for r in z if r["native_s"] is not None),6)
               if any(r["native_s"] is not None for r in z) else None,
            "added":sorted({r["added"] for r in z if r["added"] is not None}),
            "statuses":[r["status"] for r in z]}
            for mode in MODES for z in [[r for r in rows if r["mode"]==mode]]}}
    selected=sorted({r["id"] for r in paired})
    report={"status":"CRR1B8_AUDIT_PASS","protocol":PROTO,
      "scout_cases":len(scouts),"medium_eligible_count":len(qual),
      "medium_eligible":[{"id":r["id"],"sha256":r["sha256"],
          "native_s":r["native_s"],"new_clauses":r["new_certified_clauses"],
          "conflicts":r["native"]["conflicts"] if r["native"] else None}
          for r in qual],
      "scout_all":[{"id":r["id"],"sha256":r["sha256"],"status":r["status"],
          "native_s":r["native_s"],"clauses":r["new_certified_clauses"],
          "conflicts":r["native"]["conflicts"] if r["native"] else None,
          "proof":r["proof"]} for r in scouts],
      "paired_trials":len(paired),
      "paired_formulas":[summary_for(id) for id in selected],
      "fallback_control_if_no_eligible":FALLBACK_ID,
      "no_synthetic":True,"reused_TA3_not_blind":True,
      "promotion_allowed":False,
      "verified_solutions_only":True}
    save(ROOT/"report.json",report)
    save(ROOT/"all-scouts.json",scouts)
    save(ROOT/"all-paired.json",paired)
    print("CRR1B8_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","prepare","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
