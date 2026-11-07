#!/usr/bin/env python3
"""v9.4 2026 official 12-CNF newly frozen holdout, fail-closed paired PAR2 audit.

Do NOT compare 12-case sums directly to the earlier 18-case results.
The original v9.2 Sparse 15s 20/36 mean-PAR2 15.993 is a HISTORICAL
reference, not evidence of v9.4 transfer to the new cohort.
"""
import csv,json,statistics,sys
from collections import Counter,defaultdict
from pathlib import Path
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path("combined-v94")
manifest=json.loads(Path("official_manifest/official_v94_manifest.json").read_text())
assert len(manifest["cases"])==12
assert len(set(x["id"] for x in manifest["cases"]))==12
assert not(set(x["id"] for x in manifest["cases"])&set(manifest["original_18_excluded"]))
modes=("ca_plain","orig_v76","orig_v76_plain","v92_sparse","v94_cautious")
rows=[];issues=[]
for i in range(4):
    with (root/("official-v94-shard-"+str(i))/"results"/"raw.csv").open(newline="") as f:
        rows.extend(csv.DictReader(f))
assert len(rows)==12*len(modes)*2,len(rows)
lookup={x["id"]:x for x in manifest["cases"]}
expected={(id,mode,r) for id in lookup for mode in modes for r in (0,1)}
observed={(r["id"],r["mode"],int(r["rep"])) for r in rows}
assert len(observed)==len(rows) and observed==expected
for r in rows:
    i=lookup[r["id"]]
    if r["sha256"]!=i["sha256"]:issues.append("SHA mismatch "+r["id"])
    if float(r["cap_s"])!=15.0:issues.append("Wrong limit "+r["id"])
    if r["status"] not in ("SAT","UNSAT","TIMEOUT"):issues.append("ERROR "+r["id"]+" "+r["mode"]+" "+r["error"])
    if r["status"] in ("SAT","UNSAT") and r["status"]!=i["official_label"]:
        issues.append("Incorrect answer "+r["id"]+" "+r["mode"]+" "+r["status"])
bycase=defaultdict(dict)
outcomes=[]
for id in lookup:
    for mode in modes:
        rr=[r for r in rows if r["id"]==id and r["mode"]==mode]
        assert len(rr)==2
        penalty=[float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 30.
                 for r in rr]
        bycase[id][mode]=statistics.mean(penalty)
    modelrecs=[r for r in rows if r["id"]==id and r["mode"]=="v94_cautious"]
    choices=Counter(r.get("gate_reason","") for r in modelrecs)
    outcomes.append({"case":id,"official_label":lookup[id]["official_label"],
       "stratum":lookup[id]["stratum"],"sha256":lookup[id]["sha256"],
       "features":lookup[id]["features"],"selected_modes":dict(choices),
       "cost":bycase[id],"speedup_ca_over_v94":bycase[id]["ca_plain"]/bycase[id]["v94_cautious"]})
means={mode:statistics.mean(bycase[id][mode] for id in lookup) for mode in modes}
solved={mode:sum(r["status"] in ("SAT","UNSAT") for r in rows if r["mode"]==mode)
        for mode in modes}
timeouts={mode:24-solved[mode] for mode in modes}
families={}
for name in ("SAT","UNSAT"):
    ids=[id for id in lookup if lookup[id]["official_label"]==name]
    families[name]={"count":len(ids),"mean_PAR2":{
        m:statistics.mean(bycase[id][m] for id in ids) for m in modes},
        "solved":{m:sum(r["status"]==name for r in rows if r["mode"]==m and r["id"] in ids)
                  for m in modes}}
assert families["SAT"]["count"]==6 and families["UNSAT"]["count"]==6
wins=sum(x["speedup_ca_over_v94"]>1.25 for x in outcomes)
losses=sum(x["speedup_ca_over_v94"]<.8 for x in outcomes)
strongest=max(outcomes,key=lambda x:x["speedup_ca_over_v94"])
weakest=min(outcomes,key=lambda x:x["speedup_ca_over_v94"])
report={"protocol":manifest["protocol"],"count":12,"repeat":2,"cap_s":15,
        "all_raw_trials":len(rows),"mean_PAR2_s":means,
        "solved":solved,"timeouts":timeouts,"by_outcome":families,
        "wins_over_cadical_gt_1p25x":wins,"losses_under_0p8x":losses,
        "best_single":strongest,"worst_single":weakest,
        "per_case":outcomes,"errors":issues,
        "reference_prior_18_not_same_cases":{
            "v92_sparse_15s_mean_PAR2":15.9931,"v92_sparse_solved":20,
            "ca_plain_15s_mean_PAR2":17.3518,"ca_plain_solved":16,
            "trials_per_mode":36},
        "limitations":["Official 2026 public results used to stratify cases, not a blind benchmark",
            "New 12 CNFs disjoint from previous project 18 but selected by baseline difficulty",
            "Small sample, only two repeats and variable finish times on shared GitHub runners",
            "SAT model C++ witness checking; no independent UNSAT DRAT/LRAT proof",
            "Don't claim a world record or universal speedup"] }
(root/"v94_report.json").write_text(json.dumps(report,indent=2))
lines=[
"# DRNAS v9.4 — official 2026 new 12-case transfer audit","",
"12 NEW CNFs disjoint from prior 18, 6 SAT + 6 UNSAT, two repeats, 15s wall cap.",
"120 paired attempts. PAR2 timeout penalty = 30s. Same GitHub single CPU.",
"New precommitted CNF-only cautious sparse-vs-CaDiCaL gate vs frozen controls.",
"",
"| Mode | Solved/24 | Timeouts | Mean PAR2 seconds (lower better) |",
"|---|---:|---:|---:|"]
for mode in modes:
    lines.append("| %s | %d/24 | %d | %.5f |"%(mode,solved[mode],timeouts[mode],means[mode]))
lines+=["","## SAT vs UNSAT, mean PAR2 per attempt",
 "| Type | N cases | "+" | ".join(modes)+" |",
 "|---|---:|"+("".join("---:|" for x in modes))]
for typ in ("SAT","UNSAT"):
    d=families[typ]
    lines.append("| %s | %d | "%(typ,d["count"])+" | ".join("%.4f"%d["mean_PAR2"][m] for m in modes)+" |")
lines+=["","## Every paired case (mean PAR2 of 2 repeats)",
"| ID | Label | CaDiCaL | V7.6 Guided | V7.6 No Hints | V9.2 Sparse | V9.4 Cautious | Ca/V9.4 | V9.4 decision |",
"|---|---|---:|---:|---:|---:|---:|---:|---|"]
for x in outcomes:
    c=x["cost"]
    lines.append("| %s | %s | "%(x["case"][:12],x["official_label"])+
       " | ".join("%.3f"%c[m] for m in modes)+
       " | %.2fx | %s |"%(x["speedup_ca_over_v94"],str(x["selected_modes"])))
lines+=["","Practical v9.4 wins >1.25x: %d; losses <0.8x: %d."%(wins,losses),
       "Biggest gain vs CaDiCaL: %s %.3fx"%(strongest["case"],strongest["speedup_ca_over_v94"]),
       "Largest regression vs CaDiCaL: %s %.3fx"%(weakest["case"],weakest["speedup_ca_over_v94"]),
       "Errors: "+("none detected" if not issues else str(issues)),
       "Historical 18-case v9.2 sparse 15s: 20/36, 15.993s average PAR2; CaDiCaL 16/36, 17.352s.",
       "That historical result is NOT pooled with this new disjoint 12-case sample.",
       "The benchmark cannot establish a world record or general solver superiority."]
body="\n".join(lines)+"\n"
(root/"v94_report.md").write_text(body)
with (root/"all_raw.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
print(body,flush=True)
if issues:raise RuntimeError("Benchmark invalid: "+str(issues[:5]))
