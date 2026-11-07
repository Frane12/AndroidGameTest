#!/usr/bin/env python3
"""R193 certified Gauss-to-CryptoMiniSat, on original frozen CNFs.

Known R189/R192 development cohort only: 25 external originals + 13 generated
controls, 2 repeats, 12s end-to-end wall cap, 7 arms, 532 paired measurements.
All added constraints are logical consequences of ORIGINAL CNF, with source XOR
traces and local resolution proof replay. No original clauses may be deleted.
SAT witnesses checked against original CNF; non-GF2 UNSAT not independently
LRAT-certified. This is ONE-SHOT preprocessing, not live CMS CDCL callbacks.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import random
import re
import statistics
import subprocess
import time
import itertools
import tempfile

import r192_gauss_first_cms_hybrid as old
import r189_short_inference as deriv
import r188_feedback_benchmark as gf_src

ROOT=pathlib.Path("r193")
SOURCE=pathlib.Path("r189/frozen")
PROTO="DRNAS-R193-CERTIFIED-GF2-CMS-ONE-SHOT-7ARM-v1"
REPS=2
SHARDS=12
CAP=12.0
MODES=("cms_default","cms_forced","r192_r28_cms",
       "r193_units","r193_short4","r193_hybrid4","r193_hybrid_shadow")
DERIVE={"r193_short4":"short4","r193_hybrid4":"hybrid4",
        "r193_hybrid_shadow":"hybrid_shadow"}

def need(ok,msg):
    if not ok:raise RuntimeError("R193_FAIL_CLOSED "+str(msg))

def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def save(p, data):
    f=pathlib.Path(p)
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")

def verify():
    cases=old.verify()
    need(len(cases)==38 and len(set(x["sha256"] for x in cases))==38,
         "not 38 unique frozen cases")
    need(sha(SOURCE/"manifest.json")==old.SOURCE_SHA,"original source manifest changed")
    pins=json.loads((ROOT/"pins.json").read_text())
    for p,digest in pins.items():
        need(sha(p)==digest,"binary/source/script pin drift "+p)
    return cases

def timed_command(cmd, started):
    remaining=CAP-(time.perf_counter()-started)
    if remaining<0.08:
        return "TIMEOUT",{},None,"",124
    try:
        p=subprocess.run([str(a) for a in cmd],capture_output=True,text=True,
                         timeout=remaining,check=False,errors="replace")
    except subprocess.TimeoutExpired:
        return "TIMEOUT",{},None,"",124
    raw=p.stdout+"\n"+p.stderr
    status,model,route=old.inspect(raw,p.returncode)
    return status,model,route,raw,p.returncode

def prefix_unchanged(cnf_path,original_n,original):
    n,clauses=gf_src.gf.dimacs(cnf_path)
    need(n==original_n and clauses[:len(original)]==original,
         "modified or lost ORIGINAL CNF clause in augmented file")
    return len(clauses)-len(original)

def classifier(path,started):
    cmd=["r190_cms_mixed/r28",str(path.resolve()),str(pathlib.Path("r192/cms_single.sh").resolve()),"--classify-only"]
    remaining=CAP-(time.perf_counter()-started)
    if remaining<0.08:return "TIMEOUT",None
    try:
        p=subprocess.run([str(pathlib.Path(cmd[0]).resolve()),*cmd[1:]],
                         capture_output=True,text=True,timeout=remaining)
    except subprocess.TimeoutExpired:
        return "TIMEOUT",None
    need(p.returncode==0,"R28 classify failed, rc="+str(p.returncode)+" "+p.stderr[-300:])
    m=re.search(r"^c R28_ROUTE ([^\n]+)",p.stdout,re.M)
    need(m is not None,"missing R28 classifier route")
    return "CLASSIFIED",m.group(1)

def certified_preprocess(source,mode,rep,idx,started):
    stats={"original_source_sha256":sha(source),"xor_rows":0,"covered_clauses":0,
           "residual_clauses":0,"gf2_units":0,"added_short_clauses":0,
           "added_bridge_clauses":0,"added_total_clauses":0,"preprocess_s":0.0,
           "augmented_sha256":None,"source_GF2_contradiction":False,
           "certification":"source_xor_traces_replayed"}
    begin=time.perf_counter()
    n,clauses=gf_src.gf.dimacs(source)
    rows,covered=gf_src.ext.xor_source(clauses)
    stats.update(xor_rows=len(rows),covered_clauses=len(covered),
                 residual_clauses=len(clauses)-len(covered))
    if time.perf_counter()-started>CAP-0.08:
        return source,stats,"TIMEOUT"
    if not rows:
        stats["preprocess_s"]=round(time.perf_counter()-begin,6)
        return source,stats,None
    # Safeguard against uncontrolled cost of dense Python GF2 on large matrices.
    if len(rows)>3000:
        stats["certification"]="abstain_gt_3000_xor_rows"
        stats["preprocess_s"]=round(time.perf_counter()-begin,6)
        return source,stats,None
    gauss=gf_src.gf.gaussian(rows)
    if gauss["conflict"]:
        gf_src.gf.check_trace(rows,0,1,gauss["conflict_trace"])
        stats["source_GF2_contradiction"]=True
        stats["preprocess_s"]=round(time.perf_counter()-begin,6)
        return source,stats,"UNSAT"
    units=[]
    for var,(rhs,trace) in sorted(gauss["units"].items()):
        gf_src.gf.check_trace(rows,1<<(var-1),rhs,trace)
        units.append(var if rhs else -var)
    extra=[]; proof=[]; report={}
    if mode in DERIVE and time.perf_counter()-started<CAP-0.12:
        extra,report,proof=deriv.prepare(clauses,rows,covered,DERIVE[mode])
        # Every generated clause is replay-certified inside deriv.prepare().
    if mode=="r193_hybrid_shadow":
        extra=[]  # fully charge prep but do not inject generated non-unit clauses
    stats["gf2_units"]=len(units)
    stats["added_short_clauses"]=report.get("short_clauses",0) if extra else 0
    stats["added_bridge_clauses"]=report.get("bridge_resolutions",0) if extra else 0
    stats["derived_candidates"]=report.get("new_clauses",0)
    stats["prep_pair_exams"]=report.get("xor_pair_examined",0)
    if time.perf_counter()-started>CAP-0.12:
        stats["preprocess_s"]=round(time.perf_counter()-begin,6)
        return source,stats,"TIMEOUT"
    if not units and not extra:
        stats["preprocess_s"]=round(time.perf_counter()-begin,6)
        return source,stats,None
    out=ROOT/"augmented"/f"shard-{idx}"/mode/f"{source.stem}-{rep}.cnf"
    deriv.write_augmented(out,n,clauses,units,extra)
    count=prefix_unchanged(out,n,clauses)
    need(count==len(units)+len(extra),"derived file clause-count mismatch")
    stats["added_total_clauses"]=count
    stats["augmented_sha256"]=sha(out)
    stats["preprocess_s"]=round(time.perf_counter()-begin,6)
    if rep==0:
        save(ROOT/"proofs"/f"shard-{idx}"/f"{source.stem}-{mode}.json",{
            "original_sha256":sha(source),
            "augmented_sha256":stats["augmented_sha256"],
            "unit_literals":units,
            "unit_source_traces_replayed":True,
            "derived_clause_proofs":proof if extra else [],
            "derived_resolution_traces_replayed":True,
            "stats":stats})
    return out,stats,None

def trial(case,mode,rep,idx):
    source=SOURCE/(case["id"]+".cnf")
    need(sha(source)==case["sha256"],"original source changed mid-trial")
    started=time.perf_counter()
    status=None;model={};route=None;raw="";rc=None
    features={"proof":"NO_INDEPENDENT_UNSAT_LRAT","route":None,
              "original_source_sha256":case["sha256"]}
    if mode=="cms_default":
        status,model,route,raw,rc=timed_command(old.command("cms_default",source),started)
    elif mode=="cms_forced":
        status,model,route,raw,rc=timed_command(old.command("cms_forced_gauss",source),started)
    elif mode=="r192_r28_cms":
        status,model,route,raw,rc=timed_command(old.command("r28_cms_gauss_first",source),started)
    else:
        classify,route=classifier(source,started)
        features["r28_classified_route"]=route
        if classify=="TIMEOUT":status="TIMEOUT"
        elif route.startswith(("certified_xor_contradiction","certified_pure_xor_sat")):
            # Retain R28's certified mathematical SAT/UNSAT fast path, with full original witness.
            status,model,_,raw,rc=timed_command(old.command("r28_cms_gauss_first",source),started)
            features["route"]="r28_exact"
        else:
            features["route"]="cms_augmented_or_original"
            work,meta,conclusion=certified_preprocess(source,mode,rep,idx,started)
            features.update(meta)
            if conclusion=="UNSAT":
                status="UNSAT"
                features["proof"]="SOURCE_GF2_CONTRADICTION_REPLAYED"
            elif conclusion=="TIMEOUT":
                status="TIMEOUT"
            else:
                status,model,_,raw,rc=timed_command(old.command("cms_default",work),started)
    elapsed=time.perf_counter()-started
    if elapsed>=CAP:
        status="TIMEOUT"
        features["proof"]="CAP_TIMEOUT"
    if status=="SAT":
        _,clauses=gf_src.gf.dimacs(source)
        gf_src.gf.sat_check(clauses,model)
        features["proof"]="SAT_WITNESS_ORIGINAL_CNF_VERIFIED"
    elif status=="UNSAT":
        route_text=route or features.get("r28_classified_route") or ""
        if route_text.startswith("certified_xor_contradiction"):
            features["proof"]="R28_CERTIFIED_SOURCE_GF2_CONTRADICTION"
    elif status=="TIMEOUT":features["proof"]="CAP_TIMEOUT"
    need(status in ("SAT","UNSAT","TIMEOUT"),"unexpected status "+str(status))
    if case["expected"]!="UNKNOWN" and status!="TIMEOUT":
        need(status==case["expected"],"mismatch with known SAT/UNSAT truth")
    row={"id":case["id"],"sha256":case["sha256"],"real":case["real"],
         "family":case["family"],"mode":mode,"rep":rep,
         "elapsed_s":round(min(CAP,elapsed),6),"status":status,
         "par2_s":round(2*CAP if status=="TIMEOUT" else min(CAP,elapsed),6),
         **features}
    print("R193_TRIAL",json.dumps({k:row.get(k) for k in (
          "id","mode","rep","status","elapsed_s","route","xor_rows",
          "gf2_units","added_total_clauses","preprocess_s")},sort_keys=True),flush=True)
    return row

def shard(idx):
    cases=verify()
    need(0<=idx<SHARDS,"bad shard")
    records=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            methods=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(methods)
            for mode in methods:
                r=trial(c,mode,rep,idx)
                records.append(r)
                save(ROOT/f"shard-{idx}.json",records)
    need(len(records)==len(cases[idx::SHARDS])*REPS*len(MODES),"partial shard")
    print("R193_SHARD_PASS",idx,len(records),flush=True)

def audit():
    cases=verify()
    records=[]; seen=set()
    byid={c["sha256"]:c for c in cases}
    for idx in range(SHARDS):
        p=ROOT/f"shard-{idx}.json"
        need(p.is_file(),"missing shard "+str(idx))
        r=json.loads(p.read_text())
        need(len(r)==len(cases[idx::SHARDS])*REPS*len(MODES),
             "shard count failure")
        for x in r:
            need(x["sha256"] in byid and x["id"]==byid[x["sha256"]]["id"],
                 "SHA/ID mismatch")
            key=(x["sha256"],x["rep"],x["mode"])
            need(key not in seen,"duplicate paired case");seen.add(key)
            need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
            need(abs(x["par2_s"]-(2*CAP if x["status"]=="TIMEOUT" else x["elapsed_s"]))<.00001,
                 "PAR2 drift")
        records.extend(r)
    need(len(records)==38*REPS*len(MODES)==532,"must have 532 paired attempts")
    for c in cases:
        for rep in range(REPS):
            a=[x for x in records if x["sha256"]==c["sha256"] and x["rep"]==rep]
            need({x["mode"] for x in a}==set(MODES),"unpaired modes")
            ans={x["status"] for x in a if x["status"]!="TIMEOUT"}
            need(len(ans)<=1,"same CNF produced contradictory SAT/UNSAT")
    groups={
       "all":cases,
       "external_original_25":[c for c in cases if c["real"]],
       "synthetic_controls_13":[c for c in cases if not c["real"]]}
    for fam in sorted({c["family"] for c in cases if c["real"]}):
        groups["external:"+fam]=[c for c in cases if c["real"] and c["family"]==fam]
    totals={}
    for cohort,selected in groups.items():
        allowed={c["sha256"] for c in selected}
        metrics={}
        for mode in MODES:
            sample=[r for r in records if r["sha256"] in allowed and r["mode"]==mode]
            solved=[r for r in sample if r["status"]!="TIMEOUT"]
            metrics[mode]={
               "attempts":len(sample),"solved":len(solved),
               "SAT":sum(r["status"]=="SAT" for r in sample),
               "UNSAT":sum(r["status"]=="UNSAT" for r in sample),
               "timeouts":sum(r["status"]=="TIMEOUT" for r in sample),
               "PAR2_s":round(sum(r["par2_s"] for r in sample),6),
               "median_s_solved":round(statistics.median(
                     r["elapsed_s"] for r in solved),6) if solved else None,
               "gf2_units_injected":sum(r.get("gf2_units",0) for r in sample),
               "extra_clauses_injected":sum(
                  r.get("added_total_clauses",0)-r.get("gf2_units",0) for r in sample),
               "augmented_inputs":sum(bool(r.get("augmented_sha256")) for r in sample),
               "preprocess_s":round(sum(r.get("preprocess_s",0) for r in sample),6),
            }
        totals[cohort]={"cases":len(selected),"modes":metrics}
    report={
       "protocol":PROTO,"status":"R193_SOURCE_CERTIFIED_AUDIT_PASS",
       "source_manifest_sha256":old.SOURCE_SHA,
       "attempts":len(records),"repetitions":REPS,"wall_cap_s":CAP,
       "known_external_cases_not_blind":True,
       "original_clause_retention_verified":True,
       "derived_GF2_and_resolution_proofs_replayed":True,
       "SAT_models_verified_on_original":True,
       "CDCL_UNSAT_without_source_GF2_not_independently_LRAT":True,
       "one_shot_preprocessing_not_live_CMS_callback":True,
       "groups":totals,
    }
    save(ROOT/"report.json",report);save(ROOT/"all-trials.json",records)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS R193 certified GF2 → CryptoMiniSat, frozen mixed sources\n\n"
                "Original 25 reused external CNF + 13 calibrated synthetic controls, "
                "not blind. Same original SHA, two randomized paired repetitions, "
                "12s end-to-end cap, 7 configurations, 532 trials. "
                "SAT witness audit on original. Source XOR traces and XOR-CNF "
                "resolution proofs replayed; no independent LRAT for generic CDCL UNSAT.\n\n")
        f.write("| Cohort | Mode | Solved | PAR2 s | GF2 units | Added clauses | Prep s |\n"
                "|---|---|---:|---:|---:|---:|---:|\n")
        for cohort in ("external_original_25","synthetic_controls_13","all"):
            for mode,s in totals[cohort]["modes"].items():
                f.write(f"| {cohort} | {mode} | {s['solved']}/{s['attempts']} "
                        f"| {s['PAR2_s']} | {s['gf2_units_injected']} "
                        f"| {s['extra_clauses_injected']} | {s['preprocess_s']} |\n")
        f.write("\nCompare units vs hybrid_shadow for preprocessing cost, "
                "hybrid4 vs hybrid_shadow for causal value of certified short clauses. "
                "Do not promote based on these reused sources alone.\n")
    print("R193_FINAL",json.dumps({k:totals[k] for k in (
       "all","external_original_25","synthetic_controls_13")},sort_keys=True),flush=True)

def smoke():
    verify()
    deriv.selftest()
    with tempfile.TemporaryDirectory() as tmp:
        path=pathlib.Path(tmp)/"simple.cnf"
        path.write_text("p cnf 3 2\n1 0\n-1 2 0\n")
        for mode in ("cms_default","cms_forced","r192_r28_cms"):
            cmd=old.command({"r192_r28_cms":"r28_cms_gauss_first"}.get(mode,
                   {"cms_default":"cms_default","cms_forced":"cms_forced_gauss"}[mode] if mode!="r192_r28_cms" else ""),path)
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
            status,model,_=old.inspect(p.stdout+"\n"+p.stderr,p.returncode)
            need(status=="SAT" and model.get(1) and model.get(2),
                 "smoke base solver failed")
        # Deliberately mixed XOR3 + residual, verify every generated clause
        # is a logical consequence under all assignments for small source.
        clauses=[]
        for vs in ((1,2,3),(2,3,4)):
            clauses.extend(deriv.masks_to_clauses(vs,0))
        clauses.append((1,5))
        _,rows=5,0
        rows,covered=gf_src.ext.xor_source(clauses)
        for mode in ("short4","hybrid4"):
            extra,stats,proof=deriv.prepare(clauses,rows,covered,mode)
            need(bool(extra),"expected derived clauses in selftest")
            for bits in itertools.product((False,True),repeat=5):
                def sat(cl):
                    return any(bits[abs(l)-1]==(l>0) for l in cl)
                if all(sat(c) for c in clauses):
                    need(all(sat(c) for c in extra),"derived CNF clause unsound")
    print("R193_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("smoke","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    if args.action=="smoke":smoke()
    elif args.action=="shard":shard(args.shard)
    else:audit()
