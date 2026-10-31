#!/usr/bin/env python3
"""Prespecified cross-shard v8.8 summary. Includes timeouts and all regressions."""
import csv
import hashlib
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-v88")
MODES=("ca_plain","orig_v76","orig_v76_plain","adaptive_two_checkpoint",
       "adaptive_guarded_v87","lowlevel_v88","lowlevel_v88_no_hints")
FAMILIES=("random3","random4","color3","xor3","pigeonhole")
VERSION="drnas-v88-lowlevel-30-blind-20261031-seed-v1"
CAP=3.0
REPEATS=3
CASES=[]
ROWS=[]
for shard in range(5):
    folder=ROOT/("shard-"+str(shard))
    m=json.loads((folder/"manifest.json").read_text())
    assert m["version"]==VERSION and m["cap_s"]==CAP and m["repeats"]==REPEATS
    assert tuple(m["modes"])==MODES and len(m["cases"])==6
    CASES+=m["cases"]
    with (folder/"raw.csv").open(newline="") as f:ROWS+=list(csv.DictReader(f))
assert len(CASES)==30 and len({c["sha256"] for c in CASES})==30
assert len(ROWS)==30*REPEATS*len(MODES)

def med(rows):
    assert len(rows)==REPEATS and {int(x["repeat"]) for x in rows}=={0,1,2}
    solved=sum(r["status"] in ("SAT","UNSAT") for r in rows)
    costs=[float(r["wall_s"]) if r["status"] in ("SAT","UNSAT")
           else 2*CAP for r in rows]
    return statistics.median(costs),solved

lines=[
 "# DRNAS v8.8 — 30 newly generated CNFs, 630 attempts, matched 7 modes","",
 "Frozen CaDiCaL 3.0.1/v7.6 and unchanged guarded/adaptive controls.",
 "Experimental v8.8 has no per-clause learner observer and uses integer-only public counters at checkpoints.",
 "5 independent single-core runners, 3 repeats, 3-second cap each. Compare only within paired case+runner.",
 "PAR2=6 s for any timeout, unconditionally included in summed results.",
 "Significant practical advantage is descriptive >1.25x and practical regression <0.8x; no formal p-value.",
 "Speedup ratios require both methods solve all 3 repeats and baseline >=0.10 s.",
 "SAT models checked by native solver; arbitrary UNSAT proof certificates not validated.",
 "One exploratory synthetic test does not establish generalized advantage or CPU cache savings.","",
 "| Case | CaDiCaL | Guided v7.6 | No-hint v7.6 | v8.6 | Guarded v8.7 | Lowlevel v8.8 | v8.8 no hints | Ca / v8.8 | v7.6 / v8.8 | Gate |",
 "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
family=defaultdict(lambda:{"total":0,"measured_ca":[],"measured_v76":[],"wins_ca":0,"losses_ca":0,"wins_v76":0,"losses_v76":0,"timeout":0,"near":0,"durable":0,"fallback":0})
totals={k:0.0 for k in MODES}
discrepancies=[]
details=[]
for case in CASES:
    name=Path(case["cnf"]).stem
    rows=[r for r in ROWS if r["case"]==name]
    assert len(rows)==REPEATS*len(MODES)
    assert {r["sha256"] for r in rows}=={case["sha256"]}
    answers={r["status"] for r in rows if r["status"] in ("SAT","UNSAT")}
    if len(answers)>1:discrepancies.append(name+": contradictory status")
    if any(r["status"]=="ERROR" for r in rows):discrepancies.append(name+": solver error")
    if case["known_truth"]=="SAT-by-construction" and "UNSAT" in answers:
        discrepancies.append(name+": wrong UNSAT on planted SAT")
    if case["known_truth"].startswith("UNSAT") and "SAT" in answers:
        discrepancies.append(name+": wrong SAT on known UNSAT")
    cells={mode:med([r for r in rows if r["mode"]==mode]) for mode in MODES}
    base=cells["ca_plain"]; ref=cells["orig_v76"]; ll=cells["lowlevel_v88"]
    f=family[case["family"]];f["total"]+=1
    for mode in MODES:totals[mode]+=cells[mode][0]
    if any(n<REPEATS for _,n in cells.values()):f["timeout"]+=1
    good_ca=(base[1]==REPEATS and ll[1]==REPEATS and base[0]>=0.1)
    good_v76=(ref[1]==REPEATS and ll[1]==REPEATS and ref[0]>=0.1)
    ratio_ca=base[0]/ll[0] if good_ca else None
    ratio_v76=ref[0]/ll[0] if good_v76 else None
    if ratio_ca is not None:
        f["measured_ca"].append(ratio_ca)
        f["wins_ca"]+=ratio_ca>1.25;f["losses_ca"]+=ratio_ca<0.8
    if ratio_v76 is not None:
        f["measured_v76"].append(ratio_v76)
        f["wins_v76"]+=ratio_v76>1.25;f["losses_v76"]+=ratio_v76<0.8
    llrows=[r for r in rows if r["mode"]=="lowlevel_v88"]
    # Different matched repetition seeds may legitimately produce different
    # checkpoint decisions. Keep all observations instead of asserting a
    # single gate reason and discarding a valid 630-attempt experiment.
    reasons={r.get("gate_reason","") for r in llrows}
    if len(reasons)==1:
        reason=next(iter(reasons))
    else:
        reason="mixed("+",".join(
            "%s:%d"%(key,sum(r.get("gate_reason","")==key for r in llrows))
            for key in sorted(reasons))+")"
    f["near"]+=any(
        ("near_128" in key or "after_128" in key or "keep_640" in key)
        for key in reasons)
    f["durable"]+=any("preserve_v76" in key for key in reasons)
    f["fallback"]+=any("early_fallback" in key for key in reasons)
    fmt=lambda mode:"%.4fs (%d/3)"%cells[mode]
    lines.append("| "+name+" | "+" | ".join(fmt(m) for m in MODES)+" | "+
                 ("%.2fx"%ratio_ca if ratio_ca is not None else "n/a")+" | "+
                 ("%.2fx"%ratio_v76 if ratio_v76 is not None else "n/a")+" | "+reason+" |")
    details.append({"case":name,"family":case["family"],"baseline_par2":base[0],
                    "v76_par2":ref[0],"lowlevel_par2":ll[0],
                    "ratio_ca":ratio_ca,"ratio_v76":ratio_v76,"gate":reason,
                    "learned_256":[r["learned_delta"] for r in llrows],
                    "threshold":[r["threshold"] for r in llrows],
                    "learned_128":[r["checkpoint_learned"] for r in llrows],
                    "hints":[r["hints"] for r in llrows]})
lines.extend(["","## Full family accounting","","| Family | Cases | Baseline-comparable | Median Ca/v8.8 | wins | regressions | Median v7.6/v8.8 | wins | regressions | Cases with any timeout | Near probes | Preserved durable |",
"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
for name in FAMILIES:
    f=family[name]
    def display(values):return ("%.3fx"%statistics.median(values)) if values else "n/a"
    lines.append("| %s | %d | %d | %s | %d | %d | %s | %d | %d | %d | %d | %d |"%(
        name,f["total"],len(f["measured_ca"]),display(f["measured_ca"]),
        f["wins_ca"],f["losses_ca"],display(f["measured_v76"]),
        f["wins_v76"],f["losses_v76"],f["timeout"],f["near"],f["durable"]))
lines.extend(["","## PAR2 aggregate (descriptive; different formula hardness)","",
              "| Mode | Sum of case medians incl 6s timeout penalty |",
              "|---|---:|"])
for mode in MODES:lines.append("| %s | %.5f s |"%(mode,totals[mode]))
lines+=["","Reported contradictions/errors: "+(str(discrepancies) if discrepancies else "none detected"),
       "The checkpoint 'redundant' counter reflects retained redundant clauses, not proof of general usefulness.",
       "No direct microarchitecture counters were collected; a speed difference is not a measured cache optimization."]
report="\n".join(lines)+"\n"
(ROOT/"summary.md").write_text(report)
(ROOT/"family.json").write_text(json.dumps(dict(family),indent=2))
(ROOT/"diagnostics.json").write_text(json.dumps(details,indent=2))
(ROOT/"totals.json").write_text(json.dumps(totals,indent=2))
with (ROOT/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=ROWS[0].keys());w.writeheader();w.writerows(ROWS)
with open(os.environ.get("GITHUB_STEP_SUMMARY",str(ROOT/"summary-gh.md")),"a") as f:f.write(report)
print(report,flush=True)
if discrepancies:raise RuntimeError("Check solver correctness issues in results")
