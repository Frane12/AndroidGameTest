#!/usr/bin/env python3
"""ATLAS22 medium-hard SATLIB originals: 3 families x 4 sources, 6 arms x 2 reps.
Source-frozen by archive SHA. No claims of blindness or UNSAT certification.
"""
import hashlib,json,pathlib,sys
sys.path.insert(0,"research")
import drnas_atlas_wide500 as W
import drnas_atlas21_official as B
B.CAP=12.0
B.OUT=pathlib.Path("mre_atlas22");B.OUT.mkdir(exist_ok=True)
FAMILIES=("uf250-1065","uuf250-1065","flat200-479")
def main():
 import argparse
 p=argparse.ArgumentParser();p.add_argument("--smoke",action="store_true");args=p.parse_args()
 corp=W.source_corpus(limit=10)
 sources=[]
 for family in FAMILIES:
  for idx in range(6,10):
   n,clauses,sha,entry=corp[family][idx]
   raw=W.canonical(n,clauses)
   assert hashlib.sha256(raw).hexdigest()==sha
   path=B.OUT/f"{family}_{idx}.cnf";path.write_bytes(raw)
   sources.append(dict(id=len(sources),sha256=sha,archive_entry=entry,
    family=family,source_kind="SATLIB_normalized_original",bytes=len(raw),path=str(path)))
 assert len(sources)==12 and len({s["sha256"] for s in sources})==12
 (B.OUT/"manifest.json").write_text(json.dumps(sources,indent=2))
 print("ATLAS22_SOURCES "+json.dumps(sources),flush=True)
 rows=[]
 for s in (sources[:1] if args.smoke else sources):
  for rep in range(1 if args.smoke else 2):
   statuses=set()
   for arm in B.ARMS:
    r=B.run(s,arm,rep);rows.append(r)
    print("ATLAS22_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    if r["status"]!="UNKNOWN":statuses.add(r["status"])
   assert not ("SAT_VERIFIED" in statuses and "UNSAT_UNVERIFIED" in statuses)
 out=dict(sources=sources[:1] if args.smoke else sources,rows=rows,cap_s=B.CAP,
  cohort="SATLIB_mid_hard_12",UNSAT_independent_LRAT=False)
 (B.OUT/("smoke.json" if args.smoke else "pilot.json")).write_text(json.dumps(out,indent=2))
 summary={arm:dict(SAT_verified=sum(r["arm"]==arm and r["status"]=="SAT_VERIFIED" for r in rows),
  UNSAT_unverified=sum(r["arm"]==arm and r["status"]=="UNSAT_UNVERIFIED" for r in rows),
  PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in rows if r["arm"]==arm),4),
  PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rows if r["arm"]==arm),4),
  E2E_s=round(sum(r["E2E_s"] for r in rows if r["arm"]==arm),4)) for arm in B.ARMS}
 print("ATLAS22_FINAL "+json.dumps(dict(smoke=args.smoke,trials=len(rows),summary=summary),sort_keys=True),flush=True)
if __name__=="__main__":main()
