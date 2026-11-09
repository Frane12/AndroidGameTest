#!/usr/bin/env python3
"""Append X22 exact DP and X23 source-certified GF2 experiments to historical SQLite.

This is append-only on the verified X19-X21 database. X22 and X23 are
DEVELOPMENT replays of the same six known X21 sources. Their E2E wall PAR2
and original-SHA accepted trials are not a prospective holdout.
GF2 source contradictions are independently replayed, NOT LRAT proofs.
"""
import hashlib,json,pathlib,sqlite3

BASE=pathlib.Path("research/sat-analytics-data/current")
DB=BASE/"sat_analytics.sqlite"
AUDIT=BASE/"refresh_x22_x23_20261109_audit.json"
EXPECTED_SHA="aef24c8a5bce652d6286f2af75478c5005e58ffa26621ba2d8285c1cd8be0429"
RUNS=[
    ("X22",42593932547,129083904329,60,5,6,18.0),
    ("X23",42594952189,129086388495,48,4,6,18.0),
]
OLD=("datasets","formulas","attempts","telemetry",
 "mre_x9x10_runs","mre_x9x10_attempts","mre_x9x10_scores",
 "research_x19_x21_attempts_20261109","research_x19_x21_formulas_20261109")
RUN_TABLE="research_final_runs_20261109"
SCORE_TABLE="research_final_scores_20261109"
AT_TABLE="research_x22_x23_attempts_20261109"
FORMULA_TABLE="research_x22_x23_formulas_20261109"

def need(cond,why):
    if not cond:raise RuntimeError("X22_X23_SQL_FAIL_CLOSED "+str(why))

def sha(raw):return hashlib.sha256(raw).hexdigest()

def load(tag):
    files=list((pathlib.Path("source-audits")/tag.lower()).rglob("report.json"))
    need(len(files)==1,tag+" expected exactly one final report")
    raw=files[0].read_bytes()
    return json.loads(raw),sha(raw)

def attempt_rows(report,tag):
    rows=[]
    for f in report["per_source"]:
        x=f.get("rows",f.get("trials"))
        need(isinstance(x,list),tag+" no per-source audited attempts")
        need(all(r["original_sha256"]==f["sha256"] for r in x),
             tag+" wrong source row mapping")
        rows+=x
    return rows

def score(row):
    return dict(n=row["n"],solved=row["solved"],
      par2=row["PAR2_s"],sat=row.get("SAT_verified"),
      unsat=row.get("UNSAT_agreement_no_LRAT",row.get("UNSAT_source_certified")),
      cpu=row.get("child_cpu_s"),
      raw=row.get("raw_PAR2_s"))

def main():
    need(DB.exists() and sha(DB.read_bytes())==EXPECTED_SHA,
         "parent audited SQLite not exact expected SHA")
    prepared=[]
    for tag,rid,jid,trials,arms,sources,cap in RUNS:
        report,raw_sha=load(tag)
        need(report["protocol"].startswith("DRNAS-"+tag+"-"),
             tag+" protocol mismatch")
        need(report["trials"]==trials and
            report.get("source_count",report.get("sources"))==sources,
             tag+" expected source and attempt count")
        need(report.get("independent_UNSAT_LRAT") is False and
             report.get("no_auto_promotion") is True and
             report.get("no_global_blind_claim") is True,
             tag+" invalid proof/blindness metadata")
        if tag=="X23":
            need(report.get("development_on_known_X21_sources") is True,
                 "X23 known source label missing")
            need("independently_replayed_source_GF2" in report.get("evidence_type",""),
                 "X23 source algebra evidence metadata missing")
        else:
            need(report.get("development_replay_known_X21") is True,
                 "X22 known source label missing")
        scores=report["overall"]
        need(len(scores)==arms and sum(s["n"] for s in scores.values())==trials,
             tag+" aggregate arms mismatch")
        rows=attempt_rows(report,tag)
        need(len(rows)==trials and len({r["original_sha256"] for r in rows})==sources
            and len({(r["original_sha256"],r["rep"],r["arm"]) for r in rows})==trials,
             tag+" incomplete SHA seed matrix")
        for arm,v in scores.items():
            z=[r for r in rows if r["arm"]==arm]
            need(len(z)==v["n"] and sum(bool(r["accepted"]) for r in z)==v["solved"],
                 tag+" solved status aggregate mismatch "+arm)
            need(abs(sum(float(r["audited_PAR2_s"]) for r in z)-float(v["PAR2_s"]))<.02,
                 tag+" paired PAR2 aggregate mismatch "+arm)
            need(all(r["status"]!="SAT" or r.get("SAT_original_witness_verified")
                     for r in z),tag+" original SAT witness missing "+arm)
        for r in rows:
            need(r["protocol"]==report["protocol"] and r["max_logical_cpus"]==1,
                 tag+" single logical core audit mismatch")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT") and
                 r["audited_PAR2_s"]>=0 and r["elapsed_s"]>=0,
                 tag+" invalid raw trial timing")
            need(bool(r["accepted"]) or
                 abs(float(r["audited_PAR2_s"])-2*cap)<.00001,
                 tag+" invalid unaccepted penalty")
            if tag=="X23" and r["status"]=="UNSAT" and r.get("source_GF2_certificate_validated"):
                need(r["original_sha256"].startswith("43610b90"),
                     "X23 certified source differs from independent GF2 evidence")
                if r["arm"]=="parity_certified":
                    cert=r.get("certificate") or {}
                    need(cert.get("proof_replay_variables_xor_zero") is True and
                         cert.get("proof_replay_rhs_xor_one") is True,
                         "X23 missing algebraic proof replay")
        prepared.append((tag,rid,jid,trials,arms,sources,cap,report,raw_sha,rows))
    db=sqlite3.connect(DB)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        tables={x[0] for x in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        need(set(OLD+(RUN_TABLE,SCORE_TABLE)).issubset(tables),
             "historical tables missing")
        counts={table:db.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0]
                for table in OLD}
        need((db.execute(f"SELECT COUNT(*) FROM {RUN_TABLE}").fetchone()[0],
              db.execute(f"SELECT COUNT(*) FROM {SCORE_TABLE}").fetchone()[0])==(22,165),
             "expected previous 22 runs and 165 scores")
        for _,rid,*_ in prepared:
            need(not db.execute(f"SELECT 1 FROM {RUN_TABLE} WHERE run_id=?",(rid,)).fetchone(),
                 "run already ingested")
        db.execute(f"""CREATE TABLE IF NOT EXISTS {AT_TABLE} (
          run_id INTEGER NOT NULL, original_sha256 TEXT NOT NULL, rep INTEGER NOT NULL,
          arm TEXT NOT NULL, status TEXT NOT NULL, accepted INTEGER NOT NULL,
          source_gf2_certified INTEGER NOT NULL DEFAULT 0,
          original_sat_witness INTEGER NOT NULL, elapsed_s REAL NOT NULL,
          audited_par2_s REAL NOT NULL, child_cpu_s REAL, parent_cpu_s REAL,
          full_trial_json TEXT NOT NULL,
          PRIMARY KEY(run_id,original_sha256,rep,arm),
          FOREIGN KEY(run_id) REFERENCES {RUN_TABLE}(run_id))""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS {FORMULA_TABLE} (
          run_id INTEGER NOT NULL, original_sha256 TEXT NOT NULL, gbd TEXT,
          per_source_json TEXT NOT NULL,
          PRIMARY KEY(run_id,original_sha256),
          FOREIGN KEY(run_id) REFERENCES {RUN_TABLE}(run_id))""")
        need(db.execute(f"SELECT COUNT(*) FROM {AT_TABLE}").fetchone()[0]==0,
             "already ingested X22/X23 trials")
        db.execute("BEGIN IMMEDIATE")
        for tag,rid,jid,trials,arms,sources,cap,report,raw_sha,rows in prepared:
            canonical=json.dumps(report,sort_keys=True,separators=(",",":"))
            db.execute(f"""INSERT INTO {RUN_TABLE}
                (run_id,label,final_job_id,protocol,cohort_classification,run_url,
                trials_declared,score_arms,source_count,cap_s,independent_unsat_lrat,
                global_blind_claim,granularity,source_json_sha256,full_final_json)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rid,tag+"_SIX_REPLAY",jid,report["protocol"],
                 "six X21 development replay source SHA; not global blind",
                 f"https://github.com/Frane12/AndroidGameTest/actions/runs/{rid}",
                 trials,arms,sources,cap,0,0,"audited_final_aggregate_not_trial",
                 sha(canonical.encode()),canonical))
            kissat=float(report["overall"]["kissat1"]["PAR2_s"])
            for arm,row in report["overall"].items():
                z=score(row)
                db.execute(f"""INSERT INTO {SCORE_TABLE}
                  (run_id,arm,n,par2_s,raw_par2_s,solved,timeouts,sat_verified,
                   unsat_reference,child_cpu_s,speedup_vs_kissat,speedup_vs_cadical,
                   original_score_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (rid,arm,z["n"],z["par2"],z["raw"],z["solved"],
                   row.get("timeouts"),z["sat"],z["unsat"],z["cpu"],
                   round(kissat/z["par2"],6) if z["par2"] else None,None,
                   json.dumps(row,sort_keys=True,separators=(",",":"))))
            for r in rows:
                db.execute(f"""INSERT INTO {AT_TABLE}
                  (run_id,original_sha256,rep,arm,status,accepted,
                   source_gf2_certified,original_sat_witness,elapsed_s,
                   audited_par2_s,child_cpu_s,parent_cpu_s,full_trial_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (rid,r["original_sha256"],r["rep"],r["arm"],r["status"],
                    int(bool(r["accepted"])),
                    int(bool(r.get("source_GF2_certificate_validated"))),
                    int(bool(r.get("SAT_original_witness_verified"))),
                    r["elapsed_s"],r["audited_PAR2_s"],
                    r.get("child_cpu_s"),r.get("parent_cpu_s"),
                    json.dumps(r,sort_keys=True,separators=(",",":"))))
            for c in report["per_source"]:
                db.execute(f"""INSERT INTO {FORMULA_TABLE}
                 (run_id,original_sha256,gbd,per_source_json) VALUES(?,?,?,?)""",
                 (rid,c["sha256"],c.get("gbd"),
                  json.dumps(c,sort_keys=True,separators=(",",":"))))
        after={table:db.execute('SELECT COUNT(*) FROM "'+table+'"').fetchone()[0]
               for table in OLD}
        need(after==counts,"history changed during append")
        need(db.execute(f"SELECT COUNT(*) FROM {RUN_TABLE}").fetchone()[0]==24
            and db.execute(f"SELECT COUNT(*) FROM {SCORE_TABLE}").fetchone()[0]==174
            and db.execute(f"SELECT COUNT(*) FROM {AT_TABLE}").fetchone()[0]==108
            and db.execute(f"SELECT COUNT(*) FROM {FORMULA_TABLE}").fetchone()[0]==12,
             "expected appended row counts not reached")
        need(not db.execute("PRAGMA foreign_key_check").fetchall(),
             "foreign key failure")
        db.commit()
        need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
             "SQLite file integrity failure")
    except:
        db.rollback()
        raise
    finally:db.close()
    payload=dict(schema="DRNAS-SQL-X22-X23-108-PAIRED-E2E-v1",
        runs_added=2,run_ids=[x[1] for x in prepared],audited_attempts_added=108,
        score_arms_added=9,per_source_rows_added=12,run_total=24,score_total=174,
        historical_counts_unchanged=True,
        initial_database_sha256=EXPECTED_SHA,new_database_sha256=sha(DB.read_bytes()),
        no_global_blind_claim=True,no_independent_LRAT=True,
        x23_GF2_proof_source_replay_not_LRAT=True,
        previous_table_counts=counts,
        reports_sha256={x[0]:x[8] for x in prepared})
    AUDIT.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    print("X22_X23_SQL_FINAL",json.dumps(payload,sort_keys=True),flush=True)
if __name__=="__main__":main()
