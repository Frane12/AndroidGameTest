#!/usr/bin/env python3
"""Run cumulative historical SAT SQLite audit before writing future TA/TD/TK results."""
import json
import pathlib
import sqlite3
root=pathlib.Path(__file__).resolve().parents[1]
p=root/"research/drnas_sat_benchmark_history_20261107_ta.sql"
sql=p.read_text(encoding="utf8")
db=sqlite3.connect(":memory:")
db.row_factory=sqlite3.Row
def validate():
    assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
    def metric(cohort,mode):
        r=db.execute("SELECT trials,solved,par2_s FROM benchmark_modes WHERE cohort_id=? AND mode=?",
                     (cohort,mode)).fetchone()
        assert r is not None,(cohort,mode)
        return r["trials"],r["solved"],round(r["par2_s"],6)
    expected={
     ("ultimate_t_phase1_20261107","t_clean"):(40,18,1153.728945),
     ("ultimate_t_phase1_20261107","t_source"):(40,18,1152.638359),
     ("ultimate_t_phase1_20261107","t_shadow"):(40,18,1152.536897),
     ("ultimate_t_phase1_20261107","t_derived"):(40,18,1155.94461),
     ("ultimate_r2t_structural_20261107","r2_clean"):(40,18,1168.671126),
     ("ultimate_r2t_structural_20261107","r2_portfolio"):(40,18,1155.276228),
     ("r196_causal_20261107","split256"):(32,8,2257.102753),
     ("r196_causal_20261107","default"):(32,6,2376.768142),
     ("r197_state_isolation_20261107","split256"):(40,8,2980.251829),
     ("r197_state_isolation_20261107","default"):(40,6,3093.928855),
     ("new_horizon_r4f_20261107","r4f_select"):(616,584,128.977387),
     ("neural_r5_20261107","r5_neural"):(80,66,283.370511),
     ("r193short_20261107","default"):(88,88,0.185802),
     ("r193dual_20261106","dual_keep_default"):(204,156,2927.163077),
    }
    for key,target in expected.items():
        assert metric(*key)==target,(key,metric(*key),target)
    s=db.execute("SELECT * FROM benchmark_t_frontier WHERE cohort_id='ultimate_t_phase1_20261107' AND scope='all' AND mode='t_source'").fetchone()
    assert s is not None and s["frontier_updates"]==82277463 and s["completed_reasons"]==0
    s=db.execute("SELECT * FROM benchmark_t_frontier WHERE cohort_id='ultimate_t_phase1_20261107' AND scope='all' AND mode='t_derived'").fetchone()
    assert s is not None and s["candidate_proposals"]==108 and s["completed_reasons"]==40
    ta=db.execute("SELECT status FROM build_status WHERE version='TA new-to-R1/R2/R193 20261107'").fetchone()
    assert ta is not None
    ta_final=ta["status"]=="TA_FINAL_AUDIT_PASS_NOT_GLOBAL_BLIND"
    assert ta_final or ta["status"].startswith("IN_PROGRESS_"),ta["status"]
    if ta_final:
        checked={
          "r153": (60,12,2957.183758),
          "r1a": (60,10,3066.988472),
          "r2_clean": (60,8,3201.353495),
          "r2_portfolio": (60,8,3154.929632),
          "r2_binary": (60,8,3154.981717),
        }
        for mode,expected_ta in checked.items():
            assert metric("ultimate_ta_disjoint_20261107",mode)==expected_ta,(mode,metric("ultimate_ta_disjoint_20261107",mode))
        cohort=db.execute("SELECT original_formulas,total_attempts,audit_status FROM benchmark_cohorts WHERE cohort_id='ultimate_ta_disjoint_20261107'").fetchone()
        assert cohort is not None and tuple(cohort)==(30,300,"TA_30_ORIGINAL_SHA_DISJOINT_AUDIT_PASS_NOT_GLOBAL_BLIND")
        p=db.execute("SELECT paired_wins,paired_losses,paired_ties,total_par2_gain_s FROM benchmark_paired_comparisons WHERE cohort_id=? AND candidate=? AND reference=?",
              ("ultimate_ta_disjoint_20261107","r2_portfolio","r153")).fetchone()
        assert p is not None and tuple(p)==(0,12,48,-197.745874),p
    return [db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
            for t in ("benchmark_cohorts","benchmark_modes","research_findings",
                      "benchmark_mode_telemetry","benchmark_paired_comparisons",
                      "benchmark_t_frontier","build_status")]
db.executescript(sql)
first=validate()
db.executescript(sql)
assert validate()==first,"idempotency failed: duplicate rows after replay"
ta_status=db.execute("SELECT status FROM build_status WHERE version='TA new-to-R1/R2/R193 20261107'").fetchone()[0]
print("DRNAS_TA_SQL_AUDIT_PASS",json.dumps(dict(rows=first,TA=ta_status,
      T="AUDIT_PASS",R2T="AUDIT_PASS"),sort_keys=True),flush=True)
