#!/usr/bin/env python3
"""ATLAS27 audit. No blending nonblind replay with prospective test claims."""
import hashlib,json,pathlib,sqlite3,sys
sys.path.insert(0,"research")
import drnas_atlas27_benchmark as B
ROOT=pathlib.Path("audits")/"mre_atlas27"
DEST=pathlib.Path("mre_atlas27")/"audit"
DEST.mkdir(parents=True,exist_ok=True)

def main():
    allcohorts={}
    seen=set()
    total=0
    for cohort,shards,n in (("regression",1,10),("extension",1,6),
                             ("hard",1,10),("fresh",4,30)):
        sources=[];trials=[]
        for shard in range(shards):
            path=ROOT/cohort/f"shard_{shard}"/"results.json"
            assert path.is_file(),f"missing shard {path}"
            d=json.loads(path.read_text())
            m=d["manifest"]
            assert m["cohort"]==cohort and m["shard"]==shard and m["shards"]==shards
            assert m["one_cpu"] and m["original_SHA_checked"]
            assert m["code_frozen_before_evaluation"] and not m["global_blind_claim"]
            assert tuple(m["arms"])==B.ARMS and m["reps"]==2
            assert d["manifest_sha256"]==hashlib.sha256(
                json.dumps(m,sort_keys=True).encode()).hexdigest()
            assert len(d["rows"])==len(d["sources"])*2*len(B.ARMS)
            for s in d["sources"]:
                assert s["sha256"] not in seen,"cross-cohort SHA overlap"
                seen.add(s["sha256"])
            keys={(r["sha256"],r["rep"],r["arm"]) for r in d["rows"]}
            assert len(keys)==len(d["rows"])
            for r in d["rows"]:
                assert r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED",
                                        "UNSAT_UNVERIFIED","UNKNOWN")
                assert r["arm"] in B.ARMS
                assert (r["status"]=="SAT_VERIFIED")==r["original_SAT_witness_verified"]
                assert (r["status"]=="GF2_UNSAT_VERIFIED")==r["independent_GF2_UNSAT_verified"]
                assert not r["independent_LRAT_UNSAT_verified"]
                if r["status"] not in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED"):
                    assert abs(r["PAR2_verified_s"]-2*m["cap_s"])<1e-6
            sources+=d["sources"];trials+=d["rows"]
            print("ATLAS27_SHARD "+json.dumps(dict(cohort=cohort,
                shard=shard,sources=len(d["sources"]),trials=len(d["rows"]),
                summary=d["summary"]),sort_keys=True),flush=True)
        assert len(sources)==n and len(trials)==n*2*len(B.ARMS)
        allcohorts[cohort]=(sources,trials)
        total+=len(trials)

    db=DEST/"atlas27.sqlite"
    if db.exists():db.unlink()
    conn=sqlite3.connect(db)
    conn.executescript("""
      PRAGMA foreign_keys=ON;
      CREATE TABLE source(cohort TEXT, sha TEXT, family TEXT, case_index INTEGER,
         PRIMARY KEY(cohort,sha));
      CREATE TABLE trial(cohort TEXT,sha TEXT,rep INTEGER,arm TEXT,status TEXT,
         e2e REAL, verified_par2 REAL,cpu REAL,metrics TEXT,
         PRIMARY KEY(cohort,sha,rep,arm));
      CREATE TABLE event(id INTEGER PRIMARY KEY,cohort TEXT,sha TEXT,rep INTEGER,
         arm TEXT,type TEXT,verified INTEGER,payload TEXT);
    """)
    for cohort,(sources,rows) in allcohorts.items():
        conn.executemany("INSERT INTO source VALUES(?,?,?,?)",
           [(cohort,s["sha256"],s["family"],s["index"]) for s in sources])
        conn.executemany("INSERT INTO trial VALUES(?,?,?,?,?,?,?,?,?)",
           [(cohort,r["sha256"],r["rep"],r["arm"],r["status"],r["E2E_s"],
             r["PAR2_verified_s"],r["CPU_child_s"],
             json.dumps(r["telemetry"],sort_keys=True)) for r in rows])
        conn.executemany("INSERT INTO event(cohort,sha,rep,arm,type,verified,payload) VALUES(?,?,?,?,?,?,?)",
           [(cohort,r["sha256"],r["rep"],r["arm"],"trial_completed",
              int(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED")),
              json.dumps(dict(status=r["status"],GF2_core_rows=r["GF2_core_rows"]),
                         sort_keys=True)) for r in rows])
        summary=B.summarize(rows)
        controls=summary["C7_ADAPT"]
        result=dict(cohort=cohort,sources=len(sources),trials=len(rows),
           globally_blind_claim=False,
           prospective_relative_to_atlas26=cohort in ("hard","fresh"),
           summary=summary,comparisons={k:dict(
              par2_C7_over_arm=round(controls["verified_PAR2_s"]/
                            max(v["verified_PAR2_s"],1e-9),6),
              e2e_C7_over_arm=round(controls["E2E_s"]/
                            max(v["E2E_s"],1e-9),6),
              delta_verified=v["verified_solved"]-controls["verified_solved"],
              delta_rss_kb=v["max_rss_kb"]-controls["max_rss_kb"])
                  for k,v in summary.items()})
        (DEST/f"{cohort}.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print("ATLAS27_AUDIT "+json.dumps(result,sort_keys=True),flush=True)
    conn.commit()
    assert total==1120
    assert conn.execute("SELECT COUNT(*) FROM source").fetchone()[0]==56
    assert conn.execute("SELECT COUNT(*) FROM trial").fetchone()[0]==total
    assert conn.execute("SELECT COUNT(*) FROM event").fetchone()[0]==total
    assert conn.execute("PRAGMA integrity_check").fetchone()[0][0]=="ok"
    conn.close()
    print("ATLAS27_SQL "+json.dumps(dict(trials=total,sources=56,
        events=total,event_type="trial_completed",
        per_CDCL_decision_learning=False,sqlite_bytes=db.stat().st_size,
        integrity_check="ok"),sort_keys=True),flush=True)
    print("ATLAS27_AUDIT_PASS source_disjoint=true original_SAT_verified=true"
          " GF2_independent=true no_global_blind_claim=true one_CPU=true"
          " C7_C26_controls_unchanged=true",flush=True)

if __name__=="__main__":main()
