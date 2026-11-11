#!/usr/bin/env python3
"""ATLAS18 frozen blind 20-SHA audit, per-shard PAR2 and append-only SQL log."""
import collections
import hashlib
import json
import pathlib
import sqlite3

ROOT=pathlib.Path("mre_atlas18")
ROOT.mkdir(exist_ok=True)
ARMS=("A","C6_KEEP","C6_KEEP_GAUSS","C6_SELECTIVE","KISSAT","CMS")

def main():
    data_dir=pathlib.Path("audits")
    shards=[json.loads((data_dir/("audit_blind_h%d.json"%i)).read_text()) for i in range(4)]
    assert all(x["mode"]=="blind" and x["shard"]==i for i,x in enumerate(shards))
    manifest=[s for x in shards for s in x["source_manifest"]]
    rows=[r for x in shards for r in x["rows"]]
    assert len(manifest)==20 and len({s["sha256"] for s in manifest})==20
    assert len(rows)==240
    assert sum(s["origin"]=="SATLIB-original" for s in manifest)==5
    assert all(s["index"]==96 for s in manifest)
    assert set(s["category"] for s in manifest)==set(s["category"] for s in rows)
    expected={(s["sha256"],rep,arm) for s in manifest for rep in range(2) for arm in ARMS}
    actual={(r["source_sha"],r["rep"],r["arm"]) for r in rows}
    assert expected==actual and len(actual)==len(rows)
    for r in rows:
        assert r["UNSAT_independent_LRAT"] is False
        assert r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED","UNSAT_UNVERIFIED","UNKNOWN")
        if r["status"]=="GF2_UNSAT_VERIFIED":
            assert r["proof_audit"]["independent_parity_recheck"]
            assert r["proof_audit"]["kind"]=="source_GF2_core_not_LRAT"
        if r["arm"]=="C6_SELECTIVE":
            assert r["dispatch"] in ("C6_KEEP","C6_KEEP_GAUSS")
            assert (r["gauss_gate"]["gate"]=="shadow")==(
                r["dispatch"]=="C6_KEEP_GAUSS")
    grouped=collections.defaultdict(list)
    for r in rows:grouped[(r["source_sha"],r["rep"])].append(r)
    for key,group in grouped.items():
        statuses={r["status"] for r in group}
        assert not ("SAT_VERIFIED" in statuses and
                    ("GF2_UNSAT_VERIFIED" in statuses or
                     "UNSAT_UNVERIFIED" in statuses)),("SAT/UNSAT contradiction",key)
    summary={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        summary[arm]=dict(
            trials=len(subset),
            solved=sum(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") for r in subset),
            SAT=sum(r["status"]=="SAT_VERIFIED" for r in subset),
            GF2_UNSAT=sum(r["status"]=="GF2_UNSAT_VERIFIED" for r in subset),
            UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in subset),
            PAR2_s=round(sum(r["PAR2_verified_s"] for r in subset),6),
            PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in subset),6),
            E2E_s=round(sum(r["E2E_s"] for r in subset),6),
            CPU_s=round(sum(r["CPU_s"] for r in subset),6),
            gate_on=sum(r["gauss_gate"]["gate"]=="shadow" for r in subset),
            deleted=sum(r["native_telemetry"]["atlas15_deleted"] for r in subset),
            compactions=sum(r["native_telemetry"]["atlas16_compactions"] for r in subset),
            peak_rss_kb=max([r["native_telemetry"]["atlas16_maxrss_kb"] for r in subset] or [0]))
    ref=summary["A"]["PAR2_s"]
    for arm in ARMS:
        summary[arm]["speedup_vs_A"]=round(ref/summary[arm]["PAR2_s"],6)
    db=ROOT/"ATLAS18_EVENTS.sqlite"
    assert not db.exists(), "refuse to overwrite existing SQL audit"
    con=sqlite3.connect(db)
    con.executescript("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE source (sha TEXT PRIMARY KEY, category TEXT, origin TEXT,
      idx INTEGER, source_entry TEXT, clauses INTEGER, variables INTEGER);
    CREATE TABLE trial (source_sha TEXT, rep INTEGER, arm TEXT, status TEXT,
      e2e_s REAL, cpu_s REAL, par2_verified_s REAL, par2_reported_s REAL,
      dispatch TEXT, telemetry_json TEXT, proof_audit_json TEXT,
      PRIMARY KEY(source_sha,rep,arm),
      FOREIGN KEY(source_sha) REFERENCES source(sha));
    CREATE TABLE decision_event (source_sha TEXT,rep INTEGER,arm TEXT,
      event_type TEXT, payload_json TEXT,
      PRIMARY KEY(source_sha,rep,arm,event_type),
      FOREIGN KEY(source_sha,rep,arm) REFERENCES trial(source_sha,rep,arm));
    """)
    con.executemany("INSERT INTO source VALUES (?,?,?,?,?,?,?)",[
      (s["sha256"],s["category"],s["origin"],s["index"],s["entry"],
       s["clauses_count"],s["vars"]) for s in manifest])
    for r in rows:
        con.execute("INSERT INTO trial VALUES (?,?,?,?,?,?,?,?,?,?,?)",(
            r["source_sha"],r["rep"],r["arm"],r["status"],r["E2E_s"],
            r["CPU_s"],r["PAR2_verified_s"],r["PAR2_reported_s"],
            r["dispatch"],json.dumps(r["native_telemetry"],sort_keys=True),
            json.dumps(r["proof_audit"],sort_keys=True)))
        con.execute("INSERT INTO decision_event VALUES (?,?,?,?,?)",(
            r["source_sha"],r["rep"],r["arm"],"trial_completed",
            json.dumps(dict(status=r["status"],gauss_gate=r["gauss_gate"],
                            proof=r["proof_audit"],E2E_s=r["E2E_s"]),
                       sort_keys=True)))
    con.commit()
    n=con.execute("SELECT COUNT(*) FROM decision_event").fetchone()[0]
    assert n==240
    con.close()
    result=dict(cohort="ATLAS18 blind index96",source_count=20,
        original_satlib=5,generated=15,repetitions=2,
        paired_trials=240,sql_events=n,shards=[
          dict(shard=x["shard"],summary=x["summary"]) for x in shards],
        summary=summary,UNSAT_independent_LRAT=False)
    (ROOT/"ATLAS18_BLIND_FINAL.json").write_text(json.dumps(result,indent=2,sort_keys=True))
    print("ATLAS18_MERGED "+json.dumps(result,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
