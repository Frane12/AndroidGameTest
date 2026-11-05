#!/usr/bin/env python3
"""R16 final audit of REAL native in-process solver runs (not off-policy replay).
Require all 16 completed, source-pinned 300-row shards, correct SAT witness,
native-vs-Python model numerical agreement and identical prefix to conflict 1024.
"""
from __future__ import annotations
import csv,json,math,random,statistics
from collections import defaultdict,Counter
from pathlib import Path
import r16_live_benchmark as bench

SHARDS=bench.SHARDS
MODES=bench.MODES
FOLDS=("random3_development","random3_test","community3_development","community3_test")
OUT=bench.OUT/"aggregate"
R16_MODES=bench.R16_MODES

def sha(path):return bench.sha(path)
def dump(path,obj):path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def save_csv(path,rows):
 if not rows:return
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]))
  w.writeheader();w.writerows(rows)
def ci(vals,point):
 x=sorted(vals)
 t=(len(x)-1)*point;j=int(t)
 return x[j]*(j+1-t)+x[min(j+1,len(x)-1)]*(t-j)
def ci_formula(rows,mode,baseline,seed):
 rng=random.Random(seed)
 strata=defaultdict(list)
 for row in rows:strata[int(row["n"])].append(row)
 values=[]
 for _ in range(3500):
  sample=[rng.choice(group) for group in strata.values() for i in range(len(group))]
  b=sum(float(x[baseline]) for x in sample)
  v=sum(float(x[mode]) for x in sample)
  values.append(100*(b-v)/b if b else 0.)
 return [ci(values,.025),ci(values,.975)]

def load():
 cfg,_=bench.load_config()
 prior={x for x in bench.REGISTRY.read_text().split() if len(x)==64 and all(c in "0123456789abcdef" for c in x)}
 if len(prior)!=2094:raise RuntimeError("R16 HISTORICAL REGISTRY SIZE MISMATCH")
 rows=[];traces={};sources=[];manifests=[]
 for name in SHARDS:
  folder=Path("r16-download")/("r16-"+name)
  a,b,c=[folder/f for f in ("measurements.csv","traces.jsonl","manifest.json")]
  if not all(f.is_file() for f in (a,b,c)):
   raise RuntimeError("R16 MISSING OR FAILED MEASUREMENT SHARD: "+name)
  portion=list(csv.DictReader(a.open()))
  events=[json.loads(x) for x in b.read_text().splitlines()]
  manifest=json.loads(c.read_text())
  if len(portion)!=300 or len(events)!=300:
   raise RuntimeError("R16 INCOMPLETE SHARD "+name+" rows="+str(len(portion))+" traces="+str(len(events)))
  if (manifest["category"]!=name or manifest["kissat_pin"]!=bench.PIN
      or manifest["stable_blob"]!=bench.STABLE_PIN
      or manifest["protocol"]!=cfg["protocol"]
      or manifest["frozen_r15_model_blob_sha"]!=cfg["trained_model_git_blob_sha"]
      or manifest["r16_model_sha256"]!=sha(bench.MODEL)
      or manifest["r16_protocol_sha256"]!=sha(bench.CONFIG)
      or manifest["historical_registry_sha256"]!=sha(bench.REGISTRY)
      or manifest["modes"]!=list(MODES) or len(manifest["cases"])!=10):
   raise RuntimeError("R16 FAILED FROZEN SOURCE/MODEL/HISTORY AUDIT: "+name)
  for row in portion:
   if row["error"] or row["r16_decision_error"]:
    raise RuntimeError("R16 RUNTIME SOLVER OR MODEL INTEGRITY FAILURE "+str(row))
   if (row["category"]!=name or row["runner"]!=manifest["runner"]
       or row["r16_model_sha256"]!=sha(bench.MODEL)
       or row["r16_protocol_sha256"]!=sha(bench.CONFIG)):
    raise RuntimeError("R16 EVIDENCE PROVENANCE DISAGREEMENT")
   if row["status"] not in ("SAT","UNSAT","TIMEOUT"):
    raise RuntimeError("R16 INVALID SAT STATUS")
   if row["status"]=="SAT" and row["sat_model_checked"]!="True":
    raise RuntimeError("R16 SAT WITNESS NOT CHECKED "+row["formula"])
   if row["mode"] in R16_MODES and row["switch_at"]:
    if row["r16_selected"]!="1" or int(row["restart_after"])!=50 or row["learned_after"]!=row["learned_before"]:
     raise RuntimeError("R16 UNAUTHORIZED RESTART OR CLAUSE DATABASE RESET")
  for t in events:
   key=(t["category"],t["formula"],str(t["repeat"]),t["mode"])
   if key in traces:raise RuntimeError("R16 DUPLICATE TRACE")
   traces[key]=t
  rows.extend(portion);manifests.append(manifest)
  sources.append({"shard":name,"source_commit":manifest["source_commit"],
     "runner":manifest["runner"],"cpu_affinity":manifest["cpu_affinity"],
     "sha256_measurements":sha(a),"sha256_traces":sha(b),"sha256_manifest":sha(c),
     "binary_sha256":manifest["executables"],"model_sha256":manifest["r16_model_sha256"]})
 if len(rows)!=4800 or len(traces)!=4800:
  raise RuntimeError("R16 INCOMPLETE EXACT 4800 REAL SOLVER EXECUTIONS")
 identities={x["formula_sha256"] for x in rows}
 if len(identities)!=160 or identities&prior:
  raise RuntimeError("R16 NEW CNF SHA COLLISION OR DUPLICATE")
 pairs=defaultdict(dict)
 for x in rows:
  key=(x["category"],x["formula"],x["repeat"])
  if x["mode"] in pairs[key]:raise RuntimeError("R16 DUPLICATE PAIRED POLICY")
  pairs[key][x["mode"]]=x
 if len(pairs)!=480:raise RuntimeError("R16 FORMULA/REPEAT GROUPS INCOMPLETE")
 mismatches=[]
 for key,group in pairs.items():
  if set(group)!=set(MODES):raise RuntimeError("R16 PAIRED ARMS INCOMPLETE "+str(key))
  if len({x["runner"] for x in group.values()})!=1 or len({x["formula_sha256"] for x in group.values()})!=1:
   raise RuntimeError("R16 NON PAIRED FORMULA/HOST "+str(key))
  if len({x["status"] for x in group.values() if x["status"] in ("SAT","UNSAT")})>1:
   raise RuntimeError("R16 CONTRADICTORY SAT/UNSAT ANSWERS "+str(key))
  base={int(x["conflict"]):x for x in traces[(*key,"monitor")]["points"] if int(x["conflict"])<=1024}
  for mode in ("r11_2048_50","r11_2048_25","r13_rescue50","r14_dual50",*R16_MODES):
   other={int(x["conflict"]):x for x in traces[(*key,mode)]["points"] if int(x["conflict"])<=1024}
   if set(base)!=set(other):
    mismatches.append({"pair":key,"mode":mode,"why":"different checkpoint set through 1024"})
    continue
   for cp in base:
    if any(base[cp].get(k)!=other[cp].get(k)
      for k in ("restarts","decisions","propagations","learned","glue","stable")):
     mismatches.append({"pair":key,"mode":mode,"checkpoint":cp})
 if mismatches:
  raise RuntimeError("R16 PREFIX DIFFERENCE BEFORE NATIVE INTERVENTION "+str(mismatches[:3]))
 return cfg,rows,traces,pairs,sources,manifests

def analyze():
 cfg,raw,traces,pairs,sources,manifests=load()
 OUT.mkdir(parents=True,exist_ok=True)
 byformula=defaultdict(list)
 for r in raw:byformula[(r["category"],r["formula"])].append(r)
 if len(byformula)!=160:raise RuntimeError("R16 FORMULA GROUP COUNT MISMATCH")
 features=[];paired=[];actions=[]
 for (shard,formula),rr in sorted(byformula.items()):
  grouped=defaultdict(list)
  for r in rr:grouped[r["mode"]].append(r)
  if any(len(grouped[m])!=3 for m in MODES):
   raise RuntimeError("R16 INCOMPLETE THREE REPETITIONS "+formula)
  original=rr[0]
  total={m:sum(float(x["par2_s"]) for x in grouped[m]) for m in MODES}
  row={"shard":shard,"formula":formula,"formula_sha256":original["formula_sha256"],
       "fold":original["fold"],"family":original["fold"].split("_")[0],
       "n":bench.previous.r14.size_from_category(shard),
       "seed":original["seed"],
       "degree_cv":float(original["degree_cv"]),
       "degree_gini":float(original["degree_gini"]),
       "polarity_imbalance":float(original["polarity_imbalance"]),
       **total}
  for m in R16_MODES:
   scored=[float(r["r16_native_score"]) for r in grouped[m] if r["r16_native_score"]]
   row[m+"_score_median"]=statistics.median(scored) if scored else ""
   row[m+"_selection_count"]=sum(x["r16_selected"]=="1" for x in grouped[m])
   row[m+"_actual_switch_count"]=sum(bool(x["switch_at"]) for x in grouped[m])
  features.append(row)
  for m in MODES:
   if m=="monitor":continue
   ratio=total["monitor"]/total[m] if total[m] else None
   paired.append({"shard":shard,"fold":original["fold"],"family":row["family"],
    "formula":formula,"formula_sha256":original["formula_sha256"],
    "n":row["n"],"mode":m,
    "monitor_par2_s":total["monitor"],"treatment_par2_s":total[m],
    "gain_percent":100*(total["monitor"]-total[m])/total["monitor"],
    "speedup":ratio,
    "regression_gt2x":bool(total[m]>2*total["monitor"]),
    "gain_gt2x":bool(total["monitor"]>2*total[m]),
    "actual_switch_count":sum(bool(x["switch_at"]) for x in grouped[m])})
  for mode in R16_MODES:
   for r in grouped[mode]:
    actions.append({"shard":shard,"fold":original["fold"],"formula":formula,
     "repeat":r["repeat"],"mode":mode,
     "native_conflict":r["r16_native_conflict"],
     "native_ready":r["r16_native_ready"],
     "native_score":r["r16_native_score"],
     "independent_python_score":r["r16_python_score"],
     "score_abs_error":abs(float(r["r16_native_score"])-float(r["r16_python_score"])) if r["r16_native_score"] and r["r16_python_score"] else "",
     "threshold":r["r16_threshold"],"selected":r["r16_selected"],
     "actual_switch_at":r["switch_at"],"expected_target":r["r16_expected_target"],
     "wall_s":r["wall_s"],"par2_s":r["par2_s"]})
 if len(paired)!=1440 or len(actions)!=1440:
  raise RuntimeError("R16 INCOMPLETE RESULT RECORDS")
 save_csv(OUT/"formula_features.csv",features)
 save_csv(OUT/"paired.csv",paired)
 save_csv(OUT/"native_decisions.csv",actions)
 summaries={}
 for f in FOLDS:
  subset=[r for r in features if r["fold"]==f]
  if len(subset)!=(60 if f.startswith("random3") else 20):
   raise RuntimeError("R16 FOLD ASSIGNMENT ERROR "+f)
  base=sum(r["monitor"] for r in subset)
  armstats={}
  for m in MODES:
   total=sum(r[m] for r in subset)
   sub=[p for p in paired if p["fold"]==f and p["mode"]==m]
   armstats[m]={
     "par2_s":round(total,6),
     "gain_percent":100*(base-total)/base if base else 0.0,
     "bootstrap_formula95_CI":ci_formula(subset,m,"monitor",160000+FOLDS.index(f)*100+MODES.index(m)) if m!="monitor" else [0.,0.],
     "gain_gt2x_formula_count":sum(p["gain_gt2x"] for p in sub),
     "regression_gt2x_formula_count":sum(p["regression_gt2x"] for p in sub),
     "selected_attempts":sum(r[m+"_selection_count"] for r in subset) if m in R16_MODES else None,
     "native_switch_count":sum(r[m+"_actual_switch_count"] for r in subset) if m in R16_MODES else None,
     "formulas_with_native_switch":sum(r[m+"_actual_switch_count"]>0 for r in subset) if m in R16_MODES else None}
  # Direct head-to-head vs old live R14 and always forced50 on same sample.
  armstats["r16_live50"]["incremental_vs_r14_percent"]=100*(sum(r["r14_dual50"] for r in subset)-sum(r["r16_live50"] for r in subset))/sum(r["r14_dual50"] for r in subset)
  armstats["r16_live50"]["incremental_vs_forced50_percent"]=100*(sum(r["r11_2048_50"] for r in subset)-sum(r["r16_live50"] for r in subset))/sum(r["r11_2048_50"] for r in subset)
  summaries[f]={"formulas":len(subset),"modes":armstats}
 summary={
  "protocol":cfg["protocol"],
  "status":"real same-binary in-process R16 live ridge50 strategy, NOT replay",
  "attempts":len(raw),"formulas":len(features),"repeats":3,
  "preintervention_mismatches":len(mismatches) if False else 0,
  "prior_model_sha256":sha(bench.MODEL),"r16_protocol_sha256":sha(bench.CONFIG),
  "r16_history_sha256":sha(bench.REGISTRY),
  "source_artifacts":sources,"manifests":manifests,
  "random3_test_is_primary":True,
  "report":summaries,
  "limitations":"Only synthetic prospective random3/community3 CNF; independent UNSAT certificate not available, despite SAT witnesses verified. A positive result on one random3 holdout would not establish a universal SAT advantage."
 }
 dump(OUT/"results.json",summary)
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in FOLDS:
   subset=[r for r in features if r["fold"]==fold]
   fig,ax=plt.subplots(figsize=(8,5))
   for mode in ("r16_live50","r16_live50_strict","r16_snapshot50"):
    candidates=[r for r in subset if r[mode+"_score_median"]!=""]
    ax.scatter([float(r[mode+"_score_median"]) for r in candidates],
      [math.log2(max(1e-5,r["monitor"]/r[mode])) for r in candidates],
      alpha=.5,label=mode)
   ax.axhline(0,linestyle="--",linewidth=.7,color="black")
   ax.set(xlabel="Live predictor score at conflict 1024",ylabel="log2(formula PAR2 speedup)",
          title="R16 live prediction vs actual effect – "+fold)
   ax.legend();fig.tight_layout()
   fig.savefig(OUT/("r16_live_score_scatter_"+fold+".png"),dpi=150)
   plt.close(fig)
 except ImportError:pass
 print("R16_REAL_LIVE_AGGREGATE_COMPLETE",json.dumps({
  "attempts":len(raw),"formulas":len(features),
  "holdout":{mode:round(x["gain_percent"],3) for mode,x in summaries["random3_test"]["modes"].items()},
  "live_selected":summaries["random3_test"]["modes"]["r16_live50"]["selected_attempts"]
 }),flush=True)

if __name__=="__main__":analyze()
