#!/usr/bin/env python3
"""R19 blind snapshot vs trajectory: native paired timing, off-policy predictions.
Train only on new random3_development, freeze BEFORE test shard execution.
"""
import argparse,csv,hashlib,json,math,random,statistics
from pathlib import Path
from collections import defaultdict
import numpy as np
import r19_trajectory_benchmark as bench
from r16_live_benchmark import landmarks

DATA=Path("r19-download")
FROZEN=Path("r19-frozen/r19_frozen_models.json")
OUT=Path("drnas-r19-results/aggregate")
LAMBDA=30.;CUTOFF=math.log(1.05)
STATIC=["n_scaled","degree_cv","degree_gini","polarity_imbalance"]
SNAP=STATIC+["prop_per_conflict_1024","glue_1024",
"restarts_per_conflict_1024","learned_per_conflict_1024",
"stable_1024","decisions_per_conflict_1024"]
EXTRA=["prop_rate_128_256","prop_rate_256_512","prop_rate_512_1024",
"prop_slope","prop_curvature","glue_128","glue_256","glue_512",
"glue_slope","glue_curvature","restart_rate_256_512",
"restart_rate_512_1024","learned_rate_256_512",
"learned_rate_512_1024","decision_rate_512_1024"]
FULL=SNAP+EXTRA
def check(v,reason):
 if not v:raise RuntimeError("R19_BLIND_AUDIT_FAIL "+reason)
def sha(p):return bench.sha(p)
def csvread(p):
 with p.open(newline="") as f:return list(csv.DictReader(f))
def savejson(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")
def savecsv(p,rows):
 with p.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def vector(c,t):
 pts=landmarks(t)
 if not all(pts.values()):return None
 a,b,d,e=[pts[k] for k in (128,256,512,1024)]
 if not 0<int(a["conflict"])<int(b["conflict"])<int(d["conflict"])<int(e["conflict"])<2048:return None
 def rate(k,u,v):return (float(v[k])-float(u[k]))/(int(v["conflict"])-int(u["conflict"]))
 p1,p2,p3=rate("propagations",a,b),rate("propagations",b,d),rate("propagations",d,e)
 g1,g2,g3,g4=[float(x["glue"]) for x in (a,b,d,e)]
 f=c["metadata"]["features"];z=float(e["conflict"])
 v=[c["n"]/240.,float(f["degree_cv"]),float(f["degree_gini"]),float(f["polarity_imbalance"]),
 float(e["propagations"])/z,g4,float(e["restarts"])/z,
 float(e["learned"])/z,float(e["stable"]),float(e["decisions"])/z,
 p1,p2,p3,p3-p2,p3-2*p2+p1,g1,g2,g3,g4-g2,g4-2*g3+g2,
 rate("restarts",b,d),rate("restarts",d,e),
 rate("learned",b,d),rate("learned",d,e),rate("decisions",d,e)]
 check(len(v)==25,"features=25")
 return dict(zip(FULL,v)) if all(math.isfinite(x) for x in v) else None

def load(phase):
 cfg=bench.config();history=bench.history()
 shards=[s for s in bench.SHARDS if ("_development" in s)==(phase=="development")]
 check(len(shards)==8,"phase shards")
 rows=[];sources=[];distinct=set()
 for shard in shards:
  folder=DATA/(("r19-dev-" if phase=="development" else "r19-test-")+shard)
  paths=[folder/x for x in ("measurements.csv","traces.jsonl","manifest.json")]
  check(all(x.is_file() for x in paths),"missing raw data "+shard)
  rr=csvread(paths[0]);traces=[json.loads(x) for x in paths[1].read_text().splitlines()]
  m=json.loads(paths[2].read_text())
  check(len(rr)==len(traces)==120 and len(m["cases"])==10,"incomplete shard "+shard)
  check(m["protocol"]==cfg["protocol"] and m["category"]==shard and
   m["phase"]==phase and m["modes"]==list(bench.MODES) and
   m["protocol_sha256"]==sha(bench.CFG_PATH) and
   m["cpu_affinity"]==[m["cpu_core"]] and m["historic_count"]==2574 and
   m["kissat_pin"]==bench.r16.PIN,"pin/source/CPU mismatch")
  if phase=="test":check(m["frozen_model_sha256"]==sha(FROZEN),"wrong frozen model in test")
  cases={c["formula"]:c for c in m["cases"]}
  grouped=defaultdict(dict);traceidx={}
  for x,t in zip(rr,traces):
   case=cases.get(x["formula"])
   check(case is not None and x["formula_sha256"]==case["formula_sha256"] and
    x["seed"]==str(case["metadata"]["seed"]) and x["runner"]==m["runner"] and
    x["error"]=="" and x["r16_decision_error"]=="" and
    x["r19_protocol_sha256"]==sha(bench.CFG_PATH),"result/provenance")
   check(x["status"] in ("SAT","UNSAT","TIMEOUT"),"bad SAT result")
   check(x["status"]!="SAT" or x["sat_model_checked"]=="True","SAT witness")
   check(abs(float(x["par2_s"])-(24. if x["status"]=="TIMEOUT" else float(x["wall_s"])))<1e-5,"PAR2")
   key=(x["formula"],x["repeat"])
   check(x["mode"] not in grouped[key],"duplicate arm")
   grouped[key][x["mode"]]=x;traceidx[(x["formula"],x["repeat"],x["mode"])]=t
  check(len(grouped)==30,"missing paired formulas")
  for key,by in grouped.items():
   check(set(by)==set(bench.MODES),"missing paired strategy")
   check(len({z["status"] for z in by.values() if z["status"] in ("SAT","UNSAT")})<=1,"contradiction")
   baseline={int(v["conflict"]):v for v in traceidx[(*key,"monitor")]["points"] if int(v["conflict"])<=1024}
   for mode in ("r11_2048_50","r16_live50"):
    candidate={int(v["conflict"]):v for v in traceidx[(*key,mode)]["points"] if int(v["conflict"])<=1024}
    check(set(baseline)==set(candidate),"pre1024 checkpoint mismatch")
    for cp in baseline:
     check(all(baseline[cp].get(k)==candidate[cp].get(k) for k in ("restarts","decisions","propagations","learned","glue","stable")),"pre1024 solver dynamics mismatch")
  for name,case in cases.items():
   check(case["formula_sha256"] not in distinct,"repeat CNF between shards")
   distinct.add(case["formula_sha256"])
   modes={arm:[grouped[(name,str(i))][arm] for i in range(3)] for arm in bench.MODES}
   sums={arm:sum(float(x["par2_s"]) for x in values) for arm,values in modes.items()}
   ff=[vector(case,traceidx[(name,str(i),"r16_live50")]) for i in range(3)]
   ready=all(z is not None for z in ff)
   features={k:statistics.median(z[k] for z in ff) for k in FULL} if ready else None
   label=math.log(sums["monitor"]/sums["r11_2048_50"])
   rows.append(dict(formula=name,sha=case["formula_sha256"],fold=modes["monitor"][0]["fold"],
    n=case["n"],family=case["metadata"]["family"],ready=ready,landmarks=sum(z is not None for z in ff),
    features=features,logratio=label,clipped=max(-1.5,min(1.5,label)),times=sums))
  sources.append(dict(shard=shard,runner=m["runner"],source_commit=m["source_commit"],
     measures_sha256=sha(paths[0]),trace_sha256=sha(paths[1]),manifest_sha256=sha(paths[2]),
     binaries=m["executable_sha256"]))
 check(len(rows)==80 and len(distinct)==80 and not distinct&history,"historical duplicate or incomplete formula cohort")
 return rows,sources

def fit(rows,names):
 X=np.asarray([[r["features"][k] for k in names] for r in rows],float)
 y=np.asarray([r["clipped"] for r in rows],float)
 mu=X.mean(axis=0);sd=np.maximum(X.std(axis=0),1e-8)
 Z=np.clip((X-mu)/sd,-3.,3.)
 A=np.column_stack((np.ones(len(rows)),Z))
 reg=np.diag([1e-7]+[LAMBDA]*len(names))
 coef=np.linalg.solve(A.T@A/len(rows)+reg,A.T@y/len(rows))
 return dict(names=names,mu=mu.tolist(),sd=sd.tolist(),coefficients=coef.tolist(),lambda_ridge=LAMBDA)
def predict(m,r):
 if not r["ready"]:return 0.
 z=[max(-3.,min(3.,(r["features"][k]-a)/b)) for k,a,b in zip(m["names"],m["mu"],m["sd"])]
 return float(m["coefficients"][0]+np.dot(m["coefficients"][1:],z))
def freeze():
 records,refs=load("development")
 subset=[r for r in records if r["fold"]=="random3_development" and r["ready"]]
 check(len(subset)>=20,"insufficient complete dev paths")
 model=dict(protocol=bench.config()["protocol"],training_fold="random3_development",
  training_formula_count=len(subset),training_sha256=sorted(x["sha"] for x in subset),
  models=dict(snapshot=fit(subset,SNAP),trajectory=fit(subset,FULL)),
  fixed_cutoff=CUTOFF,history="R19 development only, frozen BEFORE R19 blind test",
  development_sources=refs)
 FROZEN.parent.mkdir(parents=True,exist_ok=True)
 savejson(FROZEN,model)
 savejson(FROZEN.parent/"r19_training_audit.json",{
  "training_formulas":len(subset),"community_excluded":20,"test_accessed":False,
  "model_sha256":sha(FROZEN),"snapshot_features":10,"trajectory_features":25})
 print("R19_TRAIN_FROZEN_BEFORE_TEST",sha(FROZEN),"n",len(subset),flush=True)

def evaluate():
 check(FROZEN.exists(),"frozen trained model missing")
 frozen=json.loads(FROZEN.read_text())
 check(frozen["protocol"]==bench.config()["protocol"] and
  frozen["training_fold"]=="random3_development" and len(frozen["models"])==2,
  "frozen model untrusted")
 dev,ds=load("development");test,ts=load("test")
 check(not {r["sha"] for r in dev}&{r["sha"] for r in test},"test/dev SHA overlap")
 result={};predictions=[]
 for fi,fold in enumerate(("random3_development","random3_test",
                          "community3_development","community3_test")):
  cohort=dev if "development" in fold else test
  data=[r for r in cohort if r["fold"]==fold]
  check(len(data)==(60 if fold.startswith("random3") else 20),"fold count")
  ys=[];a=[];b=[];binmap=defaultdict(list)
  armstats={}
  for k,model in frozen["models"].items():
   armstats[k]=dict(selected=0,par2=0.,large_missed=0,large_regressions=0)
  for r in data:
   preds={k:predict(m,r) for k,m in frozen["models"].items()}
   row=dict(formula=r["formula"],fold=fold,n=r["n"],formula_sha256=r["sha"],
    ready=r["ready"],landmarks=r["landmarks"],actual_logratio=r["logratio"],
    monitor_par2=r["times"]["monitor"],force50_par2=r["times"]["r11_2048_50"])
   for k,p in preds.items():
    selected=bool(r["ready"] and p>CUTOFF)
    chosen=r["times"]["r11_2048_50"] if selected else r["times"]["monitor"]
    stats=armstats[k];stats["par2"]+=chosen;stats["selected"]+=selected
    stats["large_missed"]+=not selected and r["times"]["monitor"]>2*r["times"]["r11_2048_50"]
    stats["large_regressions"]+=selected and r["times"]["r11_2048_50"]>2*r["times"]["monitor"]
    row[k+"_prediction"]=p;row[k+"_selected"]=int(selected)
   predictions.append(row)
   if r["ready"]:
    ys.append(r["clipped"]);a.append(preds["snapshot"]);b.append(preds["trajectory"])
    binmap[r["n"]].append(len(ys)-1)
  ys=np.asarray(ys);a=np.asarray(a);b=np.asarray(b)
  dif=(a-ys)**2-(b-ys)**2
  rng=random.Random(1919+fi)
  boots=[]
  if len(ys):
   for _ in range(4000):
    ids=[rng.choice(v) for n,v in sorted(binmap.items()) for j in v]
    boots.append(float(np.mean(dif[ids])))
  monitor=sum(r["times"]["monitor"] for r in data)
  for s in armstats.values():
   s["par2"]=round(s["par2"],6)
   s["replay_gain_pct"]=100*(monitor-s["par2"])/monitor
  result[fold]={
   "formulas":len(data),"feature_complete_formulas":len(ys),
   "snapshot_mse":float(np.mean((a-ys)**2)) if len(ys) else None,
   "trajectory_mse":float(np.mean((b-ys)**2)) if len(ys) else None,
   "mse_snapshot_minus_trajectory":float(np.mean(dif)) if len(ys) else None,
   "mse_difference_95_formula_bootstrap_CI":[float(np.quantile(boots,.025)),float(np.quantile(boots,.975))] if boots else None,
   "snapshot_mae":float(np.mean(abs(a-ys))) if len(ys) else None,
   "trajectory_mae":float(np.mean(abs(b-ys))) if len(ys) else None,
   "monitor_par2_s":round(monitor,6),
   "force50_par2_s":round(sum(r["times"]["r11_2048_50"] for r in data),6),
   "offpolicy_forecasts":armstats}
 OUT.mkdir(parents=True,exist_ok=True)
 report=dict(protocol=frozen["protocol"],attempts=1920,formulas=160,
  training_formula_count=frozen["training_formula_count"],frozen_model_sha256=sha(FROZEN),
  model_kind="OFF_POLICY_PREDICTIVE_VALIDATION_NOT_A_LIVE_R19_GATE",
  primary_criterion="R19 random3_test formula bootstrap CI of MSE(snapshot)-MSE(trajectory) entirely positive",
  folds=result,source_artifacts=ds+ts,
  no_overlapping_historical_formulas=True,preintervention_parity=True,
  disclaimers=["R19 genuine native SAT comparator runs; hypothetical model selection uses replay",
               "Synthetic random3/community3, not official competition formulas",
               "SAT models checked, UNSAT independent proofs unavailable",
               "No threshold/model training on R19 test formulas"])
 savejson(OUT/"results.json",report);savecsv(OUT/"predictions.csv",predictions)
 (OUT/"r19_frozen_models.json").write_bytes(FROZEN.read_bytes())
 print("R19_BLIND_HYPOTHESIS_RESULT",json.dumps(result["random3_test"],sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--freeze",action="store_true");p.add_argument("--evaluate",action="store_true")
 a=p.parse_args()
 if a.freeze:freeze()
 elif a.evaluate:evaluate()
 else:p.error("choose --freeze or --evaluate")
