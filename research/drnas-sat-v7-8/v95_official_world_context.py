#!/usr/bin/env python3
"""Historical comparison to official 2026 fastest instance-wise Main-track runs.
WARNING: Github-hosted seconds and SAT Competition HoreKa hardware seconds
are NOT directly comparable; local < official does not certify a record.
"""
import csv,json,statistics
from collections import defaultdict
from pathlib import Path
src=Path("prior95/ablate-v95/v95_ablation.json")
j=json.loads(src.read_text())
cases=j["case"]
with Path("official_scores.csv").open(newline="",encoding="utf8") as f:
    rows=list(csv.DictReader(f))
best={}
for r in rows:
    id=r["instanceid"]
    if id not in cases or r["status"] not in ("sat-verified","unsat-verified"):continue
    t=float(r["runtime"])
    if id not in best or t<best[id][0]:best[id]=(t,r["solverid"])
assert set(best)==set(cases),set(cases)-set(best)
out=[]
for id,c in cases.items():
    local=c["medians"]
    b=best[id]
    out.append({"id":id,"official_label":c["label"],
         "official_best_solver":b[1],"official_best_seconds_on_competition_hardware":b[0],
         "local_CaDiCaL":local["ca_plain"],
         "local_Single96":local["v95_single_plain_checkpoint"],
         "local_DualProbe":local["v95_dual_probe"],
         "local_Single96_faster_numeric_than_official":local["v95_single_plain_checkpoint"]<b[0]})
out.sort(key=lambda x:x["local_Single96"]/x["official_best_seconds_on_competition_hardware"])
Path("v95_official_fastest_per_case.json").write_text(json.dumps(out,indent=2))
l=["# v9.5 original 12 CNFs compared with 2026 officially published fastest per-instance runs",
   "**NOT A WORLD RECORD COMPARISON: CPU/HW, proof validation and time limits differ.**",
   "Local v9.5: GitHub Ubuntu hosted processor / 15s cap / 2 repeats.",
   "Official Main Track: KIT HoreKa/Blue competition hardware / official time limits.",
   "",
   "| Official CNF ID | Truth | Best published solver | Official seconds (different hardware!) | Local CaDiCaL seconds | Local Single-96 seconds | Numeric Single96/official |",
   "|---|---|---|---:|---:|---:|---:|"]
for x in out:
    l.append("| %s | %s | %s | %.4f | %.4f | %.4f | %.3f |"%(
       x["id"][:12],x["official_label"],x["official_best_solver"],
       x["official_best_seconds_on_competition_hardware"],x["local_CaDiCaL"],
       x["local_Single96"],x["local_Single96"]/max(x["official_best_seconds_on_competition_hardware"],1e-9)))
l+=["",
 "Cases with numerically lower local Single96 seconds than official fastest (DIFFERENT HARDWARE, NOT RECORD): "+
 str(sum(x["local_Single96_faster_numeric_than_official"] for x in out)),
 "The official results list many stronger solvers than CaDiCaL; matching the official published fastest on a different machine is not a valid record.",
 "Valid comparison requires running the best competing solver and Single96 on identical hardware and with independently verified UNSAT proofs."]
Path("v95_official_fastest_per_case.md").write_text("\n".join(l)+"\n")
print("\n".join(l),flush=True)
