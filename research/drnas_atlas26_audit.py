#!/usr/bin/env python3
"""ATLAS26 cross-shard audit and SQLite event store.

Never merge blind/prospective and nonblind cohorts into a single research claim.
decision_event records completion events, NOT internal CDCL branching decisions.
"""
import collections,hashlib,json,pathlib,sqlite3
from drnas_atlas26_benchmark import ARMS,summary

ROOT=pathlib.Path("audits")/"mre_atlas26"
OUT=pathlib.Path("mre_atlas26")/"audit"
OUT.mkdir(parents=True,exist_ok=True)

def load(cohort,shards):
    datasets=[]
    for shard in range(shards):
        path=ROOT/cohort/f"shard_{shard}"/"results.json"
        assert path.is_file(),f"missing shard {path}"
        data=json.loads(path.read_text())
        m=data["manifest"]
        assert m["cohort"]==cohort and m["shard"]==shard and m["shards"]==shards
        assert m["one_cpu"] and m["source_sha_checked"] and not m["global_blind_claim"]
        assert tuple(m["arms"])==ARMS and m["reps"]==2
        sha=hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest()
        assert sha==data["manifest_sha256"],"manifest hash drift"
        assert len(data["rows"])==len(data["sources"])*m["reps"]*len(ARMS)
        assert len({x["sha256"] for x in data["sources"]})==len(data["sources"])
        assert len({(x["sha256"],x["rep"],x["arm"]) for x in data["rows"]})==len(data["rows"])
        assert set(x["sha256"] for x in data["rows"])=={s["sha256"] for s in data["sources"]}
        for r in data["rows"]:
            assert r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED","UNSAT_UNVERIFIED","UNKNOWN")
            assert r["arm"] in ARMS and r["rep"] in (0,1)
            assert not r["independent_LRAT_UNSAT_verified"]
            assert (r["status"]=="SAT_VERIFIED")==r["original_SAT_witness_verified"]
            assert (r["status"]=="GF2_UNSAT_VERIFIED")==r["independent_GF2_UNSAT_verified"]
            assert r["PAR2_verified_s"]>=0 and r["E2E_s"]>=0
            if r["status"] not in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED"):
                assert abs(r["PAR2_verified_s"]-2*m["cap_s"])<1e-6
        datasets.append(data)
        print("ATLAS26_SHARD "+json.dumps(dict(cohort=cohort,shard=shard,
          sources=len(data["sources"]),trials=len(data["rows"]),
          summary=data["summary"]),sort_keys=True),flush=True)
    sources=[s for d in datasets for s in d["sources"]]
    trials=[r for d in datasets for r in d["rows"]]
    assert len({s["sha256"] for s in sources})==len(sources),"source duplicate across shards"
    assert len({(r["sha256"],r["rep"],r["arm"]) for r in trials})==len(trials)
    return sources,trials

def main():
    sets={}
    for cohort,shards,size in (("regression",1,10),("extension",1,6),("fresh",4,30)):
        sources,rows=load(cohort,shards)
        assert len(sources)==size and len(rows)==size*2*len(ARMS)
        sets[cohort]=(sources,rows)
    shas={cohort:{s["sha256"] for s in sources}
          for cohort,(sources,_) in sets.items()}
    for a in shas:
        for b in shas:
            if a<b:assert shas[a].isdisjoint(shas[b]),f"cohort overlap {a} {b}"

    database=OUT/"atlas26_events.sqlite"
    if database.exists():database.unlink()
    conn=sqlite3.connect(database)
    conn.executescript("""
PRAGMA foreign_keys=ON;
CREATE TABLE source(
  cohort TEXT NOT NULL, sha TEXT NOT NULL, family TEXT NOT NULL,
  source_kind TEXT NOT NULL, case_index INTEGER NOT NULL,
  PRIMARY KEY(cohort,sha));
CREATE TABLE trial(
  cohort TEXT NOT NULL, sha TEXT NOT NULL, rep INTEGER NOT NULL,
  arm TEXT NOT NULL, status TEXT NOT NULL, e2e REAL NOT NULL,
  child_cpu REAL NOT NULL, verified_par2 REAL NOT NULL,
  reported_par2 REAL NOT NULL, metadata_json TEXT NOT NULL,
  PRIMARY KEY(cohort,sha,rep,arm),
  FOREIGN KEY(cohort,sha) REFERENCES source(cohort,sha));
CREATE TABLE decision_event(
  id INTEGER PRIMARY KEY AUTOINCREMENT, cohort TEXT NOT NULL,
  sha TEXT NOT NULL, rep INTEGER NOT NULL, arm TEXT NOT NULL,
  event_type TEXT NOT NULL, verified INTEGER NOT NULL,
  payload_json TEXT NOT NULL);
CREATE INDEX event_by_sha ON decision_event(cohort,sha,arm);
""")
    for cohort,(sources,rows) in sets.items():
        conn.executemany("INSERT INTO source VALUES(?,?,?,?,?)",[
            (cohort,s["sha256"],s["family"],s["source_kind"],s["index"])
            for s in sources])
        conn.executemany("INSERT INTO trial VALUES(?,?,?,?,?,?,?,?,?,?)",[
            (cohort,r["sha256"],r["rep"],r["arm"],r["status"],
             r["E2E_s"],r["CPU_child_s"],r["PAR2_verified_s"],
             r["PAR2_reported_s"],json.dumps(r["telemetry"],sort_keys=True))
            for r in rows])
        conn.executemany("INSERT INTO decision_event(cohort,sha,rep,arm,event_type,verified,payload_json) VALUES(?,?,?,?,?,?,?)",[
            (cohort,r["sha256"],r["rep"],r["arm"],"trial_completed",
             int(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED")),
             json.dumps(dict(status=r["status"],E2E_s=r["E2E_s"],
                 GF2_core_rows=r["GF2_core_rows"]),sort_keys=True))
            for r in rows])
        sums=summary(rows)
        baseline=sums["C7_ADAPT"]
        other={}
        for arm in ARMS:
            x=sums[arm]
            other[arm]=dict(par2_ratio_C7_over_arm=round(
                     baseline["verified_PAR2_s"]/max(x["verified_PAR2_s"],1e-9),5),
                E2E_ratio_C7_over_arm=round(baseline["E2E_s"]/max(x["E2E_s"],1e-9),5),
                delta_verified=x["verified_solved"]-baseline["verified_solved"],
                rss_delta_kb=x["max_rss_kb"]-baseline["max_rss_kb"])
        payload=dict(cohort=cohort,source_count=len(sources),trials=len(rows),
            new_relative_to_prior_generated_index_registry=cohort=="fresh",
            blind_global_claim=False,control="C7_ADAPT",
            verified_UNSAT_requires_independent_GF2_core=True,
            summary=sums,comparisons=other)
        (OUT/f"{cohort}.json").write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n")
        print("ATLAS26_AUDIT "+json.dumps(payload,sort_keys=True),flush=True)
    conn.commit()
    total=conn.execute("SELECT COUNT(*) FROM trial").fetchone()[0]
    events=conn.execute("SELECT COUNT(*) FROM decision_event").fetchone()[0]
    n_sources=conn.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    assert total==events==736 and n_sources==46
    conn.execute("PRAGMA integrity_check")
    integrity=conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity=="ok"
    conn.close()
    print("ATLAS26_SQL "+json.dumps(dict(trials=total,events=events,
        event_type="trial_completed",source_shas=n_sources,
        sqlite_bytes=database.stat().st_size,integrity_check=integrity,
        online_CDCL_decision_events=False),sort_keys=True),flush=True)
    print("ATLAS26_AUDIT_PASS original_CNFs_unmodified=true"
      " SAT_witness_checked=true GF2_independent=true"
      " cohorts_disjoint=true one_cpu=true no_global_blind_claim=true"
      " references_frozen=true",flush=True)

if __name__=="__main__":main()
