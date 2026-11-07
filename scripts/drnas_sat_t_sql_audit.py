#!/usr/bin/env python3
"""Idempotent SQLite integrity audit for final R2x + recovered R194 + pending T."""
import json
import pathlib
import sqlite3
base=pathlib.Path(__file__).resolve().parents[1]
sql=(base/"research/drnas_sat_benchmark_history_20261107_t.sql").read_text()
conn=sqlite3.connect(":memory:")
conn.row_factory=sqlite3.Row
def check():
    assert conn.execute("PRAGMA foreign_key_check").fetchall()==[]
    q="SELECT version,mode,trials,solved,par2_s FROM benchmark_modes JOIN benchmark_cohorts USING(cohort_id) WHERE cohort_id=? AND mode=?"
    def metric(cohort,mode):
        r=conn.execute(q,(cohort,mode)).fetchone()
        assert r is not None,(cohort,mode)
        return (r["trials"],r["solved"],round(r["par2_s"],6))
    assert metric("ultimate_r2x_20261107","r153")== (40,14,1378.713012)
    assert metric("ultimate_r2x_20261107","r2_clean")== (40,18,1166.599241)
    assert metric("ultimate_r2x_20261107","r2_live")== (40,18,1169.270087)
    assert metric("r194_external_seed_recovered","default")== (24,0,1440)
    assert metric("r194_external_seed_recovered","dual_keep_default")== (24,6,1139.035484)
    assert conn.execute("SELECT COUNT(*) FROM benchmark_mode_telemetry WHERE cohort_id='ultimate_r2x_20261107'").fetchone()[0]==15
    assert conn.execute("SELECT COUNT(*) FROM benchmark_paired_comparisons WHERE cohort_id='ultimate_r2x_20261107'").fetchone()[0]==4
    assert conn.execute("SELECT status FROM build_status WHERE version='Ultimate T Phase1'").fetchone()[0]=="IN_PROGRESS_PREPARE_PASS_5_SHARDS_RUNNING"
    assert conn.execute("SELECT audit_status FROM benchmark_cohorts WHERE cohort_id='r194_external_seed_recovered'").fetchone()[0]=="R194_SEED_REPLAY_AUDIT_PASS"
    return tuple(conn.execute("SELECT COUNT(*) FROM "+tbl).fetchone()[0] for tbl in
                 ("benchmark_cohorts","benchmark_modes","benchmark_mode_telemetry",
                  "benchmark_paired_comparisons","research_findings","build_status"))
conn.executescript(sql)
before=check()
conn.executescript(sql)
assert check()==before,"SQLite upsert replay created duplicate rows"
result={"status":"DRNAS_T_SQL_AUDIT_PASS","R2x_frozen_attempts":200,
        "R194_recovered_attempts":96,"T_state":"not_yet_audited",
        "table_row_counts":before}
print("DRNAS_T_SQL_AUDIT",json.dumps(result,sort_keys=True),flush=True)
