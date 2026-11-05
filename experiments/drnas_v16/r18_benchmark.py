#!/usr/bin/env python3
"""DRNAS R18 genuinely native 9-arm frozen-direct-effect benchmark.

No replay. Both R18 policies are evaluated inside pinned Kissat while solving.
Training only from SHA-pinned R17 development, no R17 holdout labels.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random
from pathlib import Path
import r17_risk_benchmark as previous

ROOT=Path("experiments/drnas_v16")
CONFIG=ROOT/"r18_frozen_protocol.json"
MODEL=ROOT/"r18-frozen-model/netbenefit_model.json"
R17_RESULTS=ROOT/"r17-results/current/results.json"
OUT=Path("drnas-r18-results")
SHARDS=previous.SHARDS
REPEATS=3
CAP=12
MODES=("monitor","r11_2048_50","r16_live50","r17_risk30","r17_risk45",
       "r18_lcb","r18_mean","original_kissat","stable_v1531")
R18_MODES=("r18_lcb","r18_mean")
FIELDS=previous.FIELDS+(
 "r18_native_mean","r18_python_mean","r18_native_sigma","r18_python_sigma",
 "r18_native_lower","r18_python_lower","r18_selected","r18_base_r16_score",
 "r18_model_sha256","r18_protocol_sha256","r18_error")
PREVIOUS_EXTRACT=previous.parse_r17

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load():
 cfg=json.loads(CONFIG.read_text())
 m=json.loads(MODEL.read_text())
 if (cfg["protocol"]!="DRNAS-R18-direct-gain-uncertainty-frozen-v1-20261102"
     or cfg["model_sha256"]!=sha(MODEL) or
     cfg["model_git_blob"]!="d50f608f03c0e2b9c5c86c9a7007480b847169a4"
     or cfg["model_train_only"]!="R17 random3_development 40 n>=220 CNFs, SHA-pinned, no R17 test, no community, no R18 labels"
     or cfg["modes"]!=list(MODES) or cfg["attempts"]!=4320
     or cfg["history_count"]!=2414 or cfg["formulas"]!=160
     or cfg["original_kissat_pin"]!=previous.r16.PIN
     or cfg["stable_v1531_blob"]!=previous.r16.STABLE_PIN
     or m["trained_fold"]!="R17 random3_development ONLY" or
     len(m["bootstrap_coefficients"])!=31 or m["trained_count"]!=40):
  raise RuntimeError("R18 FROZEN MODEL/PROTOCOL MISMATCH")
 return cfg,m

def history():
 prior=previous.historic_registry()
 assert len(prior)==2254
 report=json.loads(R17_RESULTS.read_text())
 assert report["attempts"]==3360 and report["formulas"]==160
 r17={c["formula_sha256"] for m in report["manifests"] for c in m["cases"]}
 assert len(r17)==160 and not prior&r17
 together=prior|r17
 assert len(together)==2414
 return together

def make_cases(category,folder,used):
 cfg,_=load()
 n=previous.r16.previous.r14.size_from_category(category)
 family=previous.r16.previous.r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1]);cases=[]
 for j in range(10):
  seed=(cfg["generator"]["seed_constant"]+n*10000+
        (1000 if fold=="test" else 0)+part*10+j+
        (20000 if family=="community3" else 0))
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
  features=previous.r16.previous.r14.r11.features(clauses,n)
  case=previous.r16.previous.r14.r11.base.emit_cnf(folder,
    f"r18_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
    n,clauses,"UNKNOWN","generated_prospective",
    "DRNAS R18 direct gain + heuristic uncertainty risk gate (synthetic nonofficial)",
    "r18-native-direct-gain-uncertainty-frozen-v1",
    {"seed":seed,"fold":fold,"family":family,"features":features,
     "community_probability":.65 if family=="community3" else 0.})
  if case["formula_sha256"] in used:
   raise RuntimeError("R18 FORMULA SHA COLLISION WITH PREVIOUS CORPUS")
  case["category"]=category
  cases.append(case)
 if len({x["formula_sha256"] for x in cases})!=10:
  raise RuntimeError("R18 DUPLICATE FORMULA WITHIN SHARD")
 return cases

def parse_r18(output):
 points,labels=PREVIOUS_EXTRACT(output)
 recs=[]
 for line in output.splitlines():
  if not line.startswith("c R18_DECISION "):continue
  obj={}
  for token in line.split()[2:]:
   if "=" in token:
    k,v=token.split("=",1)
    obj[k]=v
  recs.append(obj)
 if len(recs)>1:raise RuntimeError("R18 DUPLICATED NATIVE DECISION EVENT")
 if recs:labels.setdefault("DRNAS_V177_EARLY",{})["r18_event"]=recs[0]
 return points,labels

previous.r16.previous.r14.r11.base.extract_tags=parse_r18

def score_model(m,score,case):
 features=case["metadata"]["features"]
 inp=[score,case["n"]/240.,features["degree_cv"],
       features["degree_gini"],features["polarity_imbalance"]]
 z=[max(-3.,min(3.,(v-a)/b)) for v,a,b in zip(inp,m["feature_mean"],m["feature_sd"])]
 vals=[beta[0]+sum(w*v for w,v in zip(beta[1:],z))
       for beta in m["bootstrap_coefficients"]]
 mean=sum(vals)/len(vals)
 variance=max(0.,sum(x*x for x in vals)/len(vals)-mean*mean)
 sigma=math.sqrt(variance+m["loo_residual_rmse"]**2)
 return mean,sigma

def run_one(case,repeat,mode,runner):
 cfg,m=load()
 if mode not in R18_MODES:
  row,trace=previous.run_one(case,repeat,mode,runner)
  event={}
 else:
  static=case["metadata"]["features"]
  envs={"DRNAS_R16_GINI":static["degree_gini"],
        "DRNAS_R16_POLARITY":static["polarity_imbalance"]}
  old={k:os.environ.get(k) for k in envs}
  for k,v in envs.items():os.environ[k]=format(v,".17g")
  try:
   row,trace=previous.r16.previous.r14.run_one(case,repeat,mode,runner)
  finally:
   for k,v in old.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
  row["fold"]=previous.r16.previous.r14.fold_from_category(case["category"])
  row["r16_protocol_sha256"]=previous.r16.sha(previous.r16.CONFIG)
  row["r16_model_sha256"]=previous.r16.sha(previous.r16.MODEL)
  row["r17_model_sha256"]=sha(previous.RISK)
  row["r17_protocol_sha256"]=sha(previous.CONFIG)
  row["r17_native_risk"]=""
  row["r17_python_risk"]=""
  row["r17_risk_limit"]=""
  row["r17_risk_selected"]=""
  row["r17_risk_error"]=""
  early=trace.get("early",{})
  native=early.get("r16_event",{})
  event=early.get("r18_event",{})
  row.update(r16_native_conflict=native.get("conflict",""),
     r16_native_ready=native.get("complete",""),
     r16_native_score=native.get("score",""),
     r16_python_score="",r16_selected=native.get("selected",""),
     r16_expected_target=native.get("target",""),
     r16_threshold=native.get("threshold",""),
     r16_model=native.get("model",""),r16_decision_error="")
  base_model=previous.r16.load_config()[1]["models"]["trajectory"]["r11_2048_50"]
  vector=previous.r16.py_feature_vector(case,trace,base_model)
  prior=previous.r16.score_from_features(base_model,vector)
  if bool(native)!=(vector is not None):
   row["r16_decision_error"]="R18 NATIVE BASE EVENT MISSING OR SPURIOUS"
  if native:
   if native.get("model")!="trajectory" or abs(float(native["threshold"])-.25)>1e-9:
    row["r16_decision_error"]="R18 R16 FROZEN BASE/THRESHOLD CHANGED"
   if bool(int(native["complete"]))!=(vector is not None):
    row["r16_decision_error"]="R18 BASE PREFIX READINESS MISMATCH"
   if int(native["conflict"])<1024 or int(native["conflict"])>=2048:
    row["r16_decision_error"]="R18 BASE DECISION TIMING INVALID"
   if prior is not None:
    row["r16_python_score"]=prior
    if abs(float(native["score"])-prior)>2e-5:
     row["r16_decision_error"]="R18 NATIVE/PYTHON R16 BASE DISAGREE"
  if bool(event)!=(prior is not None):
   row["r16_decision_error"]="R18 NATIVE NETBENEFIT EVENT MISSING"
  if event:
   mean,sigma=score_model(m,prior,case)
   rule=m["preregistered_rules"][mode]
   lower=mean-rule["uncertainty_multiplier"]*sigma
   selected=(case["n"]>=220 and mean>rule["predicted_mean_min"]
             and lower>rule["lower_bound_min"])
   if (event.get("model")!=mode.removeprefix("r18_") or
       abs(float(event["base"])-prior)>2e-5 or
       abs(float(event["mean"])-mean)>2e-5 or
       abs(float(event["sigma"])-sigma)>2e-5 or
       abs(float(event["lower"])-lower)>2e-5 or
       bool(int(event["selected"]))!=selected or
       bool(int(native["selected"]))!=selected or
       native["target"]!=("2048" if selected else "0") or
       event["target"]!=("2048" if selected else "0")):
    row["r16_decision_error"]="R18 FROZEN C/PYTHON DIRECT GAIN/SIGMA/POLICY DISAGREE"
   if row["switch_at"] and (not selected or int(row["switch_at"])<2048 or
       int(row["restart_after"])!=50 or row["learned_before"]!=row["learned_after"]):
    row["r16_decision_error"]="R18 UNSAFE ACTUATION / CLAUSE RESET"
  elif row["switch_at"]:
   row["r16_decision_error"]="R18 SWITCH WITHOUT MODEL EVENT"
  if row["r16_decision_error"]:
   row["error"]=row["r16_decision_error"]
  trace["r18_event"]=event
  trace["r18_predicted_mean"]=mean if event else ""
  trace["r18_predicted_sigma"]=sigma if event else ""
 row.update(r18_native_mean=event.get("mean",""),
    r18_python_mean=trace.get("r18_predicted_mean",""),
    r18_native_sigma=event.get("sigma",""),
    r18_python_sigma=trace.get("r18_predicted_sigma",""),
    r18_native_lower=event.get("lower",""),
    r18_python_lower=(trace.get("r18_predicted_mean",0)-
       m["preregistered_rules"][mode]["uncertainty_multiplier"]*
       trace.get("r18_predicted_sigma",0))
       if mode in R18_MODES and event else "",
    r18_selected=event.get("selected",""),
    r18_base_r16_score=event.get("base",""),
    r18_model_sha256=sha(MODEL),r18_protocol_sha256=sha(CONFIG),
    r18_error=row.get("r16_decision_error",""))
 return row,trace

def write_rows(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  writer.writeheader();writer.writerows(rows)

def run_shard(category):
 cfg,m=load()
 cpu=previous.r16.previous.r14.r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 historic=history()
 cases=make_cases(category,folder,historic)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / pinned core "+str(cpu)+" / "+platform.processor()
 manifest={
   "protocol":cfg["protocol"],"source_commit":os.environ.get("GITHUB_SHA","local"),
   "category":category,"fold":previous.r16.previous.r14.fold_from_category(category),
   "family":previous.r16.previous.r14.family_from_category(category),
   "modes":MODES,"repeats":REPEATS,"cap_seconds":CAP,
   "model_sha256":sha(MODEL),"protocol_sha256":sha(CONFIG),
   "kissat_pin":previous.r16.PIN,"stable_blob":previous.r16.STABLE_PIN,
   "history_sha256":hashlib.sha256("\n".join(sorted(historic)).encode()).hexdigest(),
   "runner":runner,"cpu_core":cpu,"cpu_affinity":sorted(os.sched_getaffinity(0)),
   "executables":{
     "native_patched":sha(previous.r16.previous.r14.r11.base.PATCHED),
     "original_kissat":sha(previous.r16.previous.r14.r11.base.ORIGINAL),
     "stable_v1531":sha(previous.r16.previous.r14.r11.base.STABLE)},
   "cases":[{k:(str(v) if isinstance(v,Path) else v)
         for k,v in case.items() if k!="clauses"} for case in cases],
   "provenance":"new generated prospective synthetic CNF, not official/independent UNSAT proofs"}
 (folder/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
 rows=[];traces=[]
 for case in cases:
  for rep in range(REPEATS):
   sequence=list(MODES)
   random.Random(181818+int(case["formula_sha256"][:12],16)+rep).shuffle(sequence)
   for mode in sequence:
    row,trace=run_one(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:
     f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R18_MEASURE",category,case["formula"],rep,mode,
      row["status"],"par2",row["par2_s"],"mean",row["r18_native_mean"],
      "sigma",row["r18_native_sigma"],"selected",row["r18_selected"],
      "switch",row["switch_at"],flush=True)
    if row["error"]:
     (folder/"error.json").write_text(json.dumps(row,sort_keys=True,indent=2)+"\n")
     raise RuntimeError("R18 INVALID SOLVER/MODEL "+str(row["error"]))
  statuses={x["status"] for x in rows if x["formula"]==case["formula"]
            and x["status"] in ("SAT","UNSAT")}
  if len(statuses)>1:raise RuntimeError("R18 SAT/UNSAT CONTRADICTION "+case["formula"])
 if len(rows)!=270 or len(traces)!=270:
  raise RuntimeError("R18 INCOMPLETE SHARD "+category)
 write_rows(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
 print("R18_SHARD_COMPLETE",category,len(rows),flush=True)

def smoke():
 from tempfile import TemporaryDirectory
 _,_=load()
 with TemporaryDirectory() as d:
  cases=make_cases("n220_development0",Path(d),history())
  for c in cases[:10]:
   for mode in ("monitor",*R18_MODES):
    row,trace=run_one(c,0,mode,"R18 smoke runner")
    if row["error"] or row["status"] not in ("SAT","UNSAT"):
     raise RuntimeError("R18 C/Python native smoke FAIL "+mode+" "+str(row))
    if mode in R18_MODES and row["r18_native_mean"]:
     print("R18_C_PYTHON_SMOKE_PASS",c["formula"],mode,
       row["r18_native_mean"],row["r18_python_mean"],row["r18_native_sigma"],flush=True)
     return
 raise RuntimeError("R18 NO NATIVE 1024 CHECKPOINT DECISION FROM 10 CNFs")

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--category",choices=SHARDS)
 ap.add_argument("--smoke",action="store_true")
 args=ap.parse_args()
 if args.smoke:smoke()
 elif args.category:run_shard(args.category)
 else:ap.error("select --category or --smoke")
