#!/usr/bin/env python3
"""ATLAS18 frozen single-stage audit: true SAT/GF2 proofs versus reported UNSAT.

The per-family learned policy table is retrospective diagnostics, never
fed into this blind holdout experiment or to frozen ATLAS16 controls.
"""
import argparse,collections,hashlib,json,pathlib,shutil,sqlite3
ARMS=("A","C6_KEEP","C7_ADAPT","C7_ADAPT_GAUSS","C8_FAST_Q8","C8_FAST_Q16","C8_GATE_Q8","C8_GATE_Q16","KISSAT","CMS")
ROOT=pathlib.Path("mre_atlas18")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stage",type=int,choices=(1,),required=True)
    p.add_argument("--audit-dir",type=pathlib.Path,required=True)
    p.add_argument("--prior-db",type=pathlib.Path)
    a=p.parse_args()
    shards=[json.loads((a.audit_dir/f"audit_s{a.stage}_h{i}.json").read_text()) for i in range(10)]
    assert sorted(s["shard"] for s in shards)==list(range(10))
    assert all(s["stage"]==a.stage for s in shards)
    manifest=[s for shard in shards for s in shard["source_manifest"]]
    rows=[r for shard in shards for r in shard["rows"]]
    assert len(manifest)==100 and len({s["sha256"] for s in manifest})==100
    assert len(rows)==2000 and len({(r["source_sha"],r["rep"],r["arm"]) for r in rows})==2000
    expected={(s["sha256"],rep,arm) for s in manifest for rep in range(2) for arm in ARMS}
    assert expected=={(r["source_sha"],r["rep"],r["arm"]) for r in rows}
    families=collections.Counter(s["category"] for s in manifest)
    assert len(families)==20 and all(x==5 for x in families.values())
    assert sum(s["origin"]=="SATLIB-original" for s in manifest)==25
    assert len(set(s["sha256"] for s in manifest))==100
    # Every SAT solver may report uncertified UNSAT but no solver can contradict
    # a verified SAT witness on the same SHA and seed.
    grouped=collections.defaultdict(dict)
    for r in rows:grouped[(r["source_sha"],r["rep"])][r["arm"]]=r
    for key,arms in grouped.items():
        st={r["status"] for r in arms.values()}
        if "SAT_VERIFIED" in st and ("UNSAT_UNVERIFIED" in st or "GF2_UNSAT_VERIFIED" in st):
            raise AssertionError("SAT/UNSAT contradiction "+str(key))
    db=ROOT/"ATLAS18_LEARNING.sqlite"
    if a.stage>1:
        assert a.prior_db and a.prior_db.is_file(),"missing chained SQL audit DB"
        shutil.copyfile(a.prior_db,db)
    else:
        assert not a.prior_db
        if db.exists():db.unlink()
    conn=sqlite3.connect(db)
    conn.executescript(pathlib.Path("research/drnas_atlas18_schema.sql").read_text())
    seen={r[0] for r in conn.execute("SELECT DISTINCT stage FROM cohort")}
    assert seen==set(range(1,a.stage)),"non-sequential stage history in DB"
    if a.stage==2:
        previous={r[0] for r in conn.execute("SELECT source_sha FROM cohort WHERE stage=1")}
        assert previous.isdisjoint(s["sha256"] for s in manifest),"stage2 not genuinely unseen"
    if a.stage==3:
        previous={r[0] for r in conn.execute("SELECT source_sha FROM cohort WHERE stage=2")}
        assert previous=={s["sha256"] for s in manifest},"stage3 source replay drift"
    conn.executemany("INSERT INTO cohort VALUES(?,?,?,?,?,?,?,?,?)",[
        (a.stage,s["sha256"],s["category"],s["origin"],s["entry"],
         s["index"],s["vars"],s["clauses_count"],int(a.stage==3)) for s in manifest])
    conn.executemany("INSERT INTO trial VALUES(?,?,?,?,?,?,?,?,?,?)",[
        (a.stage,r["source_sha"],r["rep"],r["arm"],r["status"],r["E2E_s"],
         r["PAR2_verified_s"],r["PAR2_reported_s"],r["policy"],
         json.dumps(r["native_telemetry"],sort_keys=True)) for r in rows])
    conn.executemany("INSERT INTO decision_event VALUES(?,?,?,?,?,?,?)",[
        (a.stage,r["source_sha"],r["rep"],r["arm"],"trial_completed",
         int(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED")),
         json.dumps(dict(status=r["status"],policy=r["policy"],
                         E2E_s=r["E2E_s"],telemetry=r["native_telemetry"]),
                    sort_keys=True)) for r in rows])
    # No holdout-driven policy changes in the causal factorial experiment.
    # Reference policy is frozen from pre-experiment ATLAS15 training.
    family_policy={cat:"1.0,0.85" for cat in sorted(families)}
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)") if conn.execute("PRAGMA journal_mode").fetchone()[0]=="wal" else None
    dbbytes=db.stat().st_size
    roll={}
    for arm in ARMS:
        selected=[r for r in rows if r["arm"]==arm]
        tel=[r["native_telemetry"] for r in selected]
        roll[arm]=dict(trials=len(selected),
            solved=sum(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") for r in selected),
            SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in selected),
            GF2_UNSAT_verified=sum(r["status"]=="GF2_UNSAT_VERIFIED" for r in selected),
            UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in selected),
            timeouts=sum(r["status"]=="UNKNOWN" for r in selected),
            E2E_s=round(sum(r["E2E_s"] for r in selected),5),
            PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in selected),5),
            PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in selected),5),
            deleted=sum(t["atlas15_deleted"] for t in tel),
            minimized=sum(t["atlas15_minimized"] for t in tel),
            compactions=sum(t["atlas16_compactions"] for t in tel),
            reclaimed_slots=sum(t["atlas16_reclaimed_slots"] for t in tel),
            maxrss_kb=max(t["atlas16_maxrss_kb"] for t in tel),
            watch_visits=sum(t["watch_visits"] for t in tel),
            propagations=sum(t["propagations"] for t in tel),
            bcp_watch_per_prop=round(sum(t["watch_visits"] for t in tel)/
                max(1,sum(t["propagations"] for t in tel)),5),
            pressure_cycles=sum(t["atlas17_pressure_cycles"] for t in tel),
            low_cycles=sum(t["atlas17_low_cycles"] for t in tel))
    # Comparison on uncertified UNSAT is diagnostic ONLY; verified PAR2 is separate.
    reference_leaders=collections.Counter()
    for (sha,rep),arm_results in grouped.items():
        v=arm_results
        fastest=min(ARMS,key=lambda ar:v[ar]["PAR2_reported_s"])
        if fastest in ("KISSAT","CMS"):
            reference_leaders[(v[fastest]["category"],fastest)]+=1
    result=dict(stage=a.stage,source_count=len(manifest),families=20,
        source_original_satlib=25,trials=2000,repeats=2,one_cpu=True,
        index_range=[95,99],
        blind_first_seen=True,replay_nonblind=False,
        claims="only SAT witness or independently checked original GF2 contradiction credited in verified PAR2",
        summary=roll,
        relative_verified_PAR2_A_over_C6=round(roll["A"]["PAR2_verified_s"]/
           max(roll["C6_KEEP"]["PAR2_verified_s"],1e-10),6),
        relative_reported_PAR2_KISSAT_over_C6=round(roll["KISSAT"]["PAR2_reported_s"]/
           max(roll["C6_KEEP"]["PAR2_reported_s"],1e-10),6),
        relative_reported_PAR2_C6_over_C7=round(roll["C6_KEEP"]["PAR2_reported_s"]/
           max(roll["C7_ADAPT"]["PAR2_reported_s"],1e-10),6),
        relative_reported_PAR2_FAST_Q8_over_FAST_Q16=round(
            roll["C8_FAST_Q8"]["PAR2_reported_s"]/
            max(roll["C8_FAST_Q16"]["PAR2_reported_s"],1e-10),6),
        relative_reported_PAR2_GATE_Q8_over_GATE_Q16=round(
            roll["C8_GATE_Q8"]["PAR2_reported_s"]/
            max(roll["C8_GATE_Q16"]["PAR2_reported_s"],1e-10),6),
        relative_reported_PAR2_FAST_Q8_over_GATE_Q8=round(
            roll["C8_FAST_Q8"]["PAR2_reported_s"]/
            max(roll["C8_GATE_Q8"]["PAR2_reported_s"],1e-10),6),
        relative_verified_PAR2_C7_over_GATE_Q16=round(
            roll["C7_ADAPT"]["PAR2_verified_s"]/
            max(roll["C8_GATE_Q16"]["PAR2_verified_s"],1e-10),6),
        reference_diagnostic_wins=sorted([dict(category=c,arm=arm,count=count) for
            (c,arm),count in reference_leaders.items()],key=lambda x:-x["count"])[:15],
        policy_by_family=family_policy,sqlite_bytes=dbbytes,
        sql_trials_total=conn.execute("SELECT count(*) FROM trial").fetchone()[0],
        sql_events_total=conn.execute("SELECT count(*) FROM decision_event").fetchone()[0])
    (ROOT/"policy_next.json").write_text(json.dumps(dict(stage=a.stage,
        policy_by_family=family_policy),sort_keys=True,indent=2))
    (ROOT/f"ATLAS18_STAGE{a.stage}_SUMMARY.json").write_text(json.dumps(result,sort_keys=True,indent=2))
    print("ATLAS18_MERGED "+json.dumps(result,sort_keys=True),flush=True)
    conn.close()
if __name__=="__main__":main()
