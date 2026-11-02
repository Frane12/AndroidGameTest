#!/usr/bin/env python3
"""R15: observational trajectory collection, no new adaptive policy in solver.
Single core per shard; all strategies have exact same CNF+seed+runner.
All 2048/4096 switches and frozen previous gates use pinned R14 source.
"""
from __future__ import annotations
import os,sys,json,random,csv,hashlib,platform
from pathlib import Path
import argparse
import r14_dual_benchmark as r14

PIN=r14.PIN
STABLE_PIN=r14.STABLE_PIN
SHARDS=r14.SHARDS
MODES=("monitor","r11_2048_25","r11_2048_50","r11_4096_25",
       "r13_rescue50","r14_dual50","original_kissat","stable_v1531")
REPEATS=3
CAP=12
OUT=Path("drnas-r15-results")
CONFIG=Path("experiments/drnas_v16/r15_frozen_protocol.json")
REGISTRY=Path("experiments/drnas_v16/r15_historical_sha256.txt")
FIELDS=r14.FIELDS+("r15_config_sha256",)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load_config():
 c=json.loads(CONFIG.read_text())
 if (c["protocol"]!="R15-trajectory-locked-prospective-v1" or
     c["model"]["ridge_lambda"]!=30 or
     c["model"]["abstain_below_predicted_log_gain"]!=0.12 or
     c["model"]["required_1024_landmark"] is not True or
     c["generator"]["random3_count"]!=120 or
     c["generator"]["community3_count"]!=40 or
     c["arms"]!=list(MODES) or
     c["checkpoints"]!=[128,256,512,1024]):
  raise RuntimeError("R15 FROZEN EXPERIMENT CONFIG CHANGED")
 return c
def make_cases(category,folder,registry):
 config=load_config()
 n=r14.size_from_category(category)
 family=r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1])
 cases=[]
 for j in range(10):
  seed=715150000+n*10000+(1000 if fold=="test" else 0)+part*10+j+(20000 if family=="community3" else 0)
  rng=random.Random(seed)
  clauses=[]
  for _ in range(round(4.23*n)):
   if family=="community3" and rng.random()<0.65:
    block=rng.randrange(4)
    start=block*(n//4)+1
    vs=rng.sample(range(start,start+n//4),3)
   else:
    vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  f=r14.r11.features(clauses,n)
  case=r14.r11.base.emit_cnf(folder,f"r15_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
   n,clauses,"UNKNOWN","generated_prospective",
   "DRNAS R15 frozen prospective trajectory cohort (synthetic)",
   "r15-trajectory-v1",
   {"seed":seed,"fold":fold,"family":family,"features":f,
    "community_probability":0.65 if family=="community3" else 0.0})
  if case["formula_sha256"] in registry:
   raise RuntimeError("R15 HISTORICAL DUPLICATE SHA256: "+case["formula"])
  case["category"]=category
  cases.append(case)
 if len({c["formula_sha256"] for c in cases})!=10:
  raise RuntimeError("R15 WITHIN-SHARD DUPLICATE SHA256")
 return cases
def write_rows(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  w.writeheader();w.writerows(rows)

def run_one(case,rep,mode,runner):
 row,trace=r14.run_one(case,rep,mode,runner)
 row["r15_config_sha256"]=sha(CONFIG)
 row["fold"]=r14.fold_from_category(case["category"])
 if mode=="monitor" and row["switch_at"]:
  row["error"]="R15 MONITOR MODIFIED NATIVE RESTARTS"
 if mode in ("r11_2048_25","r11_2048_50","r11_4096_25") and row["switch_at"]:
  target,interval=mode.split("_")[1:]
  if int(row["switch_at"])<int(target) or int(row["restart_after"])!=int(interval):
   row["error"]="R15 FORCED RESTART TARGET DOES NOT MATCH SOURCE"
 if mode in ("r13_rescue50","r14_dual50") and row["switch_at"] and row["learned_before"]!=row["learned_after"]:
  row["error"]="R15 POLICY RESET LEARNED CLAUSE DATABASE"
 return row,trace

def run_shard(category):
 config=load_config()
 core=r14.r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 registry=set(x for x in REGISTRY.read_text().split() if len(x)==64 and
              all(ch in "0123456789abcdef" for ch in x))
 if len(registry)!=1934:raise RuntimeError("R15 REGISTRY SHA COUNT NOT FROZEN")
 cases=make_cases(category,folder,registry)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / pinned core "+str(core)+" / "+platform.processor()
 manifest={
  "protocol":config["protocol"],"source_commit":os.environ.get("GITHUB_SHA","local"),
  "category":category,"fold":r14.fold_from_category(category),"family":r14.family_from_category(category),
  "source_ref":"experiments/drnas_v16/patch_r14_dual.py",
  "kissat_pin":PIN,"stable_blob":STABLE_PIN,
  "r15_protocol_sha256":sha(CONFIG),"historical_registry_sha256":sha(REGISTRY),
  "runner":runner,"platform":platform.platform(),
  "cpu_core":core,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "cap_seconds":CAP,"repeats":REPEATS,"modes":MODES,
  "executables":{"original_kissat":sha(r14.r11.base.ORIGINAL),
    "instrumented_pinned_kissat":sha(r14.r11.base.PATCHED),
    "stable_v1531":sha(r14.r11.base.STABLE)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v)
   for k,v in case.items() if k!="clauses"} for case in cases]}
 r14.dump(folder/"manifest.json",manifest)
 allrows=[];traces=[]
 for case in cases:
  for rep in range(REPEATS):
   modes=list(MODES)
   random.Random(715150+int(case["formula_sha256"][:12],16)+rep).shuffle(modes)
   for mode in modes:
    row,trace=run_one(case,rep,mode,runner)
    allrows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",allrows)
    with (folder/"traces.partial.jsonl").open("a") as f:
     f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R15_MEASURE",category,case["formula"],rep,mode,
      row["status"],row["par2_s"],
      "trace",row["trace_points"],"switch",row["switch_at"],flush=True)
    if row["error"]:
     r14.dump(folder/"error.json",row)
     raise RuntimeError("R15 UNVERIFIED MEASUREMENT: "+row["error"])
  answers={x["status"] for x in allrows
           if x["formula"]==case["formula"] and x["status"] in ("SAT","UNSAT")}
  if len(answers)>1:raise RuntimeError("SAT/UNSAT CONTRADICTION "+case["formula"])
 if len(allrows)!=240 or len(traces)!=240:
  raise RuntimeError("R15 INCOMPLETE SHARD")
 write_rows(folder/"measurements.csv",allrows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in traces))
 print("R15_SHARD_COMPLETE",category,len(allrows),flush=True)

if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("--category",choices=SHARDS,required=True)
 args=parser.parse_args()
 run_shard(args.category)
