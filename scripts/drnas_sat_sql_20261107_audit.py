#!/usr/bin/env python3
"""Audit cumulative DRNAS SAT SQLite migration; never infer missing CI results."""
import json
import pathlib
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "research" / "drnas_sat_benchmark_history_20261107.sql"
EXPECTED = {
    "ultimate_r1_20261107": (45, 630, 90, 7),
    "ultimate_r2_20261107": (20, 200, 40, 5),
    "ultimate_r2_prebudget_20261107": (20, 200, 40, 5),
    "ultimate_r2_prepbudget_rerun_20261107": (20, 200, 40, 5),
    "ultimate_r2x_20261107": (20, 200, 40, 5),
    "new_horizon_r4f_20261107": (None, 2464, 616, 4),
    "neural_r5_20261107": (None, 400, 80, 5),
}

def validate(conn):
    conn.row_factory = sqlite3.Row
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    for cohort_id, (originals, attempts, n, arms) in EXPECTED.items():
        c = conn.execute(
            "SELECT * FROM benchmark_cohorts WHERE cohort_id=?", (cohort_id,)
        ).fetchone()
        assert c is not None, cohort_id
        assert c["original_formulas"] == originals and c["total_attempts"] == attempts
        assert any(word in c["audit_status"] for word in ("PASS", "COMPLETE")), cohort_id
        ms = conn.execute(
            "SELECT * FROM benchmark_modes WHERE cohort_id=?", (cohort_id,)
        ).fetchall()
        assert len(ms) == arms, (cohort_id, len(ms))
        assert sum(r["trials"] for r in ms) == attempts, cohort_id
        assert all(r["trials"] == n and r["solved"] <= n and r["par2_s"] >= 0 for r in ms)
    def metric(cohort, mode):
        v = conn.execute(
            "SELECT solved,par2_s FROM benchmark_modes WHERE cohort_id=? AND mode=?",
            (cohort, mode),
        ).fetchone()
        assert v is not None, (cohort, mode)
        return v["solved"], round(v["par2_s"], 6)
    assert metric("ultimate_r1_20261107", "ultimate_r1") == (30, 3621.5175)
    assert metric("ultimate_r2_20261107", "r2_clean") == (18, 1170.72195)
    assert metric("ultimate_r2_20261107", "r2_live") == (18, 1176.449248)
    assert metric("ultimate_r2_prebudget_20261107", "r2_clean") == (16, 1235.379087)
    assert metric("ultimate_r2_prebudget_20261107", "r2_live") == (16, 1237.634491)
    assert metric("ultimate_r2_prepbudget_rerun_20261107", "r2_clean") == (18, 1170.545666)
    assert metric("ultimate_r2_prepbudget_rerun_20261107", "r2_live") == (18, 1173.075083)
    assert metric("ultimate_r2x_20261107", "r2_clean") == (18, 1166.599241)
    assert metric("ultimate_r2x_20261107", "r2_live") == (18, 1169.270087)
    assert metric("new_horizon_r4f_20261107", "r4f_select") == (584, 128.977387)
    assert metric("new_horizon_r4f_20261107", "r4e_mid") == (584, 128.874675)
    assert metric("neural_r5_20261107", "r5_neural") == (66, 283.370511)
    assert metric("neural_r5_20261107", "clean") == (66, 283.3763)
    assert conn.execute("SELECT COUNT(*) FROM research_findings").fetchone()[0] >= 15
    assert conn.execute(
        "SELECT status FROM build_status WHERE version='Ultimate R2x'"
    ).fetchone()[0] == "ULTIMATE_R2X_AUDIT_PASS_200_PAIRED_NOT_GLOBAL_BLIND"
    assert conn.execute(
        "SELECT COUNT(*) FROM benchmark_mode_telemetry WHERE cohort_id='ultimate_r2_20261107'"
    ).fetchone()[0] == 15
    return {
        "status": "DRNAS_SQL_AUDIT_PASS",
        "sql_file": str(SRC.relative_to(ROOT)),
        "audited_cohorts": list(EXPECTED),
        "formula_cohorts": len(EXPECTED),
        "totals": {key: {"formulas": value[0], "trials": value[1]}
                   for key, value in EXPECTED.items()},
        "findings": conn.execute("SELECT COUNT(*) FROM research_findings").fetchone()[0],
        "r2x_status": conn.execute(
            "SELECT status FROM build_status WHERE version='Ultimate R2x'"
        ).fetchone()[0],
    }

def main():
    sql = SRC.read_text(encoding="utf-8")
    db = sqlite3.connect(":memory:")
    db.executescript(sql)
    result = validate(db)
    # Upserts must keep the history stable when the migration is replayed.
    before = tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                   for table in ("benchmark_cohorts", "benchmark_modes",
                                 "benchmark_mode_telemetry", "research_findings"))
    db.executescript(sql)
    assert validate(db) == result
    after = tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                  for table in ("benchmark_cohorts", "benchmark_modes",
                                "benchmark_mode_telemetry", "research_findings"))
    assert before == after, (before, after)
    out = ROOT / "research" / "drnas_sat_sql_audit_20261107.json"
    out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print("DRNAS_SQL_AUDIT", json.dumps(result, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
