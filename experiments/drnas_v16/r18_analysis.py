#!/usr/bin/env python3
"""R18 strictly audited true in-process prospective SAT benchmark aggregation.

Only finished 16x270 native attempts can yield results.json. C/Python predictor
parity, 1024-prefix equality, formula/runner/bin SHA and witness checks required.
"""
from __future__ import annotations
import csv,hashlib,json,math,random,statistics
from collections import defaultdict
from pathlib import Path
import r18_benchmark as bench

INPUT=Path("r18-download")
OUT=bench.OUT/"aggregate"
FOLDS=("random3_development","random3_test","community3_development","community3_test")
MODES=bench.MODES
R18_MODES=bench.R18_MODES
PREFIX_MODES=("r11_2048_50","r16_live50","r17_risk30","r17_risk45","r18_lcb","r18_mean")
def digest(x):return bench.sha(x)
def savejson(p,v):p.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n")
def savecsv(p,items):
 if not items:return
 with p.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(items[0]))
  w.writeheader();w.writerows(items)
def pct(vals,p):
 s=sorted(vals);v=(len(s)-1)*p;i=int(v)
 return s[i]*(1-(v-i))+s[min(i+1,len(s)-1)]*(v-i)
def bootstrap(rows,mode,seed):
 rng=random.Random(seed)
 strata=defaultdict(list)
 for x in rows:strata[int(x["n"])].append(x)
 samples=[]
 for _ in range(3500):
  picked=[rng.choice(g) for n,g in sorted(strata.items()) for i in range(len(g))]
  mon=sum(x["monitor"] for x in picked)
  arm=sum(x[mode] for x in picked)
  samples.append(100*(mon-arm)/mon)
 return [pct(samples,.025),pct(samples,.975)]

def load():
 cfg,m=bench.load()
 historic=bench.history()
 raw=[];traces={};manifests=[];source=[]
 for category in bench.SHARDS:
  folder=INPUT/("r18-"+category)
  a,b,c=[folder/x for x in ("measurements.csv","traces.jsonl","manifest.json")]
  if not all(p.is_file() for p in (a,b,c)):
   raise RuntimeError("R18 MISSING COMPLETE RAW SHARD "+category)
  ms=list(csv.DictReader(a.open()))
  events=[json.loads(x) for x in b.read_text().splitlines()]
  manifest=json.loads(c.read_text())
  if len(ms)!=270 or len(events)!=270 or len(manifest["cases"])!=10:
   raise RuntimeError("R18 SHARD INCOMPLETE "+category)
  if (manifest["category"]!=category or
      manifest["protocol"]!=cfg["protocol"] or
      list(manifest["modes"])!=list(MODES) or
      manifest["repeats"]!=3 or manifest["cap_seconds"]!=12 or
      manifest["model_sha256"]!=digest(bench.MODEL) or
      manifest["protocol_sha256"]!=digest(bench.CONFIG) or
      manifest["kissat_pin"]!=bench.previous.r16.PIN or
      manifest["stable_blob"]!=bench.previous.r16.STABLE_PIN or
      manifest["cpu_affinity"]!=[manifest["cpu_core"]] or
      manifest["history_sha256"]!=hashlib.sha256(
         "\n".join(sorted(historic)).encode()).hexdigest()):
   raise RuntimeError("R18 SOURCE/MODEL/CPU/SEED PROVENANCE ERROR "+category)
  bycase={case["formula"]:case for case in manifest["cases"]}
  if len(bycase)!=10:raise RuntimeError("R18 DUPLICATE SHARD FORMULA")
  for x in ms:
   if x["error"] or x["r18_error"] or x["r16_decision_error"]:
    raise RuntimeError("R18 SOLVER/DECISION INVALID "+str(x))
   if x["formula"] not in bycase or x["formula_sha256"]!=bycase[x["formula"]]["formula_sha256"]:
    raise RuntimeError("R18 FORMULA SHA OR NAME DOES NOT MATCH")
   if (x["seed"]!=str(bycase[x["formula"]]["metadata"]["seed"]) or
       x["runner"]!=manifest["runner"] or
       x["r18_model_sha256"]!=digest(bench.MODEL) or
       x["r18_protocol_sha256"]!=digest(bench.CONFIG)):
    raise RuntimeError("R18 REPEAT/EXECUTABLE SOURCE/SEED PROVENANCE WRONG")
   if x["status"] not in ("SAT","UNSAT","TIMEOUT"):
    raise RuntimeError("R18 SOLVER RETURNED INVALID STATUS "+str(x))
   if x["status"]=="SAT" and x["sat_model_checked"]!="True":
    raise RuntimeError("R18 SAT MODEL WITNESS INVALID/UNVERIFIED")
   if x["status"]=="TIMEOUT":
    if abs(float(x["par2_s"])-24)>1e-6:
     raise RuntimeError("R18 PAR2 TIMEOUT PENALTY NOT 24s")
   elif abs(float(x["par2_s"])-float(x["wall_s"]))>1e-5:
    raise RuntimeError("R18 SOLVED PAR2 DID NOT USE REAL WALL TIME")
   if x["mode"] in R18_MODES and x["r18_native_mean"]:
    for cval,pyval in (("r18_native_mean","r18_python_mean"),
                       ("r18_native_sigma","r18_python_sigma"),
                       ("r18_native_lower","r18_python_lower")):
     if abs(float(x[cval])-float(x[pyval]))>2e-5:
      raise RuntimeError("R18 C/PYTHON PREDICTIVE MEAN/SIGMA PARITY WRONG")
  for event in events:
   key=(event["category"],event["formula"],str(event["repeat"]),event["mode"])
   if key in traces:raise RuntimeError("R18 DUPLICATED TRACE")
   traces[key]=event
  raw.extend(ms)
  manifests.append(manifest)
  source.append({"category":category,"source_commit":manifest["source_commit"],
     "runner":manifest["runner"],"cpu_core":manifest["cpu_core"],
     "measurements_sha256":digest(a),"traces_sha256":digest(b),
     "manifest_sha256":digest(c),"binary_sha256":manifest["executables"],
     "frozen_model_sha256":manifest["model_sha256"]})
 if len(raw)!=4320 or len(traces)!=4320:
  raise RuntimeError("R18 4320 REAL MEASUREMENTS/TRACE CHECK FAILED")
 ids={x["formula_sha256"] for x in raw}
 if len(ids)!=160 or ids & historic:
  raise RuntimeError("R18 FORMULA SHA REUSED OR DID NOT HAVE 160 UNIQUE")
 groups=defaultdict(dict)
 for x in raw:
  k=(x["category"],x["formula"],x["repeat"])
  if x["mode"] in groups[k]:raise RuntimeError("R18 DUPLICATE ARM FOR REPEAT")
  groups[k][x["mode"]]=x
 if len(groups)!=480:raise RuntimeError("R18 EXPECTED 480 PAIRED FORMULA REPEATS")
 for key,group in groups.items():
  if set(group)!=set(MODES):raise RuntimeError("R18 MISSING COMPARATOR")
  if len({x["runner"] for x in group.values()})!=1:
   raise RuntimeError("R18 PAIRS NOT ON SAME RUNNER")
  if len({x["formula_sha256"] for x in group.values()})!=1:
   raise RuntimeError("R18 PAIRS NOT IDENTICAL CNF")
  final={x["status"] for x in group.values() if x["status"] in ("SAT","UNSAT")}
  if len(final)>1:raise RuntimeError("R18 CONTRADICTORY SAT/UNSAT")
  baseline={int(p["conflict"]):p for p in traces[(*key,"monitor")]["points"]
            if int(p["conflict"])<=1024}
  for arm in PREFIX_MODES:
   cand={int(p["conflict"]):p for p in traces[(*key,arm)]["points"]
         if int(p["conflict"])<=1024}
   if set(baseline)!=set(cand):
    raise RuntimeError("R18 EARLY PREFIX CHECKPOINTS DISAGREE "+str(key)+arm)
   for cp in baseline:
    if any(baseline[cp].get(f)!=cand[cp].get(f)
         for f in ("restarts","decisions","propagations","learned","glue","stable")):
     raise RuntimeError("R18 FROZEN PREINTERVENTION DYNAMICS CHANGED "+str(key))
 return cfg,m,raw,traces,groups,source,manifests

def aggregate():
 cfg,m,raw,traces,groups,source,manifests=load()
 OUT.mkdir(parents=True,exist_ok=True)
 rows=defaultdict(lambda:defaultdict(list))
 for x in raw:rows[(x["category"],x["formula"])][x["mode"]].append(x)
 if len(rows)!=160:raise RuntimeError("R18 WRONG FORMULA COUNT")
 formulas=[];paired=[];decisions=[]
 for (category,formula),arms in sorted(rows.items()):
  if any(len(arms[a])!=3 for a in MODES):
   raise RuntimeError("R18 THREE REPEATS REQUIRED ON ALL ARMS")
  rep=arms["monitor"][0]
  totals={a:sum(float(x["par2_s"]) for x in arms[a]) for a in MODES}
  line={"category":category,"formula":formula,
        "formula_sha256":rep["formula_sha256"],"seed":rep["seed"],
        "fold":rep["fold"],
        "family":bench.previous.r16.previous.r14.family_from_category(category),
        "n":bench.previous.r16.previous.r14.size_from_category(category),
        "degree_cv":float(rep["degree_cv"]),
        "degree_gini":float(rep["degree_gini"]),
        "polarity_imbalance":float(rep["polarity_imbalance"]),
        **totals}
  for arm in R18_MODES:
   events=[x for x in arms[arm] if x["r18_native_mean"]]
   line[arm+"_mean"]=statistics.median(float(x["r18_native_mean"]) for x in events) if events else ""
   line[arm+"_sigma"]=statistics.median(float(x["r18_native_sigma"]) for x in events) if events else ""
   line[arm+"_selected_count"]=sum(x["r18_selected"]=="1" for x in arms[arm])
   line[arm+"_switch_count"]=sum(bool(x["switch_at"]) for x in arms[arm])
  formulas.append(line)
  for arm in MODES:
   if arm=="monitor":continue
   paired.append({
    "category":category,"fold":rep["fold"],"formula":formula,
    "formula_sha256":rep["formula_sha256"],"n":line["n"],"mode":arm,
    "monitor_par2_s":totals["monitor"],"treatment_par2_s":totals[arm],
    "gain_percent":100*(totals["monitor"]-totals[arm])/totals["monitor"],
    "speedup":totals["monitor"]/totals[arm],
    "gain_gt2x":totals["monitor"]>2*totals[arm],
    "regression_gt2x":totals[arm]>2*totals["monitor"],
    "native_switches":sum(bool(x["switch_at"]) for x in arms[arm])})
  for arm in R18_MODES:
   for x in arms[arm]:
    decisions.append({
     "category":category,"fold":rep["fold"],"formula":formula,"repeat":x["repeat"],
     "mode":arm,"mean_native":x["r18_native_mean"],
     "mean_independent_python":x["r18_python_mean"],
     "sigma_native":x["r18_native_sigma"],
     "sigma_independent_python":x["r18_python_sigma"],
     "lower_native":x["r18_native_lower"],
     "lower_independent_python":x["r18_python_lower"],
     "selected":x["r18_selected"],"actual_switch_at":x["switch_at"],
     "par2_s":x["par2_s"],"status":x["status"]})
 if len(formulas)!=160 or len(paired)!=1280 or len(decisions)!=960:
  raise RuntimeError("R18 FINAL DIMS INCORRECT")
 folds={}
 for index,fold in enumerate(FOLDS):
  sub=[x for x in formulas if x["fold"]==fold]
  if len(sub)!=(60 if fold.startswith("random3") else 20):
   raise RuntimeError("R18 WRONG FOLD FORMULA N")
  base=sum(x["monitor"] for x in sub)
  stats={}
  for arm in MODES:
   total=sum(x[arm] for x in sub)
   pm=[r for r in paired if r["fold"]==fold and r["mode"]==arm]
   stats[arm]={
    "par2_s":round(total,6),
    "gain_percent_vs_monitor":100*(base-total)/base,
    "formula_stratified_bootstrap_95_ci":bootstrap(sub,arm,181800+index*100+MODES.index(arm))
       if arm!="monitor" else [0.,0.],
    "gain_gt2x":sum(x["gain_gt2x"] for x in pm),
    "regression_gt2x":sum(x["regression_gt2x"] for x in pm),
    "selected_attempts":sum(x[arm+"_selected_count"] for x in sub) if arm in R18_MODES else None,
    "actual_switches":sum(x[arm+"_switch_count"] for x in sub) if arm in R18_MODES else None,
    "formulas_with_switch":sum(x[arm+"_switch_count"]>0 for x in sub) if arm in R18_MODES else None}
  for arm in R18_MODES:
   stats[arm]["gain_vs_r16_live50_pct"]=100*(
       sum(x["r16_live50"] for x in sub)-sum(x[arm] for x in sub)
      )/sum(x["r16_live50"] for x in sub)
  folds[fold]={"formulas":len(sub),"modes":stats}
 report={
  "protocol":cfg["protocol"],
  "status":"R18_TRUE_PROSPECTIVE_NATIVE_FROZEN_DIRECT_EFFECT_UNCERTAINTY_NOT_REPLAY",
  "attempts":4320,"formulas":160,"repeats":3,"arms":list(MODES),
  "model_sha256":digest(bench.MODEL),
  "protocol_sha256":digest(bench.CONFIG),
  "frozen_training":"R17 random3_development, 40 eligible CNF; no test labels",
  "preintervention_mismatches":0,"historical_formula_collisions":0,
  "source_artifacts":source,"manifests":manifests,"folds":folds,
  "limitations":[
    "Generated Random3/Community3 only; not official SAT benchmarks",
    "R18 residual uncertainty bound is a heuristic, NOT calibrated confidence interval",
    "No independent UNSAT certificate verification; SAT model witnesses checked",
    "Intervention only one native restartint=50 update at 2048 conflicts, no process reboot",
    "Any R18 results become retrospective for future tuning",
    "Statistical bootstrap by FORMULA, not independent correlated repeated executions",
    "All policies on same formula/runner; original Kissat/V15.3.1 built separately"
  ]}
 savejson(OUT/"results.json",report)
 savecsv(OUT/"formula_features.csv",formulas)
 savecsv(OUT/"paired.csv",paired)
 savecsv(OUT/"native_decisions.csv",decisions)
 (OUT/"netbenefit_model.json").write_bytes(bench.MODEL.read_bytes())
 (OUT/"model_audit.json").write_bytes((bench.MODEL.parent/"model_audit.json").read_bytes())
 lines=["# DRNAS R18 — frozen paired-time prediction with uncertainty",
        "","Real native in-process R18 LCB and mean-only. No replay, no model tuning.",
        "","| Fold | Mode | PAR-2 (s) | Δ vs monitor | 95% formula-bootstrap CI | Native actions | Regressions >2× |",
        "|---|---|---:|---:|---|---:|---:|"]
 for fold in FOLDS:
  for arm in MODES:
   stats=folds[fold]["modes"][arm]
   lines.append(f"| {fold} | {arm} | {stats['par2_s']:.5f} | "+
      f"{stats['gain_percent_vs_monitor']:+.3f}% | {stats['formula_stratified_bootstrap_95_ci']} | "+
      f"{stats['actual_switches']} | {stats['regression_gt2x']} |")
 lines+=["","R18 LCB bound is a heuristic decision margin, not a mathematical confidence bound.",
         "Primary R18-LCB compared against same-binary monitor on untouched random3_test.",
         "All folds are newly generated, not SAT competition official formulas.",
         "SAT models checked; no independent UNSAT certificate verified."]
 (OUT/"README.md").write_text("\n".join(lines)+"\n")
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in ("random3_test","community3_test"):
   subset=[r for r in formulas if r["fold"]==fold and r["r18_lcb_mean"]!=""]
   fig,ax=plt.subplots(figsize=(8,5))
   ax.scatter([float(x["r18_lcb_mean"]) for x in subset],
      [math.log2(x["monitor"]/x["r11_2048_50"]) for x in subset],alpha=.7)
   ax.axvline(.05,ls="--",lw=1)
   ax.axhline(0,ls="--",lw=1)
   ax.set(xlabel="R18 predicted log(Monitor / Forced50) at conflict 1024",
     ylabel="Measured log2(Monitor / Forced50) PAR-2",
     title="R18 prospective direct effect — "+fold)
   fig.tight_layout()
   fig.savefig(OUT/("scatter_gain_"+fold+".png"),dpi=150)
   plt.close(fig)
 except ImportError:pass
 print("R18_FULL_NATIVE_ANALYSIS_COMPLETE",json.dumps({
  "attempts":len(raw),"CNF":len(formulas),
  "primary":{k:{"par2_s":v["par2_s"],"gain_pct":v["gain_percent_vs_monitor"],
      "ci":v["formula_stratified_bootstrap_95_ci"],
      "actions":v["actual_switches"],"regress_2x":v["regression_gt2x"]}
     for k,v in folds["random3_test"]["modes"].items()}},sort_keys=True),flush=True)

if __name__=="__main__":aggregate()
