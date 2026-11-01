#!/usr/bin/env python3
"""Preregistered, READ-ONLY cross-family hardness transfer test for DRNAS SAT.

No V15.3.1 rebuild or policy changes; original pinned Kissat only.
All source SHA-1 hashes, SHA-256 normalized formulas, structural features and
selection identities are recorded before ANY outcome or timing is observed.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, math, os, platform
import random, statistics, subprocess, tarfile, tempfile, time
from pathlib import Path
import v1531_satlib as satlib
import v1531_structural_fingerprints as structure

ROOT=Path("crossfamily-validation")
CONFIG=Path("research/tseitin-replay/v1531_crossfamily_preregister.json")
MEDIUM=Path("research/sat-analytics-data/medium40/results.json")
SHORT=Path("research/sat-analytics-data/short40/results.json")
TRIALS=5000
FEATURES=("degree_gini","degree_cv","reused_varpair_fraction")

def sha(x):return hashlib.sha256(x).hexdigest()
def outjson(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def index_by_name(entries):
 ret={}
 for member in entries:
  name=Path(member.name).name
  if name in ret:raise RuntimeError("Ambiguous source basename "+name)
  ret[name]=member
 return ret
def ingest_inputs(category):
 config=json.loads(CONFIG.read_text())
 families={f["category"]:f for f in config["test_families"]}
 if category not in families:raise ValueError("Unknown category "+category)
 f=families[category]; p=Path("/tmp")/(category+".tar.gz")
 archive=p.read_bytes()
 if hashlib.sha1(archive).hexdigest()!=f["sha1"]:raise ValueError("Pinned SATLIB archive SHA1 mismatch")
 if config["per_family_cases"]!=40 or config["repeats"]!=2 or config["time_limit_sec"]!=5.3:
  raise RuntimeError("Frozen configuration changed")
 previous=json.loads(MEDIUM.read_text())
 by_cat=previous["all_calibration_records"]
 if category=="flat200-479":
  old=set()
 else:
  pilot=by_cat[category]
  if len(pilot)!=60:raise RuntimeError("Original pilot not exactly 60")
  old={Path(x["source_path"]).name for x in pilot}
  if len(old)!=60:raise RuntimeError("Duplicate original pilot filenames")
 oldhashes={x["sha256_normalized"] for y in by_cat.values() for x in y
             if x.get("sha256_normalized")}
 short=json.loads(SHORT.read_text())
 oldhashes.update(x["sha256_normalized"] for x in short["manifest"])
 oldvalidation=Path("research/sat-analytics-data/relations-validation/results.json")
 if oldvalidation.exists():
  y=json.loads(oldvalidation.read_text())
  oldhashes.update(x["sha256_normalized"] for x in y["manifest"])
 out=ROOT/category
 (out/"inputs").mkdir(parents=True,exist_ok=True)
 with tarfile.open(p,"r:gz") as tf:
  members=[m for m in tf.getmembers() if m.isfile() and m.name.lower().endswith(".cnf")]
  if any(m.name.startswith("/") or ".." in Path(m.name).parts for m in members):
   raise RuntimeError("Unsafe SATLIB source archive paths")
  names=index_by_name(members)
  if len(names)!=100:raise RuntimeError("Expected exact 100 source CNFs, got "+str(len(names)))
  if category=="flat200-479":
   rng=random.Random(config["graph_filename_selection_seed"])
   candidates=sorted(names)
   rng.shuffle(candidates)
   chosen=sorted(candidates[:40])
  else:chosen=sorted(set(names)-old)
  if len(chosen)!=40:raise RuntimeError("Frozen holdout is not 40 files")
  seen=set()
  manifest=[]
  with tempfile.TemporaryDirectory() as folder:
   tmp=Path(folder)/"original.cnf"
   for i,name in enumerate(chosen):
    member=names[name]
    stream=tf.extractfile(member)
    if stream is None:raise RuntimeError("Missing archive member stream")
    raw=stream.read()
    tmp.write_bytes(raw)
    got,clean,n,clauses,trailer=satlib.normalize_satlib(tmp)
    if got!=raw:raise RuntimeError("Original DIMACS drift")
    h=sha(clean)
    if h in seen or h in oldhashes:raise RuntimeError("Duplicate/previously used normalized SHA256 "+name)
    seen.add(h)
    if (category=="flat200-479" and (n!=600 or len(clauses)!=2237)) or (
          category!="flat200-479" and (n!=int(category[category.index("200"):category.index("200")+3]) if "200" in category else False)):
     # Do not select/tune on n and m; validated by the SATLIB parser.
     raise RuntimeError("Unexpected pinned source dimensions")
    case=f"{category}_xf_{i:02d}.cnf"
    (out/"inputs"/case).write_bytes(clean)
    manifest.append({"id":case,"source":member.name,"source_archive_sha1":f["sha1"],
        "sha256_source":sha(raw),"sha256_normalized":h,
        "n":n,"clauses":len(clauses),"expected":f["expected"],"family":category,
        "trailer_removed":trailer,
        "structural_features":structure.features(n,clauses)})
 froze={"frozen_before_solver_execution":True,"selection_rule":f["selection"],
   "source_archive_url":"https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/"+f["archive_path"],
   "source_archive_sha1":f["sha1"],"source_archive_sha256":sha(archive),
   "preregistration_sha256":sha(CONFIG.read_bytes()),
   "previous_training_run":config["observed_training_run"],
   "previous_confirmation_run":config["observed_untouched_confirmation_run"],
   "category":category,"selected_names":chosen,"previous_pilot_names":sorted(old),
   "manifest":manifest}
 manifest_sha=sha(json.dumps(manifest,sort_keys=True).encode())
 froze["manifest_sha256"]=manifest_sha
 outjson(out/"manifest_frozen_before_timing.json",froze)
 print("CROSSFAMILY_FREEZE",category,"formulae",len(chosen),
       "manifest_sha256",manifest_sha,flush=True)
 return f,manifest,out,manifest_sha

def run_family(category):
 f,manifest,out,h=ingest_inputs(category)
 if not satlib.SOLVERS["kissat"].is_file():raise RuntimeError("Pinned original Kissat binary missing")
 satlib.TIMEOUT=5.3
 rng=random.Random(743175+list(json.loads(CONFIG.read_text())["test_families"]).index(f))
 tasks=[(rec,rep) for rec in manifest for rep in range(2)]
 rng.shuffle(tasks)
 data=collections.defaultdict(list)
 for step,(rec,rep) in enumerate(tasks,1):
  path=out/"inputs"/rec["id"]
  _,_,n,clauses,_=satlib.normalize_satlib(path)
  case={"file":path,"expected":rec["expected"],"n":n,"clauses":clauses}
  result=satlib.run("kissat",satlib.SOLVERS["kissat"],case)
  result["rep"]=rep
  data[rec["id"]].append(result)
  # The same manifest and all partial attempts survive unexpected interruption.
  outjson(out/"attempts.partial.json",{"manifest_sha256":h,"attempts":data,"progress":step})
  print("CROSSFAMILY_MEASURE",category,step,"/",len(tasks),rec["id"],
     rep,result["status"],f"{result['seconds']:.5f}",
     "correct",bool(result["correct"]),flush=True)
 rows=[]
 for rec in manifest:
  attempts=sorted(data[rec["id"]],key=lambda x:x["rep"])
  if len(attempts)!=2:raise RuntimeError("Missing repetitions for "+rec["id"])
  rows.append({"case":rec["id"],"family":category,"expected":rec["expected"],
    "solver":"kissat","correct":all(y["correct"] for y in attempts),
    "median_seconds":statistics.median(y["seconds"] for y in attempts),
    "runs":attempts})
 dataset={"dataset_meta":{"dataset":"DRNAS-V1531-CrossFamily-"+category,
     "provenance":"preregistered_crossfamily_transfer",
     "benchmark":"External public SATLIB real CNF; untouched for this structural study; original Kissat only",
     "source_run":os.environ.get("GITHUB_RUN_ID",""),
     "source_sha":os.environ.get("GITHUB_SHA",""),
     "runner":os.environ.get("RUNNER_NAME","unknown")},
   "source":"SATLIB original / UBC",
   "source_archive_sha1":f["sha1"],"source_archive_sha256":out and
      json.loads((out/"manifest_frozen_before_timing.json").read_text())["source_archive_sha256"],
   "selection_manifest_sha256":h,"preregistration_sha256":sha(CONFIG.read_bytes()),
   "timeout_seconds":5.3,"repetitions":2,"manifest":manifest,"results":rows}
 outjson(out/"results.json",dataset)
 (out/"runner.txt").write_text(platform.platform()+"\n"+subprocess.run(
   ["lscpu"],text=True,capture_output=True).stdout)
 assert len(rows)==40 and sum(len(x["runs"]) for x in rows)==80
 print("CROSSFAMILY_CATEGORY_COMPLETE",category,
    "correct",sum(y["correct"] for x in rows for y in x["runs"]),
    "timeouts",sum(y["status"]=="TIMEOUT" for x in rows for y in x["runs"]),flush=True)

def corr(xs,ys):return structure.spearman(xs,ys)
def permutation(xs,ys,observed,seed,n=TRIALS):
 if observed is None:return None
 r=random.Random(seed);cnt=0
 for j in range(n):
  shuffled=ys[:];r.shuffle(shuffled)
  z=corr(xs,shuffled)
  if z is not None and abs(z)>=abs(observed)-1e-12:cnt+=1
 return (cnt+1)/(n+1)
def stratified_rho(grouped,feature):
 vals=[];weights=[]
 for name,records in grouped.items():
  rr=corr([x[feature] for x in records],[x["par2_median_seconds"] for x in records])
  if rr is None:return None
  rr=max(-.999999,min(.999999,rr))
  weights.append(len(records)-3)
  vals.append(math.atanh(rr)*(len(records)-3))
 return math.tanh(sum(vals)/sum(weights))
def stratified_p(grouped,feature,observed,seed,n=TRIALS):
 if observed is None:return None
 rng=random.Random(seed);count=0
 # Within-family hardness permutation; no shuffle across SAT/UNSAT types.
 base={k:[x["par2_median_seconds"] for x in v] for k,v in grouped.items()}
 for i in range(n):
  vals=[];w=[]
  for k,arr in grouped.items():
   yy=base[k][:];rng.shuffle(yy)
   r=corr([x[feature] for x in arr],yy)
   if r is None:return None
   vals.append(math.atanh(max(-.999999,min(.999999,r)))*(len(arr)-3))
   w.append(len(arr)-3)
  z=math.tanh(sum(vals)/sum(w))
  if abs(z)>=abs(observed)-1e-12:count+=1
 return (count+1)/(n+1)
def csvout(path,rows):
 if not rows:return
 columns=list(dict.fromkeys(key for row in rows for key in row))
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore")
  w.writeheader();w.writerows(rows)
def aggregate():
 config=json.loads(CONFIG.read_text())
 families=[x["category"] for x in config["test_families"]]
 if len(families)!=4 or config["per_family_cases"]!=40:raise RuntimeError("Preregister drift")
 rows=[];measurements=[];sources=[]
 for family in families:
  p=ROOT/family
  freeze=json.loads((p/"manifest_frozen_before_timing.json").read_text())
  dataset=json.loads((p/"results.json").read_text())
  if not freeze["frozen_before_solver_execution"] or dataset["repetitions"]!=2 or dataset["timeout_seconds"]!=5.3:
   raise RuntimeError("Missing frozen manifest or cap changed")
  if len(dataset["manifest"])!=40 or len(dataset["results"])!=40:
   raise RuntimeError("Missing source formulas")
  expected={x["id"]:x for x in freeze["manifest"]}
  actual={x["id"]:x for x in dataset["manifest"]}
  if expected!=actual:raise RuntimeError("Formula identities changed after measuring")
  if sha(json.dumps(dataset["manifest"],sort_keys=True).encode())!=freeze["manifest_sha256"]:
   raise RuntimeError("Frozen SHA256 manifest mismatch")
  source=config["test_families"][families.index(family)]
  if source["sha1"]!=freeze["source_archive_sha1"]:raise RuntimeError("Changed source")
  for rr in dataset["results"]:
   case=expected[rr["case"]]
   attempts=rr["runs"]
   if len(attempts)!=2 or rr["solver"]!="kissat":raise RuntimeError("Missing attempt/repeats")
   status=[y["status"] for y in attempts]
   if any(y["status"] in ("SAT","UNSAT") and not y["correct"] for y in attempts):
    raise RuntimeError("Wrong SAT/UNSAT, missing SAT witness or invalid answer")
   score=[y["seconds"] if y["correct"] and y["status"] in ("SAT","UNSAT") else 10.6
         for y in attempts]
   par2=statistics.median(score)
   rows.append({"family":family,"case":rr["case"],"expected":case["expected"],
     "variables":case["n"],"clauses":case["clauses"],
     "sha256_normalized":case["sha256_normalized"],
     "par2_median_seconds":par2,"par2_sum_seconds":sum(score),
     "timeout_attempts":sum(z=="TIMEOUT" for z in status),
     "fully_solved":all(y["correct"] for y in attempts),
     **case["structural_features"]})
   measurements.extend({"family":family,"case":rr["case"],"repeat":z["rep"],
     "seconds":z["seconds"],"status":z["status"],"correct":z["correct"],
     "par2_seconds":score[i]} for i,z in enumerate(attempts))
  sources.append({"family":family,"sha1":source["sha1"],
     "manifest_sha256":freeze["manifest_sha256"],
     "run":dataset["dataset_meta"]["source_run"],
     "sha":dataset["dataset_meta"]["source_sha"]})
 if len(rows)!=160 or len(measurements)!=320:raise RuntimeError("Missing all 160 cases/320 attempts")
 if len({x["sha256_normalized"] for x in rows})!=160:raise RuntimeError("Duplicate input")
 grouped={f:[x for x in rows if x["family"]==f] for f in families}
 tests=[]
 for i,f in enumerate(families):
  ys=[x["par2_median_seconds"] for x in grouped[f]]
  for j,feature in enumerate(FEATURES):
   xs=[x[feature] for x in grouped[f]]
   rho=corr(xs,ys)
   tests.append({"family":f,"predictor":feature,"n":40,
     "spearman_rho":rho,"permutation_p_two_sided":permutation(xs,ys,rho,
       seed=3191201+i*300+j*13),"bh_q_all_family_predictor_tests":None})
 ids=sorted(range(len(tests)),key=lambda i:tests[i]["permutation_p_two_sided"] or 1)
 q=1.
 for rank,i in reversed(list(enumerate(ids,1))):
  q=min(q,tests[i]["permutation_p_two_sided"]*len(ids)/rank)
  tests[i]["bh_q_all_family_predictor_tests"]=min(1.,q)
 pooled=[]
 for j,feature in enumerate(FEATURES):
  r=stratified_rho(grouped,feature)
  p=stratified_p(grouped,feature,r,624190+j*31)
  pooled.append({"feature":feature,"n_formulas":160,"families":4,
    "stratified_fisher_z_rho":r,"permutation_p_two_sided":p,"bh_q_three_pooled":None})
 ids=sorted(range(len(pooled)),key=lambda i:pooled[i]["permutation_p_two_sided"] or 1)
 q=1.
 for rank,i in reversed(list(enumerate(ids,1))):
  q=min(q,pooled[i]["permutation_p_two_sided"]*len(ids)/rank)
  pooled[i]["bh_q_three_pooled"]=min(1.,q)
 def signed(feature):
  return sum(next(x for x in tests if x["family"]==f and x["predictor"]==feature)
           ["spearman_rho"]<0 for f in families)
 success=(signed("degree_gini")>=3 and signed("degree_cv")>=3
      and all(next(x for x in pooled if x["feature"]==feature)["stratified_fisher_z_rho"]<0
         and next(x for x in pooled if x["feature"]==feature)["permutation_p_two_sided"]<.05
         and next(x for x in pooled if x["feature"]==feature)["bh_q_three_pooled"]<.05
          for feature in ("degree_gini","degree_cv")))
 summary={
  "pre_registration_sha256":sha(CONFIG.read_bytes()),"source_run_ids":sources,
  "sample_count":160,"attempt_count":320,"family_counts":{f:len(grouped[f]) for f in families},
  "timeouts_by_family":{f:sum(x["timeout_attempts"] for x in grouped[f]) for f in families},
  "correct_attempt_count":sum(1 for x in measurements if x["correct"]),
  "total_timeouts":sum(x["timeout_attempts"] for x in rows),
  "features":list(FEATURES),"individual_family_tests":tests,
  "family_stratified_pool":pooled,
  "negative_signs_by_feature":{feat:signed(feat) for feat in FEATURES},
  "preregistered_cross_family_transfer_success":success,
  "notes":[
    "This is transfer of a structural *hardness* correlation of original Kissat, NOT a DRNAS vs Kissat speed comparison.",
    "All 160 precommitted cases included; timed-out attempts assigned PAR-2 10.6 seconds.",
    "Source families and shape are fixed; SAT and UNSAT families analyzed separately, not pooled raw seconds.",
    "The graph-coloring family is structurally distinct, and may fail even if random 3-SAT families agree.",
    "12 within-family tests BH adjusted; 3 pooled tests separately BH adjusted.",
    "Known labels do not independently verify original Kissat UNSAT proofs.",
    "No changes to V15.3.1 source, no training/threshold adjustment from these test outcomes.",
    "No claim of general mathematical law or causality."]}
 ROOT.mkdir(exist_ok=True)
 outjson(ROOT/"aggregate.json",summary)
 csvout(ROOT/"formula_structures_and_outcomes.csv",rows)
 csvout(ROOT/"individual_attempts.csv",measurements)
 csvout(ROOT/"family_tests.csv",tests)
 csvout(ROOT/"pooled_tests.csv",pooled)
 report=["# DRNAS SAT -- preregistered cross-family structural transfer",
  f"**160 real SATLIB formulas, 4 families x 40, 320 upstream Kissat attempts.**",
  f"Prespecified transfer criterion met: **{success}**.",
  "All inputs SHA-1 verified, per-formula SHA-256 frozen before timing.",
  "",
  "| Family | Gini rho | Degree CV rho | Pair reuse rho | Timeout attempts /80 |",
  "|---|---:|---:|---:|---:|"]
 for f in families:
  get=lambda feat:next(x for x in tests if x["family"]==f and x["predictor"]==feat)["spearman_rho"]
  report.append(f"| {f} | {get('degree_gini'):+.4f} | {get('degree_cv'):+.4f} | {get('reused_varpair_fraction'):+.4f} | {summary['timeouts_by_family'][f]} |")
 report+=["","## Within-family pooled rank-effect (Fisher z, strata preserved)",
  "| Feature | Pooled rho | Permutation p | BH q |",
  "|---|---:|---:|---:|"]
 for p in pooled:
  report.append(f"| {p['feature']} | {p['stratified_fisher_z_rho']:+.4f} | {p['permutation_p_two_sided']:.4f} | {p['bh_q_three_pooled']:.4f} |")
 report+=["","**Interpretation:** A feature that predicts harder original Kissat instances in one random SATLIB family may fail on SAT, graph-coloring, or other structural classes. A failed transfer does not invalidate the original within-family finding.",
  "No interventions; original Kissat only; no independently verified UNSAT proof for original Kissat."]
 (ROOT/"report.md").write_text("\n".join(report)+"\n")
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for feat in FEATURES:
   fig,ax=plt.subplots(figsize=(8,5))
   for f in families:
    x=grouped[f]
    ax.scatter([r[feat] for r in x],
       [r["par2_median_seconds"] for r in x],label=f,alpha=.7)
   ax.set(xlabel=feat,ylabel="Original Kissat median PAR-2 (s)",
     title="Cross-family hardness transfer; unselected 40 formulae per source")
   ax.legend(fontsize=8);fig.tight_layout()
   fig.savefig(ROOT/("scatter_crossfamily_"+feat+".png"),dpi=155);plt.close(fig)
  fig,ax=plt.subplots(figsize=(8,5))
  for f in families:
   subset=grouped[f]
   ranks={key:structure.ranks([r[key] for r in subset]) if hasattr(structure,'ranks') else None
      for key in ["degree_gini","par2_median_seconds"]}
   if any(x is None for x in ranks.values()):continue
   ax.scatter(ranks["degree_gini"],ranks["par2_median_seconds"],label=f,alpha=.7)
  ax.set(xlabel="Within-family Gini rank",ylabel="Within-family Kissat PAR-2 rank",
    title="Family-normalized rank association")
  ax.legend(fontsize=8);fig.tight_layout()
  fig.savefig(ROOT/"scatter_within_family_rank.png",dpi=155);plt.close(fig)
 except ImportError: print("matplotlib unavailable: CSV and JSON remain complete",flush=True)
 print("CROSSFAMILY_FINAL",json.dumps({k:summary[k] for k in (
    "sample_count","attempt_count","total_timeouts","family_stratified_pool",
    "preregistered_cross_family_transfer_success")}),flush=True)
 print("\n".join(report),flush=True)

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--family")
 p.add_argument("--aggregate",action="store_true")
 args=p.parse_args()
 if args.aggregate:aggregate()
 else:run_family(args.family)
if __name__=="__main__":main()
