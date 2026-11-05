#!/usr/bin/env python3
"""R15 retrospective/off-policy trajectory replay on freshly measured SAT runs.

Two frozen feature sets (single 512-conflict snapshot vs 128..1024 trajectories);
ridge lambda, train/test assignments and abstain threshold were preregistered.
Train solely on prospective random3_development formulas, evaluate untouched
random3_test and community3_test. NO learned rule is deployed into Kissat.
"""
from __future__ import annotations
import csv,json,hashlib,math,random,statistics,sys
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
import r15_trajectory_benchmark as bench

OUT=Path("drnas-r15-results/aggregate")
DOWNLOAD=Path("r15-download")
ARMS=bench.MODES
SHARDS=bench.SHARDS
CONFIG=bench.CONFIG
REGISTRY=bench.REGISTRY
FOLDS=("random3_development","random3_test","community3_development","community3_test")
TREATMENTS=("r11_2048_25","r11_2048_50")
POINTS=(128,256,512,1024)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def num(v,default=None):
 try:return float(v)
 except (ValueError,TypeError):return default
def cp(trace,mark):
 # Marks are sampled at or just beyond each threshold, in fixed order.
 for point in trace:
  if int(point["conflict"])>=mark:
   return point
 return None
def diff_rate(x,y,field):
 if x is None or y is None:return 0.0
 delta=float(y[field])-float(x[field])
 dc=int(y["conflict"])-int(x["conflict"])
 return delta/max(1,dc)
def features_for(mon_trace,record):
 p=mon_trace["points"]
 v={k:cp(p,k) for k in POINTS}
 ready=all(v[k] is not None for k in POINTS)
 ep=mon_trace["early"]
 cv=float(record["degree_cv"])
 if ready:
  x1,x2,x3,x4=[v[k] for k in POINTS]
  p12=diff_rate(x1,x2,"propagations")
  p23=diff_rate(x2,x3,"propagations")
  p34=diff_rate(x3,x4,"propagations")
  g1,g2,g3,g4=[float(x["glue"]) for x in (x1,x2,x3,x4)]
  restart_512=float(x3["restarts"])
  learned_512=float(x3["learned"])
  stable_512=float(x3["stable"])
  rest23=diff_rate(x2,x3,"restarts")
  rest34=diff_rate(x3,x4,"restarts")
  learned23=diff_rate(x2,x3,"learned")
  learned34=diff_rate(x3,x4,"learned")
  decisions34=diff_rate(x3,x4,"decisions")
 else:
  p12=p23=p34=g1=g2=g3=g4=0.0
  restart_512=learned_512=stable_512=0.0
  rest23=rest34=learned23=learned34=decisions34=0.0
 # These are all available by the 1024th conflict; none uses later traces.
 return {"n_scaled":bench.r14.size_from_category(record["category"])/240.,
  "degree_cv":cv,"degree_gini":float(record["degree_gini"]),
  "polarity_imbalance":float(record["polarity_imbalance"]),
  "p512":num(ep.get("p"),0.0),"g512":num(ep.get("g"),0.0),
  "restarts512":math.log1p(restart_512),
  "learned512":learned_512/512.,
  "stable512":stable_512,"reached1024":int(ready),
  "p128_256":p12,"p256_512":p23,"p512_1024":p34,
  "p_slope_256_1024":p34-p23,"p_curvature":p34-2*p23+p12,
  "g128":g1,"g256":g2,"g1024":g4,
  "g_slope_256_1024":g4-g2,"g_curvature":g4-2*g3+g2,
  "restart_rate_256_512":rest23,"restart_rate_512_1024":rest34,
  "learned_rate_256_512":learned23,"learned_rate_512_1024":learned34,
  "decision_rate_512_1024":decisions34}

def write_csv(path,rows):
 if not rows:return
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction="ignore")
  writer.writeheader();writer.writerows(rows)

def load_dataset():
 cfg=bench.load_config()
 hashes={s for s in REGISTRY.read_text().split() if len(s)==64 and all(x in "0123456789abcdef" for x in s)}
 if len(hashes)!=1934:raise RuntimeError("R15 historical registry incomplete")
 rows=[];traces={};sources=[];manifest_by_shard={}
 for shard in SHARDS:
  folder=DOWNLOAD/("r15-"+shard)
  paths=[folder/p for p in ("measurements.csv","traces.jsonl","manifest.json")]
  if not all(p.is_file() for p in paths):
   raise RuntimeError("R15 SHARD ARTIFACT MISSING "+shard)
  part=list(csv.DictReader(paths[0].open()))
  trace=[json.loads(line) for line in paths[1].read_text().splitlines()]
  man=json.loads(paths[2].read_text())
  if len(part)!=240 or len(trace)!=240:
   raise RuntimeError("R15 PARTIAL SHARD "+shard+" rows="+str(len(part))+" traces="+str(len(trace)))
  if (man["category"]!=shard or man["kissat_pin"]!=bench.PIN or
      man["stable_blob"]!=bench.STABLE_PIN or
      man["r15_protocol_sha256"]!=sha(CONFIG) or
      man["historical_registry_sha256"]!=sha(REGISTRY) or
      man["modes"]!=list(ARMS) or len(man["cases"])!=10):
   raise RuntimeError("R15 FROZEN SOURCE OR PROTOCOL MISMATCH "+shard)
  for row in part:
   if (row["error"] or row["category"]!=shard or
       row["runner"]!=man["runner"] or row["r15_config_sha256"]!=sha(CONFIG)):
    raise RuntimeError("R15 INCONSISTENT RAW MEASUREMENT "+str(row))
   if row["status"] not in ("SAT","UNSAT","TIMEOUT"):
    raise RuntimeError("R15 UNKNOWN SOLVER STATUS")
   if row["status"]=="SAT" and row["sat_model_checked"]!="True":
    raise RuntimeError("R15 SAT ANSWER WITHOUT CHECKED ASSIGNMENT "+row["formula"])
  for t in trace:
   key=(t["category"],t["formula"],str(t["repeat"]),t["mode"])
   if key in traces:raise RuntimeError("R15 DUPLICATED TRACE IDENTIFIER "+str(key))
   traces[key]=t
  sources.append({"shard":shard,"measurements_sha256":sha(paths[0]),
    "traces_sha256":sha(paths[1]),"manifest_sha256":sha(paths[2]),
    "source_commit":man["source_commit"],"runner":man["runner"],
    "cpu_affinity":man["cpu_affinity"],"binary_sha256":man["executables"],
    "historical_registry_sha256":man["historical_registry_sha256"]})
  manifest_by_shard[shard]=man
  rows.extend(part)
 if len(rows)!=3840 or len(traces)!=3840:
  raise RuntimeError("R15 INCOMPLETE GLOBAL MATRIX (3840)")
 hashes_found={r["formula_sha256"] for r in rows}
 if len(hashes_found)!=160 or hashes_found & hashes:
  raise RuntimeError("R15 DUPLICATE/REUSED HISTORICAL FORMULA SHA256")
 pairs=defaultdict(dict)
 for row in rows:
  k=(row["category"],row["formula"],str(row["repeat"]))
  if row["mode"] in pairs[k]:raise RuntimeError("R15 DUPLICATED MATCHED MODE "+str(k))
  pairs[k][row["mode"]]=row
 if len(pairs)!=480:raise RuntimeError("R15 INCOMPLETE FORMULA/REPEAT GROUP")
 mismatch=[]
 for key,group in pairs.items():
  if set(group)!=set(ARMS):raise RuntimeError("R15 UNPAIRED ARMS "+str(key))
  if len({r["runner"] for r in group.values()})!=1:
   raise RuntimeError("R15 PAIR RUNNER NOT IDENTICAL")
  if len({r["formula_sha256"] for r in group.values()})!=1:
   raise RuntimeError("R15 PAIR SHA NOT IDENTICAL")
  if len({r["status"] for r in group.values() if r["status"] in ("SAT","UNSAT")})>1:
   raise RuntimeError("R15 SAT/UNSAT CONTRADICTION "+str(key))
  reference={int(t["conflict"]):t for t in traces[(*key,"monitor")]["points"] if int(t["conflict"])<=1024}
  for mode in ("r11_2048_25","r11_2048_50","r11_4096_25","r13_rescue50","r14_dual50"):
   treatment={int(t["conflict"]):t for t in traces[(*key,mode)]["points"] if int(t["conflict"])<=1024}
   if set(reference)!=set(treatment):
    mismatch.append({"formula":key,"mode":mode,"error":"different pre-intervention checkpoint sets"})
    continue
   for cpmark in reference:
    if any(reference[cpmark].get(f)!=treatment[cpmark].get(f)
           for f in ("restarts","decisions","propagations","learned","glue","stable")):
     mismatch.append({"formula":key,"mode":mode,"checkpoint":cpmark})
 if mismatch:
  raise RuntimeError("R15 COUNTERFACTUAL PREFIX NOT IDENTICAL "+str(mismatch[:3]))
 return cfg,rows,traces,pairs,sources,manifest_by_shard

def compile_formula_table(rows,traces):
 performula=defaultdict(list)
 for row in rows:performula[(row["category"],row["formula"])].append(row)
 formulas=[];paired=[]
 for (cat,name),rr in sorted(performula.items()):
  modes=defaultdict(list)
  for row in rr:modes[row["mode"]].append(row)
  if any(len(modes[m])!=3 for m in ARMS):
   raise RuntimeError("R15 FORMULA REPEAT MISSING "+name)
  for m in ARMS:modes[m].sort(key=lambda row:int(row["repeat"]))
  first=rr[0]
  base_trace=traces[(cat,name,"0","monitor")]
  features=features_for(base_trace,first)
  costs={m:sum(float(z["par2_s"]) for z in modes[m]) for m in ARMS}
  record={
    "shard":cat,"formula":name,"formula_sha256":first["formula_sha256"],
    "family":bench.r14.family_from_category(cat),
    "fold":bench.r14.fold_from_category(cat),
    "n":bench.r14.size_from_category(cat),
    "seed":first["seed"],
    "status":next((r["status"] for r in rr if r["status"] in ("SAT","UNSAT")),"TIMEOUT"),
    "runner":first["runner"],"trace_points_monitor_rep0":len(base_trace["points"]),
    **features,**costs}
  formulas.append(record)
  for mode in ARMS:
   if mode=="monitor":continue
   time=costs[mode];base=costs["monitor"]
   paired.append({"shard":cat,"family":record["family"],"fold":record["fold"],
    "formula":name,"formula_sha256":first["formula_sha256"],"mode":mode,
    "monitor_par2":base,"treatment_par2":time,
    "gain_percent":100*(base-time)/base if base else None,
    "speedup":base/time if time else None,
    "pair_repeats":3,
    "switch_count":sum(bool(x["switch_at"]) for x in modes[mode])})
 return formulas,paired

def normalize_fit(records,names):
 x=np.array([[float(row[f]) for f in names] for row in records],dtype=float)
 mu=x.mean(axis=0);sigma=x.std(axis=0)
 sigma=np.where(sigma<1e-7,1.0,sigma)
 z=np.clip((x-mu)/sigma,-3,3)
 return z,mu,sigma
def normalize_predict(row,names,mu,sigma):
 a=np.array([float(row[f]) for f in names],dtype=float)
 return np.concatenate(([1.0],np.clip((a-mu)/sigma,-3,3)))
def fit_model(records,names,mode,lam):
 if not records:raise RuntimeError("NO R15 TRAINING FORMULAS REACH 1024 CONFLICTS")
 z,mu,sd=normalize_fit(records,names)
 x=np.hstack((np.ones((len(records),1)),z))
 labels=np.array([max(-2.,min(2.,math.log(r["monitor"]/r[mode])))
                  for r in records],dtype=float)
 penalty=np.diag([0.]+[lam]*len(names))
 coefficients=np.linalg.solve(x.T@x+penalty,x.T@labels)
 return {"feature_names":names,"mu":mu.tolist(),"sd":sd.tolist(),
   "coefficients":coefficients.tolist(),"n_train":len(records),
   "train_target_mean":float(labels.mean()),"train_target_std":float(labels.std()),
   "target_arm":mode,"ridge_lambda":lam}
def forecast(model,row):
 x=normalize_predict(row,model["feature_names"],
                    np.array(model["mu"]),np.array(model["sd"]))
 return float(np.dot(x,np.array(model["coefficients"])))
def choose_arm(row,models,threshold):
 if not row["reached1024"]:
  return "monitor",{"r11_2048_25":0.,"r11_2048_50":0.}
 predictions={mode:forecast(model,row) for mode,model in models.items()}
 best=max(predictions,key=predictions.get)
 if predictions[best]<=threshold:return "monitor",predictions
 return best,predictions

def quantile(vals,q):
 s=sorted(vals)
 if not s:return None
 x=(len(s)-1)*q;i=int(x)
 return s[i]*(1-x+i)+s[min(i+1,len(s)-1)]*(x-i)
def bootstrap_gain(records,mode,baseline="monitor",seed=151515):
 if len(records)<1:return [None,None]
 rng=random.Random(seed);strata=defaultdict(list)
 for f in records:strata[f["n"]].append(f)
 results=[]
 for _ in range(2500):
  sample=[rng.choice(a) for a in strata.values() for j in range(len(a))]
  base=sum(float(f[baseline]) for f in sample)
  act=sum(float(f[mode]) for f in sample)
  results.append(100*(base-act)/base if base else 0.)
 return [quantile(results,.025),quantile(results,.975)]

def analyze():
 config,raw,traces,pairs,sources,manifests=load_dataset()
 formulas,paired=compile_formula_table(raw,traces)
 if len(formulas)!=160 or len(paired)!=1120:
  raise RuntimeError("R15 INCOMPLETE PAIRED FORMULA TABLE")
 features=config["feature_sets"]
 train=[r for r in formulas if r["fold"]=="random3_development" and r["reached1024"]]
 if len(train)<5:raise RuntimeError("R15 TOO FEW ELIGIBLE TRAIN FORMULAS: "+str(len(train)))
 models={}
 for kind in ("snapshot","trajectory"):
  models[kind]={m:fit_model(train,features[kind],m,config["model"]["ridge_lambda"])
                for m in TREATMENTS}
 OUT.mkdir(parents=True,exist_ok=True)
 decisions=[];augmented={}
 for row in formulas:
  choice={}
  for kind in ("snapshot","trajectory"):
   selected,pred=choose_arm(row,models[kind],config["model"]["abstain_below_predicted_log_gain"])
   choice[kind]=selected
   decisions.append({
    "family":row["family"],"fold":row["fold"],"shard":row["shard"],
    "formula":row["formula"],"formula_sha256":row["formula_sha256"],
    "n":row["n"],"reached1024":int(row["reached1024"]),
    "model":kind,"selected_arm":selected,
    "predicted_log_gain_25":pred["r11_2048_25"],
    "predicted_log_gain_50":pred["r11_2048_50"],
    "observed_monitor_PAR2":row["monitor"],
    "counterfactual_selected_PAR2":row[selected],
    "observed_25_PAR2":row["r11_2048_25"],
    "observed_50_PAR2":row["r11_2048_50"],
    "observed_r13_PAR2":row["r13_rescue50"],
    "observed_r14_PAR2":row["r14_dual50"]})
  augmented[(row["shard"],row["formula"])]={
   **row,"snapshot_replay":row[choice["snapshot"]],
   "trajectory_replay":row[choice["trajectory"]],
   "snapshot_choice":choice["snapshot"],"trajectory_choice":choice["trajectory"]}
 allrows=list(augmented.values())
 write_csv(OUT/"formula_features.csv",formulas)
 write_csv(OUT/"paired.csv",paired)
 write_csv(OUT/"policy_decisions.csv",decisions)
 with (OUT/"frozen_trained_models.json").open("w") as f:
  json.dump({"training_fold":"random3_development","n_eligible_training":len(train),
             "feature_sets":features,"lambda":config["model"]["ridge_lambda"],
             "threshold":config["model"]["abstain_below_predicted_log_gain"],
             "models":models},f,indent=2,sort_keys=True)
 report={}
 for fold in FOLDS:
  subset=[r for r in allrows if r["fold"]==fold]
  strategies=list(ARMS)+["snapshot_replay","trajectory_replay"]
  times={mode:sum(r[mode] for r in subset) for mode in strategies}
  base=times["monitor"]
  modes={}
  for mode in strategies:
   modes[mode]={
    "par2_total_s":round(times[mode],6),
    "gain_percent_vs_monitor":100*(base-times[mode])/base if base else None,
    "formula_bootstrap_95_CI":bootstrap_gain(subset,mode,seed=151500+strategies.index(mode)+FOLDS.index(fold)*10) if mode!="monitor" else [0.,0.],
    "formulas_speedup_gt_2x":sum(r["monitor"]>2*r[mode] for r in subset),
    "formulas_regression_gt_2x":sum(r[mode]>2*r["monitor"] for r in subset),
    "formulas_selected":sum(r.get(mode.replace("_replay","_choice"),"monitor")!="monitor" for r in subset) if mode.endswith("_replay") else None}
  report[fold]={"formula_count":len(subset),
   "reached_1024":sum(r["reached1024"] for r in subset),
   "modes":modes}
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in FOLDS:
   subset=[r for r in allrows if r["fold"]==fold and r["reached1024"]]
   fig,ax=plt.subplots(figsize=(8,5))
   if subset:
    ax.scatter([r["p_slope_256_1024"] for r in subset],
       [math.log(max(1e-8,r["monitor"]/r["r11_2048_50"])) for r in subset],alpha=.6,label="Forced restart50")
    ax.scatter([r["p_slope_256_1024"] for r in subset],
       [math.log(max(1e-8,r["monitor"]/r["r11_2048_25"])) for r in subset],alpha=.6,label="Forced restart25")
   ax.axhline(0,color="black",ls="--",lw=.7)
   ax.set(xlabel="Pre-2048 propagation rate trend (256..1024)",
          ylabel="ln(monitor PAR2 / forced PAR2)",
          title="R15 trajectory vs intervention response: "+fold)
   ax.legend(loc="best") if subset else None
   fig.tight_layout();fig.savefig(OUT/("r15_trajectory_scatter_"+fold+".png"),dpi=150);plt.close(fig)
   fig,ax=plt.subplots(figsize=(8,5))
   ds=[d for d in decisions if d["fold"]==fold and d["model"]=="trajectory"]
   if ds:
    ax.scatter([float(d["predicted_log_gain_50"]) for d in ds],
      [math.log(max(1e-8,float(d["observed_monitor_PAR2"])/float(d["observed_50_PAR2"]))) for d in ds],alpha=.65)
   ax.axhline(0,color="black",ls="--",lw=.7)
   ax.set(xlabel="Frozen model predicted log benefit (forced50)",
          ylabel="Actual paired log benefit",title="R15 forecast calibration: "+fold)
   fig.tight_layout();fig.savefig(OUT/("r15_prediction_scatter_"+fold+".png"),dpi=150);plt.close(fig)
 except ImportError:pass
 result={
  "protocol":"R15 observational early-trajectory predictive benchmark: zero new adaptive solver policy",
  "source_config":config,
  "status":"off-policy replay only; not an actually deployed live adaptive algorithm",
  "attempts":len(raw),"formula_count":len(formulas),"repeats":3,
  "source_artifacts":sources,"frozen_protocol_sha256":sha(CONFIG),
  "historical_registry_sha256":sha(REGISTRY),
  "monitor_prefix_mismatches":0,
  "training_eligible_count":len(train),"model_training_development_only":True,
  "trained_models_sha256":sha(OUT/"frozen_trained_models.json"),
  "report":report,
  "limitations":"The replay chooses an arm using the MONITOR's 1024-conflict prefix and inserts independently measured arm PAR2; this is NOT a timed live policy. Real adaptive gating, its overhead and interactions require a separate frozen follow-up test. Synthetic random3/community3 are not official. UNSAT uncertified independently."}
 (OUT/"results.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
 print("R15_ANALYSIS_COMPLETE",json.dumps({"attempts":len(raw),"formulas":len(formulas),
   "eligible_training":len(train),
   "primary_test":{m:round(v["gain_percent_vs_monitor"],3) for m,v in report["random3_test"]["modes"].items()}}),flush=True)

if __name__=="__main__":analyze()
