#!/usr/bin/env python3
"""Append only completed, pinned R7 and cross-family SAT artifacts to the historical warehouse.
No solver execution or heuristic changes. Fail closed on missing/corrupt evidence.
"""
import argparse, csv, hashlib, json, sqlite3, statistics
from pathlib import Path
from collections import defaultdict
import v1531_analytics_db as base
import v1531_ingest_new as old

R7 = {
 "jerk": dict(run="41346987963", commit="29e6ce16152b8744a2736e3f4546402b399c1b03",
  artifact=13099418920, formulas=40, attempts=480, percat=10, cap=8, modes=("stable_v1531","monitor","forced_restart25","r5_frozen_gate"),
  cats=("random3","graphcolor","xor","external_satlib"),
  artifact_ids={"random3":13099262713,"graphcolor":13099329052,"xor":13099617091,"external_satlib":13099204392}),
 "wide": dict(run="41345671202", commit="0f1111fadcf9db1c6914927565d17f479f6d7f10",
  artifact=13099481360, formulas=100, attempts=1500, percat=20, cap=8,
  modes=("original_kissat","stable_v1531","monitor","forced_restart25","r7_gate"),
  cats=("random3a","random3b","graphcolor","xor","external_satlib")),
 "large": dict(run="41346915939", commit="6f70bb18664cffa2608a94c6fe7c1542cd576511",
  artifact=13100071477, formulas=160, attempts=2400, percat=10, cap=12,
  modes=("original_kissat","stable_v1531","monitor","forced_restart25","r7_gate"),
  cats=tuple("random%d_%d"%(n,k) for n in (200,220,240) for k in range(4))+
       ("graphcolor","xor","external_flat","external_aim")),
 "prop": dict(run="41345148256",commit="1b35042c1650c933a190064ea4e3f54d602b1a32",
  artifact=13097934951,formulas=40,attempts=480,percat=10,cap=8,
  modes=("stable_v1531","monitor","forced_restart25","r7_gate"),
  cats=("random3","graphcolor","xor","external_satlib")),
 "target": dict(run="41345312821",commit="f26e98eda6abdbd36ad78bff09fcd78a124cdd08",
  artifact=13098956328,formulas=40,attempts=480,percat=10,cap=8,
  modes=("stable_v1531","monitor","forced_restart25","r7_gate"),
  cats=("random3","graphcolor","xor","external_satlib"))
}
CROSS = dict(run="41345835957",commit="ab32a2c7f452cb02e8ba599a5fc2987c13bf6cea",
 artifact=13098709066,families={"uf200-860":(40,80),"uf250-1065":(40,80),
                               "uuf200-860":(39,78),"flat200-479":(40,80)})

def require(condition,message):
 if not condition: raise ValueError(message)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def jsonlines(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def asint(x): return int(x) if x is not None and str(x).strip() else None
def asfloat(x): return float(x) if x is not None and str(x).strip() else None
def boolean(x):
 return 1 if str(x).lower() in ("1","true") else 0 if str(x).lower() in ("0","false") else None
def payload(path):
 with path.open(newline="") as f: return list(csv.DictReader(f))
def rowhash(r): return hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def ingest_r7_category(db,kind,cat,manifest,rows,traces,measurements_path,results_path,aid,expected_sha=None):
 spec=R7[kind]
 dataset="DRNAS-R7-"+kind+"-"+cat
 require(manifest["category"]==cat and manifest["source_commit"]==spec["commit"],
         dataset+" source commit/category mismatch")
 require(manifest["cap_seconds"]==spec["cap"] and manifest["repeats"]==3,
         dataset+" cap/repeats mismatch")
 require(tuple(manifest["modes"])==spec["modes"],dataset+" policy list mismatch")
 cases={f["formula"]:f for f in manifest["cases"]}
 require(len(cases)==spec["percat"] and len({f["formula_sha256"] for f in cases.values()})==len(cases),
         dataset+" formula count/hash duplicate")
 require(len(rows)==len(cases)*3*len(spec["modes"]),dataset+" attempt count mismatch")
 require(len(traces)==len(rows),dataset+" trace count mismatch")
 if expected_sha: require(sha(measurements_path)==expected_sha,dataset+" SHA256 differs from published report")
 key=lambda r:(r["formula"],r["mode"],int(r["repeat"]))
 keys={key(r) for r in rows}
 expected={(f,mode,rep) for f in cases for mode in spec["modes"] for rep in range(3)}
 require(keys==expected and len(keys)==len(rows),dataset+" incomplete/duplicate paired matrix")
 tkeys={(t["formula"],t["mode"],int(t["repeat"])) for t in traces}
 require(tkeys==keys and len(tkeys)==len(traces),dataset+" missing/duplicate telemetry")
 require(all(r["category"]==cat and r["runner"]==manifest["runner"] and
             r["formula_sha256"]==cases[r["formula"]]["formula_sha256"] and
             r["expected"]==cases[r["formula"]]["expected"] and not r["error"]
             for r in rows),dataset+" runner/hash/expected/error mismatch")
 bycase=defaultdict(set)
 for r in rows:
  status=r["status"]
  require(status in ("SAT","UNSAT","TIMEOUT"),dataset+" invalid status")
  wall,par2=float(r["wall_s"]),float(r["par2_s"])
  require(wall>=0 and par2>=0,dataset+" negative timing")
  require(abs(par2-(wall if status in ("SAT","UNSAT") else 2*spec["cap"]))<0.001,
          dataset+" PAR2 inconsistent")
  if status in ("SAT","UNSAT"):
   bycase[r["formula"]].add(status)
   require(r["expected"]=="UNKNOWN" or r["expected"]==status,dataset+" known answer mismatch")
   if status=="SAT": require(boolean(r["sat_model_checked"])==1,dataset+" SAT model unchecked")
  if r["seed"] not in (None,"","frozen SATLIB source"):
   seed=cases[r["formula"]].get("metadata",{}).get("seed")
   require(seed is None or str(seed)==str(r["seed"]),dataset+" seed mismatch")
 require(all(len(v)<=1 for v in bycase.values()),dataset+" SAT/UNSAT disagreement")
 provenance=("external_previously_seen" if cat.startswith("external") else
             "generated_prescreen_selected" if kind=="target" and cat=="random3" else
             "generated_development")
 # Retain pre-timing structural features and prescreen selection labels separately.
 manifest_sha=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
 for name,f in cases.items():
  features=(dataset,name,f["formula_sha256"],manifest_sha,f.get("source"),
            f.get("source_revision"),json.dumps(f.get("metadata",{}),sort_keys=True))
  previous=db.execute("""SELECT dataset,case_name,formula_sha256,manifest_sha256,
    source,source_revision,metadata_json FROM r7_formula_features
    WHERE dataset=? AND case_name=?""",(dataset,name)).fetchone()
  if previous: require(tuple(previous)==features,dataset+" changed frozen metadata "+name)
  else: db.execute("INSERT INTO r7_formula_features VALUES (?,?,?,?,?,?,?)",features)
 existing=db.execute("SELECT source_run,source_sha FROM datasets WHERE dataset=?",(dataset,)).fetchone()
 if existing:
  require(tuple(existing)==(spec["run"],spec["commit"]),dataset+" existing dataset provenance changed")
  require(db.execute("SELECT COUNT(*) FROM attempts WHERE dataset=?",(dataset,)).fetchone()[0]==len(rows),
          dataset+" existing attempts incomplete")
 else:
  db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
   (dataset,provenance,"R7 measured frozen strategies; nonofficial; "+kind,spec["run"],spec["commit"],
    manifest["runner"],spec["cap"],sha(measurements_path)))
  for name,f in cases.items():
   db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",
    (dataset,name,cat,f["expected"],f["formula_sha256"],f.get("metadata",{}).get("raw_source_sha256"),
     f.get("path"),f.get("n"),len(f.get("clauses",[])) if f.get("clauses") else None))
  for r in rows:
   case,mode,rep=key(r);status=r["status"]
   satok,unsatok=boolean(r["sat_model_checked"]),boolean(r["native_unsat_certificate_checked"])
   verified=1 if (status=="SAT" and satok==1) or (status=="UNSAT" and unsatok==1) else (0 if status=="TIMEOUT" else None)
   tier="sat_witness" if satok==1 else "native_unsat_certificate" if unsatok==1 else "unsat_label_only" if status=="UNSAT" else "timeout"
   db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    (dataset,case,mode,rep,float(r["wall_s"]),status,verified,r["route"],satok,unsatok,
     float(r["par2_s"]),asint(r["exit_code"])))
   db.execute("INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",
    (dataset,case,mode,rep,r["runner"],r["seed"],r["source_revision"],r["formula_sha256"],rowhash(r),tier))
   db.execute("INSERT INTO r6_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (dataset,case,mode,rep,asint(r["early_restarts"]),asfloat(r["early_g"]),
     asfloat(r["early_p"]),asfloat(r["early_d"]),boolean(r["gate_eligible"]),
     boolean(r["gate_action"]),asint(r["switch_at"]),asint(r["final_conflicts"]),
     asint(r["final_restarts"]),asint(r["trace_points"])))
  for t in traces:
   case,mode,rep=key(t)
   for idx,pt in enumerate(t.get("points",[])):
    db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,case,mode,rep,idx,None,asint(pt.get("conflict")),
      asint(pt.get("propagations")),asint(pt.get("restarts")),
      asint(pt.get("learned")),asfloat(pt.get("glue"))))
 old.source(db,dataset,spec["run"],spec["commit"],aid,measurements_path,sha(results_path),
            manifest["runner"],provenance,
            "Nonofficial; generated or previously public; UNSAT often label-only; no independent record.")
 return dict(dataset=dataset,formulas=len(cases),attempts=len(rows),new=not bool(existing))

def ingest_r7(db,root):
 imported=[]
 for kind,spec in R7.items():
  folder=root/kind
  if kind=="jerk":
   report=json.loads((folder/"jerk_standard_report.json").read_text())
   require(report["measurements"]==480 and report["unique_formulas"]==40,
           "Jerk R7 published report totals mismatch")
   require(len(report["sources"])==4,"Jerk R7 report incomplete")
   bycat={x["category"]:x for x in report["sources"]}
   require(set(bycat)==set(spec["cats"]),"Jerk R7 categories mismatch")
   for cat in spec["cats"]:
    path=folder/cat
    mpath=path/"measurements.csv";tpath=path/"traces.jsonl";manifestpath=path/"manifest.json"
    s=bycat[cat]
    require(sha(tpath)==s["traces_sha256"] and sha(manifestpath)==s["manifest_sha256"],
            "Jerk R7 trace/manifest SHA mismatch "+cat)
    m=json.loads(manifestpath.read_text())
    require(s["runner"]==m["runner"] and s["source_commit"]==spec["commit"],
            "Jerk R7 report source mismatch "+cat)
    imported.append(ingest_r7_category(db,kind,cat,m,payload(mpath),jsonlines(tpath),
                 mpath,folder/"jerk_standard_report.json",spec["artifact_ids"][cat],s["measurements_sha256"]))
  else:
   mpath=folder/"measurements.csv";tpath=folder/"traces.jsonl";jpath=folder/"results.json"
   report=json.loads(jpath.read_text())
   require(report["total_measurements"]==spec["attempts"] and
           report["unique_formulas"]==spec["formulas"] and
           report["repeats"]==3 and tuple(report["strategies"])==spec["modes"],
           "R7 "+kind+" report count/strategy mismatch")
   manifests={m["category"]:m for m in report["manifests"]}
   require(set(manifests)==set(spec["cats"]),"R7 "+kind+" manifests incomplete")
   rows=payload(mpath);traces=jsonlines(tpath)
   require(len(rows)==spec["attempts"] and len(traces)==len(rows),
           "R7 "+kind+" missing aggregate data")
   for cat in spec["cats"]:
    imported.append(ingest_r7_category(db,kind,cat,manifests[cat],
     [r for r in rows if r["category"]==cat],
     [t for t in traces if t["category"]==cat],
     mpath,jpath,spec["artifact"]))
 return imported

def ingest_crossfamily(db,folder):
 source_db=folder/"crossfamily-warehouse/sat_analytics.sqlite"
 require(source_db.is_file(),"Missing crossfamily source warehouse")
 aggregate=json.loads((folder/"crossfamily-validation/aggregate.json").read_text())
 require(aggregate["sample_count"]==159 and aggregate["attempt_count"]==318,
         "Crossfamily source aggregate incomplete")
 require(aggregate["source_run_ids"] and
         all(x["run"]==CROSS["run"] and x["sha"]==CROSS["commit"]
             for x in aggregate["source_run_ids"]),
         "Crossfamily aggregate run/commit mismatch")
 result=[]
 for family,(nf,na) in CROSS["families"].items():
  name="DRNAS-V1531-CrossFamily-"+family
  path=folder/"crossfamily-validation"/family/"results.json"
  spec=(name,CROSS["run"],CROSS["commit"],CROSS["artifact"],nf,na)
  result.append(old.ingest_db(db,source_db,path,spec))
  # The public source is preregistered, but still nonofficial SATLIB.
  db.execute("UPDATE source_artifacts SET warning=? WHERE dataset=?",
   ("Preregistered external SATLIB, NOT official or a DRNAS-vs-Kissat test; UNSAT proof unverified.",name))
  meta=old.rows(db,"SELECT a.*,f.formula_sha256,d.runner FROM attempts a JOIN formulas f USING(dataset,case_name) JOIN datasets d USING(dataset) WHERE a.dataset=?",(name,))
  for r in meta:
   raw=json.dumps({k:v for k,v in r.items() if k!="runner"},sort_keys=True,default=str)
   db.execute("INSERT OR IGNORE INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",
    (name,r["case_name"],r["solver"],r["repeat"],r["runner"],None,CROSS["commit"],
     r["formula_sha256"],hashlib.sha256(raw.encode()).hexdigest(),
     "SAT witness if verified; UNSAT source label otherwise"))
 return result

def new_pairs(db,out):
 records=old.rows(db,"""SELECT a.dataset,a.case_name,a.repeat,a.solver AS treatment,
 b.par2_seconds AS monitor_par2,a.par2_seconds AS treatment_par2,
 CASE WHEN a.par2_seconds>0 THEN b.par2_seconds/a.par2_seconds END AS speedup,
 f.category,d.provenance
 FROM attempts a JOIN attempts b ON b.dataset=a.dataset AND b.case_name=a.case_name
 AND b.repeat=a.repeat AND b.solver='monitor'
 JOIN formulas f ON f.dataset=a.dataset AND f.case_name=a.case_name
 JOIN datasets d ON d.dataset=a.dataset
 WHERE a.dataset LIKE 'DRNAS-R7-%' AND a.solver!='monitor'
 ORDER BY a.dataset,a.case_name,a.repeat,a.solver""")
 require(len(records)==4200,"Expected 4200 matched R7 attempts")
 cols=("dataset","case_name","repeat","treatment","monitor_par2","treatment_par2",
       "speedup","category","provenance")
 base.export_csv(out/"r7_paired.csv",records,cols)
 groups=defaultdict(list)
 for r in records:groups[(r["dataset"],r["treatment"])].append(r)
 summary=[]
 for (d,t),rows in sorted(groups.items()):
  b=sum(r["monitor_par2"] for r in rows);v=sum(r["treatment_par2"] for r in rows)
  summary.append(dict(dataset=d,treatment=t,pairs=len(rows),
    monitor_par2_sum=round(b,7),treatment_par2_sum=round(v,7),
    speedup_sum=round(b/v,7) if v else None))
 base.export_csv(out/"r7_paired_summary.csv",summary,
   ("dataset","treatment","pairs","monitor_par2_sum","treatment_par2_sum","speedup_sum"))
 import matplotlib
 matplotlib.use("Agg")
 import matplotlib.pyplot as plt
 for kind in R7:
  sub=[r for r in records if r["dataset"].startswith("DRNAS-R7-"+kind+"-")]
  fig,ax=plt.subplots(figsize=(8,6))
  for treatment in sorted({r["treatment"] for r in sub}):
   x=[r for r in sub if r["treatment"]==treatment]
   ax.scatter([r["monitor_par2"] for r in x],[r["treatment_par2"] for r in x],
              s=8,alpha=.35,label=treatment)
  ax.set(xlabel="Monitor PAR-2 (s)",ylabel="Treatment PAR-2 (s)",
         title="R7 "+kind+": paired attempts, nonofficial")
  ax.set_xscale("log");ax.set_yscale("log")
  ax.legend(fontsize=7);fig.tight_layout()
  fig.savefig(out/("scatter_r7_"+kind+".png"),dpi=140);plt.close(fig)
 return records,summary

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True)
 p.add_argument("--input",type=Path,required=True)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(a.db)
 try:
  old.schema(db)
  db.execute("""CREATE TABLE IF NOT EXISTS r7_formula_features(
   dataset TEXT,case_name TEXT,formula_sha256 TEXT,manifest_sha256 TEXT,
   source TEXT,source_revision TEXT,metadata_json TEXT,
   PRIMARY KEY(dataset,case_name))""")
  with db:
   imported=ingest_r7(db,a.input)
   cross=ingest_crossfamily(db,a.input/"crossfamily")
  grouped,paired,telemetry=base.analytics(db,a.out)
  base.plot(a.out,paired,telemetry)
  overlap,r6pairs,r6summary=old.extra(db,a.out)
  old.scatter(a.out,r6pairs)
  r7pairs,r7summary=new_pairs(db,a.out)
  features=old.rows(db,"SELECT * FROM r7_formula_features ORDER BY dataset,case_name")
  require(len(features)==380,"Expected 380 R7 frozen formula metadata records")
  base.export_csv(a.out/"r7_formula_features.csv",features,
    ("dataset","case_name","formula_sha256","manifest_sha256","source","source_revision","metadata_json"))
  selected=[f for f in features if f["dataset"]=="DRNAS-R7-target-random3"]
  require(len(selected)==10,"Targeted prescreen manifest not complete")
  buckets=defaultdict(list)
  for f in selected:
   m=json.loads(f["metadata_json"]); pre=m.get("prescreen",{})
   require(pre.get("bucket") in ("eligible","ineligible") and pre.get("p") is not None,
           "Missing targeted prescreen metadata")
   buckets[pre["bucket"]].append(f["case_name"])
  require(len(buckets["eligible"])==5 and len(buckets["ineligible"])==5,
          "Targeted prescreen strata changed")
  bucket_rows=[]
  for bucket,names in sorted(buckets.items()):
   for mode in ("forced_restart25","r7_gate"):
    sub=[r for r in r7pairs if r["dataset"]=="DRNAS-R7-target-random3" and
         r["case_name"] in names and r["treatment"]==mode]
    require(len(sub)==15,"Incomplete targeted matched prescreen pairs")
    b=sum(r["monitor_par2"] for r in sub);v=sum(r["treatment_par2"] for r in sub)
    bucket_rows.append(dict(bucket=bucket,mode=mode,formulas=5,attempt_pairs=15,
      monitor_par2_sum=round(b,8),treatment_par2_sum=round(v,8),
      speedup_sum=round(b/v,8) if v else None))
  base.export_csv(a.out/"r7_target_signal_buckets.csv",bucket_rows,
   ("bucket","mode","formulas","attempt_pairs","monitor_par2_sum",
    "treatment_par2_sum","speedup_sum"))
  counts={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
   for t in ("datasets","formulas","attempts","telemetry","source_artifacts",
             "attempt_context","verified_certificates","r7_formula_features")}
  require(counts["datasets"]==49 and counts["formulas"]==1027 and
          counts["attempts"]==10706 and counts["source_artifacts"]==44 and
          counts["r7_formula_features"]==380,
          "Cumulative count changed unexpectedly: "+str(counts))
  require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
          "SQLite integrity_check failed")
  require(db.execute("""SELECT COUNT(*) FROM (SELECT dataset,case_name,solver,repeat,
   COUNT(*) AS n FROM attempts GROUP BY 1,2,3,4 HAVING n>1)""").fetchone()[0]==0,
   "Duplicate attempt primary keys")
  audit=json.loads((a.out/"ingest_audit.json").read_text())
  audit["new_20261101_sources"]=imported+cross
  audit["new_20261101_counts"]=counts
  audit["r7_paired_attempts"]=len(r7pairs)
  audit["r7_paired_summary"]=r7summary
  audit["r7_target_signal_buckets"]=bucket_rows
  audit["cross_dataset_formula_hash_overlaps"]=len(overlap)
  audit["cautions"]+=["R7 generated and previously public SATLIB: not official/unseen.",
    "R7 original Kissat and stable V15.3.1 are not architecture-identical.",
    "Crossfamily is preregistered external transfer of Kissat hardness, not DRNAS speedup.",
    "Repeated formula attempts are paired; independent sample size is formulas.",
    "R7 targeted random3 cases were prescreen-selected on monitor signal; selection bias."]
  (a.out/"ingest_audit.json").write_text(json.dumps(audit,indent=2))
  summary=json.loads((a.out/"summary.json").read_text())
  summary["incremental_ingest"]=audit
  (a.out/"summary.json").write_text(json.dumps(summary,indent=2))
  (a.out/"new_source_audit.json").write_text(json.dumps(
   {"sources":imported+cross,"counts":counts,"r7_paired_attempts":len(r7pairs),
    "hash_overlaps":len(overlap),"r7_summary":r7summary,
    "r7_target_signal_buckets":bucket_rows},indent=2))
  print(json.dumps({"new_sources":[x["dataset"] for x in imported+cross if x["new"]],
   "counts":counts,"r7_pairs":len(r7pairs),"overlaps":len(overlap)},indent=2))
 finally:db.close()

if __name__=="__main__": main()
