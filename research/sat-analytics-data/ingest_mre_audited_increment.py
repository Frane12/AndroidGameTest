#!/usr/bin/env python3
"""Append REAL SHA/seed paired MRE7-11 attempts to the historical SQLite.

Read-only archived tables datasets/formulas/attempts/telemetry are UNTOUCHED.
New tables mre_audit_runs, mre_audit_attempts, mre_audit_scores form an
independent experiment/provenance namespace. Not a global pooled PAR2.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,pathlib,sqlite3
from collections import defaultdict

def need(b,msg):
    if not b:raise RuntimeError("DRNAS_ANALYTICS_FAIL_CLOSED "+str(msg))
def ingest(db,rawroot,registry,outdir):
    doc=json.loads(pathlib.Path(registry).read_text())
    need(doc["schema_version"]=="DRNAS-recent-audits-v1-2026-11-08","registry version")
    specs=doc["runs"]
    need(len(specs)==8 and sum(x["expected_attempts"] for x in specs)==1892,
         "regression in eight audit inventories")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS mre_audit_runs (
      dataset TEXT PRIMARY KEY, family TEXT NOT NULL, audit_run INTEGER NOT NULL,
      trial_run INTEGER NOT NULL, audit_job INTEGER NOT NULL,
      protocol TEXT NOT NULL, provenance TEXT NOT NULL,
      sources INTEGER NOT NULL, repetitions INTEGER NOT NULL,
      cap_s REAL NOT NULL, expected_attempts INTEGER NOT NULL,
      official_originals_shalocked INTEGER NOT NULL,
      unsat_independent_lrat INTEGER NOT NULL DEFAULT 0,
      audit_url TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS mre_audit_attempts (
      dataset TEXT NOT NULL, source_sha256 TEXT NOT NULL, case_name TEXT,
      year TEXT, source_cohort TEXT, mode TEXT NOT NULL, rep INTEGER NOT NULL,
      solver_seed INTEGER, independent_seed_applied INTEGER,
      verdict TEXT NOT NULL, par2_s REAL NOT NULL, wall_s REAL NOT NULL,
      original_sat_witness_checked INTEGER, unsat_source_agreement INTEGER,
      independent_unsat_lrat INTEGER NOT NULL DEFAULT 0,
      gate_applied INTEGER, variables_eliminated INTEGER,
      clauses_removed INTEGER, gate_reason TEXT,
      native_conflicts INTEGER, native_decisions INTEGER,
      native_propagations INTEGER, runner_commit TEXT,
      PRIMARY KEY(dataset,source_sha256,mode,rep),
      FOREIGN KEY(dataset) REFERENCES mre_audit_runs(dataset)
    );
    CREATE TABLE IF NOT EXISTS mre_audit_scores (
      dataset TEXT NOT NULL, mode TEXT NOT NULL, reference_mode TEXT NOT NULL,
      trials INTEGER NOT NULL, solved INTEGER NOT NULL, timeouts INTEGER NOT NULL,
      par2_s REAL NOT NULL, reference_speedup_x REAL NOT NULL,
      PRIMARY KEY(dataset,mode),
      FOREIGN KEY(dataset) REFERENCES mre_audit_runs(dataset)
    );
    CREATE INDEX IF NOT EXISTS idx_mre_audit_mode
      ON mre_audit_attempts(dataset,mode,source_sha256);
    """)
    outdir=pathlib.Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    output=[]
    for spec in specs:
        runid=spec["id"];source_run=int(spec.get("trial_run") or spec["run"])
        root=pathlib.Path(rawroot)/runid
        files=sorted(root.rglob("shard-*.json"))
        # Duplicate source files in an artifact are not expected.
        need(files and len(files)==len({f.name for f in files}),
             runid+" duplicated or missing shard files")
        trials=[]
        for path in files:
            obj=json.loads(path.read_text())
            if isinstance(obj,dict):
                obj=obj.get("trials",obj.get("rows",obj.get("results")))
            need(isinstance(obj,list),runid+" invalid shard "+str(path))
            trials.extend(obj)
        need(len(trials)==spec["expected_attempts"],
             runid+" attempts "+str(len(trials))+" != "+str(spec["expected_attempts"]))
        db.execute("""INSERT INTO mre_audit_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (runid,spec["family"],spec["run"],source_run,spec["job"],
           spec["scores"][0] and trials[0].get("protocol",trials[0].get("proto")),
           spec["cohort"],spec["sources"],spec["reps"],spec["cap"],
           spec["expected_attempts"],1,0,
           "https://github.com/Frane12/AndroidGameTest/actions/runs/"+str(spec["run"])))
        seen=set();mode_groups=defaultdict(list);by_sources=defaultdict(set)
        cap=float(spec["cap"])
        for row in trials:
            mode=row.get("mode")
            sha=row.get("sha256") or row.get("source_sha256") or row.get("original_sha256")
            name=str(row.get("source") or row.get("gbd") or sha)
            need(isinstance(sha,str) and len(sha)==64 and
                 all(c in "0123456789abcdef" for c in sha),runid+" missing SHA")
            verdict=str(row.get("verdict") or row.get("status") or "").upper()
            if verdict=="UNKNOWN":verdict="TIMEOUT"
            need(verdict in ("SAT","UNSAT","TIMEOUT"),runid+" bad verdict")
            par2=float(row["par2_s"])
            need(0<=par2<=2*cap+0.0001,runid+" bad PAR2 cap")
            if verdict=="TIMEOUT":need(abs(par2-2*cap)<0.00001,
                                       runid+" timeout not charged 2x cap")
            wall=float(row.get("wall_s",row.get("full_wall_s",0)))
            need(wall>=0,runid+" negative wall")
            rep=int(row["rep"])
            seed=row.get("seed")
            key=(sha,mode,rep)
            need(key not in seen,runid+" repeated SHA/mode/rep")
            seen.add(key);mode_groups[mode].append(row);by_sources[sha].add(rep)
            satcheck=(row.get("original_sat_verified")
               if "original_sat_verified" in row else
               row.get("model_original_verified")
               if "model_original_verified" in row else
               row.get("original_SAT_witness_verified")
               if "original_SAT_witness_verified" in row else
               row.get("source_original_SAT_witness_verified"))
            if verdict=="SAT":need(satcheck is True,runid+" unverified SAT model")
            unsat_agree=(row.get("UNSAT_agreement_CaDiCaL_no_independent_LRAT")
                      if "UNSAT_agreement_CaDiCaL_no_independent_LRAT" in row else
                         row.get("UNSAT_official_agreement_without_LRAT")
                      if "UNSAT_official_agreement_without_LRAT" in row else
                         row.get("official_UNSAT_status_crosschecked")
                      if "official_UNSAT_status_crosschecked" in row else
                         row.get("UNSAT_reported_without_independent_LRAT"))
            if verdict=="UNSAT":
                need(unsat_agree is True,runid+" UNSAT lacks source agreement")
            gate=row.get("gate") or {}
            stats=row.get("native") or row.get("native_stats") or {}
            def val(x):return int(x) if x is not None else None
            def boolean(x):return int(bool(x)) if x is not None else None
            eliminated=gate.get("variables_eliminated",gate.get("eliminated_variables"))
            reason=gate.get("reason",gate.get("gate"))
            # The original native C++ solver's gate telemetry is absent when
            # subprocess times out. Null is NOT zero.
            db.execute("""INSERT INTO mre_audit_attempts VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
             (runid,sha,name,str(row.get("year","")),row.get("source_cohort"),
              mode,rep,val(seed),boolean(row.get("independent_seed_applied")),
              verdict,par2,wall,boolean(satcheck) if verdict=="SAT" else None,
              boolean(unsat_agree) if verdict=="UNSAT" else None,0,
              boolean(gate.get("applied")) if gate else None,
              val(eliminated),val(gate.get("clauses_removed")),
              str(reason)[:180] if reason is not None else None,
              val(stats.get("conflicts",row.get("native_conflicts"))),
              val(stats.get("decisions",row.get("native_decisions"))),
              val(stats.get("propagations",row.get("native_propagations"))),
              row.get("run_sha",row.get("build_sha",row.get("github_sha")))))
        need(len(by_sources)==spec["sources"],
             runid+" unexpected source count "+str(len(by_sources)))
        mode_reference={s["mode"]:s for s in spec["scores"]}
        need(set(mode_groups)==set(mode_reference),runid+" missing/alien modes")
        for mode,rr in mode_groups.items():
            expected=mode_reference[mode]
            need(len(rr)==spec["sources"]*spec["reps"],
                 runid+" incorrect paired mode count "+mode)
            nsolved=sum(str(v.get("verdict") or v.get("status")).upper()
                        in ("SAT","UNSAT") for v in rr)
            total=sum(float(v["par2_s"]) for v in rr)
            need(nsolved==expected["solved"] and
                 abs(total-expected["PAR2_s"])<0.0001,
                 runid+" audit source score mismatch "+mode+" "+
                 str(total)+" "+str(expected["PAR2_s"]))
            db.execute("INSERT INTO mre_audit_scores VALUES (?,?,?,?,?,?,?,?)",
              (runid,mode,spec["ref"],len(rr),nsolved,
               len(rr)-nsolved,expected["PAR2_s"],
               expected["reference_x"]))
            output.append(dict(run=runid,mode=mode,sources=spec["sources"],
                      attempts=len(rr),solved=nsolved,
                      cap=cap,PAR2_s=expected["PAR2_s"],reference=spec["ref"],
                      speedup_x=expected["reference_x"],cohort=spec["cohort"]))
        for key in by_sources:
            need(by_sources[key]==set(range(spec["reps"])),
                 runid+" incomplete repeated source seeds")
        print("MRE_ANALYTICS_VERIFIED",runid,len(trials),len(by_sources),
              len(mode_groups),flush=True)
    need(len(output)==52,"52 protocol mode results expected")
    attempts=db.execute("SELECT COUNT(*) FROM mre_audit_attempts").fetchone()[0]
    need(attempts==1892,"expected 1892 additive attempts")
    # The original warehouse must remain intact and queryable.
    need({"datasets","formulas","attempts","telemetry"}<=
         {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")},
         "original V15.3.1 schema disappeared")
    db.commit()
    cols=["run","mode","sources","attempts","solved","cap","PAR2_s","reference",
          "speedup_x","cohort"]
    with (outdir/"mre_new_mode_summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(output)
    digest=hashlib.sha256(pathlib.Path(registry).read_bytes()).hexdigest()
    report=dict(verified_audited_runs=len(specs),verified_attempts=attempts,
                modes=len(output),original_V1531_tables_preserved=True,
                same_cohort_only_for_PAR2_comparison=True,
                independent_unsat_LRAT=False,
                source_registry_sha256=digest)
    (outdir/"mre_ingest_audit.json").write_text(
       json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE_ANALYTICS_FINAL",json.dumps(report,sort_keys=True),flush=True)

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--source-root",default="mre_raw")
    a.add_argument("--registry",
      default="research/sat-analytics-data/current/mre_audited_run_registry_20261108.json")
    a.add_argument("--db",
      default="research/sat-analytics-data/current/sat_analytics.sqlite")
    a.add_argument("--out",default="mre_analytics_out")
    args=a.parse_args()
    db=sqlite3.connect(args.db)
    try:
        db.execute("PRAGMA busy_timeout=5000")
        ingest(db,args.source_root,args.registry,args.out)
    finally:db.close()

if __name__=="__main__":main()
