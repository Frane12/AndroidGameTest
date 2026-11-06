#!/usr/bin/env python3
"""DRNAS Medical R11: matched R9 primal flux CEGAR with exact GPR phenotype LP memoization.
Only change is reuse of an FBA result when the entire disabled-reaction set matches.
Paired baseline/control; frozen BiGG iML1515 source and R10 solution reference.
No cancer, native DRNAS solver or general complexity claim.
"""
from __future__ import annotations
import argparse, collections, json, pathlib, statistics, subprocess, sys, time
from unittest.mock import patch
import gmispy_r9_scaling as r9
import gmispy_r8_iml1515 as r8
from gmispy_r3 import disabled_reactions

PROTO="DRNAS-MEDICAL-R11-EXACT-GPR-CACHE-20261106-v1"
REF_RUN=42286261326
SIZES=(24,48,96,192,384)
ARMS=("baseline","phenotype_cache")
REPS=2
CAP=150.0

def need(ok,reason):
    if not ok: raise RuntimeError("R11_FAIL_CLOSED "+str(reason))
def load(p): return json.loads(pathlib.Path(p).read_text())
def save(p,value):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
def canon(sets): return tuple(sorted(tuple(sorted(s)) for s in sets))

def frozen_reference(source,frozen,ref,n):
    manifest=r9.check_manifest(source,frozen)
    row=load(ref)
    need(n in SIZES and row["n"]==n and
         row["protocol"]=="DRNAS-MEDICAL-R10-CROSSENGINE-IML1515-20261106-v1" and
         row["R9_reference_run"]==42239472392 and
         row["source_SHA256"]==r9.SOURCE_SHA,"R10 source/reference drift")
    genes=manifest["cohorts"][str(n)]
    need(row["gene_SHA256"]==r9.hgenes(genes),"frozen R10 cohort drift")
    need(row["all_engine_trials_verified"] and len(row["rows"])==6 and
         row["sample_audit"]["status"]=="SAMPLE_PASS","invalid R10 certificate")
    trials=row["rows"]
    need(all(t["verified"] and t["reference_match"] and
             t["source_SHA256"]==r9.SOURCE_SHA and
             t["gene_SHA256"]==row["gene_SHA256"] and
             canon(t["minimal_sets"])==canon(trials[0]["minimal_sets"])
             for t in trials),"R10 references disagree")
    return genes,trials[0]["minimal_sets"]

def run_one(config,out):
    n,arm,rep=config["n"],config["arm"],config["rep"]
    need(n in SIZES and arm in ARMS and rep in range(REPS),"trial scope")
    src,freeze=config["source"],config["freeze"]
    genes,expected=frozen_reference(src,freeze,config["reference"],n)
    model,source_metadata=r8.load_frozen(src)
    rules=r8.all_rules(model)
    target=float(source_metadata["wildtype_biomass"])*.01
    original=r9.certified_flux
    counter=collections.Counter()
    cache={}
    def query(m,names,ko,local_rules,matrix,rxns,threshold):
        need(m is model and names==genes and local_rules is rules and
             threshold==target,"GPR/model identity changed")
        counter["logical_lp_requests"]+=1
        if arm=="baseline":
            counter["physical_lp_calls"]+=1
            return original(m,names,ko,local_rules,matrix,rxns,threshold)
        # Same EXACT knockout-reaction phenotype => identical LP feasible
        # region, objective and medium. No approximate hashes or rounding.
        signature=disabled_reactions(local_rules,(names[i] for i in ko))
        counter["phenotype_lookups"]+=1
        if signature in cache:
            counter["cache_hits"]+=1
            counter["viable_cache_hits" if cache[signature][2]
                    else "lethal_cache_hits"]+=1
            return cache[signature]
        counter["physical_lp_calls"]+=1
        answer=original(m,names,ko,local_rules,matrix,rxns,threshold)
        cache[signature]=answer
        return answer
    with patch.object(r9,"certified_flux",new=query):
        solved=r9.solve(model,genes,rules,target,CAP)
    need(solved["status"]=="SOLVED" and solved["SAT_UNSAT_stages"]==3,
         "R9 algorithm failed one search cardinality")
    independent=r9.verify_sets(model,genes,rules,target,solved["minimal_sets"])
    match=canon(solved["minimal_sets"])==canon(expected)
    need(independent["sound_minimal"] and match,"R10 solution truth mismatch")
    need(counter["logical_lp_requests"]==solved["lp_calls"] and
         counter["physical_lp_calls"]+counter["cache_hits"]==
         counter["logical_lp_requests"],"LP call accounting invalid")
    result={**solved,"protocol":PROTO,"arm":arm,"n":n,"rep":rep,
            "source_SHA256":r9.SOURCE_SHA,"gene_SHA256":r9.hgenes(genes),
            "reference_run":REF_RUN,"reference_match":match,
            "independent_gene_and_reaction_FBA":independent,
            "physical_lp_calls":counter["physical_lp_calls"],
            "logical_lp_requests":counter["logical_lp_requests"],
            "phenotype_cache_hits":counter["cache_hits"],
            "viable_cache_hits":counter["viable_cache_hits"],
            "lethal_cache_hits":counter["lethal_cache_hits"],
            "unique_phenotypes":len(cache),"not_native_drnas":True,
            "not_human_cancer_model":True}
    save(out,result)
    print("R11_TRIAL",json.dumps({
        "n":n,"arm":arm,"rep":rep,"wall_s":solved["wall_s"],
        "LP":result["physical_lp_calls"],
        "logical_LP":solved["lp_calls"],"hits":result["phenotype_cache_hits"],
        "solutions":len(solved["minimal_sets"]),"match":match},sort_keys=True),
        flush=True)

def child(cfg,destination):
    destination=pathlib.Path(destination)
    config=destination.with_suffix(".config.json")
    save(config,cfg)
    start=time.perf_counter()
    try:
        proc=subprocess.run([sys.executable,__file__,"internal",
               "--config",str(config),"--out",str(destination)],
               text=True,capture_output=True,timeout=CAP+90)
        destination.with_suffix(".stdout.log").write_text(proc.stdout[-18000:])
        destination.with_suffix(".stderr.log").write_text(proc.stderr[-18000:])
        elapsed=round(time.perf_counter()-start,6)
        if proc.returncode:
            return {"status":"ERROR","error":proc.stderr[-3200:],
                    "outer_s":elapsed}
        result=load(destination)
        result["outer_s"]=elapsed
        return result
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","outer_s":round(time.perf_counter()-start,6)}

def cohort(source,frozen,reference,n,out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    genes,expected=frozen_reference(source,frozen,reference,n)
    rows=[]
    for rep in range(REPS):
        for arm in (ARMS if rep==0 else tuple(reversed(ARMS))):
            config={"source":str(pathlib.Path(source).resolve()),
                    "freeze":str(pathlib.Path(frozen).resolve()),
                    "reference":str(pathlib.Path(reference).resolve()),
                    "n":n,"arm":arm,"rep":rep}
            result=child(config,out/(arm+"-rep"+str(rep)+".json"))
            result.update({"n":n,"arm":arm,"rep":rep})
            result["verified"]=(result.get("status")=="SOLVED" and
                                result.get("reference_match") is True and
                                result.get("wall_s",CAP+1)<=CAP)
            rows.append(result)
            print("R11_RESULT",json.dumps({
                "n":n,"arm":arm,"rep":rep,"status":result["status"],
                "wall_s":result.get("wall_s"),"verified":result["verified"],
                "physical_lp_calls":result.get("physical_lp_calls"),
                "cache_hits":result.get("phenotype_cache_hits"),
                "error":result.get("error","")[-300:]},sort_keys=True),flush=True)
            save(out/"summary.json",{"protocol":PROTO,"n":n,
                                     "rows":rows,"partial":True})
    medians={}
    physical={}
    for arm in ARMS:
        good=[r for r in rows if r["arm"]==arm and r["verified"]]
        medians[arm]=(round(statistics.median(r["wall_s"] for r in good),6)
                      if len(good)==REPS else None)
        physical[arm]=(statistics.median(r["physical_lp_calls"] for r in good)
                       if len(good)==REPS else None)
    speedup=(round(medians["baseline"]/medians["phenotype_cache"],5)
             if all(x is not None for x in medians.values()) else None)
    report={"protocol":PROTO,"n":n,"rows":rows,"partial":False,
            "source_SHA256":r9.SOURCE_SHA,"gene_SHA256":r9.hgenes(genes),
            "reference_run":REF_RUN,"cap_s":CAP,"repetitions":REPS,
            "expected_solutions":len(expected),
            "complete":all(x["verified"] for x in rows),
            "median_wall_s":medians,"median_physical_LP":physical,
            "baseline_over_cache_speedup":speedup,
            "exhaustive_reference_only_24_48":n in (24,48),
            "not_native_DRNAS":True,"not_cancer_model":True}
    save(out/"summary.json",report)
    print("R11_COHORT_FINAL",json.dumps({
        "n":n,"complete":report["complete"],"median_s":medians,
        "physical_LP":physical,"speedup":speedup},sort_keys=True),flush=True)

def audit(inputs,out):
    need(len(inputs)==len(SIZES),"all five independent cohorts required")
    cases=[load(x) for x in inputs]
    need([x["n"] for x in cases]==list(SIZES),"cohort list changed")
    for case in cases:
        need(case["protocol"]==PROTO and case["source_SHA256"]==r9.SOURCE_SHA
             and case["reference_run"]==REF_RUN and
             case["partial"] is False and len(case["rows"])==4,
             "invalid source, reference, or incomplete trials")
        need({(x["arm"],x["rep"]) for x in case["rows"]}==
             {(a,k) for a in ARMS for k in range(REPS)},
             "missing paired arm")
        for arm in ARMS:
            good=[x for x in case["rows"] if x["arm"]==arm and x["verified"]]
            if case["median_wall_s"][arm] is not None:
                need(len(good)==REPS,"unjustified median/speed claim")
                for x in good:
                    need(x["physical_lp_calls"]+
                         x["phenotype_cache_hits"]==x["logical_lp_requests"]
                         and x["reference_match"] and x["wall_s"]<=CAP,
                         "invalid LP or scientific certificate")
            else:need(len(good)<REPS,"complete arm missing medians")
        need(case["complete"]==all(x["verified"] for x in case["rows"]),
             "completion audit mismatch")
    result={"protocol":PROTO,"status":"PASS_AUDIT_WITH_LIMITATIONS",
            "R10_reference_run":REF_RUN,"cohorts":[{
                "n":c["n"],"complete":c["complete"],
                "median_wall_s":c["median_wall_s"],
                "median_physical_LP":c["median_physical_LP"],
                "baseline_over_cache_speedup":c["baseline_over_cache_speedup"]
            } for c in cases],
            "no_independent_exhaustive_large_cohort_proof":True,
            "not_native_DRNAS":True,"not_cancer_model":True,
            "not_published_gMCSpy_comparison":True}
    save(out,result)
    print("R11_FINAL",json.dumps(result,sort_keys=True),flush=True)

def selftest():
    need(r9.SOURCE_SHA==
         "9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28"
         and r9.ncomb(384)==9437504 and REPS==2,
         "frozen protocol mismatch")
    print("R11_SELFTEST_PASS",json.dumps({"arms":ARMS,"sizes":SIZES}),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","internal","cohort","audit"))
    p.add_argument("--source",default="r11/source")
    p.add_argument("--frozen",default="r11/frozen")
    p.add_argument("--reference",default="r11/reference/summary.json")
    p.add_argument("--n",type=int,default=24)
    p.add_argument("--config")
    p.add_argument("--inputs",nargs="*")
    p.add_argument("--out",default="r11/results")
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="internal":
        need(bool(a.config),"missing subprocess config")
        run_one(load(a.config),a.out)
    elif a.action=="cohort":
        cohort(a.source,a.frozen,a.reference,a.n,a.out)
    else:audit(a.inputs or [],a.out)
