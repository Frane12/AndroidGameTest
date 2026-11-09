#!/usr/bin/env python3
"""Append X9 & X10 audited E2E evidence to existing V15.3.1 + MRE analytics SQLite.
Historical tables are never deleted/updated. Data remains per-run, never pooled.
Run only on analytics experiment branch, never main/stable V15.3.1.
"""
import argparse, collections, csv, hashlib, json, pathlib, sqlite3, datetime

RUNS=(
  dict(id=42559879920,label='DRNAS_MRE_X9_REPLAY30',audit_job=128976119563,
       expected=300,sources=30,reps=2,modes=5,cap=15.,directory='x9',
       independent_lrat=False,cohort='prepared_replay_not_blind'),
  dict(id=42561615100,label='DRNAS_MRE_X10_STRUCTURAL32',audit_job=128981538691,
       expected=384,sources=32,reps=2,modes=6,cap=15.,directory='x10',
       independent_lrat=False,cohort='prepared_replay_30_plus_two_reserved_hard'),
)
def need(condition,why):
  if not condition:raise RuntimeError('DRNAS_X9_X10_ANALYTICS_FAIL_CLOSED '+why)
def digest(content):return hashlib.sha256(content).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_bytes())
def fmt(v):return round(float(v),6)

def ingest_one(db,root,spec):
  folder=pathlib.Path(root)/spec['directory']
  report_file=folder/'report.json'
  manifest_file=folder/'manifest.json'
  need(report_file.exists() and manifest_file.exists(),
       spec['label']+' missing audited report or source manifest')
  report=load(report_file);manifest=load(manifest_file)
  need(report['trials']==spec['expected'] and report['source_count']==spec['sources'],
       spec['label']+' failed trial/source count')
  need(len(report['rows'])==spec['expected'] and len(manifest['cases'])==spec['sources'],
       spec['label']+' missing rows or manifest cases')
  need(report['protocol']==manifest['protocol'],spec['label']+' mismatched protocol')
  need(report['cap_s']==spec['cap'] and manifest['cap_s']==spec['cap'],
       spec['label']+' mismatched limit')
  need(manifest['expected_trials']==spec['expected'] and
       len(manifest['modes'])==spec['modes'],spec['label']+' missing modes')
  source={c['sha256']:c for c in manifest['cases']}
  need(len(source)==spec['sources'],spec['label']+' source SHA duplicated')
  rs=report['score']['all'] if spec['directory']=='x10' else report['score']
  need(set(rs)==set(manifest['modes']),spec['label']+' audit missing a mode')
  need(not report.get('UNSAT_independent_LRAT',False),
       spec['label']+' unexpected UNSAT certificate claim')
  db.execute("""INSERT INTO mre_x9x10_runs
    (run_id,label,audit_job,url,protocol,source_count,repetitions,arms,cap_s,
     trial_count,source_manifest_sha256,audit_report_sha256,
     cohort,independent_unsat_lrat) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    (spec['id'],spec['label'],spec['audit_job'],
     'https://github.com/Frane12/AndroidGameTest/actions/runs/'+str(spec['id']),
     report['protocol'],spec['sources'],spec['reps'],spec['modes'],spec['cap'],
     spec['expected'],digest(manifest_file.read_bytes()),
     digest(report_file.read_bytes()),spec['cohort'],0))
  seen=set();by_source=collections.defaultdict(set);by_mode=collections.defaultdict(list)
  for row in report['rows']:
    sha=row['sha256'];mode=row['mode'];rep=int(row['rep'])
    need(sha in source, spec['label']+' unknown original source SHA')
    need(row['gbd']==source[sha]['gbd'] and row['protocol']==report['protocol'],
         spec['label']+' source identity mismatch')
    need(mode in rs and 0<=rep<spec['reps'],spec['label']+' invalid arm or rep')
    key=(sha,mode,rep)
    need(key not in seen,spec['label']+' duplicated trial')
    seen.add(key);by_source[sha].add((mode,rep));by_mode[mode].append(row)
    verdict=row['status']
    need(verdict in ('SAT','UNSAT','TIMEOUT'),spec['label']+' unknown verdict')
    sat_checked=bool(row['SAT_original_verified'])
    unsat_agreed=bool(row.get('UNSAT_cross_solver_agreement_no_LRAT',False))
    accepted=bool(row['accepted_solved'])
    need(verdict!='SAT' or sat_checked, spec['label']+' SAT original witness missing')
    need(not accepted or verdict=='SAT' or
         (verdict=='UNSAT' and unsat_agreed),
         spec['label']+' unverified UNSAT counted solved')
    need(accepted==(verdict=='SAT' or
                     (verdict=='UNSAT' and unsat_agreed)),
         spec['label']+' incorrect proof gate')
    raw=fmt(row['PAR2_s']);audited=fmt(row['audited_PAR2_s'])
    need(abs(audited-(raw if accepted else spec['cap']*2))<0.0001,
         spec['label']+' altered audited PAR2')
    need(0<=raw<=2*spec['cap'] and 0<=audited<=2*spec['cap'],
         spec['label']+' bad cap')
    need(verdict!='TIMEOUT' or raw==2*spec['cap'],
         spec['label']+' invalid timeout penalty')
    db.execute("""INSERT INTO mre_x9x10_attempts (
      run_id,original_sha256,gbd,source_cohort,mode,rep,solver_seed,
      seeded_in_solver,verdict,accepted_solved,par2_raw_s,par2_audited_s,
      elapsed_wall_s,preprocessing_s,sat_original_verified,
      unsat_cross_solver_no_lrat,independent_unsat_lrat,
      selected_backend,backend_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (spec['id'],sha,row['gbd'],row.get('cohort',row.get('stratum')),
       mode,rep,int(row['seed']),int(bool(row['independent_seed_applied'])),
       verdict,int(accepted),raw,audited,fmt(row['elapsed_s']),
       fmt(row['preprocessing_s']),int(sat_checked),int(unsat_agreed),0,
       row.get('selected',mode),row['binary_sha256']))
  need(len(seen)==spec['expected'] and len(by_source)==spec['sources'],
       spec['label']+' coverage incomplete')
  required={(mode,rep) for mode in rs for rep in range(spec['reps'])}
  need(all(v==required for v in by_source.values()),
       spec['label']+' source/seed arms not paired')
  baseline=float(rs['original']['PAR2_s'])
  for mode,cohort in by_mode.items():
    expected=rs[mode]
    audited=round(sum(float(r['audited_PAR2_s']) for r in cohort),6)
    solved=sum(bool(r['accepted_solved']) for r in cohort)
    timeouts=sum(r['status']=='TIMEOUT' for r in cohort)
    need(len(cohort)==spec['sources']*spec['reps']
         and abs(audited-expected['PAR2_s'])<0.001
         and solved==expected['solved']
         and timeouts==expected['timeouts'],
         spec['label']+' mode '+mode+' != audit final')
    db.execute("""INSERT INTO mre_x9x10_scores
      (run_id,mode,trials,solved,timeouts,par2_s,speedup_vs_original,
       percent_less_par2_vs_original) VALUES (?,?,?,?,?,?,?,?)""",
      (spec['id'],mode,len(cohort),solved,timeouts,audited,
       round(baseline/audited,6),round(100*(1-audited/baseline),5)))
  return dict(run=spec['id'],protocol=report['protocol'],sources=len(by_source),
      trials=len(seen),scores={
        mode:dict(solved=int(row['solved']),PAR2_s=row['PAR2_s'],
        speedup_vs_original=round(baseline/row['PAR2_s'],6),
        percent_less_par2_vs_original=round(
          (1-row['PAR2_s']/baseline)*100,4))
        for mode,row in rs.items()},
      report_sha256=digest(report_file.read_bytes()),
      manifest_sha256=digest(manifest_file.read_bytes()),
      verification='audited source SHA matched, original SAT witnesses, cross-solver UNSAT, paired seed and PAR2')

def main():
  p=argparse.ArgumentParser()
  p.add_argument('--db',default='research/sat-analytics-data/current/sat_analytics.sqlite')
  p.add_argument('--input',default='x_evidence')
  p.add_argument('--out',default='research/sat-analytics-data/current/x9_x10_ingest_audit_20261109.json')
  args=p.parse_args()
  path=pathlib.Path(args.db)
  need(path.exists() and path.stat().st_size>80_000_000,
       'missing original historical SQLite')
  prior_sha=digest(path.read_bytes())
  db=sqlite3.connect(path)
  try:
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA foreign_keys=ON")
    archived={'datasets','formulas','attempts','telemetry'}
    existing={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    need(archived.issubset(existing),'historical V15.3.1 tables missing')
    old={name:db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]
         for name in archived}
    db.executescript("""
      CREATE TABLE IF NOT EXISTS mre_x9x10_runs (
        run_id INTEGER PRIMARY KEY,label TEXT NOT NULL,audit_job INTEGER NOT NULL,
        url TEXT NOT NULL,protocol TEXT NOT NULL,source_count INTEGER NOT NULL,
        repetitions INTEGER NOT NULL,arms INTEGER NOT NULL,cap_s REAL NOT NULL,
        trial_count INTEGER NOT NULL,source_manifest_sha256 TEXT NOT NULL,
        audit_report_sha256 TEXT NOT NULL,cohort TEXT NOT NULL,
        independent_unsat_lrat INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS mre_x9x10_attempts (
        run_id INTEGER NOT NULL,original_sha256 TEXT NOT NULL,gbd TEXT NOT NULL,
        source_cohort TEXT,mode TEXT NOT NULL,rep INTEGER NOT NULL,
        solver_seed INTEGER NOT NULL,seeded_in_solver INTEGER NOT NULL,
        verdict TEXT NOT NULL,accepted_solved INTEGER NOT NULL,
        par2_raw_s REAL NOT NULL,par2_audited_s REAL NOT NULL,
        elapsed_wall_s REAL NOT NULL,preprocessing_s REAL NOT NULL,
        sat_original_verified INTEGER NOT NULL,
        unsat_cross_solver_no_lrat INTEGER NOT NULL,
        independent_unsat_lrat INTEGER NOT NULL,selected_backend TEXT NOT NULL,
        backend_sha256 TEXT NOT NULL,
        PRIMARY KEY(run_id,original_sha256,mode,rep),
        FOREIGN KEY(run_id) REFERENCES mre_x9x10_runs(run_id)
      );
      CREATE TABLE IF NOT EXISTS mre_x9x10_scores (
        run_id INTEGER NOT NULL,mode TEXT NOT NULL,trials INTEGER NOT NULL,
        solved INTEGER NOT NULL,timeouts INTEGER NOT NULL,
        par2_s REAL NOT NULL,speedup_vs_original REAL NOT NULL,
        percent_less_par2_vs_original REAL NOT NULL,
        PRIMARY KEY(run_id,mode),
        FOREIGN KEY(run_id) REFERENCES mre_x9x10_runs(run_id)
      );
      CREATE INDEX IF NOT EXISTS idx_mre_x9x10_sha
        ON mre_x9x10_attempts(original_sha256,run_id,mode);
    """)
    need(db.execute("SELECT COUNT(*) FROM mre_x9x10_runs").fetchone()[0]==0,
         'runs already present; do not overwrite historical ingestion')
    db.execute("BEGIN IMMEDIATE")
    result=[ingest_one(db,args.input,spec) for spec in RUNS]
    need(db.execute("SELECT COUNT(*) FROM mre_x9x10_attempts").fetchone()[0]==684,
         'not 684 real end-to-end attempts')
    need(db.execute("SELECT COUNT(*) FROM mre_x9x10_scores").fetchone()[0]==11,
         'not 11 separate score arms')
    after={name:db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0]
           for name in archived}
    need(old==after,'historical V15.3.1 rows changed')
    need(db.execute("PRAGMA foreign_key_check").fetchall()==[],
         'foreign key violation')
    db.commit()
  except:
    db.rollback()
    raise
  finally:db.close()
  out=dict(schema_version='DRNAS-X9-X10-SQLITE-ADDONLY-20261109-v1',
      as_of_utc='2026-11-09',prior_db_sha256=prior_sha,
      new_db_sha256=digest(path.read_bytes()),
      prior_historical_table_row_counts=old,
      historical_tables_unchanged=True,
      new_runs=2,new_attempts=684,new_score_arms=11,
      explicit_no_cross_dataset_PAR2_pooling=True,
      UNSAT_independent_LRAT=False,not_globally_blind=True,
      runs=result)
  destination=pathlib.Path(args.out);destination.parent.mkdir(parents=True,exist_ok=True)
  destination.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
  print('DRNAS_X9_X10_ANALYTICS_FINAL',json.dumps({
      'new_runs':2,'new_attempts':684,'score_arms':11,'preserved':True,
      'new_db_sha256':out['new_db_sha256']},sort_keys=True),flush=True)
if __name__=='__main__':main()
