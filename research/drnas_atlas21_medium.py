#!/usr/bin/env python3
"""ATLAS21-M: 10 frozen SATLIB medium originals, five families x two.
Distinct medium cohort; not the official 2024 hard cohort, not blind.
"""
import hashlib,json,pathlib,sys
sys.path.insert(0,"research")
import drnas_atlas_wide500 as W
import drnas_atlas21_official as B
B.CAP=10.0
B.OUT=pathlib.Path("mre_atlas21m");B.OUT.mkdir(exist_ok=True)
def main():
 corp=W.source_corpus(limit=2)
 sources=[]
 for family in W.SOURCES:
  for idx,(n,clauses,sha,entry) in enumerate(corp[family]):
   raw=W.canonical(n,clauses)
   assert hashlib.sha256(raw).hexdigest()==sha
   path=B.OUT/f"{family}_{idx}.cnf";path.write_bytes(raw)
   sources.append(dict(id=len(sources),sha256=sha,archive_entry=entry,
    family=family,source_kind="SATLIB_normalized_original",bytes=len(raw),path=str(path)))
 assert len(sources)==10 and len({x["sha256"] for x in sources})==10
 (B.OUT/"manifest.json").write_text(json.dumps(sources,indent=2))
 print("ATLAS21M_SOURCES "+json.dumps(sources),flush=True)
 rows=[]
 for s in sources:
  for rep in range(2):
   outcomes=set()
   for arm in B.ARMS:
    r=B.run(s,arm,rep);rows.append(r)
    print("ATLAS21M_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    if r["status"]!="UNKNOWN":outcomes.add(r["status"])
   assert not ("SAT_VERIFIED" in outcomes and "UNSAT_UNVERIFIED" in outcomes)
 result=dict(sources=sources,rows=rows,cap_s=B.CAP,cohort="SATLIB_medium_10",
  original_archive_sha_verified=True,UNSAT_independent_LRAT=False)
 (B.OUT/"pilot.json").write_text(json.dumps(result,indent=2))
 summary={arm:dict(sat_verified=sum(r["arm"]==arm and r["status"]=="SAT_VERIFIED" for r in rows),
  unsat_unverified=sum(r["arm"]==arm and r["status"]=="UNSAT_UNVERIFIED" for r in rows),
  PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in rows if r["arm"]==arm),4),
  PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rows if r["arm"]==arm),4))
  for arm in B.ARMS}
 print("ATLAS21M_FINAL "+json.dumps(dict(trials=len(rows),summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":main()
