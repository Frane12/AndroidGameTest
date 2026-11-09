#!/usr/bin/env python3
"""Append two COMPLETED audited research results (X18, X16A) to existing SQLite.

This is aggregate ingestion ONLY, not a new SAT solve and not new individual
attempts. Previous rows are immutable. PAR2 values are comparable ONLY within
the same source cohort, CPU budget, and timeout protocol.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3

BASE = pathlib.Path("research/sat-analytics-data/current")
DB = BASE / "sat_analytics.sqlite"
AUDIT = BASE / "refresh_x18_x16a_20261109_audit.json"
X18 = pathlib.Path("source-audits/x18/mre_x18/report.json")
X16A = pathlib.Path("source-audits/x16a/mre_x16a/report.json")
EXPECTED_PARENT_SHA = "c20c8c555a14d226e0bd98f3eb0fd8ab0ef0c4a1e840057471952e86e42d01bb"
RUNS = (
    dict(id=42579485596, job=129037427924, file=X18, name="X18_SELECTIVE",
         kind="x18", arms=7, trials=336, n=48, sources=24),
    dict(id=42579406905, job=129041037428, file=X16A, name="X16A_ASYMMETRIC",
         kind="x16a", arms=16, trials=512, n=32, sources=16),
)
HISTORICAL = ("datasets", "formulas", "attempts", "telemetry",
              "mre_x9x10_runs", "mre_x9x10_attempts", "mre_x9x10_scores")
RUN_TABLE = "research_final_runs_20261109"
SCORE_TABLE = "research_final_scores_20261109"
TIER_TABLE = "research_final_tiers_20261109"

def need(ok, reason):
    if not ok:
        raise RuntimeError("DRNAS_X18_X16A_SQL_FAIL_CLOSED " + str(reason))

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pick(row, *keys):
    for k in keys:
        v = row.get(k)
        if v is not None:
            return v
    return None

def metrics(row):
    return dict(n=row.get("n"),
        par2_s=pick(row,"PAR2_s","wall_PAR2_s"),
        raw_par2_s=pick(row,"raw_PAR2_s"),
        solved=row.get("solved"),
        timeouts=pick(row,"timeouts","timed_out"),
        sat_verified=pick(row,"SAT_original_verified","SAT_original_witness_verified"),
        unsat_reference=pick(row,"UNSAT_reference_agreed",
                             "UNSAT_crosschecked_no_LRAT"),
        child_cpu_s=pick(row,"child_cpu_s"))

def shapes(report, entry):
    if entry["kind"] == "x18":
        need(report.get("UNSAT_independent_LRAT") is False, "X18 proof flag drift")
        need(report.get("sources") == 24 and report.get("trials") == 336,
             "X18 count mismatch")
        need(report.get("native_bounded_probes_not_PAR2") is True,
             "X18 bounded probes mixed into scoring")
        scores = report["overall"]
        need(len(scores) == 7, "X18 unexpected strategy count")
        tiers = report["by_cohort"]
        need(set(tiers) == {
            "x15_previous_development_reused",
            "x15_previous_holdout_reused",
            "x18_sourceonly_official_not_global_blind",
        }, "X18 source cohort has changed")
    else:
        need(report.get("trials") == 512 and report.get("source_count") == 16,
             "X16A count mismatch")
        need(report.get("not_blind_X16_replay") is True,
             "X16A reused sources not flagged")
        ratios = report["results"]
        need(set(ratios) == {"70","80","90","95"}, "ratio grid changed")
        scores={}
        tiers={}
        for ratio, layers in ratios.items():
            need(set(layers) == {"all","development","prior_X15_holdout_replay"},
                 "X16A cohort drift")
            need(set(layers["all"]) == {"native","kissat","balanced50","asym"},
                 "X16A arm drift")
            for arm, row in layers["all"].items():
                scores[ratio+"/"+arm] = row
            for cohort, arms in layers.items():
                if cohort != "all":
                    tiers[ratio+"/"+cohort] = arms
        need(len(scores) == 16, "X16A score count incorrect")
    need(report.get("no_auto_promotion") is True, "candidate auto-promotion prohibited")
    need(all(isinstance(row,dict) and metrics(row)["n"] == entry["n"]
             for row in scores.values()), "unpaired strategy trials")
    need(sum(metrics(x)["n"] for x in scores.values()) == entry["trials"],
         "not all E2E trials accounted for")
    for arm,row in scores.items():
        m=metrics(row)
        need(m["par2_s"] is not None and float(m["par2_s"]) >= 0,
             arm+" invalid PAR2")
        need(m["timeouts"] is not None and m["solved"] is not None,
             arm+" missing solved/timeout")
    return scores, tiers

def main():
    need(DB.is_file(), "base SQLite missing")
    actual_base_sha = sha(DB.read_bytes())
    need(actual_base_sha == EXPECTED_PARENT_SHA,
         "base database SHA changed; rebuild from latest verified aggregate")
    sources=[]
    for entry in RUNS:
        p = entry["file"]
        need(p.is_file(), "missing full final audit "+str(p))
        raw = p.read_bytes()
        report = json.loads(raw)
        need(str(report.get("protocol","")).startswith(
            "DRNAS-X18-" if entry["kind"]=="x18" else "DRNAS-X16A-"),
            "source protocol mismatch")
        score, tiers=shapes(report,entry)
        sources.append((entry,report,score,tiers,sha(raw)))
    conn=sqlite3.connect(DB)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        existing_tables={r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        need(set(HISTORICAL+(RUN_TABLE,SCORE_TABLE,TIER_TABLE)) <= existing_tables,
             "baseline historical or summary table missing")
        before={t:conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                for t in HISTORICAL}
        base_counts=[conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                     for t in (RUN_TABLE,SCORE_TABLE,TIER_TABLE)]
        need(base_counts == [16,113,88],
             "expected 16 frozen audits, 113 arms, 88 cohort rows")
        need({r[0] for r in conn.execute(f"SELECT run_id FROM {RUN_TABLE}")}
             .isdisjoint({e["id"] for e in RUNS}),
             "benchmark already recorded; cannot duplicate")
        conn.execute("BEGIN IMMEDIATE")
        arms_count=tiers_count=0
        for entry, report, scores, tiers, file_sha in sources:
            rid=entry["id"]
            canonical=json.dumps(report,sort_keys=True,separators=(",",":"))
            conn.execute(f"""INSERT INTO {RUN_TABLE}
              (run_id,label,final_job_id,protocol,cohort_classification,run_url,
              trials_declared,score_arms,source_count,cap_s,independent_unsat_lrat,
              global_blind_claim,granularity,source_json_sha256,full_final_json)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (rid,entry["name"],entry["job"],report["protocol"],
               ("X18 source-only and reused X15/X6; not global blind"
                if entry["kind"]=="x18" else
                "X16A exact X16 SHA replay; not fresh holdout"),
               f"https://github.com/Frane12/AndroidGameTest/actions/runs/{rid}",
               entry["trials"],len(scores),entry["sources"],12.0,0,0,
               "audited_final_aggregate_not_trial",
               sha(canonical.encode()),canonical))
            refs=("kissat1",) if entry["kind"]=="x18" else tuple(
                str(q)+"/kissat" for q in (70,80,90,95))
            for arm,row in scores.items():
                m=metrics(row)
                if entry["kind"]=="x18":
                    ref=scores.get("kissat1")
                    cad=scores.get("cadical1")
                else:
                    ratio=arm.split("/")[0]
                    ref=scores.get(ratio+"/kissat")
                    cad=None
                r_par=float(metrics(ref)["par2_s"]) if ref else None
                c_par=float(metrics(cad)["par2_s"]) if cad else None
                t_par=float(m["par2_s"])
                conn.execute(f"""INSERT INTO {SCORE_TABLE}
                  (run_id,arm,n,par2_s,raw_par2_s,solved,timeouts,sat_verified,
                  unsat_reference,child_cpu_s,speedup_vs_kissat,speedup_vs_cadical,
                  original_score_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (rid,arm,m["n"],t_par,m["raw_par2_s"],m["solved"],
                   m["timeouts"],m["sat_verified"],m["unsat_reference"],
                   m["child_cpu_s"],
                   round(r_par/t_par,6) if r_par and t_par>0 else None,
                   round(c_par/t_par,6) if c_par and t_par>0 else None,
                   json.dumps(row,sort_keys=True,separators=(",",":"))))
                arms_count+=1
            for cohort, cohort_scores in tiers.items():
                for arm,row in cohort_scores.items():
                    m=metrics(row)
                    need(m["par2_s"] is not None and m["n"] is not None,
                         "invalid cohort "+cohort+" "+arm)
                    conn.execute(f"""INSERT INTO {TIER_TABLE}
                      (run_id,tier,arm,n,par2_s,raw_par2_s,solved,timeouts,
                      sat_verified,unsat_reference,original_score_json)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (rid,cohort,arm,m["n"],m["par2_s"],m["raw_par2_s"],
                       m["solved"],m["timeouts"],m["sat_verified"],
                       m["unsat_reference"],
                       json.dumps(row,sort_keys=True,separators=(",",":"))))
                    tiers_count+=1
        after={t:conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
               for t in HISTORICAL}
        need(before==after, "historic tables mutated")
        need(arms_count==23 and tiers_count==69, "unexpected inserted score rows")
        need([conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
             for t in (RUN_TABLE,SCORE_TABLE,TIER_TABLE)] == [18,136,157],
             "postappend counts wrong")
        need(conn.execute("PRAGMA foreign_key_check").fetchall()==[],
             "foreign key violations")
        conn.commit()
        need(conn.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
             "SQLite integrity check failed")
    except:
        conn.rollback()
        raise
    finally:
        conn.close()
    result=dict(schema="DRNAS-INCREMENTAL-AUDITED-X18-X16A-20261109-v1",
       base_sha256=actual_base_sha, new_sha256=sha(DB.read_bytes()),
       runs_added=2, run_ids=[x["id"] for x in RUNS], E2E_trials_covered=848,
       individual_attempt_rows_added=0, new_arm_rows=arms_count,
       new_cohort_rows=tiers_count, final_runs=18, final_arm_rows=136,
       final_cohort_rows=157, historical_counts_unchanged=True,
       historical_counts=before, sources_sha256={
           entry["name"]:file_sha for entry,_,_,_,file_sha in sources},
       no_global_blind_claim=True, no_independent_UNSAT_LRAT=True,
       source_original_verified=True, no_cross_dataset_PAR2_pooling=True)
    AUDIT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("DRNAS_X18_X16A_SQL_FINAL",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
