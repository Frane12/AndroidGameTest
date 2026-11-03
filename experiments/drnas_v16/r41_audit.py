#!/usr/bin/env python3
"""R41 strict audit of checkpoint/action traces on solved and timed-out trials."""
import argparse,hashlib,json,random
from pathlib import Path
from r41_checkpoint_probe import CASES,MODES,REPS,CAP
PREFIX=("stage1","extended","quality","learned","lbd2","lbd4",
        "props","conflicts","backtracks","hints","learned_delta","threshold")
def mean(a):return sum(a)/len(a)
def par2(r):return float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 2*CAP
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--root",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 man=Path(a.manifest);m=json.loads(man.read_text())
 original={x["id"]:x for x in m["cases"]}
 assert len(original)==12 and all(c in original for c in CASES)
 sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
 rows=[];binaries=set();unknown=0;known=0;paired_prefix=0
 for i,id in enumerate(CASES):
  root=Path(a.root)/("r41-case-"+str(i))/"results"
  meta=json.loads((root/"meta.json").read_text())
  assert meta["id"]==id and meta["original_manifest_sha256"]==sha(man)
  assert meta["n_trials"]==len(MODES)*REPS
  assert meta["cap_s"]==CAP and tuple(meta["modes"])==MODES
  binaries.add(meta["bin_sha256"])
  data=json.loads((root/"trials.json").read_text())
  assert len(data)==REPS*len(MODES)
  for r in data:
   assert r["id"]==id and r["sha256"]==original[id]["sha256"]
   assert r["label"]==original[id]["official_label"]
   assert int(r["rep"]) in range(REPS) and r["mode"] in MODES
   assert r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"],r
   assert float(r["cap_s"])==CAP and float(r["wall_s"])>=0
   assert r["seed"]==(830031+int(original[id]["sha256"][:8],16)+int(r["rep"])*101)%2**32
   if r["status"]!="TIMEOUT":assert r["status"]==r["label"]
   if r["checkpoint"]:
    q=r["checkpoint"];known+=1
    assert q["stage1"]=="0",r
    L=int(q["learned"]);C=int(q["conflicts"]);P=int(q["props"])
    short=int(q["lbd2"])
    assert L>=0 and C>0 and P>=0 and 0<=short<=L
    quality=(L>=20 and 100*short>=6*L and P>=32*C)
    assert int(q["quality"])==int(quality)
    if r["before_resume"]:
     z=r["before_resume"]
     assert z["quality"]==q["quality"] and z["extended"]==q["extended"]
     if r["mode"]=="v91_rescue" and z["reason"]=="r40_rescue_fallback":
      assert q["quality"]=="1" and q["extended"]=="0" and int(q["hints"])>0 and z["phase_applied"]=="1"
     if r["mode"]=="v91_force_fallback" and z["reason"]=="r40_forced_fallback":
      assert q["extended"]=="0" and int(q["hints"])>0 and z["phase_applied"]=="1"
   else:unknown+=1
   rows.append(r)
 assert len(rows)==len(CASES)*REPS*len(MODES)
 assert len(binaries)==1,"different native binary sha across shards"
 lookup={(r["id"],r["rep"],r["mode"]):r for r in rows}
 assert len(lookup)==len(rows)
 examples=[]
 for id in CASES:
  for rep in range(REPS):
   rr=[lookup[id,rep,mode] for mode in MODES]
   cps=[r["checkpoint"] for r in rr]
   if all(cps):
    assert all(tuple(cp.get(k) for k in PREFIX)==tuple(cps[0].get(k) for k in PREFIX)
               for cp in cps[1:]),("R41_NONIDENTICAL_PREFIX",id,rep,cps)
    paired_prefix+=1
   examples.append(dict(id=id,rep=rep,checkpoint_count=sum(cp is not None for cp in cps),
      prefix_valid=(True if all(cps) else None),
      early_quality=cps[0]["quality"] if all(cps) else None))
 by_mode={}
 for mode in MODES:
  data=[r for r in rows if r["mode"]==mode]
  by_mode[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in data),
    timeouts=sum(r["status"]=="TIMEOUT" for r in data),
    mean_PAR2_s=mean([par2(r) for r in data]),
    checkpoint_seen=sum(bool(r["checkpoint"]) for r in data),
    actions_before_resume=sum(bool(r["before_resume"] and r["before_resume"].get("phase_applied")=="1")
      for r in data),
    new_early_fallback_actions=sum(bool(r["before_resume"] and
         r["before_resume"].get("reason") in ("r40_rescue_fallback","r40_forced_fallback"))
         for r in data))
 by_case=[]
 for id in CASES:
  data={mode:[lookup[id,rep,mode] for rep in range(REPS)] for mode in MODES}
  times={mode:mean([par2(x) for x in records]) for mode,records in data.items()}
  by_case.append(dict(id=id,label=original[id]["official_label"],PAR2=times,
    checkpoint_seen=sum(bool(x["checkpoint"]) for x in sum([list(v) for v in data.values()],[])),
    rescue_fallback_actions=sum(bool(x["before_resume"] and
       x["before_resume"].get("reason")=="r40_rescue_fallback") for x in data["v91_rescue"])))
 base="v91_quality_gate";active="v91_rescue"
 def pct(indices):
  b=mean([by_case[i]["PAR2"][base] for i in indices])
  d=mean([by_case[i]["PAR2"][active]-by_case[i]["PAR2"][base] for i in indices])
  return 100*d/b if b else 0
 delta=pct(range(len(CASES)))
 rng=random.Random(414141);bootstrap=sorted(pct([rng.randrange(4) for _ in range(4)]) for _ in range(2000))
 report=dict(protocol="R41_SMALL_RETROSPECTIVE_OFFICIAL_CHECKPOINT_AUDIT",
  source_manifest_sha256=sha(man),native_binary_sha256=next(iter(binaries)),
  n_official_cases=4,n_trials=len(rows),checkpoint_visible=known,
  checkpoint_not_reached_or_unseen=unknown,paired_identical_prefix=paired_prefix,
  n_pairs=8,mode_summaries=by_mode,formulas=by_case,prefix_cases=examples,
  rescue_vs_v91_gate_pct=delta,
  bootstrap_95_pct_by_formula=[bootstrap[49],bootstrap[1949]],
  limitations=["R37 previously seen official CNFs, not a new blind holdout",
   "Small paired diagnostic: 4 formulas x 2 seeds, no general performance claim",
   "Missing checkpoint means no evidence it was reached before timeout",
   "No standalone UNSAT proof artifact, native solver unchanged certification checks",
   "V15.3.1 unchanged, no new world record claim"])
 Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
 print("R41_AUDIT_PASS",json.dumps({k:v for k,v in report.items() if k in
  ("n_official_cases","n_trials","checkpoint_visible","checkpoint_not_reached_or_unseen",
   "paired_identical_prefix","n_pairs","rescue_vs_v91_gate_pct","bootstrap_95_pct_by_formula")},sort_keys=True),flush=True)
 print("R41_MODE_SUMMARY",json.dumps(by_mode,sort_keys=True),flush=True)
 for x in by_case:print("R41_CASE",json.dumps(x,sort_keys=True),flush=True)
if __name__=="__main__":main()
