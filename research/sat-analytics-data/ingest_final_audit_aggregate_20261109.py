#!/usr/bin/env python3
"""Append-only audited benchmark cohort SUMMARY ingestion into historical DRNAS SQLite.

The pre-existing attempts/datasets/formulas/telemetry and X9/X10 attempt tables
are read-only. New run/arm/tier summary tables are explicitly separate.
No invented individual trial rows. No pooling PAR2 across different benchmark caps.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import sqlite3

REG=pathlib.Path("research/sat-analytics-data/frozen_final_registry_20261109_x11_x17.json")
DB=pathlib.Path("research/sat-analytics-data/current/sat_analytics.sqlite")
AUDIT=pathlib.Path("research/sat-analytics-data/current/refresh_x11_x17_20261109_audit.json")
EXPECTED_SHA="3b4b6cfd04cb0acc51430b82dc37ad5dfa0dd871dc1a44708e356b15dd7f1724"
EXPECTED_RUNS=16
EXPECTED_ATTEMPT_COUNTS=4856

def check(ok, msg):
    if not ok: raise RuntimeError("DRNAS_ANALYTICS_REFRESH_FAIL_CLOSED "+str(msg))

def digest(b): return hashlib.sha256(b).hexdigest()

def pick(data, *keys):
    for k in keys:
        v=data.get(k)
        if v is not None: return v
    return None

def numbers(data):
    return {
      "par2_s":pick(data,"PAR2_s","conservative_PAR2_s","wall_PAR2_s"),
      "raw_par2_s":pick(data,"raw_PAR2_s"),
      "n":pick(data,"n","trials"),
      "solved":pick(data,"solved"),
      "timeouts":pick(data,"timeouts","raw_timeouts"),
      "sat_verified":pick(data,"SAT_original_verified","SAT_verified","SAT"),
      "unsat_reference":pick(data,"UNSAT_reference_agreed","UNSAT_crosschecked",
                              "UNSAT_reference_only","UNSAT_unproven"),
      "child_cpu_s":pick(data,"child_cpu_s")
    }

def overall(final):
    if isinstance(final.get("main_score"), dict): return final["main_score"]
    s=final.get("score")
    if isinstance(s,dict):
        if isinstance(s.get("all"),dict): return s["all"]
        return s
    for name in ("scores","overall"):
        if isinstance(final.get(name),dict): return final[name]
    check(False,"no overall scores")

def tiers(final):
    groups=[]
    s=final.get("score",{})
    if isinstance(s,dict) and isinstance(s.get("all"),dict):
        groups.extend((k,v) for k,v in s.items() if k!="all" and isinstance(v,dict))
    for name in ("by_tier","by_original_X15_tier","by_cohort"):
        b=final.get(name,{})
        if isinstance(b,dict): groups.extend((k,v) for k,v in b.items() if isinstance(v,dict))
    for name in ("easy","hard"):
        if isinstance(final.get(name),dict): groups.append((name,final[name]))
    return groups

def run():
    check(REG.is_file() and DB.is_file(),"registry or frozen database missing")
    original_db_sha=digest(DB.read_bytes())
    check(original_db_sha==EXPECTED_SHA,"frozen X9X10 SQLite SHA drift; rebase before append")
    registry=json.loads(REG.read_text())
    check(registry.get("schema")=="DRNAS-AUDITED-POST-X9X10-FINAL-REGISTRY-20261109-v1","wrong registry")
    runs=registry.get("runs",[])
    check(len(runs)==EXPECTED_RUNS and
          sum(r["final"].get("trials",r["final"].get("n_trials",
              r["final"].get("E2E_trials",0))) for r in runs)==EXPECTED_ATTEMPT_COUNTS,
          "run or total benchmark attempt-count mismatch")
    check(len({r["run_id"] for r in runs})==EXPECTED_RUNS,"duplicate run identity")
    db=sqlite3.connect(DB)
    historical=("datasets","formulas","attempts","telemetry",
                 "mre_x9x10_runs","mre_x9x10_attempts","mre_x9x10_scores")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        check(set(historical).issubset(tables),"required V15/X9X10 historical tables absent")
        before={t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in historical}
        check(before["mre_x9x10_runs"]==2 and
              before["mre_x9x10_attempts"]==684 and
              before["mre_x9x10_scores"]==11,"frozen X9/X10 audit rows drift")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS research_final_runs_20261109(
          run_id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE,
          final_job_id INTEGER NOT NULL, protocol TEXT NOT NULL,
          cohort_classification TEXT NOT NULL, run_url TEXT NOT NULL,
          trials_declared INTEGER NOT NULL, score_arms INTEGER NOT NULL,
          source_count INTEGER, cap_s REAL, independent_unsat_lrat INTEGER NOT NULL
            CHECK(independent_unsat_lrat IN (0,1)),
          global_blind_claim INTEGER NOT NULL CHECK(global_blind_claim=0),
          granularity TEXT NOT NULL CHECK(granularity='audited_final_aggregate_not_trial'),
          source_json_sha256 TEXT NOT NULL, full_final_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS research_final_scores_20261109(
          run_id INTEGER NOT NULL, arm TEXT NOT NULL,
          n INTEGER NOT NULL, par2_s REAL NOT NULL CHECK(par2_s>=0),
          raw_par2_s REAL, solved INTEGER, timeouts INTEGER,
          sat_verified INTEGER, unsat_reference INTEGER, child_cpu_s REAL,
          speedup_vs_kissat REAL, speedup_vs_cadical REAL,
          original_score_json TEXT NOT NULL,
          PRIMARY KEY(run_id,arm),
          FOREIGN KEY(run_id) REFERENCES research_final_runs_20261109(run_id)
        );
        CREATE TABLE IF NOT EXISTS research_final_tiers_20261109(
          run_id INTEGER NOT NULL, tier TEXT NOT NULL, arm TEXT NOT NULL,
          n INTEGER, par2_s REAL NOT NULL CHECK(par2_s>=0),
          raw_par2_s REAL, solved INTEGER, timeouts INTEGER,
          sat_verified INTEGER, unsat_reference INTEGER,
          original_score_json TEXT NOT NULL,
          PRIMARY KEY(run_id,tier,arm),
          FOREIGN KEY(run_id) REFERENCES research_final_runs_20261109(run_id)
        );
        """)
        check(db.execute("SELECT COUNT(*) FROM research_final_runs_20261109").fetchone()[0]==0,
              "existing refresh rows; do not overwrite or duplicate")
        check(db.execute("SELECT COUNT(*) FROM research_final_scores_20261109").fetchone()[0]==0,
              "existing scores")
        check(db.execute("SELECT COUNT(*) FROM research_final_tiers_20261109").fetchone()[0]==0,
              "existing tier scores")
        db.execute("BEGIN IMMEDIATE")
        records=0
        tier_records=0
        for entry in runs:
            rid=entry["run_id"]
            f=entry["final"]
            scores=overall(f)
            trial_count=pick(f,"trials","n_trials","E2E_trials")
            check(f.get("protocol") and isinstance(scores,dict) and scores,
                  entry["label"]+" invalid final audit")
            check(f.get("UNSAT_independent_LRAT") is False or
                  f.get("independent_unsat_LRAT") is False,
                  entry["label"]+" unexpected independent LRAT certificate")
            check(f.get("no_auto_promotion") is True,entry["label"]+" auto-promoted candidate")
            score_counts=[]
            for arm,row in scores.items():
                if not isinstance(row,dict): check(False,entry["label"]+" malformed arm")
                v=numbers(row)
                check(v["par2_s"] is not None and v["n"] is not None,
                      entry["label"]+" missing numeric score for "+arm)
                check(v["n"]>0 and float(v["par2_s"])>=0,
                      entry["label"]+" invalid row")
                score_counts.append(int(v["n"]))
            check(sum(score_counts)==trial_count,
                  entry["label"]+" audit score rows do not sum to declared E2E trials")
            raw=json.dumps(f,sort_keys=True,separators=(",",":"))
            source_hash=digest(raw.encode())
            db.execute("""INSERT INTO research_final_runs_20261109(
              run_id,label,final_job_id,protocol,cohort_classification,run_url,
              trials_declared,score_arms,source_count,cap_s,independent_unsat_lrat,
              global_blind_claim,granularity,source_json_sha256,full_final_json
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (rid,entry["label"],entry["final_job_id"],f["protocol"],
               entry["cohort_classification"],entry["run_url"],
               trial_count,len(scores),pick(f,"source_count","sources","case_count"),
               f.get("cap_s"),0,0,"audited_final_aggregate_not_trial",source_hash,raw))
            reference_k=next((numbers(scores[n])["par2_s"] for n in
                ("kissat","kissat1","kissat_404","kissat_4_0_4") if n in scores),None)
            reference_c=next((numbers(scores[n])["par2_s"] for n in
                ("cadical","cadical1","cadical_173") if n in scores),None)
            for arm,row in scores.items():
                v=numbers(row)
                def ratio(ref):
                    return round(float(ref)/float(v["par2_s"]),6) if ref is not None and float(v["par2_s"])>0 else None
                db.execute("""INSERT INTO research_final_scores_20261109(
                  run_id,arm,n,par2_s,raw_par2_s,solved,timeouts,sat_verified,
                  unsat_reference,child_cpu_s,speedup_vs_kissat,speedup_vs_cadical,
                  original_score_json
                  ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (rid,arm,v["n"],v["par2_s"],v["raw_par2_s"],v["solved"],
                   v["timeouts"],v["sat_verified"],v["unsat_reference"],v["child_cpu_s"],
                   ratio(reference_k),ratio(reference_c),
                   json.dumps(row,sort_keys=True,separators=(",",":"))))
                records+=1
            for tier,ts in tiers(f):
                for arm,row in ts.items():
                    if not isinstance(row,dict): continue
                    v=numbers(row)
                    if v["par2_s"] is None: continue
                    db.execute("""INSERT INTO research_final_tiers_20261109(
                      run_id,tier,arm,n,par2_s,raw_par2_s,solved,timeouts,
                      sat_verified,unsat_reference,original_score_json)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                      (rid,tier,arm,v["n"],v["par2_s"],v["raw_par2_s"],
                       v["solved"],v["timeouts"],v["sat_verified"],v["unsat_reference"],
                       json.dumps(row,sort_keys=True,separators=(",",":"))))
                    tier_records+=1
        after={t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0] for t in historical}
        check(after==before,"historical table row count changed")
        check(db.execute("PRAGMA foreign_key_check").fetchall()==[],"foreign key violations")
        check(db.execute("SELECT COUNT(*) FROM research_final_runs_20261109").fetchone()[0]==EXPECTED_RUNS,
              "wrong new run count")
        check(db.execute("SELECT COUNT(*) FROM research_final_scores_20261109").fetchone()[0]==records,
              "score count mismatch")
        check(db.execute("SELECT COUNT(*) FROM research_final_tiers_20261109").fetchone()[0]==tier_records,
              "tier score count mismatch")
        db.commit()
        check(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity check failed")
    except:
        db.rollback()
        raise
    finally:
        db.close()
    result=dict(schema_version="DRNAS-RESEARCH-FINAL-AGGREGATE-REFRESH-20261109-v1",
      source_registry=str(REG),source_registry_sha256=digest(REG.read_bytes()),
      parent_sqlite_sha256=original_db_sha,updated_sqlite_sha256=digest(DB.read_bytes()),
      historical_counts_unchanged=True,historical_counts=before,
      new_audited_runs=EXPECTED_RUNS,covered_source_E2E_trials=EXPECTED_ATTEMPT_COUNTS,
      new_audited_arm_summary_rows=records,new_tier_rows=tier_records,
      individual_attempt_rows_added=0,global_blind_holdout_claim=False,
      independent_unsat_lrat=False,no_cross_dataset_PAR2_pooling=True,
      branch_isolation="experiment/drnas-analytics-refresh-x11-x17-20261109")
    AUDIT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DRNAS_REFRESH_SQL_FINAL",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    run()
