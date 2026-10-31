#!/usr/bin/env python3
"""DRNAS v8.9 predeclared audit. 25 independent fresh CNFs, 450 solver processes."""
import csv
import json
import os
import statistics
import sys
from collections import defaultdict, Counter
from pathlib import Path
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-v89")
MODES=("ca_plain","orig_v76","orig_v76_plain","delayed_v88b",
       "v89_rate_no_hints","v89_rate_late_hints")
FAMILIES=("random3","random4","color3","xor3","pigeonhole")
VERSION="drnas-v89-yield-25-20261031-frozen-v1"
CAP=3.0
REPEATS=3
cases=[]
raw=[]
for shard in range(5):
    folder=ROOT/("shard-"+str(shard))
    m=json.loads((folder/"manifest.json").read_text())
    assert m["version"]==VERSION and m["cap_s"]==CAP and m["repeats"]==REPEATS
    assert tuple(m["modes"])==MODES and len(m["cases"])==5
    cases+=m["cases"]
    with (folder/"raw.csv").open(newline="") as f:raw+=list(csv.DictReader(f))
assert len(cases)==25 and len({x["sha256"] for x in cases})==25
assert len(raw)==25*REPEATS*len(MODES)
def median_result(part):
    assert len(part)==REPEATS and {int(x["repeat"]) for x in part}=={0,1,2}
    solved=sum(x["status"] in ("SAT","UNSAT") for x in part)
    values=[float(x["wall_s"]) if x["status"] in ("SAT","UNSAT") else 2*CAP for x in part]
    return statistics.median(values),solved
totals={m:0. for m in MODES}
fams=defaultdict(lambda:{"n":0,"n_measurable":0,"win":0,"loss":0,"ratios":[],"timeouts":0,"gates":Counter()})
errors=[]
details=[]
lines=[
"# DRNAS SAT v8.9: prospective 25 new CNFs, 450 paired processes",
"",
"One core per shard, 5 shards, 3 repetitions per method, 3s wall limit, PAR2 timeout cost 6s.",
"Unmodified CaDiCaL 3.0.1 and frozen v7.6, process CPU nanoseconds measured by v8.9 only.",
"v8.9 initial 256 conflicts are unphased; high retained-clause yield triggers old 768 path,",
"near-boundary cases get 128-conflict probe and a CPU-time + conflict-yield rate gate.",
"Retained redundant clauses measure net *database retention*, NOT learnt clause LBD or proven quality.",
"Hardware perf counters may be unavailable; do NOT claim memory or cache benefits without actual counters.",
"SAT witnesses checked by C++ verifier; UNSAT certificates not independently verified.",
"Ratio criteria: both modes solve 3/3, CaDiCaL median >=0.100s; >1.25x practical win, <0.8x regression.",
"Timeouts are NEVER counted as wins. Sample is synthetic and small, not a competition.",
"",
"| Case | CaDiCaL | v7.6 guided | v7.6 no hints | v8.8b delayed | v8.9 no hints | v8.9 late hints | Ca/v8.9 no hints | Ca/v8.9 late hints | Median v8.9 probe CPU ms | Gate(s) |",
"|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
for case in cases:
    name=Path(case["cnf"]).stem
    rows=[r for r in raw if r["case"]==name]
    assert len(rows)==len(MODES)*REPEATS
    assert {r["sha256"] for r in rows}=={case["sha256"]}
    ans={r["status"] for r in rows if r["status"] in ("SAT","UNSAT")}
    if len(ans)>1:errors.append(name+": contradictory SAT/UNSAT")
    if any(r["status"]=="ERROR" for r in rows):errors.append(name+": solver error")
    if case["known_truth"].startswith("UNSAT") and "SAT" in ans:errors.append(name+": wrong SAT")
    if case["known_truth"]=="SAT-by-construction" and "UNSAT" in ans:errors.append(name+": wrong UNSAT")
    modes={m:median_result([r for r in rows if r["mode"]==m]) for m in MODES}
    family=fams[case["family"]];family["n"]+=1
    if any(v[1]<REPEATS for v in modes.values()):family["timeouts"]+=1
    for m in MODES:totals[m]+=modes[m][0]
    first=modes["ca_plain"]
    r_no=modes["v89_rate_no_hints"]
    r_late=modes["v89_rate_late_hints"]
    comparable=first[1]==REPEATS and first[0]>=0.1
    ratio_no=first[0]/r_no[0] if comparable and r_no[1]==REPEATS else None
    ratio_late=first[0]/r_late[0] if comparable and r_late[1]==REPEATS else None
    if ratio_no is not None:
        family["ratios"].append(ratio_no);family["n_measurable"]+=1
        family["win"]+=ratio_no>1.25;family["loss"]+=ratio_no<0.8
    observed=[r for r in rows if r["mode"]=="v89_rate_no_hints"]
    gates=Counter(r.get("gate_reason","") for r in observed)
    family["gates"].update(gates)
    cpu=[float(r["cpu_256_ns"])/1e6 for r in observed if r.get("cpu_256_ns","") not in ("",None)]
    cpumed=statistics.median(cpu) if cpu else None
    lines.append("| "+name+" | "+" | ".join("%.4fs (%d/3)"%modes[m] for m in MODES)+
        " | "+("%.2fx"%ratio_no if ratio_no is not None else "n/a")+
        " | "+("%.2fx"%ratio_late if ratio_late is not None else "n/a")+
        " | "+("%.3f"%cpumed if cpumed is not None else "n/a")+
        " | "+", ".join("%s:%d"%(k,v) for k,v in sorted(gates.items()))+" |")
    details.append({"case":name,"family":case["family"],"par2":{m:modes[m][0] for m in MODES},
                    "ratio_no":ratio_no,"ratio_late":ratio_late,"gate":dict(gates),
                    "cpu_256_ms":cpumed,
                    "learned_256":[r.get("learned_delta") for r in observed],
                    "learned_128":[r.get("checkpoint_learned") for r in observed],
                    "cpu_128_ns":[r.get("cpu_128_ns") for r in observed],
                    "hints":[r.get("hints") for r in observed]})
lines+=["","## All-family paired metrics (no selecting only favorable cases)","",
"| Family | CNFs | Comparable | Median Ca/v8.9 no-hints | >1.25x | <0.80x | Any mode timed out |",
"|---|---:|---:|---:|---:|---:|---:|"]
for fam in FAMILIES:
    d=fams[fam]
    lines.append("| %s | %d | %d | %s | %d | %d | %d |"%(
        fam,d["n"],d["n_measurable"],
        ("%.3fx"%statistics.median(d["ratios"]) if d["ratios"] else "n/a"),
        d["win"],d["loss"],d["timeouts"]))
lines+=["","## Sum of 25 case PAR2 medians (including all unsolved cases)","",
"| Mode | Sum |","|---|---:|"]
for m in MODES:lines.append("| %s | %.5f s |"%(m,totals[m]))
lines+=["","Contradictions and solver errors: "+(str(errors) if errors else "none detected"),
        "CPU nanoseconds are process-time observations, not processor cycles; clock-based decisions can be sensitive to host load.",
        "Winning one case or family is not a world record or statistical proof."]
report="\n".join(lines)+"\n"
(ROOT/"summary.md").write_text(report)
(ROOT/"totals.json").write_text(json.dumps(totals,indent=2))
(ROOT/"case_diagnostics.json").write_text(json.dumps(details,indent=2))
(ROOT/"family.json").write_text(json.dumps(dict(fams),indent=2,default=lambda x:dict(x)))
with (ROOT/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=raw[0].keys());w.writeheader();w.writerows(raw)
with open(os.environ.get("GITHUB_STEP_SUMMARY",str(ROOT/"step_summary.md")),"a") as f:f.write(report)
print(report,flush=True)
if errors:raise RuntimeError("Incorrect solver answer or ERROR; inspect raw results")
