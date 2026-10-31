#!/usr/bin/env python3
"""True project-level unseen official SAT 2026 fixed-checkpoint budget audit.

Compare official fastest *contextually* only. Different hardware and official
time limits prohibit claims of world records even if local seconds are lower.
"""
import csv,json,statistics,math
from pathlib import Path
from collections import Counter
root=Path("v96-results")
manifest=json.loads(Path("official_manifest/official_v96_manifest.json").read_text())
cases={c["id"]:c for c in manifest["cases"]}
modes=tuple(manifest["methods_frozen"])
assert len(cases)==12 and len(manifest["prior_30_excluded"])==30
assert modes==("ca_plain","v96_64","v96_96","v96_128","v96_256")
rows=[]
for shard in range(4):
    p=root/f"v96-shard-{shard}"/"results"/"raw.csv"
    with p.open(newline="") as fh:rows+=list(csv.DictReader(fh))
assert len(rows)==len(cases)*len(modes)*2,len(rows)
keys={(r["id"],r["mode"],int(r["rep"])) for r in rows}
assert len(keys)==len(rows)
assert keys=={(id,m,r) for id in cases for m in modes for r in (0,1)}
errors=[]
for r in rows:
    c=cases[r["id"]]
    if r["sha256"]!=c["sha256"]:errors.append("CNF SHA mismatch "+r["id"])
    if float(r["cap_s"])!=15.:errors.append("Unexpected cap")
    if r["status"] not in ("SAT","UNSAT","TIMEOUT"):
        errors.append("ERROR "+r["id"]+" "+r["mode"]+" "+r.get("error",""))
    if r["status"] in ("SAT","UNSAT") and r["status"]!=c["official_label"]:
        errors.append("WRONG RESULT "+r["id"]+" "+r["mode"])
if errors:raise RuntimeError("Invalid benchmark "+repr(errors))
def cost(r):return float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 30.
per={}
solved={m:0 for m in modes}
for case in cases:
    per[case]={}
    for mode in modes:
        rr=[r for r in rows if r["id"]==case and r["mode"]==mode]
        assert len(rr)==2
        per[case][mode]=statistics.mean(cost(r) for r in rr)
        solved[mode]+=sum(r["status"] in ("SAT","UNSAT") for r in rr)
mean={m:statistics.mean(per[k][m] for k in cases) for m in modes}
bytruth={}
for truth in ("SAT","UNSAT"):
    ids=[id for id in cases if cases[id]["official_label"]==truth]
    assert len(ids)==6
    bytruth[truth]={"mean_PAR2":{m:statistics.mean(per[id][m] for id in ids)
                                for m in modes},
                    "solved":{m:sum(r["status"]==truth for r in rows
                                     if r["mode"]==m and r["id"] in ids)
                              for m in modes}}
percase=[]
for id in cases:
    c=cases[id]
    winning=min(modes,key=lambda m:per[id][m])
    percase.append({"id":id,"truth":c["official_label"],
      "features":c["features"],"official_fastest_solver":c["official_fastest_solver"],
      "official_fastest_seconds_on_official_hardware":c["official_best_s"],
      "official_cadical_seconds_on_official_hardware":c["official_baseline_s"],
      "local_PAR2_s":per[id],"best_local_mode":winning,
      "best_local_ratio_to_cadical_PAR2":
         per[id]["ca_plain"]/max(per[id][winning],1e-9)})
best=max(percase,key=lambda x:x["best_local_ratio_to_cadical_PAR2"])
report={"official_results_pinned_revision":manifest["reference"],
 "new_cases":12,"prior_30_excluded":30,"runs":len(rows),
 "modes":modes,"solved":solved,"mean_PAR2_seconds":mean,
 "SAT_UNSAT":bytruth,"per_case":percase,
 "biggest_single_gain":best,
 "warnings":["Not an official SAT Competition score; runs on GitHub Actions Ubuntu, not HoreKa/Blue competition machines",
 "Official fastest published per-instance runtimes are different hardware and time limits",
 "The 12 cases were selected conditional on official baseline times and size, so sampling biased",
 "2 repeats on 12 instances, no independent UNSAT certificates; no world record claim supported"]}
root.mkdir(exist_ok=True)
(root/"v96_report.json").write_text(json.dumps(report,indent=2))
lines=[
"# DRNAS SAT v9.6 — 12 completely NEW official 2026 competition CNFs",
"",
"12 instances disjoint from ALL 30 previously seen in the project.",
"6 official SAT and 6 official UNSAT, 5 frozen variants x 2 repeats = 120 trials.",
"Four single-core Github Actions shards, external wall limit 15s, PAR2 timeout 30s.",
"Selection uses only public official CaDiCaL times near 12s and file size.",
"Different hardware prevents record claims against published official solver times.",
"",
"| Mode | Solved / 24 | Mean PAR2 s (lower better) | Compared with local plain CaDiCaL |",
"|---|---:|---:|---:|"]
for m in modes:
    lines.append("| %s | %d/24 | %.4f | %.2f%% |"%(
        m,solved[m],mean[m],(mean["ca_plain"]/mean[m]-1)*100))
lines+=["","## SAT / UNSAT generalization",
 "| Truth | N | "+" | ".join(modes)+" |",
 "|---|---:|"+":---:|"*len(modes)]
for t in ("SAT","UNSAT"):
    lines.append("| %s | 6 | "%t+" | ".join("%.3f"%bytruth[t]["mean_PAR2"][m] for m in modes)+" |")
lines+=["","## All source-verified new instances and world-leading reference context",
"| 2026 CNF ID | Truth | Local plain | Local 64 | Local 96 | Local 128 | Local 256 | Best local vs plain | Official fastest (published *different hardware*) |",
"|---|---|---:|---:|---:|---:|---:|---:|---|"]
for c in percase:
    v=c["local_PAR2_s"]
    lines.append("| %s | %s | "%(c["id"][:12],c["truth"])+
      " | ".join("%.3f"%v[m] for m in modes)+
      " | %.2fx | %s: %.3fs |"%(c["best_local_ratio_to_cadical_PAR2"],
          c["official_fastest_solver"],c["official_fastest_seconds_on_official_hardware"]))
lines+=["","Best local individual: "+json.dumps(best,ensure_ascii=False),
       "All 120 attempts verified and no detected solver contradiction.",
       "**No world record can be established** without identical competition hardware, official fixed benchmark and independent correctness checking.",
       "The official 2026 fastest-per-CNF value is CONTEXT ONLY, never used as a local competing stopwatch."]
body="\n".join(lines)+"\n"
(root/"v96_report.md").write_text(body)
with (root/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print(body,flush=True)
