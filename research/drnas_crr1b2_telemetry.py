#!/usr/bin/env python3
"""DRNAS CRR1-B2 — timeout-proof instrumentation and active GF2->CNF bridge.

FOCUSED DEVELOPMENT COHORT: 4 previously identified W4 SAT2026 originals
from CRR1-A. Selection is POST-HOC: never describe results as blind/holdout.

Every worker writes atomic telemetry.json *before* launching Kissat, so the
parent can recover exact discovery / graph / novelty / certification / added
counts even if the entire process group is killed at the wall deadline.
All derived units and binary clauses are replayed from exact original CNF
parity blocks. Only clauses not entailed by the original binary graph are
added; if the graph check cannot complete, fail closed to zero additions.
UNSAT: native DRAT of the augmented CNF plus checked original XOR entailment.
SAT: reconstructed original CNF witness. Source CNF never overwritten.
"""
import argparse
import collections
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import time

import drnas_crr1a_shadow as a
import drnas_crr1b_active as b

ROOT=Path("crr1b2")
SOURCE=a.SOURCE
CAP=30.0
REPS=3
SHARDS=4
MODES=("kissat_plain","crr_shadow","crr_active")
PROTO="DRNAS-CRR1B2-FOCUS4-3ARMS-3REPS-30S-v1"
FOCUS_IDS=("23daec2c71ce3c1e346e6042f3dc42eb",
           "e4d1892db27b721b88e5ee7e5987649f",
           "1eea3d913d346b900252d77fc0cb25c8",
           "dc7817dfa2817916b266c1cfacd2ee66")
BUDGET=2.0
MAX_EXTRA=64
MAX_RELATIVE_GROWTH=0.015

def need(ok,msg):
    if not ok:raise RuntimeError("CRR1B2_FAIL_CLOSED "+str(msg))

def save(path,obj):
    a.save(path,obj)

def atomic(path,obj):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+".tmp")
    tmp.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
    os.replace(tmp,p)

def cases():
    allcases=a.manifest_cases()
    m={c["id"]:c for c in allcases}
    need(len(FOCUS_IDS)==len(set(FOCUS_IDS))==SHARDS,"focus case list")
    need(set(FOCUS_IDS)<=set(m),"missing frozen source")
    return [m[i] for i in FOCUS_IDS]

def make_bridge(n,clauses):
    t=time.perf_counter()
    deadline=t+BUDGET
    stats={"status":"READY","reason":"none","analysis_budget_s":BUDGET,
           "source_variables":n,"source_clauses":len(clauses),
           "complete_xor_equations":0,"short_xor_rows":0,
           "candidate_clauses":0,"original_binary_or_unit":0,
           "already_present":0,"graph_redundant":0,
           "graph_check_unavailable":0,
           "new_after_graph":0,"proofs_replayed":0,
           "added_units":0,"added_binary":0,"added":0,
           "phase_s":{}}
    extra=[]
    certs=[]
    try:
        start=time.perf_counter()
        derived,info=b.derive_exact(clauses,deadline)
        stats["phase_s"]["derive"]=round(time.perf_counter()-start,6)
        stats["complete_xor_equations"]=info["eqs"]
        stats["xor_rank"]=info["rank"]
        stats["xor_cap_hit"]=info["xor_cap"]
        if info["gf2_unsat"]:
            stats["status"]="SKIP"
            stats["reason"]="GF2_CONTRADICTION_NOT_PROOF_EXPORTED"
        else:
            eqs,rows=derived
            stats["short_xor_rows"]=len(rows)
            start=time.perf_counter()
            graph,n_binary=b.graph_from_original(clauses,deadline)
            stats["phase_s"]["graph"]=round(time.perf_counter()-start,6)
            stats["original_binary_or_unit"]=n_binary+sum(len(c)==1 for c in clauses)
            if graph is None:
                stats["status"]="SKIP"
                stats["reason"]="BINARY_GRAPH_SIZE_UNVERIFIED"
                stats["graph_check_unavailable"]=1
            else:
                start=time.perf_counter()
                existing={tuple(sorted(c)) for c in clauses if len(c)<=2}
                seen=set()
                for row in rows:
                    if time.perf_counter()>=deadline:
                        raise TimeoutError("candidate time gate")
                    vars_=tuple(row["vars"]);rhs=row["rhs"]
                    if len(vars_)==1:
                        options=[(vars_[0] if rhs else -vars_[0],)]
                    elif len(vars_)==2:
                        options=a.to_binary(vars_,rhs)
                    else:continue
                    for raw in options:
                        clause=tuple(sorted(raw))
                        stats["candidate_clauses"]+=1
                        if clause in existing or clause in seen:
                            stats["already_present"]+=1
                            continue
                        if b.graph_implies(graph,clause,deadline):
                            stats["graph_redundant"]+=1
                            continue
                        stats["new_after_graph"]+=1
                        # Addition only after complete-CNF GF2 replay.
                        a.replay(eqs,row["xor_source_indices"],set(vars_),rhs,clauses)
                        stats["proofs_replayed"]+=1
                        if len(extra)<MAX_EXTRA:
                            extra.append(clause)
                            certs.append({"clause":list(clause),
                               "vars":list(vars_),"rhs":rhs,
                               "xor_source_indices":row["xor_source_indices"]})
                            seen.add(clause)
                stats["phase_s"]["filter"]=round(time.perf_counter()-start,6)
                if len(extra)>max(1,int(MAX_RELATIVE_GROWTH*len(clauses))):
                    extra=[];certs=[]
                    stats["status"]="SKIP"
                    stats["reason"]="GROWTH_LIMIT"
                elif len(extra)>0:
                    stats["reason"]="CERTIFIED_NOVEL_SHORT_GF2"
                else:
                    stats["reason"]="NONE_SURVIVED_GRAPH_AND_PRESENT_GATE"
    except TimeoutError as ex:
        stats["status"]="BUDGET_CUTOFF"
        stats["reason"]=str(ex)
        extra=[];certs=[]
    # Replay again independently through B1's verifier. This is charged.
    if extra:
        start=time.perf_counter()
        verified=b.certify_added(clauses,certs)
        need(verified==set(extra),"independent original GF2 replay")
        stats["phase_s"]["independent_replay"]=round(time.perf_counter()-start,6)
    stats["added"]=len(extra)
    stats["added_units"]=sum(len(x)==1 for x in extra)
    stats["added_binary"]=sum(len(x)==2 for x in extra)
    stats["analysis_s"]=round(time.perf_counter()-t,6)
    return extra,certs,stats

def worker(source,mode,directory):
    started=time.perf_counter()
    d=Path(directory)
    n,original=a.parse(source)
    telemetry=None
    extra=[];cert=[]
    active=mode=="crr_active"
    if active:
        extra,cert,telemetry=make_bridge(n,original)
    elif mode=="crr_shadow":
        telemetry=a.analyze(n,original)
    need(mode in MODES,"unknown mode")
    input_path=Path(source)
    if extra:
        input_path=d/"augmented.cnf"
        with input_path.open("w") as out:
            out.write("p cnf %d %d\n"%(n,len(original)+len(extra)))
            for clause in original:
                out.write(" ".join(map(str,clause))+" 0\n")
            for clause in extra:
                out.write(" ".join(map(str,clause))+" 0\n")
        save(d/"certificates.json",cert)
    checkpoint={"stage":"SOLVER_READY","mode":mode,"source_sha256":a.sha(source),
       "solver_cnf_sha256":a.sha(input_path),
       "telemetry":telemetry,"prep_s":round(time.perf_counter()-started,6),
       "added":len(extra),"certificate_replay_complete":True,
       "augmented_cnf_path":str(input_path) if extra else None}
    atomic(d/"telemetry.json",checkpoint)
    print("CRR1B2_BRIDGE",json.dumps(checkpoint,sort_keys=True),flush=True)
    proof=d/"native.drat"
    p=subprocess.run([str(a.KISSAT.resolve()),str(input_path.resolve()),
                      str(proof.resolve())],
                      stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    answers=re.findall(r"(?m)^s (SATISFIABLE|UNSATISFIABLE)\s*$",p.stdout)
    need(len(answers)==1 and p.returncode==(10 if answers[0]=="SATISFIABLE" else 20),
         "invalid solver verdict/exit")
    native="SAT" if answers[0]=="SATISFIABLE" else "UNSAT"
    if native=="SAT":
        model={}
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                for token in line[2:].split():
                    lit=int(token)
                    if lit:
                        need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                             "inconsistent SAT literals")
                        model[abs(lit)]=lit>0
        def sat(cs):
            return all(any(model.get(abs(lit))==(lit>0) for lit in c) for c in cs)
        need(sat(original) and sat(extra),"original/augmented SAT model failed")
        save(d/"model.json",model)
    print("CRR1B2_TERMINAL",json.dumps({"verdict":native,
          "source_sha256":a.sha(source),
          "solver_cnf_sha256":a.sha(input_path)}),flush=True)

def audit_certified(original,folder,checkpoint):
    """Parent validates durable pre-solver telemetry even after timeout."""
    added=checkpoint["added"]
    if not added:
        need(checkpoint["augmented_cnf_path"] is None,"spurious augmented path")
        need(checkpoint["solver_cnf_sha256"]==checkpoint["source_sha256"],
             "input drift")
        return
    need(checkpoint["mode"]=="crr_active" and
         checkpoint["certificate_replay_complete"],"missing replay")
    augmented=folder/"augmented.cnf"
    n,orig=original
    n_aug,new=a.parse(augmented)
    need(n==n_aug and new[:len(orig)]==orig,"original clauses changed")
    cert=json.loads((folder/"certificates.json").read_text())
    verified=b.certify_added(orig,cert)
    added_actual=new[len(orig):]
    need(len(added_actual)==added==len(cert)==len(verified) and
         set(added_actual)==verified,"not an exact certified extension")
    need(a.sha(augmented)==checkpoint["solver_cnf_sha256"],
         "augmented SHA changed")

def trial(case,mode,rep,shard):
    source=SOURCE/(case["id"]+".cnf")
    need(a.sha(source)==case["sha256"],"source SHA drift")
    folder=ROOT/"raw"/str(shard)/(case["id"]+"-"+str(rep)+"-"+mode)
    folder.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    p=subprocess.Popen([sys.executable,__file__,"worker","--source",str(source),
         "--mode",mode,"--directory",str(folder)],
         stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
         text=True,start_new_session=True)
    timedout=False
    try:
        output,_=p.communicate(timeout=max(.001,CAP-(time.perf_counter()-started)))
    except subprocess.TimeoutExpired:
        timedout=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        output,_=p.communicate()
    elapsed=min(CAP,time.perf_counter()-started)
    checkpoint_file=folder/"telemetry.json"
    checkpoint=json.loads(checkpoint_file.read_text()) if checkpoint_file.is_file() else None
    reported=None
    status="TIMEOUT"
    proof_status="WALL_CAP_TIMEOUT"
    # This verification is OUTSIDE the charged wall time; solver never
    # receives extra time. Even timed out attempts retain certified telemetry.
    if checkpoint:
        need(checkpoint["stage"]=="SOLVER_READY" and
             checkpoint["source_sha256"]==case["sha256"] and
             checkpoint["mode"]==mode,"invalid durable checkpoint")
        audit_certified(a.parse(source),folder,checkpoint)
    terminal=[line for line in output.splitlines() if "CRR1B2_TERMINAL " in line]
    if not timedout and elapsed<CAP:
        need(p.returncode==0 and checkpoint is not None and len(terminal)==1,
             "worker error "+output[-2500:])
        end=json.loads(terminal[0].split("CRR1B2_TERMINAL ",1)[1])
        need(end["source_sha256"]==case["sha256"] and
             end["solver_cnf_sha256"]==checkpoint["solver_cnf_sha256"],
             "terminal provenance mismatch")
        reported=end["verdict"]
        if reported=="SAT":
            model={int(k):v for k,v in json.loads((folder/"model.json").read_text()).items()}
            _,cs=a.parse(source)
            need(all(any(model.get(abs(x))==(x>0) for x in c)
                     for c in cs),"parent SAT witness fails ORIGINAL CNF")
            status="SAT";proof_status="SAT_ORIGINAL_MODEL_VERIFIED"
        elif reported=="UNSAT":
            check_input=(folder/"augmented.cnf") if checkpoint["added"] else source
            proof=folder/"native.drat"
            if proof.exists() and proof.stat().st_size:
                try:
                    q=subprocess.run([str(a.CHECKER.resolve()),
                          str(check_input.resolve()),str(proof)],
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,timeout=150)
                    (folder/"proof_validation.log").write_text(q.stdout[-3500:])
                    if q.returncode==0 and "s VERIFIED" in q.stdout:
                        status="UNSAT"
                        proof_status="UNSAT_DRAT_AND_ORIGINAL_GF2_REPLAY_VERIFIED"
                    else:proof_status="UNSAT_UNCERTIFIED_NOT_SCORED"
                except subprocess.TimeoutExpired:
                    (folder/"proof_validation.log").write_text("PROOF_CHECK_TIMEOUT")
                    proof_status="UNSAT_PROOF_TIMEOUT_NOT_SCORED"
        else:need(False,"unexpected solver verdict")
    else:
        if checkpoint is None:
            proof_status="TIMEOUT_BEFORE_TELEMETRY"
        else:proof_status="TIMEOUT_TELEMETRY_PERSISTED"
    for name in ("native.drat","augmented.cnf","model.json","certificates.json"):
        pth=folder/name
        if pth.exists():pth.unlink()
    row={"protocol":PROTO,"id":case["id"],"sha256":case["sha256"],
         "mode":mode,"rep":rep,"shard":shard,
         "elapsed_s":round(elapsed,6),
         "par2_s":round(elapsed if status!="TIMEOUT" else 2*CAP,6),
         "status":status,"reported":reported,"proof":proof_status,
         "telemetry_persisted":checkpoint is not None,
         "prep_s":checkpoint["prep_s"] if checkpoint else None,
         "added":checkpoint["added"] if checkpoint else None,
         "bridge":checkpoint["telemetry"] if checkpoint else None}
    print("CRR1B2_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row

def selftest():
    b.selftest()
    cnf=a.fixture_xor((1,2),0)+a.fixture_xor((1,2,3),1)
    extra,cert,stats=make_bridge(3,cnf)
    need(stats["status"]=="READY" and len(extra)>0,"B2 proof fixture")
    need(b.certify_added(cnf,cert)==set(extra),"B2 independent proof replay")
    print("CRR1B2_SELFTEST_PASS",flush=True)

def prepare():
    selftest()
    cc=cases()
    need(a.KISSAT.is_file() and a.CHECKER.is_file(),"pinned binaries missing")
    for c in cc:
        need(a.sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"frozen SHA drift")
    ROOT.mkdir(exist_ok=True)
    m={"protocol":PROTO,"modes":list(MODES),"source_cohort":"W4 four post-hoc selected XOR opportunity originals",
       "blind_holdout":False,"promotion_allowed":False,
       "case_ids":list(FOCUS_IDS),"case_sha256":[c["sha256"] for c in cc],
       "source_manifest_sha256":a.sha("history/w4sources/manifest.json"),
       "source_count":SHARDS,"repetitions":REPS,"cap_s":CAP,
       "phase_budget_s":BUDGET,"max_added_clauses":MAX_EXTRA,
       "max_relative_growth":MAX_RELATIVE_GROWTH,
       "certificate":"two full replays from original complete CNF XOR blocks",
       "native_UNSAT":"independent DRAT on augmented CNF; original GF2 entailment verified",
       "SAT":"original CNF model verified",
       "telemetry":"durable atomic checkpoint before solver, also after wall timeout"}
    save(ROOT/"manifest.json",m)
    pinfiles=["research/drnas_crr1b2_telemetry.py",
      "research/drnas_crr1b_active.py","research/drnas_crr1a_shadow.py",
      ".github/workflows/drnas-crr1b2-telemetry.yml",
      "built/bin/kissat_4_0_4","checker/drat-trim",
      "history/w4sources/manifest.json","crr1b2/manifest.json"]
    save(ROOT/"pins.json",{p:a.sha(p) for p in pinfiles})
    verify()
    print("CRR1B2_PREP_PASS",a.sha(ROOT/"manifest.json"),flush=True)

def verify():
    cc=cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["case_ids"]==list(FOCUS_IDS)
         and m["case_sha256"]==[c["sha256"] for c in cc]
         and m["source_manifest_sha256"]==a.sha("history/w4sources/manifest.json"),
         "manifest invalid")
    for p,hash_ in json.loads((ROOT/"pins.json").read_text()).items():
        need(a.sha(p)==hash_,"pinned file drift "+p)
    for c in cc:
        need(a.sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"source drift")
    return cc

def shard(i):
    cc=verify()
    need(0<=i<SHARDS,"bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    c=cc[i];rows=[]
    for rep in range(REPS):
        order=list(MODES)
        random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
        for mode in order:
            rows.append(trial(c,mode,rep,i))
            save(ROOT/("shard-%d.json"%i),rows)
    need(len(rows)==REPS*len(MODES),"shard incomplete")
    print("CRR1B2_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cc=verify()
    rows=[];seen=set()
    for i,c in enumerate(cc):
        source=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(source)==REPS*len(MODES),"shard incomplete")
        for r in source:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in seen and r["sha256"]==c["sha256"]
                 and r["id"]==c["id"] and r["protocol"]==PROTO
                 and r["rep"] in range(REPS) and r["mode"] in MODES
                 and r["shard"]==i,"bad row provenance")
            seen.add(key)
            need(r["status"] in ("TIMEOUT","SAT","UNSAT"),"invalid status")
            need(abs(r["par2_s"]-
                   (2*CAP if r["status"]=="TIMEOUT" else r["elapsed_s"]))<.00002,
                 "PAR2 mismatch")
            need(r["status"]!="SAT" or r["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED",
                 "SAT witness unverified")
            need(r["status"]!="UNSAT" or
                 r["proof"]=="UNSAT_DRAT_AND_ORIGINAL_GF2_REPLAY_VERIFIED",
                 "UNSAT proof unverified")
            rows.append(r)
    expected={(c["sha256"],rep,mode) for c in cc
              for rep in range(REPS) for mode in MODES}
    need(seen==expected and len(rows)==36,"36 paired rows expected")
    stats={}
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        stats[mode]={"attempts":len(subset),
            "solved":sum(r["status"]!="TIMEOUT" for r in subset),
            "sat":sum(r["status"]=="SAT" for r in subset),
            "unsat_certified":sum(r["status"]=="UNSAT" for r in subset),
            "PAR2_s":round(sum(r["par2_s"] for r in subset),6)}
    active=[r for r in rows if r["mode"]=="crr_active"]
    counters=("complete_xor_equations","short_xor_rows","candidate_clauses",
              "already_present","graph_redundant","new_after_graph",
              "proofs_replayed","added","added_units","added_binary")
    bycase={}
    for c in cc:
        aa=[r for r in active if r["id"]==c["id"]]
        bycase[c["id"]]={"telemetry_count":sum(r["telemetry_persisted"] for r in aa),
           "reason":[r["bridge"]["reason"] if r["bridge"] else "NO_CHECKPOINT" for r in aa],
           "added":[r["added"] for r in aa],
           "phase_s":[r["bridge"]["phase_s"] if r["bridge"] else None for r in aa],
           "discovery":[{k:r["bridge"].get(k) for k in counters} if r["bridge"] else None for r in aa],
           "active_PAR2_s":round(sum(r["par2_s"] for r in aa),6),
           "plain_PAR2_s":round(sum(r["par2_s"] for r in rows
                  if r["id"]==c["id"] and r["mode"]=="kissat_plain"),6)}
    total=stats["kissat_plain"]["PAR2_s"]-stats["crr_active"]["PAR2_s"]
    report={"status":"CRR1B2_AUDIT_PASS","protocol":PROTO,
       "case_count":len(cc),"attempts":len(rows),"posthoc_development_cohort":True,
       "promotion_allowed":False,"telemetry_recorded_active":sum(r["telemetry_persisted"] for r in active),
       "active_attempts":len(active),"active_timeout_telemetry":sum(
           r["status"]=="TIMEOUT" and r["telemetry_persisted"] for r in active),
       "total_added_repeated":sum(r["added"] or 0 for r in active),
       "primary_gain_PAR2_s":round(total,6),
       "totals":stats,"by_case":bycase}
    save(ROOT/"all-trials.json",rows)
    save(ROOT/"report.json",report)
    print("CRR1B2_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","selftest","worker","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--source");p.add_argument("--mode",choices=MODES)
    p.add_argument("--directory")
    args=p.parse_args()
    if args.action=="worker":worker(args.source,args.mode,args.directory)
    elif args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
