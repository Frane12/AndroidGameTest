#!/usr/bin/env python3
"""DRNAS R19: prospective native SAT telemetry for frozen snapshot vs trajectory hypothesis.

No model inference controls solving in R19: real monitor, real 2048/50 forced,
real R16 trajectory telemetry, original upstream Kissat. 3 repeats on 160 new
generated CNFs. Fit both models only on new development shard artifacts,
freeze before test jobs run. Pre-1024 comparator dynamics must match.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,platform,random
from pathlib import Path
import r16_live_benchmark as r16

ROOT=Path("experiments/drnas_v16")
CFG_PATH=ROOT/"r19_frozen_protocol.json"
OUT=Path("drnas-r19-results")
SHARDS=r16.SHARDS
MODES=("monitor","r11_2048_50","r16_live50","original_kissat")
CAP=12
REPEATS=3
HISTORICAL_RESULTS={
 "r16-results/current/results.json":"2b6f10b778b566debf83f2c07f86bc8639b1d251",
 "r17-results/current/results.json":"c1dff80bde422116f511a89901f54b634a06adb8",
 "r18-results/current/results.json":"aab7cd45cf1d4fef5a308dac43e681b5a7d24646"}
FIELDS=r16.FIELDS+("r19_protocol_sha256","r19_trace_ready_at_1024")
FROZEN=Path("r19-frozen/r19_frozen_models.json")

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def git_blob(path):
 import subprocess
 return subprocess.check_output(["git","hash-object",str(path)],text=True).strip()
def config():
 c=json.loads(CFG_PATH.read_text())
 if (c["protocol"]!="DRNAS-R19-dynamics-vs-1024-snapshot-blind-v1-20261102" or
     c["experiment"]["strategies"]!=list(MODES) or
     c["experiment"]["formulas"]!=160 or
     c["experiment"]["attempts"]!=1920 or
     c["provenance"]["Kissat_git_sha"]!=r16.PIN or
     c["provenance"]["V1531_blob"]!=r16.STABLE_PIN):
  raise RuntimeError("R19 PROTOCOL/GIT PIN MISCONFIGURATION")
 return c

def history():
 cfg=config()
 p=r16.REGISTRY
 if git_blob(p)!=cfg["provenance"]["R16_historical_registry_hash"]:
  raise RuntimeError("R19 HISTORICAL REGISTRY BLOB DRIFT")
 used={s for s in p.read_text().split() if len(s)==64}
 if len(used)!=2094:raise RuntimeError("R19 R16 REGISTRY 2094 NOT PRESENT")
 for name,blob in HISTORICAL_RESULTS.items():
  f=ROOT/name
  if git_blob(f)!=blob:raise RuntimeError("R19 HISTORICAL RESULTS MODIFIED "+name)
  report=json.loads(f.read_text())
  identities={case["formula_sha256"] for m in report["manifests"] for case in m["cases"]}
  if len(identities)!=160 or identities&used:
   raise RuntimeError("R19 HISTORICAL INTERSECTION "+name)
  used.update(identities)
 if len(used)!=2574:raise RuntimeError("R19 HISTORICAL COUNT NOT 2574")
 return used

def make_cases(category,folder,used):
 cfg=config()
 n=r16.previous.r14.size_from_category(category)
 family=r16.previous.r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1]);cases=[]
 for j in range(10):
  seed=cfg["experiment"]["generator_seed_base"]+n*10000+(
    1000 if fold=="test" else 0)+part*10+j+(
    20000 if family=="community3" else 0)
  rng=random.Random(seed);clauses=[]
  for _ in range(round(4.23*n)):
   if family=="community3" and rng.random()<.65:
    start=rng.randrange(4)*(n//4)+1
    vs=rng.sample(range(start,start+n//4),3)
   else:vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  features=r16.previous.r14.r11.features(clauses,n)
  case=r16.previous.r14.r11.base.emit_cnf(folder,
    f"r19_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
    n,clauses,"UNKNOWN","generated_prospective",
    "DRNAS R19 new frozen dynamics-vs-snapshot observational test; not official",
    "r19-blind-trajectory-hypothesis-v1",
    {"seed":seed,"fold":fold,"family":family,"features":features,
     "community_probability":.65 if family=="community3" else 0.0})
  if case["formula_sha256"] in used:
   raise RuntimeError("R19 HISTORICAL FORMULA HASH COLLISION")
  case["category"]=category
  cases.append(case)
 if len({c["formula_sha256"] for c in cases})!=10:
  raise RuntimeError("R19 DUPLICATE IN SHARD")
 return cases

def writecsv(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  w.writeheader();w.writerows(rows)

def one(case,rep,mode,runner):
 row,trace=r16.run_one(case,rep,mode,runner)
 row["r19_protocol_sha256"]=sha(CFG_PATH)
 landmark=r16.landmarks(trace)
 row["r19_trace_ready_at_1024"]=int(
   mode=="r16_live50" and all(landmark.values()) and bool(trace.get("early")))
 return row,trace

def run(category):
 cfg=config();phase="development" if "_development" in category else "test"
 if phase=="test":
  if not FROZEN.is_file():raise RuntimeError("R19 TEST BLOCKED: FROZEN DEV MODEL MISSING")
  frozen=json.loads(FROZEN.read_text())
  if (frozen["protocol"]!=cfg["protocol"] or
      frozen["training_fold"]!="random3_development" or
      frozen["training_formula_count"]<20 or
      len(frozen["models"])!=2):
   raise RuntimeError("R19 TEST FROZEN DEV MODEL AUDIT FAILURE")
 core=r16.previous.r14.r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 prev=history()
 cases=make_cases(category,folder,prev)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / core "+str(core)+" / "+platform.processor()
 manifest={
  "protocol":cfg["protocol"],"category":category,"phase":phase,
  "source_commit":os.environ.get("GITHUB_SHA","local"),
  "family":r16.previous.r14.family_from_category(category),
  "fold":r16.previous.r14.fold_from_category(category),
  "modes":MODES,"repeats":REPEATS,"cap_seconds":CAP,
  "runner":runner,"cpu_core":core,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "kissat_pin":r16.PIN,"stable_source_blob":r16.STABLE_PIN,
  "protocol_sha256":sha(CFG_PATH),
  "historic_count":len(prev),
  "historic_sha256":hashlib.sha256("\n".join(sorted(prev)).encode()).hexdigest(),
  "frozen_model_sha256":sha(FROZEN) if phase=="test" else None,
  "executable_sha256":{
    "patched":sha(r16.previous.r14.r11.base.PATCHED),
    "original":sha(r16.previous.r14.r11.base.ORIGINAL)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v) for k,v in c.items()
     if k!="clauses"} for c in cases],
  "limitations":"SAT witnesses are checked but UNSAT has no independently verified certificate"}
 (folder/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
 rows=[];traces=[]
 for case in cases:
  for rep in range(3):
   order=list(MODES)
   random.Random(191919+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    row,trace=one(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    writecsv(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:
     f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R19_NATIVE_MEASURE",category,case["formula"],rep,mode,row["status"],
      "PAR2",row["par2_s"],"prefix_ready",row["r19_trace_ready_at_1024"],flush=True)
    if row["error"]:
     (folder/"error.json").write_text(json.dumps(row,sort_keys=True,indent=2)+"\n")
     raise RuntimeError("R19 REAL SAT MEASUREMENT INVALID: "+row["error"])
  solved={x["status"] for x in rows
      if x["formula"]==case["formula"] and x["status"] in ("SAT","UNSAT")}
  if len(solved)>1:raise RuntimeError("R19 SAT/UNSAT CONTRADICTION")
 if len(rows)!=120 or len(traces)!=120:raise RuntimeError("R19 SHARD INCOMPLETE")
 writecsv(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(
   json.dumps(x,sort_keys=True)+"\n" for x in traces))
 print("R19_COMPLETE_NATIVE_SHARD",category,120,flush=True)

def smoke():
 from tempfile import TemporaryDirectory
 with TemporaryDirectory() as tmp:
  cases=make_cases("n220_development0",Path(tmp),history())
  for case in cases[:10]:
   for mode in MODES:
    row,trace=one(case,0,mode,"R19 smoke")
    if row["error"] or row["status"] not in ("SAT","UNSAT"):
     raise RuntimeError("R19 NATIVE SMOKE FAILED: "+str(row))
   if r16.landmarks(trace).get(1024) is not None:
    print("R19_SMOKE_SOLVER_PASS",case["formula"],flush=True)
    return
 raise RuntimeError("R19 NO PREFIX FROM SMOKE FORMULAS")

if __name__=="__main__":
 p=argparse.ArgumentParser()
 p.add_argument("--category",choices=SHARDS)
 p.add_argument("--smoke",action="store_true")
 a=p.parse_args()
 if a.smoke:smoke()
 elif a.category:run(a.category)
 else:p.error("need --category or --smoke")
