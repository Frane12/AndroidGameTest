#!/usr/bin/env python3
"""R43 fail-closed audit, exactly 40 preselected official native trials.

One R42 anchor plus four other old official formulas. Report activation
vs abstention, improvements and regressions. One/two seeds cannot establish
generalization, do NOT recommend a new deployed gate.
"""
import argparse,hashlib,json,random
from pathlib import Path
from r43_dose_probe import CASES,MODES,REPS,CAP,PREFIX_KEYS
def mean(xs):return sum(xs)/len(xs)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True)
 p.add_argument("--combined",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 mf=Path(a.manifest);m=json.loads(mf.read_text())
 known={c["id"]:c for c in m["cases"]}
 assert len(known)==12 and len(CASES)==5 and len(set(CASES))==5
 sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
 allrows=[];binary=set();casewise=[]
 for i,cid in enumerate(CASES):
  assert cid in known
  root=Path(a.combined)/f"r43-case-{i}"/"results"
  meta=json.loads((root/"meta.json").read_text())
  assert meta["case_id"]==cid and meta["index"]==i
  assert meta["manifest_sha256"]==sha(mf)
  assert meta["protocol"]=="R43_SMALL_DOSE_TRANSFER_PRESELECTED"
  assert meta["cap_s"]==CAP and meta["reps"]==REPS
  assert tuple(meta["modes"])==MODES and meta["n_trials"]==len(MODES)*REPS
  binary.add(meta["native_sha256"])
  rows=json.loads((root/"trials.json").read_text())
  assert len(rows)==len(MODES)*REPS
  lookup={}
  for r in rows:
   assert r["case_id"]==cid and r["sha256"]==known[cid]["sha256"]
   assert r["official_label"]==known[cid]["official_label"]
   assert r["mode"] in MODES and r["rep"] in range(REPS)
   assert float(r["cap_s"])==CAP
   assert r["status"] in ("SAT","UNSAT","TIMEOUT")
   if r["status"]!="TIMEOUT":assert r["status"]==known[cid]["official_label"]
   expectseed=(830031+int(r["sha256"][:8],16)+r["rep"]*101)%2**32
   assert r["seed"]==expectseed
   assert r["wall_s"]>=0 and r["cpu_s"]>=0
   assert r["checkpoint"] and r["action"],"Trace not captured"
   assert r["checkpoint"]["stage1"]=="0"
   assert int(r["actual_hints"])>=0
   key=(r["rep"],r["mode"])
   assert key not in lookup
   lookup[key]=r
  assert len(lookup)==len(MODES)*REPS
  for rep in range(REPS):
   states={tuple(lookup[rep,mode]["checkpoint"][k] for k in PREFIX_KEYS) for mode in MODES}
   assert len(states)==1,("R43 early search state divergence",cid,rep)
  summary={}
  for mode in MODES:
   z=[lookup[rep,mode] for rep in range(REPS)]
   summary[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in z),
      timeouts=sum(r["status"]=="TIMEOUT" for r in z),
      mean_PAR2_s=round(mean([r["PAR2_s"] for r in z]),6),
      actual_hint_count=[r["actual_hints"] for r in z],
      wall_s=[r["wall_s"] for r in z])
  ctrl=summary["v91_quality_gate"]["mean_PAR2_s"]
  for mode in MODES:
   summary[mode]["difference_vs_control_PAR2_s"]=round(summary[mode]["mean_PAR2_s"]-ctrl,6)
   summary[mode]["pct_change_vs_control"]=round(100*(summary[mode]["mean_PAR2_s"]/ctrl-1),4)
  casewise.append(dict(case_id=cid,label=known[cid]["official_label"],
       checkpoint=lookup[0,MODES[0]]["checkpoint"],
       modes=summary,any_activation=any(int(r["actual_hints"])>0 for r in rows)))
  allrows.extend(rows)
 assert len(binary)==1 and len(allrows)==len(CASES)*len(MODES)*REPS
 bymode={}
 for mode in MODES:
  rs=[r for r in allrows if r["mode"]==mode]
  bymode[mode]=dict(mean_PAR2_s=round(mean([r["PAR2_s"] for r in rs]),6),
    solved=sum(r["status"]!="TIMEOUT" for r in rs),
    timeouts=sum(r["status"]=="TIMEOUT" for r in rs),
    active_trials=sum(r["actual_hints"]>0 for r in rs))
 control=bymode["v91_quality_gate"]["mean_PAR2_s"]
 for mode in MODES:
  bymode[mode]["pct_change_vs_control"]=round(100*(bymode[mode]["mean_PAR2_s"]/control-1),3)
 print("R43_CASE_SCORES")
 for c in casewise:
  print("R43_CASE",json.dumps(dict(id=c["case_id"],label=c["label"],
    gate_quality=c["checkpoint"]["quality"],extended=c["checkpoint"]["extended"],
    active=c["any_activation"],
    modes={k:dict(mean_PAR2_s=v["mean_PAR2_s"],actual_hint_count=v["actual_hint_count"])
          for k,v in c["modes"].items()}),sort_keys=True),flush=True)
 report=dict(protocol="R43_SMALL_HINT_DOSE_TRANSFER",original_manifest_sha256=sha(mf),
  native_binary_sha256=next(iter(binary)),n_cases=len(CASES),
  n_trials=len(allrows),paired_prefix_equal=REPS*len(CASES),
  case_labels="published official SAT 2026 labels, no independent UNSAT proof",
  cap_s=CAP,by_mode=bymode,cases=casewise,
  limitations=["Previously observed formulas, not a new independent blind set",
      "5 formula categories, two fixed seeds only; results are exploratory",
      "Only cases with positive quality and early resume actually apply hint doses",
      "PAR-2 timeouts use 2*10 seconds, not measured completion times",
      "No automatic deployment or threshold fitting to these results"])
 Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
 print("R43_AUDIT_PASS",json.dumps({k:report[k] for k in ("n_cases","n_trials","paired_prefix_equal")},sort_keys=True),flush=True)
 print("R43_MODE_SUMMARY",json.dumps(bymode,sort_keys=True),flush=True)
if __name__=="__main__":main()
