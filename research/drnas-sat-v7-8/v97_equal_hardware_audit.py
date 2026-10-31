#!/usr/bin/env python3
"""DRNAS v9.7 strict same-runner 2026 submitted binaries comparison.

Five handpicked previous candidates and TWO negative UNSAT controls.
Unlike cross-hardware published-time comparisons, every mode for one
formula runs sequentially in one GitHub job pinned to the same CPU.
Not representative sample or an officially recognized 'world record'.
"""
import csv,json,statistics
from pathlib import Path
from collections import Counter
CANDIDATES=("ee44c3f46423","2b35377a7b95","8d0d8518a438",
            "2b8cac8e1f5c","3ed56242f55e")
MODES=("drnas_single96","drnas_single128","ca_plain","mergesat-l",
       "mergesat","kissat-mab-eae2","kissat-lr-ds","cadical3")
MAP={"zhenwei_mergesat-l[main-ai]":"mergesat-l",
     "biere_cadical3[main]":"cadical3",
     "ding_kissat-mab-eae2[main-ai]":"kissat-mab-eae2",
     "zhenwei_mergesat[main]":"mergesat",
     "liang_kissat-lr-ds[main]":"kissat-lr-ds"}
old=json.loads(Path("manifests/old/official_v94_manifest.json").read_text())
new=json.loads(Path("manifests/new/official_v96_manifest.json").read_text())
allcases={x["id"]:x for x in old["cases"]+new["cases"]}
original_best={}
with Path("official_scores.csv").open(newline="",encoding="utf8") as fh:
    for r in csv.DictReader(fh):
        if r["instanceid"] not in allcases:continue
        if r["status"] not in ("sat-verified","unsat-verified"):continue
        t=float(r["runtime"])
        k=r["instanceid"]
        if k not in original_best or t<original_best[k][0]:
            original_best[k]=(t,r["solverid"])
rows=[]
rows_by_shard={}
for i in range(3):
    folder=Path("v97-results")/f"v97-shard-{i}"/"results"
    with (folder/"raw.csv").open(newline="") as f:
        shard_rows=list(csv.DictReader(f))
    assert shard_rows,("empty raw.csv",i)
    with (folder/"meta.json").open() as f:
        meta=json.load(f)
    assert meta["shard"]==i
    assert len(shard_rows)==len(meta["cases"])*len(MODES)*3
    assert {r["case"] for r in shard_rows}=={c["id"] for c in meta["cases"]}
    assert {int(r["cpu_core"]) for r in shard_rows}=={int(meta["cpu_core"])}
    # Each GitHub runner builds DRNAS separately: compiler/build paths may
    # make binary SHA differ ACROSS runners without changing the program.
    # Check hashes strictly WITHIN each runner and matched formula.
    for mode in MODES:
        local_hashes={r["binary_sha256"] for r in shard_rows if r["mode"]==mode}
        assert len(local_hashes)==1,("same-runner binary changed",i,mode,local_hashes)
        assert all(len(h)==64 for h in local_hashes),("invalid SHA256",i,mode)
    drnas_hashes={r["binary_sha256"] for r in shard_rows
                  if r["mode"] in ("drnas_single96","drnas_single128","ca_plain")}
    assert len(drnas_hashes)==1,("DRNAS variants didn't share one executable",i)
    rows_by_shard[i]=shard_rows
    rows+=shard_rows
# These exact official entrants were compiled once each and their binaries
# were downloaded unchanged by all runners; their hashes MUST match globally.
official_modes=("mergesat-l","mergesat","kissat-mab-eae2","kissat-lr-ds","cadical3")
for mode in official_modes:
    sha={r["binary_sha256"] for r in rows if r["mode"]==mode}
    assert len(sha)==1,("official submission binary mismatch",mode,sha)
assert len(rows)==7*len(MODES)*3, len(rows)
ids=set(r["case"] for r in rows)
assert len(ids)==7
expected={(id,m,r) for id in ids for m in MODES for r in (0,1,2)}
observed={(r["case"],r["mode"],int(r["rep"])) for r in rows}
assert len(rows)==len(observed) and expected==observed
issues=[]
for r in rows:
    case=allcases[r["case"]]
    if r["sha256"]!=case["sha256"]:issues.append("wrong CNF SHA "+r["case"])
    if r["status"] not in ("SAT","UNSAT","TIMEOUT"):issues.append("invalid result "+r["case"]+" "+r["mode"])
    if r["status"] in ("SAT","UNSAT") and r["status"]!=case["official_label"]:
        issues.append("wrong SAT/UNSAT answer "+r["case"]+" "+r["mode"])
    # Binary integrity was already checked per source runner above.
assert not issues,issues[:5]
def cost(r):return float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 30.
per={}
for id in ids:
    d=allcases[id]
    info={"id":id,"label":d["official_label"],"cohort":next(r["cohort"] for r in rows if r["case"]==id),
          "published_best":original_best.get(id),
          "solvers":{}}
    for mode in MODES:
        subset=[r for r in rows if r["case"]==id and r["mode"]==mode]
        assert len(subset)==3 and {int(r["rep"]) for r in subset}=={0,1,2}
        times=[float(r["wall_s"]) for r in subset if r["status"] in ("SAT","UNSAT")]
        info["solvers"][mode]={"solved":len(times),"median_PAR2":statistics.median(cost(r) for r in subset),
            "time_min":min(times) if times else None,"time_max":max(times) if times else None,
            "all_statuses":[r["status"] for r in subset],
            "binary_sha256":subset[0]["binary_sha256"]}
    per[id]=info
matched=[]
for prefix in CANDIDATES:
    cand=[x for x in per.values() if x["id"].startswith(prefix)]
    assert len(cand)==1,prefix
    x=cand[0]
    assert x["label"]=="SAT"
    fastest=x["published_best"]
    assert fastest is not None and fastest[1] in MAP,fastest
    champion=MAP[fastest[1]]
    ref=x["solvers"][champion]
    finalists=[(m,x["solvers"][m]) for m in ("drnas_single96","drnas_single128")]
    finalists.sort(key=lambda z:z[1]["median_PAR2"])
    winner=finalists[0]
    valid=(ref["solved"]==3 and winner[1]["solved"]==3)
    ratio=(ref["median_PAR2"]/winner[1]["median_PAR2"]) if valid else None
    matched.append({"id":x["id"],"champion":champion,
      "published_fastest":fastest,"matched_competitor":ref,
      "best_drnas_budget":winner[0],"best_drnas":winner[1],
      "speedup_same_hardware":ratio,
      "stronger_same_hardware":valid and ratio>1.0,
      "stronger_by_1p25x":valid and ratio>=1.25})
total={mode:{"solved":sum(per[k]["solvers"][mode]["solved"] for k in ids),
             "mean_PAR2":statistics.mean(per[k]["solvers"][mode]["median_PAR2"] for k in ids)}
       for mode in MODES}
report={"cases":len(ids),"repeats":3,"attempts":len(rows),
    "limit_s":15,"timeout_PAR2_s":30,"matched_five":matched,
    "numeric_faster_same_cpu":sum(x["stronger_same_hardware"] for x in matched),
    "large_win_same_cpu":sum(x["stronger_by_1p25x"] for x in matched),
    "all_mode_totals":total,"per_case":list(per.values()),
    "warnings":["Five record candidates were PRESELECTED using prior DRNAS outcomes; this is NOT a random sample",
    "Same GitHub runner core per formula, but not necessarily identical CPU between separate shards",
    "Compiled from original SAT Competition 2026 source archives using supplied build.sh; not original competition environment",
    "Not official world-record validation, and UNSAT independently verified proofs absent",
    "Per-formula best of two DRNAS budgets is post-hoc selection and optimistically biased",
    "DRNAS executables freshly compiled on three runners: SHA256 checked inside each runner; official archives unchanged globally"]}
root=Path("v97-results")
(root/"v97_final_audit.json").write_text(json.dumps(report,indent=2))
lines=["# DRNAS v9.7 — same-CPU comparison to exact 2026 submitted solver binaries",
"",
"Five previously identified candidates plus 2 UNSAT control CNFs, 8 solvers,",
"3 repetitions = 168 trials, 15 s limit and 30s timeout PAR2.",
"All competitors are built from official 2026 archived sources; every formula",
"uses ONE GH Actions runner and CPU affinity across all methods.",
"Published competition result is CONTEXT ONLY (different hardware).",
"",
"## FIVE individual potential fastest results",
"| Formula | Official fastest solver (exact submission) | Published 2026 seconds (different HW) | Same-runner official solver median | DRNAS best budget | DRNAS median same runner | Same-runner ratio | Verdict |",
"|---|---|---:|---:|---|---:|---:|---|"]
for x in matched:
    ratio=x["speedup_same_hardware"]
    ref=x["matched_competitor"];winner=x["best_drnas"]
    lines.append("| %s | %s | %.3f | %s | %s | %s | %s | %s |"%(
        x["id"][:12],x["champion"],x["published_fastest"][0],
        "%.3fs (%d/3)"%(ref["median_PAR2"],ref["solved"]),
        x["best_drnas_budget"],"%.3fs (%d/3)"%(winner["median_PAR2"],winner["solved"]),
        "%.2fx"%ratio if ratio is not None else "n/a",
        "DRNAS faster (same HW)" if x["stronger_same_hardware"] else "Not confirmed"))
lines+=["",
 "Numerically faster on SAME CPU against the corresponding 2026 champion (both solve 3/3): "+
 str(report["numeric_faster_same_cpu"])+"/5.",
 "By at least 1.25x on SAME CPU with both solvers finished 3/3: "+str(report["large_win_same_cpu"])+"/5.",
 "Additional instances where DRNAS solved 3/3 but champion timed out 3/3: "+
 str(sum(x["best_drnas"]["solved"]==3 and x["matched_competitor"]["solved"]==0 for x in matched))+"/5.",
 "These timeout-only advantages cannot be assigned finite speedup ratios.",
 "",
 "## Full 7-case aggregate including two UNSAT controls",
 "| Solver | Solved/21 | Mean per-case PAR2 s (lower better) |",
 "|---|---:|---:|"]
for mode in MODES:
    t=total[mode]
    lines.append("| %s | %d/21 | %.4f |"%(mode,t["solved"],t["mean_PAR2"]))
lines+=["",
 "## Individual outcomes (all candidates and UNSAT controls)",
 "| Formula | Official answer | DRNAS 96 | DRNAS 128 | Plain CaDiCaL | MergeSAT-L | MergeSAT | Kissat-MAB-EAE2 | Kissat-LR-DS | official CaDiCaL3 |",
 "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
for x in sorted(per.values(),key=lambda x:x["id"]):
    lines.append("| %s | %s | "%(x["id"][:12],x["label"])+
        " | ".join("%.3f"%x["solvers"][mode]["median_PAR2"] for mode in MODES)+" |")
lines+=["",
"**Important:** even a same-CPU win on an official submitted solver is an",
"instance-level best-known candidate, NOT a recognized SAT Competition world record.",
"This handpicked set and best-of-two-budget methodology do not establish",
"any advantage on the official 400-problem Main Track or general NP solving.",
"Correctness: all solved answers match publicly verified SAT/UNSAT; independent",
"UNSAT proof checking and SAT witness checking of external solvers remain needed."]
body="\n".join(lines)+"\n"
(root/"v97_final_audit.md").write_text(body)
with (root/"v97_all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print(body,flush=True)
