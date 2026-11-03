#!/usr/bin/env python3
"""R40 freeze 8 additional, distinct official SAT Competition 2026 CNFs.

Frozen before solver trials: four SAT, four UNSAT, SHA uniqueness, published
metadata used only for coarse file feasibility. No DRNAS results/labels used
for model features or gate. Public competition labels used ONLY for audit.
Previously tested 18 + 12 official CNFs are fully excluded.
"""
import csv,hashlib,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_shortlong_select import download_and_features,REV,SCORES_GIT_BLOB
SALT="R40-EARLY-RESCUE-UNSEEN-20261103-v1"
QUOTA={"SAT":4,"UNSAT":4}
def main():
 from argparse import ArgumentParser
 p=ArgumentParser()
 p.add_argument("--scores",required=True);p.add_argument("--prior18",required=True)
 p.add_argument("--prior12",required=True);p.add_argument("--out",required=True)
 a=p.parse_args()
 prior18=json.loads(Path(a.prior18).read_text())
 prior12=json.loads(Path(a.prior12).read_text())
 ids18={c["id"] for c in prior18["cases"]}
 ids12={c["id"] for c in prior12["cases"]}
 assert len(ids18)==18 and len(ids12)==12 and not ids18.intersection(ids12)
 candidates={"SAT":[],"UNSAT":[]}
 with open(a.scores,newline="") as f:
  scores=list(csv.DictReader(f))
 rows=[r for r in scores if r["solverid"]=="biere_cadical3[main]"]
 assert len(rows)==400,len(rows)
 for row in rows:
  label={"sat-verified":"SAT","unsat-verified":"UNSAT"}.get(row["status"])
  if not label or row["instanceid"] in ids18.union(ids12):continue
  t=float(row["runtime"])
  if not .5<=t<=180.:continue
  candidates[label].append({"id":row["instanceid"],"label":label,"public_ref_runtime_s":t})
 def order(z):
  return (abs(math.log(z["public_ref_runtime_s"]/6.0)),
    hashlib.sha256((SALT+":"+z["id"]).encode()).hexdigest())
 final=[];attempts=[]
 for label,needed in QUOTA.items():
  for x in sorted(candidates[label],key=order):
   if sum(c["official_label"]==label for c in final)>=needed:break
   try:
    c=download_and_features(x["id"])
    if c["cnf_bytes"]>40*1024*1024 or c["clauses"]>350000:
     raise ValueError("R40 feasibility: >40MiB or >350k clauses")
    if any(k["sha256"]==c["sha256"] for k in final):
     raise ValueError("Duplicate CNF SHA")
    final.append({**c,"official_label":label,"stratum":"official_2026_independent",
      "public_ref_runtime_s_selection_only":x["public_ref_runtime_s"]})
    attempts.append({"id":x["id"],"label":label,"accepted":True})
    print("R40_OFFICIAL_ACCEPT",label,x["id"],c["clauses"],c["sha256"],flush=True)
   except Exception as ex:
    attempts.append({"id":x["id"],"label":label,"accepted":False,"reason":str(ex)})
    print("R40_OFFICIAL_REJECT",label,x["id"],str(ex),flush=True)
  got=sum(c["official_label"]==label for c in final)
  if got!=needed:raise RuntimeError(f"Could not freeze {needed} {label} formulas: got {got}")
 assert len(final)==8 and len({x["sha256"] for x in final})==8
 final.sort(key=lambda c:hashlib.sha256((SALT+":schedule:"+c["id"]).encode()).hexdigest())
 mf={"protocol":SALT,"official_commit":REV,"scores_git_blob":SCORES_GIT_BLOB,
    "original18_excluded":sorted(ids18),"prior12_excluded":sorted(ids12),
    "cases":final,"attempts":attempts,"quotas":QUOTA,
    "warnings":["Public official 2026 source, independent of frozen prior 18+12, not blind to published competition",
      "Pre-search structural criteria are not updated on R40 outcomes",
      "One small fixed cohort, competition runtime used only for feasibility and sampling",
      "Selection not demonstrably disjoint from every formula ever used in all other DRNAS research"]}
 Path(a.out).write_text(json.dumps(mf,indent=2,sort_keys=True)+"\n")
 print("R40_OFFICIAL_FROZEN_SHA",hashlib.sha256(Path(a.out).read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":main()
