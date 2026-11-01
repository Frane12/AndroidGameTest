#!/usr/bin/env python3
"""V18.3 Hardware–Logic read-only calibration aggregate (NOT blind)."""
from __future__ import annotations
import collections,csv,json,statistics
from pathlib import Path
ROOT=Path("drnas-v183-hardware-logic")
def read(path):
    with path.open(newline="") as f:return list(csv.DictReader(f))
def avg(x):return statistics.mean(x) if x else None
def main():
    rows=[];signals=[]
    for shard in range(2):
        directory=ROOT/f"shard_{shard}"
        rows+=read(directory/"measurements.csv")
        signals+=json.loads((directory/"derived_signals.json").read_text())
    # For every formula x repetition, measure full OS CPU costs against
    # ORIGINAL Kissat on the same runner. Do not mix hardware by aggregating
    # absolute CPU seconds before making local pairs.
    pairs=collections.defaultdict(dict)
    for x in rows:
        key=(int(x["index"]),int(x["repetition"]))
        if x["mode"] in pairs[key]:raise RuntimeError("duplicate case")
        pairs[key][x["mode"]]=x
        if float(x["cpu_total_s"])<0:raise RuntimeError("negative OS CPU")
    required={"baseline","monitor","fixed25","adaptive_gate"}
    if not all(set(pair)==required for pair in pairs.values()):
        raise RuntimeError("incomplete hardware comparison")
    comparisons=[]
    for (index,rep),pair in sorted(pairs.items()):
        orig=pair["baseline"]
        for mode in ("monitor","fixed25","adaptive_gate"):
            test=pair[mode]
            basecpu=float(orig["cpu_total_s"])
            basewall=float(orig["wall_s"])
            comparisons.append(dict(index=index,repetition=rep,mode=mode,
                original_cpu_s=basecpu,mode_cpu_s=float(test["cpu_total_s"]),
                cpu_pct_delta=round(100*(float(test["cpu_total_s"])/basecpu-1),5)
                    if basecpu>0 else None,
                wall_pct_delta=round(100*(float(test["wall_s"])/basewall-1),5)
                    if basewall>0 else None,
                phase=test["stage"],preprocess_rounds=int(test["preprocess_rounds"]),
                search_samples=int(test["search_samples"]),
                monitor_internal_pct=test["internal_monitor_pct"],
                false_zero_avoided=bool(
                    int(test["preprocess_rounds"])>0 and int(test["search_samples"])==0)))
    out=ROOT/"aggregate";out.mkdir(exist_ok=True)
    os_cpu_monitor=[x["cpu_pct_delta"] for x in comparisons
                    if x["mode"]=="monitor" and x["cpu_pct_delta"] is not None]
    preprocess_only=[x for x in rows
                     if x["stage"]=="preprocessing_only"]
    search_present=[x for x in rows if int(x["search_samples"])>0]
    if not preprocess_only:
        raise RuntimeError("Missing preprocessing-round telemetry in replay: check C patch")
    stages=collections.Counter(x["stage"] for x in rows)
    summary={
      "phase":"DRNAS V18.3 hardware-logic telemetry calibration REPLAY",
      "blind_holdout":False,"competition_scoring":False,
      "formulas":len({int(x["index"]) for x in rows}),
      "measurement_count":len(rows),
      "os_cpu_measured_attempts":sum(float(x["cpu_total_s"])>0 for x in rows),
      "preprocessing_only_measurements":len(preprocess_only),
      "main_search_measurements":len(search_present),
      "preprocess_rounds_total":sum(int(x["preprocess_rounds"]) for x in rows),
      "search_snapshots_total":sum(int(x["search_samples"]) for x in rows),
      "monitor_vs_original_cpu_pct_mean":round(avg(os_cpu_monitor),6) if os_cpu_monitor else None,
      "monitor_vs_original_cpu_pct_median":round(statistics.median(os_cpu_monitor),6) if os_cpu_monitor else None,
      "monitor_vs_original_cpu_below_half_percent_in_all_pairs":
        bool(os_cpu_monitor) and all(x<=0.5 for x in os_cpu_monitor),
      "monitor_0_5_pct_target_proven":False,
      "reason":"Limited diagnostic replay, not statistically adequate to establish universal 0.5% overhead. CPU clock/OS metrics may differ from CPU cycles and power.",
      "third_derivative_available_groups":sum(x["third_diff_available"] for x in signals),
      "third_derivative_unavailable_groups":sum(not x["third_diff_available"] for x in signals),
      "stage_counts":dict(stages),
      "not_measured":["CPU instructions","CPU cycles","L1/L2/LLC misses","joules","CPU power"],
      "actual_hardware_indicators":["OS child user+system CPU time","page faults","context switches","block I/O"],
      "causality":"No causal claim: full benchmark only distinguishes effects within formula/runner.",
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    (out/"derived_signals.json").write_text(json.dumps(signals,indent=2))
    with (out/"hardware_pairs.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(comparisons[0]))
        w.writeheader();w.writerows(comparisons)
    with (out/"REPORT.md").open("w") as f:
        f.write("# DRNAS V18.3 — Hardware–Logic Calibration\n\n")
        f.write("**Replay of previously used official 2026 CNFs; NOT blind.**\n\n")
        f.write("Original Kissat is measured as a separate binary built at the "
                "same pinned SHA. This run separates full OS CPU usage from "
                "search-only conflict snapshots and preprocessing rounds.\n\n")
        f.write("## Observations\n\n")
        for key,val in summary.items():
            f.write(f"- **{key}:** {val}\n")
        f.write("\n**Important:** Psi is a placeholder for a dynamic-state "
                "feature vector. It is not a physical constant and is not "
                "a proven measure of distance to a satisfying assignment.\n")
    print("V183_AGGREGATE_FINAL",json.dumps(summary,separators=(",",":")),flush=True)
if __name__=="__main__":main()
