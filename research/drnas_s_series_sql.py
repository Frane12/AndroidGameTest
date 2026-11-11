#!/usr/bin/env python3
"""DRNAS S21+ persistent SQL ledger. Prior successful S-series artifacts are imported
by explicit prior-run reference. Benchmark holdout results never tune same-run policy.
"""
import argparse,hashlib,json,pathlib,sqlite3,datetime
SCHEMA="""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS series_run(
 series TEXT NOT NULL, run_id TEXT NOT NULL, created_utc TEXT NOT NULL,
 source_count INTEGER NOT NULL, trial_count INTEGER NOT NULL,
 prior_run_id TEXT, input_sha256 TEXT NOT NULL,
 PRIMARY KEY(series,run_id));
CREATE TABLE IF NOT EXISTS source(
 sha256 TEXT PRIMARY KEY, source_entry TEXT, source_kind TEXT, first_series TEXT);
CREATE TABLE IF NOT EXISTS trial(
 series TEXT NOT NULL,run_id TEXT NOT NULL,source_sha TEXT NOT NULL,
 rep INTEGER NOT NULL,arm TEXT NOT NULL,status TEXT NOT NULL,
 e2e_s REAL NOT NULL,par2_verified_s REAL NOT NULL,par2_reported_s REAL NOT NULL,
 telemetry_json TEXT NOT NULL,
 PRIMARY KEY(series,run_id,source_sha,rep,arm),
 FOREIGN KEY(series,run_id) REFERENCES series_run(series,run_id),
 FOREIGN KEY(source_sha) REFERENCES source(sha256));
CREATE TABLE IF NOT EXISTS decision_event(
 series TEXT NOT NULL,run_id TEXT NOT NULL,source_sha TEXT NOT NULL,
 rep INTEGER NOT NULL,arm TEXT NOT NULL,event TEXT NOT NULL,payload_json TEXT NOT NULL,
 PRIMARY KEY(series,run_id,source_sha,rep,arm,event));
CREATE TABLE IF NOT EXISTS policy_candidate(
 series TEXT NOT NULL,run_id TEXT NOT NULL,arm TEXT NOT NULL,
 verified_pairs INTEGER NOT NULL,par2_verified_s REAL NOT NULL,
 training_only INTEGER NOT NULL DEFAULT 1,
 PRIMARY KEY(series,run_id,arm));
CREATE INDEX IF NOT EXISTS idx_trial_arm ON trial(series,arm,status);
"""
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--series",required=True)
 p.add_argument("--run-id",required=True)
 p.add_argument("--input",type=pathlib.Path,required=True)
 p.add_argument("--output",type=pathlib.Path,required=True)
 p.add_argument("--prior",type=pathlib.Path)
 p.add_argument("--prior-run-id",default="")
 a=p.parse_args()
 assert a.series.startswith("S") and a.series[1:].isdigit()
 assert a.input.is_file()
 data=a.input.read_bytes();obj=json.loads(data)
 sources=obj["sources"];rows=obj["rows"]
 assert sources and rows
 assert len({s["sha256"] for s in sources})==len(sources)
 allowed={s["sha256"] for s in sources}
 assert all(r["sha256"] in allowed for r in rows)
 assert len({(r["sha256"],r["rep"],r["arm"]) for r in rows})==len(rows)
 assert all(r["status"] in ("SAT_VERIFIED","UNSAT_UNVERIFIED","UNKNOWN","GF2_UNSAT_VERIFIED") for r in rows)
 a.output.parent.mkdir(parents=True,exist_ok=True)
 if a.prior:
  assert a.prior.is_file() and a.prior_run_id,"prior DB requires prior run identity"
  import shutil;shutil.copy2(a.prior,a.output)
 elif a.output.exists():a.output.unlink()
 conn=sqlite3.connect(a.output)
 conn.executescript(SCHEMA)
 conn.execute("BEGIN IMMEDIATE")
 assert not conn.execute("SELECT 1 FROM series_run WHERE series=? AND run_id=?",(a.series,a.run_id)).fetchone(),"duplicate run"
 for s in sources:
  conn.execute("INSERT OR IGNORE INTO source VALUES(?,?,?,?)",
   (s["sha256"],s.get("archive_entry",s.get("entry","")),s.get("source_kind","original"),a.series))
 conn.execute("INSERT INTO series_run VALUES(?,?,?,?,?,?,?)",
  (a.series,a.run_id,datetime.datetime.now(datetime.timezone.utc).isoformat(),
   len(sources),len(rows),a.prior_run_id,hashlib.sha256(data).hexdigest()))
 for r in rows:
  conn.execute("INSERT INTO trial VALUES(?,?,?,?,?,?,?,?,?,?)",
   (a.series,a.run_id,r["sha256"],r["rep"],r["arm"],r["status"],
    r["E2E_s"],r["PAR2_verified_s"],r["PAR2_reported_s"],
    json.dumps(r.get("telemetry",{}),sort_keys=True)))
  conn.execute("INSERT INTO decision_event VALUES(?,?,?,?,?,?,?)",
   (a.series,a.run_id,r["sha256"],r["rep"],r["arm"],"trial_completed",
    json.dumps(dict(status=r["status"],verified=r["status"] in
      ("SAT_VERIFIED","GF2_UNSAT_VERIFIED"),e2e_s=r["E2E_s"]),sort_keys=True)))
 for arm in sorted({r["arm"] for r in rows}):
  subset=[r for r in rows if r["arm"]==arm]
  conn.execute("INSERT INTO policy_candidate VALUES(?,?,?,?,?,1)",
   (a.series,a.run_id,arm,
    sum(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") for r in subset),
    sum(r["PAR2_verified_s"] for r in subset)))
 conn.commit()
 counts=dict(series_runs=conn.execute("SELECT count(*) FROM series_run").fetchone()[0],
  unique_sources=conn.execute("SELECT count(*) FROM source").fetchone()[0],
  trials=conn.execute("SELECT count(*) FROM trial").fetchone()[0],
  events=conn.execute("SELECT count(*) FROM decision_event").fetchone()[0])
 assert counts["trials"]==counts["events"]
 print("DRNAS_SQL_LEDGER "+json.dumps(dict(series=a.series,run_id=a.run_id,
  prior_run_id=a.prior_run_id,counts=counts,source_sha256=hashlib.sha256(data).hexdigest(),
  holdout_feedback_applied=False),sort_keys=True),flush=True)
 conn.close()
if __name__=="__main__":main()
