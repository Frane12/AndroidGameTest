#!/usr/bin/env python3
"""R6: paired SAT gene-MCS vs published gMCSpy specialized G/F-matrix MILP.

Authentic BiGG E. coli core GPR rules; fixed gene subsets, identical intervention
cardinality and phenotype threshold audited by independent COBRApy/GLPK oracle.

No native DRNAS, no full gMISpy regulatory/Bonesis, no drug claims.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import pathlib
import random
import statistics
import subprocess
import sys
import time
import warnings

from gmispy_r3 import structural_oracle,sat_arm,disabled_reactions,fba_growth
from gmispy_r5 import prepare_48

ORIGINAL_GMCSPY_COMMIT = "4567a6d14bd2e5517e7a86b17aebefb0f285544c"
SOURCE_SHA = "13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f"

def freeze_model(out, cohort):
    model,genes,rules,wild,sha,n_and,n_or,examples,extra = prepare_48(out,16)
    if cohort == 64:
        used=set(genes)
        rest=[g.id for g in model.genes if g.id not in used and g.reactions
              and g.id.startswith("b") and len(g.id)==5 and g.id[1:].isdigit()]
        ranked=sorted(rest,key=lambda x:hashlib.sha256(
            ("R6-blind-external-cohort-20261106:"+x).encode()).hexdigest())
        if len(ranked)<16:
            raise AssertionError("No 16 additional independently selected locus genes")
        genes=genes+ranked[:16]
    elif cohort!=48:
        raise ValueError("cohort must be 48 or 64")
    if sha!=SOURCE_SHA or len(genes)!=cohort or len(set(genes))!=cohort:
        raise AssertionError("Unexpected source hash or cohort length")
    if not all(len(g)==5 and g.startswith("b") and g[1:].isdigit() for g in genes):
        raise AssertionError("Invalid spontaneous pseudo-gene selected")
    return model,genes,rules,wild,sha

def internal_gmcspy(config_path,out_path):
    from cobra.io import load_model,write_sbml_model
    from gMCSpy import calculateGeneMCS
    config=json.loads(pathlib.Path(config_path).read_text())
    model=load_model("textbook")
    model.solver="glpk"
    if (len(model.reactions),len(model.metabolites),len(model.genes))!=(95,72,137):
        raise RuntimeError("Unexpected source metabolic model")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        t0=time.perf_counter()
        result=calculateGeneMCS(
            cobraModel=model,
            geneSubset=config["genes"],
            maxKOLength=config["max_k"],
            maxNumberGMCS=50000,
            solver="gurobi",
            timeLimit=config["cap_s"],
            numWorkers=1,
            forceLength=False,
            earlyStop=True,
            removeRelated=False,
            checkSolutions=False,
            saveSolutions=False,
            verbose=0,
            enumeration="staged-lazy"
        )
        duration=time.perf_counter()-t0
    if not isinstance(result,dict):
        raise TypeError("Original gMCSpy returned unexpected type: "+str(type(result)))
    solutions=[]
    for key,value in result.items():
        if not isinstance(value,dict) or "solution" not in value:
            raise ValueError("Original gMCSpy output format invalid")
        sol=sorted(str(x) for x in value["solution"])
        solutions.append(sol)
    report=dict(
        status="returned",wall_s=round(duration,7),
        upstream_commit=ORIGINAL_GMCSPY_COMMIT,
        upstream_api="gMCSpy.calculateGeneMCS",
        enumeration="staged-lazy",kwargs=config,
        source_model="COBRApy textbook/e_coli_core",
        solutions=solutions,
        warnings=[str(x.message) for x in caught],
    )
    pathlib.Path(out_path).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DRNAS_MEDICAL_R6_UPSTREAM_INTERNAL",json.dumps({
        "seconds":report["wall_s"],"solutions":len(solutions),
        "warnings":report["warnings"][:3]},sort_keys=True),flush=True)

def upstream_once(config,out,cap):
    path=out/"gmcspy_config.json"
    path.write_text(json.dumps(config,indent=2,sort_keys=True)+"\n")
    destination=out/("gmcspy_run_%02d.json"%config["repeat"])
    cmd=[sys.executable,__file__,"upstream-internal","--config",str(path),
         "--result",str(destination)]
    start=time.perf_counter()
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+45)
        total=time.perf_counter()-start
        (out/("upstream_stdout_%02d.txt"%config["repeat"])).write_text(result.stdout[-25000:])
        (out/("upstream_stderr_%02d.txt"%config["repeat"])).write_text(result.stderr[-25000:])
        if result.returncode:
            return dict(status="ERROR",reason="upstream process failed",
                        exit_code=result.returncode,wall_outer_s=total)
        report=json.loads(destination.read_text())
        report["wall_outer_s"]=round(total,7)
        return report
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",wall_outer_s=round(time.perf_counter()-start,7))

def solve(out, cohort, max_k, repeats, competitor_cap):
    model,genes,rules,wild,sha=freeze_model(out,cohort)
    out.mkdir(parents=True,exist_ok=True)
    threshold=wild*.01
    t0=time.perf_counter()
    truth,minima,oracle_rows,oracle_s=structural_oracle(
        model,genes,rules,max_k,threshold)
    from gmispy_r4 import check_gpr_signatures
    checked=check_gpr_signatures(genes,rules,truth,max_tests=50000)
    minimum={frozenset(genes[i] for i in c) for c in minima}
    metadata=dict(
        protocol="DRNAS-MEDICAL-R6-REAL-GENE-MCS",
        source_model_sha256=sha,cohort=cohort,genes=genes,
        max_gene_KO=max_k,growth_fraction=.01,baseline_growth=wild,
        growth_threshold=threshold,
        exhaustive=dict(candidate_KO_sets=len(truth),
                         gene_and_reaction_FBA_calls=2*len(truth),
                         monotone_checked=checked,
                         wall_s=oracle_s,
                         minimal_solutions=[sorted(x) for x in sorted(minimum,key=lambda x:(len(x),sorted(x)))]),
        upstream_gmcspy_commit=ORIGINAL_GMCSPY_COMMIT,
        upstream_comparable_only_if_exact_sets_equal=True,
        native_drnas_solver=False,full_gmispy_regulatory_network=False,
        repetitions=[]
    )
    (out/"cohort.json").write_text(json.dumps(
        {"genes":genes,"cohort":cohort,"source_sha256":sha,
         "max_k":max_k,"target_flux_threshold":threshold},indent=2)+"\n")
    print("DRNAS_MEDICAL_R6_REFERENCE",json.dumps({
        "cohort":cohort,"candidates":len(truth),"minimal":len(minimum),
        "sha":sha,"wall_s":round(time.perf_counter()-t0,5)}),flush=True)
    for rep in range(repeats):
        order=("sat","gmcspy") if rep%2==0 else ("gmcspy","sat")
        for method in order:
            if method=="sat":
                rec=sat_arm(model,genes,rules,max_k,threshold,truth,minima,"structural_memo")
                rec["method"]="drnas_architecture_sat_glpk"
                rec["all_solutions_verified"]=rec["crosscheck"]=="PASS"
            else:
                rec=upstream_once({
                    "genes":genes,"max_k":max_k,"cap_s":competitor_cap,
                    "repeat":rep},out,competitor_cap)
                rec["method"]="published_gMCSpy_staged_lazy"
                if rec["status"]=="returned":
                    sets=[frozenset(x) for x in rec["solutions"]]
                    rec["duplicates"]=len(sets)-len(set(sets))
                    rec["unknown_solutions"]=[sorted(x) for x in set(sets)-minimum]
                    rec["missing_solutions"]=[sorted(x) for x in minimum-set(sets)]
                    rec["timeout_warning"]=any("time limit" in w.lower() or "lower bound" in w.lower()
                                               for w in rec["warnings"])
                    rec["all_solutions_verified"]=(not rec["duplicates"]
                         and not rec["unknown_solutions"] and not rec["missing_solutions"]
                         and not rec["timeout_warning"])
                else:
                    rec["all_solutions_verified"]=False
            rec["repeat"]=rep
            metadata["repetitions"].append(rec)
            (out/"summary.json").write_text(json.dumps(metadata,indent=2,sort_keys=True)+"\n")
            print("DRNAS_MEDICAL_R6_TRIAL",json.dumps({
                "cohort":cohort,"repeat":rep,"method":rec["method"],
                "wall_s":rec.get("wall_s"),"status":rec.get("status","complete"),
                "verified":rec["all_solutions_verified"],
                "solutions":len(rec.get("solutions",[])),
                "lp_calls":rec.get("lp_calls"),
                "missing":len(rec.get("missing_solutions",[])),
                "extra":len(rec.get("unknown_solutions",[])),
            },sort_keys=True),flush=True)
    both_complete=all(t["all_solutions_verified"] for t in metadata["repetitions"])
    medians={}
    for name in ("drnas_architecture_sat_glpk","published_gMCSpy_staged_lazy"):
        vals=[x["wall_s"] for x in metadata["repetitions"] if x["method"]==name
              and x["all_solutions_verified"]]
        medians[name]=statistics.median(vals) if len(vals)==repeats else None
    metadata["complete_comparable"]=both_complete
    metadata["median_wall_s"]=medians
    (out/"summary.json").write_text(json.dumps(metadata,indent=2,sort_keys=True)+"\n")
    print("DRNAS_MEDICAL_R6_SUMMARY",json.dumps({
        "cohort":cohort,"candidates":len(truth),"minimal":len(minimum),
        "strict_comparison_pass":both_complete,"medians":medians},sort_keys=True),flush=True)
    # If upstream cannot verify same solution semantics, preserve artifacts
    # but do not label this as a valid speed comparison.
    if not both_complete:
        print("DRNAS_MEDICAL_R6_CAUTION original solver incomplete/different, no speedup claim",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["benchmark","upstream-internal"])
    parser.add_argument("--out",default="medical-results/r6")
    parser.add_argument("--cohort",type=int,choices=[48,64],default=64)
    parser.add_argument("--max-k",type=int,default=3)
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--competitor-cap",type=float,default=120.)
    parser.add_argument("--config")
    parser.add_argument("--result")
    args=parser.parse_args()
    if args.mode=="benchmark":
        solve(pathlib.Path(args.out),args.cohort,args.max_k,args.repeats,args.competitor_cap)
    else:
        if not args.config or not args.result:
            parser.error("--config and --result required for internal call")
        internal_gmcspy(args.config,args.result)
