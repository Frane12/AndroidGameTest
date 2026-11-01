#!/usr/bin/env python3
"""R6 exploratory analysis on imported warehouse: formula-level correlations only.
Never treat three repeat timings as three independent problem instances.
"""
import argparse,csv,json,math,sqlite3,statistics
from collections import defaultdict,Counter
from pathlib import Path

MODES=("stable_v1531","monitor","forced_restart25","r5_frozen_gate")
FEATURES=("early_restarts","early_glue_ratio","early_prop_per_conflict","early_decisions_per_conflict")
def write_csv(path,rows,cols):
 with path.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore")
  w.writeheader();w.writerows(rows)
def ranks(seq):
 order=sorted(range(len(seq)),key=lambda i:seq[i])
 out=[0.0]*len(seq);i=0
 while i<len(seq):
  j=i+1
  while j<len(seq) and seq[order[j]]==seq[order[i]]:j+=1
  for k in range(i,j):out[order[k]]=(i+1+j)/2
  i=j
 return out
def corr(x,y):
 if len(x)<4 or len(x)!=len(y):return None
 a=statistics.mean(x);b=statistics.mean(y)
 xx=sum((p-a)**2 for p in x);yy=sum((p-b)**2 for p in y)
 if xx<1e-18 or yy<1e-18:return None
 return sum((p-a)*(q-b) for p,q in zip(x,y))/math.sqrt(xx*yy)
def med(x):return statistics.median(x)
def report(db,out):
 db.row_factory=sqlite3.Row
 data=[dict(x) for x in db.execute("""
 SELECT a.dataset,a.case_name,a.solver,a.repeat,a.par2_seconds,a.status,
 f.category, f.formula_sha256,
 m.early_restarts,m.early_glue_ratio,
 m.early_prop_per_conflict,m.early_decisions_per_conflict,
 m.switch_at,m.evidence_level
 FROM attempts a JOIN formulas f
  ON f.dataset=a.dataset AND f.case_name=a.case_name
 JOIN r6_attempt_features m
  ON m.dataset=a.dataset AND m.case_name=a.case_name
  AND m.solver=a.solver AND m.repeat=a.repeat
 WHERE a.dataset LIKE 'r6_%'
 """)]
 assert len(data)==480
 unique=defaultdict(lambda:defaultdict(list))
 for x in data:unique[(x["dataset"],x["case_name"])][x["solver"]].append(x)
 assert len(unique)==40
 medians=[]
 for (ds,cnf),groups in sorted(unique.items()):
  assert set(groups)==set(MODES) and all(len(groups[k])==3 for k in MODES)
  baseline=med([x["par2_seconds"] for x in groups["monitor"]])
  baseline_sig={}
  for feat in FEATURES:
   xx=[x[feat] for x in groups["monitor"] if x[feat] is not None]
   baseline_sig[feat]=med(xx) if xx else None
  for mode in MODES:
   candidates=groups[mode]
   treated=med([x["par2_seconds"] for x in candidates])
   medians.append(dict(dataset=ds,formula=cnf,mode=mode,
    monitor_par2=baseline,treated_par2=treated,
    speedup=round(baseline/treated,8),
    log_speedup=math.log(baseline/treated),
    intervention_repeats=sum(x["switch_at"] is not None for x in candidates),
    **baseline_sig))
 write_csv(out/"r6_formula_medians.csv",medians,list(medians[0]))
 summary=[]
 for cat in sorted({x["dataset"] for x in medians}):
  for mode in MODES:
   rows=[x for x in medians if x["dataset"]==cat and x["mode"]==mode]
   ctrl=sum(x["monitor_par2"] for x in rows)
   treated=sum(x["treated_par2"] for x in rows)
   deltas=[x["monitor_par2"]-x["treated_par2"] for x in rows]
   summary.append(dict(dataset=cat,mode=mode,n_distinct_formulas=len(rows),
    sum_formula_median_monitor=round(ctrl,7),
    sum_formula_median_treated=round(treated,7),
    speedup=round(ctrl/treated,7),
    median_paired_delta_s=round(med(deltas),7),
    intervention_repeats=sum(x["intervention_repeats"] for x in rows)))
 write_csv(out/"r6_category_summary.csv",summary,list(summary[0]))
 corr_rows=[]
 for mode in ("forced_restart25","r5_frozen_gate"):
  for feat in FEATURES:
   sample=[x for x in medians if x["mode"]==mode and x[feat] is not None]
   xx=[x[feat] for x in sample];yy=[x["log_speedup"] for x in sample]
   n=len(sample)
   corr_rows.append(dict(mode=mode,feature=feat,n_distinct_formulas=n,
    spearman_r=round(corr(ranks(xx),ranks(yy)),6)
      if corr(ranks(xx),ranks(yy)) is not None else None,
    pearson_r=round(corr(xx,yy),6) if corr(xx,yy) is not None else None,
    interpretation="exploratory only; no independent validation"
      if n>=8 else "insufficient independent formulas"))
 write_csv(out/"r6_feature_correlations.csv",corr_rows,list(corr_rows[0]))
 dynamics=[dict(x) for x in db.execute("""
 SELECT t.dataset,t.case_name,t.solver,t.repeat,t.event,t.conflicts,
 t.propagations,t.restarts,t.learned_clauses,
 g.glue_ratio,g.stable_mode,g.propagation_rate,
 g.propagation_rate_delta,g.propagation_curvature
 FROM telemetry t JOIN r6_checkpoint_features g
 ON g.dataset=t.dataset AND g.case_name=t.case_name AND
 g.solver=t.solver AND g.repeat=t.repeat AND g.event=t.event
 WHERE t.dataset LIKE 'r6_%'
 ORDER BY t.dataset,t.case_name,t.repeat,t.solver,t.event
 """)]
 assert dynamics
 write_csv(out/"r6_dynamics.csv",dynamics,list(dynamics[0]))
 after=[dict(x) for x in db.execute("SELECT * FROM r6_post_intervention ORDER BY dataset,case_name,repeat,treatment,checkpoint")]
 if after:write_csv(out/"r6_post_intervention.csv",after,list(after[0]))
 else:write_csv(out/"r6_post_intervention.csv",[],[
  "dataset","case_name","repeat","treatment","checkpoint",
  "delta_restarts","delta_decisions","delta_propagations",
  "delta_learned","delta_glue_ratio","action_applied"])
 early=db.execute("""
 SELECT COUNT(*) FROM r6_attempt_features
 WHERE solver='monitor' AND early_glue_ratio IS NOT NULL""").fetchone()[0]
 actions=db.execute("""
 SELECT COUNT(*) FROM r6_attempt_features
 WHERE switch_at IS NOT NULL""").fetchone()[0]
 done=db.execute("""
 SELECT COUNT(*) FROM attempts
 WHERE dataset LIKE 'r6_%' AND status IN ('SAT','UNSAT')""").fetchone()[0]
 gate=db.execute("""
 SELECT COUNT(*) FROM r6_attempt_features
 WHERE solver='r5_frozen_gate' AND switch_at IS NOT NULL""").fetchone()[0]
 assert done==480 and early==36 and gate==0
 findings=dict(unique_formulas=40,total_attempts=480,
  reached_512_monitor=early,restart_interventions=actions,
  frozen_gate_interventions=gate,total_trace_points=len(dynamics),
  post_intervention_pairs=len(after),
  summary=summary,correlations=corr_rows,
  scientific_cautions=[
   "Exploratory benchmark: not official or independent holdout",
   "C/D vs monitor are in-process comparisons; V15.3.1 uses different preprocessing",
   "Three repeats within one formula are not independent observations",
   "External SATLIB inputs are publicly known, not genuinely blind",
   "Recorded fast/slow glue ratio is not absolute LBD; no invented missing readings",
   "Missing 512 checkpoint means solved before that sample, not absent data",
   "Kissat UNSAT has no independently checked proof in this run",
   "R5 had zero actual interventions; apparent differences vs monitor are measurement noise",
   "Correlation and post-intervention signatures require new unseen testing"])
 (out/"r6_findings.json").write_text(json.dumps(findings,indent=2)+"\n")
 lines=["# DRNAS SAT V15.3.1 + R6 — cumulative analysis",
  "",
  "Base SQLite: GitHub Actions run 41341529210; appended R6: 41343506152.",
  "Previous data preserved; R6 adds 40 formulas and 480 attempts.",
  "Generated and already-public SATLIB are labelled separately. This is not official competition validation.",
  "",
  "## R6 by formula-level PAR-2 medians",
  "",
  "| Category | Strategy | Formula count | Speedup vs monitor | Switches (repeats) |",
  "|---|---|---:|---:|---:|"]
 for x in summary:
  lines.append("| "+x["dataset"]+" | "+x["mode"]+" | "+str(x["n_distinct_formulas"])+
  " | "+str(x["speedup"])+"x | "+str(x["intervention_repeats"])+" |")
 lines.extend(["","## Measured early indicators",
  "",
  "Monitor crossed 512 conflicts "+str(early)+" times across 120 monitor executions.",
  "R5 frozen gate switched "+str(gate)+" times; forced policies switched "+str(actions)+" times overall.",
  "R6 produced "+str(len(dynamics))+" observed telemetry points and "+str(len(after))+" paired post-action checkpoints.",
  "",
  "Feature association computed on distinct formulas (not repeated attempts); results are hypothesis generators only.",
  "Blank values mean the threshold was not reached or the value could not be measured.",
  "",
  "## Warehouse and CSV exports",
  "",
  "sat_analytics.sqlite, r6_import_audit.json, r6_findings.json,",
  "r6_formula_medians.csv, r6_category_summary.csv,",
  "r6_feature_correlations.csv, r6_dynamics.csv, r6_post_intervention.csv.",
  "",
  "## SQLite example",
  "",
  "SELECT f.category, a.solver, COUNT(*), SUM(a.par2_seconds)",
  "FROM attempts a JOIN formulas f ON a.dataset=f.dataset AND a.case_name=f.case_name",
  "WHERE a.dataset LIKE 'r6_%' GROUP BY f.category,a.solver;",
  "",
  "GLUE RATIO is stored as r6_checkpoint_features.glue_ratio, NOT telemetry.avg_lbd.",
  "All R6 source pins and hashes are in the imported manifest and r6_import_audit.",
  ])
 (out/"README.md").write_text("\n".join(lines)+"\n")
 print("R6_FORMULA_LEVEL_ANALYSIS",json.dumps(dict(formulas=len(unique),
   early=early,actions=actions,gate_actions=gate,
   trace_points=len(dynamics),post_pairs=len(after))),flush=True)

def plots(out):
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
 except ImportError:
  return
 with (out/"r6_formula_medians.csv").open(newline="") as f:rows=list(csv.DictReader(f))
 for feat,target in (("early_glue_ratio","r6_glue_vs_speedup.png"),
                     ("early_prop_per_conflict","r6_propagation_vs_speedup.png")):
  fig,ax=plt.subplots(figsize=(7.5,4.5))
  for mode in ("forced_restart25","r5_frozen_gate"):
   subset=[r for r in rows if r["mode"]==mode and r[feat]]
   if subset:
    ax.scatter([float(r[feat]) for r in subset],
        [float(r["speedup"]) for r in subset],label=mode,alpha=.8)
  ax.axhline(1,linestyle="--",linewidth=1)
  ax.set_title("DRNAS R6 — exploratory, not holdout validated")
  ax.set_xlabel(feat+" at 512 conflicts")
  ax.set_ylabel("Per-formula PAR-2 median speedup vs monitor")
  ax.legend()
  fig.tight_layout()
  fig.savefig(out/target,dpi=150)
  plt.close(fig)

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--db",type=Path,required=True)
 ap.add_argument("--out",type=Path,required=True)
 a=ap.parse_args()
 a.out.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(a.db) as conn:report(conn,a.out)
 plots(a.out)
