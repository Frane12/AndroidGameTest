#!/usr/bin/env python3
"""ATLAS39 source-disjoint paired SHA audit: original SAT verified, UNSAT unverified."""
import collections,hashlib,json,pathlib
root=pathlib.Path("audits")
cohorts=(("regression",10),("extension",6),("hard",10))
allsha=set()
allrows=[]
for cohort,n in cohorts:
 rows=[];sha=set()
 for shard in (0,1):
    folder=root/f"ATLAS39-{cohort}-{shard}"
    matches=list(folder.rglob(f"result_{shard}.json"))
    assert len(matches)==1,(cohort,shard,[str(p) for p in matches])
    data=json.loads(matches[0].read_text())
    assert data["cohort"]==cohort and data["one_logical_CPU"]
    assert len(data["rows"])==(n//2)*2*5
    shas={x["sha256"] for x in data["rows"]}
    assert len(shas)==n//2 and not sha.intersection(shas)
    sha|=shas;rows.extend(data["rows"])
    print("ATLAS39_SHARD "+json.dumps(dict(cohort=cohort,shard=shard,
          sha=len(shas),trials=len(data["rows"]),summary=data["summary"]),
          sort_keys=True),flush=True)
 assert len(sha)==n and not allsha.intersection(sha)
 allsha|=sha
 assert len(rows)==n*2*5
 by=collections.defaultdict(dict)
 for r in rows:
    assert r["status"] in ("SAT_VERIFIED","UNSAT_UNVERIFIED","UNKNOWN")
    assert not r["independent_UNSAT_proof_verified"]
    assert (r["status"]=="SAT_VERIFIED")==r["original_SAT_witness_verified"]
    assert r["PAR2_verified_s"]>=r["PAR2_reported_s"]-1e-5
    by[(r["sha256"],r["rep"])][r["arm"]]=r
 assert all(set(v)=={"V23_C7_STABLE","A36_75","A39_SHADOW","A39_PROTECT","KISSAT"} for v in by.values())
 sums={}
 for arm in ("V23_C7_STABLE","A36_75","A39_SHADOW","A39_PROTECT","KISSAT"):
    rr=[r for r in rows if r["arm"]==arm]
    t=lambda field:sum(r["telemetry"].get(field,0) for r in rr)
    sums[arm]=dict(solved=sum(r["status"]!="UNKNOWN" for r in rr),
      sat_verified=sum(r["status"]=="SAT_VERIFIED" for r in rr),
      unsat_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in rr),
      PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rr),6),
      PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in rr),6),
      E2E_s=round(sum(r["E2E_s"] for r in rr),6),
      conflicts=t("conflicts"),propagations=t("propagations"),
      watch_visits=t("watch_visits"),deleted=t("atlas15_deleted"),
      recent_reason_uses=t("atlas39_reason_uses"),
      repeated_reason_uses=t("atlas39_reuses"),
      recent_clause_candidates=t("atlas39_recent"),
      rank_reassignments=t("atlas39_changed_rank"),
      reduction_events=t("atlas39_reduction_events"),
      compaction_remaps=t("atlas39_compaction_remaps"),
      metadata_peak_bytes=max(r["telemetry"]["atlas39_metadata_bytes"] for r in rr))
 print("ATLAS39_COHORT_AUDIT "+json.dumps(dict(cohort=cohort,sources=n,
      trials=len(rows),global_blind=False,summary=sums,
      C39_protect_minus_A36_verified_par2=round(sums["A39_PROTECT"]["PAR2_verified_s"]-
                                                 sums["A36_75"]["PAR2_verified_s"],6),
      C39_protect_minus_A36_reported_par2=round(sums["A39_PROTECT"]["PAR2_reported_s"]-
                                                 sums["A36_75"]["PAR2_reported_s"],6)),
      sort_keys=True),flush=True)
 allrows.extend(rows)
assert len(allsha)==26 and len(allrows)==260
print("ATLAS39_AUDIT_PASS "+json.dumps(dict(sources=26,trials=260,
    hard_sources=10,one_cpu=True,sha_disjoint=True,
    original_sat_witness_checked=True,independent_unsat_LRAT=False,
    source_prospective_vs_atlas37_not_globally_blind=True),sort_keys=True),flush=True)
