#!/usr/bin/env python3
"""DRNAS R13 frozen rescue gate on real in-process Kissat.
R12 R11 outcomes were exploratory; R13 formula stream is a new prospective test.
Frozen V15.3.1 and previous experimental source files are not modified.
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
MODES=("monitor","r11_2048_50","r11_2048_25",
       "r13_rescue50","r13_rescue25","r13_struct50","r13_inverse50",
       "r12_hybrid","original_kissat","stable_v1531")
R13_MODES=("r13_rescue50","r13_rescue25","r13_struct50","r13_inverse50")
OUT=Path("drnas-r13-results")
REGISTRY=Path("experiments/drnas_v16/r13_historical_sha256.txt")
RULE_PATH=Path("experiments/drnas_v16/r13_frozen_rescue_rule.json")
SOURCE_R12="123d90302524e067a0abb20b4ce7a2497230053d"
FIELDS=r11.FIELDS+("expected_action","rule_path_sha256","r13_choice_logged","r13_decision_n","r13_decision_p","r13_decision_g")
GATE_N_MIN=220
GATE_P_MAX=46.5
GATE_G=0.95
GATE_CV=0.27

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,obj):return r11.dump(path,obj)
def write_rows(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
  writer.writeheader();writer.writerows(rows)
def select_mode(mode,n,cv,p,g):
 if p is None or g is None:return False
 band=n>=GATE_N_MIN and p>0.0 and p<GATE_P_MAX
 hi=(g>=GATE_G)
 if mode=="r13_rescue50" or mode=="r13_rescue25":return band and hi
 if mode=="r13_struct50":return band and hi and cv>=GATE_CV
 if mode=="r13_inverse50":return band and not hi
 if mode=="r12_hybrid":return cv>=0.265 and p>0 and p<43 and g<0.95
 raise KeyError("Unknown gate: "+mode)
def target_interval(mode):
 return 25 if mode in ("r13_rescue25","r12_hybrid","r11_2048_25") else 50
def load_rule():
 rule=json.loads(RULE_PATH.read_text())
 d=rule["mode_definitions"]
 if (rule["protocol"]!="R13-frozen-rescue-v1-before-any-R13-benchmark"
     or rule["feature_measurement_at_conflicts"]!=512
     or rule["action_at_conflicts"]!=2048
     or len(d)!=4
     or not d["r13_rescue50"].startswith("n>=220 and 0 < p < 46.5 and g >= 0.95")):
  raise RuntimeError("R13 FROZEN RULE CHANGED")
 return rule
def make_cases(category,folder,registry):
 n=int(category[1:4]);fold="development" if "_development" in category else "test"
 part=int(category[-1]);cases=[]
 for j in range(10):
  # Independent R13 seed stream, disjoint from historical R7-R12 seeds.
  seed=513130000+n*10000+(0 if fold=="development" else 1000)+part*10+j
  rng=random.Random(seed)
  m=round(4.23*n)
  clauses=[]
  for _ in range(m):
   vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  f=r11.features(clauses,n)
  case=r11.base.emit_cnf(folder,f"r13_{n}_{fold}_{part}_{j:02d}.cnf",
    n,clauses,"UNKNOWN","generated_prospective",
    "DRNAS R13 prospectively frozen random-3SAT source","r13-rescue-missed-wins-v1",
    {"seed":seed,"fold":fold,"features":f})
  if case["formula_sha256"] in registry:
   raise RuntimeError("R13 SHA256 collision with historical formula: "+case["formula"])
  case["category"]=category
  cases.append(case)
 if len({c["formula_sha256"] for c in cases})!=10:
  raise RuntimeError("Repeated formula identity within shard")
 return cases
# R13 choice trace is carried as extra early telemetry, without mutating
# any imported V15.3.1/R11/R12 source file or solver decisions.
_ORIGINAL_EXTRACT=r11.base.extract_tags
def _extract_r13(output):
 points,labels=_ORIGINAL_EXTRACT(output)
 choices=[]
 for line in output.splitlines():
  if not line.startswith("c R13_CHOICE "):continue
  record={}
  for token in line.split()[2:]:
   if "=" in token:
    k,v=token.split("=",1)
    record[k]=v
  choices.append(record)
 if len(choices)>1:raise RuntimeError("DUPLICATE R13_CHOICE marker")
 if choices:
  labels.setdefault("DRNAS_V177_EARLY",{}).update({
   "r13_selected":choices[0].get("selected",""),
   "r13_interval":choices[0].get("interval",""),
   "r13_n":choices[0].get("n",""),
   "r13_target":choices[0].get("target",""),
   "r13_cv":choices[0].get("cv","")})
 return points,labels
r11.base.extract_tags=_extract_r13

def run_one(case,rep,mode,runner):
 cv=case["metadata"]["features"]["degree_cv"]
 old_cv=os.environ.get("DRNAS_R12_DEGREE_CV")
 old_n=os.environ.get("DRNAS_R13_N")
 os.environ["DRNAS_R12_DEGREE_CV"]=format(cv,".17g")
 os.environ["DRNAS_R13_N"]=str(case["n"])
 try:row,trace=r11.run_one(case,rep,mode,runner)
 finally:
  if old_cv is None:os.environ.pop("DRNAS_R12_DEGREE_CV",None)
  else:os.environ["DRNAS_R12_DEGREE_CV"]=old_cv
  if old_n is None:os.environ.pop("DRNAS_R13_N",None)
  else:os.environ["DRNAS_R13_N"]=old_n
 early=trace["early"]
 p=float(early["p"]) if early and "p" in early else None
 g=float(early["g"]) if early and "g" in early else None
 row["rule_path_sha256"]=sha(RULE_PATH)
 row["r13_choice_logged"]=early.get("r13_selected","") if early else ""
 row["r13_decision_n"]=early.get("r13_n","") if early else ""
 row["r13_decision_p"]=p if p is not None else ""
 row["r13_decision_g"]=g if g is not None else ""
 row["expected_action"]=""
 if mode in (*R13_MODES,"r12_hybrid"):
  chosen=select_mode(mode,case["n"],cv,p,g) if early else False
  row["expected_action"]="2048" if chosen else "0"
  trace["expected_action"]=row["expected_action"]
  trace["recomputed_selected"]=int(chosen)
  if mode in R13_MODES:
   if early and row["r13_choice_logged"]=="":
    row["error"]="R13 CHOICE MARKER MISSING"
   elif not early and row["r13_choice_logged"]:
    row["error"]="R13 CHOICE MARKER WITHOUT EARLY SAMPLE"
   elif early and (
       row["r13_choice_logged"]!=str(int(chosen))
       or row["r13_decision_n"]!=str(case["n"])
       or early.get("r13_target","")!=row["expected_action"]
       or int(early.get("r13_interval","0"))!=target_interval(mode)):
    row["error"]="R13 FROZEN IN-PROCESS CHOICE MISMATCH"
  if row["switch_at"]:
   if (not chosen or int(row["switch_at"])<2048
        or int(row["restart_after"])!=target_interval(mode)
        or row["learned_before"]!=row["learned_after"]):
    row["error"]="UNAUTHORIZED R13/R12 RESTART OR LEARNED CLAUSE MODIFICATION"
  elif chosen and row["status"]=="TIMEOUT":
   # Allowed if timer fired before 2048 conflicts; telemetry records it.
   trace["selected_unreached_timeout"]=True
 elif mode=="monitor" and row["switch_at"]:
  row["error"]="MONITOR ILLEGALLY SWITCHED"
 return row,trace

def shard_run(category):
 rule=load_rule()
 core=r11.set_cpu_affinity()
 folder=OUT/category;folder.mkdir(parents=True,exist_ok=True)
 registry={x for x in REGISTRY.read_text().split() if len(x)==64 and all(c in "0123456789abcdef" for c in x)}
 if len(registry)<1650:raise RuntimeError("R13 historical registry is incomplete")
 cases=make_cases(category,folder,registry)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / pinned core "+str(core)+" / "+platform.processor()
 manifest={"category":category,"fold":cases[0]["metadata"]["fold"],
  "provenance":"new prospective generated random-3SAT, project holdout not official",
  "source_commit":os.environ.get("GITHUB_SHA","local"),
  "source_ref":SOURCE_R12,"kissat_pin":PIN,"stable_blob":STABLE_PIN,
  "runner":runner,"platform":platform.platform(),
  "cpu_core":core,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "cap_seconds":CAP,"repeats":REPEATS,"modes":MODES,
  "frozen_rule":rule,"frozen_rule_sha256":sha(RULE_PATH),
  "historical_registry_sha256":sha(REGISTRY),
  "executables":{"original_kissat":sha(r11.base.ORIGINAL),
    "same_binary_monitor_and_r13":sha(r11.base.PATCHED),"stable_v1531":sha(r11.base.STABLE)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v)
     for k,v in case.items() if k!="clauses"} for case in cases]}
 dump(folder/"manifest.json",manifest)
 rows=[];traces=[]
 for case in cases:
  for rep in range(REPEATS):
   order=list(MODES)
   random.Random(513130+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    row,trace=run_one(case,rep,mode,runner)
    rows.append(row);traces.append(trace)
    write_rows(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as f:f.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R13_MEASURE",category,case["formula"],rep,mode,
     row["status"],row["par2_s"],"selected",row["expected_action"],
     "switch",row["switch_at"],flush=True)
    if row["error"]:
     dump(folder/"error.json",row)
     raise RuntimeError(row["error"])
  solved={r["status"] for r in rows if r["formula"]==case["formula"]
          and r["status"] in ("SAT","UNSAT")}
  if len(solved)>1:raise RuntimeError("CONTRADICTORY SAT/UNSAT across R13 modes: "+case["formula"])
 if len(rows)!=300 or len(traces)!=300:raise RuntimeError("Partial R13 benchmark shard")
 write_rows(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
 print("R13_SHARD_COMPLETE",category,len(rows),flush=True)

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
  folder=Path("r13-download")/("r13-"+shard)
  files=[folder/name for name in ("measurements.csv","manifest.json","traces.jsonl")]
  if not all(f.is_file() for f in files):raise RuntimeError("MISSING VERIFIED R12 SHARD "+shard)
  part=list(csv.DictReader(files[0].open()))
  meta=json.loads(files[1].read_text())
  ts=[json.loads(line) for line in files[2].read_text().splitlines()]
  if len(part)!=300 or len(ts)!=300:raise RuntimeError("INCOMPLETE MATRIX "+shard)
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
 if len(rows)!=3600 or len(traces)!=3600:raise RuntimeError("EXPECTED EXACTLY 3600 MEASUREMENTS")
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
  for mode in ("r11_2048_25","r11_2048_50","r12_hybrid",*R13_MODES):
   other={int(v["conflict"]):v for v in traces[(*key,mode)]["points"]
          if int(v["conflict"])<=384}
   for cp in set(initial)&set(other):
    if any(initial[cp].get(z)!=other[cp].get(z)
       for z in ("restarts","decisions","propagations","learned","glue","stable")):
     mismatch.append((key,mode,cp))
  for mode in (*R13_MODES,"r12_hybrid"):
   entry=groups[mode]
   trace=traces[(*key,mode)]
   early=trace["early"]
   cv=float(entry["degree_cv"])
   p=float(early["p"]) if early and "p" in early else None
   g=float(early["g"]) if early and "g" in early else None
   n=int(entry["category"][1:4])
   predicted=select_mode(mode,n,cv,p,g) if early else False
   if (entry["expected_action"]=="2048")!=predicted:
    raise RuntimeError("R13 FROZEN CHOICE RECONSTRUCTION ERROR "+str(key))
   if mode in R13_MODES and early and entry["r13_choice_logged"]!=str(int(predicted)):
    raise RuntimeError("R13 C/PY DECISION LOG DISAGREEMENT "+str(key))
   if entry["switch_at"] and not predicted:
    raise RuntimeError("R13 SWITCH WHEN EXPECTED ABSTAIN "+str(key))
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
 result={"protocol":"R13 preregistered rescue50 high-glue gate, prospective fresh 3-CNF",
   "run_attempts":len(rows),"formula_count":len(features),"repeats":REPEATS,
   "frozen_rule":rule,"frozen_rule_sha256":sha(RULE_PATH),
   "comparison_modes":MODES,"source_artifacts":sources,"manifests":manifests,
   "pre_intervention_counter_mismatch_count":len(mismatch),
   "report":summary,
   "limitations":"Synthetic prospective random 3SAT, not official. Kissat UNSAT lacks independent independent certificates. R12 test now used to design R13 so R12 is exploratory only; R13 is a newly frozen validation. V15.3.1 is a separate architecture."}
 dump(out/"results.json",result)
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in FOLDS:
   sub=[x for x in features if x["fold"]==fold]
   fig,ax=plt.subplots(figsize=(9,5))
   for m in ("r13_rescue50","r13_rescue25","r13_struct50","r13_inverse50","r11_2048_50"):
    points=[(x["early_p"],math.log2(max(.005,x["monitor"]/x[m])))
            for x in sub if x["early_p"] not in ("",None)]
    if points:ax.scatter([p for p,_ in points],[v for _,v in points],
      alpha=.52,label=m)
   ax.axhline(0,color="black",lw=.7,ls="--")
   ax.set(xlabel="Early propagations/conflict at conflict 512",
          ylabel="log2 PAR-2 speedup vs monitor",
          title="R13 rescue early dynamics vs controls – "+fold)
   ax.legend();fig.tight_layout()
   fig.savefig(out/("scatter_r13_early_"+fold+".png"),dpi=150);plt.close(fig)
   fig,ax=plt.subplots(figsize=(9,5))
   for m in ("r13_rescue50","r13_struct50","r13_inverse50","r12_hybrid"):
    ax.scatter([x["degree_cv"] for x in sub],
       [math.log2(max(.005,x["monitor"]/x[m])) for x in sub],
       alpha=.52,label=m)
   ax.axhline(0,color="black",lw=.7,ls="--");ax.axvline(GATE_CV,color="grey",lw=.9,ls=":")
   ax.set(xlabel="Variable-degree coefficient of variation (from CNF)",
     ylabel="log2 PAR-2 speedup vs monitor",title="R13 CNF structure – "+fold)
   ax.legend();fig.tight_layout()
   fig.savefig(out/("scatter_r13_structure_"+fold+".png"),dpi=150);plt.close(fig)
 except ImportError:pass
 print("R13_AGGREGATE_COMPLETE",json.dumps({"attempts":len(rows),"formulas":len(features),
    "summary":{k:{m:round(x["gain_percent"],3) for m,x in v["by_strategy"].items()}
     for k,v in summary.items()}}),flush=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument("--category",choices=SHARDS)
 ap.add_argument("--aggregate",action="store_true");args=ap.parse_args()
 if args.category:shard_run(args.category)
 elif args.aggregate:aggregate()
 else:ap.error("Provide --category or --aggregate")
if __name__=="__main__":main()
