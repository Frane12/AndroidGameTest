#!/usr/bin/env python3
"""Retrospective per-instance explanation of the exact screenshot's 360 runs.

NO solver reruns. Uses artifacts from 41231153158 and 18 frozen official CNFs.
The 2x/15x cap are distinct conditions, never pool as independent instances.
"""
import csv,json,statistics
from collections import Counter,defaultdict
from pathlib import Path
root=Path("old18")
manifest=json.loads(Path("old_manifest/official_shortlong_manifest.json").read_text())
cases={c["id"]:c for c in manifest["cases"]}
assert len(cases)==18
caps=(2.,15.)
modes=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v92_structural")
rows=[]
for shard in range(6):
    p=root/f"official-shortlong-shard-{shard}"/"results"/"raw.csv"
    with p.open(newline="",encoding="utf8") as f:rows+=list(csv.DictReader(f))
assert len(rows)==360
expected={(id,cap,mode,rep) for id in cases for cap in caps for mode in modes for rep in (0,1)}
got={(x["id"],float(x["cap_s"]),x["mode"],int(x["rep"])) for x in rows}
assert expected==got and len(got)==len(rows)
def cost(x):
    if x["status"] in ("SAT","UNSAT"):
        assert x["status"]==cases[x["id"]]["official_label"]
        return float(x["wall_s"])
    assert x["status"]=="TIMEOUT",x
    return float(x["cap_s"])*2
percase=[]
mode_stats={}
for cap in caps:
    mode_stats[cap]={}
    for mode in modes:
        block=[x for x in rows if float(x["cap_s"])==cap and x["mode"]==mode]
        solved=[x for x in block if x["status"] in ("SAT","UNSAT")]
        mode_stats[cap][mode]={"solved":len(solved),"timeouts":len(block)-len(solved),
           "mean_PAR2":round(statistics.mean(map(cost,block)),6),
           "min_finished":min((float(x["wall_s"]) for x in solved),default=None),
           "max_finished":max((float(x["wall_s"]) for x in solved),default=None)}
for id,c in cases.items():
    d={"id":id,"split":c["split"],"status":c["official_label"],
       "stratum":c["stratum"],"vars":c["variables"],"clauses":c["clauses"],
       "features":c["features"],"bycap":{}}
    for cap in caps:
        block=[r for r in rows if r["id"]==id and float(r["cap_s"])==cap]
        d["bycap"][cap]={}
        for mode in modes:
            rec=[r for r in block if r["mode"]==mode]
            d["bycap"][cap][mode]={"solved":sum(r["status"] in ("SAT","UNSAT") for r in rec),
                 "mean_PAR2":round(statistics.mean(cost(r) for r in rec),6),
                 "finished_times":[float(r["wall_s"]) for r in rec if r["status"] in ("SAT","UNSAT")],
                 "gate_reasons":dict(Counter(r.get("gate_reason","") for r in rec)),
                 "phase_hints":list(r.get("hints") for r in rec)}
    percase.append(d)
sparse_extra=[]
ca_wins=[]
for d in percase:
    b=d["bycap"][15.]
    spar=b["v92_sparse"];ca=b["ca_plain"]
    if spar["solved"]>ca["solved"]:
        sparse_extra.append({"id":d["id"],"status":d["status"],"split":d["split"],
            "ca_solved":ca["solved"],"sparse_solved":spar["solved"],
            "ca_PAR2":ca["mean_PAR2"],"sparse_PAR2":spar["mean_PAR2"]})
    if spar["mean_PAR2"]>ca["mean_PAR2"]:
        ca_wins.append({"id":d["id"],"status":d["status"],"split":d["split"],
            "ca_PAR2":ca["mean_PAR2"],"sparse_PAR2":spar["mean_PAR2"]})
top=sorted(percase,key=lambda d:(d["bycap"][15.]["ca_plain"]["mean_PAR2"]/
          d["bycap"][15.]["v92_sparse"]["mean_PAR2"]),reverse=True)
report={"source_run":41231153158,"audit_run":41232079816,
        "measurement_count":len(rows),"case_count":18,
        "mode_by_cap":mode_stats,"cases":percase,
        "more_successful_than_Ca":sparse_extra,"sparse_regressions":ca_wins,
        "highest_relative_PAR2_gains":[{
            "id":d["id"],"status":d["status"],"split":d["split"],
            "ratio":round(d["bycap"][15.]["ca_plain"]["mean_PAR2"]/
                          d["bycap"][15.]["v92_sparse"]["mean_PAR2"],4)}
            for d in top[:6]],
        "warning":"Prior 18 public cases were used in model exploration; this is RETROSPECTIVE and cannot validate a tuned gate."}
Path("v94_historical_360_diagnosis.json").write_text(json.dumps(report,indent=2))
l=["# DRNAS v9.4 preflight — screenshot 360 attempts retrospective audit",
    "Frozen inputs 18, official SAT Competition 2026, 5 modes, 2 repeats, 2 wall caps (2s and 15s).",
    "The v9.4 selector has NOT been tested on these records. Previous v9.2 results are descriptive.",
    "","## Exact screenshot at 15s",
    "| Mode | Solved/36 | Timeout/36 | Mean PAR2 s |","|---|---:|---:|---:|"]
for m in modes:
    x=mode_stats[15.][m]
    l.append("| %s | %d | %d | %.5f |"%(m,x["solved"],x["timeouts"],x["mean_PAR2"]))
l+=["","## Two extra sparse solutions relative to CaDiCaL (paired case detail)",
    json.dumps(sparse_extra,indent=2),"",
    "## All 18 case mean PAR2 at 15s (two repeats)",
    "| Case ID | Label | Split | CaDiCaL | V7.6 guided | V7.6 no hints | v9.2 Sparse | v9.2 Structural | Ca/Sparse |",
    "|---|---|---|---:|---:|---:|---:|---:|---:|"]
for d in percase:
    a=d["bycap"][15.]
    l.append("| %s | %s | %s | "%(d["id"][:10],d["status"],d["split"])+
             " | ".join("%.3f"%a[m]["mean_PAR2"] for m in modes)+
             " | %.2fx |"%(a["ca_plain"]["mean_PAR2"]/a["v92_sparse"]["mean_PAR2"]))
l+=["","## Best relative v9.2 sparse results",
    json.dumps(report["highest_relative_PAR2_gains"],indent=2),"",
    "Note: a timeout is CENSORED at 15s; PAR2 charges 30s. Do not infer true solver time beyond 15s.",
    "Two repeats on one instance do not represent two independent NP problems.",
    "This is not a generalization test, but the source-backed basis for the v9.4 follow-up."]
Path("v94_historical_360_diagnosis.md").write_text("\n".join(l)+"\n")
print("\n".join(l),flush=True)
