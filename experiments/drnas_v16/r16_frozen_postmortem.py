#!/usr/bin/env python3
"""DRNAS R16 read-only, FROZEN, formula-level postmortem.

This diagnostic does not train, change thresholds, update native solver, rerun
any SAT problem, or treat R16 holdout as a new tuning set. R16 generated random3
and community3 problems are not official benchmarks. Comparator r11_2048_50 is
a separately measured arm on the *same formula, repeat, and runner*, not an
oracle for an alternative solver with identical overhead in all circumstances.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import random
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path("experiments/drnas_v16")
INPUT = ROOT / "r16-results" / "current"
OUT = Path("research/drnas-r16-postmortem")
PINNED_BLOBS = {
    "results.json": "2b6f10b778b566debf83f2c07f86bc8639b1d251",
    "native_decisions.csv": "c2b265789bc0ea15bb0d88b2ae5b1cf932b1cd18",
    "paired.csv": "da3df4fe43cf0215b273f6a96cbe804fa9107ec8",
    "formula_features.csv": "0a51dead07645bf6e84bb16a44dfba84f9e4526c",
}
PROTOCOL_BLOB = "d0ba1f19c73e082026e0f385dc8ce39bff99a7c5"
MODEL_BLOB = "d005747f177008172b49cef5f0b8a6f29c3ffc46"
THRESHOLD = 0.25
R16_RUN = 41426664482
BASE_SNAPSHOT = "c31a02578ff0f98a9dabe8325e9b01392e13be10"
FOLDS = ("random3_development", "random3_test",
         "community3_development", "community3_test")
R16_MODES = ("r16_live50", "r16_live50_strict", "r16_snapshot50")

def check(test: bool, msg: str) -> None:
    if not test:
        raise RuntimeError("R16_DIAGNOSTIC_AUDIT_FAILURE: " + msg)

def blob(path: Path) -> str:
    return subprocess.check_output(["git", "hash-object", str(path)], text=True).strip()

def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def to_float(x):
    if x is None or x == "":
        return None
    n = float(x)
    check(math.isfinite(n), "non-finite metric")
    return n

def num(x):
    n = to_float(x)
    return 0. if n is None else n

def save_csv(path: Path, rows: list[dict], cols: list[str]):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.] * len(xs)
    i = 0
    while i < len(order):
        j = i+1
        while j < len(order) and xs[order[j]] == xs[order[i]]:
            j += 1
        for k in range(i, j):
            r[order[k]] = (i+j-1)/2
        i = j
    return r

def pearson(xs, ys):
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    xy = sum((a-mx)*(b-my) for a,b in zip(xs,ys))
    xx = sum((a-mx)**2 for a in xs)
    yy = sum((b-my)**2 for b in ys)
    if xx <= 1e-20 or yy <= 1e-20:
        return None
    return xy/math.sqrt(xx*yy)

def spearman(xs,ys):
    return pearson(ranks(xs),ranks(ys))

def auroc(rows):
    # Tie-correct AUC for positive measured response, descriptive, not CV.
    pos = [x["score"] for x in rows if x["force_log_gain"]>0]
    neg = [x["score"] for x in rows if x["force_log_gain"]<=0]
    if not pos or not neg:return None
    return sum(1 if a>b else 0.5 if a==b else 0
               for a in pos for b in neg)/(len(pos)*len(neg))

def percentile(items,q):
    if not items:return None
    x=sorted(items)
    k=q*(len(x)-1)
    i=int(k)
    return x[i]*(1-(k-i))+x[min(i+1,len(x)-1)]*(k-i)

def corr_bootstrap(rows, rounds=1500):
    # Fixed-size stratified *formula* bootstrap, not repeated-attempt bootstrap.
    byn=defaultdict(list)
    for row in rows:
        byn[row["n"]].append(row)
    rng=random.Random(161602)
    values=[]
    for _ in range(rounds):
        sample=[rng.choice(group) for _,group in sorted(byn.items())
                for _j in range(len(group))]
        statistic=spearman([x["score"] for x in sample],
                           [x["force_log_gain"] for x in sample])
        if statistic is not None:values.append(statistic)
    return [percentile(values,.025),percentile(values,.975)]

def audit():
    for filename,sha in PINNED_BLOBS.items():
        path=INPUT/filename
        check(path.is_file() and blob(path)==sha,
              "archived source blob changed "+filename)
    check(blob(ROOT/"r16_frozen_live_protocol.json")==PROTOCOL_BLOB,
          "R16 protocol blob changed")
    check(blob(ROOT/"r15-results/current/frozen_trained_models.json")==MODEL_BLOB,
          "frozen R15 model changed")
    cfg=json.loads((ROOT/"r16_frozen_live_protocol.json").read_text())
    summary=json.loads((INPUT/"results.json").read_text())
    assert cfg["trained_model_git_blob_sha"]==MODEL_BLOB
    assert cfg["decision_conflict_checkpoint"]==1024
    assert cfg["intervention_at_conflict"]==2048
    assert cfg["safety_design"]["allowed_thresholds"]["r16_live50"]==THRESHOLD
    assert cfg["trained_model_train_count"]==59
    check(summary["attempts"]==4800 and summary["formulas"]==160
          and summary["preintervention_mismatches"]==0,
          "failed archived R16 completion or 1024-prefix audit")
    check(len(summary["source_artifacts"])==16
          and len(summary["manifests"])==16,
          "16-shard provenance missing")
    manifests=summary["manifests"]
    check(len({case["formula_sha256"] for manifest in manifests
          for case in manifest["cases"]})==160, "formula collision")
    for manifest in manifests:
        check(len(manifest["cases"])==10, "not 10 formulas/shard")
        check(manifest["stable_blob"]=="d280a2ffa28d72aec183323bbea40544d676112d",
              "stable V15.3.1 altered")
        check(manifest["kissat_pin"]=="8af8e56f174b778aef3aa45af9f739b2a5f492c2",
              "Kissat version drift")
        check(manifest["cpu_core"]==0 and manifest["cpu_affinity"]==[0],
              "CPU pin changed")
        check(len({x["metadata"]["seed"] for x in manifest["cases"]})==10,
              "nonunique seeds in shard")
    return cfg,summary

def classify(formulas,decisions,paired,summary):
    check(len(formulas)==160,"expected 160 formula feature rows")
    check(len(decisions)==1440,"expected 1440 native decisions")
    check(len(paired)==1440,"expected 1440 paired comparator rows")
    check(len({x["formula_sha256"] for x in formulas})==160,"feature SHA collision")
    fdict={x["formula"]:x for x in formulas}
    decision_key=defaultdict(list)
    for row in decisions:
        check(row["formula"] in fdict and row["fold"]==fdict[row["formula"]]["fold"],
              "unmatched native decision")
        check(row["mode"] in R16_MODES, "invalid native arm")
        decision_key[(row["formula"],row["mode"])].append(row)
        native=to_float(row["native_score"])
        python=to_float(row["independent_python_score"])
        if native is not None:
            check(python is not None and abs(native-python)<2e-5,
                  "C/Python score parity failure")
            check(row["native_conflict"]=="1024", "wrong checkpoint")
        if row["selected"]=="1":
            check(native is not None and row["native_ready"]=="1",
                  "selected before ready")
        if row["actual_switch_at"]:
            check(row["selected"]=="1" and row["actual_switch_at"]=="2048",
                  "unauthorized action")
    for form in fdict:
        for mode in R16_MODES:
            check(len(decision_key[(form,mode)])==3,
                  "three native repeats missing")
    pindex={}
    for row in paired:
        key=(row["formula"],row["mode"])
        check(key not in pindex,"duplicate paired formula")
        check(row["formula"] in fdict and
              row["formula_sha256"]==fdict[row["formula"]]["formula_sha256"],
              "formula SHA mismatch")
        check(row["fold"]==fdict[row["formula"]]["fold"],
              "provenance fold mismatch")
        pindex[key]=row
    check(len(pindex)==1440,"paired index incomplete")
    results=[]
    for r in formulas:
        f=r["formula"]
        mon=num(r["monitor"])
        forced=num(r["r11_2048_50"])
        live=num(r["r16_live50"])
        check(min(mon,forced,live)>0,"bad PAR-2")
        for arm in ("r16_live50","r11_2048_50"):
            check(abs(num(pindex[(f,arm)]["monitor_par2_s"])-mon)<1e-6,
                  "matched monitor disagreement")
            check(abs(num(pindex[(f,arm)]["treatment_par2_s"])-num(r[arm]))<1e-6,
                  "matched comparator disagreement")
        checks=decision_key[(f,"r16_live50")]
        selected=sum(x["selected"]=="1" for x in checks)
        actual=sum(bool(x["actual_switch_at"]) for x in checks)
        check(selected==int(r["r16_live50_selection_count"])
              and actual==int(r["r16_live50_actual_switch_count"]),
              "actual intervention/selection mismatch")
        n=int(r["n"])
        score=to_float(r["r16_live50_score_median"])
        ready=sum(x["native_ready"]=="1" for x in checks)
        if n<220:
            check(selected==0 and actual==0,
                  "R16 should abstain when n<220")
        if score is not None and n>=220:
            check((score>THRESHOLD)==bool(selected),
                  "reported selected score outside frozen threshold")
        force_log_gain=math.log(mon/forced)
        material_gain=100*(mon-forced)/mon
        live_gain=100*(mon-live)/mon
        outcome=("ineligible_n_lt_220" if n<220 else
                 "no_1024_score" if score is None else
                 "selected_not_applied" if selected and not actual else
                 "selected_and_applied" if actual else
                 "score_below_threshold")
        mis=("outside_eligible_scope" if n<220 else
             "missing_checkpoint" if score is None else
             "false_positive_harm" if actual and forced>mon else
             "missed_eligible_benefit" if not selected and forced<mon else
             "correct_benefit_choice" if actual and forced<mon else
             "correct_abstention" if not selected and forced>=mon else
             "other")
        results.append(dict(
            fold=r["fold"],family=r["family"],n=n,shard=r["shard"],
            formula=f,formula_sha256=r["formula_sha256"],seed=r["seed"],
            degree_cv=num(r["degree_cv"]),degree_gini=num(r["degree_gini"]),
            polarity_imbalance=num(r["polarity_imbalance"]),
            score=score,score_margin=(score-THRESHOLD) if score is not None else None,
            ready_repeats=ready,selected_repeats=selected,actual_repeats=actual,
            monitor_par2=mon,forced50_par2=forced,live50_par2=live,
            strict50_par2=num(r["r16_live50_strict"]),
            snapshot50_par2=num(r["r16_snapshot50"]),
            force_log_gain=force_log_gain,forced_gain_pct=material_gain,
            live_gain_pct=live_gain,live_minus_forced_s=live-forced,
            forced_gain_gt2x=(mon>2*forced),
            forced_regression_gt2x=(forced>2*mon),
            live_gain_gt2x=(mon>2*live),
            live_regression_gt2x=(live>2*mon),
            policy_state=outcome,error_class=mis))
    check(len(results)==160 and
          {r["fold"] for r in results}==
          {"random3_test","random3_development","community3_test","community3_development"},
          "missing fold")
    for fold in FOLDS:
        group=[x for x in results if x["fold"]==fold]
        check(len(group)==(60 if fold.startswith("random3") else 20),
              "unexpected fold size")
        published=summary["report"][fold]["modes"]
        for mode,col in (("monitor","monitor_par2"),("r11_2048_50","forced50_par2"),
                         ("r16_live50","live50_par2")):
            check(abs(sum(x[col] for x in group)-published[mode]["par2_s"])<.0001,
                  "published PAR2 disagree: "+fold+" "+mode)
    return results

def group_summary(rows):
    m=sum(x["monitor_par2"] for x in rows)
    f=sum(x["forced50_par2"] for x in rows)
    l=sum(x["live50_par2"] for x in rows)
    eligible=[x for x in rows if x["n"]>=220]
    actual=[x for x in rows if x["actual_repeats"]>0]
    unrealized=[x for x in rows if x["actual_repeats"]==0]
    def gains(group):return sum(max(0,x["monitor_par2"]-x["forced50_par2"]) for x in group)
    return {
      "formulas":len(rows),
      "eligible_formula_count":len(eligible),
      "monitor_par2_seconds":round(m,6),
      "always_forced50_par2_seconds":round(f,6),
      "live50_par2_seconds":round(l,6),
      "live50_gain_vs_monitor_pct":round(100*(m-l)/m,6),
      "always_forced50_gain_vs_monitor_pct":round(100*(m-f)/m,6),
      "selected_attempts":sum(x["selected_repeats"] for x in rows),
      "actual_interventions":sum(x["actual_repeats"] for x in rows),
      "actual_selected_formulas":len(actual),
      "eligible_force_beneficial":sum(x["forced50_par2"]<x["monitor_par2"] for x in eligible),
      "eligible_force_harmful":sum(x["forced50_par2"]>x["monitor_par2"] for x in eligible),
      "selected_beneficial":sum(x["forced50_par2"]<x["monitor_par2"] for x in actual),
      "selected_harmful":sum(x["forced50_par2"]>x["monitor_par2"] for x in actual),
      "eligible_benefit_missed":sum(
          x["n"]>=220 and x["actual_repeats"]==0 and
          x["forced50_par2"]<x["monitor_par2"] for x in rows),
      "ineligible_n200_benefit_missed":sum(
          x["n"]<220 and x["forced50_par2"]<x["monitor_par2"] for x in rows),
      "missed_forced_gain_gt2x":sum(
          x["forced_gain_gt2x"] and not x["actual_repeats"] for x in rows),
      "observed_live_regress_gt2x":sum(x["live_regression_gt2x"] for x in rows),
      "abstained_potential_positive_s":round(gains(unrealized),6),
      "selected_forced_benefit_s":round(sum(
          x["monitor_par2"]-x["forced50_par2"] for x in actual),6),
      "selected_live_benefit_s":round(sum(
          x["monitor_par2"]-x["live50_par2"] for x in actual),6),
      "selected_live_vs_forced_delta_s":round(sum(
          x["live50_par2"]-x["forced50_par2"] for x in actual),6),
      "hindsight_formula_oracle_gain_upper_bound_s":round(gains(rows),6),
      "interpretation":"Hindsight forced50 is NOT implementable oracle; no new model trained."
    }

def analyse_scores(rows):
    eligible=[x for x in rows if x["n"]>=220 and x["score"] is not None]
    scores=[x["score"] for x in eligible]
    effects=[x["force_log_gain"] for x in eligible]
    spe=spearman(scores,effects) if eligible else None
    roc=auroc(eligible)
    res={
     "formula_count":len(eligible),
     "spearman_predicted_log_gain_vs_observed_log_gain":spe,
     "pearson_predicted_log_gain_vs_observed_log_gain":pearson(scores,effects),
     "auc_rank_for_any_positive_gain":roc,
     "mean_model_score":statistics.mean(scores) if scores else None,
     "mean_observed_log_gain":statistics.mean(effects) if effects else None,
     "spearman_95_bootstrap_formula_ci":corr_bootstrap(eligible) if len(eligible)>5 else [None,None],
     "threshold_025":"frozen; not reoptimized",
     "posthoc_notice":"These associations are descriptive on already inspected test labels, not an independent performance claim."
    }
    return res

def main():
    cfg,source=audit()
    OUT.mkdir(parents=True,exist_ok=True)
    fs=read_csv(INPUT/"formula_features.csv")
    ns=read_csv(INPUT/"native_decisions.csv")
    ps=read_csv(INPUT/"paired.csv")
    rows=classify(fs,ns,ps,source)
    tests=[x for x in rows if x["fold"]=="random3_test"]
    eligible=[x for x in tests if x["n"]>=220]
    summaries={fold:group_summary([x for x in rows if x["fold"]==fold]) for fold in FOLDS}
    summaries["random3_test_n200"]=group_summary([x for x in tests if x["n"]==200])
    summaries["random3_test_n220"]=group_summary([x for x in tests if x["n"]==220])
    summaries["random3_test_n240"]=group_summary([x for x in tests if x["n"]==240])
    summaries["random3_test_eligible_n220_240"]=group_summary(eligible)
    stats={fold:analyse_scores([x for x in rows if x["fold"]==fold])
           for fold in FOLDS}
    stats["random3_test_eligible"]=analyse_scores(eligible)

    # Explicit investigation examples, descriptive, never model training.
    missed=sorted((r for r in tests if r["actual_repeats"]==0
                  and r["forced50_par2"]<r["monitor_par2"]),
                  key=lambda x: x["monitor_par2"]-x["forced50_par2"],reverse=True)
    harmful=sorted((r for r in tests if r["actual_repeats"]>0
                  and r["live50_par2"]>r["monitor_par2"]),
                  key=lambda x: x["live50_par2"]-x["monitor_par2"],reverse=True)
    examples={"largest_missed_savings":missed[:12],
              "largest_observed_live_harms":harmful[:12]}
    allcols=list(rows[0])
    save_csv(OUT/"r16_postmortem_per_formula.csv",rows,allcols)
    examplecols=("fold","n","formula","formula_sha256","score",
                 "selected_repeats","actual_repeats","policy_state","error_class",
                 "monitor_par2","forced50_par2","live50_par2",
                 "forced_gain_pct","live_gain_pct")
    save_csv(OUT/"r16_missed.csv",missed,list(examplecols))
    save_csv(OUT/"r16_regressions.csv",harmful,list(examplecols))
    payload={
      "kind":"FROZEN_R16_POSTHOC_READONLY_DIAGNOSTICS",
      "run":R16_RUN,
      "input_snapshot_commit":BASE_SNAPSHOT,
      "input_file_git_blobs":PINNED_BLOBS,
      "protocol_git_blob":PROTOCOL_BLOB,
      "model_git_blob":MODEL_BLOB,
      "training_formula_count":cfg["trained_model_train_count"],
      "frozen_cutoff":THRESHOLD,
      "conflict_decision_at":1024,
      "restart_policy_applied_at":2048,
      "outcomes":summaries,
      "score_diagnostics":stats,
      "notable_examples":examples,
      "limitations":[
        "The primary random3_test was already analyzed; ALL new failure explanations here are retrospective.",
        "Do NOT use R16 random3_test or community3_test to adjust features, thresholds or retrain then claim untouched holdout.",
        "R16 train source is 59 R15 development formulas, outside R16; model coefficients unchanged.",
        "n<220 forced restart comparator exists but R16 was prohibited from selecting it; this is an explicit eligibility miss.",
        "Comparisons between monitor, forced and live arms are same-formula/same-runner paired but can include timer overhead and noise.",
        "R16 interventions only switch restartint to 50 at conflict 2048; no proven causal law.",
        "Synthetic formulas only; independent UNSAT proof validation not available; no official benchmark record.",
        "The hindsight best-of-two is an unreachable upper bound, NOT an attainable future policy.",
        "Small or near-zero differences can be timing noise; the evidence for strong harms/gains is more persuasive."
      ]}
    (OUT/"diagnostics.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    lines=["# DRNAS R16 — frozen-model decision error analysis",
      "",
      "Read-only audit of frozen run "+str(R16_RUN)+".",
      "Input commit "+BASE_SNAPSHOT+", frozen source git hashes explicitly checked.",
      "No solver changes, no retraining, no adapted thresholds, no new holdout claim.",
      "",
      "## Primary random3 test — same formula & runner",
      "",
      "| Scope | CNFs | Monitor PAR-2 | Forced50 | Live50 | Selected | Missed beneficial | Selected harmful |",
      "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for key in ("random3_test","random3_test_n200",
                "random3_test_eligible_n220_240",
                "random3_test_n220","random3_test_n240"):
        g=summaries[key]
        lines.append("| "+key+" | "+str(g["formulas"])+" | "+
            str(g["monitor_par2_seconds"])+" | "+
            str(g["always_forced50_par2_seconds"])+" | "+
            str(g["live50_par2_seconds"])+" | "+
            str(g["actual_selected_formulas"])+" | "+
            str(g["eligible_benefit_missed"]+g["ineligible_n200_benefit_missed"])+" | "+
            str(g["selected_harmful"])+" |")
    si=stats["random3_test_eligible"]
    lines+=["","## Key failure modes",
      "",
      "1. **Eligibility exclusion:** n=200 cannot be selected, even if independently measured forced50 is faster.",
      "2. **Weak ranking:** on 40 eligible random3_test CNFs, formula-level Spearman="+str(round(si["spearman_predicted_log_gain_vs_observed_log_gain"],4))+
      ", AUC="+str(round(si["auc_rank_for_any_positive_gain"],4))+
      ", bootstrap 95% Spearman CI="+str([round(v,4) for v in si["spearman_95_bootstrap_formula_ci"]])+".",
      "3. **Harmful high scores:** model selects some formulas with measured severe regressions.",
      "4. **Missed beneficial low scores:** model declines some formulas with real measured 2048/50 gains.",
      "5. **Policy vs observed overhead:** selected live and forced50 differ slightly despite same restart interval; don't equate the two timings mechanically.",
      "",
      "## Candidate future experiments (NOT implemented or optimized here)",
      "",
      "- Fit error/risk model on development formulas only (new split), validate on new untouched SHA cohort.",
      "- Preserve unmodified V15.3.1, R16 model SHA, fixed decision at 1024, action at 2048.",
      "- Add a conservative abstention decision, uncertainty/robustness margins and counterfactual diagnostics *before* evaluating on fresh formulas.",
      "- For n200, run a separate PREDECLARED eligibility ablation rather than silently changing the R16 primary rule.",
      "- Collect more conflict trajectories and quantify solver-time overhead; no proof of an invariant universal jerk law.",
      "",
      "## Provenance",
      "",
      "R16 generated Random3-SAT/Community3-SAT. SAT witnesses were checked by existing R16 code;",
      "independent UNSAT certificates were not checked. The historic test is now exploratory for any new rule.",
      "",
      "See diagnostics.json for exact scores, source hashes, measured cases and risk breakdown."]
    (OUT/"README.md").write_text("\n".join(lines)+"\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(8,5))
        for category,subset in (("Selected",[x for x in eligible if x["actual_repeats"]>0]),
                                ("Declined",[x for x in eligible if x["actual_repeats"]==0])):
            if subset:
                ax.scatter([x["score"] for x in subset],
                           [x["force_log_gain"] for x in subset],
                           label=category,alpha=.8)
        ax.axvline(THRESHOLD,ls="--",linewidth=1)
        ax.axhline(0,ls="--",linewidth=1)
        ax.set(xlabel="R16 native score at 1024 conflicts",
               ylabel="Observed log(Monitor PAR-2 / Forced50 PAR-2)",
               title="R16 random3_test — retrospective predictor errors")
        ax.legend();fig.tight_layout()
        fig.savefig(OUT/"r16_score_vs_real_gain.png",dpi=160)
        plt.close(fig)
    except ImportError:
        pass
    check(len(tests)==60 and len(eligible)==40,"test counts changed")
    check(summaries["random3_test"]["actual_interventions"]==33,
          "expected 33 live interventions")
    check(summaries["random3_test"]["observed_live_regress_gt2x"]==2,
          "expected 2 severe regressions")
    check(summaries["random3_test_eligible_n220_240"]["eligible_benefit_missed"]==14,
          "expected 14 missed eligible benefits")
    print("R16_POSTMORTEM_PASS",json.dumps({
        "test_formulas":len(tests),
        "eligible":len(eligible),
        "actions":summaries["random3_test"]["actual_interventions"],
        "missed_eligible":summaries["random3_test_eligible_n220_240"]["eligible_benefit_missed"],
        "ineligible_missed":summaries["random3_test_n200"]["ineligible_n200_benefit_missed"],
        "harmful_selected":summaries["random3_test"]["selected_harmful"],
        "spearman":si["spearman_predicted_log_gain_vs_observed_log_gain"],
        "auc":si["auc_rank_for_any_positive_gain"]
    },sort_keys=True),flush=True)

if __name__=="__main__":
    main()
