#!/usr/bin/env python3
"""Freeze R44 eight additional SAT Competition 2026 original DIMACS CNFs.

Exclude SHA/ID from all previous official cohorts used by R37/R40. Selection
uses ONLY public official CaDiCaL runtime, file size, and deterministic salt.
No R44 solver results can influence sample or gate.
"""
import argparse,csv,hashlib,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"research/drnas-sat-v7-8"))
from official_shortlong_select import REV,SCORES_GIT_BLOB,download_and_features
SALT="R44-FROZEN-QUALITY-DOSE-20261103-V1"
QUOTAS={"SAT":4,"UNSAT":4}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--scores",required=True)
 p.add_argument("--prior18",required=True)
 p.add_argument("--prior12",required=True)
 p.add_argument("--prior8",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 prev=[]
 for name,path,count in (("18",a.prior18,18),("12",a.prior12,12),("8",a.prior8,8)):
  m=json.loads(Path(path).read_text())
  assert len(m["cases"])==count,(name,count)
  prev+=m["cases"]
 excluded_ids={x["id"] for x in prev}
 excluded_sha={x["sha256"] for x in prev}
 assert len(excluded_ids)==len(excluded_sha)==38
 with open(a.scores,newline="") as f:
  rows=[r for r in csv.DictReader(f) if r["solverid"]=="biere_cadical3[main]"]
 assert len(rows)==400
 candidates={"SAT":[],"UNSAT":[]}
 for x in rows:
  label={"sat-verified":"SAT","unsat-verified":"UNSAT"}.get(x["status"])
  if label is None or x["instanceid"] in excluded_ids:continue
  t=float(x["runtime"])
  if not .05<=t<=30.:continue
  candidates[label].append(dict(id=x["instanceid"],label=label,reference_s=t))
 def rank(row):
  return (abs(math.log(row["reference_s"]/2.0)),
          hashlib.sha256((SALT+"/"+row["id"]).encode()).hexdigest())
 selected=[];decisions=[]
 for label,count in QUOTAS.items():
  for x in sorted(candidates[label],key=rank):
   if sum(v["official_label"]==label for v in selected)>=count:break
   try:
    c=download_and_features(x["id"])
    if c["cnf_bytes"]>24*1024*1024:raise ValueError("raw DIMACS >24 MiB")
    if c["clauses"]>280000:raise ValueError("more than 280k clauses")
    if c["sha256"] in excluded_sha:raise ValueError("original CNF SHA already used")
    if c["sha256"] in {v["sha256"] for v in selected}:raise ValueError("duplicate case SHA")
    selected.append({**c,"official_label":label,
     "sampling_only_official_cadical_runtime_s":x["reference_s"]})
    decisions.append(dict(id=x["id"],label=label,accepted=True))
    print("R44_FREEZE_ACCEPT",label,x["id"],"ref",x["reference_s"],
       "vars",c["variables"],"clauses",c["clauses"],flush=True)
   except Exception as ex:
    decisions.append(dict(id=x["id"],label=label,accepted=False,reason=str(ex)))
    print("R44_FREEZE_REJECT",label,x["id"],str(ex),flush=True)
  if sum(v["official_label"]==label for v in selected)!=count:
   raise RuntimeError("No valid "+label+" group after size/identity filters")
 selected.sort(key=lambda z:hashlib.sha256((SALT+":schedule:"+z["id"]).encode()).hexdigest())
 assert len(selected)==8 and len({x["sha256"] for x in selected})==8
 m=dict(protocol=SALT,cases=selected,
  quotas=QUOTAS,official_commit=REV,scores_git_blob=SCORES_GIT_BLOB,
  excluded_prior_count=len(excluded_ids),excluded_prior_ids=sorted(excluded_ids),
  excluded_prior_sha256=sorted(excluded_sha),
  selection_trace=decisions,
  caution=["Official SAT Competition 2026 formulas, SHA-distinct from 38 previously frozen official CNFs",
   "Not guaranteed disjoint from every formula ever touched by other DRNAS experiments",
   "Selection on known public official CaDiCaL runtimes and size causes nonrepresentative sample",
   "Selection does not use R44 experiment timing; no algorithm tuning after sample freeze",
   "Official SAT/UNSAT labels public; no independent UNSAT proof certificates in R44"])
 out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
 print("R44_FROZEN_8_SHA",hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":main()
