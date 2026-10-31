#!/usr/bin/env python3
"""Strict causal ablation of the observed 96-conflict v9.5 improvement.
Single checkpoint same CNF, no second solver, no selection.
Historical dataset (already seen in prior v9.4 and v9.5), not blind.
"""
import csv,json,statistics,sys
from collections import defaultdict,Counter
from pathlib import Path
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path("ablate-v95")
manifest=json.loads(Path("official_manifest/official_v94_manifest.json").read_text())
cases={x["id"]:x for x in manifest["cases"]}
assert len(cases)==12
modes=("ca_plain","orig_v76_plain","v95_single_plain_checkpoint","v95_dual_probe")
raw=[]
for i in range(4):
    path=root/f"official-v95-ablate-shard-{i}"/"results"/"raw.csv"
    with path.open(newline="") as f:raw+=list(csv.DictReader(f))
assert len(raw)==12*len(modes)*2
expected={(id,mode,r) for id in cases for mode in modes for r in (0,1)}
actual={(r["id"],r["mode"],int(r["rep"])) for r in raw}
assert len(raw)==len(actual) and actual==expected
issues=[]
for r in raw:
    if r["sha256"]!=cases[r["id"]]["sha256"]:issues.append("hash mismatch "+r["id"])
    if float(r["cap_s"])!=15.:issues.append("wrong cap")
    if r["status"] not in ("SAT","UNSAT","TIMEOUT"):issues.append("error "+r["id"]+" "+r["error"])
    if r["status"] in ("SAT","UNSAT") and r["status"]!=cases[r["id"]]["official_label"]:
        issues.append("incorrect answer "+r["id"])
def penalty(r):
    return float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 30.
pairs={};solved={m:0 for m in modes}
means={}
for id in cases:
    pairs[id]={}
    for m in modes:
        rr=[r for r in raw if r["id"]==id and r["mode"]==m]
        assert len(rr)==2
        pairs[id][m]=statistics.mean(penalty(r) for r in rr)
        solved[m]+=sum(r["status"] in ("SAT","UNSAT") for r in rr)
for m in modes:means[m]=statistics.mean(pairs[id][m] for id in cases)
sums={m:sum(pairs[id][m] for id in cases) for m in modes}
outcomes=Counter(r.get("gate_reason","") for r in raw if r["mode"]=="v95_dual_probe")
probe_known=[r for r in raw if r["mode"]=="v95_dual_probe" and r["status"] in ("SAT","UNSAT")
             and r.get("probe_us","") not in ("",None)]
ms_probe=[float(r["probe_us"])/1000 for r in probe_known]
dual_better=sum(pairs[id]["v95_dual_probe"]<pairs[id]["v95_single_plain_checkpoint"]*.8 for id in cases)
single_better=sum(pairs[id]["v95_dual_probe"]>pairs[id]["v95_single_plain_checkpoint"]*1.25 for id in cases)
report={"count":12,"attempts":len(raw),"solved":solved,"means":means,
        "sums":sums,"dual_gate_reasons":dict(outcomes),
        "dual_vs_single_strong_wins":dual_better,"dual_vs_single_strong_losses":single_better,
        "measured_dual_probe_ms_median":statistics.median(ms_probe) if ms_probe else None,
        "case":{id:{"label":cases[id]["official_label"],"medians":pairs[id]} for id in cases},
        "errors":issues,"method_limitations":["These cases are already viewed",
         "Selected formula families size-bounded; no official competition performance claim",
         "Causal comparison is between single 96-conflict split and double 96-conflict split",
         "Only two wall clock repeats; UNSAT proof not independently checked"]}
(root/"v95_ablation.json").write_text(json.dumps(report,indent=2))
lines=["# DRNAS v9.5 — essential falsification: single 96-conflict probe vs dual",
       "12 previously-viewed official SAT Competition 2026 CNFs; 96 matched",
       "attempts, four modes, two repetitions, 15s wall cap, 30s PAR2 timeout.",
       "Same frozen CaDiCaL 3.0.1 and input SHA256 across runner shards.",
       "",
       "| Method | Solved/24 | Mean PAR2 s (lower better) | Sum of 12 formula mean PAR2 |",
       "|---|---:|---:|---:|"]
for m in modes:
    lines.append("| %s | %d/24 | %.5f | %.5f |"%(m,solved[m],means[m],sums[m]))
lines+=["","## Per-case results",
        "| Case | Official answer | Plain CaDiCaL | Frozen V7.6 no hints | SINGLE 96 | DUAL 96+96 | Single/dual |",
        "|---|---|---:|---:|---:|---:|---:|"]
for id in cases:
    c=pairs[id]
    lines.append("| %s | %s | "%(id[:12],cases[id]["official_label"])+
        " | ".join("%.3f"%c[m] for m in modes)+
        " | %.2fx |"%(c["v95_single_plain_checkpoint"]/c["v95_dual_probe"]))
lines+=["","Dual gate_reason from completed (censored timeouts have none): "+
        str(dict(outcomes)),
        "Strong dual wins vs single >1.25x: %d, losses >1.25x: %d."%(dual_better,single_better),
        "Median completed dual first-probe+CNF construction cost: %s ms"%(
             ("%.3f"%statistics.median(ms_probe)) if ms_probe else "no measured"),
        "Errors: "+("none detected" if not issues else str(issues)),
        "Interpretation: if SINGLE96 approximates DUAL96+96, the gain is checkpoint/resume, NOT two-arm selection.",
        "No universal or world-record claim from 12 previously viewed samples."]
body="\n".join(lines)+"\n"
(root/"v95_ablation.md").write_text(body)
with (root/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=raw[0].keys());w.writeheader();w.writerows(raw)
print(body,flush=True)
if issues:raise RuntimeError("Incorrect source/correctness in v9.5 ablation")
