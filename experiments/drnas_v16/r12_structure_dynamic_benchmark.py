#!/usr/bin/env python3
"""DRNAS R12 frozen candidate: real in-process Kissat structure+early-dynamics gates.
New generated instances. Frozen decision rule pre-committed. R11 is source/diagnostic only.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random,statistics
from collections import defaultdict,Counter
from pathlib import Path
import r11_restart_timing as r11

PIN=r11.PIN
STABLE_PIN=r11.STABLE_PIN
CAP=r11.CAP
REPEATS=3
NS=(200,220,240)
FOLDS=("development","test")
SHARDS=tuple(f"n{n}_{fold}{part}" for n in NS for fold in FOLDS for part in (0,1))
MODES=("monitor","r11_2048_25","r11_2048_50","r12_early",
       "r12_structure","r12_hybrid","r12_inverse","original_kissat","stable_v1531")
R12_MODES=("r12_early","r12_structure","r12_hybrid","r12_inverse")
OUT=Path("drnas-r12-results")
REGISTRY=Path("experiments/drnas_v16/r12_historical_sha256.txt")
RULE_PATH=Path("experiments/drnas_v16/r12_frozen_structure_early_rule.json")
SOURCE_R11="9d43502c39177f7650128cebc5a222681380e023"
FIELDS=r11.FIELDS+("static_pass","early_pass","expected_action","rule_path_sha256")
GATE_CV=0.265
GATE_P=43.0
GATE_G=0.95

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,obj):return r11.dump(path,obj)
def write_rows(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  writer.writeheader();writer.writerows(rows)
def feature_rule(cv,p,g):
 static=cv>=GATE_CV
 early=(p is not None and g is not None and p>0.0 and p<GATE_P and g<GATE_G)
 return bool(static),bool(early)
def selected(mode,static,early):
 return {"r12_hybrid":static and early,"r12_early":early,
         "r12_structure":static,"r12_inverse":early and not static}[mode]
def load_rule():
 rule=json.loads(RULE_PATH.read_text())
 if (rule["static_threshold_gte"]!=GATE_CV or
     rule["early_features"]["glue_ratio_lt"]!=GATE_G or
     rule["early_features"]["propagations_per_conflict_lt"]!=GATE_P or
     rule["action"]!={"conflict":2048,"restartint":25}):
  raise RuntimeError("FROZEN RULE FILE CHANGED")
 return rule
def make_cases(category,folder,registry):
 n=int(category[1:4]);fold="development" if "_development" in category else "test"
 part=int(category[-1]);cases=[]
 for j in range(10):
  # New deterministic seed stream, disjoint from R7/R10/R11.
  seed=411200000+n*10000+(0 if fold=="development" else 1000)+part*10+j
  rng=random.Random(seed)
  m=round(4.23*n)
  clauses=[]
  for _ in range(m):
   vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  f=r11.features(clauses,n)
  case=r11.base.emit_cnf(folder,f"r12_{n}_{fold}_{part}_{j:02d}.cnf",
    n,clauses,"UNKNOWN","generated_prospective",
    "DRNAS R12 fresh preregistered random-3SAT source","r12-dynamic-structural-v1",
    {"seed":seed,"fold":fold,"features":f})
  if case["formula_sha256"] in registry:
   raise RuntimeError("R12 SHA256 collision with historical formula: "+case["formula"])
  case["category"]=category
  cases.append(case)
 if len({c["formula_sha256"] for c in cases})!=10:
  raise RuntimeError("Repeated formula identity within shard")
 return cases
def run_one(case,rep,mode,runner):
 previous=os.environ.get("DRNAS_R12_DEGREE_CV")
 cv=case["metadata"]["features"]["degree_cv"]
 os.environ["DRNAS_R12_DEGREE_CV"]=format(cv,".17g")
 try: row,trace=r11.run_one(case,rep,mode,runner)
 finally:
  if previous is None:os.environ.pop("DRNAS_R12_DEGREE_CV",None)
  else:os.environ["DRNAS_R12_DEGREE_CV"]=previous
 early=trace["early"]
 p=float(early["p"]) if early and "p" in early else None
 g=float(early["g"]) if early and "g" in early else None
 static,early_pass=feature_rule(cv,p,g)
 row["static_pass"]=int(static)
 row["early_pass"]=int(early_pass)
 row["rule_path_sha256"]=sha(RULE_PATH)
 row["expected_action"]=""
 if mode in R12_MODES:
  choice=selected(mode,static,early_pass) if early else False
  row["expected_action"]="2048" if choice else "0"
  trace["expected_action"]=row["expected_action"]
  trace["r12_static_pass"]=int(static)
  trace["r12_early_pass"]=int(early_pass)
  if row["switch_at"]:
   if not choice or int(row["switch_at"])<2048 or int(row["restart_after"])!=25:
    row["error"]="R12 UNAUTHORIZED SWITCH against frozen decision"
  elif choice and row["status"]=="TIMEOUT":
   row["error"]="R12 SELECTED BUT TIMEOUT WITHOUT INTERVENTION"
  if not early and row["switch_at"]:
   row["error"]="R12 SWITCH WITHOUT ANY EARLY 512 TRACE"
 elif mode=="monitor" and row["switch_at"]:
  row["error"]="MONITOR ALTERED RESTARTS"
 return row,trace

def shard_run(category):
 rule=load_rule()
 core=r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 registry={x for x in REGISTRY.read_text().split() if len(x)==64 and all(c in "0123456789abcdef" for c in x)}
 if len(registry)<1530:raise RuntimeError("R12 historical registry is incomplete")
 cases=make_cases(category,folder,registry)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / pinned core "+str(core)+" / "+platform.processor()
 manifest={"category":category,"fold":cases[0]["metadata"]["fold"],
  "provenance":"new prospective generated random-3SAT, project holdout not official",
  "source_commit":os.environ.get("GITHUB_SHA","local"),
  "source_ref":SOURCE_R11,"kissat_pin":PIN,"stable_blob":STABLE_PIN,
  "runner":runner,"platform":platform.platform(),
  "cpu_core":core,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "cap_seconds":CAP,"repeats":REPEATS,"modes":MODES,
  "frozen_rule":rule,"frozen_rule_sha256":sha(RULE_PATH),
  "historical_registry_sha256":sha(REGISTRY),
  "executables":{"original_kissat":sha(r11.base.ORIGINAL),
    "same_binary_monitor_and_r12":sha(r11.base.PATCHED),"stable_v1531":sha(r11.base.STABLE)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v)
     for k,v in case.items() if k!="clauses"} for case in cases]}
 dump(folder/"manifest.json",manifest)
 rows=[];traces=[]
 for case in cases:
  for rep in range(REPEATS):
   order=list(MODES)
   random.Random(411200+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    row,trace=run_one(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R12_MEASURE",category,case["formula"],rep,mode,
     row["status"],row["par2_s"],"selected",row["expected_action"],
     "switch",row["switch_at"],flush=True)
    if row["error"]:
     dump(folder/"error.json",row)
     raise RuntimeError(row["error"])
  solved={r["status"] for r in rows if r["formula"]==case["formula"]
          and r["status"] in ("SAT","UNSAT")}
  if len(solved)>1:raise RuntimeError("CONTRADICTORY SAT/UNSAT across R12 modes: "+case["formula"])
 if len(rows)!=270 or len(traces)!=270:raise RuntimeError("Partial R12 benchmark shard")
 write_rows(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
 print("R12_SHARD_COMPLETE",category,len(rows),flush=True)

def quantile(values,p):
 if not values:return None
 values=sorted(values);v=(len(values)-1)*p;j=int(v)
 return values[j]*(1-(v-j))+values[min(j+1,len(values)-1)]*(v-j)
def formula_bootstrap(rows,mode,seed):
 rng=random.Random(seed);by=defaultdict(list)
 for r in rows:by[r["n"]].append(r)
 values=[]
 for _ in range(3500):
  sampled=[rng.choice(arr) for arr in by.values() for _ in arr]
  base=sum(x["monitor"] for x in sampled)
  treat=sum(x[mode] for x in sampled)
  values.append((base-treat)/base*100 if base else 0)
 return [quantile(values,.025),quantile(values,.975)]

def aggregate():
 rule=load_rule();rows=[];manifests=[];traces={}
 sources=[]
 for shard in SHARDS:
  folder=Path("r12-download")/("r12-"+shard)
  files=[folder/name for name in ("measurements.csv","manifest.json","traces.jsonl")]
  if not all(f.is_file() for f in files):raise RuntimeError("MISSING VERIFIED R12 SHARD "+shard)
  part=list(csv.DictReader(files[0].open()))
  meta=json.loads(files[1].read_text())
  ts=[json.loads(line) for line in files[2].read_text().splitlines()]
  if len(part)!=270 or len(ts)!=270:raise RuntimeError("INCOMPLETE MATRIX "+shard)
  if (meta["kissat_pin"]!=PIN or meta["stable_blob"]!=STABLE_PIN or
      meta["frozen_rule_sha256"]!=sha(RULE_PATH) or
      meta["historical_registry_sha256"]!=sha(REGISTRY) or
      meta["modes"]!=list(MODES) or len(meta["cases"])!=10):
   raise RuntimeError("R12 SOURCE/RULE/HISTORY PIN VIOLATION "+shard)
  for x in part:
   if x["category"]!=shard or x["runner"]!=meta["runner"] or x["error"]:
    raise RuntimeError("R12 ROW INCONSISTENCY "+str(x))
  for x in ts:
   key=(x["category"],x["formula"],str(x["repeat"]),x["mode"])
   if key in traces:raise RuntimeError("DUPLICATE TRACE")
   traces[key]=x
  sources.append({"shard":shard,"manifest_sha256":sha(files[1]),
    "measurements_sha256":sha(files[0]),"traces_sha256":sha(files[2]),
    "runner":meta["runner"],"source_commit":meta["source_commit"],
    "binary_sha256":meta["executables"],"historical_registry_sha256":meta["historical_registry_sha256"]})
  rows.extend(part);manifests.append(meta)
 if len(rows)!=3240 or len(traces)!=3240:raise RuntimeError("EXPECTED EXACTLY 3240 MEASUREMENTS")
 byattempt=defaultdict(dict)
 for x in rows:
  key=(x["category"],x["formula"],x["repeat"])
  if x["mode"] in byattempt[key]:raise RuntimeError("Duplicate solver mode in matched group")
  byattempt[key][x["mode"]]=x
 if len(byattempt)!=360:raise RuntimeError("EXPECTED 360 FORMULA/REPEAT PAIRS")
 mismatch=[]
 for key,groups in byattempt.items():
  if set(groups)!=set(MODES):raise RuntimeError("MISSING SOLVER IN PAIRED GROUP "+str(key))
  if len({r["runner"] for r in groups.values()})!=1:
   raise RuntimeError("PAIRED CPU RUNNER DIFFERENCE "+str(key))
  if len({r["formula_sha256"] for r in groups.values()})!=1:
   raise RuntimeError("UNPAIRED CANONICAL CNF HASH "+str(key))
  status={r["status"] for r in groups.values() if r["status"] in ("SAT","UNSAT")}
  if len(status)>1:raise RuntimeError("SAT/UNSAT CONTRADICTION "+str(key))
  initial={int(v["conflict"]):v for v in traces[(*key,"monitor")]["points"]
           if int(v["conflict"])<=384}
  for mode in ("r11_2048_25","r11_2048_50",*R12_MODES):
   other={int(v["conflict"]):v for v in traces[(*key,mode)]["points"]
          if int(v["conflict"])<=384}
   for cp in set(initial)&set(other):
    if any(initial[cp].get(z)!=other[cp].get(z)
       for z in ("restarts","decisions","propagations","learned","glue","stable")):
     mismatch.append((key,mode,cp))
  for mode in R12_MODES:
   entry=groups[mode];t=traces[(*key,mode)]
   trace_early=t["early"]
   static=entry["static_pass"]=="1"
   early=entry["early_pass"]=="1"
   recomputed=selected(mode,static,early) if trace_early else False
   if (entry["expected_action"]=="2048")!=recomputed:
    raise RuntimeError("R12 DECISION RECONSTRUCTION MISMATCH "+str(key))
   if entry["switch_at"] and not recomputed:
    raise RuntimeError("R12 ACTED WHEN FROZEN RULE SAYS ABSTAIN "+str(key))
 if mismatch:raise RuntimeError("R12 PREINTERVENTION PREFIX MISMATCH "+str(mismatch[:4]))
 if len({x["formula_sha256"] for x in rows})!=120:
  raise RuntimeError("FORMULA SHA256 DUPLICATES BETWEEN SHARDS")
 features=[];pairs=[];rawbyformula=defaultdict(list)
 for r in rows:rawbyformula[(r["category"],r["formula"])].append(r)
 for (shard,formula),rr in sorted(rawbyformula.items()):
  d=defaultdict(list)
  for x in rr:d[x["mode"]].append(x)
  if any(len(d[m])!=3 for m in MODES):raise RuntimeError("MISSING THREE PAIRED REPEATS")
  totals={m:sum(float(x["par2_s"]) for x in d[m]) for m in MODES}
  first=rr[0];n=int(shard[1:4]);fold=first["fold"]
  baseearly=[traces[(shard,formula,str(rep),"monitor")]["early"] for rep in range(3)]
  early=[x for x in baseearly if x]
  fs={"shard":shard,"formula":formula,"formula_sha256":first["formula_sha256"],
      "fold":fold,"n":n,"seed":first["seed"],
      "degree_cv":float(first["degree_cv"]),"degree_gini":float(first["degree_gini"]),
      "polarity_imbalance":float(first["polarity_imbalance"]),
      "early_p":statistics.median(float(x["p"]) for x in early) if early else "",
      "early_g":statistics.median(float(x["g"]) for x in early) if early else "",**totals}
  features.append(fs)
  for m in MODES:
   if m=="monitor":continue
   total=totals[m]
   pairs.append({"shard":shard,"fold":fold,"formula":formula,
    "formula_sha256":first["formula_sha256"],"mode":m,
    "monitor_par2":totals["monitor"],"treatment_par2":total,
    "speedup":totals["monitor"]/total if total else None,
    "gain_percent":(totals["monitor"]-total)/totals["monitor"]*100,
    "wins":sum(float(d[m][rep]["par2_s"])<float(d["monitor"][rep]["par2_s"]) for rep in range(3)),
    "action_count":sum(bool(x["switch_at"]) for x in d[m]),
    "declared_selection_count":sum(x["expected_action"]=="2048" for x in d[m]),
    "degree_cv":fs["degree_cv"],"degree_gini":fs["degree_gini"],"early_p":fs["early_p"]})
 out=OUT/"aggregate";out.mkdir(parents=True,exist_ok=True)
 for name,data in (("formula_features.csv",features),("paired.csv",pairs)):
  with (out/name).open("w",newline="") as f:
   writer=csv.DictWriter(f,fieldnames=list(data[0]))
   writer.writeheader();writer.writerows(data)
 summary={}
 for fold in FOLDS:
  subset=[x for x in features if x["fold"]==fold]
  totals={m:sum(x[m] for x in subset) for m in MODES}
  sm={}
  for m in MODES:
   pp=[p for p in pairs if p["fold"]==fold and p["mode"]==m]
   sm[m]={"total_par2_s":round(totals[m],6),
    "gain_percent":(totals["monitor"]-totals[m])/totals["monitor"]*100,
    "speedup":totals["monitor"]/totals[m] if totals[m] else None,
    "solved":sum(x["status"] in ("SAT","UNSAT") for x in rows if x["fold"]==fold and x["mode"]==m),
    "timeouts":sum(x["status"]=="TIMEOUT" for x in rows if x["fold"]==fold and x["mode"]==m),
    "gains_gt2x":sum(p["speedup"]>2 for p in pp),
    "regressions_gt2x":sum(p["speedup"]<.5 for p in pp),
    "selected_attempts":sum(p["declared_selection_count"] for p in pp),
    "switched_attempts":sum(p["action_count"] for p in pp),
    "bootstrap_95_formula_CI":formula_bootstrap(subset,m,411200+MODES.index(m)) if m!="monitor" else [0.,0.] }
  summary[fold]={"formulas":len(subset),"by_strategy":sm}
 result={"protocol":"R12 preregistered structure+early-dynamics gate, prospective new CNF",
   "run_attempts":len(rows),"formula_count":len(features),"repeats":REPEATS,
   "frozen_rule":rule,"frozen_rule_sha256":sha(RULE_PATH),
   "comparison_modes":MODES,"source_artifacts":sources,"manifests":manifests,
   "pre_intervention_counter_mismatch_count":len(mismatch),
   "report":summary,
   "limitations":"Synthetic random 3SAT at clause/variable ratio 4.23, not official. Kissat UNSAT lacks independent proofs. R11 train was exploratory; R12 is first new-frozen holdout; comparison to V15.3.1 uses a different architecture."}
 dump(out/"results.json",result)
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in FOLDS:
   sub=[x for x in features if x["fold"]==fold]
   fig,ax=plt.subplots(figsize=(9,5))
   for m in ("r12_hybrid","r12_early","r12_structure","r11_2048_25"):
    points=[(x["early_p"],math.log2(max(.005,x["monitor"]/x[m])))
            for x in sub if x["early_p"] not in ("",None)]
    if points:ax.scatter([p for p,_ in points],[v for _,v in points],
      alpha=.52,label=m)
   ax.axhline(0,color="black",lw=.7,ls="--")
   ax.set(xlabel="Early propagations/conflict at conflict 512",
          ylabel="log2 PAR-2 speedup vs monitor",
          title="R12 dynamic+structure vs control – "+fold)
   ax.legend();fig.tight_layout()
   fig.savefig(out/("scatter_r12_early_"+fold+".png"),dpi=150);plt.close(fig)
   fig,ax=plt.subplots(figsize=(9,5))
   for m in ("r12_hybrid","r12_early","r12_structure"):
    ax.scatter([x["degree_cv"] for x in sub],
       [math.log2(max(.005,x["monitor"]/x[m])) for x in sub],
       alpha=.52,label=m)
   ax.axhline(0,color="black",lw=.7,ls="--");ax.axvline(GATE_CV,color="grey",lw=.9,ls=":")
   ax.set(xlabel="Variable-degree coefficient of variation (from CNF)",
     ylabel="log2 PAR-2 speedup vs monitor",title="R12 CNF structure – "+fold)
   ax.legend();fig.tight_layout()
   fig.savefig(out/("scatter_r12_structure_"+fold+".png"),dpi=150);plt.close(fig)
 except ImportError:pass
 print("R12_AGGREGATE_COMPLETE",json.dumps({"attempts":len(rows),"formulas":len(features),
    "summary":{k:{m:round(x["gain_percent"],3) for m,x in v["by_strategy"].items()}
     for k,v in summary.items()}}),flush=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--category",choices=SHARDS)
 ap.add_argument("--aggregate",action="store_true");args=ap.parse_args()
 if args.category:shard_run(args.category)
 elif args.aggregate:aggregate()
 else:ap.error("Provide --category or --aggregate")
if __name__=="__main__":main()
