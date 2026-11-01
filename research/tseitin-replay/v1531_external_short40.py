#!/usr/bin/env python3
"""Frozen SATLIB external short40: four real public benchmark families, no solver changes.

The 40 file choices below were fixed before any short40 timing was collected.
They exclude the 13..20 instances used by frozen V15.3.1 SATLIB F regression.
They have NOT been proven unseen in all historical DRNAS experiments.
The original frozen selection included dubois100.cnf, which was rejected before
benchmarking because its header claimed 800 clauses but only 598 existed; it
was replaced by verified well-formed dubois21.cnf, without timing-based filtering.
This is NOT an official SAT Competition benchmark.
"""
import argparse, hashlib, json, os, random, statistics, subprocess, sys, time
from pathlib import Path
import v1531_satlib as legacy

PIN="fc0e735aff48989326f256121b5ed6fc585858c3"
SOURCE="mitchellh/go-sat"
BASE=Path("/tmp/satlib-repo/testdata/satlib")
CAP=8.0
REPS=3
SEED=153120261102
CHOICES={
 "uniform_sat": [(f"sat-uniform-20-91/uf20-0{x}.cnf","SAT") for x in (11,35,52,58,66,67,69,77,89,97)],
 "graph_coloring": [(f"sat-flat125-301/flat125-{x}.cnf","SAT") for x in (5,11,24,29,35,41,45,61,75,77)],
 "uniform_unsat": [(f"unsat-uniform-50-218/uuf50-0{x}.cnf","UNSAT") for x in (8,31,43,59,61,71,72,75,86,87)],
 "dubois_unsat": [(f"unsat-dimacs-dubois/dubois{x}.cnf","UNSAT") for x in (22,24,25,26,27,28,29,30,50,21)]
}
legacy.TIMEOUT=CAP

def sha(data): return hashlib.sha256(data).hexdigest()

def run_category(category):
 if category not in CHOICES:raise ValueError(category)
 if subprocess.check_output(["git","-C","/tmp/satlib-repo","rev-parse","HEAD"],text=True).strip()!=PIN:
  raise RuntimeError("Source commit drift")
 for name,p in ((name,legacy.SOLVERS[name]) for name in ("kissat","v1531")):
  if not p.exists():raise RuntimeError(f"Missing {name}: {p}")
 out=Path(f"short40-{category}")
 out.mkdir(exist_ok=True)
 manifest=[];rows=[];seen=set()
 rng=random.Random(SEED+list(CHOICES).index(category)*100)
 for idx,(rel,expected) in enumerate(CHOICES[category]):
  if category in ("uniform_sat","graph_coloring","uniform_unsat"):
   k=int(Path(rel).stem.split("-")[-1])
   if 13<=k<=20:raise RuntimeError("Previously seen reference instance "+rel)
  raw,normalized,n,clauses,trailer=legacy.normalize_satlib(BASE/rel)
  h=sha(normalized)
  if h in seen:raise RuntimeError("Duplicate normalized DIMACS within category")
  seen.add(h)
  name=f"{category}_{idx:02d}.cnf"
  dst=out/name
  dst.write_bytes(normalized)
  case={"file":dst,"n":n,"clauses":clauses,"expected":expected,"family":category}
  manifest.append({"id":name,"family":category,"expected":expected,
   "source":rel,"sha256_source":sha(raw),"sha256_normalized":h,
   "n":n,"clauses":len(clauses),"removed_satlib_trailer":trailer})
  measurements={"kissat":[],"v1531":[]}
  for repetition in range(REPS):
   order=["kissat","v1531"]
   rng.shuffle(order)
   for solver in order:
    result=legacy.run(solver,legacy.SOLVERS[solver],case)
    result["rep"]=repetition
    # UNSAT label agreement is NOT independent proof for Kissat;
    # native proof_valid may be null for Kissat fallback.
    result["model_verified"] = result.get("model_valid")
    result["unsat_proof_verified"] = result.get("proof_valid")
    measurements[solver].append(result)
    print("SHORT40",category,name,solver,repetition,
          result["status"],round(result["seconds"],6),
          "correct",result["correct"],"proof",result.get("proof_valid"),flush=True)
  for solver,runs in measurements.items():
   rows.append({"case":name,"family":category,"expected":expected,
    "solver":solver,"correct":all(x["correct"] for x in runs),
    "median_seconds":statistics.median(x["seconds"] for x in runs),
    "runs":runs})
 output={"dataset_meta":{"dataset":"DRNAS-V1531-External-Short40",
    "provenance":"external_holdout_relative_to_v1531",
    "source_run":"", "runner":os.environ.get("RUNNER_NAME","unknown"),
    "source_sha":os.environ.get("GITHUB_SHA","unknown"),
    "benchmark":"SATLIB, public external, not official 2026 or globally guaranteed unseen"},
    "source":SOURCE,"revision":PIN,"selection_seed":SEED,
    "family":category,"timeout_seconds":CAP,"repetitions":REPS,
    "manifest":manifest,"results":rows}
 (out/"part.json").write_text(json.dumps(output,indent=2)+"\n")
 if len(manifest)!=10 or len(rows)!=20 or sum(len(r["runs"]) for r in rows)!=60:
  raise RuntimeError("Wrong benchmark dimensions")
 return output

def aggregate(root):
 parts=[json.loads(p.read_text()) for p in sorted(root.glob("short40-*/part.json"))]
 if len(parts)!=4 or {x["family"] for x in parts}!=set(CHOICES):
  raise RuntimeError("Missing category")
 allm=[y for p in parts for y in p["manifest"]]
 allr=[y for p in parts for y in p["results"]]
 if len(allm)!=40 or len(allr)!=80 or sum(len(r["runs"]) for r in allr)!=240:
  raise RuntimeError("Missing measurements")
 if len({m["sha256_normalized"] for m in allm})!=40:raise RuntimeError("Duplicated formula hash")
 if len({m["id"] for m in allm})!=40:raise RuntimeError("Duplicated formula id")
 for p in parts:
  if p["revision"]!=PIN or p["timeout_seconds"]!=CAP:raise RuntimeError("Mismatched setup")
 output=Path("DRNAS-V1531-External-Short40")
 output.mkdir(exist_ok=True)
 combined={
 "dataset_meta":{"dataset":"DRNAS-V1531-External-Short40",
   "provenance":"external_holdout_relative_to_v1531",
   "source_run":os.environ.get("GITHUB_RUN_ID","unknown"),
   "source_sha":os.environ.get("GITHUB_SHA","unknown"),
   "runner":"github-hosted-ubuntu-24.04; paired within each category runner",
   "benchmark":"external SATLIB; not official; never seen only relative to 41278912894 SATLIB F"},
 "source":SOURCE,"revision":PIN,"selection_seed":SEED,
 "timeout_seconds":CAP,"repetitions":REPS,
 "manifest":allm,"results":allr}
 (output/"results.json").write_text(json.dumps(combined,indent=2)+"\n")
 md=["# DRNAS SAT V15.3.1 — 40 external short SATLIB problems",
     "Frozen before measuring; public external SATLIB benchmark, **not official competition**.",
     "Source "+SOURCE+" @ "+PIN,
     "40 distinct source-file hashes, four categories × 10; 2 solvers × 3 repetitions; 8 s cap.",
     "Each paired solver comparison is made within one GitHub runner per family.",
     "SAT checked against original clauses; DRNAS native UNSAT checked where proof emitted.",
     "Kissat UNSAT and DRNAS Kissat-fallback UNSAT labels do **not** constitute independently verified UNSAT proofs.",
     "Not known globally unseen across historical experiments; 13–20 previously used in the V15.3.1 baseline were excluded.",
     "Input validation exclusion: dubois100.cnf has 598 clauses against claimed 800; replaced with dubois21.cnf before new timing.","",
     "| Family | Solver | Correct attempts | Timeouts | PAR-2 total (s) | Median wall (s) |",
     "|---|---|---:|---:|---:|---:|"]
 summary={}
 for family in CHOICES:
  summary[family]={}
  for solver in ("kissat","v1531"):
   r=[x for x in allr if x["family"]==family and x["solver"]==solver]
   vals=[run for row in r for run in row["runs"]]
   correct=sum(v["correct"] for v in vals)
   timeout=sum(v["status"]=="TIMEOUT" for v in vals)
   par2=sum(v["seconds"] if v["correct"] and v["status"] in ("SAT","UNSAT") else 2*CAP for v in vals)
   median=statistics.median(v["seconds"] for v in vals)
   summary[family][solver]={"correct_attempts":correct,"attempts":len(vals),
    "timeouts":timeout,"par2_total":par2,"median_wall":median}
   md.append(f"| {family} | {solver} | {correct}/{len(vals)} | {timeout} | {par2:.6f} | {median:.6f} |")
 md+=["","## Paired category speedup (Kissat PAR-2 / V15.3.1 PAR-2)"]
 for cat,d in summary.items():
  a=d["kissat"]["par2_total"];b=d["v1531"]["par2_total"]
  md.append(f"- {cat}: {a/b:.4f}x" if b else f"- {cat}: undefined")
 (output/"results.md").write_text("\n".join(md)+"\n")
 (output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
 print("\n".join(md),flush=True)

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--category",choices=CHOICES)
 ap.add_argument("--aggregate",action="store_true")
 args=ap.parse_args()
 if args.aggregate: aggregate(Path("."))
 else:run_category(args.category)
