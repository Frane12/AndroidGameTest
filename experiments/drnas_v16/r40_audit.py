#!/usr/bin/env python3
"""R40 strict blind-to-outcome gate audit; no new SAT work in audit stage."""
import argparse,csv,hashlib,json,random,statistics
from collections import defaultdict
from pathlib import Path
from r40_benchmark import MODES,CAP,REPS
N=8
NATIVE=tuple(m for m in MODES if m!="kissat_pinned")
PREFIX=("stage1","extended","v90_learned_256","v90_lbd2_256","v90_lbd4_256",
 "v90_props_256","v90_conflicts_256","v90_backtracks_256","v90_jumpdepth_256",
 "cpu_256_ns")
# CPU time itself is excluded from prefix equality, because elapsed CPU
# instrumentation is non-deterministic, unlike integer search counters.
PREFIX_EQUAL=tuple(x for x in PREFIX if x!="cpu_256_ns")
def par2(row):
 return float(row["wall_s"]) if row["status"] in ("SAT","UNSAT") else 2*CAP
def mean(s):return sum(s)/len(s)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--combined",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 mp=Path(a.manifest);mf=json.loads(mp.read_text())
 assert mf["protocol"]=="R40-EARLY-RESCUE-UNSEEN-20261103-v1"
 expected={x["id"]:x for x in mf["cases"]}
 assert len(expected)==N and len({x["sha256"] for x in expected.values()})==N
 assert not set(expected).intersection(mf["original18_excluded"])
 assert not set(expected).intersection(mf["prior12_excluded"])
 mfsha=hashlib.sha256(mp.read_bytes()).hexdigest()
 records=[];sha_sets=set();cpu_cores=[]
 for shard in range(4):
  root=Path(a.combined)/f"r40-shard-{shard}"/"results"
  meta=json.loads((root/"meta.json").read_text())
  assert meta["shard"]==shard and meta["manifest_sha256"]==mfsha
  assert meta["cap_s"]==CAP and meta["repetitions"]==REPS
  assert tuple(meta["modes"])==MODES
  assert set(meta["binaries_sha256"])=={"probe","kissat"}
  sha_sets.add(tuple(sorted(meta["binaries_sha256"].items())))
  cpu_cores.append(meta["core"])
  with (root/"raw.csv").open(newline="") as f:rows=list(csv.DictReader(f))
  assert len(rows)==2*REPS*len(MODES),len(rows)
  for r in rows:
   c=expected.get(r["id"])
   assert c and r["sha256"]==c["sha256"]
   assert r["official_label"]==c["official_label"]
   assert r["mode"] in MODES and int(r["rep"]) in range(REPS)
   assert float(r["cap_s"])==CAP
   assert r["status"] in ("SAT","UNSAT","TIMEOUT"),r
   if r["status"]!="TIMEOUT":assert r["status"]==c["official_label"]
   assert not r["error"],r
   checkseed=(920401+int(c["sha256"][:8],16)+int(r["rep"])*101)%2**32
   assert int(r["seed"])==checkseed
   assert float(r["wall_s"])>=0
   records.append(r)
 assert len(sha_sets)==1 and len(records)==N*REPS*len(MODES)
 lookup={(r["id"],int(r["rep"]),r["mode"]):r for r in records}
 assert len(lookup)==len(records)
 assert set(lookup)=={(cid,rep,mode) for cid in expected for rep in range(REPS) for mode in MODES}
 by_case=[];prefix_checked=0;prefix_unknown=0;activated_rescue=[];activated_forced=[]
 for cid in expected:
  block={}
  for mode in MODES:
   rows=[lookup[cid,rep,mode] for rep in range(REPS)]
   block[mode]={"mean_PAR2_s":mean([par2(x) for x in rows]),
     "solved":sum(x["status"] in ("SAT","UNSAT") for x in rows),
     "statuses":[x["status"] for x in rows]}
  for rep in range(REPS):
   native=[lookup[cid,rep,mode] for mode in NATIVE]
   if all(row["status"]!="TIMEOUT" for row in native):
    for key in PREFIX_EQUAL:
     vals={row[key] for row in native}
     assert len(vals)==1,("R40_PRE_INTERVENTION_DIVERGENCE",cid,rep,key,vals)
    prefix_checked+=1
   else:prefix_unknown+=1
   control=lookup[cid,rep,"v91_quality_gate"]
   rescue=lookup[cid,rep,"v91_rescue"]
   forced=lookup[cid,rep,"v91_force_fallback"]
   for mode,row in (("rescue",rescue),("forced",forced)):
    if row["status"]!="TIMEOUT" and row["gate_reason"] in ("r40_rescue_fallback","r40_forced_fallback"):
     assert row["v91_phase_applied"]=="1"
     assert row["extended"]=="0" and row["stage1"]=="0"
     assert int(row["hints"])>0
     (activated_rescue if mode=="rescue" else activated_forced).append((cid,rep))
    if row["status"]!="TIMEOUT" and row["v91_phase_applied"]=="1" and row["extended"]=="0":
     assert row["gate_reason"] in ("r40_rescue_fallback","r40_forced_fallback")
  by_case.append({"id":cid,"label":expected[cid]["official_label"],
     "features":expected[cid]["features"],"modes":block,
     "rescue_activations":sum(a[0]==cid for a in activated_rescue),
     "forced_activations":sum(a[0]==cid for a in activated_forced)})
 by_mode={}
 for mode in MODES:
  rows=[r for r in records if r["mode"]==mode]
  vals=[par2(x) for x in rows]
  by_mode[mode]={"mean_PAR2_s":mean(vals),"sum_PAR2_s":sum(vals),
    "solved":sum(r["status"] in ("SAT","UNSAT") for r in rows),
    "timeouts":sum(r["status"]=="TIMEOUT" for r in rows),
    "best_s":min((float(r["wall_s"]) for r in rows if r["status"]!="TIMEOUT"),default=None)}
 control="v91_quality_gate";active="v91_rescue"
 diffs=[x["modes"][active]["mean_PAR2_s"]-x["modes"][control]["mean_PAR2_s"] for x in by_case]
 base=mean([x["modes"][control]["mean_PAR2_s"] for x in by_case])
 change_pct=100*mean(diffs)/base if base else None
 rng=random.Random(401140)
 bootstrap=[]
 for _ in range(4000):
  ix=[rng.randrange(N) for j in range(N)]
  bas=mean([by_case[i]["modes"][control]["mean_PAR2_s"] for i in ix])
  diff=mean([diffs[i] for i in ix])
  bootstrap.append(100*diff/bas if bas else 0.)
 bootstrap.sort()
 ci=[bootstrap[int(.025*len(bootstrap))],bootstrap[int(.975*len(bootstrap))-1]]
 winner=sum(x<-0.01 for x in diffs)
 loser=sum(x>0.01 for x in diffs)
 severe_regressions=sum(
  x["modes"][active]["mean_PAR2_s"]>2*x["modes"][control]["mean_PAR2_s"]+0.01
  for x in by_case)
 report={
 "protocol":"R40_PROSPECTIVE_OFFICIAL_V91_FALLBACK_RESCUE",
 "sources":{"manifest_sha256":mfsha,"binary_hashes":dict(next(iter(sha_sets))),
            "case_source":"SAT Competition 2026, additional frozen 8; no reuse of R37 12 or preceding 18"},
 "n_official_cases":N,"n_native_and_kissat_trials":len(records),
 "paired_seeds_per_formula":REPS,"cap_s":CAP,
 "source_label_check":"Matches published SAT/UNSAT status; native SAT witness checked by probe; no independent UNSAT proof artifact",
 "preintervention_identical_integer_prefix":prefix_checked,
 "preintervention_prefix_unknown_due_to_timeout":prefix_unknown,
 "active_rescue_attempts":len(activated_rescue),"active_rescue_formulas":len(set(x[0] for x in activated_rescue)),
 "forced_fallback_attempts":len(activated_forced),
 "primary_rescue_vs_frozen_gate":{"change_percent_positive_means_regression":change_pct,
   "bootstrap_95_percent_by_formula":ci,
   "win_cases":winner,"regression_cases":loser,
   "regressions_over_2x_cases":severe_regressions},
 "modes":by_mode,"cases":by_case,
 "limitations":["Only 8 preselected published official cases and 2 seeds; selection feasibility biased",
    "One small test cannot demonstrate general SAT algorithm superiority",
    "CPU time and wall time influenced by GitHub scheduling; paired order randomized",
    "No independent UNSAT certificate in this workflow",
    "If active_rescue_attempts=0, experiment has NO evidence of rescue usefulness even if audit passes",
    "No V15.3.1 comparator in this small native probe; untouched stable baseline",
    "No threshold adjustment after holdout; R39 historic tuning context only"]
 }
 Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
 print("R40_AUDIT_PASS",json.dumps({k:v for k,v in report.items() if k in ("n_official_cases","n_native_and_kissat_trials","preintervention_identical_integer_prefix","preintervention_prefix_unknown_due_to_timeout","active_rescue_attempts","active_rescue_formulas","forced_fallback_attempts","primary_rescue_vs_frozen_gate")},sort_keys=True),flush=True)
 print("R40_MODE_PAR2",json.dumps(by_mode,sort_keys=True),flush=True)
 print("| Formula | Label | v9.1 baseline PAR2 | R40 rescue PAR2 | forced rescue PAR2 | v9.1 never PAR2 | Kissat PAR2 | active |")
 print("|---|---|---:|---:|---:|---:|---:|---:|")
 for x in by_case:
  b=x["modes"]
  print("|",x["id"][:8],"|",x["label"],"|",*[f'{b[z]["mean_PAR2_s"]:.3f} |' for z in (control,active,"v91_force_fallback","v91_never_late","kissat_pinned")],x["rescue_activations"],"|")
if __name__=="__main__":main()
