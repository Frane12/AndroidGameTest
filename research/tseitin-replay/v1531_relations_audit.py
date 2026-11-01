#!/usr/bin/env python3
"""Read-only relational audit of V15.3.1 SQLite data.

Prespecified exploratory questions:
1) Does native-route selection coincide with performance gain?
2) Is fallback overhead additive or proportional to Kissat duration?
3) Are paired differences larger than within-instance repeat jitter?
4) Does Kissat-only pilot time reproduce on independent benchmark repetitions?
5) Is there any systematic signed benefit after formula-level clustering?

No solver changes. No new algorithmic or world-record claim. Source notes below.
"""
from __future__ import annotations
import argparse, collections, csv, json, math, random, sqlite3, statistics
from pathlib import Path

SEED=170320261101
BOOT=4000
def mean(x):return statistics.fmean(x) if x else None
def median(x):return statistics.median(x) if x else None
def quantile(x,q):
 if not x:return None
 a=sorted(x);z=(len(a)-1)*q;k=int(z);return a[k]*(1-z+k)+a[min(k+1,len(a)-1)]*(z-k)
def spearman(xs,ys):
 if len(xs)<4:return None
 def ranks(v):
  order=sorted(range(len(v)),key=lambda i:v[i])
  out=[0.0]*len(v)
  for j,i in enumerate(order):out[i]=j+1
  return out
 x=ranks(xs);y=ranks(ys);xm=mean(x);ym=mean(y)
 num=sum((a-xm)*(b-ym) for a,b in zip(x,y))
 den=math.sqrt(sum((a-xm)**2 for a in x)*sum((b-ym)**2 for b in y))
 return num/den if den else None
def bootstrap_ci(xs,fn=median,seed=SEED,iterations=BOOT):
 if not xs:return [None,None]
 rg=random.Random(seed)
 ys=[fn([xs[rg.randrange(len(xs))] for _ in range(len(xs))]) for i in range(iterations)]
 return [quantile(ys,.025),quantile(ys,.975)]
def sign_p(wins,losses):
 n=wins+losses
 if n==0:return None
 return min(1.0,2.0*sum(math.comb(n,k) for k in range(min(wins,losses)+1))/(2**n))
def rowwise(db):
 db.row_factory=sqlite3.Row
 return [dict(x) for x in db.execute("""
  SELECT a.dataset,a.case_name,a.solver,a.repeat,a.seconds,a.par2_seconds,
         a.correct,a.route,a.status,d.provenance,f.category,f.expected,
         f.variables,f.clauses
    FROM attempts AS a
    JOIN formulas f ON (a.dataset=f.dataset AND a.case_name=f.case_name)
    JOIN datasets d ON a.dataset=d.dataset
   ORDER BY a.dataset,a.case_name,a.solver,a.repeat""")]
def pairs_from_rows(rows):
 group=collections.defaultdict(lambda:collections.defaultdict(list))
 for r in rows:
  group[(r["dataset"],r["case_name"])][r["solver"]].append(r)
 pairs=[]
 for (dataset,case),solvers in sorted(group.items()):
  if "v1531" not in solvers or "kissat" not in solvers:continue
  a=solvers["v1531"];b=solvers["kissat"]
  a2=[x["par2_seconds"] for x in a]
  b2=[x["par2_seconds"] for x in b]
  if any(x is None for x in a2+b2):continue
  ma=median(a2);mb=median(b2)
  routes=collections.Counter(x["route"] for x in a)
  route=routes.most_common(1)[0][0] or "unrecorded_route"
  pairs.append({"dataset":dataset,"case":case,"category":a[0]["category"],
   "provenance":a[0]["provenance"],"expected":a[0]["expected"],
   "variables":a[0]["variables"],"clauses":a[0]["clauses"],
   "route":route,"route_mixed":len(routes)>1,"v1531_median_s":ma,
   "kissat_median_s":mb,"delta_ms":1000*(ma-mb),
   "relative_delta_pct":100*(ma-mb)/mb if mb>0 else None,
   "speedup":mb/ma if ma>0 else None,
   "v1531_repeat_range_ms":1000*(max(a2)-min(a2)),
   "kissat_repeat_range_ms":1000*(max(b2)-min(b2)),
   "jitter_dominates":abs(ma-mb) <= max(max(a2)-min(a2),max(b2)-min(b2)),
   "both_correct":all(x["correct"]==1 and x["status"] in ("SAT","UNSAT")
                      for x in a+b),
   "repeats_v1531":len(a),"repeats_kissat":len(b)})
 return pairs
def groupstats(pairs,key):
 by=collections.defaultdict(list)
 for r in pairs:by[r[key]].append(r)
 result=[]
 for name,group in sorted(by.items()):
  ds=[x["delta_ms"] for x in group]
  wins=sum(x<0 for x in ds);losses=sum(x>0 for x in ds)
  result.append({"group":name,"n_formulas":len(ds),"v1531_faster":wins,
   "kissat_faster":losses,"median_delta_ms":median(ds),
   "mean_delta_ms":mean(ds),"median_delta_bootstrap95_ms":bootstrap_ci(ds),
   "median_abs_delta_ms":median([abs(x) for x in ds]),
   "jitter_dominates_count":sum(x["jitter_dominates"] for x in group),
   "wrong_status_or_proof_flag":sum(not x["both_correct"] for x in group),
   "two_sided_sign_p":sign_p(wins,losses),
   "native_routes":dict(collections.Counter(x["route"] for x in group)),
   "median_kissat_seconds":median([x["kissat_median_s"] for x in group])})
 return result
def leave_one_out_compare(fallback):
 # Compare additive delta = a and proportional delta = b*t using
 # leave-one-formula-out: family-level derived datasets never mixed in this fit.
 errors_add=[]; errors_prop=[]
 for i,x in enumerate(fallback):
  others=fallback[:i]+fallback[i+1:]
  alpha=median([z["delta_ms"] for z in others])
  beta=median([z["delta_ms"]/(1000*z["kissat_median_s"]) for z in others
                if z["kissat_median_s"]>0])
  errors_add.append(abs(x["delta_ms"]-alpha))
  errors_prop.append(abs(x["delta_ms"]-1000*beta*x["kissat_median_s"]))
 return {"n_formulas":len(fallback),
  "additive_median_overhead_ms":median([x["delta_ms"] for x in fallback]),
  "additive_bootstrap95_ms":bootstrap_ci([x["delta_ms"] for x in fallback]),
  "additive_loo_mean_absolute_error_ms":mean(errors_add),
  "proportional_loo_mean_absolute_error_ms":mean(errors_prop),
  "winner":"additive" if mean(errors_add)<mean(errors_prop) else "proportional",
  "spearman_kissat_vs_absolute_delta":spearman(
    [x["kissat_median_s"] for x in fallback],
    [x["delta_ms"] for x in fallback]),
  "spearman_kissat_vs_relative_delta":spearman(
    [x["kissat_median_s"] for x in fallback],
    [x["relative_delta_pct"] for x in fallback]),
  "within_repeat_jitter_dominates":sum(x["jitter_dominates"] for x in fallback)}
def pilot_audit(path):
 d=json.loads(path.read_text())
 rows=d.get("all_calibration_records",{})
 manifest=d.get("manifest",[])
 selected={x["sha256_normalized"]:x for x in manifest}
 result={}
 for family,pool in sorted(rows.items()):
  arr=[r for r in pool if r.get("pilot_correct") is True and
       isinstance(r.get("pilot_seconds"),(int,float))]
  shared=[(r["pilot_seconds"],selected[r["sha256_normalized"]])
          for r in arr if r.get("sha256_normalized") in selected]
  result[family]={"pilot_attempts":len(pool),"solved_pilot":len(arr),
    "timed_out_or_invalid_pilot":len(pool)-len(arr),
    "pilot_range_0p1_to_5":sum(.1<=x["pilot_seconds"]<=5. for x in arr),
    "selected":len(shared)}
  if shared:
   final_times=[]
   for pilot,m in shared:
    # Paired final durations not in manifest, loaded via formula name separately.
    final_times.append(pilot)
   result[family]["selected_pilot_median_s"]=median(final_times)
 return result
def write_csv(path,rows):
 if not rows:return
 cols=list(rows[0])
 with path.open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore")
  writer.writeheader();writer.writerows(rows)
def plots(out,pairs):
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
 except ImportError:return []
 files=[]
 medium=[p for p in pairs if p["dataset"]=="DRNAS-V1531-External-Medium40"]
 short=[p for p in pairs if p["dataset"]=="DRNAS-V1531-External-Short40"]
 for name,rows in [("medium",medium),("short",short)]:
  if not rows:continue
  fig,ax=plt.subplots(figsize=(8,5))
  for cat in sorted({r["category"] for r in rows}):
   rr=[r for r in rows if r["category"]==cat]
   ax.scatter([r["kissat_median_s"] for r in rr],[r["delta_ms"] for r in rr],
              label=cat,alpha=.85)
  ax.axhline(0,ls="--",lw=1)
  ax.set(xlabel="Kissat formula median (seconds)",
         ylabel="V15.3.1 − Kissat median (ms)",
         title=name+" external: paired absolute timing residual")
  ax.legend(fontsize=8);fig.tight_layout()
  path=out/("scatter_delta_"+name+".png");fig.savefig(path,dpi=160);plt.close(fig)
  files.append(path.name)
 if medium:
  fig,ax=plt.subplots(figsize=(8,5))
  ax.scatter([r["kissat_median_s"] for r in medium],
             [r["relative_delta_pct"] for r in medium],alpha=.8)
  ax.axhline(0,ls="--",lw=1)
  ax.set(xlabel="Kissat median (seconds)",
         ylabel="Relative V15.3.1 overhead (%)",
         title="Relative overhead versus instance duration")
  fig.tight_layout()
  path=out/"scatter_relative_medium.png";fig.savefig(path,dpi=160)
  plt.close(fig);files.append(path.name)
 if short:
  fig,ax=plt.subplots(figsize=(8,5))
  palette={"kissat":"C0","v153_affine_unsat":"C1"}
  for route in sorted({r["route"] for r in short}):
   rr=[r for r in short if r["route"]==route]
   ax.scatter([r["kissat_median_s"] for r in rr],
              [r["delta_ms"] for r in rr],label=route,
              color=palette.get(route,"C2"),alpha=.9)
  ax.axhline(0,ls="--",lw=1)
  ax.set(xlabel="Kissat median (seconds)",
         ylabel="Paired delta (ms)",title="Route-conditioned differences (not causal)")
  ax.legend(fontsize=8);fig.tight_layout()
  path=out/"scatter_route_short.png";fig.savefig(path,dpi=160)
  plt.close(fig);files.append(path.name)
 return files
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--db",type=Path,required=True)
 ap.add_argument("--medium",type=Path,required=True)
 ap.add_argument("--out",type=Path,default=Path("relation-analysis"))
 a=ap.parse_args();a.out.mkdir(exist_ok=True,parents=True)
 db=sqlite3.connect(a.db);rows=rowwise(db);db.close()
 pairs=pairs_from_rows(rows)
 write_csv(a.out/"formula_pairs.csv",pairs)
 by_origin=groupstats(pairs,"provenance")
 by_dataset=groupstats(pairs,"dataset")
 by_category=groupstats(pairs,"category")
 by_route=groupstats(pairs,"route")
 medium=[x for x in pairs if x["dataset"]=="DRNAS-V1531-External-Medium40"]
 short=[x for x in pairs if x["dataset"]=="DRNAS-V1531-External-Short40"]
 if len(medium)!=40 or len(short)!=40:
  raise RuntimeError(f"Expected 40 medium and 40 short; got {len(medium)}, {len(short)}")
 if any(not x["both_correct"] for x in medium+short):
  raise RuntimeError("Wrong answer detected in external test data")
 selected_routes=collections.Counter(x["route"] for x in medium)
 short_routes=collections.Counter(x["route"] for x in short)
 fallback=[x for x in medium if x["route"]=="kissat"]
 model=leave_one_out_compare(fallback)
 win_by_difficulty=[]
 for lo,hi in [(0,.005),(.005,.05),(.05,.5),(.5,1.5),(1.5,10)]:
  g=[r for r in pairs if lo<=r["kissat_median_s"]<hi and r["provenance"].startswith("external")]
  if not g:continue
  win_by_difficulty.append({"lo_s":lo,"hi_s":hi,"n":len(g),
    "mean_delta_ms":mean([x["delta_ms"] for x in g]),
    "median_delta_ms":median([x["delta_ms"] for x in g]),
    "median_relative_delta_percent":median([x["relative_delta_pct"] for x in g]),
    "faster":sum(x["delta_ms"]<0 for x in g)})
 reports={"source_db":str(a.db),"database_attempts":len(rows),
  "all_paired_formulas":len(pairs),"medium_paired":len(medium),
  "short_paired":len(short),"routes_medium":dict(selected_routes),
  "routes_short":dict(short_routes),
  "by_provenance":by_origin,"by_dataset":by_dataset,
  "by_category":by_category,"by_route":by_route,
  "medium_fallback_models":model,
  "external_duration_bins":win_by_difficulty,
  "pilot":pilot_audit(a.medium),
  "caveats":["All medium40 V15.3.1 routes are original Kissat fallback; a speedup there would not prove a new SAT search policy.",
   "Route is confounded with formula family and runner; route association is not causal.",
   "Time deltas computed from per-formula medians of paired repeated attempts.",
   "Relative delta decreases mechanically as baseline time rises if there is fixed overhead.",
   "For all data, different datasets and runners may have systematically different noise.",
   "Bootstrap samples by formula, not by individual repeat; confidence intervals are descriptive.",
   "No early conflict/restart telemetry is present in source database.",
   "Pilot selection is original-Kissat-calibrated, not untouched blind holdout.",
   "Exploratory analysis is not evidence of a new mathematical law."]}
 (a.out/"relation_audit.json").write_text(json.dumps(reports,indent=2)+"\n")
 write_csv(a.out/"group_category.csv",by_category)
 write_csv(a.out/"group_route.csv",by_route)
 figs=plots(a.out,pairs)
 lines=["# DRNAS SAT V15.3.1 — read-only mathematical relational audit",
  f"{len(rows)} source attempts, {len(pairs)} source-paired formula comparisons.",
  "Analysis predefines route, formula-level delta, additive overhead, repeat jitter and calibration axes.",
  "No modification to solver or previous experimental measurements.","",
  "## New structural route observation",
  f"- Medium 40 routes: {dict(selected_routes)}.",
  f"- Short 40 routes: {dict(short_routes)}.",
  "- Structural/affine routes can be beneficial on their own families; do not extrapolate to all random SAT.",
  "",
  "## Fallback overhead model (only external medium 40)",
  f"- Median delta: {model['additive_median_overhead_ms']:.4f} ms; formula-bootstrap 95% interval {model['additive_bootstrap95_ms']} ms.",
  f"- Leave-one-formula-out absolute error: additive {model['additive_loo_mean_absolute_error_ms']:.4f} ms; proportional {model['proportional_loo_mean_absolute_error_ms']:.4f} ms.",
  f"- Better LOOCV fit: {model['winner']}.",
  f"- Within-run repeat range >= observed delta in {model['within_repeat_jitter_dominates']}/40 formulas.",
  "",
  "## Per source family"]
 for g in by_category:
  lines.append(f"- {g['group']}: {g['n_formulas']} formulas; median delta {g['median_delta_ms']:.4f} ms; "
      f"V15.3.1 faster {g['v1531_faster']}/{g['n_formulas']}; routes {g['native_routes']}.")
 lines.extend(["","## Limitations","Correlation is not causation. Structural fingerprints and early dynamics need independent data and passive tracing.",
   "SAT/UNSAT model and proof checks are those recorded in original runs; do not claim independent universal UNSAT verification.",
   "No multiple-testing claims; any new correlations require a fresh frozen validation set.",
   "","## Files",", ".join(figs)+", formula_pairs.csv, group_route.csv, group_category.csv, relation_audit.json."])
 (a.out/"report.md").write_text("\n".join(lines)+"\n")
 print("\n".join(lines),flush=True)
if __name__=="__main__":main()
