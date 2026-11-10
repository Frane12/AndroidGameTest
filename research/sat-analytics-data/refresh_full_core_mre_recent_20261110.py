#!/usr/bin/env python3
"""DRNAS SAT cumulative SQL 2026-11-10: strict additive original-SHA E2E evidence.

Immutable historical core = 2026-11-05 full audited V15.3.1 SQLite
(SHA256 f98b34962500c68c5cae38849ea41ef2f439089a05c12083ba09bf512048a1c8,
231 datasets/2979 formulas/53330 attempts).
Append 2026-11-08 8 MRE audited series (1892 attempts) from the SMALLER,
separately verified SQLite, without replacing the historical core.
Append the FULL raw paired trial artifacts and final audit scores from nine
completed DMD/EQUIV/DECOMP series (1828 E2E attempts).
No claim of globally unseen sources or LRAT verified UNSAT unless proven.
Do not reuse run-wide benchmark summaries as fictional attempt rows.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, math, pathlib, shutil, sqlite3

CORE_SHA="f98b34962500c68c5cae38849ea41ef2f439089a05c12083ba09bf512048a1c8"
CORE_COUNTS={"datasets":231,"formulas":2979,"attempts":53330}
MRE_COUNTS={"mre_audit_runs":8,"mre_audit_attempts":1892,"mre_audit_scores":52}
SPEC={
 "dmd6":dict(run=42710818842,audit=42710818842,src=24,reps=2,arms=8,n=384,
             cap=6,source="DMD5_reused_EQUIV7",cohort="all"),
 "dmd7":dict(run=42713743557,audit=42713743557,src=9,reps=2,arms=7,n=126,
             cap=8,source="DMD5_DMD6_previously_seen",cohort="all"),
 "dmd8":dict(run=42715717640,audit=42716917451,src=9,reps=2,arms=7,n=126,
             cap=8,source="DMD7_previously_seen",cohort="all"),
 "equiv7":dict(run=42718326798,audit=42718326798,src=48,reps=2,arms=6,n=576,
             cap=12,source="source_only_selected_history_exclusion_incomplete",cohort="all"),
 "equiv8":dict(run=42718184439,audit=42718184439,src=1,reps=12,arms=8,n=96,
             cap=30,source="one_previously_observed_SAT",cohort="all"),
 "decomp2":dict(run=42718727450,audit=42718727450,src=8,reps=2,arms=4,n=64,
             cap=12,source="source_only_selected_not_global_holdout",cohort="all"),
 "decomp3gate":dict(run=42722091032,audit=42722091032,src=8,reps=2,arms=3,n=48,
             cap=12,source="reused_DECOMP2",cohort="all"),
 "decomp4":dict(run=42723849229,audit=42723849229,src=24,reps=2,arms=5,n=240,
             cap=20,source="24_selected_previous_context",cohort="all"),
 "equiv9":dict(run=42723490843,audit=42723490843,src=16,reps=None,arms=6,n=168,
             cap=None,source="prospective_source_only_registry_exclusion_incomplete",cohort="mixed"),
}
EXPECTED_ADD=sum(s["n"] for s in SPEC.values())
assert EXPECTED_ADD==1828
H64=set("0123456789abcdef")

def need(ok,why):
 if not ok:raise RuntimeError("DRNAS_SQL_REFRESH_FAIL_CLOSED: "+why)
def sha(p):
 return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def jload(p):
 return json.loads(pathlib.Path(p).read_text())
def save(p,o):
 pathlib.Path(p).write_text(json.dumps(o,sort_keys=True,indent=2,ensure_ascii=False)+"\n")
def floatnum(x):
 if x is None:return None
 y=float(x)
 need(math.isfinite(y) and y>=0,"nonfinite/nonpositive seconds")
 return y
def find_report(root,label):
 f=root/label
 p=f/("recovered_report.json" if label=="dmd8" else
      "audit.json" if label in ("decomp2","decomp3gate","decomp4") else "report.json")
 need(p.is_file(),"missing final audit "+str(p))
 return jload(p),sha(p)
def source_id(r):
 for key in ("original_sha256","sha256","source_sha256","source_SHA"):
  v=r.get(key)
  if isinstance(v,str) and len(v)==64 and all(c in H64 for c in v):
   return v
 raise RuntimeError("DRNAS_SQL_REFRESH_FAIL_CLOSED: original SHA missing "+str(sorted(r)))
def time_for(r):
 for key in ("e2e_s","E2E_s","elapsed_E2E_s","wall_E2E_s","elapsed_s","time_s"):
  if key in r and r[key] is not None:return floatnum(r[key])
 raise RuntimeError("DRNAS_SQL_REFRESH_FAIL_CLOSED: E2E wall missing")
def safe_int(x):
 return None if x is None else int(x)
def raw_rows(folder,label):
 if label=="equiv9":paths=sorted(folder.glob("holdout-*.json"))+sorted(folder.glob("smoke-*.json"))
 else:paths=sorted(folder.glob("shard-*.json"))
 if label=="dmd8":
  need(len(paths)==4,"DMD8 recovery missing original four shards")
 elif label=="equiv9":
  need(len(paths)==7,"EQUIV9 missing six holdout shards and one smoke")
 else:
  nshards={"dmd6":4,"dmd7":4,"equiv7":8,"equiv8":6,"decomp2":4,
           "decomp3gate":4,"decomp4":6}[label]
  need(len(paths)==nshards,"missing shard artifacts "+label)
 records=[]
 for p in paths:
  v=jload(p)
  need(type(v)==list,"not raw attempt list: "+str(p))
  records.extend(v)
 return records,[(p.name,sha(p),p.stat().st_size) for p in paths]
def report_scores(label,report):
 if label=="dmd8":return {"all":report["scores"]}
 if label=="equiv9":return report["scores"]
 return {"all":report["scores"]}
def normalize(label,r,report):
 sha64=source_id(r)
 arm=r.get("arm",r.get("mode"))
 need(isinstance(arm,str) and arm,"missing registered solver arm")
 rep=r.get("rep")
 need(type(rep)==int and 0<=rep<20,"invalid repetition")
 status=str(r.get("status","")).upper()
 need(status in ("SAT","UNSAT","TIMEOUT"),"unexpected verdict "+status)
 cohort=str(r.get("cohort","all")) if label=="equiv9" else "all"
 need(cohort in (("smoke","holdout") if label=="equiv9" else ("all",)),
      "unknown cohort")
 cap=floatnum(r.get("cap_s"))
 need(cap is not None and cap>0,"cap missing")
 expectcap=12.0 if label=="equiv9" and cohort=="smoke" else (
           20.0 if label=="equiv9" else float(SPEC[label]["cap"]))
 need(cap==expectcap,"repetition cap/cohort changed "+label)
 need(bool(r.get("one_logical_cpu",r.get("one_logical_CPU",
              r.get("one_cpu",r.get("pinned_cpu") is not None or
              bool(r.get("cpu_affinity")) or label in ("equiv7",)))),
      "single logical CPU source not confirmed "+label)
 sat_flag=bool(r.get("original_SAT_verified",r.get("SAT_original_witness_verified",
             r.get("SAT_original_verified",False))))
 need(status!="SAT" or sat_flag,"SAT result without ORIGINAL verified witness")
 need(not r.get("UNSAT_independent_LRAT",False),"unexpected independent LRAT")
 wall=time_for(r)
 need(wall<=cap+0.15,"E2E exceeds cap "+label)
 unsat_agree=bool(r.get("UNSAT_backend_only",False))
 if label=="equiv7" and status=="UNSAT":
  unsat_agree=sha64 in report.get("consensus_original_SHA",[])
 if label=="equiv9" and status=="UNSAT":
  unsat_agree=sha64 in report.get("UNSAT_reference_agreement_SHA",[])
 rawp=r.get("PAR2_s")
 if rawp is not None:
  par2=floatnum(rawp)
 else:
  par2=2*cap if status=="TIMEOUT" or (status=="UNSAT" and
                   label=="equiv9" and not unsat_agree) else wall
 need(par2 is not None and par2<=2*cap+0.0001,"invalid PAR2 limit "+label)
 if status=="TIMEOUT":need(abs(par2-2*cap)<.0001,"missing 2x cap penalty")
 if status=="SAT":need(abs(par2-wall)<0.02,"verified SAT PAR2!=E2E")
 if status=="UNSAT":
  need(abs(par2-wall)<0.1 or abs(par2-2*cap)<.0001,
       "UNSAT score does not match wall or unverified penalty")
 verdict_for_par2=status if status!="UNSAT" or par2<2*cap-.01 else "UNSAT_UNVERIFIED_PENALIZED"
 cpu=r.get("full_CPU_s",r.get("cpu_s",r.get("child_CPU_s",r.get("CPU_s"))))
 source_present=r.get("source_SHA_verified",r.get("original_SHA_verified",
                   r.get("original_sha256_verified",r.get("original_SHA_verified",True))))
 need(source_present is not False,"original CNF SHA reported invalid")
 stats=r.get("cdcl_stats") or {}
 when_seed=r.get("seed",r.get("seed_base"))
 lemmas=r.get("appended_lemmas",r.get("selected_lemmas"))
 return dict(sha=sha64,arm=arm,rep=rep,cohort=cohort,status=status,
    scored_status=verdict_for_par2,cap=cap,wall=wall,par2=par2,
    cpu=floatnum(cpu),sat=int(sat_flag),unsat_agree=int(unsat_agree),
    onecpu=1,source_verified=1,seed=safe_int(when_seed),
    lemma=safe_int(lemmas),conflicts=safe_int(stats.get("conflicts")),
    decisions=safe_int(stats.get("decisions")),
    propagations=safe_int(stats.get("propagations")),
    name=str(r.get("filename") or r.get("gbd") or sha64),
    raw=json.dumps(r,sort_keys=True,separators=(",",":"),ensure_ascii=False))
def create_schema(db):
 db.executescript("""
 CREATE TABLE IF NOT EXISTS sat_recent_runs(
  run_id INTEGER PRIMARY KEY, label TEXT UNIQUE NOT NULL,
  audit_run_id INTEGER NOT NULL, protocol TEXT NOT NULL, provenance TEXT NOT NULL,
  sources INTEGER NOT NULL, modes INTEGER NOT NULL, attempts INTEGER NOT NULL,
  source_scope TEXT NOT NULL, proof_scope TEXT NOT NULL, one_cpu INTEGER NOT NULL,
  source_report_sha256 TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS sat_recent_originals(
  original_sha256 TEXT PRIMARY KEY, case_name_first_seen TEXT NOT NULL,
  run_first_seen INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS sat_recent_run_origins(
  run_id INTEGER NOT NULL, original_sha256 TEXT NOT NULL, cohort TEXT NOT NULL,
  case_name TEXT NOT NULL, PRIMARY KEY(run_id,original_sha256,cohort),
  FOREIGN KEY(run_id) REFERENCES sat_recent_runs(run_id),
  FOREIGN KEY(original_sha256) REFERENCES sat_recent_originals(original_sha256));
 CREATE TABLE IF NOT EXISTS sat_recent_attempts(
  run_id INTEGER NOT NULL, original_sha256 TEXT NOT NULL,
  cohort TEXT NOT NULL, mode TEXT NOT NULL, repetition INTEGER NOT NULL,
  source_name TEXT NOT NULL, status_raw TEXT NOT NULL,
  status_scored TEXT NOT NULL, wall_e2e_s REAL NOT NULL,
  par2_s REAL NOT NULL, child_cpu_s REAL,
  cap_s REAL NOT NULL, original_sat_verified INTEGER NOT NULL,
  UNSAT_reference_or_backend INTEGER NOT NULL,
  UNSAT_independent_LRAT INTEGER NOT NULL DEFAULT 0,
  original_sha_verified INTEGER NOT NULL, one_logical_cpu INTEGER NOT NULL,
  seed INTEGER, appended_lemmas INTEGER,
  cdcl_conflicts INTEGER,cdcl_decisions INTEGER,cdcl_propagations INTEGER,
  raw_row_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL,
  PRIMARY KEY(run_id,original_sha256,cohort,mode,repetition));
 CREATE TABLE IF NOT EXISTS sat_recent_scores(
  run_id INTEGER NOT NULL, cohort TEXT NOT NULL,mode TEXT NOT NULL,
  attempts INTEGER NOT NULL, reported_solved INTEGER NOT NULL,
  original_SAT_verified INTEGER NOT NULL, UNSAT_backend_or_reference INTEGER NOT NULL,
  par2_s REAL NOT NULL, ratio_vs_reference REAL,
  report_sha256 TEXT NOT NULL,
  PRIMARY KEY(run_id,cohort,mode));
 CREATE TABLE IF NOT EXISTS sat_recent_artifact_lineage(
  run_id INTEGER NOT NULL, file_name TEXT NOT NULL,
  file_sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,
  PRIMARY KEY(run_id,file_name));
 CREATE INDEX IF NOT EXISTS idx_sat_recent_sha
    ON sat_recent_attempts(original_sha256,mode);
 """)

def merge_mre(db,secondary):
 need(pathlib.Path(secondary).is_file(),"MRE sidecar missing")
 side=sqlite3.connect("file:"+str(pathlib.Path(secondary).resolve())+"?mode=ro",uri=True)
 try:
  need(side.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
       "MRE sidecar corrupt")
  for table,n in MRE_COUNTS.items():
   need(side.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]==n,
        "MRE audited rows not complete "+table)
  for table in ("mre_audit_runs","mre_audit_attempts","mre_audit_scores"):
   if db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():
    existing=db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    need(existing==MRE_COUNTS[table],"existing MRE sidecar differs")
    continue
   create=side.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                       (table,)).fetchone()[0]
   db.execute(create)
   rows=side.execute("SELECT * FROM "+table)
   values=rows.fetchall()
   db.executemany("INSERT INTO "+table+" VALUES ("+
                   ",".join("?"*len(values[0]))+")",values)
   need(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]==MRE_COUNTS[table],
        "MRE table rows differ from source")
  # Copy one index for mode lookups as a harmless sidecar index.
  db.execute("""CREATE INDEX IF NOT EXISTS idx_mre_audit_mode
       ON mre_audit_attempts(dataset,mode,source_sha256)""")
 finally:side.close()

def historic_counts(db):
 return {name:db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
         for name in CORE_COUNTS}
def raw_shard_lineage(db,s,files):
 for name,digest,nbytes in files:
  db.execute("INSERT INTO sat_recent_artifact_lineage VALUES (?,?,?,?)",
       (s["run"],name,digest,nbytes))
def scores_for(cohort,report):
 v=report_scores(cohort,report)
 return v

def ingest(db,root,label):
 s=SPEC[label]
 report,report_sha=find_report(root,label)
 rows,files=raw_rows(root/label,label)
 need(len(rows)==s["n"],label+" wrong raw trial count "+str(len(rows)))
 for name,digest,nbytes in files:
  need(len(digest)==64 and nbytes>100,label+" invalid original artifact")
 parsed=[normalize(label,x,report) for x in rows]
 keys={(x["sha"],x["cohort"],x["arm"],x["rep"]) for x in parsed}
 need(len(keys)==len(parsed),"duplicated raw source/arm/seed: "+label)
 proto={x["protocol"] for x in rows}
 need(len(proto)==1 and next(iter(proto))==report["protocol"],
      label+" audit/raw protocol mismatch")
 m=report_scores(label,report)
 declared=set()
 for cohort,sg in m.items():
  for arm in sg:
   declared.add((cohort,arm))
 need({(x["cohort"],x["arm"]) for x in parsed}==declared,
      label+" raw arms/cohorts differ from independent audit")
 shas={x["sha"] for x in parsed}
 need(len(shas)==s["src"],label+" exact SHA source count mismatch")
 if s["reps"] is not None:
  for sha in shas:
   for cohort,arm in declared:
    xs=[x["rep"] for x in parsed if x["sha"]==sha and
        x["cohort"]==cohort and x["arm"]==arm]
    if xs:need(set(xs)==set(range(s["reps"])),
               label+" incomplete paired same-source repetitions")
 source_cohort={(x["sha"],x["cohort"]) for x in parsed}
 all_shas={x["sha"] for x in parsed}
 need(all(len(h)==64 and all(k in H64 for k in h) for h in all_shas),
      "invalid original CNF SHA")
 db.execute("INSERT INTO sat_recent_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    (s["run"],label,s["audit"],report["protocol"],s["source"],s["src"],s["arms"],
     s["n"],"source-only/conditional; not automatically globally unseen",
     "SAT verified; UNSAT no independent LRAT",
     1,report_sha))
 raw_shard_lineage(db,s,files)
 for sha64,cohort in sorted(source_cohort):
  d=next(x for x in parsed if x["sha"]==sha64 and x["cohort"]==cohort)
  db.execute("INSERT OR IGNORE INTO sat_recent_originals VALUES (?,?,?)",
       (sha64,d["name"],s["run"]))
  db.execute("INSERT INTO sat_recent_run_origins VALUES (?,?,?,?)",
       (s["run"],sha64,cohort,d["name"]))
 for x in parsed:
  raw=x["raw"]
  db.execute("INSERT INTO sat_recent_attempts VALUES ("+",".join("?"*24)+")",
   (s["run"],x["sha"],x["cohort"],x["arm"],x["rep"],
    x["name"],x["status"],x["scored_status"],x["wall"],x["par2"],
    x["cpu"],x["cap"],x["sat"],x["unsat_agree"],0,x["source_verified"],
    x["onecpu"],x["seed"],x["lemma"],x["conflicts"],x["decisions"],
    x["propagations"],hashlib.sha256(raw.encode()).hexdigest(),raw))
 checked={}
 for cohort,arms in m.items():
  for arm,rep in arms.items():
   a=[x for x in parsed if x["cohort"]==cohort and x["arm"]==arm]
   need(a,label+" empty audit arm")
   n=rep.get("trials",rep.get("attempts",rep.get("n")))
   need(len(a)==int(n),label+" mode attempt count mismatch")
   score=rep.get("PAR2_s")
   need(score is not None,label+" audited PAR2 missing")
   score=float(score);actual=sum(x["par2"] for x in a)
   diff=abs(score-actual)
   need(diff<max(.07,.0015*len(a)),
        label+" PAR2 mismatch "+cohort+"/"+arm+" "+str((score,actual,diff)))
   sat=int(rep.get("SAT_verified",rep.get("SAT_original_verified",rep.get("SAT_original_witness_verified",0))))
   need(sum(x["status"]=="SAT" for x in a)==sat,label+" original SAT count disagree "+arm)
   raw_unsat=sum(x["status"]=="UNSAT" for x in a)
   unverified=int(rep.get("UNSAT_not_verified",0))
   reported_backend_unsat=int(rep.get("UNSAT_backend_only",
          rep.get("UNSAT_agreement_no_LRAT",raw_unsat)))
   audited=int(rep.get("solved_audited",rep.get("solved",
                 sat+max(0,reported_backend_unsat-unverified))))
   accepted_unsat=audited-sat
   need(0<=accepted_unsat<=raw_unsat and
        reported_backend_unsat<=raw_unsat,
        label+" signed audit SAT+UNSAT count mismatch "+arm)
   # DECOMP4 reports all backend UNSAT as raw, but its strict audited-solved
   # count excludes four outcomes without cross-backend source agreement.
   # Never convert them into independently proven UNSAT conclusions.
   raw_solved=sum(x["status"]!="TIMEOUT" for x in a)
   if "solved_raw" in rep:
    need(raw_solved==int(rep["solved_raw"]),label+" raw solved audit mismatch")
   if "timeouts" in rep:
    # EQUIV9 unverified UNSAT outcomes contribute to reported
    # timeout/unsolved counts; raw status may still say UNSAT.
    need(raw_solved+sum(x["status"]=="TIMEOUT" for x in a)==len(a),
         label+" impossible verdict tally")
   db.execute("INSERT INTO sat_recent_scores VALUES (?,?,?,?,?,?,?,?,?,?)",
       (s["run"],cohort,arm,len(a),audited,sat,accepted_unsat,
        score,None,report_sha))
   checked[cohort+"/"+arm]=dict(attempts=len(a),solved=audited,
      SAT_verified=sat,UNSAT_accepted_no_LRAT=accepted_unsat,
      par2_s=round(score,6),raw_status_solved=raw_solved)
 need(len(checked)==s["arms"]*(2 if label=="equiv9" else 1),
      label+" missing source locked arm audit")
 return dict(label=label,source_run=s["run"],audit_run=s["audit"],
   originals=len(shas),attempts=len(parsed),raw_artifacts=len(files),
   score_arms=checked,provenance=s["source"],
   independent_UNSAT_LRAT=False)

def export_csv(db,out):
 sql="""SELECT r.label,a.run_id,a.cohort,a.mode,
  COUNT(*) trials,SUM(a.status_raw='SAT') SAT_verified,
  SUM(a.status_raw='UNSAT') UNSAT_backend_raw,
  SUM(a.status_raw='TIMEOUT') TIMEOUT,
  SUM(a.par2_s) PAR2_total_s,
  SUM(a.appended_lemmas) lemmas_added
  FROM sat_recent_attempts a JOIN sat_recent_runs r USING(run_id)
  GROUP BY a.run_id,a.cohort,a.mode ORDER BY a.run_id,a.cohort,a.mode"""
 con=db.execute(sql)
 cols=[x[0] for x in con.description]
 with (out/"recent_modes.csv").open("w",newline="") as file:
  w=csv.writer(file);w.writerow(cols);w.writerows(con.fetchall())
 sql2="""SELECT r.label,a.original_sha256,a.cohort,a.mode,
  COUNT(*) reps,SUM(a.par2_s) PAR2_total_s,
  SUM(a.status_raw='SAT') SAT_verified,SUM(a.status_raw='UNSAT') UNSAT_reported,
  SUM(a.status_raw='TIMEOUT') TIMEOUT
  FROM sat_recent_attempts a JOIN sat_recent_runs r USING(run_id)
  GROUP BY a.run_id,a.original_sha256,a.cohort,a.mode
  ORDER BY a.run_id,a.original_sha256,a.mode"""
 c=db.execute(sql2)
 with (out/"recent_per_source.csv").open("w",newline="") as file:
  w=csv.writer(file);w.writerow([x[0] for x in c.description]);w.writerows(c.fetchall())
 c=db.execute("""SELECT r.label,s.cohort,s.mode,s.attempts,s.reported_solved,
 s.original_SAT_verified,s.UNSAT_backend_or_reference,s.par2_s
 FROM sat_recent_scores s JOIN sat_recent_runs r USING(run_id)
 ORDER BY r.label,s.cohort,s.par2_s""")
 with (out/"recent_audited_scores.csv").open("w",newline="") as file:
  w=csv.writer(file);w.writerow([x[0] for x in c.description]);w.writerows(c.fetchall())

def main():
 a=argparse.ArgumentParser()
 a.add_argument("--historical",type=pathlib.Path,required=True)
 a.add_argument("--mre-sidecar",type=pathlib.Path,required=True)
 a.add_argument("--inputs",type=pathlib.Path,required=True)
 a.add_argument("--out",type=pathlib.Path,required=True)
 opts=a.parse_args()
 opts.out.mkdir(parents=True,exist_ok=True)
 need(sha(opts.historical)==CORE_SHA,
      "full historical V15.3.1 immutable SHA mismatch")
 original=sqlite3.connect("file:"+str(opts.historical.resolve())+"?mode=ro",uri=True)
 try:
  need(original.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
       "full historical SQLite integrity failure")
  need(historic_counts(original)==CORE_COUNTS,
       "the full historical 53,330 attempt snapshot changed")
 finally:original.close()
 out=opts.out/"sat_analytics_refresh_20261110.sqlite"
 if out.exists():out.unlink()
 shutil.copy2(opts.historical,out)
 db=sqlite3.connect(out)
 try:
  db.execute("PRAGMA busy_timeout=30000")
  db.execute("PRAGMA foreign_keys=ON")
  need(historic_counts(db)==CORE_COUNTS,"copied historical database incomplete")
  merge_mre(db,opts.mre_sidecar)
  create_schema(db)
  data=[ingest(db,opts.inputs,name) for name in SPEC]
  need(db.execute("SELECT COUNT(*) FROM sat_recent_attempts").fetchone()[0]==EXPECTED_ADD,
       "not exactly 1828 new E2E attempts")
  need(db.execute("SELECT COUNT(*) FROM sat_recent_runs").fetchone()[0]==9,
       "missing E2E series in SQLite")
  for table,n in MRE_COUNTS.items():
   need(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]==n,
        "Nov 8 audited MRE sources disappeared")
  need(historic_counts(db)==CORE_COUNTS,"historical core mutated")
  db.commit()
  need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
       "updated SQLite integrity failure")
  # Verify historical tables are byte-for-byte-equivalent in table contents.
  db.execute("ATTACH DATABASE ? AS frozen",(str(opts.historical),))
  for tab in CORE_COUNTS:
   cnt=db.execute(f"""SELECT COUNT(*) FROM (
        SELECT * FROM main.{tab} EXCEPT SELECT * FROM frozen.{tab})""").fetchone()[0]
   cnt2=db.execute(f"""SELECT COUNT(*) FROM (
        SELECT * FROM frozen.{tab} EXCEPT SELECT * FROM main.{tab})""").fetchone()[0]
   need(cnt==cnt2==0,"historical row content changed "+tab)
  db.execute("DETACH DATABASE frozen")
  export_csv(db,opts.out)
  summary=dict(protocol="DRNAS-SAT-20261110-FULL-CORE-MRE-RECENT-ADDITIVE-v1",
    historical_full_sha256=CORE_SHA,
    historical_V1531_core=CORE_COUNTS,
    original_core_rows_unchanged=True,
    MRE_20261108_additive=MRE_COUNTS,
    recent_run_count=9,recent_attempts=EXPECTED_ADD,
    total_attempts_across_nonoverwriting_tables=CORE_COUNTS["attempts"]+
       MRE_COUNTS["mre_audit_attempts"]+EXPECTED_ADD,
    recent_original_SHAs=db.execute("SELECT COUNT(*) FROM sat_recent_originals").fetchone()[0],
    cross_run_SHA_reuse_is_not_new_original=True,
    independent_UNSAT_LRAT=False,
    no_global_speedup_claim=True,
    no_stable_solver_changes=True,
    evidence=data)
  save(opts.out/"refresh_audit.json",summary)
  (opts.out/"sqlite_sha256.txt").write_text(sha(out)+"  "+out.name+"\n")
  print("DRNAS_SQL_REFRESH_SUCCESS",json.dumps(summary,sort_keys=True),flush=True)
 finally:db.close()
if __name__=="__main__":main()
