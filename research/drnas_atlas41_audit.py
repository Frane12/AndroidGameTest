#!/usr/bin/env python3
"""ATLAS41 audit for one isolated decision-tree branch. Strict original SHA pairs."""
import json, pathlib, collections
ROOT=pathlib.Path("audits")
ARMS=("A36_75","A39_PROTECT","A41_GUARD","A41_DECAY","KISSAT")
expected={"regression":10,"extension":6,"hard":10}
rows=[];global_sha=set()
for cohort,count in expected.items():
    sha=set()
    for shard in (0,1):
        candidates=list((ROOT/f"ATLAS41-{cohort}-{shard}").rglob(f"result_{shard}.json"))
        assert len(candidates)==1,(cohort,shard,[str(p) for p in candidates])
        d=json.loads(candidates[0].read_text())
        rr=d["rows"]
        assert len(rr)==(count//2)*len(ARMS)*2,(cohort,shard,len(rr))
        ss={r["sha256"] for r in rr}
        assert len(ss)==count//2 and not(ss&sha)
        assert all(r["cohort"]==cohort for r in rr)
        sha|=ss
        rows.extend(rr)
    assert len(sha)==count and not sha&global_sha
    global_sha|=sha
assert len(global_sha)==26 and len(rows)==260
pairs=collections.defaultdict(dict)
for r in rows:
    k=(r["sha256"],r["rep"])
    assert r["arm"] not in pairs[k]
    pairs[k][r["arm"]]=r
    assert r["status"]!="SAT_VERIFIED" or r["original_SAT_witness_verified"]
    assert not r["independent_UNSAT_proof_verified"]
    if r["arm"] in ("A41_GUARD","A41_DECAY") and r["status"]!="UNKNOWN":
        assert r["telemetry"]["atlas39_mode"]==(3 if r["arm"]=="A41_GUARD" else 4)
        assert r["telemetry"]["atlas36_quota_pct"]==75
assert len(pairs)==52
assert all(set(d)==set(ARMS) for d in pairs.values())
for d in pairs.values():
    assert not (any(x["status"]=="SAT_VERIFIED" for x in d.values())
                and any(x["status"]=="UNSAT_UNVERIFIED" for x in d.values()))
for cohort in expected:
    sums={}
    for arm in ARMS:
        rr=[r for r in rows if r["cohort"]==cohort and r["arm"]==arm]
        sums[arm]=dict(trials=len(rr),
           reported_PAR2_s=round(sum(x["PAR2_reported_s"] for x in rr),6),
           verified_PAR2_s=round(sum(x["PAR2_verified_s"] for x in rr),6),
           E2E_s=round(sum(x["E2E_s"] for x in rr),6),
           sat_verified=sum(x["status"]=="SAT_VERIFIED" for x in rr),
           unsat_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" for x in rr),
           timeouts=sum(x["status"]=="UNKNOWN" for x in rr),
           conflicts=sum(x["telemetry"]["conflicts"] for x in rr),
           deleted=sum(x["telemetry"]["atlas15_deleted"] for x in rr),
           watch_visits=sum(x["telemetry"]["watch_visits"] for x in rr),
           changed_rank=sum(x["telemetry"]["atlas39_changed_rank"] for x in rr),
           metadata_bytes=max(x["telemetry"]["atlas39_metadata_bytes"] for x in rr))
    print("ATLAS41_COHORT_AUDIT "+json.dumps(dict(cohort=cohort,summary=sums),sort_keys=True),flush=True)
all_summary={}
for arm in ARMS:
    rr=[r for r in rows if r["arm"]==arm]
    all_summary[arm]=dict(reported_PAR2_s=round(sum(x["PAR2_reported_s"] for x in rr),6),
       verified_PAR2_s=round(sum(x["PAR2_verified_s"] for x in rr),6),
       sat_verified=sum(x["status"]=="SAT_VERIFIED" for x in rr),
       unsat_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" for x in rr),
       timeouts=sum(x["status"]=="UNKNOWN" for x in rr),
       changed_rank=sum(x["telemetry"]["atlas39_changed_rank"] for x in rr))
print("ATLAS41_AUDIT "+json.dumps(dict(sha=26,trials=260,arms=all_summary),sort_keys=True),flush=True)
print("ATLAS41_AUDIT_PASS original_SHA=true one_CPU=true independent_UNSAT_LRAT=false",flush=True)
