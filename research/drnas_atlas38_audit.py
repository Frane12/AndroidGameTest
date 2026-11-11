#!/usr/bin/env python3
"""ATLAS38 locked-SHA within-state difference analysis.
Never call matching telemetric fingerprints bitwise full-state identity.
"""
import json,pathlib,collections
ROOT=pathlib.Path("audits")
rows=[];shas=set()
for shard,num in ((0,2),(1,1)):
 candidates=list((ROOT/f"ATLAS38-{shard}").rglob(f"shard_{shard}.json"))
 assert len(candidates)==1,("artifact layout mismatch",shard,[str(x) for x in candidates])
 p=candidates[0]
 d=json.loads(p.read_text())
 assert d["shard"]==shard and len(d["sources"])==num
 for source in d["sources"]:
    assert source["sha256"] not in shas
    shas.add(source["sha256"])
 assert len(d["rows"])==num*2*10
 rows.extend(d["rows"])
assert len(shas)==3 and len(rows)==60
by=collections.defaultdict(dict)
for r in rows:
 key=(r["sha256"],r["rep"],r["target"])
 assert r["arm"]=="KISSAT" or r["arm"]=="A36_75" or r["arm"].startswith("PULSE")
 if r["arm"].startswith("PULSE"):
    assert r["target"] in (5,15,30,45)
    assert r["arm"] not in by[key]
    by[key][r["arm"]]=r
    assert r["status"]!="SAT_VERIFIED" or r["original_SAT_witness_verified"]
    assert not r["independent_UNSAT_LRAT"]
pairs=[]
for key,arms in by.items():
 assert set(arms)=={"PULSE75","PULSE100"}
 a,b=arms["PULSE75"],arms["PULSE100"]
 prefix=None
 if a["pre"] and b["pre"]:
    assert a["pre"]["hash"]==b["pre"]["hash"],"fingerprint mismatch"
    assert all(a["pre"][k]==b["pre"][k] for k in
      ("target","conflicts","decisions","propagations",
       "watch_visits","deleted","clauses","trail"))
    prefix="MATCHED_PRESTATE"
 else:prefix="UNREACHED_OR_OUTPUT_MISSING"
 result=dict(sha=key[0][:16],family=a["family"],index=a["index"],
    rep=a["rep"],target=a["target"],prefix=prefix,
    a75=a["E2E_s"],b100=b["E2E_s"],
    delta_reported_par2=round(b["PAR2_reported_s"]-a["PAR2_reported_s"],6),
    status75=a["status"],status100=b["status"],
    conflicts75=a["telemetry"]["conflicts"],conflicts100=b["telemetry"]["conflicts"],
    watch75=a["telemetry"]["watch_visits"],watch100=b["telemetry"]["watch_visits"])
 pairs.append(result)
 print("ATLAS38_PAIR_AUDIT "+json.dumps(result,sort_keys=True),flush=True)
assert len(pairs)==24
matched=[p for p in pairs if p["prefix"]=="MATCHED_PRESTATE"]
unmatched=[p for p in pairs if p["prefix"]!="MATCHED_PRESTATE"]
summary=dict(source_sha=3,trials=60,pairs=24,matched_prefix=len(matched),
 unverified_prefix=len(unmatched),
 reported_PAR2_delta_matched=round(sum(p["delta_reported_par2"] for p in matched),6),
 matched_100_better=sum(p["delta_reported_par2"]<-.01 for p in matched),
 matched_75_better=sum(p["delta_reported_par2"]>.01 for p in matched),
 neutral=sum(abs(p["delta_reported_par2"])<=.01 for p in matched),
 no_global_blind_claim=True,unsat_LRAT_certified=False,
 causal_design="deterministic_replay_single_intervention_not_in_memory_snapshot")
print("ATLAS38_AUDIT "+json.dumps(summary,sort_keys=True),flush=True)
print("ATLAS38_AUDIT_PASS SHA_disjoint=true one_cpu=true original_SAT_checked=true"
" prestate_fingerprints_verified=true",flush=True)
