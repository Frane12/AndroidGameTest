#!/usr/bin/env python3
"""DRNAS V18.2 fixed-holdout, formula-cluster paired analysis.

Avoid treating two repeats as two independent formulas. A 0.5% internal
measurement estimate does NOT prove end-to-end <0.5% wall-time overhead.
"""
from __future__ import annotations
import collections,csv,hashlib,json,random,statistics
from pathlib import Path
from official_neuroflow_v182 import ROOT,POLICIES,KISSAT_SHA,CAP,FROZEN

def mean(x):return statistics.mean(x) if x else None
def fmt(x):return "n/a" if x is None else f"{x:.3f}"
def read_csv(path):
    with path.open(newline="") as f:return list(csv.DictReader(f))
def save_csv(path,rows,fields):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def ci_cluster(values,seed=182000,n=2000):
    if not values:return [None,None]
    rng=random.Random(seed)
    results=sorted(mean([values[rng.randrange(len(values))]
               for _ in range(len(values))]) for _ in range(n))
    return [round(results[int(n*.025)],6),round(results[int(n*.975)],6)]

def main():
    data=[];overhead=[];snapshots=[];shards=[]
    for i in range(4):
        path=ROOT/f"shard_{i}"
        summary=json.loads((path/"summary.json").read_text())
        shards.append(summary)
        data+=read_csv(path/"measurements.csv")
        overhead+=read_csv(path/"overhead.csv")
        snapshots+=read_csv(path/"snapshots.csv")
    by_case=collections.defaultdict(lambda:collections.defaultdict(list))
    for x in data:
        by_case[int(x["official_index"])][x["mode"]].append(x)
    if not by_case:raise RuntimeError("No cases")
    if not snapshots:
        raise RuntimeError(
            "V182_ZERO_LOGIC_SNAPSHOTS: rejecting an uninstrumented run "
            "(original run 41310002605 silently compared the same executable).")
    instrumented_traces=sum(x["monitor_internal_pct"] not in ("",None)
         for x in data if x["mode"]!="baseline")
    if instrumented_traces<4:
        raise RuntimeError(
            f"V182_TOO_FEW_INSTRUMENTED_TRACES: only {instrumented_traces}")
    for i,modes in by_case.items():
        if set(modes)!=set(POLICIES) or any(len(modes[m])!=2 for m in POLICIES):
            raise RuntimeError(f"Incomplete paired formula: {i}")
    formulas=sorted(by_case)
    by_repetition=collections.defaultdict(dict)
    for x in data:
        k=(int(x["official_index"]),int(x["repeat"]))
        if x["mode"] in by_repetition[k]:
            raise RuntimeError("Duplicate policy measurement")
        by_repetition[k][x["mode"]]=x
    paired=[]
    for i in formulas:
        base=mean([float(x["par2"]) for x in by_case[i]["baseline"]])
        trace=mean([float(x["par2"]) for x in by_case[i]["monitor"]])
        for mode in POLICIES:
            selected=by_case[i][mode]
            val=mean([float(x["par2"]) for x in selected])
            paired.append(dict(official_index=i,mode=mode,
                 baseline_par2=round(base,6),
                 monitor_par2=round(trace,6),
                 strategy_par2=round(val,6),
                 improvement_vs_baseline_s=round(base-val,6),
                 improvement_vs_monitor_s=round(trace-val,6),
                 solved=sum(x["status"] in ("SAT","UNSAT") for x in selected),
                 attempts=len(selected),
                 fallback_count=sum(int(x["fallbacks"] or 0) for x in selected),
                 budget_aborts=sum(x["monitor_budget_abort"]=="1" for x in selected)))
    policies=[]
    baseline=mean([float(x["par2"]) for x in data if x["mode"]=="baseline"])
    for mode in POLICIES:
        part=[x for x in data if x["mode"]==mode]
        values=[float(x["par2"]) for x in part]
        gains=[row["improvement_vs_baseline_s"] for row in paired if row["mode"]==mode]
        wall=mean(values)
        costs=[float(x["monitor_internal_pct"]) for x in part
               if x["monitor_internal_pct"] not in ("",None)]
        policies.append(dict(mode=mode,formula_count=len(formulas),attempts=len(part),
             solved=sum(x["status"] in ("SAT","UNSAT") for x in part),
             timeout=sum(x["status"]=="TIMEOUT" for x in part),
             par2_mean=round(wall,6),improvement_pct=round(100*(1-wall/baseline),3),
             delta_seconds_per_formula=round(mean(gains),6),
             bootstrap_ci95_seconds=ci_cluster(gains,seed=182000+len(mode)),
             formula_wins=sum(g>0.001 for g in gains),
             formula_losses=sum(g< -0.001 for g in gains),
             fallback_count=sum(int(x["fallbacks"] or 0) for x in part),
             budget_stop_count=sum(x["monitor_budget_abort"]=="1" for x in part),
             monitor_internal_pct_max=round(max(costs),6) if costs else None,
             monitor_internal_pct_mean=round(mean(costs),6) if costs else None,
             monitor_traces=len(costs)))
    policies.sort(key=lambda x:x["par2_mean"])
    overhead_pct=[float(x["paired_wall_pct"]) for x in overhead]
    internal_pct=[float(x["monitor_internal_pct"]) for x in overhead
                  if x["monitor_internal_pct"] not in ("",None)]
    # Median of paired per-case wall deltas reflects real executable costs,
    # while distribution may be noisy for very short instances.
    overhead_report=dict(paired_completed_controls=len(overhead),
         wall_pct_median=round(statistics.median(overhead_pct),6)
              if overhead_pct else None,
         wall_pct_mean=round(mean(overhead_pct),6) if overhead_pct else None,
         wall_pct_range=[round(min(overhead_pct),6),round(max(overhead_pct),6)]
              if overhead_pct else None,
         internal_monitor_pct_mean=round(mean(internal_pct),6) if internal_pct else None,
         internal_monitor_pct_max=round(max(internal_pct),6) if internal_pct else None,
         internal_exceeded_half_percent=sum(x>0.5 for x in internal_pct),
         wall_exceeded_half_percent=sum(x>0.5 for x in overhead_pct),
         below_half_percent_wall_for_every_case=bool(overhead_pct) and all(
              x<=0.5 for x in overhead_pct),
         note=("Guard self-timing is a lower bound on total process overhead. "
               "Use paired original-Kissat vs patched-monitor wall times, "
               "and do not claim a guaranteed 0.5% end-to-end CPU bound."))
    action_rows=[]
    for i in formulas:
        d=by_case[i]
        for fallback_mode,uncorrected in [
             ("adaptive_force","fixed25"),
             ("adaptive_gate","gate_no_guard")]:
            x=mean([float(r["par2"]) for r in d[fallback_mode]])
            y=mean([float(r["par2"]) for r in d[uncorrected]])
            action_rows.append(dict(official_index=i,adaptive_mode=fallback_mode,
                 comparison_mode=uncorrected,
                 adaptive_par2=round(x,6),
                 no_guard_par2=round(y,6),
                 saved_s=round(y-x,6),
                 fallbacks=sum(int(r["fallbacks"] or 0) for r in d[fallback_mode]),
                 budget_aborts=sum(r["monitor_budget_abort"]=="1" for r in d[fallback_mode])))
    changed=[r for r in action_rows if r["fallbacks"]]
    outcome=dict(experiment="DRNAS SAT V18.2 NeuroFlow regression guard",
         exact_pinned_kissat=KISSAT_SHA,
         official_2026_instances=True,
         official_competition_scoring=False,
         formula_count=len(formulas),
         actual_measurements=len(data),
         planned_repeats=2,
         modes=POLICIES,
         time_cap_seconds=CAP,
         best_measured_policy=policies[0]["mode"],
         ranking=policies,
         monitor_overhead=overhead_report,
         triggered_fallback_formula_pairs=len(changed),
         fallback_benefits_on_triggered=sum(x["saved_s"]>0.001 for x in changed),
         fallback_regressions_on_triggered=sum(x["saved_s"]< -0.001 for x in changed),
         all_sat_witnesses_verified=all(x["sat_model_verified"]=="True" for x in data
                                         if x["status"]=="SAT"),
         independently_verified_unsat_proofs=0,
         total_snapshots=len(snapshots),
         warning=("Tests on previously unused official CNF instances, not official "
                  "SAT Competition 2026 scoring; policies are held fixed before test. "
                  "Any top-ranked selection made here needs another independent holdout."))
    folder=ROOT/"aggregate"
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"summary.json").write_text(json.dumps(outcome,indent=2))
    (folder/"frozen_selection.json").write_bytes(FROZEN.read_bytes())
    save_csv(folder/"formula_pairing.csv",paired,
        ("official_index","mode","baseline_par2","monitor_par2",
         "strategy_par2","improvement_vs_baseline_s","improvement_vs_monitor_s",
         "solved","attempts","fallback_count","budget_aborts"))
    save_csv(folder/"fallback_effect.csv",action_rows,
        ("official_index","adaptive_mode","comparison_mode","adaptive_par2",
         "no_guard_par2","saved_s","fallbacks","budget_aborts"))
    save_csv(folder/"overhead.csv",overhead,
        ("official_index","repeat","baseline_s","monitor_s",
         "paired_wall_pct","monitor_internal_pct"))
    with (folder/"REPORT.md").open("w") as f:
        f.write("# DRNAS SAT V18.2 — independently replayed 2026 CNFs\n\n")
        f.write(f"Unique formulas: **{len(formulas)}**; measurements: **{len(data)}**; "
                "8 fixed policies and 2 repeats per selected formula.\n\n")
        f.write("| Strategy | Solved | PAR2 seconds | Δ vs original Kissat | "
                "Fallbacks | CI95 on saved seconds |\n")
        f.write("|---|---:|---:|---:|---:|---|\n")
        for p in policies:
            f.write(f"| {p['mode']} | {p['solved']}/{p['attempts']} | "
                 f"{p['par2_mean']:.4f} | {p['improvement_pct']:+.2f}% | "
                 f"{p['fallback_count']} | {p['bootstrap_ci95_seconds']} |\n")
        f.write("\n## Monitoring overhead\n\n")
        f.write(json.dumps(overhead_report,indent=2)+"\n\n")
        f.write("Monitoring CPU time is measured with process CPU clocks, "
                "but does not include instrumentation's background branch costs "
                "or all I/O: wall-clock paired control is the external audit. "
                "The 0.5% target is NOT guaranteed, and if missed must be disclosed.\n\n")
        f.write("## Caveats\n\n")
        f.write("No independent UNSAT proofs; verified SAT models only. "
                "No world record claim. Paired runs are within runner shard, "
                "and repeated attempts on a formula are not independent formulas. "
                "Restoring restartint cannot rewind past learned clauses or search history.\n")
    print("V182_FINAL",json.dumps(outcome,separators=(",",":")),flush=True)

if __name__=="__main__":main()
