#!/usr/bin/env python3
"""Import measured DRNAS SAT R6 into an existing V15.3.1 SQLite warehouse.
Keeps all previous tables and rows; no solver modification and no official claims.
"""
import argparse,csv,hashlib,json,math,shutil,sqlite3,statistics
from collections import defaultdict
from pathlib import Path

BASE_RUN="41341529210"
R6_RUN="41343506152"
R6_SHA="2caca7ff6fe77137725a9093f71baba98b6904bb"
KISSAT_SHA="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
STABLE_BLOB="d280a2ffa28d72aec183323bbea40544d676112d"
SATLIB_SHA="fc0e735aff48989326f256121b5ed6fc585858c3"
CATEGORIES=("random3","graphcolor","xor","external_satlib")
MODES=("stable_v1531","monitor","forced_restart25","r5_frozen_gate")
CAP=8.0

SCHEMA="""
CREATE TABLE IF NOT EXISTS r6_attempt_features (
 dataset TEXT, case_name TEXT, solver TEXT, repeat INTEGER,
 cpu_seconds REAL, runner TEXT, seed TEXT, expected TEXT,
 answer_consistent INTEGER, evidence_level TEXT,
 gate_eligible INTEGER, gate_action INTEGER, switch_at INTEGER,
 final_conflicts INTEGER, final_restarts INTEGER,
 early_restarts INTEGER, early_glue_ratio REAL,
 early_prop_per_conflict REAL, early_decisions_per_conflict REAL,
 trace_points INTEGER, PRIMARY KEY(dataset,case_name,solver,repeat));
CREATE TABLE IF NOT EXISTS r6_checkpoint_features (
 dataset TEXT, case_name TEXT, solver TEXT, repeat INTEGER, event INTEGER,
 glue_ratio REAL, stable_mode INTEGER, propagation_rate REAL,
 propagation_rate_delta REAL, propagation_curvature REAL,
 PRIMARY KEY(dataset,case_name,solver,repeat,event));
CREATE TABLE IF NOT EXISTS r6_paired_outcomes (
 dataset TEXT, case_name TEXT, repeat INTEGER, treatment TEXT,
 monitor_par2 REAL, treatment_par2 REAL, speedup REAL,
 early_gate INTEGER, action_applied INTEGER, outcome_label TEXT,
 PRIMARY KEY(dataset,case_name,repeat,treatment));
CREATE TABLE IF NOT EXISTS r6_post_intervention (
 dataset TEXT, case_name TEXT, repeat INTEGER, treatment TEXT,
 checkpoint INTEGER, delta_restarts INTEGER, delta_decisions INTEGER,
 delta_propagations INTEGER, delta_learned INTEGER,
 delta_glue_ratio REAL, action_applied INTEGER,
 PRIMARY KEY(dataset,case_name,repeat,treatment,checkpoint));
CREATE TABLE IF NOT EXISTS r6_import_audit (
 run_id TEXT PRIMARY KEY, source_sha TEXT, source_json_sha256 TEXT,
 baseline_sqlite_sha256 TEXT, baseline_datasets INTEGER,
 baseline_attempts INTEGER, new_datasets INTEGER, new_formulas INTEGER,
 new_attempts INTEGER, new_checkpoints INTEGER, new_pairs INTEGER,
 new_post_samples INTEGER);
CREATE INDEX IF NOT EXISTS idx_r6_solver_signal
 ON r6_attempt_features(dataset,solver,gate_eligible,switch_at);
"""

def hashfile(path):
 return hashlib.sha256(path.read_bytes()).hexdigest()

def numeric(value,integer=False):
 if value in (None,"","None","null","missing"):return None
 n=float(value)
 if not math.isfinite(n):raise ValueError("Nonfinite metric")
 return int(n) if integer else n

def truth(value):
 if value in (None,"","None","null"):return None
 if value in ("True","true","1",True,1):return 1
 if value in ("False","false","0",False,0):return 0
 raise ValueError("Unexpected boolean "+str(value))

def read_csv(path):
 with path.open(newline="") as handle:return list(csv.DictReader(handle))

def require(condition,message):
 if not condition:raise RuntimeError(message)

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--base-db",type=Path,required=True)
 p.add_argument("--r6-artifact",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True)
 args=p.parse_args()
 base=args.base_db
 source=args.r6_artifact
 for f in [base,source/"measurements.csv",source/"traces.jsonl",
           source/"results.json",source/"paired.csv"]:
  require(f.is_file() and f.stat().st_size>0,"MISSING_INPUT "+str(f))
 args.out.mkdir(parents=True,exist_ok=True)
 report=json.loads((source/"results.json").read_text())
 rows=read_csv(source/"measurements.csv")
 pairs=read_csv(source/"paired.csv")
 traces=[json.loads(s) for s in (source/"traces.jsonl").read_text().splitlines()]
 require(report["total_measurements"]==480 and report["unique_formulas"]==40,"BAD_R6_REPORT")
 require(report["repeats"]==3 and tuple(report["strategies"])==MODES,"UNFROZEN_MODES")
 require(report["reference_pins"]==[KISSAT_SHA,STABLE_BLOB,SATLIB_SHA],"BAD_SOURCE_PINS")
 require(len(rows)==480 and len(traces)==480 and len(pairs)==240,"INCOMPLETE_INPUT")
 manifests={m["category"]:m for m in report["manifests"]}
 require(set(manifests)==set(CATEGORIES),"BAD_CATEGORY_SET")
 cases={}
 for category,manifest in manifests.items():
  require(manifest["kissat_pin"]==KISSAT_SHA,"BAD_KISSAT_PIN")
  require(manifest["stable_blob"]==STABLE_BLOB,"BAD_STABLE_BLOB")
  require(manifest["satlib_pin"]==SATLIB_SHA,"BAD_SATLIB_PIN")
  require(manifest["repeats"]==3 and float(manifest["cap_seconds"])==CAP,"BAD_RUN_CAP")
  require(len(manifest["cases"])==10,"BAD_FORMULA_COUNT")
  require(not manifest["official_competition"],"MISLABELED_OFFICIAL")
  require(not manifest["independent_kissat_unsat_certificates"],"MISLABELED_PROOFS")
  require(manifest["dataset_type"]==("external_prior_public" if category=="external_satlib" else "generated"),"WRONG_DATA_TYPE")
  cases[category]={c["formula"]:c for c in manifest["cases"]}
  require(len(cases[category])==10,"DUPLICATE_CASE")
 seen=set()
 for x in rows:
  require(x["category"] in CATEGORIES and x["mode"] in MODES,"BAD_ROW_ID")
  require(x["repeat"] in ("0","1","2"),"BAD_REPEAT")
  require(x["status"] in ("SAT","UNSAT","TIMEOUT"),"BAD_STATUS")
  require(not x["error"],"SOLVER_ERROR "+x["error"])
  key=(x["category"],x["formula"],int(x["repeat"]),x["mode"])
  require(key not in seen,"DUPLICATE_ATTEMPT "+str(key))
  seen.add(key)
  src=cases[x["category"]].get(x["formula"])
  require(src is not None and x["formula_sha256"]==src["formula_sha256"],"FORMULA_CHECKSUM_MISMATCH")
  require(x["dataset_type"]==src["dataset_type"],"WRONG_PROVENANCE")
  require(x["source_revision"]==src["source_revision"],"SOURCE_REVISION_MISMATCH")
  wall=float(x["wall_s"])
  require(wall>=0 and float(x["cpu_s"])>=0,"NEGATIVE_TIME")
  score=wall if x["status"] in ("SAT","UNSAT") else 2*CAP
  require(abs(float(x["par2_s"])-score)<0.00001,"PAR2_MISMATCH")
  if x["status"]=="SAT":require(truth(x["sat_model_checked"])==1,"UNVERIFIED_SAT_MODEL")
  require(truth(x["native_unsat_certificate_checked"])!=0,"INVALID_UNSAT_CERT")
 for cat in CATEGORIES:
  require(sum(x["category"]==cat for x in rows)==120,"INCOMPLETE_SHARD "+cat)
 idx={}
 for t in traces:
  k=(t["category"],t["formula"],int(t["repeat"]),t["mode"])
  require(k in seen and k not in idx,"BAD_TRACE_ID")
  idx[k]=t
 require(len(idx)==480,"MISSING_TRACES")
 require(len({(x["category"],x["formula"],int(x["repeat"]),x["mode"]) for x in pairs})==240,"BAD_PAIR_ID")
 groups=defaultdict(list)
 for x in rows:groups[(x["category"],x["formula"],x["repeat"])].append(x)
 require(len(groups)==120,"INCOMPLETE_GROUPS")
 for key,items in groups.items():
  require(len(items)==4 and {x["mode"] for x in items}==set(MODES),"INCOMPLETE_MODES")
  require(len({x["runner"] for x in items})==1,"CROSS_RUNNER_PAIR")
  status={x["status"] for x in items if x["status"] in ("SAT","UNSAT")}
  require(len(status)<=1,"ANSWER_DISAGREEMENT")
 basehash=hashfile(base)
 destination=args.out/"sat_analytics.sqlite"
 shutil.copy2(base,destination)
 db=sqlite3.connect(destination)
 try:
  required={"datasets","formulas","attempts","telemetry"}
  present={s[0] for s in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  require(required.issubset(present),"BASE_DB_SCHEMA_MISSING")
  require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","BASE_DB_INVALID")
  original_datasets=db.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
  original_attempts=db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
  require(original_datasets>=1 and original_attempts>=100,"BASE_DB_INCOMPLETE")
  require(db.execute("SELECT COUNT(*) FROM datasets WHERE dataset LIKE 'r6_%'").fetchone()[0]==0,
          "DUPLICATE_R6_IMPORT")
  db.executescript(SCHEMA)
  for category,manifest in manifests.items():
   dataset="r6_"+category
   db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",(
    dataset,manifest["dataset_type"],
    "R6 exploratory four-strategy paired, not blind official",
    R6_RUN,R6_SHA,manifest["runner"],CAP,hashfile(source/"results.json")))
   for c in manifest["cases"]:
    metadata=c.get("metadata") or {}
    clause_count=c.get("nclauses") or c.get("clause_count")
    db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",(
     dataset,c["formula"],category,c["expected"],c["formula_sha256"],
     metadata.get("raw_source_sha256"),metadata.get("upstream_relative_path"),
     c["n"],clause_count))
  for x in rows:
   cat=x["category"];ds="r6_"+cat
   name=x["formula"];rep=int(x["repeat"]);mode=x["mode"]
   proof=truth(x["native_unsat_certificate_checked"])
   evid=("sat_clause_checked" if x["status"]=="SAT" else
         "native_unsat_proof" if proof==1 else
         "unsat_label_only" if x["expected"]=="UNSAT" else
         "unsat_unverified" if x["status"]=="UNSAT" else "timeout")
   certified=1 if (x["status"]=="SAT" or proof==1) else None
   consistent=None if x["expected"]=="UNKNOWN" or x["status"]=="TIMEOUT" else int(x["expected"]==x["status"])
   db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(
     ds,name,mode,rep,float(x["wall_s"]),x["status"],certified,x["route"],
     truth(x["sat_model_checked"]),proof,float(x["par2_s"]),
     numeric(x["exit_code"],True)))
   db.execute("INSERT INTO r6_attempt_features VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
     ds,name,mode,rep,float(x["cpu_s"]),x["runner"],x["seed"],
     x["expected"],consistent,evid,truth(x["gate_eligible"]),
     numeric(x["gate_action"],True),numeric(x["switch_at"],True),
     numeric(x["final_conflicts"],True),numeric(x["final_restarts"],True),
     numeric(x["early_restarts"],True),numeric(x["early_g"]),
     numeric(x["early_p"]),numeric(x["early_d"]),int(x["trace_points"])))
   series=idx[(cat,name,rep,mode)]["points"]
   require(len(series)==int(x["trace_points"]),"TRACE_COUNT_MISMATCH")
   prevconf=0;prevprops=0;prevrate=None;prevslope=None
   for event,pt in enumerate(series):
    conflict=int(pt["conflict"]);props=int(pt["propagations"])
    require(conflict>prevconf and props>=prevprops,"NONMONOTONIC_TRACE")
    rate=(props-prevprops)/(conflict-prevconf)
    slope=(rate-prevrate) if prevrate is not None else None
    curvature=(slope-prevslope) if slope is not None and prevslope is not None else None
    db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",(
      ds,name,mode,rep,event,None,conflict,props,int(pt["restarts"]),
      int(pt["learned"]),None))
    # This is fast/slow glue ratio, not absolute average LBD.
    db.execute("INSERT INTO r6_checkpoint_features VALUES (?,?,?,?,?,?,?,?,?,?)",(
      ds,name,mode,rep,event,float(pt["glue"]),int(pt["stable"]),
      rate,slope,curvature))
    prevconf=conflict;prevprops=props;prevrate=rate;prevslope=slope
  for item in pairs:
   db.execute("INSERT INTO r6_paired_outcomes VALUES (?,?,?,?,?,?,?,?,?,?)",(
     "r6_"+item["category"],item["formula"],int(item["repeat"]),item["mode"],
     float(item["monitor_par2"]),float(item["treatment_par2"]),
     float(item["speedup"]),truth(item["early_gate"]),
     truth(item["intervention_applied"]),item["verdict"]))
  for (cat,name,rep,mode),series in idx.items():
   if mode not in ("forced_restart25","r5_frozen_gate"):continue
   monitor=idx[(cat,name,rep,"monitor")]
   basepoints={int(x["conflict"]):x for x in monitor["points"]
               if int(x["conflict"])>=4096}
   for point in series["points"]:
    conflict=int(point["conflict"])
    if conflict<4096 or conflict not in basepoints:continue
    b=basepoints[conflict]
    db.execute("INSERT INTO r6_post_intervention VALUES (?,?,?,?,?,?,?,?,?,?,?)",(
      "r6_"+cat,name,rep,mode,conflict,
      int(point["restarts"])-int(b["restarts"]),
      int(point["decisions"])-int(b["decisions"]),
      int(point["propagations"])-int(b["propagations"]),
      int(point["learned"])-int(b["learned"]),
      float(point["glue"])-float(b["glue"]),
      int(bool(series.get("switch")))))
  counts={"existing_datasets":original_datasets,
          "existing_attempts":original_attempts,
          "r6_datasets":db.execute("SELECT COUNT(*) FROM datasets WHERE dataset LIKE 'r6_%'").fetchone()[0],
          "r6_formulas":db.execute("SELECT COUNT(*) FROM formulas WHERE dataset LIKE 'r6_%'").fetchone()[0],
          "r6_attempts":db.execute("SELECT COUNT(*) FROM attempts WHERE dataset LIKE 'r6_%'").fetchone()[0],
          "r6_checkpoints":db.execute("SELECT COUNT(*) FROM telemetry WHERE dataset LIKE 'r6_%'").fetchone()[0],
          "r6_pairs":db.execute("SELECT COUNT(*) FROM r6_paired_outcomes").fetchone()[0],
          "r6_post_samples":db.execute("SELECT COUNT(*) FROM r6_post_intervention").fetchone()[0]}
  require((counts["r6_datasets"],counts["r6_formulas"],counts["r6_attempts"],counts["r6_pairs"])==(4,40,480,240),
          "IMPORTED_ROW_COUNTS_WRONG")
  require(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]==original_attempts+480,
          "BASE_ATTEMPTS_CHANGED")
  require(db.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]==original_datasets+4,
          "BASE_DATASETS_CHANGED")
  require(counts["r6_checkpoints"]>0,"TELEMETRY_NOT_IMPORTED")
  db.execute("INSERT INTO r6_import_audit VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(
      R6_RUN,R6_SHA,hashfile(source/"results.json"),basehash,
      original_datasets,original_attempts,
      counts["r6_datasets"],counts["r6_formulas"],
      counts["r6_attempts"],counts["r6_checkpoints"],
      counts["r6_pairs"],counts["r6_post_samples"]))
  db.commit()
  require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","FINAL_SQLITE_BROKEN")
  require(not db.execute("PRAGMA foreign_key_check").fetchall(),"FOREIGN_KEY_BROKEN")
  counts["final_total_attempts"]=db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
  counts["final_sqlite_sha256"]=hashfile(destination)
  (args.out/"r6_import_audit.json").write_text(json.dumps(counts,indent=2)+"\n")
  print("R6_WAREHOUSE_IMPORT_SUCCESS",json.dumps(counts,sort_keys=True),flush=True)
 finally:
  db.close()

if __name__=="__main__":
 main()
