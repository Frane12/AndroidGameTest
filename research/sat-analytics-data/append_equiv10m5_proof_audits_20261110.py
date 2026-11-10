#!/usr/bin/env python3
"""Append EQUIV10M5 (50 original 2024-25 SAT E2E) and two later proof audits
to already VERIFIED full-core + MRE + nine-run 57050-attempt SQLite.
Never rewrite/fix old trials, frozen V15.3.1 tables, nor the prior SQL artifact.
UNSAT with cross-backend agreement is not independent LRAT, while EQUIV11
CMS XLRUP checked independently by CakeML is recorded as a distinct proof.
"""
import argparse,hashlib,json,math,pathlib,shutil,sqlite3
RUN=42729709584
PROOF_RUNS={"equiv10p512":42728822870,"equiv11":42729025702}
CORE={"datasets":231,"formulas":2979,"attempts":53330}
OLD={"mre_audit_attempts":1892,"sat_recent_attempts":1828,
     "mre_audit_runs":8,"sat_recent_runs":9}
SHA_CHARS=set("0123456789abcdef")
def need(ok,reason):
 if not ok:raise RuntimeError("DRNAS_SQL_LATEST_FAIL_CLOSED "+str(reason))
def j(path):return json.loads(pathlib.Path(path).read_text())
def digest(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def jsonhash(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def verify_sha(x):return isinstance(x,str) and len(x)==64 and all(c in SHA_CHARS for c in x)
def find_data(root,predicate):
 vals=[]
 for path in sorted(pathlib.Path(root).rglob("*.json")):
  try:x=j(path)
  except (ValueError,UnicodeError):continue
  if isinstance(x,dict) and predicate(x):vals.append((path,x))
 need(len(vals)==1,"expected a single matching JSON report in "+str(root)+
      " found "+str([str(p) for p,_ in vals]))
 return vals[0]
def all_trials(root):
 files=sorted(pathlib.Path(root).rglob("shard-*.json"))
 need(len(files)==5,"five original EQUIV10M5 shards required")
 rows=[]
 for f in files:
  x=j(f)
  need(type(x)==list and len(x)==10,"incorrect shard trials "+str(f))
  rows+=x
 return files,rows
def checks(db,expected):
 need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite corrupt")
 for table,n in expected.items():
  need(db.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]==n,
       "immutable prior table changed "+table)
def source_solved(raw):
 return int(raw["status"]!="TIMEOUT")
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--baseline",type=pathlib.Path,required=True)
 ap.add_argument("--inputs",type=pathlib.Path,required=True)
 ap.add_argument("--out",type=pathlib.Path,required=True)
 a=ap.parse_args()
 a.out.mkdir(parents=True,exist_ok=True)
 need(a.baseline.is_file(),"verified 57050 SQL baseline missing")
 before={**CORE,**OLD}
 orig=sqlite3.connect("file:"+str(a.baseline.resolve())+"?mode=ro",uri=True)
 try:checks(orig,before)
 finally:orig.close()
 dest=a.out/"sat_analytics_refresh_20261110_latest.sqlite"
 if dest.exists():dest.unlink()
 shutil.copy2(a.baseline,dest)
 db=sqlite3.connect(dest)
 try:
  db.execute("PRAGMA busy_timeout=30000")
  db.execute("PRAGMA foreign_keys=ON")
  checks(db,before)
  audit_path,report=find_data(a.inputs/"equiv10m5",
     lambda x:x.get("protocol","").startswith("DRNAS-EQUIV10M5-") and
              "scores" in x and x.get("trial_count")==50)
  need(report["cap_s"]==15.0 and report["original_source_count"]==5 and
       report["independent_UNSAT_LRAT"] is False and
       report["one_logical_CPU"] is True,
       "EQUIV10M5 report scope/cap changed")
  files,raw=all_trials(a.inputs/"equiv10m5")
  need(len(raw)==50,"not 50 attempts")
  allowed=set(report["scores"])
  need(len(allowed)==5 and "kissat1" in allowed,"5 known arms missing")
  consensus=set(report["strict_UNSAT_agreement_SHA"])
  need(len(consensus)==1 and all(verify_sha(h) for h in consensus),
       "source-level original UNSAT agreement frozen SHA invalid")
  pairs=set()
  shas=set()
  parsed=[]
  for row in raw:
   sha=row.get("sha256") or row.get("original_sha256")
   arm=row.get("arm");rep=row.get("rep")
   status=row.get("status")
   need(verify_sha(sha) and arm in allowed and rep in (0,1),
        "foreign SHA/arm/repeat in original source trial")
   need(status in ("SAT","UNSAT","TIMEOUT") and
        float(row["cap_s"])==15.0 and
        row.get("UNSAT_independent_LRAT") is False and
        row.get("original_sha256_verified") is True and
        type(row.get("pinned_cpu"))==int,
        "source SHA / independent LRAT / oneCPU protocol changed")
   need(row.get("protocol")==report["protocol"],"raw/report protocol disagreement")
   key=(sha,arm,rep)
   need(key not in pairs,"duplicate EQUIV10M5 trial")
   pairs.add(key);shas.add(sha)
   wall=float(row["wall_E2E_s"])
   need(math.isfinite(wall) and 0<=wall<=15.1,"bad original E2E time")
   sat=bool(row["SAT_original_witness_verified"])
   if status=="SAT":need(sat,"SAT original witness not verified")
   if status=="UNSAT":need(sha in consensus,"UNSAT without cross solver SHA agreement")
   par2=30.0 if status=="TIMEOUT" else wall
   cpu=float(row.get("child_CPU_s",0))
   need(cpu>=0 and math.isfinite(cpu),"bad CPU")
   rawtxt=json.dumps(row,sort_keys=True,separators=(",",":"))
   parsed.append((sha,arm,rep,status,wall,par2,int(sat),int(status=="UNSAT"),
       cpu,row.get("seed_base"),row["gbd"],rawtxt))
  need(len(shas)==5 and len(pairs)==50,"incomplete exact five original SHA roster")
  for sha in shas:
   for mode in allowed:
    need({p[2] for p in parsed if p[0]==sha and p[1]==mode}=={0,1},
         "repetitions not paired on source SHA")
  audited={}
  for mode,s in report["scores"].items():
   q=[r for r in parsed if r[1]==mode]
   need(len(q)==int(s["n"])==10 and
        sum(r[6] for r in q)==int(s["SAT_original_model_verified"]) and
        sum(r[7] for r in q)==int(s["UNSAT_crosssolver_agreed_no_LRAT"]) and
        sum(source_solved({"status":r[3]}) for r in q)==int(s["solved"]),
        "audit solved/SAT/UNSAT disagree "+mode)
   p=sum(r[5] for r in q)
   need(abs(p-float(s["PAR2_s"]))<0.015,"PAR2 sum disagrees signed audit "+mode+
        " "+str((p,s["PAR2_s"])))
   audited[mode]=dict(solved=int(s["solved"]),PAR2_s=float(s["PAR2_s"]),
      SAT_verified=int(s["SAT_original_model_verified"]),
      UNSAT_crosssolver_no_LRAT=int(s["UNSAT_crosssolver_agreed_no_LRAT"]))
  report_sha=digest(audit_path)
  db.execute("INSERT INTO sat_recent_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(
    RUN,"equiv10m5",RUN,report["protocol"],"reference-conditioned five frozen 2024-25 SHA, not globally blind",
    5,5,50,"five previously frozen original SHA; 1 easy + 4 medium",
    "original SAT witness verified; source-agreed UNSAT no independent LRAT",
    1,report_sha))
  for f in files:
   db.execute("INSERT INTO sat_recent_artifact_lineage VALUES (?,?,?,?)",
              (RUN,f.name,digest(f),f.stat().st_size))
  for sha in sorted(shas):
   case=next(r[10] for r in parsed if r[0]==sha)
   db.execute("INSERT OR IGNORE INTO sat_recent_originals VALUES(?,?,?)",
              (sha,case,RUN))
   db.execute("INSERT INTO sat_recent_run_origins VALUES (?,?,?,?)",
              (RUN,sha,"holdout",case))
  for sha,mode,rep,status,wall,par2,sat,unsat,cpu,seed,case,rawtxt in parsed:
   db.execute("INSERT INTO sat_recent_attempts VALUES ("+
              ",".join("?"*24)+")",(
     RUN,sha,"holdout",mode,rep,case,status,status,wall,par2,cpu,15.,
     sat,unsat,0,1,1,seed,None,None,None,None,
     hashlib.sha256(rawtxt.encode()).hexdigest(),rawtxt))
  ref=audited["kissat1"]["PAR2_s"]
  for mode,s in audited.items():
   db.execute("INSERT INTO sat_recent_scores VALUES(?,?,?,?,?,?,?,?,?,?)",(
    RUN,"holdout",mode,10,s["solved"],s["SAT_verified"],
    s["UNSAT_crosssolver_no_LRAT"],s["PAR2_s"],
    round(ref/s["PAR2_s"],6),report_sha))
  db.executescript("""
  CREATE TABLE IF NOT EXISTS sat_recent_proof_audits (
   proof_run_id INTEGER PRIMARY KEY, source_sha256 TEXT NOT NULL,
   certification_status TEXT NOT NULL,
   independently_certified INTEGER NOT NULL,
   independent_checker TEXT NOT NULL, generator TEXT NOT NULL,
   proof_format TEXT, proof_bytes INTEGER, proof_sha256 TEXT,
   source_SAT_claim TEXT NOT NULL, evidence_json_sha256 TEXT NOT NULL,
   audit_json TEXT NOT NULL
  );""")
  proof_meta=[]
  for name,run in PROOF_RUNS.items():
   proof_path,proof=find_data(a.inputs/name,
     lambda x: x.get("certification_status") is not None and
          (x.get("source_original_sha256") or x.get("original_sha256")) is not None)
   sha=proof.get("source_original_sha256") or proof.get("original_sha256")
   need(verify_sha(sha) and sha=="327bfcaa1933d1c2b293f90f5761bfb25448c577d4a6958b962d4a09a1c88b7a",
        "wrong independently audited source original SHA")
   if name=="equiv11":
    cert=bool(proof.get("UNSAT_certified_by_independent_proof"))
    cake=proof.get("independent_cake_result",{})
    need(cert and proof["certification_status"]=="CERTIFIED_ORIGINAL_UNSAT_BY_CMS_XLRUP" and
         cake.get("return_code")==0 and
         "VERIFIED UNSAT" in cake.get("stdout_tail","") and
         proof.get("original_sha_verified") is True and
         verify_sha(proof.get("proof_sha256","")),"original XLRUP CakeML proof not verified")
    checker="CakeML independent binary XLRUP checker"
    generator="CryptoMiniSat 5.17"
    kind="binary XLRUP";size=int(proof["proof_bytes"]);proof_digest=proof["proof_sha256"]
   else:
    cert=bool(proof.get("independent_LRAT_verified"))
    need(not cert and proof["certification_status"]=="UNVERIFIED",
         "cannot classify native-only UNSAT as independently proved")
    checker=str(proof.get("checker") or "DRAT-LRAT attempted without certificate")
    generator="Kissat 4.0.4 and CaDiCaL 3.0.1 truncated at 512 MiB"
    kind="DRAT attempt, no accepted proof";size=None;proof_digest=None
   proof_payload=json.dumps(proof,sort_keys=True,separators=(",",":"))
   db.execute("INSERT INTO sat_recent_proof_audits VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(
      run,sha,proof["certification_status"],int(cert),checker,generator,
      kind,size,proof_digest,"original native UNSAT claim under crosscheck",
      digest(proof_path),proof_payload))
   proof_meta.append(dict(run_id=run,certified=cert,
     original_sha256=sha,certification_status=proof["certification_status"]))
  need(len(proof_meta)==2 and sum(v["certified"] for v in proof_meta)==1,
       "missing proof success/failure contrast")
  db.commit()
  checks(db,{**before,"sat_recent_runs":10,"sat_recent_attempts":1878,
             "sat_recent_proof_audits":2})
  db.execute("ATTACH DATABASE ? AS frozen",(str(a.baseline),))
  for tab in ("datasets","formulas","attempts","mre_audit_attempts",
              "sat_recent_attempts","sat_recent_runs"):
   left=db.execute(f"""SELECT COUNT(*) FROM (
      SELECT * FROM frozen.{tab} EXCEPT SELECT * FROM main.{tab})""").fetchone()[0]
   need(left==0,"old SQL evidence mutated "+tab)
  db.execute("DETACH DATABASE frozen")
  summary=dict(protocol="DRNAS-SAT-20261110-57100-PLUS-INDEPENDENT-XLRUP-v1",
    historical_core=CORE,MRE_attempts=1892,
    before_E2E_attempts=1828,new_E2E_attempts=50,total_E2E_recent=1878,
    cumulative_attempt_rows=57100,run_count=10,
    added_equiv10m5=audited,proof_audits=proof_meta,
    historical_and_prior_SQL_unchanged=True,independent_UNSAT_XLRUP_count=1,
    native_has_not_produced_this_certificate=True,
    globally_blind=False,no_general_speedup_claim=True)
  (a.out/"latest_refresh_audit.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
  (a.out/"sqlite_sha256.txt").write_text(digest(dest)+"  "+dest.name+"\n")
  print("DRNAS_SQL_LATEST_SUCCESS",json.dumps(summary,sort_keys=True),flush=True)
 finally:db.close()
if __name__=="__main__":main()
