#!/usr/bin/env python3
"""DRNAS Medical R7-A: original G/F dual MILP, stronger logically equivalent
mixed discrete/continuous coupling formulations. Eliminates R6's candidate-
by-candidate FBA architecture in every arm.

This is a research experiment reusing upstream gMCSpy's source, published
G/F matrices, solver, and enumerator, not yet a native DRNAS SAT/PB
implementation and NOT a novel therapeutic discovery. The reformulation
options are already available in gMCSpy's pinned upstream API. This experiment
compares them fairly and determines whether SAT/PB integration is worthwhile.

Biological truth: R6 independently audited BiGG e_coli_core 48/64 gene
cohorts, exactly all 1-3 knockouts, and COBRA gene-vs-reaction FBA agreement.
Every R7 intervention family must match the independently frozen R6 truth.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib
import json
import pathlib
import random
import statistics
import subprocess
import sys
import time
import warnings

from gmispy_r6_specialist import freeze_model, SOURCE_SHA, ORIGINAL_GMCSPY_COMMIT

ROOT=pathlib.Path("medical-results/r7")
REPS=3
MODES=("published_staged_lazy","dual_on_linear",
       "dual_on_linear_cardinality","dual_compact")
PROTOCOL="DRNAS-MEDICAL-R7-GF-DUAL-REFORMULATIONS-20261106-v1"
EXPECTED_REFERENCE={48:18472,64:43744}
EXPECTED_MINIMAL={48:25,64:70}
MAX_K=3
CAP=120.

def need(cond,message):
    if not cond:raise RuntimeError("R7_FAIL_CLOSED "+str(message))

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,item):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(item,indent=2,sort_keys=True)+"\n")

def normalize(solutions,genes):
    pool=set(genes);seen=set()
    for entry in solutions:
        item=frozenset(map(str,entry))
        need(item and item.issubset(pool) and len(item)<=MAX_K,
             "invalid gene intervention")
        need(item not in seen,"duplicate gene intervention")
        seen.add(item)
    return seen

def reference_check(reference,cohort,genes):
    need(reference["cohort"]==cohort and reference["source_model_sha256"]==SOURCE_SHA,
         "R6 model/cohort drift")
    need(reference["genes"]==genes,"R6 gene order drift")
    exhaustive=reference["exhaustive"]
    need(exhaustive["candidate_KO_sets"]==EXPECTED_REFERENCE[cohort] and
         exhaustive["gene_and_reaction_FBA_calls"]==2*EXPECTED_REFERENCE[cohort] and
         exhaustive["monotone_checked"]==EXPECTED_REFERENCE[cohort],
         "R6 exhaustive FBA certificate missing")
    truth=normalize(exhaustive["minimal_solutions"],genes)
    need(len(truth)==EXPECTED_MINIMAL[cohort],"R6 minimal intervention count drift")
    source_arms=[x for x in reference["repetitions"]
                 if x["method"]=="published_gMCSpy_staged_lazy"]
    need(len(source_arms)==REPS and all(x["all_solutions_verified"] for x in source_arms),
         "R6 upstream comparator certificate missing")
    for arm in source_arms:need(normalize(arm["solutions"],genes)==truth,
                              "R6 original specialist solution-set drift")
    return truth

def call_gmcspy(mode,model,genes,cap):
    """One unchanged published enumerator; patched only dual formulation options.
    All modes have one MILP dual model, no LP oracle loop over gene combinations.
    """
    need(mode in MODES,"unknown formulation")
    module=importlib.import_module("gMCSpy.calculateGMCS")
    original=module.buildDictionaryMCSGeneProblem
    config={
       "published_staged_lazy":{},
       "dual_on_linear":{"indicatorEncoding":"onLinear"},
       "dual_on_linear_cardinality":{
            "indicatorEncoding":"onLinear","cardinalityConstraint":True},
       "dual_compact":{
            "indicatorEncoding":"onLinear","cardinalityConstraint":True,
            "fixZw":True,"normalizeW":True},
    }[mode]
    info={"called":0,"variant":config}
    def wrapper(*args,**kwargs):
        info["called"]+=1
        need(info["called"]==1,"unexpected dual model reconstruction")
        need(len(args)>=3,"upstream gMCSpy signature changed")
        gdict=args[1];gmatrix=args[2]
        need(gmatrix.shape[0]==len(gdict),"G matrix / gDict mismatch")
        info["GF_rows"]=int(gmatrix.shape[0])
        info["GF_columns"]=int(gmatrix.shape[1])
        info["possible_interventions"]=int(len(gdict))
        for k,v in config.items():
            need(k not in kwargs,"upstream extra config collision: "+k)
            kwargs[k]=v
        obj=original(*args,**kwargs)
        info["MILP_variables"]=len(obj.getVariables())
        info["MILP_linear_constraints"]=len(obj.getConstraints())
        info["MILP_indicators"]=len(obj.getIndicators())
        return obj
    module.buildDictionaryMCSGeneProblem=wrapper
    try:
        from gMCSpy import calculateGeneMCS
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            t0=time.perf_counter()
            output=calculateGeneMCS(
                cobraModel=model,
                geneSubset=genes,
                maxKOLength=MAX_K,
                maxNumberGMCS=50000,
                solver="gurobi",
                timeLimit=cap,
                numWorkers=1,
                forceLength=False,
                earlyStop=True,
                removeRelated=False,
                checkSolutions=False,
                saveSolutions=False,
                verbose=0,
                enumeration="staged-lazy",
            )
            wall=time.perf_counter()-t0
    finally:
        module.buildDictionaryMCSGeneProblem=original
    need(info["called"]==1,"G/F dual interception did not execute")
    need(isinstance(output,dict),"upstream returned invalid result type")
    solutions=[]
    for datum in output.values():
        need(isinstance(datum,dict) and "solution" in datum,
             "upstream returned malformed solution entry")
        solutions.append(sorted(map(str,datum["solution"])))
    return {"status":"returned","wall_s":round(wall,7),
            "method":mode,"solutions":solutions,"warnings":[str(w.message)
                 for w in caught],"dual":info}

def internal(config_path,out_path):
    cfg=read(config_path)
    need(cfg["protocol"]==PROTOCOL,"R7 config mismatch")
    cohort=cfg["cohort"];mode=cfg["mode"]
    need(cohort in (48,64) and mode in MODES,"invalid trial cohort/variant")
    t0=time.perf_counter()
    model,genes,rules,wild,digest=freeze_model(
        pathlib.Path(cfg["work_dir"]),cohort)
    need(digest==SOURCE_SHA and genes==cfg["genes"],"real model gene subset drift")
    prep=time.perf_counter()-t0
    result=call_gmcspy(mode,model,genes,cfg["cap_s"])
    result.update({
      "preparation_outside_timing_s":round(prep,7),
      "source_model_sha256":digest,
      "upstream_gmcspy_commit":ORIGINAL_GMCSPY_COMMIT,
      "protocol":PROTOCOL,
      "cohort":cohort,
      "repeat":cfg["repeat"],
    })
    save(out_path,result)
    print("DRNAS_MEDICAL_R7_INTERNAL",json.dumps({
      "cohort":cohort,"mode":mode,
      "wall_s":result["wall_s"],"solutions":len(result["solutions"]),
      "dual":result["dual"]},sort_keys=True),flush=True)

def subprocess_once(cfg,target):
    target=pathlib.Path(target)
    cfg_path=target.with_suffix(".config.json")
    save(cfg_path,cfg)
    cmd=[sys.executable,__file__,"internal","--config",str(cfg_path),
         "--out",str(target)]
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cfg["cap_s"]+45)
        total=time.perf_counter()-t
        target.with_suffix(".stdout.txt").write_text(p.stdout[-16000:])
        target.with_suffix(".stderr.txt").write_text(p.stderr[-16000:])
        if p.returncode:
            return {"status":"ERROR","error":p.stderr[-1600:],
                    "exit_code":p.returncode,"outer_wall_s":round(total,6)}
        result=read(target)
        result["outer_wall_s"]=round(total,6)
        return result
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","outer_wall_s":round(time.perf_counter()-t,6)}

def benchmark(cohort,source,out,repeats,cap):
    need(cohort in EXPECTED_REFERENCE,"only R6 independently verified cohorts")
    need(repeats==REPS and cap==CAP,"R7 frozen comparable protocol mismatch")
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    ref=read(source)
    ref_sha=sha(source)
    model,genes,rules,wild,digest=freeze_model(out/"reference_model",cohort)
    need(digest==SOURCE_SHA,"BiGG E coli core source changed")
    truth=reference_check(ref,cohort,genes)
    saved={"protocol":PROTOCOL,"cohort":cohort,"source_model_sha256":digest,
          "reference_R6_summary_sha256":ref_sha,
          "gmcspy_commit":ORIGINAL_GMCSPY_COMMIT,
          "gene_subset":genes,"max_k":MAX_K,"cap_s":CAP,"repeats":REPS,
          "reference_candidate_sets":EXPECTED_REFERENCE[cohort],
          "reference_solutions":[sorted(x) for x in sorted(truth,key=lambda x:(len(x),sorted(x)))],
          "truth_source":"R6 two independent FBA implementations on full gene knockout enumeration",
          "all_variants_use_original_GF_dual_formulation":True,
          "no_candidate_level_LP_calls":True,
          "not_native_drnas_sat":True,
          "trials":[]}
    for rep in range(repeats):
        order=list(MODES)
        random.Random(PROTOCOL+str(cohort)+"/"+str(rep)).shuffle(order)
        for mode in order:
            cfg={"protocol":PROTOCOL,"cohort":cohort,
                 "genes":genes,"mode":mode,"repeat":rep,"cap_s":cap,
                 "work_dir":str((out/f"work-{rep}-{mode}").resolve())}
            record=subprocess_once(cfg,out/f"trial-{rep}-{mode}.json")
            record["mode"]=mode;record["repeat"]=rep
            if record["status"]=="returned":
                actual=normalize(record["solutions"],genes)
                record["missing_solutions"]=[sorted(x) for x in sorted(truth-actual,
                   key=lambda x:(len(x),sorted(x)))]
                record["extra_solutions"]=[sorted(x) for x in sorted(actual-truth,
                   key=lambda x:(len(x),sorted(x)))]
                timed_out=any("time limit" in w.lower() or "incomplete" in w.lower()
                    for w in record["warnings"])
                record["all_solutions_verified"]=not (record["missing_solutions"]
                      or record["extra_solutions"] or timed_out)
                record["source_GF_rows"]=record["dual"]["GF_rows"]
                record["linear_constraints"]=record["dual"]["MILP_linear_constraints"]
                record["indicators"]=record["dual"]["MILP_indicators"]
            else:record["all_solutions_verified"]=False
            saved["trials"].append(record)
            save(out/"summary.json",saved)
            print("DRNAS_MEDICAL_R7_TRIAL",json.dumps({
                  "cohort":cohort,"method":mode,"rep":rep,
                  "status":record["status"],"wall_s":record.get("wall_s"),
                  "GF_rows":record.get("source_GF_rows"),
                  "indicators":record.get("indicators"),
                  "verified":record["all_solutions_verified"],
                  "solutions":len(record.get("solutions",[])),
                  "error":record.get("error","")[:180]},sort_keys=True),flush=True)
    medians={}
    for mode in MODES:
        results=[x for x in saved["trials"] if x["mode"]==mode]
        medians[mode]=(round(statistics.median(x["wall_s"] for x in results),7)
          if len(results)==REPS and all(x["all_solutions_verified"] for x in results)
          else None)
    saved["median_wall_s"]=medians
    saved["all_arms_exact"]=all(x["all_solutions_verified"] for x in saved["trials"])
    saved["speedup_vs_original"]={
       mode:round(medians["published_staged_lazy"]/v,5)
       if medians["published_staged_lazy"] is not None and v else None
       for mode,v in medians.items() if mode!="published_staged_lazy"
    }
    save(out/"summary.json",saved)
    print("DRNAS_MEDICAL_R7_SUMMARY",json.dumps({
       "cohort":cohort,"all_exact":saved["all_arms_exact"],
       "medians":medians,"speedups":saved["speedup_vs_original"]},sort_keys=True),flush=True)

def audit(path48,path64,out):
    input_files=(path48,path64)
    summaries=[read(p) for p in input_files]
    need([r["cohort"] for r in summaries]==[48,64],"cohort order")
    digest=sha(input_files[0])
    for s in summaries:
        n=s["cohort"]
        need(s["protocol"]==PROTOCOL and s["source_model_sha256"]==SOURCE_SHA,
             "source/protocol drift")
        need(s["gmcspy_commit"]==ORIGINAL_GMCSPY_COMMIT,"G/F code drift")
        need(s["reference_candidate_sets"]==EXPECTED_REFERENCE[n] and
             len(s["reference_solutions"])==EXPECTED_MINIMAL[n],"R6 oracle missing")
        need(len(s["trials"])==REPS*len(MODES),"missing variants/repetitions")
        for mode in MODES:
            t=[r for r in s["trials"] if r["mode"]==mode]
            need(len(t)==REPS and {r["repeat"] for r in t}==set(range(REPS)),
                 "not all matched solver runs")
            for r in t:
                if r["status"]=="returned":
                    need(r["source_model_sha256"]==SOURCE_SHA and
                         r["upstream_gmcspy_commit"]==ORIGINAL_GMCSPY_COMMIT,
                         "source or variant not identical")
                    need(r["dual"]["called"]==1 and
                         r["dual"]["GF_rows"]>0 and
                         r["dual"]["GF_columns"]==95,"real G/F model missing")
                    need(r["dual"]["variant"]=={
                       "published_staged_lazy":{},
                       "dual_on_linear":{"indicatorEncoding":"onLinear"},
                       "dual_on_linear_cardinality":{
                           "indicatorEncoding":"onLinear","cardinalityConstraint":True},
                       "dual_compact":{
                           "indicatorEncoding":"onLinear","cardinalityConstraint":True,
                           "fixZw":True,"normalizeW":True}}[mode],
                         "dual reformulation version drift")
        for mode in MODES:
            verified=[r for r in s["trials"] if r["mode"]==mode and
                      r["all_solutions_verified"]]
            need((s["median_wall_s"][mode] is not None)==(len(verified)==REPS),
                 "median must be withheld on incomplete arm")
    report={"status":"PASS_SOURCE_AND_COMPLETION_AUDIT",
       "protocol":PROTOCOL,
       "model_sha256":SOURCE_SHA,
       "published_original_code_commit":ORIGINAL_GMCSPY_COMMIT,
       "results":[{"cohort":s["cohort"],
                   "exact_all_variants":s["all_arms_exact"],
                   "medians":s["median_wall_s"],
                   "speedups":s["speedup_vs_original"],
                   "model_GF_shapes":{mode:[
                       [r["source_GF_rows"],r["dual"]["GF_columns"]]
                          for r in s["trials"] if r["mode"]==mode and
                          r["status"]=="returned"]
                       for mode in MODES}}
                  for s in summaries],
       "not_native_DRNAS":True,
       "FBA_per_candidate_during_R7":False,
       "reference_gene_KO_FBA_exhaustive_R6":True,
       "scope":"one bacterial metabolic model, two overlapping gene cohorts",
       "no_therapeutic_validation":True}
    save(out,report)
    print("DRNAS_MEDICAL_R7_AUDIT",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    # Do not claim dual equivalence by comparing code: verify algebraically
    # and leave ALL intervening MCS enumerations to strict independent oracle.
    # For v>=0, z in {0,1}: [z=1 => v>=1] iff v-z>=0.
    for z in (0,1):
        for v in (0.,.25,.75,1.,2.):
            indicator=(z==0 or v>=1.-1e-9)
            linear=(v-z>=-1e-9)
            need(indicator==linear,"zOnLinear not logically equivalent")
    # Original documented constraint forceBioCons: -.001*w<=-.001,
    # hence w>=1, proving zw cannot equal 0 in a feasible primal-dual
    # feasible model (regardless of the rest of the dual constraints).
    for w in (1.,2.,5.):
        need((-1e-3*w<=-1e-3) and w>0,"w proof failed")
    print("DRNAS_MEDICAL_R7_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","benchmark","internal","audit"))
    p.add_argument("--cohort",type=int,default=48)
    p.add_argument("--reference")
    p.add_argument("--out",required=False,default="medical-results/r7")
    p.add_argument("--config")
    p.add_argument("--cohort48")
    p.add_argument("--cohort64")
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--cap",type=float,default=120.)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="internal":
        need(bool(a.config),"missing internal config")
        internal(a.config,a.out)
    elif a.action=="benchmark":
        need(bool(a.reference),"reference R6 is required")
        benchmark(a.cohort,a.reference,a.out,a.repeats,a.cap)
    else:
        need(bool(a.cohort48 and a.cohort64),"both reference cohorts required")
        audit(a.cohort48,a.cohort64,a.out)
