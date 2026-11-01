#!/usr/bin/env python3
"""Ingest frozen official 2025/2026 R5 paired CSV into V15.3.1 analytics without modifying solver."""
import argparse,csv,hashlib,json,sqlite3
from collections import defaultdict
from pathlib import Path
import v1531_analytics_db as base

RUN="41334526696"
COMMIT="df74b859e38742e1e05f6848798bcebceb23d426"
DATASET="DRNAS-R5-Official-2025-2026-Measured"
CAP=60.0
MODES={"original":"kissat","stable_v1531":"v1531",
       "monitor":"r5_monitor","r4_restart20":"r4_restart20",
       "r5_multisignal":"r5_multisignal","forced_restart25":"forced_restart25"}

def optional_int(x):
 try:
  if str(x).strip().lower() in ("true","false"): return int(str(x).strip().lower()=="true")
  return int(x) if str(x).strip() else None
 except (TypeError,ValueError): return None

def optional_float(x):
 try: return float(x) if str(x).strip() else None
 except (TypeError,ValueError): return None

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--input",type=Path,required=True)
 ap.add_argument("--out",type=Path,required=True)
 args=ap.parse_args()
 files=[args.input/f"r5_shard_{i}"/"measurements.csv" for i in range(4)]
 if not all(x.is_file() for x in files): raise SystemExit("R5 shards missing: "+repr([str(x) for x in files if not x.is_file()]))
 rows=[]
 for f in files:
  with f.open(newline="") as h: part=list(csv.DictReader(h))
  if not part: raise SystemExit("Empty R5 shard: "+str(f))
  rows+=part
 cases=defaultdict(list)
 for r in rows:
  if r["mode"] not in MODES: raise ValueError("Unexpected R5 policy")
  if r["status"] not in ("SAT","UNSAT","TIMEOUT"): raise ValueError("Unexpected status "+r["status"])
  if int(r["year"]) not in (2025,2026): raise ValueError("Unexpected year")
  if len(r["cnf_sha256"])!=64: raise ValueError("Missing formula SHA")
  key=(r["year"],r["index"],r["cnf_sha256"])
  cases[key].append(r)
 if not (1 <= len(cases) <= 64):raise ValueError(f"Expected 1..64 measured formulas; got {len(cases)}")
 for key,group in cases.items():
  got={(int(x["repeat"]),x["mode"]) for x in group}
  expected={(repeat,mode) for repeat in range(2) for mode in MODES}
  if got!=expected or len(group)!=12:raise ValueError("Missing or duplicate paired R5 attempts "+str(key))
  if len({x["expected"] for x in group})!=1:raise ValueError("Contradictory labels "+str(key))
  if any(x["status"] in ("SAT","UNSAT") and x["expected"] in ("SAT","UNSAT")
         and x["status"]!=x["expected"] for x in group):raise ValueError("Official label mismatch "+str(key))
 db=sqlite3.connect(args.out/"sat_analytics.sqlite")
 try:
  db.execute("BEGIN")
  if db.execute("SELECT 1 FROM datasets WHERE dataset=?",(DATASET,)).fetchone():
   raise ValueError("R5 already ingested: refusing duplicate dataset")
  hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
  db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
    (DATASET,"official_frozen_holdout","Official 2025+2026 source CNFs; frozen candidate pool 64 but only successfully fetched measured cases ingested; unofficial paired R5 replay; UNSAT certificates not independently checked",
     RUN,COMMIT,"github-hosted-ubuntu-24.04; four R5 shards",CAP,
     hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()))
  for (year,index,cnfsha),group in sorted(cases.items()):
   case=f"official_{year}_{index}"
   g=group[0]
   db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",
    (DATASET,case,f"official_{year}",g["expected"],cnfsha,g["gbd_hash"],
     f"satcompetition/{year}/index/{index}",None,None))
   for r in group:
    solver=MODES[r["mode"]]
    status=r["status"];secs=float(r["wall_s"]);par2=float(r["par2_s"])
    if secs<0 or par2<0:raise ValueError("Negative time")
    expected_par2=secs if status in ("SAT","UNSAT") else 2*CAP
    if abs(expected_par2-par2)>0.001:raise ValueError("Inconsistent PAR2 source")
    witness=optional_int(r["sat_witness_verified"])
    if status=="SAT" and witness!=1:raise ValueError("Missing SAT model check")
    # UNKNOWN label for 2025 UNSAT is NOT independently verified.
    verified=1 if (status=="SAT" and witness==1) or (status=="UNSAT" and g["expected"]=="UNSAT") else None
    db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
      (DATASET,case,solver,int(r["repeat"]),secs,status,verified,
       r["mode"],witness,None,par2,None))
    conflict=optional_int(r["early_conflicts"])
    if conflict is not None:
     db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (DATASET,case,solver,int(r["repeat"]),0,None,conflict,
       optional_int(r["early_propagations"]),optional_int(r["early_restarts"]),None,
       optional_float(r["early_lbd_ratio"])))
    endconflict=optional_int(r["final_conflicts"])
    if endconflict is not None:
     db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (DATASET,case,solver,int(r["repeat"]),1,secs,endconflict,
       None,optional_int(r["final_restarts"]),None,None))
  db.commit()
  groups,paired,telemetry=base.analytics(db,args.out)
  plots=base.plot(args.out,paired,telemetry)
  print(json.dumps({"dataset":DATASET,"cases":len(cases),"attempts":len(rows),
                    "groups":len(groups),"paired_rows":len(paired),"telemetry_events":len(telemetry),
                    "charts":plots},indent=2))
 except:
  db.rollback()
  raise
 finally:db.close()

if __name__=="__main__":main()
