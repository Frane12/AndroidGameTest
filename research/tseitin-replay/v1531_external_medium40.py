#!/usr/bin/env python3
"""SATLIB calibrated medium cohort: original public CNFs; no solver modifications.

Four predeclared SATLIB corpora. Select candidates using *only original Kissat*
pilot timings, never using V15.3.1 outcomes. Report all pilot candidates and
out-of-band fallbacks. Calibrated selection is NOT an untouched blind holdout,
nor an official SAT Competition result. Source SHA1 hashes externally pinned.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, platform, random, statistics, subprocess
from pathlib import Path
from collections import defaultdict
import v1531_satlib as legacy

OUT=Path("medium40")
SRC=Path("/tmp/satlib-extract")
KISSAT_PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
SOURCE_BASE="https://www.cs.ubc.ca/~hoos/SATLIB/Benchmarks/SAT/RND3SAT/"
CORPORA={
 "uf200-860":{"sha1":"e27208778d47d2405a9368cad3ab8dfb41206be8","expected":"SAT"},
 "uf250-1065":{"sha1":"acaf37c9e92694a38974a6a1a9647e0f9bcf80b2","expected":"SAT"},
 "uuf200-860":{"sha1":"05aacf179ed739a8311f2821874183daa5a9b134","expected":"UNSAT"},
 "uuf250-1065":{"sha1":"138484766c966e3f18395db92cf6d69d3c442a3e","expected":"UNSAT"}
}
SEED=153120261103
PILOT_N=60
PILOT_CAP=5.3
MIN_KISSAT=0.1
MAX_KISSAT=5.0
BENCH_CAP=8.0
REPEATS=3
TARGET_N=10

def hash_bytes(data): return hashlib.sha256(data).hexdigest()
def dump(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def source_hash(path):return hash_bytes(path.read_bytes())
def prior_hashes():
 out=set()
 p=Path("research/sat-analytics-data/short40/results.json")
 if p.exists():
  for m in json.loads(p.read_text()).get("manifest",[]):
   for k in ("sha256_normalized","sha256_source"):
    if m.get(k):out.add(m[k])
 q=Path("research/sat-analytics-data/current/formulas.csv")
 if q.exists():
  with q.open(newline="") as f:
   for r in csv.DictReader(f):
    for k in ("formula_sha256","original_sha256"):
     if r.get(k):out.add(r[k])
 return out
def category_run(category):
 if category not in CORPORA:raise ValueError(category)
 out=Path("medium40-"+category)
 out.mkdir(exist_ok=True)
 archive=Path("/tmp/"+category+".tar.gz")
 if not archive.is_file():raise RuntimeError("Missing original archive "+str(archive))
 actual=hashlib.sha1(archive.read_bytes()).hexdigest()
 if actual!=CORPORA[category]["sha1"]:raise RuntimeError("Pinned SATLIB archive checksum mismatch")
 import tarfile
 with tarfile.open(archive,"r:gz") as t:
  members=[m for m in t.getmembers() if m.isfile() and m.name.lower().endswith(".cnf")]
  paths=[m for m in members if not m.name.startswith("/") and ".." not in Path(m.name).parts]
  if len(paths)!=len(members) or len(paths)<TARGET_N:raise RuntimeError("Invalid archive paths or too few entries")
  r=random.Random(SEED+list(CORPORA).index(category))
  r.shuffle(paths)
  chosen=paths[:min(PILOT_N,len(paths))]
  pool=[];dupes=prior_hashes();seen=set()
  for item in chosen:
   fh=t.extractfile(item)
   if fh is None:continue
   raw=fh.read()
   original=out/"pilot-original"/Path(item.name).name
   original.parent.mkdir(exist_ok=True)
   original.write_bytes(raw)
   try: raw2,clean,n,clauses,trailer=legacy.normalize_satlib(original)
   except (ValueError,UnicodeDecodeError) as e:
    pool.append({"file":item.name,"invalid":str(e)[:140]})
    continue
   if raw2!=raw:raise RuntimeError("Original raw hash drift")
   h=hash_bytes(clean)
   entry={"source_path":item.name,"sha256_source":hash_bytes(raw),
          "sha256_normalized":h,"variables":n,"clauses":len(clauses),
          "trailer_removed":trailer,"expected":CORPORA[category]["expected"]}
   if h in dupes or h in seen:
    entry["excluded"]="duplicate of existing dataset or pilot"
   else:
    seen.add(h)
    target=out/"pilot-normalized"/Path(item.name).name
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(clean)
    entry["normalized_path"]=str(target)
   pool.append(entry)
 freeze={"category":category,"pilot_seed":SEED+list(CORPORA).index(category),
  "archive_sha1":actual,"archive_sha256":source_hash(archive),
  "source_url":SOURCE_BASE+category+".tar.gz",
  "sampled_count":len(chosen),"prior_hashes_count":len(dupes),
  "selected_before_any_timing":pool,"selection_uses_only_original_kissat":True,
  "pilot_cap":PILOT_CAP,"target_window":[MIN_KISSAT,MAX_KISSAT]}
 dump(out/"pilot_frozen_before_timing.json",freeze)
 legacy.TIMEOUT=PILOT_CAP
 pilot=[]
 for i,e in enumerate(pool):
  if "normalized_path" not in e:
   pilot.append({**e,"pilot_status":"EXCLUDED"})
   continue
  case={"file":Path(e["normalized_path"]),"n":e["variables"],
   "clauses":legacy.normalize_satlib(Path(e["normalized_path"]))[3],
   "expected":e["expected"]}
  m=legacy.run("kissat",legacy.SOLVERS["kissat"],case)
  row={**e,"pilot_status":m["status"],"pilot_seconds":m["seconds"],
       "pilot_correct":bool(m["correct"]),"pilot_model_ok":m.get("model_valid")}
  pilot.append(row)
  dump(out/"pilot_all.json",pilot)
  print("PILOT",category,i,e["source_path"],m["status"],
        round(m["seconds"],5),"valid",m["correct"],flush=True)
 valid=[x for x in pilot if x.get("pilot_correct") and x.get("pilot_status") in ("SAT","UNSAT")]
 inwindow=[x for x in valid if MIN_KISSAT<=x["pilot_seconds"]<=MAX_KISSAT]
 selected=inwindow[:TARGET_N]
 if len(selected)<TARGET_N:
  # Deterministic fallback minimizing distance to calibrated time window;
  # list all out-of-window choices explicitly, do not call all cases medium.
  rest=[x for x in valid if x not in selected]
  def distance(x):
   t=x["pilot_seconds"]
   return (MIN_KISSAT-t) if t<MIN_KISSAT else max(0,t-MAX_KISSAT)
  rest.sort(key=lambda x:(distance(x),x["source_path"]))
  selected+=rest[:TARGET_N-len(selected)]
 if len(selected)!=TARGET_N:raise RuntimeError(f"Only {len(selected)} valid candidates, expected 10")
 for x in selected:x["within_target_window"]=MIN_KISSAT<=x["pilot_seconds"]<=MAX_KISSAT
 manifest=[];rows=[]
 legacy.TIMEOUT=BENCH_CAP
 order_rng=random.Random(SEED+9000+list(CORPORA).index(category))
 for i,e in enumerate(selected):
  filename=f"{category}_{i:02d}.cnf"
  normalized=Path(e["normalized_path"])
  name=out/filename
  name.write_bytes(normalized.read_bytes())
  manifest.append({"id":filename,"family":category,"expected":e["expected"],
    "source":e["source_path"],"archive_sha1":actual,
    "sha256_source":e["sha256_source"],"sha256_normalized":e["sha256_normalized"],
    "n":e["variables"],"clauses":e["clauses"],
    "pilot_kissat_seconds":e["pilot_seconds"],"within_target_window":e["within_target_window"],
    "selection_method":"Kissat-only calibration; before V15.3.1 evaluation"})
  case={"file":name,"expected":e["expected"],"n":e["variables"],
         "clauses":legacy.normalize_satlib(name)[3]}
  measurements=defaultdict(list)
  for rep in range(REPEATS):
   order=["kissat","v1531"]
   order_rng.shuffle(order)
   for solver in order:
    m=legacy.run(solver,legacy.SOLVERS[solver],case)
    m["rep"]=rep
    measurements[solver].append(m)
    print("BENCH",category,filename,rep,solver,m["status"],
     round(m["seconds"],6),"correct",m["correct"],"proof",m.get("proof_valid"),flush=True)
  for solver,repvals in measurements.items():
   rows.append({"case":filename,"family":category,"expected":e["expected"],
     "solver":solver,"correct":all(x["correct"] for x in repvals),
     "median_seconds":statistics.median(x["seconds"] for x in repvals),
     "runs":repvals})
  dump(out/"measurements.partial.json",{"manifest":manifest,"results":rows})
 dump(out/"part.json",{"dataset_meta":{"dataset":"DRNAS-V1531-External-Medium40",
   "provenance":"external_kissat_calibrated_not_blind",
   "benchmark":"SATLIB original 200/250 random 3-SAT, selected on Kissat-only calibration",
   "source_run":os.environ.get("GITHUB_RUN_ID",""),
   "source_sha":os.environ.get("GITHUB_SHA",""),
   "runner":os.environ.get("RUNNER_NAME","unknown")},
   "source":"SATLIB UBC original archived","archive_url":SOURCE_BASE+category+".tar.gz",
   "archive_sha1":actual,"archive_sha256":source_hash(archive),
   "family":category,"selection_seed":SEED,"pilot_cap":PILOT_CAP,
   "pilot_window":[MIN_KISSAT,MAX_KISSAT],"pilot":pilot,
   "timeout_seconds":BENCH_CAP,"repetitions":REPEATS,
   "manifest":manifest,"results":rows})
 (out/"runner.txt").write_text(platform.platform()+"\n"+subprocess.run(
  ["lscpu"],capture_output=True,text=True).stdout)
 print("CATEGORY_DONE",category,"target_matches",len(inwindow),
       "selected_in_target",sum(e["within_target_window"] for e in selected),
       "attempts",sum(len(y["runs"]) for y in rows),flush=True)

def aggregate():
 parts=[json.loads(p.read_text()) for p in sorted(Path(".").glob("medium40-*/part.json"))]
 if len(parts)!=4 or {x["family"] for x in parts}!=set(CORPORA):
  raise RuntimeError("Missing category part(s)")
 allm=[m for p in parts for m in p["manifest"]]
 allr=[r for p in parts for r in p["results"]]
 if len(allm)!=40 or len(allr)!=80 or sum(len(r["runs"]) for r in allr)!=240:
  raise RuntimeError("Missing formula / measurement rows")
 if len({m["sha256_normalized"] for m in allm})!=40:raise RuntimeError("Duplicate input SHA256")
 if any(p["timeout_seconds"]!=BENCH_CAP for p in parts):raise RuntimeError("Cap mismatch")
 OUT.mkdir(exist_ok=True)
 combined={"dataset_meta":{"dataset":"DRNAS-V1531-External-Medium40",
    "provenance":"external_kissat_calibrated_not_blind",
    "benchmark":"Original SATLIB UF/UUF 200/250, calibration selection on original Kissat only; unofficial",
    "source_run":os.environ.get("GITHUB_RUN_ID","unknown"),
    "source_sha":os.environ.get("GITHUB_SHA","unknown"),
    "runner":"GitHub-hosted Ubuntu 24.04, within-family same runner"},
    "source":"SATLIB UBC original",
    "archive_sha1_by_category":{p["family"]:p["archive_sha1"] for p in parts},
    "archive_sha256_by_category":{p["family"]:p["archive_sha256"] for p in parts},
    "timeout_seconds":BENCH_CAP,"repetitions":REPEATS,
    "selection_seed":SEED,"pilot_cap_seconds":PILOT_CAP,
    "target_window":[MIN_KISSAT,MAX_KISSAT],
    "all_calibration_records":{p["family"]:p["pilot"] for p in parts},
    "manifest":allm,"results":allr}
 dump(OUT/"results.json",combined)
 summary={}
 lines=["# DRNAS SAT V15.3.1 — external calibrated medium40",
   "Four SATLIB public source families, 10 each, 3 repeats × 2 solvers = 240 measurements.",
   "Original archive SHA1 pinned; solver baseline unchanged; matched comparisons per same runner.",
   "Cases were chosen by **original Kissat-only pilot time**, not V15.3.1.",
   "Window 0.1–5.0 s is a target, not a guaranteed achieved property. Out-of-window fallbacks shown.",
   "Calibrated selection is NOT a strictly blind holdout or official SAT Competition result.",
   "SAT witnesses validated; native DRNAS UNSAT proof checked where available. No independent",
   "UNSAT proof validation for original Kissat or Kissat fallback in this experiment.","",
   "| Family | In target /10 | Solver | Correct /30 | Timeouts | PAR-2 (s) | Median (s) |",
   "|---|---:|---|---:|---:|---:|---:|"]
 for family in CORPORA:
  summary[family]={}
  count=sum(e["family"]==family and e["within_target_window"] for e in allm)
  for solver in ("kissat","v1531"):
   rs=[x for x in allr if x["family"]==family and x["solver"]==solver]
   measurements=[y for r in rs for y in r["runs"]]
   correct=sum(bool(y["correct"]) for y in measurements)
   timeouts=sum(y["status"]=="TIMEOUT" for y in measurements)
   par2=sum(y["seconds"] if y["correct"] and y["status"] in ("SAT","UNSAT")
            else 2*BENCH_CAP for y in measurements)
   median=statistics.median(y["seconds"] for y in measurements)
   summary[family][solver]={"par2":par2,"correct_attempts":correct,
       "total_attempts":len(measurements),"timeouts":timeouts,"median_seconds":median}
   lines.append(f"| {family} | {count}/10 | {solver} | {correct}/30 | {timeouts} | {par2:.6f} | {median:.6f} |")
 lines+=["","## Paired PAR-2 speedup (Kissat/V15.3.1; >1 means DRNAS faster)"]
 for family in CORPORA:
  x=summary[family]["kissat"]["par2"]
  y=summary[family]["v1531"]["par2"]
  lines.append(f"- {family}: {x/y:.4f}x" if y else f"- {family}: undefined")
 dump(OUT/"summary.json",summary)
 (OUT/"results.md").write_text("\n".join(lines)+"\n")
 print("\n".join(lines),flush=True)

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--category",choices=list(CORPORA))
 ap.add_argument("--aggregate",action="store_true")
 args=ap.parse_args()
 if args.aggregate:aggregate()
 else:category_run(args.category)
