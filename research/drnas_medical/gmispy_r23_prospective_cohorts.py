#!/usr/bin/env python3
"""DRNAS Medical R23: prospective source-locked gene-cohort transfer of R22.

Compare unmodified R9 vs R15 share_12_control on TWO new 384-gene families,
both completely disjoint from R22's R9 384 genes and from one another.
The R23 families are NOT claimed disjoint from ALL historical R17/R18 genes.
Each family has nested N=96/192/384 source-only selected cohorts.

All cohorts are frozen as an artifact before any R23 solver trial. No
knockout phenotype, LP result, training outcome, or wall time is used in
selection. This stays on the SAME bacterial iML1515 SBML model (not an
independent-organism holdout and not native DRNAS SAT).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import re
import statistics
import time
from unittest.mock import patch

from pysat.solvers import Solver as OriginalSolver

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r15_stage_boundary as r15
import gmispy_r14_cross_stage as r14

PROTO = "DRNAS-MEDICAL-R23-NEW-COHORTS-SHARE12-v1"
SEED = "DRNAS-MEDICAL-R23-PROSPECTIVE-GENE-FAMILIES-20261107-v1"
FAMILIES = ("sha_disjoint_from_r22", "degree_disjoint_from_r22")
SIZES = (96,192,384)
ARMS = ("r9_baseline","share_12_control")
REPS = 3
CAP = 150.0
MODEL_SHA = r9.SOURCE_SHA
need = r14.need
save = r14.save
load = r14.load
canon = r14.canon


def hash_gene_family(genes):
    return r9.hgenes(genes)


def stable_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def manifest_digest(manifest):
    basis={k:v for k,v in manifest.items() if k!="manifest_digest"}
    return stable_hash(json.dumps(basis,sort_keys=True,separators=(",",":")))


def candidate_pool(model, prior):
    available = {g.id:g for g in model.genes
                 if re.fullmatch(r"b[0-9]{4}",g.id) and len(g.reactions)>0}
    prior_genes=set(prior)
    need(prior_genes.issubset(available),"original R9 genes not eligible")
    new_ids=set(available)-prior_genes
    need(len(new_ids)>=768,"insufficient genes disjoint from original R9 384")
    return available,new_ids


def create_manifest(source,old_frozen,out):
    old=r9.check_manifest(source,old_frozen)
    model,metadata=r8.load_frozen(source)
    need(metadata["SBML_sha256"]==MODEL_SHA,"wrong frozen SBML source")
    old384=old["cohorts"]["384"]
    need(len(old384)==384 and len(set(old384))==384,"wrong frozen R9 cohort")
    available,other=candidate_pool(model,old384)
    family_a=sorted(other,key=lambda gid:stable_hash(SEED+":SHA:"+gid))[:384]
    family_b=sorted(other-set(family_a),key=lambda gid:
        (-len(available[gid].reactions),
         stable_hash(SEED+":DEGREE:"+gid)))[:384]
    need(len(family_a)==len(family_b)==384 and
         not (set(family_a)&set(family_b)),"R23 family disjointness failure")
    need(not ((set(family_a)|set(family_b))&set(old384)),
         "R23 genes overlap R22 frozen cohort")
    by_family={
        FAMILIES[0]:{str(n):family_a[:n] for n in SIZES},
        FAMILIES[1]:{str(n):family_b[:n] for n in SIZES},
    }
    result={
        "protocol":PROTO,
        "model_name":"iML1515",
        "source_sha":MODEL_SHA,
        "prior_R9_cohort_sha":hash_gene_family(old384),
        "selection_seed":SEED,
        "selection":"SHA ranks in family A; reaction-degree plus SHA ties in B; no phenotype",
        "prior_R22_genes_excluded":384,
        "families_disjoint_from_each_other":True,
        "families_disjoint_from_R22":True,
        "NOT_disjoint_from_all_R17_R18_genes":True,
        "NOT_a_new_organism_or_independent_model":True,
        "not_native_DRNAS":True,
        "gene_families":by_family,
        "gene_hashes":{fam:{str(n):hash_gene_family(genes)
                      for n,genes in family.items()} for fam,family in by_family.items()},
        "sizes":list(SIZES),"repetitions":REPS,"max_knockouts":3,
        "two_solver_arms":list(ARMS),"R9_frozen_wall_cap_s":CAP,
        "precommit_before_first_R23_trial":True,
        "eligible_genes_total":len(available),
        "genes_available_after_excluding_R22":len(other),
    }
    result["manifest_digest"]=manifest_digest(result)
    save(out,result)
    print("R23_PRECOMMIT",json.dumps({
        "manifest_digest":result["manifest_digest"],
        "source_sha":result["source_sha"],
        "gene_hashes":result["gene_hashes"],
        "family_disjointness":True,
        "prior_R22_genes_excluded":384,
        "other_prior_R17_R18_overlap_not_excluded":True},sort_keys=True),flush=True)


def verified_manifest(path):
    manifest=load(path)
    need(manifest["protocol"]==PROTO and manifest["source_sha"]==MODEL_SHA,
         "wrong source/protocol")
    need(manifest["manifest_digest"]==manifest_digest(manifest),
         "changed prospective manifest")
    families=manifest["gene_families"]
    need(set(families)==set(FAMILIES),"missing source families")
    need(manifest["sizes"]==list(SIZES) and manifest["repetitions"]==REPS,
         "wrong frozen protocol")
    for fam in FAMILIES:
        cohorts=families[fam]
        need(set(cohorts)==set(str(n) for n in SIZES),"missing frozen sizes")
        for n in SIZES:
            genes=cohorts[str(n)]
            need(len(genes)==n and len(set(genes))==n,"duplicate or short cohort")
            need(hash_gene_family(genes)==manifest["gene_hashes"][fam][str(n)],
                 "frozen cohort changed")
        need(cohorts["384"][:96]==cohorts["96"] and
             cohorts["384"][:192]==cohorts["192"],"not nested")
    need(not (set(families[FAMILIES[0]]["384"]) &
              set(families[FAMILIES[1]]["384"])),"families overlap")
    return manifest


def run_one(source,genes,arm,rep,family,n,manifest):
    need(arm in ARMS and rep in range(REPS) and n in SIZES,"wrong arm/rep/n")
    overall_start=time.perf_counter()
    model,source_m=r8.load_frozen(source)
    rules=r8.all_rules(model)
    threshold=float(source_m["wildtype_biomass"])*0.01
    need(threshold>0 and source_m["SBML_sha256"]==MODEL_SHA,
         "biomass or source drift")
    coord=None
    if arm=="r9_baseline":
        result=r9.solve(model,genes,rules,threshold,CAP)
        bridge={"solver_creations":3,"mode":"r9_original"}
    else:
        coord=r15.BoundaryCoordinator(OriginalSolver,genes,rules,"share_12")
        try:
            with patch("pysat.solvers.Solver",coord.factory):
                result=r9.solve(model,genes,rules,threshold,CAP)
        finally:
            coord.close()
        bridge=coord.audit()
        need(bridge["solver_creations"]==2 and
             bridge["boundary_reset_after_k"]==[2],
             "expected share_12 solver lifetime not respected")
    solver_elapsed=time.perf_counter()-overall_start
    need(result["status"]=="SOLVED" and result["SAT_UNSAT_stages"]==3,
         "full SAT exact-cardinality search not completed")
    need(result["wall_s"]>0 and math.isfinite(result["wall_s"]),
         "nonfinite solver wall")
    need(result["lp_calls"]==result["viable_lp"]+result["lethal_lp"],
         "LP request accounting mismatch")
    candidate=canon(result["minimal_sets"])
    # Always use a newly loaded GLPK/COBRA model, not the solver's mutated model,
    # to prevent the R19/R20 stall and preserve independent biological FBA.
    oracle_start=time.perf_counter()
    fresh, fresh_meta=r8.load_frozen(source)
    fresh_rules=r8.all_rules(fresh)
    need(source_m["SBML_sha256"]==fresh_meta["SBML_sha256"] and
         r8.dims(fresh)==r8.dims(model),"oracle source mismatch")
    need({k:v[0] for k,v in rules.items()}==
         {k:v[0] for k,v in fresh_rules.items()},
         "independent oracle gene rules mismatch")
    check=r9.verify_sets(fresh,genes,fresh_rules,threshold,result["minimal_sets"])
    oracle_wall=time.perf_counter()-oracle_start
    need(check["sound_minimal"] and
         check["FBA_calls"]==check["independent_checks"],
         "biological oracle failed")
    row={
        "protocol":PROTO,"family":family,"n":n,"rep":rep,"arm":arm,
        "source_sha":MODEL_SHA,"manifest_digest":manifest["manifest_digest"],
        "gene_sha":hash_gene_family(genes),
        "status":"SOLVED","three_exact_k_UNSAT_terminations":True,
        "wall_s":result["wall_s"],
        "driver_s_including_model_load":round(solver_elapsed,6),
        "independent_oracle_s":round(oracle_wall,6),
        "total_trial_s_including_oracle":round(time.perf_counter()-overall_start,6),
        "LP_requests":result["lp_calls"],"SAT_calls":result["sat_calls"],
        "flux_cuts":result["flux_cuts"],"minimal_sets":[list(x) for x in candidate],
        "minimal_count":len(candidate),
        "independent_reference_sound":True,
        "independent_FBA_checks":check["FBA_calls"],
        "solver_bridge":bridge,
        "not_independent_organism":True,
        "not_native_DRNAS":True,
    }
    print("R23_TRIAL",json.dumps({k:row[k] for k in
        ("family","n","rep","arm","wall_s","LP_requests","SAT_calls",
         "flux_cuts","minimal_count","independent_FBA_checks",
         "independent_reference_sound","total_trial_s_including_oracle")},
         sort_keys=True),flush=True)
    return row


def paired(source,frozen,manifest_path,family,n,rep,out):
    manifest=verified_manifest(manifest_path)
    need(family in FAMILIES and n in SIZES and rep in range(REPS),
         "invalid frozen cohort or repeat")
    prior=r9.check_manifest(source,frozen)
    need(prior["gene_cohort_SHA256"]["384"]==manifest["prior_R9_cohort_sha"],
         "prior frozen R22 384 cohort SHA differs")
    genes=manifest["gene_families"][family][str(n)]
    need(not set(genes)&set(prior["cohorts"]["384"]),
         "gene overlap with R22")
    order=ARMS if (rep+FAMILIES.index(family))%2==0 else ARMS[::-1]
    rows=[]
    for arm in order:
        row=run_one(source,genes,arm,rep,family,n,manifest)
        rows.append(row)
        save(out,{"protocol":PROTO,"complete":False,"family":family,
                  "n":n,"rep":rep,"rows":rows,"manifest_digest":manifest["manifest_digest"]})
    a,b=rows
    need(canon(a["minimal_sets"])==canon(b["minimal_sets"]),
         "control and R9 independently verified minimal sets differ")
    need(a["minimal_count"]==b["minimal_count"],"minimal count differs")
    by_arm={r["arm"]:r for r in rows}
    speedup=by_arm["r9_baseline"]["wall_s"]/by_arm["share_12_control"]["wall_s"]
    response={
        "protocol":PROTO,"complete":True,"source_sha":MODEL_SHA,
        "manifest_digest":manifest["manifest_digest"],"family":family,
        "n":n,"rep":rep,"rows":rows,
        "speedup_control_over_R9":round(speedup,7),
        "cross_arm_canonical_sets_equal":True,
        "new_cohort_disjoint_from_R22":True,
        "not_new_independent_model":True,
    }
    save(out,response)
    print("R23_PAIRED_PASS",json.dumps({
        "family":family,"n":n,"rep":rep,
        "R9_s":by_arm["r9_baseline"]["wall_s"],
        "share12_s":by_arm["share_12_control"]["wall_s"],
        "speedup":round(speedup,7),"minima":a["minimal_count"],
        "source_paired":True,"independent_FBA_for_both":True},sort_keys=True),flush=True)


def strict_audit(inputs,manifest_path,out):
    manifest=verified_manifest(manifest_path)
    cases=[load(p) for p in inputs]
    expected={(family,n,rep) for family in FAMILIES
              for n in SIZES for rep in range(REPS)}
    received={(x["family"],x["n"],x["rep"]) for x in cases}
    need(len(cases)==len(expected) and received==expected,
         "partial/incomplete or duplicate pairing")
    by_family={}
    for fam in FAMILIES:
        by_family[fam]={}
        for n in SIZES:
            pairings=sorted((x for x in cases if x["family"]==fam and x["n"]==n),
                            key=lambda x:x["rep"])
            r9_times=[]
            control_times=[]
            speeds=[]
            minima=[]
            for case in pairings:
                need(case["complete"] and case["protocol"]==PROTO and
                     case["source_sha"]==MODEL_SHA and
                     case["manifest_digest"]==manifest["manifest_digest"] and
                     case["cross_arm_canonical_sets_equal"] and
                     case["new_cohort_disjoint_from_R22"],"missing frozen proof")
                arms={r["arm"]:r for r in case["rows"]}
                need(len(case["rows"])==2 and set(arms)==set(ARMS),
                     "wrong arm count")
                for arm,row in arms.items():
                    need(row["independent_reference_sound"] and
                         row["three_exact_k_UNSAT_terminations"] and
                         row["source_sha"]==MODEL_SHA and
                         row["gene_sha"]==manifest["gene_hashes"][fam][str(n)] and
                         row["manifest_digest"]==manifest["manifest_digest"] and
                         row["n"]==n and row["family"]==fam and
                         row["rep"]==case["rep"],"wrong biological reference")
                    need(row["wall_s"]>0 and
                         math.isfinite(row["total_trial_s_including_oracle"]) and
                         row["total_trial_s_including_oracle"]>=row["wall_s"] and
                         row["LP_requests"]>=1 and row["SAT_calls"]>=1,
                         "inconsistent timings or calls")
                need(canon(arms["r9_baseline"]["minimal_sets"])==
                     canon(arms["share_12_control"]["minimal_sets"]),
                     "different solutions to same source")
                r9_times.append(arms["r9_baseline"]["wall_s"])
                control_times.append(arms["share_12_control"]["wall_s"])
                speeds.append(r9_times[-1]/control_times[-1])
                minima.append(arms["r9_baseline"]["minimal_count"])
            need(len(set(minima))==1,"different numbers of minimal interventions")
            m0=statistics.median(r9_times)
            m1=statistics.median(control_times)
            by_family[fam][str(n)]={
                "R9_median_s":round(m0,6),
                "share12_median_s":round(m1,6),
                "ratio_of_medians":round(m0/m1,6),
                "paired_speedups":[round(t,6) for t in speeds],
                "control_faster_reps":sum(t>1 for t in speeds),
                "minimal_count":minima[0],
                "rep_R9_s":[round(x,6) for x in r9_times],
                "rep_share12_s":[round(x,6) for x in control_times],
            }
    summary={
        "status":"R23_FROZEN_SOURCE_DISJOINT_COHORT_AUDIT_PASS",
        "protocol":PROTO,
        "total_trials":len(cases)*2,
        "paired_cases":len(cases),
        "families":by_family,
        "all_cross_arm_minimal_sets_match":True,
        "all_independent_FBA_minimality_checks_passed":True,
        "same_original_iML1515_bacterial_model":True,
        "two_disjoint_genetic_families_excluding_R22":True,
        "NOT_gene_disjoint_from_all_R17_R18_history":True,
        "no_external_organism_holdout":True,
        "no_blind_external_source":True,
        "not_native_DRNAS":True,
        "no_world_record_claim":True,
        "conclusion_only_if_all_pairs_complete":True,
        "manifest_digest":manifest["manifest_digest"],
    }
    save(out,summary)
    print("R23_FINAL",json.dumps({
        "status":summary["status"],"paired_cases":summary["paired_cases"],
        "total_trials":summary["total_trials"],"families":by_family,
        "manifest_digest":summary["manifest_digest"]},sort_keys=True),flush=True)


def selftest():
    need(FAMILIES==("sha_disjoint_from_r22","degree_disjoint_from_r22")
         and SIZES==(96,192,384) and REPS==3 and CAP==150.0,"protocol drift")
    need(len(ARMS)==2 and len(set(ARMS))==2,"wrong arm specification")
    need(r9.SOURCE_SHA==MODEL_SHA,"source differs from frozen R9")
    print("R23_SELFTEST_PASS",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("selftest","freeze","paired","audit"))
    p.add_argument("--source")
    p.add_argument("--frozen")
    p.add_argument("--manifest")
    p.add_argument("--family",choices=FAMILIES)
    p.add_argument("--n",type=int)
    p.add_argument("--rep",type=int)
    p.add_argument("--out")
    p.add_argument("--inputs",nargs="*")
    args=p.parse_args()
    if args.cmd=="selftest":selftest()
    elif args.cmd=="freeze":
        need(args.source and args.frozen and args.out,"missing freeze inputs")
        create_manifest(args.source,args.frozen,args.out)
    elif args.cmd=="paired":
        need(args.source and args.frozen and args.manifest and args.out,
             "missing paired inputs")
        paired(args.source,args.frozen,args.manifest,args.family,args.n,args.rep,args.out)
    else:
        need(args.manifest and args.inputs and args.out,"missing audit inputs")
        strict_audit(args.inputs,args.manifest,args.out)
