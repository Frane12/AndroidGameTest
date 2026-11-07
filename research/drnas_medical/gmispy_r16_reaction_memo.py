#!/usr/bin/env python3
"""DRNAS Medical R16 — exact reaction-signature FBA memoization at k=3.

Scientific question: can identical GPR-derived disabled-reaction sets across
different candidate gene knockouts safely avoid redundant primal LP solves?
All SAT/FBA algorithms and the published iML1515 model remain unchanged.

The memo key is the **complete, exact disabled-reaction signature** computed
from the original GPR rules, not a heuristic approximate fingerprint.
This is an optimization of FBA re-evaluation, NOT a new SAT proof method.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,pathlib,statistics,time
from unittest.mock import patch
from pysat.solvers import Solver as OriginalSolver

import gmispy_r3 as r3
import gmispy_r8_iml1515 as r8
import gmispy_r9_scaling as r9
import gmispy_r11_phenotype_cache as r11
import gmispy_r14_cross_stage as r14
import gmispy_r15_stage_boundary as r15

PROTO="DRNAS-MEDICAL-R16-EXACT-GPR-FBA-SIGNATURE-MEMO-20261107-v1"
SIZES=(24,48,96,192,384)
REPS=3
CAP=150.0
ARMS=("r9_baseline","share_12_control","share_12_memo_k3",
      "share_12_memo_all","gated_fresh_memo_k3")
SOURCE_SHA=r9.SOURCE_SHA
VALIDATE_HIT_NUMBERS=(1,2,8,32,128,512)
need=r14.need
save=r14.save
load=r14.load
canon=r14.canon

class CertifiedReactionMemo:
    """Memo *verified reaction-deletion phenotype* and primal witness.

    The same GPR function yields identical disabled reactions for any KO
    sets with equal reaction signatures. Consequently their FBA *feasible
    region* and objective coincide for one fixed frozen model. A stored
    growth/flux result is reusable for that exact signature. All other
    original LP calls remain unchanged. Re-check a predeclared subset of
    hits by independent original LP computations.
    """
    def __init__(self,original,genes,rules,threshold,mode):
        self.original=original
        self.genes=tuple(genes)
        self.rules=rules
        self.threshold=float(threshold)
        self.mode=mode
        self.cache={}
        self.counts=collections.Counter()
        self.stage=collections.defaultdict(collections.Counter)
        self.first_result_by_signature={}
        self.samples=[]
        self.signatures_by_stage=collections.defaultdict(set)
    def __call__(self,model,genes,ko,rules,matrix,rxns,threshold):
        need(tuple(genes)==self.genes and rules is self.rules,
             "FBA memo called outside frozen matching GPR/rule set")
        need(abs(float(threshold)-self.threshold)<1e-12,
             "threshold differs across memoized results")
        ko=tuple(ko)
        k=len(ko)
        need(0<=k<=3,"unexpected KO cardinality")
        self.counts["requests"]+=1
        self.stage[k]["requests"]+=1
        active=k>=1 and (self.mode=="all" or k==3)
        if not active:
            self.counts["uncached_original_LP"]+=1
            self.stage[k]["uncached_original_LP"]+=1
            return self.original(model,genes,ko,rules,matrix,rxns,threshold)
        key=r3.disabled_reactions(rules,(genes[i] for i in ko))
        self.signatures_by_stage[k].add(key)
        need(key==tuple(sorted(set(key))),"signature not canonical")
        self.counts["signature_checks"]+=1
        self.stage[k]["signature_checks"]+=1
        if key not in self.cache:
            value=self.original(model,genes,ko,rules,matrix,rxns,threshold)
            self.cache[key]=value
            self.first_result_by_signature[key]=(k,ko)
            self.counts["memo_miss_original_LP"]+=1
            self.stage[k]["memo_miss_original_LP"]+=1
            return value
        self.counts["memo_hits"]+=1
        self.stage[k]["memo_hits"]+=1
        cached=self.cache[key]
        hit_id=self.counts["memo_hits"]
        # Validation is charged. Always use the original unpatched
        # certified_flux for sampled hits, not another cache.
        if hit_id in VALIDATE_HIT_NUMBERS:
            reference=self.original(model,genes,ko,rules,matrix,rxns,threshold)
            self.counts["independent_hit_rechecks"]+=1
            self.stage[k]["independent_hit_rechecks"]+=1
            a,b=cached[0],reference[0]
            need(bool(cached[2])==bool(reference[2]),
                 "cached FBA phenotype differs from original LP")
            need(abs(float(a)-float(b))<=1e-6,
                 "cached FBA optimum differs from original LP")
            self.samples.append(dict(hit=hit_id,k=k,reference_growth=float(b),
                  cached_growth=float(a),signature_reactions=len(key)))
        return cached
    def report(self):
        total_requests=sum(x["requests"] for x in self.stage.values())
        need(total_requests==self.counts["requests"],"cache accounting drift")
        actual_LP=(self.counts["uncached_original_LP"]+
                   self.counts["memo_miss_original_LP"]+
                   self.counts["independent_hit_rechecks"])
        need(actual_LP+self.counts["memo_hits"]-
             self.counts["independent_hit_rechecks"]==total_requests,
             "physical LP accounting mismatch")
        return dict(requests=total_requests,actual_LP=actual_LP,
            LP_avoided=total_requests-actual_LP,
            memo_hits=self.counts["memo_hits"],
            memo_misses=self.counts["memo_miss_original_LP"],
            signature_evaluations=self.counts["signature_checks"],
            hit_rechecks=self.counts["independent_hit_rechecks"],
            unique_reaction_signatures=len(self.cache),
            stage={str(k):dict(v) for k,v in sorted(self.stage.items())},
            stage_distinct_signatures={
               str(k):len(v) for k,v in sorted(self.signatures_by_stage.items())},
            validation_samples=self.samples)

def selftest():
    need(SIZES==(24,48,96,192,384) and REPS==3 and CAP==150.0,"frozen protocol")
    need(len(ARMS)==5 and r9.SOURCE_SHA==SOURCE_SHA,"wrong frozen source")
    need(all(s in ARMS for s in ("share_12_control","share_12_memo_k3",
          "share_12_memo_all")),"missing controls")
    # GPR signature memo invariance: KO identity may differ while reaction
    # state matches. Verify on a tiny Boolean rule with two equivalent genes.
    rules={"r":(None,None,lambda knocked: not ({"a","b"}.issubset(knocked)))}
    assert r3.disabled_reactions(rules,["a"])==()
    assert r3.disabled_reactions(rules,["b"])==()
    assert r3.disabled_reactions(rules,["a","b"])==("r",)
    print("R16_SELFTEST_PASS",flush=True)

def trial(model,genes,rules,threshold,expected,arm,rep,n):
    need(arm in ARMS and rep in range(REPS),"invalid trial arm/rep")
    start=time.perf_counter()
    memo=None;coord=None
    if arm=="r9_baseline":
        result=r9.solve(model,genes,rules,threshold,CAP)
        bridge={"mode":"R9_unmodified","solver_creations":3}
    else:
        mode=("gated_fresh" if arm=="gated_fresh_memo_k3"
              else "share_12")
        coord=r15.BoundaryCoordinator(OriginalSolver,genes,rules,mode)
        memo_mode=("all" if arm=="share_12_memo_all" else "k3")
        memo=CertifiedReactionMemo(r9.certified_flux,genes,rules,threshold,memo_mode)
        try:
            with patch("pysat.solvers.Solver",coord.factory):
                if arm=="share_12_control":
                    result=r9.solve(model,genes,rules,threshold,CAP)
                else:
                    with patch.object(r9,"certified_flux",memo):
                        result=r9.solve(model,genes,rules,threshold,CAP)
        finally:
            coord.close()
        bridge=coord.audit()
    driver_s=time.perf_counter()-start
    need(result["status"]=="SOLVED" and
         result["SAT_UNSAT_stages"]==3,"incomplete original 3-stage search")
    need(canon(result["minimal_sets"])==canon(expected),
         "candidate minimal KOs differ from frozen R10 reference")
    oracle=r9.verify_sets(model,genes,rules,threshold,result["minimal_sets"])
    need(oracle["sound_minimal"],"independent FBA failed")
    stageLP=[result["stages"][0]["lp_calls_total"]]+[
       result["stages"][i]["lp_calls_total"]-
       result["stages"][i-1]["lp_calls_total"] for i in (1,2)]
    stageWall=[result["stages"][0]["wall_elapsed_s"]]+[
       round(result["stages"][i]["wall_elapsed_s"]-
         result["stages"][i-1]["wall_elapsed_s"],6) for i in (1,2)]
    memo_result=memo.report() if arm not in ("r9_baseline","share_12_control") else None
    if memo_result is not None:
        need(memo_result["requests"]==result["lp_calls"],
             "R9 requested LP count differs from memo wrapper")
        need(memo_result["actual_LP"]>=0 and
             memo_result["LP_avoided"]>=0,"negative physical LPs")
        need(memo_result["stage"].get("3",{}).get("requests",0)==stageLP[2],
             "wrong stage3 LP accounting")
    return dict(protocol=PROTO,n=n,rep=rep,arm=arm,
      wall_s=result["wall_s"],driver_s=round(driver_s,6),
      reference_match=True,independent_FBA_sound=True,
      minimum_intervention_count=len(expected),
      gene_SHA=r9.hgenes(genes),source_SHA=SOURCE_SHA,
      LP_requests=result["lp_calls"],SAT_calls=result["sat_calls"],
      flux_cuts=result["flux_cuts"],
      stage_LP_requests=stageLP,stage_wall_s=stageWall,
      physical_LP_calls=(memo_result["actual_LP"] if memo_result else result["lp_calls"]),
      physical_LP_avoided=(memo_result["LP_avoided"] if memo_result else 0),
      memo=memo_result,bridge=bridge,
      no_human_cancer_model=True,no_native_DRNAS=True)

def cohort(source,frozen,reference,n,out):
    need(n in SIZES,"unplanned size")
    genes,expected=r11.frozen_reference(source,frozen,reference,n)
    m,manifest=r8.load_frozen(source)
    threshold=float(manifest["wildtype_biomass"])*.01
    del m
    need(len(genes)==n and threshold>0,"invalid frozen cohort")
    rows=[]
    for rep in range(REPS):
        order=ARMS[rep:]+ARMS[:rep]
        for arm in order:
            model,manifest=r8.load_frozen(source)
            need(abs(float(manifest["wildtype_biomass"])*.01-threshold)<1e-12,
                 "wildtype differs")
            rules=r8.all_rules(model)
            row=trial(model,genes,rules,threshold,expected,arm,rep,n)
            rows.append(row)
            save(out,dict(protocol=PROTO,partial=True,n=n,rows=rows))
            print("R16_TRIAL",json.dumps({k:row[k] for k in
             ("n","rep","arm","wall_s","LP_requests","physical_LP_calls",
              "physical_LP_avoided","SAT_calls","flux_cuts",
              "stage_wall_s","stage_LP_requests","reference_match")}),
              flush=True)
    need(len(rows)==REPS*len(ARMS),"missing paired arms")
    medians={arm:round(statistics.median(x["wall_s"] for x in rows
                 if x["arm"]==arm),6) for arm in ARMS}
    baseline=medians["share_12_control"]
    speedups={arm:round(baseline/medians[arm],6) for arm in ARMS}
    by_arm={}
    for arm in ARMS:
        subset=[x for x in rows if x["arm"]==arm]
        by_arm[arm]=dict(median_seconds=medians[arm],
          median_physical_LP=statistics.median(x["physical_LP_calls"] for x in subset),
          median_avoided_LP=statistics.median(x["physical_LP_avoided"] for x in subset),
          median_stage3_seconds=statistics.median(x["stage_wall_s"][2] for x in subset),
          median_stage3_LP_requests=statistics.median(x["stage_LP_requests"][2]
                                                      for x in subset))
    save(out,dict(protocol=PROTO,partial=False,n=n,rows=rows,
                  medians_s=medians,speedups_vs_share12=speedups,
                  by_arm=by_arm,source_SHA=SOURCE_SHA,
                  full_independent_exhaustive_only_24_48=True))
    print("R16_COHORT_PASS",json.dumps(dict(n=n,medians_s=medians,
      speedups_vs_share12=speedups,by_arm=by_arm),sort_keys=True),flush=True)

def audit(paths,out):
    cases=[load(p) for p in paths]
    need(len(cases)==len(SIZES),"wrong cohort count")
    allrows=[]
    for o,n in zip(cases,SIZES):
        need(o["protocol"]==PROTO and o["n"]==n and not o["partial"]
          and len(o["rows"])==REPS*len(ARMS),"incomplete cohort "+str(n))
        seen={(r["arm"],r["rep"]) for r in o["rows"]}
        need(seen=={(a,i) for a in ARMS for i in range(REPS)},
             "incomplete paired matrix "+str(n))
        for row in o["rows"]:
            need(row["reference_match"] and row["independent_FBA_sound"],
                 "incorrect biological intervention")
            need(row["source_SHA"]==SOURCE_SHA,"source SHA mismatch")
            if row["memo"]:
                need(row["physical_LP_calls"] + row["physical_LP_avoided"]==
                     row["LP_requests"],"cached LP count inaccurate")
        allrows.extend(o["rows"])
    overall={n:next(c for c in cases if c["n"]==n)["by_arm"] for n in SIZES}
    report=dict(status="R16_BIOLOGICAL_CAUSAL_MEMO_AUDIT_PASS",
                protocol=PROTO,n_trials=len(allrows),
                results=overall,
                no_blind_new_biological_source=True,
                no_human_cancer_model=True,
                no_native_DRNAS=True,
                ics_exhaustive_only_24_48=True,
                exact_GPR_signature_no_heuristic_hash=True,
                statistical_scope="3 repeats per cohort; timings shared runners")
    save(out,report)
    print("R16_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cmd",choices=("selftest","cohort","audit"))
    ap.add_argument("--source")
    ap.add_argument("--frozen")
    ap.add_argument("--reference")
    ap.add_argument("--n",type=int)
    ap.add_argument("--out")
    ap.add_argument("--inputs",nargs="*")
    args=ap.parse_args()
    if args.cmd=="selftest":selftest()
    elif args.cmd=="cohort":
        need(args.source and args.frozen and args.reference and args.out,
             "missing frozen source or reference")
        cohort(args.source,args.frozen,args.reference,args.n,args.out)
    else:
        need(args.inputs and args.out,"audit input missing")
        audit(args.inputs,args.out)
