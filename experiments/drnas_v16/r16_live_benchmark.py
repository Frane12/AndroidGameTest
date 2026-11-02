#!/usr/bin/env python3
"""R16 native-in-process R15 frozen ridge50 test, never hindsight replay.
All modes are real solver executions. Python independently audits C model
scores/decisions on each R16 case using only 1024-conflict prefix.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random
from pathlib import Path
import r15_trajectory_benchmark as previous

PIN=previous.PIN
STABLE_PIN=previous.STABLE_PIN
SHARDS=previous.SHARDS
REPEATS=3
CAP=12
MODES=("monitor","r11_2048_50","r11_2048_25","r13_rescue50","r14_dual50",
       "r16_live50","r16_live50_strict","r16_snapshot50",
       "original_kissat","stable_v1531")
R16_MODES=("r16_live50","r16_live50_strict","r16_snapshot50")
OUT=Path("drnas-r16-results")
REGISTRY=Path("experiments/drnas_v16/r16_historical_sha256.txt")
CONFIG=Path("experiments/drnas_v16/r16_frozen_live_protocol.json")
MODEL=Path("experiments/drnas_v16/r15-results/current/frozen_trained_models.json")
FIELDS=previous.FIELDS+("r16_native_conflict","r16_native_ready","r16_native_score",
    "r16_python_score","r16_selected","r16_expected_target","r16_threshold","r16_model",
    "r16_decision_error","r16_protocol_sha256","r16_model_sha256")

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load_config():
 cfg=json.loads(CONFIG.read_text())
 mod=json.loads(MODEL.read_text())
 if cfg["protocol"]!="R16-live-trajectory-ridge50-frozen-20261102-v1":
  raise RuntimeError("R16 FROZEN PROTOCOL MODIFIED")
 if cfg["modes"]!=list(MODES) or cfg["historical_formula_sha_count"]!=2094:
  raise RuntimeError("R16 MODES OR HASH COUNT NOT REGISTERED")
 if (cfg["trained_model_git_blob_sha"]!="d005747f177008172b49cef5f0b8a6f29c3ffc46"
     or mod["training_fold"]!="random3_development" or mod["n_eligible_training"]!=59):
  raise RuntimeError("R16 PRETRAINED FROZEN RIDGE MODEL INVALID")
 return cfg,mod

def make_cases(category,folder,registry):
 cfg,_=load_config()
 n=previous.r14.size_from_category(category)
 family=previous.r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1]);cases=[]
 for j in range(10):
  seed=cfg["generator"]["seed_constant"]+n*10000+(1000 if fold=="test" else 0)+part*10+j+(20000 if family=="community3" else 0)
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
  features=previous.r14.r11.features(clauses,n)
  case=previous.r14.r11.base.emit_cnf(folder,
    f"r16_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
    n,clauses,"UNKNOWN","generated_prospective",
    "DRNAS R16 prospective frozen live model validation; synthetic",
    "r16-real-native-ridge50-v1",
    {"seed":seed,"fold":fold,"family":family,"features":features,
     "community_probability":.65 if family=="community3" else 0.0})
  if case["formula_sha256"] in registry:
   raise RuntimeError("R16 FORMULA SHA256 COLLISION WITH HISTORICAL CORPUS")
  case["category"]=category
  cases.append(case)
 if len({x["formula_sha256"] for x in cases})!=10:
  raise RuntimeError("R16 DUPLICATE SHA256 WITHIN SHARD")
 return cases

def write_rows(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  w.writeheader();w.writerows(rows)

# Keep all prior R13/R14 native event parsing; add independent R16 event.
PREVIOUS_EXTRACT=previous.r14.r11.base.extract_tags
def parse_r16(output):
 points,labels=PREVIOUS_EXTRACT(output)
 markers=[]
 for line in output.splitlines():
  if not line.startswith("c R16_DECISION "):continue
  d={}
  for token in line.split()[2:]:
   if "=" in token:
    key,val=token.split("=",1)
    d[key]=val
  markers.append(d)
 if len(markers)>1:raise RuntimeError("R16 NATIVE DECISION LOGGED MORE THAN ONCE")
 if markers:labels["R16_DECISION"]=markers[0]
 return points,labels
previous.r14.r11.base.extract_tags=parse_r16

def landmarks(trace):
 result={}
 for cp in (128,256,512,1024):
  result[cp]=next((row for row in trace["points"] if int(row["conflict"])>=cp),None)
 return result

def py_feature_vector(case,trace,model):
 pts=landmarks(trace)
 early=trace["early"]
 if not all(pts.values()) or not early or "p" not in early or "g" not in early:
  return None
 a,b,c,d=[pts[k] for k in (128,256,512,1024)]
 def ratio(x,y,key):
  return (float(y[key])-float(x[key]))/(int(y["conflict"])-int(x["conflict"]))
 p12=ratio(a,b,"propagations")
 p23=ratio(b,c,"propagations")
 p34=ratio(c,d,"propagations")
 g1,g2,g3,g4=[float(z["glue"]) for z in (a,b,c,d)]
 features=case["metadata"]["features"]
 x={
  "n_scaled":case["n"]/240.,
  "degree_cv":features["degree_cv"],
  "degree_gini":features["degree_gini"],
  "polarity_imbalance":features["polarity_imbalance"],
  "p512":float(early["p"]),"g512":float(early["g"]),
  "restarts512":math.log1p(float(c["restarts"])),
  "learned512":float(c["learned"])/512.,
  "stable512":float(c["stable"]),"reached1024":1.0,
  "p128_256":p12,"p256_512":p23,"p512_1024":p34,
  "p_slope_256_1024":p34-p23,"p_curvature":p34-2*p23+p12,
  "g128":g1,"g256":g2,"g1024":g4,
  "g_slope_256_1024":g4-g2,"g_curvature":g4-2*g3+g2,
  "restart_rate_256_512":ratio(b,c,"restarts"),
  "restart_rate_512_1024":ratio(c,d,"restarts"),
  "learned_rate_256_512":ratio(b,c,"learned"),
  "learned_rate_512_1024":ratio(c,d,"learned"),
  "decision_rate_512_1024":ratio(c,d,"decisions")
 }
 return x

def score_from_features(model,x):
 if x is None:return None
 pred=float(model["coefficients"][0])
 for i,key in enumerate(model["feature_names"]):
  z=(x[key]-float(model["mu"][i]))/float(model["sd"][i])
  pred+=float(model["coefficients"][i+1])*max(-3.,min(3.,z))
 return pred

def run_one(case,rep,mode,runner):
 cfg,model=load_config()
 env_names={"DRNAS_R16_GINI":"degree_gini",
            "DRNAS_R16_POLARITY":"polarity_imbalance"}
 old={name:os.environ.get(name) for name in env_names}
 for name,feat in env_names.items():
  os.environ[name]=format(case["metadata"]["features"][feat],".17g")
 try:row,trace=previous.r14.run_one(case,rep,mode,runner)
 finally:
  for name,val in old.items():
   if val is None:os.environ.pop(name,None)
   else:os.environ[name]=val
 row["fold"]=previous.r14.fold_from_category(case["category"])
 row["r16_protocol_sha256"]=sha(CONFIG)
 row["r16_model_sha256"]=sha(MODEL)
 early=trace.get("early",{})
 native=early.get("r16_event",{})
 row.update(r16_native_conflict=native.get("conflict",""),
   r16_native_ready=native.get("complete",""),
   r16_native_score=native.get("score",""),
   r16_python_score="",r16_selected=native.get("selected",""),
   r16_expected_target=native.get("target",""),
   r16_threshold=native.get("threshold",""),
   r16_model=native.get("model",""),r16_decision_error="")
 if mode in R16_MODES:
  points=landmarks(trace)
  expected_present=points[1024] is not None and bool(early)
  if expected_present != bool(native):
   row["r16_decision_error"]="R16 MISSING/SPURIOUS DECISION AT 1024"
  if native:
   candidate="snapshot" if mode=="r16_snapshot50" else "trajectory"
   m=model["models"][candidate]["r11_2048_50"]
   x=py_feature_vector(case,trace,m)
   expected_ready=x is not None
   threshold=cfg["safety_design"]["allowed_thresholds"][mode]
   predicted=score_from_features(m,x)
   selected=bool(expected_ready and case["n"]>=220 and predicted>threshold)
   row["r16_python_score"]=predicted if predicted is not None else ""
   if native.get("model")!=candidate or abs(float(native["threshold"])-threshold)>1e-10:
    row["r16_decision_error"]="R16 NATIVE MODE/THRESHOLD IS NOT FROZEN"
   elif bool(int(native["complete"]))!=expected_ready:
    row["r16_decision_error"]="R16 NATIVE READINESS MISMATCH"
   elif predicted is not None and abs(float(native["score"])-predicted)>0.00002:
    row["r16_decision_error"]="R16 C VS PYTHON RIDGE50 SCORE PARITY FAILURE"
   elif bool(int(native["selected"]))!=selected:
    row["r16_decision_error"]="R16 C VS PYTHON SELECTOR CHOICE MISMATCH"
   elif native["target"]!=("2048" if selected else "0"):
    row["r16_decision_error"]="R16 NATIVE TARGET MISMATCH"
   elif int(native["conflict"])<1024 or int(native["conflict"])>=2048:
    row["r16_decision_error"]="R16 DECISION OUTSIDE ALLOWED 1024-2048 WINDOW"
  if row["switch_at"]:
   if not native or native["selected"]!="1" or int(row["switch_at"])<2048:
    row["r16_decision_error"]="R16 UNAUTHORIZED SOLVER INTERVENTION"
   elif int(row["restart_after"])!=50 or row["learned_before"]!=row["learned_after"]:
    row["r16_decision_error"]="R16 RESTART50/LEARNED CLAUSE INTEGRITY FAILURE"
  if row["r16_decision_error"]:row["error"]=row["r16_decision_error"]
 elif native:
  row["error"]="NON R16 ARM EMITTED R16 NATIVE MODEL DECISION"
 trace["r16_decision"]=native
 trace["r16_python_score"]=row["r16_python_score"]
 return row,trace

def run_shard(category):
 cfg,_=load_config()
 core=previous.r14.r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 registry={x for x in REGISTRY.read_text().split() if len(x)==64 and all(c in "0123456789abcdef" for c in x)}
 if len(registry)!=2094:raise RuntimeError("R16 HISTORY REGISTRY INCOMPLETE")
 cases=make_cases(category,folder,registry)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / pinned core "+str(core)+" / "+platform.processor()
 manifest={
  "protocol":cfg["protocol"],"source_commit":os.environ.get("GITHUB_SHA","local"),
  "category":category,"fold":previous.r14.fold_from_category(category),
  "family":previous.r14.family_from_category(category),
  "kissat_pin":PIN,"stable_blob":STABLE_PIN,
  "frozen_r15_model_blob_sha":cfg["trained_model_git_blob_sha"],
  "r16_model_sha256":sha(MODEL),"r16_protocol_sha256":sha(CONFIG),
  "historical_registry_sha256":sha(REGISTRY),
  "runner":runner,"platform":platform.platform(),
  "cpu_core":core,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "cap_seconds":CAP,"repeats":REPEATS,"modes":MODES,
  "executables":{"original_kissat":sha(previous.r14.r11.base.ORIGINAL),
    "same_binary_monitor_and_r16":sha(previous.r14.r11.base.PATCHED),
    "stable_v1531":sha(previous.r14.r11.base.STABLE)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v)
    for k,v in case.items() if k!="clauses"} for case in cases]}
 previous.r14.dump(folder/"manifest.json",manifest)
 rows=[];traces=[]
 for case in cases:
  for rep in range(REPEATS):
   order=list(MODES)
   random.Random(816160+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    row,trace=run_one(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R16_MEASURE",category,case["formula"],rep,mode,
          row["status"],row["par2_s"],
          "model",row["r16_model"],"score",row["r16_native_score"],
          "decision",row["r16_selected"],"switch",row["switch_at"],flush=True)
    if row["error"]:
     previous.r14.dump(folder/"error.json",row)
     raise RuntimeError("R16_INVALID_REAL_SAT_RESULT "+row["error"])
  final={r["status"] for r in rows if r["formula"]==case["formula"] and r["status"] in ("SAT","UNSAT")}
  if len(final)>1:raise RuntimeError("R16 CONTRADICTORY SAT/UNSAT "+case["formula"])
 if len(rows)!=300 or len(traces)!=300:
  raise RuntimeError("R16 INCOMPLETE SHARD")
 write_rows(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
 print("R16_SHARD_COMPLETE",category,len(rows),flush=True)

def smoke_native():
 from tempfile import TemporaryDirectory
 cfg,_=load_config()
 registry=set(x for x in REGISTRY.read_text().split() if len(x)==64)
 if len(registry)!=2094:raise RuntimeError("R16 SMOKE HISTORY INCOMPLETE")
 with TemporaryDirectory() as tmp:
  cases=make_cases("n220_development0",Path(tmp),registry)
  for case in cases[:5]:
   for mode in ("r16_live50","r16_live50_strict","r16_snapshot50"):
    row,trace=run_one(case,0,mode,"R16 audit smoke")
    if row["error"] or row["status"] not in ("SAT","UNSAT"):
     raise RuntimeError("R16 SMOKE FAIL "+mode+" "+str(row))
    if not row["r16_native_score"]:
     continue
    print("R16_SMOKE_NATIVE_PARITY",case["formula"],mode,
      "native",row["r16_native_score"],"python",row["r16_python_score"],flush=True)
   if any(run_one(case,0,"r16_live50","R16 audit smoke")[0]["r16_native_score"] for _ in range(1)):
    print("R16_NATIVE_PREDICTOR_SMOKE_PASS")
    return
 raise RuntimeError("R16 SMOKE FAILED: NO TEST CNF REACHED 1024 CONFLICTS")

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--category",choices=SHARDS)
 p.add_argument("--smoke-native",action="store_true")
 args=p.parse_args()
 if args.smoke_native:smoke_native()
 elif args.category:run_shard(args.category)
 else:p.error("select --category or --smoke-native")
