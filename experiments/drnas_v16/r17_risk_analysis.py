#!/usr/bin/env python3
"""R17 prospective risk-aware native SAT benchmark aggregation.

Full source/seed/hash audit, exact 16x210 real executions, paired same-runner
formula bootstrap by 10-CNF shard, C/Python parity and pre-action prefix match.
No fitting, retuning or training on any R17 development/test outcome.
"""
from __future__ import annotations
import csv,hashlib,json,math,random,statistics
from collections import Counter,defaultdict
from pathlib import Path
import r17_risk_benchmark as bench

MODES=bench.MODES
RISK_MODES=bench.RISK_MODES
FOLDS=("random3_development","random3_test",
       "community3_development","community3_test")
OUT=bench.OUT/"aggregate"
INPUT=Path("r17-download")

def sha(path):return bench.sha(path)
def write_json(path,data):path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def write_csv(path,rows):
 if not rows:return
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]))
  w.writeheader();w.writerows(rows)
def ci(vals,q):
 items=sorted(vals)
 k=q*(len(items)-1);j=int(k)
 return items[j]*(1-(k-j))+items[min(j+1,len(items)-1)]*(k-j)

def confidence(rows,mode,ref,seed):
 # Formula-level stratified bootstrap, never resample three repeats independently.
 rng=random.Random(seed)
 strata=defaultdict(list)
 for row in rows:strata[int(row["n"])].append(row)
 vals=[]
 for _ in range(4000):
  samples=[rng.choice(g) for n,g in sorted(strata.items())
           for j in range(len(g))]
  a=sum(float(x[ref]) for x in samples)
  b=sum(float(x[mode]) for x in samples)
  vals.append(100*(a-b)/a)
 return [ci(vals,.025),ci(vals,.975)]

def load():
 cfg,risk=bench.load()
 history=bench.historic_registry()
 rows=[];traces={};manifests=[];provenance=[]
 for category in bench.SHARDS:
  folder=INPUT/("r17-"+category)
  inputs=[folder/name for name in ("measurements.csv","traces.jsonl","manifest.json")]
  if not all(p.is_file() for p in inputs):
   raise RuntimeError("R17 MISSING SHARD "+category)
  a=list(csv.DictReader(inputs[0].open()))
  logs=[json.loads(line) for line in inputs[1].read_text().splitlines()]
  m=json.loads(inputs[2].read_text())
  if len(a)!=210 or len(logs)!=210 or len(m["cases"])!=10:
   raise RuntimeError("R17 INCOMPLETE REAL SHARD "+category)
  if (m["shard"]!=category or m["protocol"]!=cfg["protocol"] or
      m["modes"]!=list(MODES) or m["repeats"]!=3 or m["cap_seconds"]!=12 or
      m["risk_model_sha256"]!=sha(bench.RISK) or
      m["protocol_sha256"]!=sha(bench.CONFIG) or
      m["kissat_pin"]!=bench.r16.PIN or
      m["stable_blob"]!=bench.r16.STABLE_PIN or
      m["cpu_affinity"]!=[m["cpu_core"]] or
      m["historic_sha256_hash"]!=hashlib.sha256(
         "\n".join(sorted(history)).encode()).hexdigest()):
   raise RuntimeError("R17 FROZEN RISK / CPU / PROVENANCE MISMATCH "+category)
  cases={c["formula"]:c for c in m["cases"]}
  if len(cases)!=10 or len({c["formula_sha256"] for c in m["cases"]})!=10:
   raise RuntimeError("R17 DUPLICATED SHARD FORMULA")
  for x in a:
   if x["error"] or x["r17_risk_error"]:
    raise RuntimeError("R17 SOLVER ERROR "+str(x))
   if x["formula"] not in cases or x["formula_sha256"]!=cases[x["formula"]]["formula_sha256"]:
    raise RuntimeError("R17 FORMULA SHA MISMATCH")
   if (x["runner"]!=m["runner"] or x["r17_model_sha256"]!=sha(bench.RISK)
       or x["r17_protocol_sha256"]!=sha(bench.CONFIG) or
       x["status"] not in ("SAT","UNSAT","TIMEOUT")):
    raise RuntimeError("R17 MEASUREMENT PROVENANCE OR STATUS INVALID")
   if x["status"]=="SAT" and x["sat_model_checked"]!="True":
    raise RuntimeError("R17 SAT MODEL UNCHECKED")
   if x["status"]=="TIMEOUT":
    if abs(float(x["par2_s"])-24.)>1e-6:
     raise RuntimeError("R17 WRONG PAR2 TIMEOUT")
   elif abs(float(x["par2_s"])-float(x["wall_s"]))>1e-5:
    raise RuntimeError("R17 WRONG PAR2 SOLVED TIME")
   if x["mode"] in RISK_MODES and x["r17_native_risk"]:
    if abs(float(x["r17_native_risk"])-float(x["r17_python_risk"]))>2e-5:
     raise RuntimeError("R17 RISK C/PYTHON PARITY FAILURE")
  for t in logs:
   key=(t["category"],t["formula"],str(t["repeat"]),t["mode"])
   if key in traces:raise RuntimeError("R17 TRACE COLLISION "+str(key))
   traces[key]=t
  rows.extend(a)
  manifests.append(m)
  provenance.append({"category":category,"source_commit":m["source_commit"],
    "runner":m["runner"],"cpu_core":m["cpu_core"],
    "measurements_sha256":sha(inputs[0]),"trace_sha256":sha(inputs[1]),
    "manifest_sha256":sha(inputs[2]),"binary_sha256":m["executables"],
    "frozen_risk_sha256":m["risk_model_sha256"]})
 if len(rows)!=3360 or len(traces)!=3360:
  raise RuntimeError("R17 MISSING REAL SOLVER EXECUTIONS")
 hashes={x["formula_sha256"] for x in rows}
 if len(hashes)!=160 or hashes&history:
  raise RuntimeError("R17 FORMULA WAS PREVIOUSLY USED")
 groups=defaultdict(dict)
 for row in rows:
  key=(row["category"],row["formula"],row["repeat"])
  if row["mode"] in groups[key]:
   raise RuntimeError("R17 DUPLICATE PAIRED MEASUREMENT")
  groups[key][row["mode"]]=row
 if len(groups)!=480:raise RuntimeError("R17 PAIRED GROUPS INCOMPLETE")
 for key,g in groups.items():
  if set(g)!=set(MODES):
   raise RuntimeError("R17 MISSING PAIRED ARM "+str(key))
  if len({x["runner"] for x in g.values()})!=1:
   raise RuntimeError("R17 NOT SAME RUNNER")
  if len({x["status"] for x in g.values() if x["status"] in ("SAT","UNSAT")})>1:
   raise RuntimeError("R17 SAT/UNSAT CONTRADICTION")
  if len({x["formula_sha256"] for x in g.values()})!=1:
   raise RuntimeError("R17 CASE CHANGED BETWEEN ARMS")
  pre={int(p["conflict"]):p for p in traces[(*key,"monitor")]["points"]
       if int(p["conflict"])<=1024}
  for mode in ("r11_2048_50","r16_live50",*RISK_MODES):
   other={int(p["conflict"]):p for p in traces[(*key,mode)]["points"]
          if int(p["conflict"])<=1024}
   if set(pre)!=set(other):
    raise RuntimeError("R17 PREINTERVENTION CHECKPOINT SET MISMATCH")
   for point in pre:
    if any(pre[point].get(f)!=other[point].get(f)
           for f in ("restarts","decisions","propagations","learned","glue","stable")):
     raise RuntimeError("R17 EARLY DYNAMICS CHANGED BEFORE ACTION "+str(key))
 return cfg,risk,rows,traces,groups,provenance,manifests

def main():
 cfg,risk,raw,traces,groups,provenance,manifests=load()
 OUT.mkdir(parents=True,exist_ok=True)
 byformula=defaultdict(lambda:defaultdict(list))
 for x in raw:
  byformula[(x["category"],x["formula"])][x["mode"]].append(x)
 if len(byformula)!=160:
  raise RuntimeError("R17 DIFFERENT FORMULA GROUP COUNT")
 features=[];paired=[];actions=[]
 for (cat,formula),modes in sorted(byformula.items()):
  if any(len(modes[m])!=3 for m in MODES):
   raise RuntimeError("R17 LOST REPEATS "+formula)
  base=modes["monitor"][0]
  total={m:sum(float(x["par2_s"]) for x in modes[m]) for m in MODES}
  line={"category":cat,"formula":formula,
   "formula_sha256":base["formula_sha256"],"seed":base["seed"],
   "fold":base["fold"],"family":bench.r16.previous.r14.family_from_category(cat),
   "n":bench.r16.previous.r14.size_from_category(cat),
   "degree_cv":base["degree_cv"],"degree_gini":base["degree_gini"],
   "polarity_imbalance":base["polarity_imbalance"],**total}
  for m in RISK_MODES:
   native=[x for x in modes[m] if x["r17_native_risk"]]
   line[m+"_risk_probability_median"]=statistics.median(
    [float(x["r17_native_risk"]) for x in native]) if native else ""
   line[m+"_selected_count"]=sum(x["r17_risk_selected"]=="1" for x in modes[m])
   line[m+"_switch_count"]=sum(bool(x["switch_at"]) for x in modes[m])
  line["r16_switch_count"]=sum(bool(x["switch_at"]) for x in modes["r16_live50"])
  features.append(line)
  for m in MODES:
   if m=="monitor":continue
   paired.append(dict(fold=base["fold"],category=cat,
    formula=formula,formula_sha256=base["formula_sha256"],n=line["n"],mode=m,
    monitor_par2=total["monitor"],treatment_par2=total[m],
    gain_pct=100*(total["monitor"]-total[m])/total["monitor"],
    speedup=total["monitor"]/total[m],
    gain_gt2x=total["monitor"]>2*total[m],
    regression_gt2x=total[m]>2*total["monitor"],
    switched=sum(bool(x["switch_at"]) for x in modes[m])))
  for arm in RISK_MODES:
   for x in modes[arm]:
    actions.append({
     "fold":x["fold"],"category":cat,"formula":formula,
     "repeat":x["repeat"],"arm":arm,
     "risk_C":x["r17_native_risk"],"risk_Python":x["r17_python_risk"],
     "risk_limit":x["r17_risk_limit"],
     "r16_benefit_score":x["r16_native_score"],
     "selected":x["r17_risk_selected"],"actual_switch":x["switch_at"],
     "monitor_PAR2_3_repeats":total["monitor"],
     "forced50_PAR2_3_repeats":total["r11_2048_50"],
     "risk_arm_PAR2_3_repeats":total[arm],
     "forced50_harm_gt20_percent":total["r11_2048_50"]>total["monitor"]*1.2
    })
 if len(features)!=160 or len(paired)!=960 or len(actions)!=960:
  raise RuntimeError("R17 AGGREGATED DATA DIMENSIONS INCORRECT")
 summary={}
 for i,fold in enumerate(FOLDS):
  subset=[r for r in features if r["fold"]==fold]
  if len(subset)!=(60 if fold.startswith("random3") else 20):
   raise RuntimeError("R17 WRONG FOLD SIZE")
  summary[fold]={"formulas":len(subset),"modes":{}}
  base=sum(x["monitor"] for x in subset)
  for m in MODES:
   total=sum(x[m] for x in subset)
   pm=[p for p in paired if p["fold"]==fold and p["mode"]==m]
   summary[fold]["modes"][m]={
    "par2_s":round(total,6),
    "gain_percent_vs_monitor":100*(base-total)/base,
    "formula_bootstrap_95_ci":confidence(subset,m,"monitor",171700+i*100+MODES.index(m))
      if m!="monitor" else [0.,0.],
    "gain_gt2x":sum(x["gain_gt2x"] for x in pm),
    "regression_gt2x":sum(x["regression_gt2x"] for x in pm),
    "selected_attempts":sum(x[m+"_selected_count"] for x in subset) if m in RISK_MODES else None,
    "actual_switches":sum(x[m+"_switch_count"] for x in subset) if m in RISK_MODES else None,
    "formulas_with_switch":sum(x[m+"_switch_count"]>0 for x in subset) if m in RISK_MODES else None}
  for m in RISK_MODES:
   summary[fold]["modes"][m]["gain_percent_vs_r16_live50"]=100*(
    sum(x["r16_live50"] for x in subset)-sum(x[m] for x in subset)) / (
    sum(x["r16_live50"] for x in subset))
 # Preserve formulas whose true forced50 harm exceeds the trained label.
 report={
  "protocol":cfg["protocol"],
  "kind":"R17_REAL_NATIVE_FROZEN_RISK_MODEL_PROSPECTIVE_NOT_REPLAY",
  "model_sha256":bench.sha(bench.RISK),
  "protocol_sha256":bench.sha(bench.CONFIG),
  "prior_r15_model_git_blob":cfg["r15_benefit_model_git_blob"],
  "trained_on":"39 R16 random3_development scored CNFs; NO R16 test or R17 labels",
  "risk_target":"P(>20% forced50 PAR2 regression) at conflict 1024",
  "attempts":len(raw),"formulas":len(features),
  "repeats":bench.REPEATS,"strategies":list(MODES),
  "folds":summary,"source_artifacts":provenance,
  "manifests":manifests,
  "early_prefix_mismatches":0,
  "historical_sha_duplicates":0,
  "risk_score_c_python_parity":"all under 2e-5",
  "provenance":"generated new SHA-exclusive Random3-SAT and community3-SAT",
  "limitations":[
   "No independent UNSAT certificates; SAT witnesses checked in original paired benchmark",
   "Random3 development/test are generated, NOT official competition problems",
   "No universal law or proof of general SAT speed advantage from this cohort",
   "All risk limits and model coefficients frozen before R17 executions",
   "R16 tests were prior diagnosis only and excluded from risk training",
   "Bootstrap resamples formulas within each variable-count stratum",
   "Failure to reduce regression may arise from small sample size (39 trained CNFs) or nonstationarity"
  ]
 }
 write_json(OUT/"results.json",report)
 write_csv(OUT/"formula_features.csv",features)
 write_csv(OUT/"paired.csv",paired)
 write_csv(OUT/"native_risk_decisions.csv",actions)
 (OUT/"risk_model.json").write_bytes(bench.RISK.read_bytes())
 (OUT/"train_audit.json").write_bytes(
    (bench.RISK.parent/"train_audit.json").read_bytes())
 lines=["# DRNAS R17 — real native frozen harm risk veto",
  "",
  "Risk coefficients trained on 39 R16 development CNFs only, frozen before generating",
  "any R17 problem. Main policy: R16 live50 score > .25 AND estimated harm risk <=.30.",
  "Secondary risk ceiling .45. Monitor/R16/forced50 measured in same runner/core.",
  "",
  "| Fold | Mode | PAR2 (s) | Δ vs monitor | Bootstrap formula CI | Selected | Real switches | Regressions >2x |",
  "|---|---|---:|---:|---|---:|---:|---:|"]
 for fold in FOLDS:
  for m in MODES:
   z=summary[fold]["modes"][m]
   lines.append(f"| {fold} | {m} | {z['par2_s']:.5f} | {z['gain_percent_vs_monitor']:+.3f}% | {z['formula_bootstrap_95_ci']} | {z['selected_attempts']} | {z['actual_switches']} | {z['regression_gt2x']} |")
 lines+=["",
  "Primary: R17_risk30 vs SAME-BINARY monitor on fresh random3_test.",
  "The R17 test set remains a holdout only for the *frozen* rule.",
  "Any policy changes based on these results require ANOTHER unseen formula set.",
  "No official competition score, no independent UNSAT proof certification.",
  "All 16 manifests contain native and input SHA256, seed, pinned CPU and source revision."]
 (OUT/"README.md").write_text("\n".join(lines)+"\n")
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in ("random3_test","community3_test"):
   fig,ax=plt.subplots(figsize=(8,5))
   data=[x for x in features if x["fold"]==fold and x["r17_risk30_risk_probability_median"]!=""]
   ax.scatter([float(x["r17_risk30_risk_probability_median"]) for x in data],
     [math.log2(x["monitor"]/x["r11_2048_50"]) for x in data],alpha=.75)
   ax.axhline(0,ls="--",lw=1)
   ax.axvline(.3,ls="--",lw=1)
   ax.axvline(.45,ls=":",lw=1)
   ax.set(xlabel="Native R17 predicted P(>20% harm) at 1024",
          ylabel="Actual log2(Monitor / Always forced50) PAR2",
          title="R17 frozen harm model vs real intervention — "+fold)
   fig.tight_layout()
   fig.savefig(OUT/("risk_scatter_"+fold+".png"),dpi=150)
   plt.close(fig)
 except ImportError:pass
 print("R17_REAL_PROSPECTIVE_AGGREGATE_COMPLETE",json.dumps({
  "attempts":len(raw),"formulas":len(features),
  "random3_test":{m:{"gain":round(v["gain_percent_vs_monitor"],4),
        "PAR2":v["par2_s"],"CI":v["formula_bootstrap_95_ci"],
        "actions":v["actual_switches"],
        "regression_2x":v["regression_gt2x"]}
     for m,v in summary["random3_test"]["modes"].items()}},sort_keys=True),flush=True)

if __name__=="__main__":main()
