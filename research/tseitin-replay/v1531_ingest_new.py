#!/usr/bin/env python3
"""Append source-verified SAT measurements to frozen V15.3.1 SQLite. Analytics only."""
import argparse, csv, hashlib, json, sqlite3
from collections import defaultdict
from pathlib import Path
import v1531_analytics_db as base

SOURCES = [
 ("DRNAS-V1531-External-Short40","41340619884","e88db7802e5849b5e425fa5a363f3b3d9548ae87",13096398964,40,240),
 ("DRNAS-V1531-External-Medium40","41341529210","8c8d4c132bd021407544d78ea37251a38406b0ab",13097676734,40,240),
 ("DRNAS-V1531-Structural-UUF250-Validation","41343735998","88982f5d1ecd0ab743fba7a5953ebe9e02b0b819",13097888572,40,80),
]
R6_RUN="41343506152"
R6_SHA="2caca7ff6fe77137725a9093f71baba98b6904bb"
CATS=("random3","graphcolor","xor","external_satlib")
MODES=("stable_v1531","monitor","forced_restart25","r5_frozen_gate")

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def sha_ok(s): return isinstance(s,str) and len(s)==64 and all(x in "0123456789abcdef" for x in s.lower())
def optint(s): return int(s) if s is not None and str(s).strip() else None
def optfloat(s): return float(s) if s is not None and str(s).strip() else None
def flag(s):
 s=str(s).lower()
 return 1 if s in ("true","1") else (0 if s in ("false","0") else None)
def rows(db,query,params=()):
 db.row_factory=sqlite3.Row
 return [dict(x) for x in db.execute(query,params)]
def csvout(out,name,data,cols):
 base.export_csv(out/name,data,cols)

def schema(db):
 db.executescript("""
 CREATE TABLE IF NOT EXISTS source_artifacts(
  dataset TEXT PRIMARY KEY,source_run TEXT,source_commit TEXT,artifact_id INTEGER,
  payload_sha256 TEXT,results_sha256 TEXT,runner TEXT,provenance TEXT,warning TEXT);
 CREATE TABLE IF NOT EXISTS attempt_context(
  dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,runner TEXT,seed TEXT,
  source_revision TEXT,formula_sha256 TEXT,row_sha256 TEXT,verification_tier TEXT,
  PRIMARY KEY(dataset,case_name,solver,repeat));
 CREATE TABLE IF NOT EXISTS r6_signals(
  dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,early_restarts INTEGER,
  early_g REAL,early_p REAL,early_d REAL,gate_eligible INTEGER,gate_action INTEGER,
  switch_at INTEGER,final_conflicts INTEGER,final_restarts INTEGER,trace_points INTEGER,
  PRIMARY KEY(dataset,case_name,solver,repeat));
 CREATE TABLE IF NOT EXISTS verified_certificates(
  formula_sha256 TEXT PRIMARY KEY,dataset TEXT,source_run TEXT,source_commit TEXT,
  source_path TEXT,variables INTEGER,clauses INTEGER,rank_coeff INTEGER,
  rank_augmented INTEGER,method TEXT,payload_sha256 TEXT,proof_sha256 TEXT);
 """)

def source(db,dataset,run,commit,aid,path,resultsha,runner,provenance,warning):
 record=(dataset,run,commit,aid,sha(path),resultsha,runner,provenance,warning)
 old=db.execute("SELECT source_run,source_commit,artifact_id,payload_sha256 FROM source_artifacts WHERE dataset=?",(dataset,)).fetchone()
 if old:
  if tuple(old)!=record[1:5]: raise ValueError("Changed artifact for existing dataset: "+dataset)
 else: db.execute("INSERT INTO source_artifacts VALUES (?,?,?,?,?,?,?,?,?)",record)

def ingest_db(db,path,jsonpath,spec):
 dataset,run,commit,aid,nf,na=spec
 with sqlite3.connect("file:"+str(path.resolve())+"?mode=ro",uri=True) as src:
  if src.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("Source SQLite corrupt")
  meta=rows(src,"SELECT * FROM datasets WHERE dataset=?",(dataset,))
  if len(meta)!=1: raise ValueError("Source dataset missing: "+dataset)
  m=meta[0]
  if dataset!=SOURCES[2][0] and (m["source_run"],m["source_sha"])!=(run,commit):
   raise ValueError("Source run/commit mismatch: "+dataset)
  if not sha_ok(m["json_sha256"]) or sha(jsonpath)!=m["json_sha256"]:
   raise ValueError("Source JSON SHA256 mismatch: "+dataset)
  formulas=rows(src,"SELECT * FROM formulas WHERE dataset=?",(dataset,))
  attempts=rows(src,"SELECT * FROM attempts WHERE dataset=?",(dataset,))
  telem=rows(src,"SELECT * FROM telemetry WHERE dataset=?",(dataset,))
  if len(formulas)!=nf or len(attempts)!=na: raise ValueError("Unexpected source counts: "+dataset)
  if any(not sha_ok(f["formula_sha256"]) for f in formulas): raise ValueError("Missing CNF SHA256")
  if len({(a["case_name"],a["solver"],a["repeat"]) for a in attempts})!=na:
   raise ValueError("Duplicate source attempt")
  known={f["case_name"]:f for f in formulas}
  for a in attempts:
   if a["case_name"] not in known or a["seconds"] is None or a["seconds"]<0:
    raise ValueError("Invalid attempt")
   e=known[a["case_name"]]["expected"]
   if e in ("SAT","UNSAT") and a["status"] in ("SAT","UNSAT") and e!=a["status"]:
    raise ValueError("Label contradiction")
  old=db.execute("SELECT COUNT(*) FROM datasets WHERE dataset=?",(dataset,)).fetchone()[0]
  if old:
   if db.execute("SELECT COUNT(*) FROM attempts WHERE dataset=?",(dataset,)).fetchone()[0]!=na:
    raise ValueError("Conflicting existing dataset")
  else:
   db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
    (dataset,m["provenance"],m["description"],run,commit,m["runner"],m["timeout"],m["json_sha256"]))
   for table,rr in (("formulas",formulas),("attempts",attempts),("telemetry",telem)):
    for r in rr:
     cols=list(r)
     db.execute("INSERT INTO "+table+" ("+",".join(cols)+") VALUES ("+",".join("?" for _ in cols)+")",
                [r[c] for c in cols])
  source(db,dataset,run,commit,aid,path,m["json_sha256"],m["runner"],m["provenance"],
         "SATLIB not official. UNSAT labels are not independently validated certificates.")
  return dict(dataset=dataset,formulas=nf,attempts=na,new=not bool(old))

def ingest_r6(db,csvpath,resultspath,tracespath):
 data=json.loads(resultspath.read_text())
 rs=list(csv.DictReader(csvpath.open(newline="")))
 traces=[json.loads(x) for x in tracespath.read_text().splitlines() if x.strip()]
 trace={(t["category"],t["formula"],t["mode"],int(t["repeat"])):t for t in traces}
 if len(rs)!=480 or len(trace)!=480 or data.get("total_measurements")!=480 or data.get("unique_formulas")!=40:
  raise ValueError("R6 must contain 480 distinct attempts and traces on 40 formulas")
 if data.get("early_prefix_mismatch_count")!=0: raise ValueError("R6 prefix inconsistency")
 manifest={m["category"]:m for m in data["manifests"]}
 if set(manifest)!=set(CATS): raise ValueError("Unexpected R6 categories")
 bycat=defaultdict(list)
 for r in rs:
  if r["category"] not in CATS or r["mode"] not in MODES or not sha_ok(r["formula_sha256"]):
   raise ValueError("R6 invalid category/mode/SHA")
  if r["error"] or r["status"] not in ("SAT","UNSAT","TIMEOUT"): raise ValueError("R6 failed attempt")
  if r["status"]!="TIMEOUT" and abs(float(r["wall_s"])-float(r["par2_s"]))>.001:
   raise ValueError("R6 invalid PAR-2")
  bycat[r["category"]].append(r)
 result=[]
 for cat in CATS:
  dataset="DRNAS-R6-"+cat
  m=manifest[cat]; rr=bycat[cat]
  if len(rr)!=120 or len(m["cases"])!=10 or m["source_commit"]!=R6_SHA or m["cap_seconds"]!=8:
   raise ValueError("R6 category source mismatch: "+cat)
  cases={f["formula"]:f for f in m["cases"]}
  if len(cases)!=10 or len({f["formula_sha256"] for f in cases.values()})!=10:
   raise ValueError("R6 formula duplicate")
  keys={(r["formula"],r["mode"],int(r["repeat"])) for r in rr}
  if len(keys)!=120 or keys!={(c,mode,i) for c in cases for mode in MODES for i in range(3)}:
   raise ValueError("R6 missing/duplicate pair")
  if any(r["runner"]!=m["runner"] or r["formula_sha256"]!=cases[r["formula"]]["formula_sha256"]
         or r["expected"]!=cases[r["formula"]]["expected"] for r in rr):
   raise ValueError("R6 runner or source hash mismatch")
  provenance="external_previously_seen" if cat=="external_satlib" else "generated_development"
  old=db.execute("SELECT COUNT(*) FROM datasets WHERE dataset=?",(dataset,)).fetchone()[0]
  if old:
   if db.execute("SELECT COUNT(*) FROM attempts WHERE dataset=?",(dataset,)).fetchone()[0]!=120:
    raise ValueError("R6 existing dataset conflict")
  else:
   db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
    (dataset,provenance,"R6 exploratory four frozen strategies; not official",R6_RUN,R6_SHA,
     m["runner"],8.0,sha(csvpath)))
   for name,f in cases.items():
    db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",
     (dataset,name,cat,f["expected"],f["formula_sha256"],None,f.get("path"),f.get("n"),f.get("clauses")))
   for r in rr:
    case,mode,rep=r["formula"],r["mode"],int(r["repeat"])
    status,expected=r["status"],r["expected"]
    if expected in ("SAT","UNSAT") and status in ("SAT","UNSAT") and status!=expected:
     raise ValueError("R6 status mismatch")
    satok,unsatok=flag(r["sat_model_checked"]),flag(r["native_unsat_certificate_checked"])
    if status=="SAT" and satok!=1: raise ValueError("R6 missing SAT witness")
    verified=1 if (status=="SAT" and satok==1) or (status=="UNSAT" and unsatok==1) else None
    tier="sat_witness" if satok==1 else ("native_unsat_certificate" if unsatok==1 else "unsat_label_only")
    db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,case,mode,rep,float(r["wall_s"]),status,verified,r["route"],satok,unsatok,
      float(r["par2_s"]),optint(r["exit_code"])))
    db.execute("INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",
     (dataset,case,mode,rep,r["runner"],r["seed"],r["source_revision"],r["formula_sha256"],
      hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest(),tier))
    db.execute("INSERT INTO r6_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,case,mode,rep,optint(r["early_restarts"]),optfloat(r["early_g"]),
      optfloat(r["early_p"]),optfloat(r["early_d"]),flag(r["gate_eligible"]),
      flag(r["gate_action"]),optint(r["switch_at"]),optint(r["final_conflicts"]),
      optint(r["final_restarts"]),optint(r["trace_points"])))
    t=trace[(cat,case,mode,rep)]
    for i,pt in enumerate(t["points"]):
     db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (dataset,case,mode,rep,i,None,optint(pt.get("conflict")),optint(pt.get("propagations")),
       optint(pt.get("restarts")),optint(pt.get("learned")),None))
  source(db,dataset,R6_RUN,R6_SHA,13098233449,csvpath,sha(resultspath),m["runner"],provenance,
         "R6 non-official; generated/prior public; UNSAT mostly label-only.")
  result.append(dict(dataset=dataset,formulas=10,attempts=120,new=not bool(old)))
 return result

def certificates(db,path,proof):
 rr=list(csv.DictReader(path.open(newline="")))
 if len(rr)!=10: raise ValueError("Expected ten affine certificates")
 new=0
 for r in rr:
  if not (sha_ok(r["sha256"]) and r["certificate_verified"]=="True" and
          r["cnf_xor_equivalence_checked"]=="True" and
          int(r["rank_augmented"])>int(r["rank_coeff"])):
   raise ValueError("Invalid independent GF2 certificate")
  matches=db.execute("SELECT dataset FROM formulas WHERE formula_sha256=? AND category='dubois_unsat'",
                     (r["sha256"],)).fetchall()
  if len(matches)!=1 or matches[0][0]!="DRNAS-V1531-External-Short40":
   raise ValueError("Certificate not matched to measured CNF")
  if db.execute("SELECT 1 FROM verified_certificates WHERE formula_sha256=?",(r["sha256"],)).fetchone():
   continue
  db.execute("INSERT INTO verified_certificates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
   (r["sha256"],matches[0][0],"41344096160","ff00cc545c53bceb04af504514e75e3f06551f4f",
    r["file"],int(r["nvars"]),int(r["clauses"]),int(r["rank_coeff"]),
    int(r["rank_augmented"]),"CNF-XOR equivalence and GF(2) rank contradiction",sha(path),sha(proof)))
  new+=1
 return new

def extra(db,out):
 for table in ("source_artifacts","attempt_context","r6_signals","verified_certificates"):
  cur=db.execute("SELECT * FROM "+table+" ORDER BY 1,2,3,4")
  cols=[x[0] for x in cur.description]
  csvout(out,table+".csv",[dict(zip(cols,r)) for r in cur.fetchall()],cols)
 overlap=rows(db,"""SELECT formula_sha256,COUNT(DISTINCT dataset) AS datasets,
 GROUP_CONCAT(DISTINCT dataset) AS dataset_names FROM formulas WHERE formula_sha256 IS NOT NULL
 GROUP BY formula_sha256 HAVING COUNT(DISTINCT dataset)>1 ORDER BY datasets DESC,formula_sha256""")
 csvout(out,"cross_dataset_hash_overlaps.csv",overlap,
        ["formula_sha256","datasets","dataset_names"])
 pairs=rows(db,"""SELECT a.dataset,a.case_name,a.repeat,a.solver AS treatment,
 m.par2_seconds AS monitor_par2,a.par2_seconds AS treatment_par2,
 CASE WHEN a.par2_seconds>0 THEN m.par2_seconds/a.par2_seconds END AS speedup,
 s.early_g,s.early_p,s.early_d,s.gate_action,s.final_conflicts
 FROM attempts a JOIN attempts m ON a.dataset=m.dataset AND a.case_name=m.case_name
 AND a.repeat=m.repeat AND m.solver='monitor'
 LEFT JOIN r6_signals s ON s.dataset=a.dataset AND s.case_name=a.case_name
 AND s.solver=a.solver AND s.repeat=a.repeat
 WHERE a.dataset LIKE 'DRNAS-R6-%' AND a.solver!='monitor'
 ORDER BY a.dataset,a.case_name,a.repeat,a.solver""")
 if len(pairs)!=360: raise ValueError("Expected 360 R6 matched comparisons")
 cols=["dataset","case_name","repeat","treatment","monitor_par2","treatment_par2",
       "speedup","early_g","early_p","early_d","gate_action","final_conflicts"]
 csvout(out,"r6_paired.csv",pairs,cols)
 sums=[]
 for dataset,treatment in sorted({(r["dataset"],r["treatment"]) for r in pairs}):
  sub=[r for r in pairs if r["dataset"]==dataset and r["treatment"]==treatment]
  b=sum(r["monitor_par2"] for r in sub);v=sum(r["treatment_par2"] for r in sub)
  sums.append(dict(dataset=dataset,treatment=treatment,pairs=len(sub),
                   monitor_par2_sum=round(b,8),treatment_par2_sum=round(v,8),
                   speedup_sum=round(b/v,8)))
 csvout(out,"r6_paired_summary.csv",sums,
        ["dataset","treatment","pairs","monitor_par2_sum","treatment_par2_sum","speedup_sum"])
 return overlap,pairs,sums

def scatter(out,pairs):
 import matplotlib
 matplotlib.use("Agg")
 import matplotlib.pyplot as plt
 names=[]
 for mode in ("stable_v1531","forced_restart25","r5_frozen_gate"):
  fig,ax=plt.subplots(figsize=(8,6))
  sub=[r for r in pairs if r["treatment"]==mode]
  for dataset in sorted({r["dataset"] for r in sub}):
   zz=[r for r in sub if r["dataset"]==dataset]
   ax.scatter([r["monitor_par2"] for r in zz],[r["treatment_par2"] for r in zz],
              label=dataset.replace("DRNAS-R6-",""),alpha=.65)
  ax.set_xscale("log");ax.set_yscale("log")
  ax.plot([.0001,1],[.0001,1],"--",linewidth=1)
  ax.set(xlabel="R6 monitor PAR-2 (s)",ylabel=mode+" PAR-2 (s)",
         title="R6 matched attempts; not official")
  ax.legend();fig.tight_layout()
  name="scatter_r6_monitor_vs_"+mode+".png"
  fig.savefig(out/name,dpi=140);plt.close(fig);names.append(name)
 return names

def main():
 p=argparse.ArgumentParser()
 for key in ("db","out","short-db","short-json","medium-db","medium-json","uuf-db","uuf-json",
             "r6-csv","r6-json","r6-traces","cert-csv","cert-json"):
  p.add_argument("--"+key,required=True,type=Path)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(a.db)
 try:
  schema(db)
  with db:
   imported=[ingest_db(db,a.short_db,a.short_json,SOURCES[0]),
             ingest_db(db,a.medium_db,a.medium_json,SOURCES[1]),
             ingest_db(db,a.uuf_db,a.uuf_json,SOURCES[2])]
   imported+=ingest_r6(db,a.r6_csv,a.r6_json,a.r6_traces)
   newcert=certificates(db,a.cert_csv,a.cert_json)
  grouped,paired,telemetry=base.analytics(db,a.out)
  charts=base.plot(a.out,paired,telemetry)
  overlap,r6pairs,r6summary=extra(db,a.out)
  charts+=scatter(a.out,r6pairs)
  counts={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
          for t in ("datasets","formulas","attempts","telemetry",
                    "source_artifacts","attempt_context","verified_certificates")}
  if counts["datasets"]<12 or counts["attempts"]<5048 or db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
   raise ValueError("Cumulative database incomplete/corrupt")
  audit=dict(ingested_sources=[{k:v for k,v in x.items() if k!="new"} for x in imported],
             counts=counts,cross_dataset_formula_hash_overlaps=len(overlap),
             r6_paired_attempts=len(r6pairs),r6_paired_summary=r6summary,
             verified_certificates_total=counts["verified_certificates"],charts=charts,
             cautions=["UNSAT label alone is not an independent proof",
                       "R6 monitor is not identical to original Kissat or V15.3.1",
                       "R6 uses generated and previously public SATLIB, not official",
                       "UUF250 correlation with Kissat is not a DRNAS speedup proof"])
  (a.out/"ingest_audit.json").write_text(json.dumps(audit,indent=2))
  summ=a.out/"summary.json";data=json.loads(summ.read_text())
  data["incremental_ingest"]=audit;summ.write_text(json.dumps(data,indent=2))
  print(json.dumps(dict(new_datasets=[x["dataset"] for x in imported if x["new"]],
                        new_certificates=newcert,counts=counts,r6_summary=r6summary),indent=2))
 finally: db.close()

if __name__=="__main__": main()
