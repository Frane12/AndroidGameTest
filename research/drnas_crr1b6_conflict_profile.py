#!/usr/bin/env python3
"""DRNAS CRR1-B6 — source-paired B3L-8 vs B5-8 at fixed Kissat conflict limits.

DEVELOPMENT ONLY: four post-hoc SAT2026 W4 originals, not an unseen holdout.
Kissat 4.0.4 is identical, source SHA locked, 1 CPU, randomized paired arms.
--conflicts=<limit> ends the search with UNKNOWN, not a verified solve.
Unknown is never counted as SAT/UNSAT or as PAR2 success.

Tracked: CPU-pinned per-run wall time including certified preprocessing,
native solve time, exact conflicts, decisions and propagations on normal exits.
Does NOT claim conflicts reached means progress toward a solution.
Verified SAT models must satisfy the ORIGINAL source; UNSAT DRAT checks run
on the exact augmented input and every appended clause has GF(2) replay.
No giant solver logs or proof blobs are kept in GitHub artifacts.
"""
import argparse
import json
import math
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
import drnas_crr1b3loose as b3
import drnas_crr1b4_value as b4
import drnas_crr1b5_discrimination as b5

ROOT=Path("crr1b6")
SOURCE=a.SOURCE
PROTO="DRNAS-CRR1B6-W4-4SHA-3ARMS-3CONFLICTCAPS-2REPS-v1"
MODES=("kissat_plain","b3_loose8","b5_multi8")
LIMITS=(500,5000,25000)
REPS=2
SHARDS=4
SELECTION_SEED=101  # Precommitted first B5 diagnostic seed; never adapt to timing.
WALL_CAP=25.0

def need(ok,description):
    if not ok:raise RuntimeError("CRR1B6_FAIL_CLOSED "+str(description))

def save(path,obj):a.save(path,obj)

def cases():
    cc=b2.cases()
    need(len(cc)==SHARDS and tuple(c["id"] for c in cc)==b2.FOCUS_IDS,
         "original focus cohort changed")
    return cc

def select_input(n,original,mode):
    if mode=="kissat_plain":return [],[],{"selection":"NONE","selected":0}
    candidate,proofs,base=b2.make_bridge(n,original)
    if mode=="b3_loose8":
        selected,cert,gate=b3.filter_novel(n,original,candidate,proofs,max_added=8)
        return selected,cert,{"selection":"B3L_STRUCTURE","discovered":len(candidate),
                             "selected":len(selected),"gate_status":gate["status"],
                             "gate_reason":gate.get("reason"),"analysis_s":gate.get("analysis_s")}
    need(mode=="b5_multi8","unrecognized selection")
    if not candidate:
        return [],[],{"selection":"B5_MULTI_CONTEXT","discovered":0,
                     "selected":0,"status":"NO_CANDIDATES"}
    deadline=time.perf_counter()+4.0
    try:
        profile=b5.discriminate(original,candidate,proofs,SELECTION_SEED,deadline)
    except TimeoutError as exc:
        return [],[],{"selection":"B5_MULTI_CONTEXT","status":"BUDGET_CUTOFF",
                     "reason":str(exc),"discovered":len(candidate),"selected":0}
    need(profile["status"]=="OK","B5 original-CNF discrimination did not finish")
    ranked=sorted(profile["all_candidates"],
                  key=lambda r:(tuple(-v for v in r["profile_vector"]),
                                -r["b4_support"],r["clause"]))
    picked=[tuple(r["clause"]) for r in ranked[:8]]
    by_clause={tuple(sorted(c)):proof for c,proof in zip(candidate,proofs)}
    need(len(by_clause)==len(candidate),"duplicate original GF2 candidates")
    chosen_certs=[by_clause[c] for c in picked]
    need(b.certify_added(original,chosen_certs)==set(picked),
         "B5 selected candidates not certified")
    return picked,chosen_certs,{"selection":"B5_MULTI_CONTEXT",
      "status":"OK","discovered":len(candidate),"selected":len(picked),
      "seed":SELECTION_SEED,"unique_b4_scores":profile["unique_b4_scores"],
      "unique_b5_profiles":profile["unique_b5_profiles"],
      "top8_changes_vs_B4":profile["top8_changes"],
      "top8_conflicts":sum(r["profile"]["conflicts"] for r in ranked[:8]),
      "top8_downstream":sum(r["profile"]["downstream"] for r in ranked[:8]),
      "selection_analysis_s":profile["elapsed_s"]}

def stat(log,key):
    matches=re.findall(r"(?m)^c\s+"+re.escape(key)+r":\s+([0-9]+)(?=\s|$)",log)
    return int(matches[-1]) if matches else None

def native_statistics(log):
    return {field:stat(log,field)
            for field in ("conflicts","decisions","propagations","restarts")}

def witness(log,original,extra):
    model={}
    for line in log.splitlines():
        if line.startswith("v "):
            for word in line[2:].split():
                lit=int(word)
                if not lit:continue
                need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                     "SAT assignment contains conflicting literal")
                model[abs(lit)]=lit>0
    need(model,"empty native SAT assignment")
    for clause in original+list(extra):
        need(any(model.get(abs(l))==(l>0) for l in clause),
             "SAT witness does not satisfy exact original/augmented CNF")
    return model

def worker(source,mode,limit,folder):
    started=time.perf_counter()
    folder=Path(folder)
    n,original=a.parse(source)
    selected,cert,selection=select_input(n,original,mode)
    need(len(selected)==len(cert),"selected proof cardinality")
    if selected:need(b.certify_added(original,cert)==set(selected),
                     "GF2 consequences not certified from original")
    input_path=Path(source)
    if selected:
        input_path=folder/"augmented.cnf"
        with input_path.open("w") as f:
            f.write("p cnf %d %d\n"%(n,len(original)+len(selected)))
            for c in original:
                f.write(" ".join(map(str,c))+" 0\n")
            for c in selected:
                f.write(" ".join(map(str,c))+" 0\n")
        save(folder/"certificates.json",cert)
    ready={"stage":"SOLVER_READY","source_sha256":a.sha(source),
       "solver_input_sha256":a.sha(input_path),
       "mode":mode,"conflict_limit":limit,"selection":selection,
       "selected_clauses":[list(c) for c in selected],
       "prep_s":round(time.perf_counter()-started,6),
       "proof_replay_complete":True}
    save(folder/"telemetry.json",ready)
    print("CRR1B6_READY",json.dumps({k:v for k,v in ready.items()
          if k!="selected_clauses"},sort_keys=True),flush=True)
    proof=folder/"native.drat"
    solver_start=time.perf_counter()
    command=[str(a.KISSAT.resolve()),"--statistics",
             "--conflicts=%d"%limit,str(input_path.resolve()),
             str(proof.resolve())]
    p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                     text=True)
    elapsed=time.perf_counter()-solver_start
    matches=re.findall(r"(?m)^s\s+(SATISFIABLE|UNSATISFIABLE|UNKNOWN)\s*$",p.stdout)
    need(len(matches)==1,"missing/ambiguous Kissat verdict: "+p.stdout[-1000:])
    verdict=matches[0]
    need((verdict=="UNKNOWN" and p.returncode==0) or
         (verdict=="SATISFIABLE" and p.returncode==10) or
         (verdict=="UNSATISFIABLE" and p.returncode==20),
         "native Kissat returned wrong exit code or verdict")
    stats=native_statistics(p.stdout)
    need(stats["conflicts"] is not None and
         stats["decisions"] is not None and
         stats["propagations"] is not None,
         "missing native stats at fixed conflict budget")
    if verdict=="SATISFIABLE":
        save(folder/"model.json",witness(p.stdout,original,selected))
    # Only retain last 4 kB of native diagnostics; extract metrics before.
    (folder/"native.log").write_text(p.stdout[-4000:])
    terminal={"verdict":verdict,"native_returncode":p.returncode,
       "statistics":stats,"solver_s":round(elapsed,6),
       "source_sha256":a.sha(source),"solver_input_sha256":a.sha(input_path),
       "conflict_limit":limit}
    save(folder/"terminal.json",terminal)
    print("CRR1B6_TERMINAL",json.dumps(terminal,sort_keys=True),flush=True)

def verified_input(source,folder,ready):
    need(ready["source_sha256"]==a.sha(source),"original SHA drift")
    need(ready["proof_replay_complete"],"unverified source consequence")
    selected=[tuple(c) for c in ready["selected_clauses"]]
    if not selected:
        need(ready["solver_input_sha256"]==a.sha(source),
             "solver source input drift")
        return source
    augmented=folder/"augmented.cnf"
    n,original=a.parse(source)
    aug_n,combined=a.parse(augmented)
    proof=json.loads((folder/"certificates.json").read_text())
    need(aug_n==n and combined[:len(original)]==original
         and combined[len(original):]==selected
         and b.certify_added(original,proof)==set(selected),
         "source vs augmented/certified CNF mismatch")
    need(ready["solver_input_sha256"]==a.sha(augmented),
         "augmented native input SHA drift")
    return augmented

def trial(c,mode,limit,rep,shard):
    source=SOURCE/(c["id"]+".cnf")
    need(a.sha(source)==c["sha256"],"frozen original source SHA mismatch")
    folder=ROOT/"raw"/str(shard)/("%s-r%d-%s-c%d"%(c["id"],rep,mode,limit))
    folder.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    p=subprocess.Popen([sys.executable,__file__,"worker",
          "--source",str(source),"--mode",mode,
          "--limit",str(limit),"--directory",str(folder)],
          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
          text=True,start_new_session=True)
    overtime=False
    try:
        out,_=p.communicate(timeout=max(.001,WALL_CAP-(time.perf_counter()-start)))
    except subprocess.TimeoutExpired:
        overtime=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,_=p.communicate()
    wall=min(WALL_CAP,time.perf_counter()-start)
    ready=json.loads((folder/"telemetry.json").read_text()) if (
      folder/"telemetry.json").is_file() else None
    terminal=json.loads((folder/"terminal.json").read_text()) if (
      folder/"terminal.json").is_file() else None
    status="WALL_TIMEOUT" if overtime else "INVALID"
    proof_status="TIMEOUT_BEFORE_PREP" if ready is None else "NO_NATIVE_VERDICT"
    stats=None;solver_s=None
    if ready:
        need(ready["stage"]=="SOLVER_READY" and
             ready["source_sha256"]==c["sha256"] and
             ready["mode"]==mode and ready["conflict_limit"]==limit,
             "telemetry metadata mismatch")
        input_path=verified_input(source,folder,ready)
    else:input_path=source
    proof_checker_s=None
    if terminal is not None and not overtime:
        need(p.returncode==0 and ready is not None and
             terminal["source_sha256"]==c["sha256"] and
             terminal["solver_input_sha256"]==ready["solver_input_sha256"]
             and terminal["conflict_limit"]==limit,
             "native reported terminal but worker failed: "+out[-800:])
        reported=terminal["verdict"]
        stats=terminal["statistics"];solver_s=terminal["solver_s"]
        if reported=="UNKNOWN":
            status="BUDGET"
            proof_status="CONFLICT_LIMIT_UNKNOWN_NOT_SOLVED"
            need(stats["conflicts"] is not None
                 and stats["conflicts"]<=limit+16,
                 "conflicts above specified native limit")
        elif reported=="SATISFIABLE":
            model={int(k):v for k,v in json.loads(
                (folder/"model.json").read_text()).items()}
            _,original=a.parse(source)
            need(all(any(model.get(abs(l))==(l>0) for l in clause)
                     for clause in original),"SAT original witness invalid")
            status="SAT";proof_status="SAT_ORIGINAL_MODEL_VERIFIED"
        elif reported=="UNSATISFIABLE":
            t=time.perf_counter()
            proof=folder/"native.drat"
            if proof.is_file() and proof.stat().st_size:
                try:
                    ch=subprocess.run([str(a.CHECKER.resolve()),
                          str(input_path.resolve()),str(proof.resolve())],
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,timeout=55)
                    if ch.returncode==0 and "s VERIFIED" in ch.stdout:
                        status="UNSAT"
                        proof_status="UNSAT_DRAT_PLUS_SOURCE_GF2_VERIFIED"
                    else:
                        status="UNVERIFIED_UNSAT"
                        proof_status="UNSAT_PROOF_INVALID_NOT_SCORED"
                except subprocess.TimeoutExpired:
                    status="UNVERIFIED_UNSAT"
                    proof_status="UNSAT_PROOF_TIMEOUT_NOT_SCORED"
            else:
                status="UNVERIFIED_UNSAT"
                proof_status="UNSAT_PROOF_MISSING_NOT_SCORED"
            proof_checker_s=round(time.perf_counter()-t,6)
        else:need(False,"unexpected native solver verdict")
    elif not overtime:
        need(False,"worker exited prematurely: "+out[-1200:])
    for name in ("native.drat","augmented.cnf","certificates.json",
                 "model.json","native.log","terminal.json"):
        f=folder/name
        if f.exists():f.unlink()
    result={"protocol":PROTO,"id":c["id"],"sha256":c["sha256"],
       "shard":shard,"rep":rep,"mode":mode,
       "conflict_limit":limit,"status":status,"proof":proof_status,
       "elapsed_s":round(wall,6),"solver_s":solver_s,
       "prep_s":ready["prep_s"] if ready else None,
       "added":len(ready["selected_clauses"]) if ready else None,
       "selected_clauses":ready["selected_clauses"] if ready else None,
       "selection":ready["selection"] if ready else None,
       "native":stats,"native_reached_budget":status=="BUDGET" and
             stats["conflicts"]>=max(0,limit-16),
       "proof_checker_s":proof_checker_s}
    print("CRR1B6_TRIAL",json.dumps({k:v for k,v in result.items()
          if k!="selected_clauses"},sort_keys=True),flush=True)
    return result

def make_ph_formula(path):
    # Unsat pigeonhole: 13 pigeons, 12 holes, no shortcut by a unit.
    pigeons=13;holes=12
    clauses=[]
    def x(i,j):return i*holes+j+1
    for i in range(pigeons):
        clauses.append([x(i,j) for j in range(holes)])
    for j in range(holes):
        for i in range(pigeons):
            for k in range(i+1,pigeons):
                clauses.append([-x(i,j),-x(k,j)])
    with Path(path).open("w") as f:
        f.write("p cnf %d %d\n"%(pigeons*holes,len(clauses)))
        for c in clauses:f.write(" ".join(map(str,c))+" 0\n")

def selftest():
    # Both original certifications and the B5 multi-context differentiation.
    b5.selftest()
    original=a.fixture_xor((1,2),0)+a.fixture_xor((1,2,3),1)
    chosen,cert,base=b2.make_bridge(3,original)
    if chosen:
        derived,proof,sel=select_input(3,original,"b5_multi8")
        need(b.certify_added(original,proof)==set(derived),
             "B6 B5 selected GF2 original entailment")
    need(stat("c conflicts:  4523 8.0 per second\n","conflicts")==4523,
         "native Kissat conflicts stats parser")
    need(stat("c propagations: 1234567 11.2 per second","propagations")==1234567,
         "native Kissat propagations stats parser")
    print("CRR1B6_SELFTEST_PASS",flush=True)

def prepare():
    selftest()
    need(a.KISSAT.is_file() and a.CHECKER.is_file(),"pinned Kissat/checker missing")
    cc=cases()
    for c in cc:need(a.sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],
                     "source corpus SHA drift")
    ROOT.mkdir(exist_ok=True)
    smoke=ROOT/"conflict-smoke.cnf"
    make_ph_formula(smoke)
    try:
        proc=subprocess.run([str(a.KISSAT.resolve()),"--statistics",
                        "--conflicts=5",str(smoke)],
                        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                        text=True,timeout=20)
        marks=re.findall(r"(?m)^s\s+(SATISFIABLE|UNSATISFIABLE|UNKNOWN)\s*$",
                         proc.stdout)
        need(len(marks)==1 and proc.returncode in (0,10,20),
             "pinned Kissat does not support --conflicts= and stats")
        metrics=native_statistics(proc.stdout)
        need(metrics["conflicts"] is not None and
             metrics["decisions"] is not None and
             metrics["propagations"] is not None,
             "native conflict-limited termination has no statistics")
        need(marks[0]=="UNKNOWN" and proc.returncode==0,
             "pigeonhole calibration did not terminate as UNKNOWN by cap")
        save(ROOT/"smoke.json",{"verdict":marks[0],
                "exit_code":proc.returncode,"metrics":metrics,"limit":5})
    finally:
        if smoke.exists():smoke.unlink()
    manifest={"protocol":PROTO,"modes":list(MODES),"conflict_limits":list(LIMITS),
       "reps":REPS,"shards":SHARDS,"wall_cap_s":WALL_CAP,
       "source_ids":[c["id"] for c in cc],
       "case_sha256":[c["sha256"] for c in cc],
       "original_w4_manifest_sha256":a.sha("history/w4sources/manifest.json"),
       "selection_seed":SELECTION_SEED,"source_set_posthoc":True,
       "blind_holdout":False,"promotion_allowed":False,
       "main_goal":"B3L8 vs B5multi8 at equal native Kissat conflict limits",
       "comparator":"plain Kissat exact original SHA",
       "winner_only_if_solves":False,
       "run_metrics":"elapsed including prep, native conflicts decisions propagations",
       "verified_result":"SAT source model; UNSAT exact augmented DRAT + original GF2 replay",
       "unknown_conflict_limit":"not solved; only profiler statistics",
       "proof_artifacts":"ephemeral; excluded from uploaded artifacts"}
    save(ROOT/"manifest.json",manifest)
    files=["research/drnas_crr1b6_conflict_profile.py",
       "research/drnas_crr1b5_discrimination.py",
       "research/drnas_crr1b4_value.py",
       "research/drnas_crr1b3loose.py",
       "research/drnas_crr1b2_telemetry.py",
       "research/drnas_crr1b_active.py",
       "research/drnas_crr1a_shadow.py",
       ".github/workflows/drnas-crr1b6-conflict-profile.yml",
       "history/w4sources/manifest.json",
       "crr1b6/manifest.json"]
    save(ROOT/"pins.json",{p:a.sha(p) for p in files})
    verify()
    print("CRR1B6_PREP_PASS",a.sha(ROOT/"manifest.json"),flush=True)

def verify():
    cc=cases()
    meta=json.loads((ROOT/"manifest.json").read_text())
    need(meta["protocol"]==PROTO and
         meta["modes"]==list(MODES) and meta["conflict_limits"]==list(LIMITS)
         and meta["case_sha256"]==[c["sha256"] for c in cc]
         and meta["original_w4_manifest_sha256"]==a.sha("history/w4sources/manifest.json"),
         "source lock manifest mismatch")
    for file,digest in json.loads((ROOT/"pins.json").read_text()).items():
        need(a.sha(file)==digest,"source/script/workflow SHA drift: "+file)
    for c in cc:need(a.sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],
                     "original CNF SHA drift")
    return cc

def shard(i):
    cc=verify()
    need(0<=i<SHARDS,"shard outside focus cohort")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    c=cc[i]
    result=[]
    for limit in LIMITS:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(limit)+str(rep)).shuffle(modes)
            for mode in modes:
                row=trial(c,mode,limit,rep,i)
                result.append(row)
                save(ROOT/("shard-%d.json"%i),result)
    need(len(result)==len(LIMITS)*REPS*len(MODES),"incomplete shard")
    print("CRR1B6_SHARD_PASS",i,len(result),flush=True)

def geomean(vals):
    return math.exp(sum(math.log(x) for x in vals)/len(vals)) if vals else None

def audit():
    cc=verify()
    rows=[];keys=set()
    for i,c in enumerate(cc):
        file=ROOT/("shard-%d.json"%i)
        group=json.loads(file.read_text())
        need(len(group)==len(LIMITS)*REPS*len(MODES),
             "incomplete source shard file")
        for row in group:
            key=(row["sha256"],row["conflict_limit"],row["rep"],row["mode"])
            need(key not in keys and
                 row["protocol"]==PROTO and row["sha256"]==c["sha256"]
                 and row["id"]==c["id"] and row["shard"]==i
                 and row["conflict_limit"] in LIMITS and row["rep"] in range(REPS)
                 and row["mode"] in MODES,"incorrect paired provenance")
            keys.add(key)
            need(row["status"] in ("BUDGET","SAT","UNSAT",
                "WALL_TIMEOUT","UNVERIFIED_UNSAT"),"unknown solver status")
            need(row["status"]!="SAT" or
                 row["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED","unverified SAT")
            need(row["status"]!="UNSAT" or
                 row["proof"]=="UNSAT_DRAT_PLUS_SOURCE_GF2_VERIFIED",
                 "unverified UNSAT")
            need(row["status"]!="BUDGET" or
                 row["proof"]=="CONFLICT_LIMIT_UNKNOWN_NOT_SOLVED",
                 "budget result improperly scored")
            if row["status"]=="BUDGET":
                need(row["native_reached_budget"],"unknown without native conflict limit reached")
            rows.append(row)
    required={(c["sha256"],cap,rep,mode) for c in cc for cap in LIMITS
              for rep in range(REPS) for mode in MODES}
    need(keys==required and len(rows)==SHARDS*len(LIMITS)*REPS*len(MODES),
         "paired coverage is missing")
    by={(r["sha256"],r["conflict_limit"],r["rep"],r["mode"]):r for r in rows}
    summaries=[]
    for limit in LIMITS:
        for mode in MODES:
            subset=[r for r in rows if r["conflict_limit"]==limit
                    and r["mode"]==mode]
            reach=[r for r in subset if r["status"]=="BUDGET"]
            summaries.append({"conflict_limit":limit,"mode":mode,
                "attempts":len(subset),"budget_reached":len(reach),
                "solved_verified":sum(r["status"] in ("SAT","UNSAT") for r in subset),
                "timeouts":sum(r["status"]=="WALL_TIMEOUT" for r in subset),
                "unverified":sum(r["status"]=="UNVERIFIED_UNSAT" for r in subset),
                "median_wall_s_at_limit":round(
                    statistics.median(r["elapsed_s"] for r in reach),6) if reach else None,
                "median_native_s_at_limit":round(
                    statistics.median(r["solver_s"] for r in reach),6) if reach else None,
                "median_conflicts":statistics.median(r["native"]["conflicts"]
                        for r in reach) if reach else None,
                "median_decisions":statistics.median(r["native"]["decisions"]
                        for r in reach) if reach else None,
                "median_propagations":statistics.median(r["native"]["propagations"]
                        for r in reach) if reach else None,
                "median_prep_s":round(
                    statistics.median(r["prep_s"] for r in subset
                        if r["prep_s"] is not None),6)})
    paired=[]
    for limit in LIMITS:
        for comparator in ("kissat_plain","b3_loose8"):
            times=[];details=[]
            for c in cc:
                for rep in range(REPS):
                    base=by[c["sha256"],limit,rep,comparator]
                    nxt=by[c["sha256"],limit,rep,"b5_multi8"]
                    if base["status"]=="BUDGET" and nxt["status"]=="BUDGET":
                        ratio=base["elapsed_s"]/nxt["elapsed_s"]
                        times.append(ratio)
                        details.append({"id":c["id"],"rep":rep,
                            "baseline_s":base["elapsed_s"],
                            "b5_s":nxt["elapsed_s"],"speedup":round(ratio,5)})
            paired.append({"conflict_limit":limit,"baseline":comparator,
                "valid_pairs":len(times),
                "geomean_wall_speedup_b5":round(geomean(times),6) if times else None,
                "paired_details":details})
    by_focus=[]
    for c in cc:
        for limit in LIMITS:
            sample=[r for r in rows if r["id"]==c["id"]
                    and r["conflict_limit"]==limit]
            by_focus.append({"id":c["id"],"limit":limit,
                "outcomes":{m:[{"status":r["status"],"wall_s":r["elapsed_s"],
                         "conflicts":r["native"]["conflicts"] if r["native"] else None,
                         "decisions":r["native"]["decisions"] if r["native"] else None,
                         "propagations":r["native"]["propagations"] if r["native"] else None,
                         "added":r["added"]}
                         for r in sample if r["mode"]==m] for m in MODES}})
    focus=cc[0]["id"]
    select_data=[r for r in rows if r["id"]==focus and r["conflict_limit"]==LIMITS[0]
                 and r["rep"]==0]
    picks={r["mode"]:{tuple(c) for c in r["selected_clauses"] or []}
           for r in select_data}
    intersection=len(picks["b3_loose8"]&picks["b5_multi8"])
    report={"status":"CRR1B6_AUDIT_PASS","protocol":PROTO,
       "attempts":len(rows),"cases":len(cc),
       "modes":list(MODES),"limits":list(LIMITS),"reps":REPS,
       "metrics":summaries,"paired":paired,"by_formula":by_focus,
       "focus_source":focus,
       "focus_clause_overlap_8":intersection,
       "focus_clause_changed_8":8-intersection,
       "posthoc_development":True,"promotion_allowed":False,
       "claim_solved_only_with_verification":True,
       "unknown_budget_not_a_solution":True,
       "conflict_rate_not_a_solution_metric":True}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("CRR1B6_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","prepare","worker","shard","audit"))
    parser.add_argument("--source")
    parser.add_argument("--mode")
    parser.add_argument("--limit",type=int)
    parser.add_argument("--directory")
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="worker":
        need(args.mode in MODES and args.limit in LIMITS,
             "invalid native worker input")
        worker(args.source,args.mode,args.limit,args.directory)
    elif args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
