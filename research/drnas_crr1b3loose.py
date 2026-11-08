#!/usr/bin/env python3
"""CRR1-B3L: dynamic redundancy gate with relaxed bounded XOR-only relevance.

Development-only post-hoc four-source W4 focus set. No claim of blind holdout.
Three arms: original Kissat; previous certified B2 active; B3 certified
active with extra syntactic/subsumption/dynamic-graph/cross-CNF relevance
filtering. All preprocessing included in one-CPU per-trial wall time.

B3 only ADDS clauses entailed by the original CNF. Every accepted addition
is independently reconstructed from exact complete CNF parity blocks before
a new DIMACS file is sent to native Kissat. A DRAT certificate is checked
against the exact augmented formula for any UNSAT result. SAT models are
checked on original. No unverified result counts as solved.
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
import drnas_crr1b2_telemetry as b2

ROOT=Path("crr1b3loose")
SOURCE=a.SOURCE
FOCUS_IDS=b2.FOCUS_IDS
PROTO="DRNAS-CRR1B3LOOSE-FOCUS4-4ARMS-3REPS-60S-v1"
MODES=("kissat_plain","b2_active","b3_loose8","b3_loose16")
CAP=60.0
REPS=3
SHARDS=4
FILTER_BUDGET=0.90
B3_MAX_ADDED=16
B3_MAX_GROWTH=0.01
# Scoring is structural, never influenced by solve status, timing, ID or SHA.
MIN_CROSS_CNF_TOUCHES=0

def need(ok,msg):
    if not ok:raise RuntimeError("CRR1B3LOOSE_FAIL_CLOSED "+str(msg))

def save(path,obj):a.save(path,obj)

def checkpoint(path,obj):
    b2.atomic(path,obj)

def focused_cases():
    return b2.cases()

def filter_novel(n,original,extra,certs,max_added=B3_MAX_ADDED):
    """Independently filter B2 certified clauses, returning subset of certificates.

    Syntactic duplicates and unit subsumption -> dynamic implication closure ->
    rank strong XOR structure first (cross-CNF preferred, not mandatory) ->
    fixed clause cap and growth gate. Every accepted clause remains GF2-certified.
    Updates graph with EACH accepted clause, preventing later redundant edges.
    A fallible/budget-limited graph check causes fail-closed no additions.
    """
    start=time.perf_counter();deadline=start+FILTER_BUDGET
    stats={"status":"OK","budget_s":FILTER_BUDGET,
       "input_candidates":len(extra),"normalized_dupes":0,
       "tautologies":0,"original_duplicates":0,"subsumed_by_unit":0,
       "dynamic_graph_redundant":0,"irrelevant_no_cross_CNF":0,
       "skipped_by_cap":0,"selected":0,"selected_units":0,
       "selected_binary":0,"candidate_scores":[],
       "static_nonparity_clauses":0,"phase_s":{}, "xor_support_floor":2, "weak_xor_support":0, "zero_cross_admitted":0}
    need(len(extra)==len(certs),"B2 certificate count mismatch")
    # Replay all B2 input candidates independently before any filtering.
    if extra:need(b.certify_added(original,certs)=={tuple(sorted(x)) for x in extra},
                  "B2 input GF2 certificates invalid")
    dedup=set()
    known={tuple(sorted(c)) for c in original if len(c)<=2}
    source_units={c[0] for c in original if len(c)==1}
    candidates=[]
    for c,cert in zip(extra,certs):
        norm=tuple(sorted(c))
        if len(set(norm))!=len(norm) or any(-x in norm for x in norm):
            stats["tautologies"]+=1;continue
        if norm in dedup:
            stats["normalized_dupes"]+=1;continue
        dedup.add(norm)
        if norm in known:
            stats["original_duplicates"]+=1;continue
        if len(norm)==2 and (norm[0] in source_units or norm[1] in source_units):
            stats["subsumed_by_unit"]+=1;continue
        candidates.append((norm,cert))
    t=time.perf_counter()
    equations,_,_=a.xor_blocks(original,deadline)
    # 'Non-XOR' here means outside the detected complete parity-block premises.
    parity_ids={cid for vs,rhs,ids in equations for cid in ids}
    nonparity=[c for idx,c in enumerate(original) if idx not in parity_ids]
    stats["static_nonparity_clauses"]=len(nonparity)
    xor_occs=collections.Counter()
    for ix in parity_ids:
        for lit in original[ix]:xor_occs[abs(lit)]+=1
    touches=collections.Counter()
    for i,c in enumerate(nonparity):
        if i%512==0 and time.perf_counter()>=deadline:
            stats["status"]="BUDGET_CUTOFF"
            stats["reason"]="cross-CNF scan budget"
            stats["phase_s"]["score"]=round(time.perf_counter()-t,6)
            return [],[],stats
        for v in {abs(lit) for lit in c}:touches[v]+=1
    stats["phase_s"]["score"]=round(time.perf_counter()-t,6)
    # Deterministic priority: stronger interaction with non-parity CNF first.
    ranked=[]
    for c,cert in candidates:
        score=sum(touches[abs(v)] for v in c)
        support=sum(xor_occs[abs(v)] for v in c)
        ranked.append((-score,-support,c,cert))
    ranked.sort(key=lambda x:(x[0],x[1],x[2]))
    t=time.perf_counter()
    try:
        graph,binary_count=b.graph_from_original(original,deadline)
        if graph is None:
            stats["status"]="SKIPPED"
            stats["reason"]="graph too large to prove redundancy"
            return [],[],stats
        accepted=[];accepted_cert=[];accepted_set=set()
        for negative_score,negative_support,c,cert in ranked:
            if time.perf_counter()>=deadline:
                raise TimeoutError("dynamic implication budget")
            score=-negative_score
            stats["candidate_scores"].append({"clause":list(c),"cross_touch":score,"xor_support":-negative_support})
            if -negative_support<2:
                stats["weak_xor_support"]+=1
                continue
            if score<MIN_CROSS_CNF_TOUCHES:
                stats["irrelevant_no_cross_CNF"]+=1
                continue
            if c in accepted_set:
                stats["normalized_dupes"]+=1;continue
            if len(c)==2:
                # Check AFTER all previously accepted clauses modify graph.
                if b.graph_implies(graph,c,deadline):
                    stats["dynamic_graph_redundant"]+=1
                    continue
            elif len(c)==1:
                if b.reachable(graph,-c[0],c[0],deadline):
                    stats["dynamic_graph_redundant"]+=1
                    continue
            if len(accepted)>=max_added:
                stats["skipped_by_cap"]+=1
                continue
            if score==0:stats["zero_cross_admitted"]+=1
            accepted.append(c);accepted_cert.append(cert)
            accepted_set.add(c)
            if len(c)==2:
                p,q=c;graph[-p].append(q);graph[-q].append(p)
            else:
                lit=c[0];graph[-lit].append(lit)
        if len(accepted)>max(1,int(B3_MAX_GROWTH*len(original))):
            stats["status"]="SKIPPED"
            stats["reason"]="growth limit"
            accepted=[];accepted_cert=[]
    except TimeoutError as exc:
        stats["status"]="BUDGET_CUTOFF"
        stats["reason"]=str(exc)
        accepted=[];accepted_cert=[]
    stats["phase_s"]["filter"]=round(time.perf_counter()-t,6)
    if accepted:
        need(b.certify_added(original,accepted_cert)==set(accepted),
             "selected GF2 original CNF certification failed")
    stats["selected"]=len(accepted)
    stats["selected_units"]=sum(len(c)==1 for c in accepted)
    stats["selected_binary"]=sum(len(c)==2 for c in accepted)
    stats["analysis_s"]=round(time.perf_counter()-start,6)
    return accepted,accepted_cert,stats

def selftest():
    b2.selftest()
    # Real b3 candidate from a valid original-CNF XOR reduction with
    # a distinct non-parity clause linking the XOR variable to another.
    original=a.fixture_xor((1,2),0)+a.fixture_xor((1,2,3),1)+[(3,4)]
    extra,cert,base=b2.make_bridge(4,original)
    need(extra and base["status"]=="READY","B2 algebraic input fixture")
    selected,cert_sel,stat=filter_novel(4,original,extra,cert)
    need(len(selected)>0 and stat["selected"]==len(selected),
         "B3 relevant certified unit must survive")
    need(b.certify_added(original,cert_sel)==set(selected),"B3 proof replay")
    # No external nonparity CNF touch -> bounded XOR-only mode may pass.
    pure=a.fixture_xor((1,2),0)+a.fixture_xor((1,2,3),1)
    extra,cert,_=b2.make_bridge(3,pure)
    selected,_,stat=filter_novel(3,pure,extra,cert)
    need(not selected and stat["irrelevant_no_cross_CNF"]>0,
         "B3 cross-CNF relevance filter failed")
    graph,_=b.graph_from_original([],time.perf_counter()+2)
    graph[-1].append(2);graph[-2].append(1)
    need(b.graph_implies(graph,(1,2),time.perf_counter()+2),
         "dynamic graph should contain accepted implication")
    print("CRR1B3LOOSE_SELFTEST_PASS",flush=True)

def worker(source,mode,directory):
    started=time.perf_counter()
    folder=Path(directory)
    n,original=a.parse(source)
    extra=[];cert=[]
    telemetry=None
    if mode=="b2_active":
        extra,cert,telemetry=b2.make_bridge(n,original)
    elif mode.startswith("b3_loose"):
        t=time.perf_counter()
        proposed,proposed_cert,first=b2.make_bridge(n,original)
        t_base=time.perf_counter()-t
        cap=int(mode.split("loose",1)[1])
        need(cap in (8,16),"bad relaxed cap")
        extra,cert,filtered=filter_novel(n,original,proposed,proposed_cert,max_added=cap)
        telemetry={"b2_discovery":first,"b3_redundancy":filtered,
             "b2_discovery_s":round(t_base,6),
             "selected":len(extra),
             "source_CNF_changed":False}
    need(mode in MODES,"unknown solver mode")
    input_path=Path(source)
    if extra:
        # Independent check for every accepted clause, including B2 control.
        need(b.certify_added(original,cert)==set(extra),
             "native input must be certified exact original consequence")
        input_path=folder/"augmented.cnf"
        with input_path.open("w") as f:
            f.write("p cnf %d %d\n"%(n,len(original)+len(extra)))
            for c in original:
                f.write(" ".join(map(str,c))+" 0\n")
            for c in extra:
                f.write(" ".join(map(str,c))+" 0\n")
        save(folder/"certificates.json",cert)
    snapshot={"stage":"SOLVER_READY","mode":mode,"source_sha256":a.sha(source),
      "solver_cnf_sha256":a.sha(input_path),"telemetry":telemetry,
      "prep_s":round(time.perf_counter()-started,6),
      "added":len(extra),"augmented":bool(extra),
      "proof_replay_completed":True}
    checkpoint(folder/"telemetry.json",snapshot)
    print("CRR1B3_READY",json.dumps(snapshot,sort_keys=True),flush=True)
    # Request statistics for normal completions; timeout statistics may be
    # unavailable and are explicitly NOT inferred.
    proof=(folder/"native.drat").resolve()
    args=[str(a.KISSAT.resolve()),"--statistics",str(input_path.resolve()),str(proof)]
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    (folder/"native.log").write_text(p.stdout[-12000:])
    matches=re.findall(r"(?m)^s (SATISFIABLE|UNSATISFIABLE)\s*$",p.stdout)
    need(len(matches)==1 and p.returncode==(10 if matches[0]=="SATISFIABLE" else 20),
         "solver exit/verdict or --statistics flag failed")
    native="SAT" if matches[0]=="SATISFIABLE" else "UNSAT"
    if native=="SAT":
        model={}
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                for raw in line[2:].split():
                    lit=int(raw)
                    if lit:
                        need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                             "conflicting SAT witness values")
                        model[abs(lit)]=lit>0
        def good(cs):
            return all(any(model.get(abs(l))==(l>0) for l in c) for c in cs)
        need(good(original) and good(extra),"native SAT model fails original")
        save(folder/"model.json",model)
    print("CRR1B3_TERMINAL",json.dumps({"status":native,
       "source_sha256":a.sha(source),"solver_cnf_sha256":a.sha(input_path)}),
       flush=True)

def certify_input(source,folder,snapshot):
    need(snapshot["source_sha256"]==a.sha(source),"original input SHA drift")
    added=snapshot["added"]
    if not added:
        need(not snapshot["augmented"] and
             snapshot["solver_cnf_sha256"]==a.sha(source),
             "phantom CNF mutation")
        return source
    need((snapshot["mode"]=="b2_active" or snapshot["mode"].startswith("b3_loose")) and
         snapshot["proof_replay_completed"],"no parent replay")
    augmented=folder/"augmented.cnf"
    n,original=a.parse(source)
    new_n,combined=a.parse(augmented)
    cert=json.loads((folder/"certificates.json").read_text())
    checked=b.certify_added(original,cert)
    need(new_n==n and combined[:len(original)]==original and
         len(combined)==len(original)+added and len(checked)==added and
         set(combined[len(original):])==checked,"bad exact CNF extension")
    need(a.sha(augmented)==snapshot["solver_cnf_sha256"],
         "native augmented SHA drift")
    return augmented

def trial(c,mode,rep,shard):
    source=SOURCE/(c["id"]+".cnf")
    need(a.sha(source)==c["sha256"],"source SHA changed")
    folder=ROOT/"raw"/str(shard)/(c["id"]+"-"+str(rep)+"-"+mode)
    folder.mkdir(parents=True,exist_ok=True)
    t=time.perf_counter()
    p=subprocess.Popen([sys.executable,__file__,"worker","--source",str(source),
        "--mode",mode,"--directory",str(folder)],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        text=True,start_new_session=True)
    timedout=False
    try:
        output,_=p.communicate(timeout=max(.001,CAP-(time.perf_counter()-t)))
    except subprocess.TimeoutExpired:
        timedout=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        output,_=p.communicate()
    elapsed=min(CAP,time.perf_counter()-t)
    path=folder/"telemetry.json"
    snap=json.loads(path.read_text()) if path.is_file() else None
    status="TIMEOUT";proof_status="WALL_CAP_TIMEOUT"
    reported=None;native_metrics=None
    if snap:
        need(snap["stage"]=="SOLVER_READY" and snap["mode"]==mode
             and snap["source_sha256"]==c["sha256"],"telemetry is not valid")
        native_input=certify_input(source,folder,snap)
    else:native_input=source
    end=[ln.split("CRR1B3_TERMINAL ",1)[1] for ln in output.splitlines()
         if "CRR1B3_TERMINAL " in ln]
    if not timedout and elapsed<CAP:
        need(p.returncode==0 and snap is not None and len(end)==1,
             "worker failure: "+output[-2200:])
        x=json.loads(end[0]);reported=x["status"]
        need(x["source_sha256"]==c["sha256"] and
             x["solver_cnf_sha256"]==snap["solver_cnf_sha256"],
             "native terminal SHA drift")
        stdout=(folder/"native.log").read_text()
        # Stats are descriptive: only populated for normal terminal attempts.
        for field in ("decisions","conflicts","propagations","restarts"):
            lines=[ln for ln in stdout.splitlines()
                   if re.search(r"\b"+field+r"\b",ln,re.I)]
            if lines:
                if native_metrics is None:native_metrics={}
                native_metrics[field]=lines[-1][-180:]
        if reported=="SAT":
            model={int(k):v for k,v in json.loads((folder/"model.json").read_text()).items()}
            _,original=a.parse(source)
            need(all(any(model.get(abs(v))==(v>0) for v in clause)
                     for clause in original),"parent original SAT witness fails")
            status="SAT";proof_status="SAT_ORIGINAL_MODEL_VERIFIED"
        elif reported=="UNSAT":
            proof=folder/"native.drat"
            if proof.is_file() and proof.stat().st_size:
                try:
                    check=subprocess.run([str(a.CHECKER.resolve()),str(native_input.resolve()),
                          str(proof)],stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,text=True,timeout=180)
                    (folder/"proof_validation.log").write_text(check.stdout[-4000:])
                    if check.returncode==0 and "s VERIFIED" in check.stdout:
                        status="UNSAT";proof_status="UNSAT_DRAT_PLUS_ORIGINAL_XOR_VERIFIED"
                    else:proof_status="UNSAT_PROOF_INVALID_NOT_SCORED"
                except subprocess.TimeoutExpired:
                    proof_status="UNSAT_PROOF_TIMEOUT_NOT_SCORED"
        else:need(False,"invalid native verdict")
    elif snap is not None:
        proof_status="TIMEOUT_TELEMETRY_CAPTURED"
    else:proof_status="TIMEOUT_BEFORE_TELEMETRY"
    for file in ("native.drat","augmented.cnf","certificates.json","model.json","native.log"):
        f=folder/file
        if f.exists():f.unlink()
    row={"protocol":PROTO,"id":c["id"],"sha256":c["sha256"],
         "mode":mode,"rep":rep,"shard":shard,
         "status":status,"reported":reported,"proof":proof_status,
         "elapsed_s":round(elapsed,6),
         "par2_s":round(elapsed if status!="TIMEOUT" else 2*CAP,6),
         "telemetry_persisted":snap is not None,
         "added":snap["added"] if snap else None,
         "prep_s":snap["prep_s"] if snap else None,
         "bridge":snap["telemetry"] if snap else None,
         "native_stats":native_metrics}
    print("CRR1B3LOOSE_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row

def prepare():
    selftest()
    cc=focused_cases()
    need(a.KISSAT.is_file() and a.CHECKER.is_file(),"solver/checker missing")
    for c in cc:need(a.sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"source SHA drift")
    ROOT.mkdir(exist_ok=True)
    manifest={"protocol":PROTO,"modes":list(MODES),"case_ids":list(FOCUS_IDS),
        "case_sha256":[c["sha256"] for c in cc],
        "parent_source_manifest_sha256":a.sha("history/w4sources/manifest.json"),
        "source_set_posthoc_from_CRR1A":True,
        "blind_holdout":False,"promotion_allowed":False,
        "analysis_rule":"exact GF2 CNF verified proposals only; B3 graph updated after each accepted clause",
        "selection":"cross-CNF preferential ranking, then XOR occurrence support, never outcomes",
        "duplicate_filter":"normalized, unit subsumption, dynamic implication closure, finite cap",
        "min_cross_CNF_touches":MIN_CROSS_CNF_TOUCHES,
        "max_added":B3_MAX_ADDED,"max_growth":B3_MAX_GROWTH,
        "max_added_by_arm":{"b3_loose8":8,"b3_loose16":16},
        "xor_support_floor":2,"source_relevance_threshold_relaxed":True,
        "cap_s":CAP,"reps":REPS,"shards":SHARDS,
        "native_stats":"--statistics; on normal termination only",
        "proofs":"original SAT model; native DRAT of exact appended CNF and GF2 replay"}
    save(ROOT/"manifest.json",manifest)
    pinned=["research/drnas_crr1b3loose.py",
        "research/drnas_crr1b2_telemetry.py",
        "research/drnas_crr1b_active.py",
        "research/drnas_crr1a_shadow.py",
        ".github/workflows/drnas-crr1b3loose.yml",
        "built/bin/kissat_4_0_4","checker/drat-trim",
        "history/w4sources/manifest.json","crr1b3loose/manifest.json"]
    save(ROOT/"pins.json",{p:a.sha(p) for p in pinned})
    verify()
    print("CRR1B3LOOSE_PREP_PASS",a.sha(ROOT/"manifest.json"),flush=True)

def selftest():
    filter_test=a.fixture_xor((1,2),0)
    need(filter_test,"underlying test")
    b2.selftest()
    original=a.fixture_xor((1,2),0)+a.fixture_xor((1,2,3),1)+[(3,4)]
    extra,cert,meta=b2.make_bridge(4,original)
    need(extra and meta["status"]=="READY","B3 relevant GF2 fixture")
    chosen,cc,stat=filter_novel(4,original,extra,cert)
    need(chosen and b.certify_added(original,cc)==set(chosen),
         "B3 certified relevant fixture not kept")
    pure=a.fixture_xor((1,2),0)+a.fixture_xor((1,2,3),1)
    extra,cert,_=b2.make_bridge(3,pure)
    chosen,_,stat=filter_novel(3,pure,extra,cert)
    need(chosen and stat["zero_cross_admitted"]>0,
         "relaxed filter must admit bounded XOR-supported candidates")
    print("CRR1B3_SELFTEST_PASS",flush=True)

def verify():
    cc=focused_cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["modes"]==list(MODES)
         and m["case_ids"]==list(FOCUS_IDS)
         and m["case_sha256"]==[c["sha256"] for c in cc]
         and m["parent_source_manifest_sha256"]==a.sha("history/w4sources/manifest.json"),
         "manifest changed")
    for name,h in json.loads((ROOT/"pins.json").read_text()).items():
        need(a.sha(name)==h,"file pin drift "+name)
    for c in cc:
        need(a.sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"source SHA drift")
    return cc

def shard(i):
    cc=verify()
    need(0<=i<SHARDS,"bad shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    c=cc[i];rows=[]
    for rep in range(REPS):
        modes=list(MODES)
        random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
        for mode in modes:
            rows.append(trial(c,mode,rep,i))
            save(ROOT/("shard-%d.json"%i),rows)
    need(len(rows)==REPS*len(MODES),"shard incomplete")
    print("CRR1B3LOOSE_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cc=verify()
    rows=[];seen=set()
    for i,c in enumerate(cc):
        subset=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(subset)==REPS*len(MODES),"missing shard trials")
        for row in subset:
            key=(row["sha256"],row["rep"],row["mode"])
            need(key not in seen and row["sha256"]==c["sha256"] and
                 row["id"]==c["id"] and row["protocol"]==PROTO and
                 row["shard"]==i and row["rep"] in range(REPS) and
                 row["mode"] in MODES,"row provenance mismatch")
            seen.add(key)
            need(row["status"] in ("SAT","UNSAT","TIMEOUT") and
                 abs(row["par2_s"]-(2*CAP if row["status"]=="TIMEOUT"
                 else row["elapsed_s"]))<.00002,"invalid PAR2")
            need(row["status"]!="SAT" or
                 row["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED","unchecked SAT")
            need(row["status"]!="UNSAT" or
                 row["proof"]=="UNSAT_DRAT_PLUS_ORIGINAL_XOR_VERIFIED","unchecked UNSAT")
            rows.append(row)
    expected={(c["sha256"],rep,mode) for c in cc
              for rep in range(REPS) for mode in MODES}
    need(seen==expected and len(rows)==48,"missing full paired coverage")
    for c in cc:
        answers={r["status"] for r in rows if r["sha256"]==c["sha256"]
                 and r["status"]!="TIMEOUT"}
        need(len(answers)<=1,"contradictory verified SAT answers")
    metrics={}
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        metrics[mode]={"attempts":len(subset),
                       "solved":sum(r["status"]!="TIMEOUT" for r in subset),
                       "SAT":sum(r["status"]=="SAT" for r in subset),
                       "UNSAT_verified":sum(r["status"]=="UNSAT" for r in subset),
                       "PAR2_s":round(sum(r["par2_s"] for r in subset),6),
                       "added_total_repeated":sum(r["added"] or 0 for r in subset),
                       "timeout_telemetry":sum(r["telemetry_persisted"] and
                           r["status"]=="TIMEOUT" for r in subset)}
    per={}
    for c in cc:
        per[c["id"]]={}
        for mode in MODES:
            subset=[r for r in rows if r["id"]==c["id"] and r["mode"]==mode]
            per[c["id"]][mode]={
                "PAR2_s":round(sum(r["par2_s"] for r in subset),6),
                "added":[r["added"] for r in subset],
                "prep_s":[r["prep_s"] for r in subset],
                "reasons":[r["bridge"].get("b3_redundancy",{}).get("status")
                           if r["bridge"] and mode.startswith("b3_loose") else None
                           for r in subset],
                "b3_redundancy":[r["bridge"].get("b3_redundancy",{})
                          if r["bridge"] and mode=="b3_filtered" else None
                          for r in subset]}
    report={"status":"CRR1B3LOOSE_AUDIT_PASS",
        "protocol":PROTO,"attempts":len(rows),"formulas":len(cc),
        "posthoc_development":True,"promotion_allowed":False,
        "primary_gain_8_PAR2_s":round(metrics["kissat_plain"]["PAR2_s"]-
               metrics["b3_loose8"]["PAR2_s"],6),
        "primary_gain_16_PAR2_s":round(metrics["kissat_plain"]["PAR2_s"]-
               metrics["b3_loose16"]["PAR2_s"],6),
        "loose16_vs_b2_gain_PAR2_s":round(metrics["b2_active"]["PAR2_s"]-
               metrics["b3_loose16"]["PAR2_s"],6),
        "metrics":metrics,"by_formula":per}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",rows)
    print("CRR1B3LOOSE_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("prepare","selftest","worker","shard","audit"))
    p.add_argument("--source")
    p.add_argument("--mode",choices=MODES)
    p.add_argument("--directory")
    p.add_argument("--shard",type=int,default=0)
    z=p.parse_args()
    if z.action=="worker":worker(z.source,z.mode,z.directory)
    elif z.action=="shard":shard(z.shard)
    else:globals()[z.action]()
