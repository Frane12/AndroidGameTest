#!/usr/bin/env python3
"""Untouched UUF250 source holdout for frozen *structural*, not solver, hypotheses.

40 SATLIB UUF250-1065 formulas excluded from the original 60-formula pilot.
Before timing, commit 40-file hash manifest and structural feature values.
Only original pinned Kissat used, with 2 repeats and 5.3s cap. No source
selection or tuning after measurement, no DRNAS code change.
"""
from __future__ import annotations
import csv, hashlib, json, random, statistics, tarfile, tempfile
from pathlib import Path
import v1531_satlib as legacy
import v1531_structural_fingerprints as structure

REG=Path("research/tseitin-replay/v1531_structural_holdout_uuf250_frozen.json")
TRAIN=Path("research/sat-analytics-data/medium40/results.json")
OUT=Path("uuf250-structural-validation")
NAME="uuf250-1065"
CAP=5.3
REPEATS=2
HYPOTHESES=("degree_gini","degree_cv","reused_varpair_fraction")
def sha(b):return hashlib.sha256(b).hexdigest()
def dump(path,d):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(d,indent=2,sort_keys=True)+"\n")
def bootstrap_rho(x,y,seed,rep=2500):
 rng=random.Random(seed);n=len(x)
 vals=[]
 for k in range(rep):
  ii=[rng.randrange(n) for _ in range(n)]
  z=structure.spearman([x[i] for i in ii],[y[i] for i in ii])
  if z is not None:vals.append(z)
 if not vals:return [None,None]
 vals.sort()
 return [vals[int(.025*len(vals))],vals[min(len(vals)-1,int(.975*len(vals)))]]
def main():
 prereg=json.loads(REG.read_text())
 training=json.loads(TRAIN.read_text())
 if len(prereg["features"])!=3 or tuple(x["feature"] for x in prereg["features"])!=HYPOTHESES:
  raise RuntimeError("Unexpected frozen hypotheses")
 if prereg["cap_seconds"]!=CAP or prereg["repeats"]!=REPEATS:
  raise RuntimeError("Frozen cap/repeat drift")
 if not Path("/tmp/kissat_solver").is_file():raise RuntimeError("Missing pinned original Kissat")
 archive=Path("/tmp/uuf250-1065.tar.gz")
 if hashlib.sha1(archive.read_bytes()).hexdigest()!=prereg["source_sha1"]:
  raise RuntimeError("Original SATLIB archive SHA1 drift")
 pilot=training["all_calibration_records"][NAME]
 if len(pilot)!=60:raise RuntimeError("Original pilot count not 60")
 pilotnames={Path(x["source_path"]).name for x in pilot}
 if len(pilotnames)!=60:raise RuntimeError("Duplicate original pilot names")
 known={x["sha256_normalized"] for x in pilot}
 for m in training["manifest"]:
  known.add(m["sha256_normalized"])
 short=json.loads(Path("research/sat-analytics-data/short40/results.json").read_text())
 known.update(x["sha256_normalized"] for x in short["manifest"])
 entries={}
 with tarfile.open(archive,"r:gz") as tar:
  for member in tar:
   if not member.isfile() or not member.name.endswith(".cnf"):continue
   if member.name.startswith("/") or ".." in Path(member.name).parts:
    raise RuntimeError("Unsafe archive member path")
   name=Path(member.name).name
   if name in entries:raise RuntimeError("Duplicate source basename "+name)
   f=tar.extractfile(member)
   if f:entries[name]=(member.name,f.read())
 if len(entries)!=100:raise RuntimeError("Expected exactly 100 source CNFs")
 holdout=sorted(set(entries)-pilotnames)
 if len(holdout)!=40:raise RuntimeError(f"Holdout not 40: {len(holdout)}")
 OUT.mkdir(exist_ok=True)
 manifest=[];features={}
 with tempfile.TemporaryDirectory() as folder:
  tmp=Path(folder)/"temp.cnf"
  for i,basename in enumerate(holdout):
   orig,raw=entries[basename]
   clean,n,clauses=structure.normalize_raw(raw,tmp)
   origsha=sha(raw);normalized_sha=sha(clean)
   if normalized_sha in known:raise RuntimeError("Input overlaps old pilot/benchmark "+basename)
   known.add(normalized_sha)
   feat=structure.features(n,clauses)
   fileid=f"uuf250_holdout_{i:02d}.cnf"
   (OUT/"inputs").mkdir(exist_ok=True)
   (OUT/"inputs"/fileid).write_bytes(clean)
   record={"id":fileid,"source":orig,"sha256_source":origsha,
           "sha256_normalized":normalized_sha,"expected":"UNSAT",
           "family":"uuf250_unused_40","n":n,"clauses":len(clauses),
           "structural_features":feat}
   manifest.append(record)
   features[fileid]=feat
 allhash=sha(json.dumps(manifest,sort_keys=True).encode())
 pre={"preregistered":prereg,"source_archive_sha1":prereg["source_sha1"],
       "source_archive_sha256":sha(archive.read_bytes()),"manifest_sha256":allhash,
       "pilot_names":sorted(pilotnames),"test_names":holdout,"manifest":manifest,
       "frozen_without_timing":True}
 dump(OUT/"frozen_before_timing.json",pre)
 print("HOLDOUT_FREEZE",len(manifest),"sha256",allhash,flush=True)
 # Run each source formula in fixed randomized attempt ordering, not
 # sorted by expected runtime; repeat runs on same runner.
 legacy.TIMEOUT=CAP
 rng=random.Random(26110146)
 tasks=[(i,r) for r in manifest for i in range(REPEATS)]
 rng.shuffle(tasks)
 by_case={r["id"]:[] for r in manifest}
 for step,(repeat,m) in enumerate(tasks):
  file=OUT/"inputs"/m["id"]
  case={"file":file,"n":m["n"],"clauses":legacy.normalize_satlib(file)[3],"expected":"UNSAT"}
  got=legacy.run("kissat",legacy.SOLVERS["kissat"],case)
  got["rep"]=repeat
  by_case[m["id"]].append(got)
  dump(OUT/"progress.partial.json",{"manifest_sha256":allhash,
     "completed_attempts":step+1,"attempts":by_case})
  print("VALIDATE",step+1,len(tasks),m["id"],"rep",repeat,
        got["status"],round(got["seconds"],5),"correct",got["correct"],flush=True)
 rows=[];data=[]
 for m in manifest:
  attempt=sorted(by_case[m["id"]],key=lambda x:x["rep"])
  if len(attempt)!=REPEATS:raise RuntimeError("Missing attempt")
  times=[x["seconds"] if x["correct"] and x["status"]=="UNSAT" else 2*CAP for x in attempt]
  rows.append({"case":m["id"],"family":"uuf250_unused_40",
    "expected":"UNSAT","solver":"kissat","correct":all(x["correct"] for x in attempt),
    "median_seconds":statistics.median(x["seconds"] for x in attempt),
    "runs":attempt})
  data.append({**m["structural_features"],"case":m["id"],"source":m["source"],
    "par2_median_seconds":statistics.median(times),
    "timeout_attempts":sum(x["status"]=="TIMEOUT" for x in attempt),
    "both_solved":all(x["correct"] for x in attempt)})
 results={"dataset_meta":{"dataset":"DRNAS-V1531-Structural-UUF250-Validation",
  "provenance":"external_preregistered_untouched_40","benchmark":"SATLIB UUF250 Kissat-only blind structural correlation validation",
  "source_run":"","source_sha":"","runner":"GitHub-hosted Ubuntu 24.04"},
  "source":"SATLIB UBC uuf250-1065","source_archive_sha1":prereg["source_sha1"],
  "preregistration_sha256":sha(REG.read_bytes()),
  "source_archive_sha256":pre["source_archive_sha256"],
  "manifest_sha256":allhash,"timeout_seconds":CAP,"repetitions":REPEATS,
  "manifest":manifest,"results":rows}
 dump(OUT/"results.json",results)
 pvals=[]
 for i,feat in enumerate(HYPOTHESES):
  x=[v[feat] for v in data];y=[v["par2_median_seconds"] for v in data]
  rho=structure.spearman(x,y)
  p=structure.permutation_p(x,y,rho,35132+i*100)
  ci=bootstrap_rho(x,y,95341+i*100)
  sub=[v for v in data if v["both_solved"]]
  secondary=structure.spearman([z[feat] for z in sub],
                                [z["par2_median_seconds"] for z in sub])
  pvals.append({"feature":feat,"n":len(data),"rho_holdout":rho,
    "permutation_p":p,"bootstrap95_rho":ci,"direction_matches":rho is not None and rho<0,
    "n_both_solved":len(sub),"solved_only_rho_sensitivity":secondary,"bh_q":None})
 structure.bh_adjust(pvals)
 condition=all(p["rho_holdout"] is not None and p["rho_holdout"]<0 and
               p["permutation_p"]<.05 and p["bh_q"]<.05
               for p in pvals if p["feature"] in ("degree_gini","degree_cv"))
 info={"dataset":"uuf250_unused40","n":len(data),
  "attempts":sum(len(x["runs"]) for x in rows),
  "timeout_attempts":sum(v["timeout_attempts"] for v in data),
  "all_source_hashes_unique":len({x["sha256_normalized"] for x in manifest})==40,
  "preregistered_success_rule_met":bool(condition),
  "hypothesis_tests":pvals,
  "warning":"This tests structure versus **original Kissat** time within one SATLIB family only; no DRNAS speed claim, causation claim, global SAT inference or independently UNSAT-proof-verified claim."}
 dump(OUT/"validation.json",info)
 with (OUT/"features_outcomes.csv").open("w",newline="") as f:
  cols=list(data[0]);w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(data)
 report=["# Independent structural validation (40 untouched UUF250 CNFs)",
 f"- Input identity manifest sha256: {allhash}",
 f"- Attempts: {info['attempts']}, timeouts: {info['timeout_attempts']}.",
 f"- Preregistered joint rule met: **{condition}**.",
 "| Feature | Holdout Spearman rho | permutation p | BH q | Bootstrap 95% rho |",
 "|---|---:|---:|---:|---|"]
 for p in pvals:
  report.append(f"| {p['feature']} | {p['rho_holdout']:.4f} | {p['permutation_p']:.4f} | {p['bh_q']:.4f} | {p['bootstrap95_rho']} |")
 report.extend(["","All 40 formulas included; timeout PAR-2=10.6s.",
  "No outcomes, thresholds or formula identities altered after the preregistration.",
  "SATLIB UNSAT status labels not independently proof-validated here.",
  "Statistical association is neither causality nor validation of DRNAS-specific acceleration."])
 (OUT/"report.md").write_text("\n".join(report)+"\n")
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for feature in HYPOTHESES:
   fig,ax=plt.subplots(figsize=(8,5))
   ax.scatter([z[feature] for z in data],[z["par2_median_seconds"] for z in data],alpha=.8)
   ax.set(xlabel=feature,ylabel="Original Kissat median PAR-2 (seconds)",
          title="Previously unseen UUF250 holdout; n=40")
   fig.tight_layout();fig.savefig(OUT/("validate_"+feature+".png"),dpi=160);plt.close(fig)
 except ImportError: pass
 print("HOLDOUT_FINAL",json.dumps(info),flush=True)
if __name__=="__main__":main()
