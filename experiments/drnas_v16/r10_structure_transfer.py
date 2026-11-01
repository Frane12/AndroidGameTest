#!/usr/bin/env python3
"""DRNAS R10 frozen structure-to-action experiment.

Reads structural features before solving. Selective action uses ONLY predeclared
variable-degree CV/Gini rule; no adaptive fitting, outcome peeking or solver changes.
Original Kissat / frozen V15.3.1 / monitor / forced / structural chooser are paired.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random,statistics,subprocess
from collections import defaultdict
from pathlib import Path
import r7_large as base

FROZEN_SOURCE="6f70bb18664cffa2608a94c6fe7c1542cd576511"
PIN_KISSAT=base.PIN_KISSAT
PIN_STABLE_BLOB=base.PIN_STABLE_BLOB
CAP=base.CAP
REPEATS=3
NS=(200,220,240)
FOLDS=("development","test")
SHARDS=tuple(f"n{n}_{fold}{part}" for n in NS for fold in FOLDS for part in range(2))
MODES=("original_kissat","stable_v1531","monitor","forced_restart25","structure_gate")
OUT=Path("drnas-r10-results")
REGISTRY=Path("experiments/drnas_v16/r10_prior_registry_sha256.txt")
GATE_SPEC={"type":"degree_skew_high","degree_cv_gte":0.285,"degree_gini_gte":0.158,
           "action":"same in-process switch2048/restartint25 as frozen R7","else":"r5_monitor"}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def csv_write(path,rows):
 if not rows:raise RuntimeError("No rows")
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]))
  w.writeheader();w.writerows(rows)
def make_features(clauses,n):
 degrees=[0]*n;positive=[0]*n;negative=[0]*n
 for cl in clauses:
  for lit in cl:
   i=abs(lit)-1
   degrees[i]+=1
   (positive if lit>0 else negative)[i]+=1
 mu=sum(degrees)/n
 cv=(sum((d-mu)**2 for d in degrees)/n)**.5/mu if mu else 0.
 ordered=sorted(degrees)
 gini=sum((2*i-n-1)*v for i,v in enumerate(ordered,1))/(n*sum(ordered)) if mu else 0.
 polarity=sum(abs(positive[i]-negative[i]) for i in range(n))/max(1,sum(degrees))
 return dict(n=n,m=len(clauses),density=len(clauses)/n,degree_cv=cv,
    degree_gini=gini,degree_min=min(degrees),degree_max=max(degrees),
    polarity_imbalance=polarity)
def eligible(f):
 return f["degree_cv"]>=GATE_SPEC["degree_cv_gte"] and f["degree_gini"]>=GATE_SPEC["degree_gini_gte"]
def make_cases(shard,folder,registry):
 n=int(shard[1:4]);fold="development" if "_development" in shard else "test"
 part=int(shard[-1]);out=[]
 # Two disjoint deterministic streams; new formulas are not outcome-selected.
 for j in range(10):
  i=20*NS.index(n)+10*part+j+(0 if fold=="development" else 100)
  seed=221100000+n*10000+i
  rng=random.Random(seed)
  m=round(4.23*n)
  clauses=[]
  for _ in range(m):
   vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  features=make_features(clauses,n)
  selected=eligible(features)
  name=f"r10_{n}_{fold}_{part}_{j:02d}.cnf"
  case=base.emit_cnf(folder,name,n,clauses,"UNKNOWN","generated_prospective",
       "DRNAS R10 prospectively frozen 3-SAT generator","r10-structure-transfer-v1",
       {"seed":seed,"fold":fold,"structural":features,"structure_gate_selected":selected})
  if case["formula_sha256"] in registry:
   raise RuntimeError("R10 SHA collision with historical registry: "+name)
  case["category"]=shard
  out.append(case)
 if len({c["formula_sha256"] for c in out})!=10:raise RuntimeError("Duplicate CNF in shard")
 return out
def run_shard(shard):
 folder=OUT/shard;folder.mkdir(parents=True,exist_ok=True)
 registry={line.strip() for line in REGISTRY.read_text().splitlines() if len(line.strip())==64 and all(x in "0123456789abcdef" for x in line.strip().lower())}
 if len(registry)<1200:raise RuntimeError("Registry unexpectedly short")
 cases=make_cases(shard,folder,registry)
 runner=os.environ.get("RUNNER_NAME","unknown")+" / "+platform.processor()
 fold=cases[0]["metadata"]["fold"]
 manifest={"category":shard,"fold":fold,"provenance":"prospectively_generated_dev" if fold=="development" else "prospectively_generated_reserved_test",
  "source_commit":os.environ.get("GITHUB_SHA","local"),"source_revision":FROZEN_SOURCE,
  "kissat_pin":PIN_KISSAT,"stable_blob":PIN_STABLE_BLOB,
  "cap_seconds":CAP,"repeats":REPEATS,"modes":MODES,"gate":GATE_SPEC,
  "runner":runner,"cpu_affinity":sorted(os.sched_getaffinity(0)),
  "platform":platform.platform(),"registry_sha256":sha(REGISTRY),
  "executables":{"kissat_original":sha(base.ORIGINAL),"kissat_patched":sha(base.PATCHED),"stable_v1531":sha(base.STABLE)},
  "cases":[{k:(str(v) if isinstance(v,Path) else v) for k,v in c.items() if k!="clauses"} for c in cases]}
 dump(folder/"manifest.json",manifest)
 rows=[];traces=[]
 for case in cases:
  for rep in range(REPEATS):
   order=list(MODES)
   random.Random(310001+int(case["formula_sha256"][:12],16)+rep).shuffle(order)
   for mode in order:
    action="forced_restart25" if (mode=="structure_gate" and case["metadata"]["structure_gate_selected"]) else ("monitor" if mode=="structure_gate" else mode)
    row,trace=base.run_one(case,rep,action,runner)
    row["mode"]=mode;row["actual_execution"]=action
    row["structure_gate_selected"]=int(case["metadata"]["structure_gate_selected"])
    row["degree_cv"]=case["metadata"]["structural"]["degree_cv"]
    row["degree_gini"]=case["metadata"]["structural"]["degree_gini"]
    trace["mode"]=mode;trace["actual_execution"]=action
    rows.append(row);traces.append(trace)
    csv_write(folder/"measurements.partial.csv",rows)
    with (folder/"traces.partial.jsonl").open("a") as fp:fp.write(json.dumps(trace,sort_keys=True)+"\n")
    print("R10_MEASURE",shard,case["formula"],rep,mode,
         row["status"],row["par2_s"],"selected",row["structure_gate_selected"],flush=True)
    if row["error"]:
     dump(folder/"error.json",row)
     raise RuntimeError(row["error"])
  actual={r["status"] for r in rows if r["formula"]==case["formula"] and r["status"] in ("SAT","UNSAT")}
  if len(actual)>1:raise RuntimeError("SAT/UNSAT disagreement "+case["formula"])
 if len(rows)!=150:raise RuntimeError("Incomplete shard")
 csv_write(folder/"measurements.csv",rows)
 (folder/"traces.jsonl").write_text("".join(json.dumps(t,sort_keys=True)+"\n" for t in traces))
 print("R10_SHARD_COMPLETE",shard,len(rows),flush=True)

def quantile(xs,p):
 xs=sorted(xs)
 if not xs:return None
 k=(len(xs)-1)*p;j=int(k)
 return xs[j]*(1-(k-j))+xs[min(j+1,len(xs)-1)]*(k-j)
def bootstrap(rows,base_mode="monitor",treat_mode="structure_gate",seed=311011):
 by=defaultdict(lambda:defaultdict(float))
 for r in rows:
  key=(r["category"],r["formula"])
  by[key][r["mode"]]+=float(r["par2_s"])
 keys=list(by)
 formula_groups=defaultdict(list)
 for key in keys:formula_groups[key[0].split("_")[0]].append(key)
 rng=random.Random(seed);gains=[]
 for _ in range(4000):
  picked=[]
  for group,choices in formula_groups.items():
   picked.extend(choices[rng.randrange(len(choices))] for _ in choices)
  a=sum(by[k][base_mode] for k in picked);b=sum(by[k][treat_mode] for k in picked)
  gains.append((a-b)/a*100 if a else 0)
 return [quantile(gains,.025),quantile(gains,.975)]
def aggregate():
 rows=[];manifests=[];files=[]
 for shard in SHARDS:
  folder=Path("r10-download")/f"r10-{shard}"
  paths=[folder/"measurements.csv",folder/"manifest.json",folder/"traces.jsonl"]
  if not all(p.is_file() for p in paths):raise RuntimeError("Missing full shard "+shard)
  items=list(csv.DictReader(paths[0].open()))
  if len(items)!=150:raise RuntimeError("Incomplete shard "+shard)
  meta=json.loads(paths[1].read_text())
  if meta["stable_blob"]!=PIN_STABLE_BLOB or meta["kissat_pin"]!=PIN_KISSAT:raise RuntimeError("Solver pin mismatch")
  if meta["gate"]!=GATE_SPEC or len(meta["cases"])!=10:raise RuntimeError("Unfrozen gate/cases")
  if not meta["registry_sha256"]:raise RuntimeError("Registry provenance absent")
  for r in items:
   if r.get("error"):raise RuntimeError("Invalid SAT attempt "+r["formula"])
   if r["category"]!=shard:raise RuntimeError("Shard provenance mismatch")
  rows.extend(items)
  manifests.append(meta)
  files.append({"shard":shard,"measurements_sha256":sha(paths[0]),
      "manifest_sha256":sha(paths[1]),"traces_sha256":sha(paths[2])})
 if len(rows)!=1800:raise RuntimeError("Expected 1800 new solver executions")
 groups=defaultdict(list)
 for r in rows:groups[(r["category"],r["formula"],r["repeat"])].append(r)
 if len(groups)!=360 or any(len(grp)!=5 or len({r["mode"] for r in grp})!=5 for grp in groups.values()):
  raise RuntimeError("Incomplete/duplicate paired matrix")
 for k,grp in groups.items():
  if len({r["runner"] for r in grp})!=1 or len({r["formula_sha256"] for r in grp})!=1:
   raise RuntimeError("Unpaired SHA/runner "+str(k))
  status={r["status"] for r in grp if r["status"] in ("SAT","UNSAT")}
  if len(status)>1:raise RuntimeError("Contradictory solver outcomes "+str(k))
  modes={r["mode"]:r for r in grp}
  if (modes["structure_gate"]["actual_execution"]!=
     ("forced_restart25" if modes["structure_gate"]["structure_gate_selected"]=="1" else "monitor")):
   raise RuntimeError("Structural gate execution mismatch "+str(k))
 unique_sha={r["formula_sha256"] for r in rows}
 if len(unique_sha)!=120:raise RuntimeError("CNF collision across shards")
 out=OUT/"aggregate";out.mkdir(parents=True,exist_ok=True)
 csv_write(out/"measurements.csv",rows)
 records=[];paired=[]
 by=defaultdict(list)
 for r in rows:by[(r["category"],r["formula"])].append(r)
 for (shard,formula),rr in sorted(by.items()):
  modes=defaultdict(list)
  for r in rr:modes[r["mode"]].append(r)
  if any(len(modes[m])!=3 for m in MODES):raise RuntimeError("Partial formula")
  sums={m:sum(float(r["par2_s"]) for r in modes[m]) for m in MODES}
  first=rr[0];folder=next(mm for mm in manifests if mm["category"]==shard)
  info=next(c for c in folder["cases"] if c["formula"]==formula)
  struct=info["metadata"]["structural"];selected=info["metadata"]["structure_gate_selected"]
  for mode in MODES:
   if mode=="monitor":continue
   paired.append(dict(shard=shard,fold=folder["fold"],formula=formula,
    formula_sha256=first["formula_sha256"],mode=mode,selected=int(selected),
    cv=struct["degree_cv"],gini=struct["degree_gini"],
    monitor_par2=sums["monitor"],treatment_par2=sums[mode],
    speedup_vs_monitor=sums["monitor"]/sums[mode] if sums[mode] else 0,
    wins=sum(float(modes[mode][j]["par2_s"])<float(modes["monitor"][j]["par2_s"]) for j in range(3))))
  records.append(dict(shard=shard,fold=folder["fold"],formula=formula,sha=first["formula_sha256"],
    n=struct["n"],density=struct["density"],degree_cv=struct["degree_cv"],
    degree_gini=struct["degree_gini"],polarity_imbalance=struct["polarity_imbalance"],
    gate_selected=int(selected),monitor=sums["monitor"],forced=sums["forced_restart25"],
    gate=sums["structure_gate"],stable=sums["stable_v1531"],original=sums["original_kissat"],
    speedup_forced=sums["monitor"]/sums["forced_restart25"],
    speedup_gate=sums["monitor"]/sums["structure_gate"],
    monitor_early_p=statistics.median([float(x["early_p"]) for x in modes["monitor"] if x["early_p"] not in ("",None)]) if any(x["early_p"] not in ("",None) for x in modes["monitor"]) else "",
    observed_wins_gate=sum(float(modes["structure_gate"][j]["par2_s"])<float(modes["monitor"][j]["par2_s"]) for j in range(3))))
 csv_write(out/"paired.csv",paired);csv_write(out/"formula_features.csv",records)
 summary={}
 for fold in FOLDS:
  data=[r for r in rows if fold in r["category"]]
  tests=[r for r in records if r["fold"]==fold]
  total={m:sum(float(r["par2_s"]) for r in data if r["mode"]==m) for m in MODES}
  selected=[r for r in tests if r["gate_selected"]]
  unselected=[r for r in tests if not r["gate_selected"]]
  gains=(total["monitor"]-total["structure_gate"])/total["monitor"]*100
  # Bootstrap resamples independent formulas (not replicates) and preserves size strata.
  per_attempt=[r for r in data if r["mode"] in ("monitor","structure_gate","forced_restart25")]
  ci=bootstrap(per_attempt)
  summary[fold]=dict(formulas=len(tests),selected=len(selected),unselected=len(unselected),
     totals_par2=total,gate_gain_percent=gains,forced_gain_percent=
     100*(total["monitor"]-total["forced_restart25"])/total["monitor"],
     gate_gain_ci95_formula_bootstrap=ci,
     loss_formulas=sum(r["speedup_gate"]<.97 for r in tests),
     gain_formulas=sum(r["speedup_gate"]>1.03 for r in tests),
     selected_median_forced_speedup=statistics.median(r["speedup_forced"] for r in selected) if selected else None)
 result=dict(protocol="R10 frozen structure-gated Restart25",summary=summary,
   status="OBSERVATIONAL prospective experiment; no demonstrated general rule until independent validation",
   modes=MODES,gate=GATE_SPEC,count=len(rows),formula_count=len(records),
   raw_source_sha256=files,manifests=manifests,
   caution="Generated prospective random 3-SAT; not official SAT Competition. UNSAT lacks independent certificate.")
 dump(out/"results.json",result)
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fold in FOLDS:
   sub=[r for r in records if r["fold"]==fold]
   fig,ax=plt.subplots(figsize=(8,5))
   for selected in (0,1):
    x=[r for r in sub if r["gate_selected"]==selected]
    ax.scatter([r["degree_cv"] for r in x],
               [math.log2(max(1e-6,r["speedup_forced"])) for r in x],
               alpha=.65,label=("structural gate on" if selected else "structural gate off"))
   ax.axhline(0,ls="--",lw=1,color="black")
   ax.set(xlabel="Pre-solve variable-degree CV",
          ylabel="log2 forced-restart speedup vs monitor",
          title="R10 structural transfer — "+fold)
   ax.legend();fig.tight_layout()
   fig.savefig(out/("structure_scatter_"+fold+".png"),dpi=160);plt.close(fig)
 except ImportError:pass
 print("R10_AGGREGATE_COMPLETE",json.dumps({k:{x:v for x,v in d.items() if x!="totals_par2"} for k,d in summary.items()}))
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--category",choices=SHARDS)
 ap.add_argument("--aggregate",action="store_true");args=ap.parse_args()
 if args.aggregate:aggregate()
 elif args.category:run_shard(args.category)
 else:ap.error("Specify --category or --aggregate")
if __name__=="__main__":main()
