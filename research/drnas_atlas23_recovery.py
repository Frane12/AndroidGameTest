#!/usr/bin/env python3
"""ATLAS23 frozen-source paired CDCL recovery: same 12 SHA as ATLAS22.
Only recovery arms are new; baseline policy and sources are unchanged.
"""
import json,pathlib,sys
sys.path.insert(0,"research")
import drnas_atlas22_mid_hard as S
import drnas_atlas21_official as B
import drnas_atlas_wide500 as W
B.CAP=12.0;B.OUT=pathlib.Path("mre_atlas23");B.OUT.mkdir(exist_ok=True)
B.ARMS=("A","C6_KEEP","C7_ADAPT","C23_QUOTA","C23_RECENT","KISSAT","CMS")
def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument("--smoke",action="store_true");a=p.parse_args()
 corp=W.source_corpus(limit=10);sources=[]
 for family in S.FAMILIES:
  for idx in range(6,10):
   n,clauses,sha,entry=corp[family][idx]
   raw=W.canonical(n,clauses)
   path=B.OUT/f"{family}_{idx}.cnf";path.write_bytes(raw)
   sources.append(dict(id=len(sources),sha256=sha,archive_entry=entry,
    family=family,source_kind="SATLIB_normalized_original",bytes=len(raw),path=str(path)))
 assert len(sources)==12 and len({s["sha256"] for s in sources})==12
 (B.OUT/"manifest.json").write_text(json.dumps(sources,indent=2))
 print("ATLAS23_SOURCES "+json.dumps(sources),flush=True)
 rows=[]
 for s in (sources[:1] if a.smoke else sources):
  for rep in range(1 if a.smoke else 2):
   statuses=set()
   for arm in B.ARMS:
    r=B.run(s,arm,rep);rows.append(r)
    print("ATLAS23_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    if r["status"]!="UNKNOWN":statuses.add(r["status"])
   assert not ("SAT_VERIFIED" in statuses and "UNSAT_UNVERIFIED" in statuses)
 (B.OUT/("smoke.json" if a.smoke else "pilot.json")).write_text(json.dumps(
  dict(sources=sources[:1] if a.smoke else sources,rows=rows,cap_s=B.CAP,
  cohort="SATLIB_ATLAS22_SHA_replay",UNSAT_independent_LRAT=False),indent=2))
 summary={arm:dict(SAT_verified=sum(r["arm"]==arm and r["status"]=="SAT_VERIFIED" for r in rows),
  UNSAT_unverified=sum(r["arm"]==arm and r["status"]=="UNSAT_UNVERIFIED" for r in rows),
  PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in rows if r["arm"]==arm),4),
  PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rows if r["arm"]==arm),4),
  E2E_s=round(sum(r["E2E_s"] for r in rows if r["arm"]==arm),4),
  deleted=sum(r["telemetry"]["atlas15_deleted"] for r in rows if r["arm"]==arm),
  conflicts=sum(r["telemetry"]["conflicts"] for r in rows if r["arm"]==arm),
  watch_visits=sum(r["telemetry"]["watch_visits"] for r in rows if r["arm"]==arm))
  for arm in B.ARMS}
 print("ATLAS23_FINAL "+json.dumps(dict(smoke=a.smoke,trials=len(rows),summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":main()
