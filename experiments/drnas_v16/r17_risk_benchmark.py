#!/usr/bin/env python3
"""R17 prospective 7-arm REAL SAT test using frozen R16 benefit + frozen R17 risk.

No R17 labels are used in the predictor. All C/Python parity checks run from
1024-conflict *pre-intervention* traces. One runner/core per matched 7-arm group.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random
from pathlib import Path
import r16_live_benchmark as r16

ROOT=Path("experiments/drnas_v16")
CONFIG=ROOT/"r17_frozen_protocol.json"
RISK=ROOT/"r17-frozen-model/risk_model.json"
R16_REPORT=ROOT/"r16-results/current/results.json"
OUT=Path("drnas-r17-results")
SHARDS=r16.SHARDS
MODES=("monitor","r11_2048_50","r16_live50",
       "r17_risk30","r17_risk45","original_kissat","stable_v1531")
RISK_MODES=("r17_risk30","r17_risk45")
REPEATS=3
CAP=12
FIELDS=r16.FIELDS+("r17_native_risk","r17_python_risk","r17_risk_limit",
    "r17_risk_selected","r17_risk_error","r17_model_sha256","r17_protocol_sha256")
R16_EXTRACT=r16.parse_r16

def sha(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load():
 cfg=json.loads(CONFIG.read_text())
 risk=json.loads(RISK.read_text())
 assert cfg["protocol"]=="R17-risk-aware-live-v1-20261102"
 assert cfg["risk_model_sha256"]==sha(RISK)
 assert cfg["risk_model_git_blob"]=="93ce3a16d28cb90f2ba674e846a2740566414b6e"
 assert cfg["modes"]==list(MODES) and cfg["risk_model_path"]==str(RISK)
 assert cfg["total_executions"]==3360 and len(SHARDS)==16
 assert cfg["kissat_commit"]==r16.PIN and cfg["stable_blob"]==r16.STABLE_PIN
 assert risk["training_fold"]=="R16 random3_development ONLY"
 assert risk["train_count"]==39
 assert risk["frozen_approved_risk_limits"]=={"r17_risk30":.3,"r17_risk45":.45}
 assert risk["feature_order"]==["r16_score","n_scaled","degree_cv",
                                 "degree_gini","polarity_imbalance"]
 assert len(risk["coefficients"])==5
 return cfg,risk

def historic_registry():
 old={x for x in r16.REGISTRY.read_text().split() if len(x)==64}
 assert len(old)==2094
 j=json.loads(R16_REPORT.read_text())
 assert j["attempts"]==4800 and j["formulas"]==160
 recent={c["formula_sha256"] for m in j["manifests"] for c in m["cases"]}
 assert len(recent)==160 and not recent&old
 registry=old|recent
 assert len(registry)==2254
 return registry

def make_cases(category,folder,history):
 cfg,_=load()
 n=r16.previous.r14.size_from_category(category)
 family=r16.previous.r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1])
 cases=[]
 for j in range(10):
  seed=cfg["generator"]["seed_base"]+n*10000+(1000 if fold=="test" else 0)+part*10+j+(20000 if family=="community3" else 0)
  rng=random.Random(seed)
  clauses=[]
  for _ in range(round(4.23*n)):
   if family=="community3" and rng.random()<.65:
    block=rng.randrange(4)
    start=block*(n//4)+1
    vs=rng.sample(range(start,start+n//4),3)
   else:
    vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  f=r16.previous.r14.r11.features(clauses,n)
  case=r16.previous.r14.r11.base.emit_cnf(folder,
   f"r17_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
   n,clauses,"UNKNOWN","generated_prospective",
   "DRNAS R17 new prospective risk model CNF (not official)",
   "r17-native-risk-v1",
   {"seed":seed,"fold":fold,"family":family,"features":f,
    "community_probability":.65 if family=="community3" else 0.})
  if case["formula_sha256"] in history:
   raise RuntimeError("R17 FORMULA HISTORICAL SHA DUPLICATE "+case["formula"])
  case["category"]=category
  cases.append(case)
 if len({c["formula_sha256"] for c in cases})!=10:
  raise RuntimeError("R17 WITHIN SHARD FORMULA SHA DUPLICATE")
 return cases

def parse_r17(output):
 pts,labels=R16_EXTRACT(output)
 events=[]
 for line in output.splitlines():
  if not line.startswith("c R17_RISK "):continue
  item={}
  for token in line.split()[2:]:
   if "=" in token:
    k,v=token.split("=",1)
    item[k]=v
  events.append(item)
 if len(events)>1:raise RuntimeError("R17 RISK EMITTED MULTIPLE TIMES")
 if events:
  labels.setdefault("DRNAS_V177_EARLY",{})["r17_event"]=events[0]
 return pts,labels

r16.previous.r14.r11.base.extract_tags=parse_r17

def risk_probability(model,score,case):
 feats=case["metadata"]["features"]
 vals=[score,case["n"]/240.,feats["degree_cv"],
       feats["degree_gini"],feats["polarity_imbalance"]]
 z=[max(-3.,min(3.,(x-m)/s)) for x,m,s
    in zip(vals,model["mu"],model["sd"])]
 logit=model["intercept"]+sum(a*b for a,b in zip(z,model["coefficients"]))
 return 1./(1.+math.exp(-max(-40.,min(40.,logit))))

def run_one(case,rep,mode,runner):
 cfg,risk=load()
 if mode not in RISK_MODES:
  row,trace=r16.run_one(case,rep,mode,runner)
 else:
  # The lower-level runner is the same compiled Kissat, wall/CPU time measurement,
  # SAT witness checker and trace collector as R16. Only R17 policy differs.
  feats=case["metadata"]["features"]
  envkeys={"DRNAS_R16_GINI":feats["degree_gini"],
           "DRNAS_R16_POLARITY":feats["polarity_imbalance"]}
  old={k:os.environ.get(k) for k in envkeys}
  for k,v in envkeys.items():os.environ[k]=format(v,".17g")
  try:row,trace=r16.previous.r14.run_one(case,rep,mode,runner)
  finally:
   for k,v in old.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
  row["fold"]=r16.previous.r14.fold_from_category(case["category"])
  row["r16_protocol_sha256"]=r16.sha(r16.CONFIG)
  row["r16_model_sha256"]=r16.sha(r16.MODEL)
  early=trace.get("early",{})
  native=early.get("r16_event",{})
  row.update(r16_native_conflict=native.get("conflict",""),
    r16_native_ready=native.get("complete",""),
    r16_native_score=native.get("score",""),
    r16_python_score="",r16_selected=native.get("selected",""),
    r16_expected_target=native.get("target",""),
    r16_threshold=native.get("threshold",""),
    r16_model=native.get("model",""),
    r16_decision_error="")
  risk_native=early.get("r17_event",{})
  m=r16.load_config()[1]["models"]["trajectory"]["r11_2048_50"]
  x=r16.py_feature_vector(case,trace,m)
  predicted=r16.score_from_features(m,x)
  if native and predicted is not None:
   row["r16_python_score"]=predicted
   if abs(float(native["score"])-predicted)>2e-5:
    row["r16_decision_error"]="R17 R16 BENEFIT C/PYTHON PARITY FAILED"
  if native:
   if native.get("model")!="trajectory" or abs(float(native["threshold"])-.25)>1e-10:
    row["r16_decision_error"]="R17 BASE R16 FROZEN TRAJECTORY CHANGED"
   elif bool(int(native["complete"]))!=(x is not None):
    row["r16_decision_error"]="R17 INVALID NATIVE PREFIX READINESS"
   elif int(native["conflict"])<1024 or int(native["conflict"])>=2048:
    row["r16_decision_error"]="R17 DECISION OUTSIDE [1024,2048)"
  if bool(native)!=bool(risk_native):
   row["r16_decision_error"]="R17 NATIVE RISK EVENT MISSING"
  if risk_native:
   risk_python=risk_probability(risk,predicted,case)
   maxrisk=cfg["risk_arms"][mode]["max_estimated_harm_probability"]
   selected=(case["n"]>=220 and x is not None and
             predicted>.25 and risk_python<=maxrisk)
   if (abs(float(risk_native["risk"])-risk_python)>2e-5 or
       abs(float(risk_native["benefit"])-predicted)>2e-5 or
       abs(float(risk_native["risk_limit"])-maxrisk)>1e-10 or
       bool(int(risk_native["selected"]))!=selected or
       bool(int(native["selected"]))!=selected or
       risk_native["target"]!=("2048" if selected else "0")):
    row["r16_decision_error"]="R17 C/PYTHON RISK OR SELECTION DISAGREEMENT"
   elif row["switch_at"] and (not selected or int(row["switch_at"])<2048
       or int(row["restart_after"])!=50 or row["learned_before"]!=row["learned_after"]):
    row["r16_decision_error"]="R17 UNAUTHORIZED SWITCH/CLAUSE RESET"
  elif row["switch_at"]:
   row["r16_decision_error"]="R17 SWITCH WITHOUT RISK EVENT"
  if row["r16_decision_error"]:
   row["error"]=row["r16_decision_error"]
  trace["r17_risk_event"]=risk_native
  trace["r17_python_risk"]=risk_probability(risk,predicted,case) if predicted is not None else ""
 row.update(
  r17_native_risk=risk_native.get("risk","") if mode in RISK_MODES else "",
  r17_python_risk=trace.get("r17_python_risk","") if mode in RISK_MODES else "",
  r17_risk_limit=risk_native.get("risk_limit","") if mode in RISK_MODES else "",
  r17_risk_selected=risk_native.get("selected","") if mode in RISK_MODES else "",
  r17_risk_error=row.get("r16_decision_error",""),
  r17_model_sha256=sha(RISK),r17_protocol_sha256=sha(CONFIG))
 return row,trace

def write_rows(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  w.writeheader();w.writerows(rows)

def run_shard(cat):
 cfg,risk=load()
 pin=r16.previous.r14.r11.set_cpu_affinity()
 folder=OUT/cat
 folder.mkdir(parents=True,exist_ok=True)
 history=historic_registry()
 cases=make_cases(cat,folder,history)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / core "+str(pin)+" / "+platform.processor()
 report={
  "protocol":cfg["protocol"],"source_commit":os.environ.get("GITHUB_SHA","local"),
  "shard":cat,"fold":r16.previous.r14.fold_from_category(cat),
  "family":r16.previous.r14.family_from_category(cat),
  "modes":MODES,"repeats":REPEATS,"cap_seconds":CAP,
  "risk_model_sha256":sha(RISK),"protocol_sha256":sha(CONFIG),
  "kissat_pin":r16.PIN,"stable_blob":r16.STABLE_PIN,
  "historic_sha256_hash":hashlib.sha256("\n".join(sorted(history)).encode()).hexdigest(),
  "runner":runner,"cpu_core":pin,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "executables":{
    "native_patched":sha(r16.previous.r14.r11.base.PATCHED),
    "original_kissat":sha(r16.previous.r14.r11.base.ORIGINAL),
    "stable_v1531":sha(r16.previous.r14.r11.base.STABLE)},
  "cases":[{k:str(v) if isinstance(v,Path) else v for k,v in c.items()
           if k!="clauses"} for c in cases],
  "provenance":"Prospective generated Random3/community3, NOT official and no independent UNSAT certificate."
 }
 (folder/"manifest.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
 rows=[];traces=[]
 for case in cases:
  for repeat in range(REPEATS):
   modes=list(MODES)
   random.Random(917170+int(case["formula_sha256"][:12],16)+repeat).shuffle(modes)
   for mode in modes:
    row,trace=run_one(case,repeat,mode,runner)
    rows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:
     f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R17_MEASURE",cat,case["formula"],repeat,mode,row["status"],
          "par2",row["par2_s"],"risk",row["r17_native_risk"],
          "selected",row["r17_risk_selected"],"switch",row["switch_at"],
          flush=True)
    if row["error"]:
     (folder/"error.json").write_text(json.dumps(row,indent=2)+"\n")
     raise RuntimeError("R17 RUNTIME INVALID "+row["error"])
  statuses={x["status"] for x in rows if x["formula"]==case["formula"] and
            x["status"] in ("SAT","UNSAT")}
  if len(statuses)>1:
   raise RuntimeError("R17 SAT STATUS CONTRADICTION "+case["formula"])
 if len(rows)!=210 or len(traces)!=210:
  raise RuntimeError("R17 WRONG SHARD ROW COUNT")
 write_rows(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(
  json.dumps(x,sort_keys=True)+"\n" for x in traces))
 print("R17_SHARD_COMPLETE",cat,210,flush=True)

def smoke():
 from tempfile import TemporaryDirectory
 cfg,_=load()
 hist=historic_registry()
 with TemporaryDirectory() as tmp:
  cases=make_cases("n220_development0",Path(tmp),hist)
  for case in cases[:6]:
   for mode in ("monitor","r16_live50",*RISK_MODES):
    row,trace=run_one(case,0,mode,"R17 smoke")
    if row["error"] or row["status"] not in ("SAT","UNSAT"):
     raise RuntimeError("R17 LIVE SMOKE FAIL "+mode+": "+str(row))
    if mode in RISK_MODES and row["r17_native_risk"]:
     print("R17_SMOKE_C_PYTHON_RISK",case["formula"],mode,
        row["r17_native_risk"],row["r17_python_risk"],flush=True)
     return
 raise RuntimeError("R17 NATIVE SMOKE DID NOT REACH RISK LANDMARK")

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--category",choices=SHARDS)
 p.add_argument("--smoke",action="store_true")
 args=p.parse_args()
 if args.smoke:smoke()
 elif args.category:run_shard(args.category)
 else:p.error("missing --category/--smoke")
