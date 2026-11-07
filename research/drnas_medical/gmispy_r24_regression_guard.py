#!/usr/bin/env python3
"""DRNAS Medical R24: frozen conservative GPR router, prospectively audited.

R23 is the ONLY supervised router-development source. Before running any R24
solver, freeze the trained router and two disjoint R24 test families, holding
out the NEW combinations from all optimization outcomes. R24 inherits R9's
unchanged CEGAR SAT/FBA and the R15 share_12 coordinator verbatim.
R9 fallback means the literal unmodified R9 algorithm, not a gated imitation.

Limitations: one E. coli iML1515 model, historical gene identities partly
reused in mixed 384 groups, no independent-organism holdout; not native DRNAS.
An empirical no-regression claim needs heldout successes, not just safe routing.
"""
from __future__ import annotations
import argparse, hashlib, json, math, pathlib, re, statistics, time, faulthandler, sys
from unittest.mock import patch
from pysat.solvers import Solver as OriginalSolver

import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r14_cross_stage as r14
import gmispy_r15_stage_boundary as r15
import gmispy_r23_prospective_cohorts as r23

PROTOCOL="DRNAS-MEDICAL-R24-FROZEN-REGRESSION-GUARD-v1"
SEED="R24-CONSERVATIVE-STRUCTURAL-FROZEN-20261107"
FAMILIES=("unseen_sha_mix","unseen_degree_mix")
SIZES=(96,192,384)
REPS=3
ARMS=("r9_baseline","share_12_control","r24_guarded")
CAP=150.0
SOURCE_SHA=r9.SOURCE_SHA
need=r14.need
save=r14.save
load=r14.load
canon=r14.canon

def sig(x):
    return r9.hgenes(x)

def hashed(s):
    return hashlib.sha256(s.encode()).hexdigest()

def digest(obj):
    return hashed(json.dumps({k:v for k,v in obj.items() if k!="digest"},
                             sort_keys=True,separators=(",",":")))

def fingerprint(model,genes,rules):
    """Pure source GPR structure; no knockout LP, SAT solve, or phenotypes."""
    values=[]
    disables=[]
    for gid in genes:
        g=model.genes.get_by_id(gid)
        candidates=[r.id for r in g.reactions if r.id in rules]
        values.append(len(candidates))
        knocked=frozenset((gid,))
        disables.append(sum(not rules[rid][2](knocked) for rid in candidates))
    n=len(genes)
    need(n in SIZES and all(d<=v for d,v in zip(disables,values)),
         "invalid structural GPR source fingerprint")
    return [round(math.log1p(sum(values)/n),9),
            round(math.log1p(sum(disables)/n),9),
            round(sum(d>0 for d in disables)/n,9)]

def metric_distance(a,b):
    # Source units are log mean reaction degree, log direct-disabled degree,
    # and fraction of directly disabling genes; no fitted weights.
    return math.sqrt(sum(((x-y)/scale)**2 for x,y,scale in zip(
        a,b,(0.30,0.30,0.20))))

def build_freeze(source,r9f,r23manifest,r23report,out):
    r9old=r9.check_manifest(source,r9f)
    previous=load(r23manifest)
    report=load(r23report)
    need(previous["protocol"]==r23.PROTO and
         previous["manifest_digest"]==r23.manifest_digest(previous),
         "R23 genetic precommit failed")
    need(report["status"]=="R23_FROZEN_SOURCE_DISJOINT_COHORT_AUDIT_PASS"
         and report["paired_cases"]==18 and report["total_trials"]==36
         and report["manifest_digest"]==previous["manifest_digest"],
         "R23 complete certified training artifact missing")
    model,meta=r8.load_frozen(source)
    rules=r8.all_rules(model)
    need(meta["SBML_sha256"]==SOURCE_SHA,"changed published bacterial model")
    oldgenes=set(r9old["cohorts"]["384"])
    sha=previous["gene_families"]["sha_disjoint_from_r22"]["384"]
    degree=previous["gene_families"]["degree_disjoint_from_r22"]["384"]
    need(len(oldgenes)==len(sha)==len(degree)==384 and
         not (oldgenes&set(sha) or oldgenes&set(degree) or set(sha)&set(degree)),
         "R9/R23 training genes overlap")
    eligible={g.id:g for g in model.genes
              if re.fullmatch(r"b[0-9]{4}",g.id) and len(g.reactions)>0}
    unused=set(eligible)-oldgenes-set(sha)-set(degree)
    # 288 genuinely unused genes are split across the two families.
    need(len(unused)>=288,"not enough source genes unused in R9 and R23")
    new_a=sorted(unused,key=lambda gid:hashed(SEED+":SHA:"+gid))[:192]
    new_b=sorted(unused-set(new_a),key=lambda gid:
                 (-len(eligible[gid].reactions),hashed(SEED+":DEG:"+gid)))[:96]
    need(len(new_a)==192 and len(new_b)==96,"prospective gene selection short")
    all_a=new_a+sha[:192]
    all_b=new_b+degree[:288]
    need(len(all_a)==len(all_b)==384 and not(set(all_a)&set(all_b)),
         "non-disjoint future 384 family")
    need(set(all_a)!=set(sha) and set(all_b)!=set(degree) and
         not set(all_a)&oldgenes and not set(all_b)&oldgenes,
         "R24 test must be new combinations disjoint from original R9")
    cohorts={fam:{str(n):genes[:n] for n in SIZES}
             for fam,genes in zip(FAMILIES,(all_a,all_b))}
    # R23 outcomes determine positive/negative training LABELS only.
    # All structural feature computations are source-only and are frozen
    # before any R24 test solver is executed.
    training={}
    for n in SIZES:
        samples=[]
        for fam in r23.FAMILIES:
            data=report["families"][fam][str(n)]
            need(len(data["paired_speedups"])==3,"insufficient R23 training repeats")
            positive=(data["control_faster_reps"]==3 and
                      data["ratio_of_medians"]>=1.04)
            genes=previous["gene_families"][fam][str(n)]
            samples.append(dict(family=fam,positive=positive,
                                feature=fingerprint(model,genes,rules),
                                ratio_of_medians=data["ratio_of_medians"],
                                wins=data["control_faster_reps"]))
        training[str(n)]=samples
    need(all(x["positive"] for x in training["96"]),"R23 96 not robustly positive")
    for n in (192,384):
        need(sum(x["positive"] for x in training[str(n)])==1,
             "cannot fit selective frozen R24 router")
    frozen={
      "protocol":PROTOCOL,"model_sha":SOURCE_SHA,
      "r9_original_gene_sha":sig(r9old["cohorts"]["384"]),
      "r23_training_manifest_digest":previous["manifest_digest"],
      "r23_source_run":42420380424,
      "policy":"N96 share12; N192/384 use share12 only when source-only distance to R23 positive training point is safely smaller than negative; else exact R9",
      "positive_distance_ratio_max":0.60,
      "positive_distance_max":2.0,
      "features":"log1p(mean source degree), log1p(mean direct GPR disabling), disabling fraction",
      "r23_training":training,
      "cohorts":cohorts,
      "cohort_sha":{f:{str(n):sig(v[str(n)]) for n in SIZES}
                    for f,v in cohorts.items()},
      "families_disjoint":True,
      "original_R9_genes_excluded":True,
      "new_genes_unused_R9_R23_familyA_192":True,
      "new_genes_unused_R9_R23_familyB_96":True,
      "N384_mix_uses_some_historical_R23_genes":True,
      "no_phenotype_or_runtime_used_to_select_R24_test":True,
      "same_bacterial_organism":True,
      "no_external_holdout":True,"not_native_DRNAS":True,
      "sizes":list(SIZES),"reps":REPS,"arms":list(ARMS),
      "CAP_s":CAP,
    }
    frozen["digest"]=digest(frozen)
    save(out,frozen)
    print("R24_PRECOMMIT",json.dumps({
       "digest":frozen["digest"],"cohort_sha":frozen["cohort_sha"],
       "train_labels":{k:[x["positive"] for x in v] for k,v in training.items()},
       "fully_new_gene_counts":{"unseen_sha_mix":192,"unseen_degree_mix":96},
       "mixed_384_uses_some_prior_gene_identities":True},sort_keys=True),flush=True)

def certified_frozen(path):
    d=load(path)
    need(d["protocol"]==PROTOCOL and d["model_sha"]==SOURCE_SHA
         and d["digest"]==digest(d),"R24 frozen gate/holdout SHA mismatch")
    need(set(d["cohorts"])==set(FAMILIES) and d["sizes"]==list(SIZES)
         and d["reps"]==REPS and d["arms"]==list(ARMS),
         "R24 freeze schema drift")
    for fam in FAMILIES:
        for n in SIZES:
            genes=d["cohorts"][fam][str(n)]
            need(len(genes)==n and len(set(genes))==n and
                 sig(genes)==d["cohort_sha"][fam][str(n)],
                 "R24 cohort hash invalid")
        need(d["cohorts"][fam]["384"][:192]==d["cohorts"][fam]["192"]
             and d["cohorts"][fam]["384"][:96]==d["cohorts"][fam]["96"],
             "R24 non-nested")
    need(not(set(d["cohorts"][FAMILIES[0]]["384"])&
             set(d["cohorts"][FAMILIES[1]]["384"])),"R24 family overlap")
    return d

def decide(n,model,genes,rules,frozen):
    start=time.perf_counter()
    feature=fingerprint(model,genes,rules)
    training=frozen["r23_training"][str(n)]
    positives=[x for x in training if x["positive"]]
    negatives=[x for x in training if not x["positive"]]
    if n==96:
        need(len(positives)==2 and not negatives,"R24 N96 training drift")
        choice="share_12_control"
        reason="two_R23_families_both_3of3_positive"
        posdist=None
        negdist=None
    else:
        need(len(positives)==len(negatives)==1,"R24 N192/384 training drift")
        posdist=metric_distance(feature,positives[0]["feature"])
        negdist=metric_distance(feature,negatives[0]["feature"])
        passed=(posdist < frozen["positive_distance_max"] and
                posdist < frozen["positive_distance_ratio_max"]*negdist)
        choice="share_12_control" if passed else "r9_baseline"
        reason="high_confidence_GPR_structure" if passed else "conservative_R9_fallback"
    elapsed=time.perf_counter()-start
    return dict(selected=choice,reason=reason,
                feature=feature,positive_distance=posdist,
                negative_distance=negdist,decision_seconds=round(elapsed,7),
                trained_only_on="R23_locked_18_pairs")

def run_arm(source,genes,arm,rep,family,n,frozen):
    start=time.perf_counter()
    model,meta=r8.load_frozen(source)
    rules=r8.all_rules(model)
    threshold=float(meta["wildtype_biomass"])*.01
    need(meta["SBML_sha256"]==SOURCE_SHA and threshold>0,
         "source model/medium mismatch")
    selected=arm
    routing=None
    if arm=="r24_guarded":
        routing=decide(n,model,genes,rules,frozen)
        selected=routing["selected"]
    if selected=="r9_baseline":
        result=r9.solve(model,genes,rules,threshold,CAP)
        bridge={"solver_creations":3,"mode":"original_R9"}
    elif selected=="share_12_control":
        coord=r15.BoundaryCoordinator(OriginalSolver,genes,rules,"share_12")
        try:
            with patch("pysat.solvers.Solver",coord.factory):
                result=r9.solve(model,genes,rules,threshold,CAP)
        finally:
            coord.close()
        bridge=coord.audit()
        need(bridge["solver_creations"]==2 and
             bridge["boundary_reset_after_k"]==[2],
             "wrong share12 solver boundary")
    else:
        raise RuntimeError("unknown R24 solver route")
    need(result["status"]=="SOLVED" and
         result["SAT_UNSAT_stages"]==3 and
         result["lp_calls"]==result["viable_lp"]+result["lethal_lp"],
         "R24 original full SAT/FBA solve failed")
    timed=result["wall_s"]+(routing["decision_seconds"] if routing else 0.0)
    oracle_start=time.perf_counter()
    # Mandatory fresh model to avoid R19/20 GLPK mutation-based stalling.
    fresh,freshmeta=r8.load_frozen(source)
    fresh_rules=r8.all_rules(fresh)
    need(freshmeta["SBML_sha256"]==meta["SBML_sha256"] and
         {k:v[0] for k,v in fresh_rules.items()}==
         {k:v[0] for k,v in rules.items()},"independent GLPK rule mismatch")
    checked=r9.verify_sets(fresh,genes,fresh_rules,threshold,result["minimal_sets"])
    oracle_s=time.perf_counter()-oracle_start
    need(checked["sound_minimal"] and
         checked["FBA_calls"]==checked["independent_checks"],
         "independent gene-vs-reaction FBA failed")
    row={
      "protocol":PROTOCOL,"arm":arm,"selected":selected,
      "family":family,"n":n,"rep":rep,"frozen_digest":frozen["digest"],
      "gene_sha":sig(genes),"source_sha":SOURCE_SHA,
      "wall_s":result["wall_s"],
      "effective_wall_s":round(timed,6),
      "decision_seconds":routing["decision_seconds"] if routing else 0.0,
      "full_trial_wall_s":round(time.perf_counter()-start,6),
      "independent_oracle_s":round(oracle_s,6),
      "minimal_sets":[list(x) for x in canon(result["minimal_sets"])],
      "minimal_count":len(result["minimal_sets"]),
      "LP_requests":result["lp_calls"],"SAT_calls":result["sat_calls"],
      "flux_cuts":result["flux_cuts"],
      "router":routing,"bridge":bridge,
      "independent_FBA_checks":checked["FBA_calls"],
      "independent_sound":True,"exact_stage_count":3,
      "same_original_R9_algorithm":True,
    }
    print("R24_TRIAL",json.dumps({k:row[k] for k in (
      "family","n","rep","arm","selected","wall_s","effective_wall_s",
      "decision_seconds","LP_requests","minimal_count",
      "independent_FBA_checks","independent_sound")},
      sort_keys=True),flush=True)
    return row

def paired(source,r9f,manifest,family,n,rep,out):
    d=certified_frozen(manifest)
    prior=r9.check_manifest(source,r9f)
    need(sig(prior["cohorts"]["384"])==d["r9_original_gene_sha"],
         "prior R9 frozen source changed")
    genes=d["cohorts"][family][str(n)]
    need(not set(genes)&set(prior["cohorts"]["384"]),
         "R24 test accidentally overlaps old R9 genes")
    orders=(ARMS,ARMS[1:]+ARMS[:1],ARMS[2:]+ARMS[:2])
    rows=[]
    for arm in orders[rep]:
        row=run_arm(source,genes,arm,rep,family,n,d)
        rows.append(row)
        save(out,{"protocol":PROTOCOL,"complete":False,"rows":rows})
    reference=canon(rows[0]["minimal_sets"])
    need(all(canon(r["minimal_sets"])==reference for r in rows),
         "R24 arm interventions disagree")
    need(len({r["minimal_count"] for r in rows})==1,
         "R24 arm minimal intervention counts differ")
    complete={"protocol":PROTOCOL,"complete":True,"frozen_digest":d["digest"],
              "family":family,"n":n,"rep":rep,"rows":rows,
              "all_arm_minimal_sets_equal":True}
    save(out,complete)
    by={r["arm"]:r for r in rows}
    print("R24_PAIR_PASS",json.dumps({
      "family":family,"n":n,"rep":rep,
      "R9_s":by["r9_baseline"]["wall_s"],
      "share12_s":by["share_12_control"]["wall_s"],
      "guarded_effective_s":by["r24_guarded"]["effective_wall_s"],
      "chosen":by["r24_guarded"]["selected"],
      "speedup_guarded_vs_R9":round(by["r9_baseline"]["wall_s"]/
                                     by["r24_guarded"]["effective_wall_s"],6),
      "minima":by["r9_baseline"]["minimal_count"],
      "independent_FBA":True},sort_keys=True),flush=True)

def audit(paths,manifest,out):
    d=certified_frozen(manifest)
    cases=[load(p) for p in paths]
    wanted={(f,n,rep) for f in FAMILIES for n in SIZES for rep in range(REPS)}
    seen={(v["family"],v["n"],v["rep"]) for v in cases}
    need(len(cases)==18 and seen==wanted,"R24 incomplete/duplicate matrix")
    detail={}
    totals={arm:0.0 for arm in ARMS}
    total_wins={arm:0 for arm in ARMS[1:]}
    for f in FAMILIES:
        detail[f]={}
        for n in SIZES:
            rows=[next(v for v in cases if v["family"]==f
                       and v["n"]==n and v["rep"]==rep) for rep in range(REPS)]
            med={}
            speeds={}
            route=[]
            series={}
            for arm in ARMS:
                times=[]
                for case in rows:
                    need(case["complete"] and case["protocol"]==PROTOCOL and
                         case["frozen_digest"]==d["digest"] and
                         case["all_arm_minimal_sets_equal"],
                         "R24 partial/wrong frozen case")
                    by={r["arm"]:r for r in case["rows"]}
                    need(len(case["rows"])==3 and set(by)==set(ARMS),
                         "R24 arm missing")
                    result=by[arm]
                    need(result["independent_sound"] and
                         result["exact_stage_count"]==3 and
                         result["gene_sha"]==d["cohort_sha"][f][str(n)] and
                         result["source_sha"]==SOURCE_SHA and
                         result["minimal_count"]>=0 and
                         result["independent_FBA_checks"]>=1 and
                         result["wall_s"]>0 and
                         math.isfinite(result["effective_wall_s"]),
                         "R24 biological/cost/source mismatch")
                    need(canon(result["minimal_sets"])==
                         canon(by["r9_baseline"]["minimal_sets"]),
                         "R24 different biological interventions")
                    need(result["selected"] in ("r9_baseline","share_12_control"),
                         "invalid router decision")
                    if arm=="r24_guarded":
                        need(result["router"]["selected"]==result["selected"] and
                             result["decision_seconds"]>=0,
                             "R24 router telemetry invalid")
                    else:
                        need(result["selected"]==arm and
                             result["decision_seconds"]==0,
                             "changed reference algorithms")
                    duration=result["effective_wall_s"]
                    times.append(duration)
                    totals[arm]+=duration
                series[arm]=times
                med[arm]=round(statistics.median(times),6)
            for arm in ARMS[1:]:
                speeds[arm]=[round(a/b,6) for a,b in
                             zip(series["r9_baseline"],series[arm])]
                total_wins[arm]+=sum(v>1 for v in speeds[arm])
            route=[{r["arm"]:r for r in case["rows"]}["r24_guarded"]["selected"]
                   for case in rows]
            detail[f][str(n)]={
              "median_seconds":med,
              "speedup_guarded_vs_R9":round(med["r9_baseline"]/
                                            med["r24_guarded"],6),
              "paired_speedups":speeds,
              "guarded_wins":sum(x>1 for x in speeds["r24_guarded"]),
              "unconditional_share_wins":sum(x>1 for x in speeds["share_12_control"]),
              "selected_routes":route,
              "minima":{r["arm"]:r["minimal_count"] for r in rows[0]["rows"]},
            }
    result={
      "status":"R24_FROZEN_HOLDOUT_BIOLOGICAL_AUDIT_PASS",
      "protocol":PROTOCOL,"total_trials":54,"paired_cases":18,
      "frozen_digest":d["digest"],"family_results":detail,
      "totals_s":{arm:round(v,6) for arm,v in totals.items()},
      "aggregate_ratio_R9_over_guard":round(totals["r9_baseline"]/
                                              totals["r24_guarded"],6),
      "aggregate_ratio_R9_over_always_share":round(totals["r9_baseline"]/
                                              totals["share_12_control"],6),
      "paired_wins":total_wins,
      "no_regression_claim_if_any_slower":total_wins["r24_guarded"]==18,
      "r23_results_used_ONLY_for_training":True,
      "holdout_combinations_precommitted":True,
      "not_all_genes_new":True,
      "same_iML1515_source":True,"no_new_organism":True,
      "not_native_DRNAS":True,"no_world_record_claim":True,
      "timing_scope":"solver wall plus selector CPU only, excluding independent postsolve oracle/model loading",
    }
    save(out,result)
    print("R24_FINAL",json.dumps({
      "status":result["status"],"paired_cases":18,"total_trials":54,
      "aggregate_ratio_R9_over_guard":result["aggregate_ratio_R9_over_guard"],
      "aggregate_ratio_R9_over_always_share":
         result["aggregate_ratio_R9_over_always_share"],
      "paired_wins":result["paired_wins"],
      "no_regression_claim_if_any_slower":result["no_regression_claim_if_any_slower"],
      "family_results":detail},sort_keys=True),flush=True)

def selftest():
    need(REPS==3 and len(ARMS)==3 and
         SIZES==(96,192,384) and CAP==150.0,"R24 protocol drift")
    need(r9.SOURCE_SHA==SOURCE_SHA and len(FAMILIES)==2,
         "R24 original frozen source changed")
    assert metric_distance([1.,1.,1.],[1.,1.,1.])==0
    print("R24_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("selftest","freeze","paired","audit"))
    for a in ("source","r9-frozen","r23-manifest","r23-report",
              "manifest","family","out"):
        p.add_argument("--"+a)
    p.add_argument("--n",type=int)
    p.add_argument("--rep",type=int)
    p.add_argument("--inputs",nargs="*")
    x=p.parse_args()
    faulthandler.enable()
    faulthandler.dump_traceback_later(60,repeat=True,file=sys.stderr)
    try:
        if x.cmd=="selftest":selftest()
        elif x.cmd=="freeze":
            need(x.source and x.r9_frozen and x.r23_manifest and
                 x.r23_report and x.out,"incomplete freeze arguments")
            build_freeze(x.source,x.r9_frozen,x.r23_manifest,x.r23_report,x.out)
        elif x.cmd=="paired":
            need(x.source and x.r9_frozen and x.manifest and
                 x.family in FAMILIES and x.n in SIZES and
                 x.rep in range(REPS) and x.out,"invalid paired arguments")
            paired(x.source,x.r9_frozen,x.manifest,x.family,x.n,x.rep,x.out)
        else:
            need(x.manifest and x.inputs and x.out,"invalid audit arguments")
            audit(x.inputs,x.manifest,x.out)
    finally:
        faulthandler.cancel_dump_traceback_later()
