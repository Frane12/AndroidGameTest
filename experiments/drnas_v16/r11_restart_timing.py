#!/usr/bin/env python3
"""R11: frozen, observational restart-timing intervention sweep.
Real in-process Kissat SAT solving on prospectively generated 3-SAT formulas.
Never edits the V15.3.1 solver; no adaptive policy or holdout fitting.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random,resource,signal,statistics,subprocess,time
from collections import defaultdict,Counter
from pathlib import Path
import r7_large as base

PIN=base.PIN_KISSAT
STABLE_PIN=base.PIN_STABLE_BLOB
SOURCE_R7="6f70bb18664cffa2608a94c6fe7c1542cd576511"
CAP=12
REPEATS=3
NS=(200,220,240)
FOLDS=("development","test")
SHARDS=tuple(f"n{n}_{fold}{part}" for n in NS for fold in FOLDS for part in (0,1))
MODES=("monitor","r11_512_25","r11_1024_25","r11_2048_25","r11_4096_25","r11_2048_50","original_kissat","stable_v1531")
INTERVENTIONS=tuple(m for m in MODES if m.startswith("r11_"))
OUT=Path("drnas-r11-results")
REGISTRY=Path("experiments/drnas_v16/r11_historical_sha256.txt")
FIELDS=("category","fold","formula","formula_sha256","seed","repeat","mode","status","expected","wall_s","cpu_s","par2_s",
        "runner","error","sat_model_checked","unsat_certificate_checked","exit_code","switch_at","restart_before",
        "restart_after","learned_before","learned_after","early_r","early_d","early_p","early_g","early_l",
        "final_conflicts","final_restarts","trace_points","degree_cv","degree_gini","polarity_imbalance")
MARKS=(32,64,96,128,192,256,384,512,768,1024,1536,2048,3072,4096,6144,8192)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def write_rows(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore");w.writeheader();w.writerows(rows)

def features(clauses,n):
 degree=[0]*n;pos=[0]*n;neg=[0]*n
 for cl in clauses:
  for lit in cl:
   degree[abs(lit)-1]+=1
   (pos if lit>0 else neg)[abs(lit)-1]+=1
 mean=sum(degree)/n
 cv=(sum((x-mean)**2 for x in degree)/n)**.5/mean if mean else 0
 sorted_degree=sorted(degree)
 gini=sum((2*i-n-1)*d for i,d in enumerate(sorted_degree,1))/(n*sum(sorted_degree)) if mean else 0
 return {"variables":n,"clauses":len(clauses),"clause_density":len(clauses)/n,
  "degree_cv":cv,"degree_gini":gini,"degree_min":min(degree),"degree_max":max(degree),
  "polarity_imbalance":sum(abs(p-q) for p,q in zip(pos,neg))/max(1,sum(degree))}

def cases_for(category,folder,registry):
 n=int(category[1:4]);fold="development" if "_development" in category else "test"
 part=int(category[-1]);cases=[]
 for j in range(10):
  seed=311100000 + n*10000 + (0 if fold=="development" else 1000) + part*10+j
  rng=random.Random(seed)
  m=round(4.23*n)
  clauses=[]
  for _ in range(m):
   vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  f=features(clauses,n)
  case=base.emit_cnf(folder,f"r11_{n}_{fold}_{part}_{j:02d}.cnf",n,
   clauses,"UNKNOWN","generated_prospective",
   "DRNAS R11 preregistered fresh 3-SAT generator","r11-timing-v1",
   {"seed":seed,"fold":fold,"features":f})
  if case["formula_sha256"] in registry:
   raise RuntimeError("SHA256 duplicate against frozen prior registry: "+case["formula"])
  case["category"]=category
  cases.append(case)
 if len({c["formula_sha256"] for c in cases})!=10:
  raise RuntimeError("Repeated SHA256 within shard")
 return cases

def set_cpu_affinity():
 if not hasattr(os,"sched_setaffinity"):
  raise RuntimeError("CPU pinning required on GitHub Linux")
 cpus=os.sched_getaffinity(0)
 if not cpus:raise RuntimeError("No CPU affinity target")
 chosen=min(cpus);os.sched_setaffinity(0,{chosen})
 if os.sched_getaffinity(0)!={chosen}:raise RuntimeError("Failed to pin same CPU core")
 return chosen

def run_one(case,rep,mode,runner):
 env=os.environ.copy()
 env.pop("DRNAS_V177_MODE",None);env.pop("DRNAS_V177_RULE_FILE",None)
 path=str(case["path"].resolve())
 if mode=="original_kissat":
  command=[str(base.ORIGINAL),"-s",path]
 elif mode=="stable_v1531":
  command=[str(base.STABLE),path,str(base.ORIGINAL),"1"]
 else:
  env["DRNAS_V177_MODE"]="r5_monitor" if mode=="monitor" else mode
  command=[str(base.PATCHED),"-s",path]
 before=resource.getrusage(resource.RUSAGE_CHILDREN)
 start=time.perf_counter()
 proc=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    text=True,errors="replace",start_new_session=True)
 try:
  stdout,stderr=proc.communicate(timeout=CAP)
  status={10:"SAT",20:"UNSAT"}.get(proc.returncode,"ERROR")
 except subprocess.TimeoutExpired:
  os.killpg(proc.pid,signal.SIGKILL)
  stdout,stderr=proc.communicate()
  status="TIMEOUT"
 wall=time.perf_counter()-start
 after=resource.getrusage(resource.RUSAGE_CHILDREN)
 cpu=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
 payload=None
 for line in stdout.splitlines():
  if line.startswith("DRNAS_HYBRID_RESULT\t"):
   payload=json.loads(line.split("\t",1)[1])
 if payload:status=payload.get("status","ERROR").upper()
 trace,labels=base.extract_tags(stdout+"\n"+stderr)
 early=labels.get("DRNAS_V177_EARLY",{})
 switched=labels.get("DRNAS_V177_SWITCH",{})
 finish=labels.get("DRNAS_V177_FINAL",{})
 witness=(base.check_witness(case,stdout,payload) if status=="SAT" else None)
 certificate=(base.proof_check(case,payload) if status=="UNSAT" and payload else None)
 error=""
 if status=="ERROR":error="EXIT ERROR "+str(proc.returncode)+" "+stderr[-260:]
 if status=="SAT" and witness is not True:error="SAT WITNESS INVALID/MISSING"
 if certificate is False:error="INVALID NATIVE UNSAT CERTIFICATE"
 if status not in ("SAT","UNSAT","TIMEOUT"):error="UNKNOWN STATUS "+status
 if mode=="monitor" and switched:error="MONITOR ALTERED POLICY"
 if mode.startswith("r11_"):
  _,at,interval=mode.split("_");at=int(at);interval=int(interval)
  if switched:
   if (int(switched.get("at",0))<at or
       int(switched.get("restart_after",-1))!=interval or
       switched.get("before")!=switched.get("after")):
    error="R11 UNAUTHORIZED OR INCORRECT RESTART SWITCH"
  elif status=="TIMEOUT" and len(trace)>0:
   # A long-running unsolved formula should reach the action threshold.
   if int(trace[-1].get("conflict",0))>=at: error="MISSING REQUIRED R11 SWITCH"
 if mode in ("original_kissat","stable_v1531") and switched:error="REFERENCE EMITTED R11 SWITCH"
 row=dict(category=case["category"],fold=case["metadata"]["fold"],
  formula=case["formula"],formula_sha256=case["formula_sha256"],
  seed=case["metadata"]["seed"],repeat=rep,mode=mode,status=status,
  expected=case["expected"],wall_s=round(wall,6),cpu_s=round(cpu,6),
  par2_s=round(wall,6) if status in ("SAT","UNSAT") else 2*CAP,
  runner=runner,error=error,sat_model_checked=witness,
  unsat_certificate_checked=certificate,exit_code=proc.returncode,
  switch_at=switched.get("at",""),restart_before=switched.get("restart_before",""),
  restart_after=switched.get("restart_after",""),learned_before=switched.get("before",""),
  learned_after=switched.get("after",""),
  early_r=early.get("r",""),early_d=early.get("d",""),
  early_p=early.get("p",""),early_g=early.get("g",""),early_l=early.get("l",""),
  final_conflicts=finish.get("conflicts",""),final_restarts=finish.get("restarts",""),
  trace_points=len(trace),
  degree_cv=case["metadata"]["features"]["degree_cv"],
  degree_gini=case["metadata"]["features"]["degree_gini"],
  polarity_imbalance=case["metadata"]["features"]["polarity_imbalance"])
 return row,{"category":case["category"],"formula":case["formula"],
  "repeat":rep,"mode":mode,"points":trace,"early":early,"switch":switched,"final":finish}

def shard_run(category):
 core=set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 registry={s for s in REGISTRY.read_text().split() if len(s)==64 and all(c in "0123456789abcdef" for c in s)}
 if len(registry)<1300:raise RuntimeError("Registry incomplete")
 cases=cases_for(category,folder,registry)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / core "+str(core)+" / "+platform.processor()
 manifest=dict(category=category,fold=cases[0]["metadata"]["fold"],
  provenance="generated_prospective_project_holdout_not_official",
  source_commit=os.environ.get("GITHUB_SHA","local"),source_ref=SOURCE_R7,
  pin_kissat=PIN,stable_blob=STABLE_PIN,
  cpu_core=core,cpu_affinity=sorted(os.sched_getaffinity(0)),
  runner=runner,platform=platform.platform(),
  registry_sha256=sha(REGISTRY),
  cap_seconds=CAP,repeats=REPEATS,modes=MODES,checkpoints=MARKS,
  executables={"original":sha(base.ORIGINAL),"patched":sha(base.PATCHED),"v1531":sha(base.STABLE)},
  cases=[{k:(str(v) if isinstance(v,Path) else v) for k,v in case.items() if k!="clauses"} for case in cases])
 dump(folder/"manifest.json",manifest)
 rows=[];traces=[]
 for case in cases:
  for rep in range(REPEATS):
   order=list(MODES)
   random.Random(311111+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    row,trace=run_one(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R11_MEASURE",category,case["formula"],rep,mode,
      row["status"],row["par2_s"],"switch",row["switch_at"],flush=True)
    if row["error"]:
     dump(folder/"error.json",row)
     raise RuntimeError(row["error"])
  solved={r["status"] for r in rows if r["formula"]==case["formula"] and r["status"] in ("SAT","UNSAT")}
  if len(solved)>1:raise RuntimeError("SAT/UNSAT CONTRADICTION: "+case["formula"])
 if len(rows)!=10*REPEATS*len(MODES):raise RuntimeError("Incomplete shard")
 write_rows(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
 print("R11_SHARD_COMPLETE",category,len(rows),flush=True)

def quantile(vals,p):
 vals=sorted(vals);x=(len(vals)-1)*p;i=int(x)
 return vals[i]*(1-(x-i))+vals[min(i+1,len(vals)-1)]*(x-i) if vals else None

def bootstrap(features,mode,seed):
 # Resample formulas within fixed variable count strata; three repeats are a block.
 rng=random.Random(seed)
 by=defaultdict(list)
 for f in features:by[f["n"]].append(f)
 gains=[]
 for _ in range(2000):
  sampled=[rng.choice(group) for group in by.values() for _ in group]
  baseline=sum(f["monitor"] for f in sampled)
  treatment=sum(f[mode] for f in sampled)
  gains.append(100*(baseline-treatment)/baseline if baseline else 0)
 return [quantile(gains,.025),quantile(gains,.975)]

def aggregate():
 raw=[];manifests=[];sources=[];alltraces={}
 for category in SHARDS:
  folder=Path("r11-download")/("r11-"+category)
  a,b,c=[folder/x for x in ("measurements.csv","manifest.json","traces.jsonl")]
  if not all(p.is_file() for p in (a,b,c)):raise RuntimeError("MISSING SHARD "+category)
  rows=list(csv.DictReader(a.open()))
  manifest=json.loads(b.read_text())
  trace=[json.loads(x) for x in c.read_text().splitlines()]
  if len(rows)!=240 or len(trace)!=240:raise RuntimeError("SHARD INCOMPLETE "+category)
  if manifest["pin_kissat"]!=PIN or manifest["stable_blob"]!=STABLE_PIN or manifest["modes"]!=list(MODES):
   raise RuntimeError("SOLVER PIN OR FROZEN STRATEGIES DIFFER")
  if manifest["registry_sha256"]!=sha(REGISTRY):raise RuntimeError("INCONSISTENT HISTORY")
  if len(manifest["cases"])!=10:raise RuntimeError("INVALID CASES")
  for r in rows:
   if r["error"]:raise RuntimeError("Recorded incorrect solver outcome "+r["formula"])
   if r["category"]!=category or r["runner"]!=manifest["runner"]:raise RuntimeError("RUNNER OR SHARD ERROR")
  for t in trace:
   key=(t["category"],t["formula"],str(t["repeat"]),t["mode"])
   if key in alltraces:raise RuntimeError("DUPLICATE TRACE")
   alltraces[key]=t
  raw.extend(rows);manifests.append(manifest)
  sources.append(dict(category=category,measurements_sha256=sha(a),
    traces_sha256=sha(c),manifest_sha256=sha(b),
    commit=manifest["source_commit"],runner=manifest["runner"],
    binary_sha256=manifest["executables"],registry_sha256=manifest["registry_sha256"]))
 if len(raw)!=2880 or len(alltraces)!=2880:raise RuntimeError("MISSING FULL 2880 ATTEMPTS")
 groups=defaultdict(list)
 for r in raw:groups[(r["category"],r["formula"],r["repeat"])].append(r)
 if len(groups)!=360:raise RuntimeError("INCORRECT FORMULA-REPEAT COUNT")
 prefix_mismatches=[]
 for k,rs in groups.items():
  if len(rs)!=8 or len({x["mode"] for x in rs})!=8:raise RuntimeError("MISSING PAIRED MODE "+str(k))
  if len({x["formula_sha256"] for x in rs})!=1 or len({x["runner"] for x in rs})!=1:
   raise RuntimeError("UNPAIRED FORMULA/RUNNER "+str(k))
  if len({x["status"] for x in rs if x["status"] in ("SAT","UNSAT")})>1:
   raise RuntimeError("SAT/UNSAT DISAGREEMENT "+str(k))
  vals={r["mode"]:r for r in rs}
  tbase=alltraces[(*k,"monitor")]["points"]
  ref={int(t["conflict"]):t for t in tbase if int(t["conflict"])<=384}
  for mode in INTERVENTIONS:
   t=alltraces[(*k,mode)]["points"]
   candidate={int(v["conflict"]):v for v in t if int(v["conflict"])<=384}
   shared=set(ref)&set(candidate)
   for cp in shared:
    if any(ref[cp].get(p)!=candidate[cp].get(p) for p in ("restarts","decisions","propagations","learned","glue","stable")):
     prefix_mismatches.append({"formula":k,"mode":mode,"checkpoint":cp})
  for mode in INTERVENTIONS:
   if vals[mode]["status"]=="TIMEOUT" and vals[mode]["switch_at"]=="":
    raise RuntimeError("Expected intervention not applied for timeout case")
 if len(prefix_mismatches):raise RuntimeError("PREINTERVENTION PREFIX MISMATCH count="+str(len(prefix_mismatches))+" e.g "+str(prefix_mismatches[:2]))
 sha_id={r["formula_sha256"] for r in raw}
 if len(sha_id)!=120:raise RuntimeError("REPEATED CANONICAL FORMULA SHA")
 byformula=defaultdict(list)
 for r in raw:byformula[(r["category"],r["formula"])].append(r)
 features=[];paired=[];mode_sum=defaultdict(lambda:defaultdict(float));solved=Counter()
 for (cat,formula),rr in sorted(byformula.items()):
  per=defaultdict(list)
  for r in rr:per[r["mode"]].append(r)
  if any(len(per[m])!=3 for m in MODES):raise RuntimeError("PARTIAL PER-FORMULA REPEATS")
  sums={m:sum(float(r["par2_s"]) for r in per[m]) for m in MODES}
  first=rr[0]
  n=int(cat[1:4]);fold=first["fold"]
  tbase=[alltraces[(cat,formula,str(rep),"monitor")] for rep in range(3)]
  base_early=[t["early"] for t in tbase if t["early"]]
  feature={"shard":cat,"formula":formula,"formula_sha256":first["formula_sha256"],
    "n":n,"fold":fold,"seed":first["seed"],
    "degree_cv":float(first["degree_cv"]),"degree_gini":float(first["degree_gini"]),
    "polarity_imbalance":float(first["polarity_imbalance"]),
    "early_p":statistics.median(float(t["p"]) for t in base_early) if base_early else "",
    "early_g":statistics.median(float(t["g"]) for t in base_early) if base_early else "",
    "early_d":statistics.median(float(t["d"]) for t in base_early) if base_early else "",
    "early_r":statistics.median(float(t["r"]) for t in base_early) if base_early else "",
    **sums}
  features.append(feature)
  for m in MODES:
   mode_sum[fold][m]+=sums[m]
   solved[(fold,m)]+=sum(z["status"] in ("SAT","UNSAT") for z in per[m])
   if m=="monitor":continue
   speedup=sums["monitor"]/sums[m] if sums[m] else None
   paired.append({"shard":cat,"fold":fold,"formula":formula,
     "formula_sha256":first["formula_sha256"],"mode":m,
     "monitor_par2":sums["monitor"],"treatment_par2":sums[m],
     "speedup":speedup,"gain_percent":100*(sums["monitor"]-sums[m])/sums["monitor"],
     "wins":sum(float(per[m][j]["par2_s"])<float(per["monitor"][j]["par2_s"]) for j in range(3)),
     "switch_count":sum(bool(r["switch_at"]) for r in per[m]),
     "degree_cv":first["degree_cv"],"degree_gini":first["degree_gini"],
     "early_p":feature["early_p"]})
 out=OUT/"aggregate";out.mkdir(parents=True,exist_ok=True)
 for path,rows in ((out/"paired.csv",paired),(out/"formula_features.csv",features)):
  with path.open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 summary={}
 for fold in FOLDS:
  subset=[f for f in features if f["fold"]==fold]
  modes={}
  for m in MODES:
   base_total=mode_sum[fold]["monitor"];total=mode_sum[fold][m]
   related=[p for p in paired if p["mode"]==m and p["fold"]==fold]
   modes[m]={"par2_total":total,"gain_percent":100*(base_total-total)/base_total,
      "speedup":base_total/total if total else None,"solved":solved[(fold,m)],
      "formulas_gain_gt_50pct":sum(p["speedup"]>2 for p in related),
      "formulas_regression_gt_2x":sum(p["speedup"]<.5 for p in related),
      "ci95_formula_bootstrap":bootstrap(subset,m,310000+MODES.index(m)) if m!="monitor" else [0,0]}
  summary[fold]={"formulas":len(subset),"modes":modes}
 result={"status":"exploratory causal timing sweep, NOT an adaptive policy or proof",
    "run_attempts":len(raw),"formulas":len(features),"repeats":3,
    "strategies":MODES,"intervals":"512/1024/2048/4096 conflicts x restartint25; 2048 x restartint50",
    "report":summary,"prefix_mismatches":prefix_mismatches,
    "source_artifacts":sources,"manifests":manifests,
    "caution":"Synthetic prospective generated project test (not official). UNSAT has no independent certified proof for Kissat. Held-out R11 results cannot be reused to fit and validate a classifier."}
 dump(out/"results.json",result)
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in FOLDS:
   fig,ax=plt.subplots(figsize=(9,5))
   subset=[p for p in paired if p["fold"]==fold and p["mode"] in INTERVENTIONS and p["early_p"]!=""]
   for m in INTERVENTIONS:
    x=[p for p in subset if p["mode"]==m]
    if x:ax.scatter([float(p["early_p"]) for p in x],
      [math.log2(max(.01,p["speedup"])) for p in x],alpha=.45,label=m)
   ax.axhline(0,color="black",lw=0.7,linestyle="--")
   ax.set(xlabel="Monitor propagation/conflict at 512",ylabel="log2 speedup vs monitor",
     title="DRNAS R11 timing sweep – "+fold)
   ax.legend();fig.tight_layout();fig.savefig(out/("r11_scatter_"+fold+".png"),dpi=160);plt.close(fig)
 except ImportError:pass
 print("R11_COMPLETE",json.dumps({"attempts":len(raw),"formulas":len(features),
    "gains":{fold:{m:round(v["gain_percent"],3) for m,v in stats["modes"].items()} for fold,stats in summary.items()}}),flush=True)

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--category",choices=SHARDS)
 p.add_argument("--aggregate",action="store_true")
 args=p.parse_args()
 if args.category:shard_run(args.category)
 elif args.aggregate:aggregate()
 else:p.error("Choose --category or --aggregate")

if __name__=="__main__":main()
