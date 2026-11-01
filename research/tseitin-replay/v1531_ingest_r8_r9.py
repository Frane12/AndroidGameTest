#!/usr/bin/env python3
"""Append only verified R8/R9 measured holdouts to the cumulative V15.3.1 warehouse.

No solver modification. R8/R9 are nonofficial; SATLIB is publicly known and
R9 may reuse R8 SATLIB hashes. Independent unit is formula, not repeat.
"""
import argparse,csv,hashlib,json,sqlite3
from pathlib import Path
from collections import defaultdict
import v1531_analytics_db as base
import v1531_ingest_new as old
import v1531_ingest_r7_crossfamily as r7

CATS=("random3","graphcolor","xor","external_satlib")
RUNS={
 "R8":dict(run="41352136853",commit="6cc1163951c24ee5f6f64f9198a8bace8a16049a",
   analysis_artifact=13101548959,shards={"random3":13101507606,"graphcolor":13100879046,
   "xor":13101648127,"external_satlib":13101975360},
   modes=("stable_v1531","monitor","forced_restart25","r5_frozen_gate"),
   report="jerk_holdout_report.json",attempts=1200),
 "R9":dict(run="41353826120",commit="a9758338790a2c5bfa6509afcd676f16893f68bd",
   analysis_artifact=13102895966,shards={"random3":13102336641,"graphcolor":13102186885,
   "xor":13102436494,"external_satlib":13102307687},
   modes=("stable_v1531","monitor","forced_restart25","r5_frozen_gate","jerk_gate"),
   report="jerk_gate_report.json",attempts=1500)
}
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def readcsv(p):
 with p.open(newline="") as f:return list(csv.DictReader(f))
def trace(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def export(out,name,rows,cols):base.export_csv(out/name,rows,cols)
def ingest(db,root):
 imported=[];reports={};before={r[0] for r in db.execute("SELECT DISTINCT formula_sha256 FROM formulas")}
 for kind,spec in RUNS.items():
  r7.R7[kind]=dict(run=spec["run"],commit=spec["commit"],cap=8,
    modes=spec["modes"],percat=25)
  folder=root/kind.lower()
  report_path=folder/spec["report"]
  report=json.loads(report_path.read_text())
  require(report["measurements"]==spec["attempts"] and report["unique_formulas"]==100,
          kind+" report totals mismatch")
  require(len(report["sources"])==4,kind+" missing report source shards")
  sources={s["category"]:s for s in report["sources"]}
  require(set(sources)==set(CATS),kind+" category mismatch")
  reports[kind]=report
  protocols=[]
  for cat in CATS:
   d=folder/cat
   paths={n:d/n for n in ("measurements.csv","traces.jsonl","manifest.json")}
   s=sources[cat]
   for n,key in (("measurements.csv","measurements_sha256"),
                 ("traces.jsonl","traces_sha256"),("manifest.json","manifest_sha256")):
    require(sha(paths[n])==s[key],kind+"/"+cat+" SHA-256 mismatch "+n)
   m=json.loads(paths["manifest.json"].read_text())
   require(m["runner"]==s["runner"] and m["source_commit"]==spec["commit"] and
           s["source_commit"]==spec["commit"],kind+"/"+cat+" source lineage mismatch")
   require(sorted(f["formula_sha256"] for f in m["cases"])==sorted(s["formula_hashes"]),
           kind+"/"+cat+" formula hash registry mismatch")
   protocol_path=d/"protocol.json"
   require(protocol_path.is_file(),kind+"/"+cat+" missing frozen protocol")
   protocols.append(sha(protocol_path))
   p=json.loads(protocol_path.read_text())
   require(p["formula_total"]==100 and p["repeats_per_formula"]==3 and
           tuple(p["strategies"])==spec["modes"],kind+"/"+cat+" protocol changed")
   rows=readcsv(paths["measurements.csv"]);traces=trace(paths["traces.jsonl"])
   provenance=("external_public_hash_new_at_R8" if kind=="R8" else
      "external_public_reused_or_known") if cat=="external_satlib" else "generated_holdout"
   item=r7.ingest_r7_category(db,kind,cat,m,rows,traces,paths["measurements.csv"],
      report_path,spec["shards"][cat],s["measurements_sha256"],
      dataset_prefix="DRNAS-",provenance_override=provenance,
      description_override=kind+" hash-new holdout, nonofficial; frozen V15.3.1")
   db.execute("UPDATE source_artifacts SET warning=? WHERE dataset=?",
      ("External SATLIB is public and NOT official/unseen globally; R9 may reuse R8 hashes. "
       "UNSAT label is not independently proven." if cat=="external_satlib" else
       "Generated holdout, not an official competition benchmark; UNSAT proof may be absent.",
       item["dataset"]))
   imported.append(item)
  require(len(set(protocols))==1,kind+" inconsistent protocol across runner shards")
  if kind=="R8":
   require(report["paired_comparisons"]==900 and
           report["monitor_trials_total"]==300,kind+" incomplete paired analysis")
  else:
   require(report["gate_attempts"]==300 and
           report["gate_triggered_attempts"]<=report["gate_evaluated_attempts"],
           kind+" invalid gate count")
  # Freeze the raw source report in audit; the pre-registered test must not be refitted.
  require(report.get("signal_predictive_rule_supported",report.get("signal_gate_supported")) is False,
          kind+" reported support flag unexpectedly changed")
  reports[kind+"_protocol_sha256"]=protocols[0]
 # Keep the pre-existing R7-only feature table at its frozen 380 rows.
 db.execute("""CREATE TABLE IF NOT EXISTS holdout_formula_features(
  dataset TEXT,case_name TEXT,formula_sha256 TEXT,manifest_sha256 TEXT,
  source TEXT,source_revision TEXT,metadata_json TEXT,
  PRIMARY KEY(dataset,case_name))""")
 moved=db.execute("SELECT * FROM r7_formula_features WHERE dataset LIKE 'DRNAS-R8-%' OR dataset LIKE 'DRNAS-R9-%'").fetchall()
 for row in moved:
  prior=db.execute("SELECT * FROM holdout_formula_features WHERE dataset=? AND case_name=?",
                    row[:2]).fetchone()
  require(prior is None or tuple(prior)==tuple(row),"Changed holdout formula metadata")
  if prior is None:db.execute("INSERT INTO holdout_formula_features VALUES (?,?,?,?,?,?,?)",row)
 db.execute("DELETE FROM r7_formula_features WHERE dataset LIKE 'DRNAS-R8-%' OR dataset LIKE 'DRNAS-R9-%'")
 require(db.execute("SELECT COUNT(*) FROM r7_formula_features").fetchone()[0]==380,
         "R7 frozen features modified")
 require(db.execute("SELECT COUNT(*) FROM holdout_formula_features").fetchone()[0]==200,
         "R8/R9 holdout metadata incomplete")
 return imported,reports,before

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True)
 p.add_argument("--input",type=Path,required=True)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(a.db)
 try:
  old.schema(db)
  with db:imported,reports,before=ingest(db,a.input)
  require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity failed")
  counts={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
    for t in ("datasets","formulas","attempts","telemetry","source_artifacts",
              "attempt_context","r7_formula_features","holdout_formula_features")}
  require(counts["datasets"]==57 and counts["formulas"]==1227 and
          counts["attempts"]==13406 and counts["source_artifacts"]==52 and
          counts["attempt_context"]>=8838,"Cumulative history changed: "+str(counts))
  require(db.execute("""SELECT COUNT(*) FROM attempt_context WHERE dataset LIKE 'DRNAS-R8-%' OR dataset LIKE 'DRNAS-R9-%'""").fetchone()[0]==2700,
          "New holdout attempt contexts incomplete")
  require(db.execute("""SELECT COUNT(*) FROM (
    SELECT dataset,case_name,solver,repeat,COUNT(*) AS n FROM attempts
    GROUP BY 1,2,3,4 HAVING n>1)""").fetchone()[0]==0,
    "Duplicate attempt keys")
  require(db.execute("""SELECT COUNT(*) FROM attempts a JOIN formulas f
    ON f.dataset=a.dataset AND f.case_name=a.case_name
    WHERE (a.dataset LIKE 'DRNAS-R8-%' OR a.dataset LIKE 'DRNAS-R9-%')
    AND (a.status IN ('SAT','UNSAT') AND f.expected NOT IN ('UNKNOWN',a.status))""").fetchone()[0]==0,
    "Status mismatch")
  r8={r[0] for r in db.execute("SELECT formula_sha256 FROM formulas WHERE dataset='DRNAS-R8-external_satlib'")}
  r9={r[0] for r in db.execute("SELECT formula_sha256 FROM formulas WHERE dataset='DRNAS-R9-external_satlib'")}
  # 'Hash new' means absent from the pre-R8 cumulative registry, not globally unseen.
  require(not (r8 & before),"R8 SATLIB holdout overlaps pre-existing cumulative registry")
  grouped,paired,telemetry=base.analytics(db,a.out)
  base.plot(a.out,paired,telemetry)
  overlaps,r6pairs,r6summary=old.extra(db,a.out)
  old.scatter(a.out,r6pairs)
  r7.new_pairs(db,a.out)
  holdout=old.rows(db,"""SELECT a.dataset,a.case_name,a.repeat,a.solver AS treatment,
    m.par2_seconds AS monitor_par2,a.par2_seconds AS treatment_par2,
    CASE WHEN a.par2_seconds>0 THEN m.par2_seconds/a.par2_seconds END AS speedup,
    f.category,d.provenance
    FROM attempts a JOIN attempts m ON m.dataset=a.dataset AND m.case_name=a.case_name
      AND m.repeat=a.repeat AND m.solver='monitor'
    JOIN formulas f ON f.dataset=a.dataset AND f.case_name=a.case_name
    JOIN datasets d ON d.dataset=a.dataset
    WHERE (a.dataset LIKE 'DRNAS-R8-%' OR a.dataset LIKE 'DRNAS-R9-%')
      AND a.solver!='monitor'
    ORDER BY a.dataset,a.case_name,a.repeat,a.solver""")
  require(len(holdout)==2100,"Incomplete paired R8/R9 attempts")
  cols=("dataset","case_name","repeat","treatment","monitor_par2","treatment_par2",
        "speedup","category","provenance")
  export(a.out,"holdout_paired.csv",holdout,cols)
  sums=[]
  for ds,mode in sorted({(x["dataset"],x["treatment"]) for x in holdout}):
   z=[x for x in holdout if x["dataset"]==ds and x["treatment"]==mode]
   b=sum(x["monitor_par2"] for x in z);v=sum(x["treatment_par2"] for x in z)
   sums.append(dict(dataset=ds,treatment=mode,pairs=len(z),monitor_par2_sum=round(b,9),
      treatment_par2_sum=round(v,9),speedup_sum=round(b/v,7) if v else None))
  export(a.out,"holdout_paired_summary.csv",sums,
    ("dataset","treatment","pairs","monitor_par2_sum","treatment_par2_sum","speedup_sum"))
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for kind in RUNS:
   sub=[x for x in holdout if x["dataset"].startswith("DRNAS-"+kind+"-")]
   fig,ax=plt.subplots(figsize=(8,6))
   for mode in sorted({x["treatment"] for x in sub}):
    zz=[x for x in sub if x["treatment"]==mode]
    ax.scatter([x["monitor_par2"] for x in zz],[x["treatment_par2"] for x in zz],
               s=9,alpha=.4,label=mode)
   ax.set_xscale("log");ax.set_yscale("log")
   ax.set(xlabel="Monitor PAR-2 seconds",ylabel="Treatment PAR-2 seconds",
          title=kind+" paired holdout (nonofficial)")
   ax.legend(fontsize=7);fig.tight_layout()
   fig.savefig(a.out/("scatter_holdout_"+kind.lower()+".png"),dpi=140)
   plt.close(fig)
  feat=old.rows(db,"SELECT * FROM holdout_formula_features ORDER BY dataset,case_name")
  export(a.out,"holdout_formula_features.csv",feat,
    ("dataset","case_name","formula_sha256","manifest_sha256",
     "source","source_revision","metadata_json"))
  audit={"source_runs":{k:{"run":v["run"],"commit":v["commit"],
         "analysis_artifact":v["analysis_artifact"],"shards":v["shards"]} for k,v in RUNS.items()},
    "new_datasets":[x["dataset"] for x in imported if x["new"]],
    "sources":imported,"counts":counts,"holdout_paired":len(holdout),
    "formula_sha_overlap_r8_r9_external":len(r8 & r9),
    "cross_dataset_formula_hash_overlaps":len(overlaps),
    "r8_signal_supported":reports["R8"]["signal_predictive_rule_supported"],
    "r8_formula_level_complete_signals":reports["R8"]["formulas_with_jerk_in_all_repeats"],
    "r8_forced_restart25_jerk_association":reports["R8"]["associations"]["forced_restart25/all"]["jerk_abs_vs_gain"],
    "r9_gate_supported":reports["R9"]["signal_gate_supported"],
    "r9_gate_evaluated":reports["R9"]["gate_evaluated_attempts"],
    "r9_gate_triggered":reports["R9"]["gate_triggered_attempts"],
    "r9_gate_vs_monitor":reports["R9"]["effects"]["jerk_gate_vs_monitor"],
    "cautions":["No official competition benchmark; no world record claim.",
      "R8 external SATLIB hash-new relative to prior registry only.",
      "R9 public SATLIB may reuse R8 cases; treat overlap as non-independent.",
      "UNSAT source labels are not independent proof certificates.",
      "Formula-level paired comparisons, not 3x independent samples.",
      "V15.3.1 source frozen; R9 Jerk gate is opt-in Kissat intervention only."]}
  (a.out/"holdout_source_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
  summary_path=a.out/"summary.json"
  summary=json.loads(summary_path.read_text())
  summary["r8_r9_holdout"]=audit
  summary_path.write_text(json.dumps(summary,indent=2)+"\n")
  print(json.dumps({"new_datasets":audit["new_datasets"],"counts":counts,
    "holdout_paired":len(holdout),"r8_supported":audit["r8_signal_supported"],
    "r9_supported":audit["r9_gate_supported"],
    "r8_r9_external_hash_overlap":len(r8&r9)},indent=2))
 finally:db.close()
if __name__=="__main__":main()
