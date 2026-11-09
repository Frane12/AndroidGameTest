#!/usr/bin/env python3
"""Append four audited X19/X19B/X20/X21 cohorts and their real E2E rows.

Base is the previously verified X18/X16A SQLite. Historical tables are immutable.
No fake attempts, no cross-cohort PAR2 pooling, no global-blind or UNSAT LRAT claim.
"""
from __future__ import annotations
import hashlib, json, pathlib, re, sqlite3

BASE = pathlib.Path("research/sat-analytics-data/current")
DB = BASE / "sat_analytics.sqlite"
AUDIT = BASE / "refresh_x19_x21_20261109_audit.json"
EXPECTED_PARENT_SHA = "e0d0df933c17dde44237647cb40cf843b41afe7b27943fa3d4b60782f2420173"
SOURCES = (
    ("X19", 42581795977, 129043592428, 12, 144, 6, 12.0),
    ("X19B",42582976460, 129047570246, 8, 128, 8, 12.0),
    ("X20", 42587550843, 129064942008, 24, 288, 6, 12.0),
    ("X21", 42586193407, 129067846662, 24, 432, 9, 30.0),
)
HISTORICAL = ("datasets","formulas","attempts","telemetry",
    "mre_x9x10_runs","mre_x9x10_attempts","mre_x9x10_scores")
RUNS = "research_final_runs_20261109"
SCORES = "research_final_scores_20261109"
TIERS = "research_final_tiers_20261109"
ATTEMPTS = "research_x19_x21_attempts_20261109"
FORMULAS = "research_x19_x21_formulas_20261109"

def need(value, reason):
    if not value:
        raise RuntimeError("DRNAS_SQL_X19_X21_FAIL_CLOSED "+reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def get(row, *keys):
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None

def find_report(tag):
    p=pathlib.Path("source-audits")/tag.lower()
    matches=list(p.rglob("report.json"))
    need(len(matches)==1, tag+" expected exactly one report.json: "+str(matches))
    path=matches[0]
    raw=path.read_bytes()
    return json.loads(raw), sha(raw), path

def arm_score(s):
    return dict(n=s["n"],
        par2=get(s,"PAR2_s","wall_PAR2_s"),
        solved=s["solved"], timeouts=s.get("timeouts"),
        sat=get(s,"SAT_verified","SAT_original_verified"),
        unsat=get(s,"UNSAT_backend_agreement","UNSAT_cross_solver_agreement_no_LRAT",
                  "UNSAT_agreement_no_LRAT"),
        cpu=get(s,"child_cpu_s","actual_child_cpu_s"),
        cpu_budget=get(s,"CPU_PAR2_s","CPU_budget_PAR2_s","cpu_budget_PAR2_s"))

def prepare():
    reports=[]
    for tag,rid,jid,sources,trials,arms,cap in SOURCES:
        report,raw_sha,report_path=find_report(tag)
        need(report.get("protocol","").startswith("DRNAS-"+tag+"-"),tag+" wrong protocol")
        need(report.get("UNSAT_independent_LRAT") is False,tag+" independent proof drift")
        need(report["trials"]==trials and report["sources"]==sources,tag+" source/trial drift")
        need(len(report.get("overall",report.get("score",{})))==arms,tag+" arm count drift")
        sc=report.get("overall",report.get("score",{}))
        if tag=="X19B":
            need(report.get("no_auto_promotion") is True,tag+" promotion drift")
        elif tag=="X21":
            need(report.get("no_auto_promotion") is True and report.get("global_blind_claim") is False,
                 "X21 blindness/promotion drift")
        else:
            need(report.get("strict_no_auto_promotion") is True and report.get("blind_holdout") is False,
                 tag+" blindness/promotion drift")
        rows=report.get("rows")
        if tag=="X19B":
            # X19B's final audit intentionally stores paired attempts in the
            # eight adjacent shard JSON files rather than duplicating rows in report.json.
            rows=[]
            for shard in range(8):
                f=report_path.parent/("shard-%d.json"%shard)
                need(f.is_file(),tag+" audited shard file missing "+str(shard))
                data=json.loads(f.read_text())
                need(len(data.get("trials",[]))==16,
                     tag+" invalid shard size "+str(shard))
                rows.extend(data["trials"])
            for orig_sha in {r["original_sha256"] for r in rows}:
                subset=[r for r in rows if r["original_sha256"]==orig_sha]
                ref_k=any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in subset)
                ref_c=any(r["arm"]=="cadical1" and r["status"]=="UNSAT" for r in subset)
                for r in subset:
                    r["accepted"] = bool(r["status"]=="SAT" or
                        (r["status"]=="UNSAT" and ref_k and ref_c))
                    r["audited_PAR2_s"]=(r["PAR2_s"] if r["accepted"] else 2*cap)
            # Replayed audited acceptance must exactly regenerate report's scores.
            report["rows"]=rows
        need(isinstance(rows,list) and len(rows)==trials,tag+" full audited rows missing")
        srcs={r["original_sha256"] for r in rows}
        need(len(srcs)==sources and all(re.fullmatch(r"[0-9a-f]{64}",a) for a in srcs),
             tag+" SHA/source count wrong")
        need(len({(r["original_sha256"],r["rep"],r["arm"]) for r in rows})==trials,
             tag+" duplicate pairing")
        for arm,score in sc.items():
            g=[r for r in rows if r["arm"]==arm]
            n=arm_score(score)
            need(len(g)==2*sources and n["n"]==len(g),tag+" unpaired arm "+arm)
            need(n["par2"] is not None and n["solved"] is not None,
                 tag+" aggregate missing "+arm)
            need(all(r.get("protocol")==report["protocol"] and
                isinstance(r.get("accepted"),bool) and
                r["status"] in ("SAT","UNSAT","TIMEOUT") and
                float(r.get("audited_PAR2_s",0))>=0 and
                float(r.get("elapsed_s",-1))>=0 and
                (r["status"]!="SAT" or r.get("SAT_original_witness_verified"))
                for r in g),tag+" invalid audited attempt "+arm)
            need(sum(bool(r["accepted"]) for r in g)==n["solved"],
                 tag+" solved aggregate mismatch "+arm)
            need(abs(sum(float(r["audited_PAR2_s"]) for r in g)-float(n["par2"]))<.02,
                 tag+" PAR2 aggregate mismatch "+arm)
            need(all(int(r["rep"]) in (0,1) for r in g),tag+" bad paired repetition")
            need(all((r["accepted"] or abs(float(r["audited_PAR2_s"])-2*cap)<1e-4)
                 for r in g),tag+" invalid timeout/UNSAT penalty "+arm)
        need(all(set(r["arm"] for r in rows if r["original_sha256"]==s and r["rep"]==rep)
                 ==set(sc) for s in srcs for rep in (0,1)),
             tag+" missing SHA-arm pairing")
        reports.append((tag,rid,jid,sources,trials,arms,cap,report,raw_sha))
    return reports

def main():
    need(DB.is_file(),"database missing")
    parent=sha(DB.read_bytes())
    need(parent==EXPECTED_PARENT_SHA,"base database SHA drift")
    reports=prepare()
    db=sqlite3.connect(DB)
    try:
        db.execute("PRAGMA foreign_keys=ON")
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        need(set(HISTORICAL+(RUNS,SCORES,TIERS)).issubset(tables),
             "historical summary tables missing")
        before={t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0]
                for t in HISTORICAL}
        summary_before=tuple(db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0]
                             for t in (RUNS,SCORES,TIERS))
        need(summary_before==(18,136,141),"unexpected previous aggregate counts")
        need(all(db.execute(f"SELECT COUNT(*) FROM {RUNS} WHERE run_id=?",(rid,)).fetchone()[0]==0
                 for _,rid,*_ in reports),"run already ingested")
        db.execute(f"""CREATE TABLE IF NOT EXISTS {ATTEMPTS} (
            run_id INTEGER NOT NULL, original_sha256 TEXT NOT NULL,
            rep INTEGER NOT NULL, arm TEXT NOT NULL, seed INTEGER,
            status TEXT NOT NULL, accepted INTEGER NOT NULL,
            sat_witness_verified INTEGER NOT NULL,
            audited_par2_s REAL NOT NULL, elapsed_s REAL NOT NULL,
            child_cpu_s REAL, parent_cpu_s REAL,
            allocated_logical_cpus INTEGER, full_trial_json TEXT NOT NULL,
            PRIMARY KEY (run_id,original_sha256,rep,arm),
            FOREIGN KEY(run_id) REFERENCES {RUNS}(run_id))""")
        db.execute(f"""CREATE TABLE IF NOT EXISTS {FORMULAS} (
            run_id INTEGER NOT NULL, original_sha256 TEXT NOT NULL,
            gbd TEXT, year TEXT, features_json TEXT, score_json TEXT,
            PRIMARY KEY(run_id,original_sha256),
            FOREIGN KEY(run_id) REFERENCES {RUNS}(run_id))""")
        need(db.execute(f"SELECT COUNT(*) FROM {ATTEMPTS}").fetchone()[0]==0,
             "trial table already populated")
        need(db.execute(f"SELECT COUNT(*) FROM {FORMULAS}").fetchone()[0]==0,
             "formula table already populated")
        db.execute("BEGIN IMMEDIATE")
        tier_count=0
        formula_count=0
        for tag,rid,jid,sources,trials,arms,cap,report,raw_sha in reports:
            sc=report.get("overall",report.get("score",{}))
            canonical=json.dumps(report,sort_keys=True,separators=(",",":"))
            db.execute(f"""INSERT INTO {RUNS}
             (run_id,label,final_job_id,protocol,cohort_classification,run_url,
              trials_declared,score_arms,source_count,cap_s,independent_unsat_lrat,
              global_blind_claim,granularity,source_json_sha256,full_final_json)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (rid,tag+"_SOURCE_AUDITED",jid,report["protocol"],
               "source-only prior-registry-disjoint; not global blind; original SHA",
               "https://github.com/Frane12/AndroidGameTest/actions/runs/"+str(rid),
               trials,arms,sources,cap,0,0,"audited_final_aggregate_not_trial",
               sha(canonical.encode()),canonical))
            ref=arm_score(sc["kissat1"])["par2"]
            for arm,score in sc.items():
                m=arm_score(score)
                cpar=float(m["par2"])
                db.execute(f"""INSERT INTO {SCORES}
                 (run_id,arm,n,par2_s,raw_par2_s,solved,timeouts,
                 sat_verified,unsat_reference,child_cpu_s,
                 speedup_vs_kissat,speedup_vs_cadical,original_score_json)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (rid,arm,m["n"],cpar,
                  get(score,"raw_PAR2_s","PAR2_s","wall_PAR2_s"),
                  m["solved"],m["timeouts"],m["sat"],m["unsat"],m["cpu"],
                  round(ref/cpar,6) if cpar else None,
                  round(arm_score(sc["cadical1"])["par2"]/cpar,6)
                    if cpar and "cadical1" in sc else None,
                  json.dumps(score,sort_keys=True,separators=(",",":"))))
            for group in ("by_binary_class","by_horn_class","by_year"):
                for tier,subs in report.get(group,{}).items():
                    for arm,score in subs.items():
                        m=arm_score(score)
                        db.execute(f"""INSERT INTO {TIERS}
                        (run_id,tier,arm,n,par2_s,raw_par2_s,solved,
                        timeouts,sat_verified,unsat_reference,original_score_json)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                        (rid,group+"/"+tier,arm,m["n"],m["par2"],
                         get(score,"raw_PAR2_s","PAR2_s","wall_PAR2_s"),
                         m["solved"],m["timeouts"],m["sat"],m["unsat"],
                         json.dumps(score,sort_keys=True,separators=(",",":"))))
                        tier_count+=1
            for r in report["rows"]:
                db.execute(f"""INSERT INTO {ATTEMPTS}
                (run_id,original_sha256,rep,arm,seed,status,accepted,
                 sat_witness_verified,audited_par2_s,elapsed_s,child_cpu_s,
                 parent_cpu_s,allocated_logical_cpus,full_trial_json)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (rid,r["original_sha256"],r["rep"],r["arm"],r.get("seed"),
                  r["status"],int(r["accepted"]),int(bool(r.get("SAT_original_witness_verified"))),
                  r["audited_PAR2_s"],r["elapsed_s"],r.get("child_cpu_s"),
                  r.get("parent_cpu_s"),r.get("allocated_logical_cpus"),
                  json.dumps(r,sort_keys=True,separators=(",",":"))))
            for sf in report.get("per_source",[]):
                info=sf.get("features") or sf.get("structure")
                db.execute(f"""INSERT INTO {FORMULAS}
                  (run_id,original_sha256,gbd,year,features_json,score_json)
                  VALUES(?,?,?,?,?,?)""",
                  (rid,sf["sha256"],sf.get("gbd"),sf.get("year"),
                   json.dumps(info,sort_keys=True) if info is not None else None,
                   json.dumps(sf.get("score",sf.get("scores")),sort_keys=True)))
                formula_count+=1
        after={t:db.execute('SELECT COUNT(*) FROM "'+t+'"').fetchone()[0]
               for t in HISTORICAL}
        need(after==before,"historic tables mutated")
        need(db.execute(f"SELECT COUNT(*) FROM {ATTEMPTS}").fetchone()[0]==992,
             "trial count mismatch")
        need(db.execute(f"SELECT COUNT(*) FROM {RUNS}").fetchone()[0]==22,
             "run count mismatch")
        need(db.execute(f"SELECT COUNT(*) FROM {SCORES}").fetchone()[0]==165,
             "score count mismatch")
        need(db.execute("PRAGMA foreign_key_check").fetchall()==[],
             "foreign key violation")
        db.execute(f"CREATE INDEX IF NOT EXISTS idx_x19_x21_accepted ON {ATTEMPTS}(run_id,accepted,status)")
        db.execute(f"CREATE INDEX IF NOT EXISTS idx_x19_x21_source ON {ATTEMPTS}(original_sha256)")
        db.commit()
        need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
             "database integrity failed")
    except:
        db.rollback()
        raise
    finally:
        db.close()
    result=dict(schema="DRNAS-SQL-X19-X21-992-INDIVIDUAL-E2E-v1",
       base_sha256=parent,new_sha256=sha(DB.read_bytes()),runs_added=4,
       run_ids=[x[1] for x in reports],audited_e2e_attempts_added=992,
       score_arms_added=29,source_formula_rows_added=formula_count,
       tier_rows_added=tier_count,old_run_count=18,new_run_count=22,
       old_score_count=136,new_score_count=165,
       historical_counts_unchanged=True,historical_counts=before,
       original_audit_report_sha256={tag:raw for tag,_,_,_,_,_,_,_,raw in reports},
       independently_proven_unsat=False,no_global_blind_claim=True,
       mixed_cohort_PAR2_not_poolable=True)
    AUDIT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("DRNAS_X19_X21_SQL_FINAL",json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
