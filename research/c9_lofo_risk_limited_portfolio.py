#!/usr/bin/env python3
"""DRNAS C9 — risk-penalized ONE-STEP structural portfolio gate, LOFO evaluation.

No new solver run. Source-locked development C8D: 19 original SHA x 10 arms
x 2 repetitions, 15s PAR2. LOFO = leave one complete original formula out
for selecting ONE conjunct-free source-only predicate and ONE backend.
Fallback always CaDiCaL default; NO online pilot overhead, only source scan
(c8d source features were measured in source-only prefix); scan overhead
is charged 2x, once per paired repetition, even if default chosen.
One baseline policy and rule thresholds are frozen by this source before
reading any C8D run results. Prescreened C8D development cohort is NOT
genuinely independent blind; this is an internal stability test ONLY.

No regression protection guarantee: source-level LOO can overfit to strong
outliers. Report worst missed source, solved deltas, and outlier sensitivity.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,pathlib,statistics
OUT=pathlib.Path("c9_out")
PRIOR=pathlib.Path("c9_prior_c8d")
PROTO="DRNAS-C9-LOFO-19SHA-SOURCE-ONLY-STUMP-6SOLVERS-NO-PILOT-v1"
C8D_PROTO="DRNAS-C8D-C7-BVE-EARLY-CDCL-19SHA-10ARM-2REP-15S-v1"
BASE="cadical"
REPS=2
CAP=15.0
ALTERNATES=("cadical_noelim","cadical_noelim_novivify",
 "cadical_novivify","kissat","cms_native","cms_dedup_nobve")
# Finite prespecified feature thresholds, no outcome-dependent split generation.
THRESHOLDS={
 "binary_fraction":(.05,.25,.90,.97,.995),
 "horn_fraction":(.55,.80,.95,.995),
 "duplicate_fraction":(.005,.025,.05),
 "pair_drop_fraction":(.05,.10,.20),
 "nvars":(100,500,1500,5000,10000),
 "source_BVE_eligible_proxy":(0,100,1000),
 "proxy_flips_on":(0,),
 "scan_truncated":(.5,),
}
MIN_SUPPORT=3
MAX_SELECTED_SHARE=.60
MAX_TRAIN_CASE_REGRESSION_S=2.0
MIN_TRAIN_GAIN_S=5.0
MIN_RELATIVE_TRAIN_BENEFIT=.10
MIN_WHOLE_TRAIN_GAIN_FRACTION=.03

def need(ok,why):
    if not ok:raise RuntimeError("C9_FAIL_CLOSED "+str(why))
def load():
    r=PRIOR/"report.json"
    need(r.is_file(),"original C8D final report missing")
    report=json.loads(r.read_text())
    need(report["status"]=="C8D_E2E_AUDIT_PASS" and
         report["protocol"]==C8D_PROTO and report["source_count"]==19 and
         report["full_trials"]==380 and report["cap_s"]==CAP and
         report["repeats"]==REPS and report["no_auto_promotion"],
         "C8D original 19 SHA source lock/audit mismatch")
    rr=[]
    for i in range(5):
        p=PRIOR/("shard-%d.json"%i)
        need(p.is_file(),"original C8D shard missing")
        a=json.loads(p.read_text())
        rr+=a
    need(len(rr)==380,"not all 380 real timed attempts recovered")
    by=collections.defaultdict(dict)
    for x in rr:
        need(x["protocol"]==C8D_PROTO and
             x["mode"] in (BASE,*ALTERNATES,"cms_nobve","c8_bve_static","c8_bve_early") and
             x["rep"] in range(REPS) and x["cap_s"]==CAP,
             "alien original SHA/rep/mode/cap")
        key=(x["source_sha256"],x["rep"])
        need(x["mode"] not in by[key],"duplicate same source/repetition arm")
        by[key][x["mode"]]=x
        need(x["status"] in ("SAT","UNSAT","TIMEOUT") and
             x["par2_s"]>0,"bad original terminal row")
        need(x["status"]!="SAT" or x["original_SAT_witness_verified"],
             "original SAT witness not validated")
        need(x["status"]!="TIMEOUT" or x["par2_s"]==30.0,
             "timeout must be cap*2 PAR2")
    need(len(by)==19*REPS and all(len(v)==10 for v in by.values()),
         "original C8D ten-arm paired source matrix incomplete")
    cases=report["per_source"]
    need(len(cases)==19 and len({x["sha256"] for x in cases})==19,
         "C8D source features missing or duplicate")
    orig_sha={x["source_sha256"] for x in rr}
    need({x["sha256"] for x in cases}==orig_sha,"source SHA changed vs trials")
    for c in cases:
        f=c["BVE_proxy"]
        need(0<=f["scan_cost_s"]<=2.0 and f["nvars"]>0,
             "invalid source-only scan timing")
        for mode in (BASE,*ALTERNATES):
            a=[by[(c["sha256"],rep)][mode] for rep in range(REPS)]
            summed=round(sum(x["par2_s"] for x in a),6)
            v=c["by_mode"][mode]
            need(abs(summed-v["PAR2_s"])<=0.000002 and
                 sum(x["status"]!="TIMEOUT" for x in a)==v["solved"],
                 "reference per-source scores drifted")
    return report,cases,by

def rules():
    return [(f,float(th),op)
            for f,values in THRESHOLDS.items()
            for th in values for op in ("ge","le")]
def match(c,rule):
    f,threshold,op=rule
    v=float(c["BVE_proxy"][f])
    return v>=threshold if op=="ge" else v<=threshold
def by(c,mode):
    return c["by_mode"][mode]
def select(train):
    need(len(train)>=16,"train too small for LOFO")
    train_total=sum(by(c,BASE)["PAR2_s"] for c in train)
    candidates=[]
    for rule in rules():
        selected=[c for c in train if match(c,rule)]
        if (len(selected)<MIN_SUPPORT or
            len(selected)>len(train)*MAX_SELECTED_SHARE):
            continue
        chosen_baseline=sum(by(c,BASE)["PAR2_s"] for c in selected)
        for mode in ALTERNATES:
            dif=[by(c,mode)["PAR2_s"]-by(c,BASE)["PAR2_s"]
                 for c in selected]
            gain=-sum(dif)
            worst=max(dif)
            solved_delta=sum(by(c,mode)["solved"]-by(c,BASE)["solved"]
                for c in selected)
            if (gain<max(MIN_TRAIN_GAIN_S,train_total*MIN_WHOLE_TRAIN_GAIN_FRACTION)
                or gain/max(1e-9,chosen_baseline)<MIN_RELATIVE_TRAIN_BENEFIT
                or solved_delta<0 or worst>MAX_TRAIN_CASE_REGRESSION_S):
                continue
            score=gain-0.5*max(0,worst)-.1*sum(d>0 for d in dif)
            candidates.append(dict(rule=rule,mode=mode,
                support=len(selected),train_gain_s=round(gain,6),
                train_worst_regression_s=round(worst,6),
                train_extra_solved=solved_delta,score=round(score,6)))
    if not candidates:return None
    # Tie-break by fixed rule list priority and backend spelling, not test data.
    candidates.sort(key=lambda x:(-x["score"],x["rule"][0],
        x["rule"][1],x["rule"][2],x["mode"]))
    return candidates[0]
def score_case(c,mode):
    return dict(solved=by(c,mode)["solved"],par2_s=by(c,mode)["PAR2_s"])
def score():
    report,cases,_=load()
    cases=sorted(cases,key=lambda c:c["sha256"])
    folds=[]
    for c in cases:
        training=[a for a in cases if a["sha256"]!=c["sha256"]]
        need(len(training)==18,"LOFO train includes held-out source")
        rule=select(training)
        route=rule["mode"] if rule and match(c,rule["rule"]) else BASE
        a=score_case(c,route);b=score_case(c,BASE)
        fee=2*float(c["BVE_proxy"]["scan_cost_s"])
        folds.append(dict(source_sha256=c["sha256"],cohort=c["cohort"],
            source_nvars=c["BVE_proxy"]["nvars"],selected_rule=rule,
            source_selected=route!=BASE,
            selected_backend=route,
            base_par2_s=b["par2_s"],LOFO_solver_par2_s=a["par2_s"],
            charged_source_scan_s=round(fee,6),
            LOFO_charged_par2_s=round(a["par2_s"]+fee,6),
            base_solved=b["solved"],LOFO_solved=a["solved"],
            delta_par2_s=round(a["par2_s"]+fee-b["par2_s"],6)))
    baseline=round(sum(x["base_par2_s"] for x in folds),6)
    model=round(sum(x["LOFO_charged_par2_s"] for x in folds),6)
    solved_base=sum(x["base_solved"] for x in folds)
    solved_model=sum(x["LOFO_solved"] for x in folds)
    need(solved_base==report["scores"][BASE]["solved"] and
         abs(baseline-report["scores"][BASE]["PAR2_s"])<0.000002,
         "LOFO underlying baseline changed")
    selected=[x for x in folds if x["source_selected"]]
    wins=[x for x in folds if x["delta_par2_s"]<0]
    regression=[x for x in folds if x["delta_par2_s"]>0]
    dominant=max(folds,key=lambda x:x["base_par2_s"]-x["LOFO_charged_par2_s"])
    rest_b=baseline-dominant["base_par2_s"]
    rest_m=model-dominant["LOFO_charged_par2_s"]
    final_policy=select(cases)
    report=dict(protocol=PROTO,
        training_data="C8D 19 development original SHA; NOT BLIND; no real new solver execution",
        source_SHA_count=19,source_cohorts=sorted({x["cohort"] for x in folds}),
        C8D_run_id=42526134599,C8D_total_real_E2E_trials=380,
        paired_repetitions_per_source=REPS,
        pilot_s=0,charged_source_scan_for_each_repetition=True,
        source_only_features=True,one_variable_threshold_single_backend=True,
        rule_thresholds_frozen_in_code=True,
        fold_train_sources=18,fold_test_sources=1,
        no_aggregate_oracle_leakage=True,
        independent_external_solver_seeds=False,
        original_SAT_witness_verified=True,
        independent_UNSAT_LRAT=False,
        cap_s=CAP,
        baseline_CaDiCaL_PAR2_s=baseline,
        LOFO_charge_included_PAR2_s=model,
        speedup_vs_CaDiCaL_PAR2_x=round(baseline/model,6),
        solved_CaDiCaL=solved_base,
        solved_LOFO=solved_model,
        selected_source_count=len(selected),
        winning_source_count=len(wins),
        regressed_source_count=len(regression),
        max_regression_s=round(max([x["delta_par2_s"] for x in folds]+[0]),6),
        largest_single_source_gain_s=round(
            dominant["base_par2_s"]-dominant["LOFO_charged_par2_s"],6),
        largest_gain_source_sha256=dominant["source_sha256"],
        speedup_excluding_biggest_gain_x=round(rest_b/rest_m,6),
        final_all19_candidate_rule_for_future_prospective_test=final_policy,
        no_auto_promotion=True,
        required_next_step="prospective disjoint 2026 ORIGINAL SHA run with predeclared rule and equal cap",
        folds=folds)
    OUT.mkdir(exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("C9_FINAL",json.dumps({k:v for k,v in report.items() if k!="folds"},
                               sort_keys=True),flush=True)
    for x in folds:
        print("C9_LOFO_CASE",json.dumps(dict(sha=x["source_sha256"],
          nvars=x["source_nvars"],mode=x["selected_backend"],
          baseline=x["base_par2_s"],LOFO=x["LOFO_charged_par2_s"],
          delta=x["delta_par2_s"],
          train_rule=x["selected_rule"]["rule"] if x["selected_rule"] else None),
          sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("verify","score"))
    a=p.parse_args()
    if a.action=="verify":
        r,c,by=load()
        print("C9_PRIOR_19SHA_380_REAL_ROWS_VALIDATED",len(c),len(by),flush=True)
    else:score()
