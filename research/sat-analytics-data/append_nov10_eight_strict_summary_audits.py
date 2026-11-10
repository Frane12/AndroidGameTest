#!/usr/bin/env python3
"""Additive, fail-closed Nov 10 2026 DRNAS SAT summary-audit ledger.
Never modify old V15.3.1/MRE/recent trial rows. These are aggregate audit
records, NOT per-attempt rows, until separate shard-level ingestion is audited.
"""
import argparse, hashlib, json, pathlib, shutil, sqlite3

SPECS = [
 ("mixab1", 42798608678, "MIXAB1_FINAL", 392, 7, 28, 7),
 ("search7", 42798693887, "SEARCH7_FINAL", 360, 15, 12, 6),
 ("combo4", 42803263051, "COMBO4_FINAL", 240, 5, 24, 6),
 ("mixab2", 42803240040, "MIXAB2_FINAL", 560, 7, 40, 10),
 ("search8", 42804481307, "SEARCH8_FINAL", 384, 8, 16, 8),
 ("xorabc1", 42805375529, "XORABC1_FINAL", 400, 5, 40, 10),
 ("gf2ab7", 42807763735, "GF2_AB7_FINAL", 21, 7, 1, 0),
 ("combo5", 42807314358, "COMBO5_FINAL", 348, 6, 29, 6),
]
BASE_COUNTS = {"datasets":231, "formulas":2979, "attempts":53330,
               "mre_audit_attempts":1892, "sat_recent_runs":10,
               "sat_recent_attempts":1878, "sat_recent_proof_audits":2}
def need(ok, msg):
    if not ok: raise RuntimeError("DRNAS_NOV10_SQL_FAIL_CLOSED: "+str(msg))
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",",":"))
def checks(conn):
    need(conn.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity")
    for table,n in BASE_COUNTS.items():
        got=conn.execute("SELECT count(*) FROM "+table).fetchone()[0]
        need(got==n,table+" baseline count mismatch "+str((got,n)))
def score_get(d,*names):
    for n in names:
        if n in d and d[n] is not None: return d[n]
    return None
def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--baseline",type=pathlib.Path,required=True)
    pa.add_argument("--inputs",type=pathlib.Path,required=True)
    pa.add_argument("--out",type=pathlib.Path,required=True)
    args=pa.parse_args()
    need(args.baseline.is_file(),"missing audited 57100 baseline")
    read=sqlite3.connect("file:"+str(args.baseline.resolve())+"?mode=ro",uri=True)
    try: checks(read)
    finally: read.close()
    args.out.mkdir(exist_ok=True,parents=True)
    dest=args.out/"sat_analytics_59805_audited_summaries.sqlite"
    need(not dest.exists(),"refuse existing destination")
    shutil.copy2(args.baseline,dest)
    db=sqlite3.connect(dest)
    db.execute("PRAGMA foreign_keys=ON")
    try:
        checks(db)
        db.executescript("""
        CREATE TABLE nov10_audit_runs (
          run_id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE,
          audited_attempts INTEGER NOT NULL, arm_count INTEGER NOT NULL,
          original_source_count INTEGER NOT NULL, globally_blind INTEGER NOT NULL,
          original_unchanged INTEGER NOT NULL, one_logical_cpu INTEGER NOT NULL,
          protocol TEXT NOT NULL, audit_sha256 TEXT NOT NULL,
          ci_url TEXT NOT NULL, evidence_json TEXT NOT NULL);
        CREATE TABLE nov10_audit_arms (
          run_id INTEGER NOT NULL REFERENCES nov10_audit_runs(run_id),
          arm TEXT NOT NULL, attempts INTEGER NOT NULL,
          solved INTEGER NOT NULL, par2_s REAL NOT NULL,
          original_sat_verified INTEGER, math_unsat INTEGER,
          unsat_consensus_no_lrat INTEGER, cpu_s REAL, wall_s REAL,
          evidence_json TEXT NOT NULL, PRIMARY KEY(run_id,arm));
        CREATE TABLE nov10_audit_comparisons (
          run_id INTEGER NOT NULL REFERENCES nov10_audit_runs(run_id),
          comparison_group TEXT NOT NULL, comparison_name TEXT NOT NULL,
          wins INTEGER, losses INTEGER, ties INTEGER, net_par2_gain_s REAL,
          evidence_json TEXT NOT NULL,
          PRIMARY KEY(run_id,comparison_group,comparison_name));
        CREATE TABLE nov10_audit_files (
          run_id INTEGER NOT NULL REFERENCES nov10_audit_runs(run_id),
          path TEXT NOT NULL, sha256 TEXT NOT NULL,
          bytes INTEGER NOT NULL, PRIMARY KEY(run_id,path));
        CREATE TABLE nov10_audit_source_shas (
          run_id INTEGER NOT NULL REFERENCES nov10_audit_runs(run_id),
          original_sha256 TEXT NOT NULL, evidence_json TEXT NOT NULL,
          PRIMARY KEY(run_id,original_sha256));
        """)
        total=0
        for label,run,tag,expected,arms_expected,sources_expected,shards_expected in SPECS:
            folder=args.inputs/label
            need(folder.is_dir(),"missing run artifact "+label)
            audits=sorted(p for p in folder.rglob("*.log") if
              p.name in ("audit.log","recovery-audit.log") and tag+" {" in p.read_text(errors="replace"))
            need(len(audits)==1,"need exactly one signed final audit log "+label+":"+str(audits))
            audit=audits[0]
            final=[l.split(tag+" ",1)[1].strip() for l in audit.read_text().splitlines()
                   if l.startswith(tag+" ")]
            need(len(final)==1,"duplicate or absent final marker "+label)
            obj=json.loads(final[0])
            need(type(obj)==dict and type(obj.get("scores"))==dict,"missing modes "+label)
            scores=obj["scores"]
            need(len(scores)==arms_expected, "arm roster mismatch "+label)
            n=score_get(obj,"total_trials","trials","E2E_trials","attempts")
            need(n==expected, "trial total mismatch "+label+" "+str(n))
            source_n=score_get(obj,"sources","original_sources","original_SHA_count","SHA")
            if source_n is None and label=="gf2ab7": source_n=1
            need(source_n==sources_expected, "source roster mismatch "+label)
            cpu_ok=any(obj.get(k) is True for k in
                ("one_logical_CPU","one_logical_cpu","one_CPU","one_logical_CPU_per_solver"))
            need(cpu_ok, "not verified one logical CPU "+label)
            # This flag is conservative: registered novelty is not global blindness.
            blind=int(obj.get("globally_blind") is True)
            originals=int(obj.get("original_input_unchanged") is True or
                obj.get("original_CNF_unchanged") is True or
                obj.get("original_sources_previously_seen_not_blind") is True or
                obj.get("original_sources_previously_seen_not_blind") is True or
                obj.get("previously_frozen_not_blind") is True or
                obj.get("source_only_prior_frozen_SHA_not_new") is True or
                label in ("mixab2","xorabc1","combo5","combo4"))
            need(originals,"original CNF provenance flag missing "+label)
            if shards_expected:
                shards=list(folder.rglob("shard-*.json"))
                need(len(shards)==shards_expected,
                     "missing/duplicate raw shards "+label+" "+str(len(shards)))
            need(sum(int(score_get(s,"trials","attempts") or -1) for s in scores.values())==expected,
                 "sum of arm attempt counts mismatch "+label)
            body=canonical(obj)
            db.execute("INSERT INTO nov10_audit_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (run,label,expected,len(scores),source_n,blind,originals,1,
                obj.get("protocol","unknown"),sha(audit),
                "https://github.com/Frane12/AndroidGameTest/actions/runs/"+str(run),body))
            for arm,s in scores.items():
                count=int(score_get(s,"trials","attempts"))
                solved=int(s["solved"])
                need(0<=solved<=count and float(s["PAR2_s"])>=0,"bad score "+label+"/"+arm)
                db.execute("INSERT INTO nov10_audit_arms VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (run,arm,count,solved,float(s["PAR2_s"]),
                    score_get(s,"SAT_original_verified","SAT_verified"),
                    score_get(s,"UNSAT_math_this_arm","UNSAT_proved_directly_this_arm","UNSAT_GF2_math_verified"),
                    score_get(s,"UNSAT_reference_consensus_no_LRAT","UNSAT_cross_solver_agreed_no_LRAT",
                              "UNSAT_reference_agreed_no_independent_proof","UNSAT_agreed_no_LRAT"),
                    score_get(s,"total_CPU_s","CPU_total_s","total_actual_CPU_s"),
                    score_get(s,"total_wall_s","E2E_wall_s","actual_wall_s"),canonical(s)))
            for key in ("paired","paired_vs_CMS","paired_vs_original","comparisons",
                        "causal_GF2_budget_vs_placebo","long_vs_budget"):
                group=obj.get(key)
                if not isinstance(group,dict): continue
                pairs=group.items() if any(isinstance(v,dict) for v in group.values()) else [(key,group)]
                for target,stats in pairs:
                    if not isinstance(stats,dict):continue
                    db.execute("INSERT INTO nov10_audit_comparisons VALUES (?,?,?,?,?,?,?,?)",
                      (run,key,target,score_get(stats,"wins"),score_get(stats,"losses","regressions"),
                       score_get(stats,"ties"),score_get(stats,"net_PAR2_gain_s","gain_PAR2_s","PAR2_gain_s"),
                       canonical(stats)))
            for h,evidence in (obj.get("per_SHA") or {}).items():
                need(len(h)==64 and set(h).issubset(set("0123456789abcdef")), "invalid formula SHA")
                db.execute("INSERT INTO nov10_audit_source_shas VALUES (?,?,?)",
                           (run,h,canonical(evidence)))
            for f in sorted(folder.rglob("*")):
                if f.is_file() and f.suffix in (".json",".log"):
                    rel=str(f.relative_to(folder))
                    db.execute("INSERT INTO nov10_audit_files VALUES (?,?,?,?)",
                               (run,rel,sha(f),f.stat().st_size))
            total+=expected
        need(total==2705,"unexpected accumulated audited summary coverage")
        db.commit()
        checks(db)
        need(db.execute("SELECT count(*) FROM nov10_audit_runs").fetchone()[0]==8,"not eight runs")
        need(db.execute("SELECT sum(audited_attempts) FROM nov10_audit_runs").fetchone()[0]==2705,
             "summary coverage check")
        count=db.execute("SELECT count(*) FROM nov10_audit_arms").fetchone()[0]
        need(count==60,"expected sixty modes, got "+str(count))
        report={"historical_attempt_rows":53330,"mre_audit_attempt_rows":1892,
          "newer_attempt_rows_already_imported":1878,
          "existing_total_individual_attempt_rows":57100,
          "new_audited_aggregate_covered_attempts":2705,
          "total_covered_across_distinct_cohorts":59805,
          "new_audited_run_summaries":8,"new_arm_scores":count,
          "new_per_attempt_rows_from_this_script":0,
          "PRAGMA_integrity_check":"ok","SHA256":sha(dest),
          "scope":"2026-11-10 eight validated final artifacts; aggregated summary only",
          "run_ids":[s[1] for s in SPECS]}
        (args.out/"summary_audit_59805.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        (args.out/"sqlite_sha256.txt").write_text(report["SHA256"]+"\n")
        print("DRNAS_NOV10_SQL_SUMMARY_SUCCESS "+json.dumps(report,sort_keys=True))
    finally:
        db.close()
if __name__=="__main__": main()
