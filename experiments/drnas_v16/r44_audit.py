#!/usr/bin/env python3
"""R44 strict SHA/paired prospective official quality-dose holdout audit."""
import argparse,hashlib,json,random
from pathlib import Path
from r44_benchmark import MODES,CAP,REPS,FINGERPRINT,expected_dose
def mean(vals):return sum(vals)/len(vals)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--combined",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args();mp=Path(a.manifest);m=json.loads(mp.read_text())
 assert m["protocol"]=="R44-FROZEN-QUALITY-DOSE-20261103-V1"
 assert len(m["cases"])==8
 known={c["id"]:c for c in m["cases"]}
 assert len(known)==len({c["sha256"] for c in m["cases"]})==8
 assert not set(known).intersection(m["excluded_prior_ids"])
 assert not {c["sha256"] for c in m["cases"]}.intersection(m["excluded_prior_sha256"])
 sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 allrows=[];binset=set();prefix_checked=0;prefix_missing=0
 activations={mode:0 for mode in MODES}
 for shard in range(4):
  folder=Path(a.combined)/f"r44-shard-{shard}"/"results"
  meta=json.loads((folder/"meta.json").read_text())
  assert meta["shard"]==shard and meta["manifest_sha256"]==sha(mp)
  assert meta["protocol"]==m["protocol"]
  assert float(meta["cap_s"])==CAP and int(meta["reps"])==REPS
  assert tuple(meta["modes"])==MODES
  assert meta["source_case_ids"]==[c["id"] for c in m["cases"][2*shard:2*shard+2]]
  binset.add(tuple(sorted(meta["binary_sha256"].items())))
  rows=json.loads((folder/"trials.json").read_text())
  assert len(rows)==2*REPS*len(MODES)
  for r in rows:
   c=known[r["id"]]
   assert r["sha256"]==c["sha256"] and r["official_label"]==c["official_label"]
   assert r["mode"] in MODES and r["rep"] in range(REPS)
   assert r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"]
   if r["status"]!="TIMEOUT":assert r["status"]==c["official_label"]
   expectedseed=(441144+int(c["sha256"][:8],16)+r["rep"]*103)%2**32
   assert r["seed"]==expectedseed
   assert float(r["PAR2_s"])>=0 and float(r["wall_s"])>=0
   if r["status"]=="TIMEOUT":assert r["PAR2_s"]==2*CAP
   else:assert abs(float(r["PAR2_s"])-float(r["wall_s"]))<1e-8
   cp=r["checkpoint"];act=r["before_resume"]
   if r["mode"]=="kissat_pinned":
    assert cp is None and act is None and r["actual_early_hints"]==0
   else:
    if act:
     assert cp is not None and act["extended"]==cp["extended"]
     if r["mode"]=="v91_adaptive":
      assert r["actual_early_hints"]==min(expected_dose(cp),int(cp["hints"]))
     elif r["mode"]=="v91_cap32":
      assert r["actual_early_hints"]==(min(32,int(cp["hints"])) if cp["extended"]=="0" and cp["quality"]=="1" else 0)
     else:assert r["actual_early_hints"]==0
    else:assert r["actual_early_hints"]==0
   activations[r["mode"]]+=int(r["actual_early_hints"]>0)
  allrows.extend(rows)
 assert len(binset)==1 and len(allrows)==8*REPS*len(MODES)
 lut={(r["id"],r["rep"],r["mode"]):r for r in allrows}
 assert len(lut)==len(allrows)
 assert set(lut)=={(cid,rep,mode) for cid in known for rep in range(REPS) for mode in MODES}
 cases=[]
 for cid,c in known.items():
  per_mode={}
  for mode in MODES:
   rs=[lut[(cid,rep,mode)] for rep in range(REPS)]
   per_mode[mode]=dict(mean_PAR2_s=mean([r["PAR2_s"] for r in rs]),
       solved=sum(r["status"]!="TIMEOUT" for r in rs),
       statuses=[r["status"] for r in rs],
       early_doses=[r["actual_early_hints"] for r in rs])
  for rep in range(REPS):
   n=[lut[(cid,rep,mode)] for mode in MODES if mode!="kissat_pinned"]
   cps=[r["checkpoint"] for r in n]
   if all(cps):
    assert len({tuple(cp.get(k) for k in FINGERPRINT) for cp in cps})==1,("EARLY_PREFIX_DRIFT",cid,rep)
    prefix_checked+=1
   else:prefix_missing+=1
  cases.append(dict(id=cid,label=c["official_label"],features=c["features"],
     preselected_official_runtime_s=c["sampling_only_official_cadical_runtime_s"],
     modes=per_mode,adaptive_activation=sum(x>0 for x in per_mode["v91_adaptive"]["early_doses"])))
 bymode={}
 for mode in MODES:
  rs=[r for r in allrows if r["mode"]==mode]
  bymode[mode]=dict(mean_PAR2_s=mean([r["PAR2_s"] for r in rs]),
    sum_PAR2_s=sum(r["PAR2_s"] for r in rs),
    solved=sum(r["status"]!="TIMEOUT" for r in rs),
    timeout=sum(r["status"]=="TIMEOUT" for r in rs),
    active_early_rescue=activations[mode])
 base=bymode["v91_quality_gate"]["mean_PAR2_s"]
 for mode in MODES:
  bymode[mode]["pct_vs_v91_positive_is_regression"]=100*(bymode[mode]["mean_PAR2_s"]/base-1)
 def bootstrap(mode):
  rng=random.Random(440044)
  vals=[]
  for _ in range(4000):
   ix=[rng.randrange(len(cases)) for j in cases]
   b=mean([cases[i]["modes"]["v91_quality_gate"]["mean_PAR2_s"] for i in ix])
   v=mean([cases[i]["modes"][mode]["mean_PAR2_s"] for i in ix])
   vals.append(100*(v/b-1) if b else 0)
  vals.sort()
  return [vals[100],vals[3899]]
 ci={mode:bootstrap(mode) for mode in ("v91_cap32","v91_adaptive")}
 report=dict(protocol=m["protocol"],eight_sha_distinct_official_cases=8,
    n_native_and_kissat_trials=len(allrows),repetitions=REPS,
    case_fingerprints_identical=prefix_checked,
    paired_prefix_unverified_if_one_missed=prefix_missing,
    dose_activations=activations,
    original_manifest_sha256=sha(mp),binary_fingerprints=dict(next(iter(binset))),
    modes=bymode,cases=cases,
    bootstrap_95_pct_by_formula=ci,
    limitations=["Precommit from prior R41-R43 signal and thresholds, but small published official selected sample",
      "NOT guaranteed unseen relative to all prior DRNAS work (excluded 38 known official originals only)",
      "Public official CaDiCaL runtime used for candidate selection; sample not representative",
      "If adaptive activation count is zero the test cannot validate its usefulness",
      "2 repetitions/case and shared GitHub hosted environment, wide statistical uncertainty",
      "PAR2 timeout penalty is 30s; cannot claim completion time for censored runs",
      "Solver SAT output checked; official UNSAT label comparison but no proof certificate",
      "No after-the-fact threshold changes or general SAT speedup/record claim"])
 Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
 print("R44_AUDIT_PASS",json.dumps({k:report[k] for k in
   ("eight_sha_distinct_official_cases","n_native_and_kissat_trials",
    "case_fingerprints_identical","paired_prefix_unverified_if_one_missed",
    "dose_activations","bootstrap_95_pct_by_formula")},sort_keys=True),flush=True)
 print("R44_MODE_SUMMARY",json.dumps(bymode,sort_keys=True),flush=True)
 for c in cases:
  print("R44_CASE",c["id"][:8],c["label"],
      "PAR2",json.dumps({k:round(v["mean_PAR2_s"],4) for k,v in c["modes"].items()},sort_keys=True),
      "adaptive_doses",c["modes"]["v91_adaptive"]["early_doses"],flush=True)
if __name__=="__main__":main()
