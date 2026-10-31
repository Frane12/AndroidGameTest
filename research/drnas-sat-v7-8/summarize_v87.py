#!/usr/bin/env python3
"""Aggregate the 5 frozen DRNAS v8.5 shards without changing thresholds."""
import csv
import json
import statistics
from pathlib import Path
from collections import defaultdict
import sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-v87")
MODES=("ca_plain","orig_v76_plain","orig_v76","adaptive_select")
DISPLAY_MODES=("ca_plain","orig_v76_plain","orig_v76","adaptive_select")
FAMILIES=("random3","random4","color3","xor3","pigeonhole")
REPEATS=3
CAP=3.0
SOURCE="drnas-blind-v87-20261031-50-untouched-seeds-v1"
all_cases=[]
all_rows=[]
for shard in range(5):
    path=ROOT/("shard-"+str(shard))
    manifest=json.loads((path/"manifest.json").read_text())
    assert manifest["version"]==SOURCE and manifest["cap_s"]==CAP
    assert manifest["repeats"]==REPEATS and tuple(manifest["modes"])==MODES
    assert manifest["selector_model"]["train_source_run"]==41224588277
    assert len(manifest["cases"])==10
    all_cases.extend(manifest["cases"])
    with (path/"raw.csv").open(newline="") as f:
        all_rows.extend(csv.DictReader(f))
assert len(all_cases)==50 and len({c["sha256"] for c in all_cases})==50
assert len(all_rows)==50*REPEATS*len(MODES)

def score(rs):
    assert len(rs)==REPEATS and {int(r["repeat"]) for r in rs}==set(range(REPEATS))
    solved=sum(r["status"] in ("SAT","UNSAT") for r in rs)
    median=statistics.median(float(r["wall_s"]) if r["status"] in ("SAT","UNSAT")
                             else CAP*2 for r in rs)
    return median,solved

lines=[
    "# DRNAS v8.7: 50 new SAT formulas, predeclared 5-family analysis","",
    "Five independent runner shards; per-case comparisons are paired on the same runner/CPU.",
    "Three repeats per solver; 3-second time limit; original v7.6 and CaDiCaL logic frozen.",
    "Time includes startup and parsing and selector feature overhead. Timeout PAR2=6 s.",
    "Only all-solved paired cases with CaDiCaL median >=50 ms count for speedup.",
    "Practical win: >1.25x; practical regression: <0.80x. No significance test from 3 repeats.",
    "Phase-hint contribution isolates v7.6 guided versus v7.6 without hints, both with checkpointing.",
    "SAT models are checked; arbitrary UNSAT claims lack independent proof certificates.",
    "Out-of-sample seeds; family types and sizes informed by prior work, pigeonhole cases may be isomorphic. Not a formal proof.","",
    "| Case | CaDiCaL | No hints | Guided v7.6 | Selector v8.7 | Selector speedup | Hint impact | Chosen mode |",
    "|---|---:|---:|---:|---:|---:|---:|---|"]
byfamily=defaultdict(lambda:{"cases":0,"measurable":0,"speedups":[],"hint_effects":[],"wins":0,"losses":0,"incomplete":0})
inconsistencies=[]
diagnostics=[]
for case in all_cases:
    name=case["family"]+"-"+str(case["size"])
    family=case["family"]
    f=byfamily[family]
    f["cases"]+=1
    rows=[r for r in all_rows if r["case"]==name]
    assert len(rows)==REPEATS*len(MODES)
    assert {r["sha256"] for r in rows}=={case["sha256"]}
    known={r["status"] for r in rows if r["status"] in ("SAT","UNSAT")}
    if len(known)>1:inconsistencies.append(name+" conflicting SAT/UNSAT")
    if case["known_truth"].startswith("UNSAT") and "SAT" in known:
        inconsistencies.append(name+" contradicted pigeonhole principle")
    if any(r["status"]=="ERROR" for r in rows):
        inconsistencies.append(name+" solver error")
    cells={m:score([r for r in rows if r["mode"]==m]) for m in MODES}
    base,plain,guided,selector=(cells[m] for m in MODES)
    if any(cell[1]<REPEATS for cell in cells.values()):f["incomplete"]+=1
    measurable=base[1]==REPEATS and selector[1]==REPEATS and base[0]>=0.05
    ratio=base[0]/selector[0] if measurable else None
    hint=plain[0]/guided[0] if (plain[1]==REPEATS and guided[1]==REPEATS and base[0]>=0.05) else None
    if ratio is not None:
        f["measurable"]+=1;f["speedups"].append(ratio)
        f["wins"]+=ratio>1.25;f["losses"]+=ratio<0.8
    if hint is not None:f["hint_effects"].append(hint)
    fmt=lambda cell:"%.4fs (%d/3)"%(cell[0],cell[1])
    chosen={r["selected_mode"] for r in rows if r["mode"]=="adaptive_select"}
    assert len(chosen)==1
    chosen_mode=next(iter(chosen))
    lines.append("| "+name+" | "+" | ".join(fmt(cells[m]) for m in DISPLAY_MODES)+" | "+
                 ("%.2fx"%ratio if ratio is not None else "n/a")+" | "+
                 ("%.2fx"%hint if hint is not None else "n/a")+" | "+chosen_mode+" |")
    gr=[r for r in rows if r["mode"]=="orig_v76"]
    diagnostics.append({"case":name,"family":family,"selected_mode":chosen_mode,"selector_speedup":ratio,
        "hint_impact":hint,"guided_extended":[r["extended"] for r in gr],
        "guided_hints":[r["hints"] for r in gr],
        "guided_learned_delta":[r["learned_delta"] for r in gr],
        "guided_threshold":[r["threshold"] for r in gr]})
lines+=["","## All family outcomes (no filtering of unfavorable results)","",
        "| Family | Cases | Measurable | Median speedup | >1.25x | <0.80x | Incomplete any mode |",
        "|---|---:|---:|---:|---:|---:|---:|---|"]
for name in FAMILIES:
    d=byfamily[name]
    speed=statistics.median(d["speedups"]) if d["speedups"] else None
    lines.append("| %s | %s | %s | %s | %s | %s | %s |"%(
        name,d["cases"],d["measurable"],("%.3fx"%speed if speed is not None else "n/a"),
        d["wins"],d["losses"],d["incomplete"]))
lines+=["","## Diagnostics", "",
       "Contradictions/errors: "+(str(inconsistencies) if inconsistencies else "none detected"),
       "A speedup on the same formula is not evidence of polynomial-time SAT.",
       "Selector rule trained on v8.5 only, evaluated without tuning on v8.7. No world record claim."]
report="\n".join(lines)+"\n"
(ROOT/"summary.md").write_text(report)
(ROOT/"diagnostics.json").write_text(json.dumps(diagnostics,indent=2))
(ROOT/"family_summary.json").write_text(json.dumps(dict(byfamily),indent=2))
(ROOT/"all_cases.json").write_text(json.dumps(all_cases,indent=2))
with (ROOT/"all_raw.csv").open("w",newline="") as fh:
    w=csv.DictWriter(fh,fieldnames=all_rows[0].keys())
    w.writeheader();w.writerows(all_rows)
with open(str(Path(__import__("os").environ.get("GITHUB_STEP_SUMMARY",ROOT/"step_summary.md"))),"a") as summary:
    summary.write(report)
print(report,flush=True)
if inconsistencies:raise RuntimeError("Found inconsistent or invalid solver answers")
