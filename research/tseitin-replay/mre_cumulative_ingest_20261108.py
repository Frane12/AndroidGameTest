#!/usr/bin/env python3
"""DRNAS MRE evidence extension. Append-only companion SQLite, frozen V15.3.1 untouched.

Inputs are the *completed GitHub Actions audit artifact* and every original
source/seed/mode result shard, not excerpts of logs. Fail closed if any
source SHA, run SHA, seed, pair, original SAT witness, independent proof tier,
PAR2 timeout, row count, or report aggregate does not match.
Separate run IDs preserve repeat measurements; unique source hashes are
deduplicated globally without conflating repeated experiments.
"""
from __future__ import annotations
import argparse,collections,csv,gzip,hashlib,json,math,pathlib,re,sqlite3,tempfile,shutil

SPEC = {
 "mre10_dev":dict(run=42509505558,audit=42509505558,sha="aa791ceb5fa1b6b1f24bbda96267da565f2466a0",
     prefix="mre10",shards=8,attempts_per_shard=80,cases=16,reps=4,modes=10,cap=8.0,baseline="N_ext",
     novelty="DEVELOPMENT_REUSED_2021_25",holdout="previously_used"),
 "mre10_repeat":dict(run=42513793922,audit=42513793922,sha="90424bbaf4fab661aabe9e636f9aeda97a56a232",
     prefix="mre10",shards=8,attempts_per_shard=80,cases=16,reps=4,modes=10,cap=8.0,baseline="N_ext",
     novelty="EXACT_SAME_DEVELOPMENT_SHAS_REPEAT",holdout="repeated"),
 "mre10b_external":dict(run=42511332725,audit=42511332725,sha="5ed0cf1f37636884fd4a5b0c19b8e83ddd52e0ff",
     prefix="mre10b",shards=6,attempts_per_shard=24,cases=12,reps=3,modes=4,cap=15.0,baseline="N_ext",
     novelty="NEW_RELATIVE_TO_TRACKED_MRE10_EXTERNAL_CADICAL_SELECTED",holdout="reference_conditioned"),
 "mre6g_certified":dict(run=42505145407,audit=42506460983,sha="ed9a81e48da963a6fb44722a87dec4e12b6958b4",
     prefix="mre6g",shards=3,attempts_per_shard=20,cases=6,reps=2,modes=5,cap=35.0,baseline="native_no_xor",
     novelty="REUSED_2_AND_REFERENCE_NEW_4",holdout="mixed"),
 "mre6h_fast":dict(run=42507215971,audit=42507215971,sha="cc675c4a45a05c026e958fd03076185c5c4951d0",
     prefix="mre6h",shards=3,attempts_per_shard=20,cases=6,reps=2,modes=5,cap=35.0,baseline="native_no_xor",
     novelty="REUSED_2_AND_REFERENCE_NEW_4",holdout="mixed"),
 "mre6i_gate":dict(run=42509063941,audit=42509063941,sha="a4112d0ea6d51dcdcdff4b2b511ffc22691bacc0",
     prefix="mre6i",shards=4,attempts_per_shard=20,cases=8,reps=2,modes=5,cap=35.0,baseline="native_no_xor",
     novelty="REUSED_2_REFERENCE_NEW_4_SYNTHETIC_2",holdout="mixed"),
}
CORE_COUNTS=(231,2979,53330)
H64=re.compile(r"^[0-9a-f]{64}$")
DDL="""
PRAGMA foreign_keys=ON;
CREATE TABLE mre_runs(
 run_id INTEGER PRIMARY KEY, label TEXT NOT NULL UNIQUE,
 source_run INTEGER NOT NULL, audited_run INTEGER NOT NULL,
 source_commit TEXT NOT NULL, protocol TEXT NOT NULL,
 novelty TEXT NOT NULL, holdout TEXT NOT NULL, cap REAL NOT NULL,
 n_originals INTEGER NOT NULL, repetitions INTEGER NOT NULL,
 n_modes INTEGER NOT NULL, baseline TEXT NOT NULL,
 attempts INTEGER NOT NULL, audited INTEGER NOT NULL,
 independent_unsat_lrat INTEGER NOT NULL, audit_report_sha256 TEXT NOT NULL);
CREATE TABLE original_sources(
 original_sha256 TEXT PRIMARY KEY, case_name TEXT NOT NULL,
 provenance_first_seen TEXT NOT NULL);
CREATE TABLE run_original_sources(
 source_run INTEGER NOT NULL, original_sha256 TEXT NOT NULL,
 case_name TEXT NOT NULL, cohort TEXT NOT NULL, expected TEXT NOT NULL,
 PRIMARY KEY(source_run,original_sha256),
 FOREIGN KEY(original_sha256) REFERENCES original_sources(original_sha256));
CREATE TABLE mre_attempts(
 source_run INTEGER NOT NULL, original_sha256 TEXT NOT NULL,
 mode TEXT NOT NULL, repetition INTEGER NOT NULL, paired_seed INTEGER NOT NULL,
 verdict TEXT NOT NULL, original_sat_witness INTEGER NOT NULL,
 unsat_crosschecked_no_lrat INTEGER NOT NULL,
 seconds_full_wall REAL NOT NULL, par2_seconds REAL NOT NULL,
 proof_tier TEXT NOT NULL, gate_applied INTEGER NOT NULL,
 eliminated_variables INTEGER NOT NULL, removed_clauses INTEGER NOT NULL,
 conflicts INTEGER, decisions INTEGER, propagations INTEGER,
 raw_row_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL,
 PRIMARY KEY(source_run,original_sha256,mode,repetition),
 FOREIGN KEY(source_run,original_sha256)
 REFERENCES run_original_sources(source_run,original_sha256));
CREATE TABLE mre_paired(
 source_run INTEGER NOT NULL, original_sha256 TEXT NOT NULL,
 repetition INTEGER NOT NULL, mode TEXT NOT NULL,
 baseline_mode TEXT NOT NULL, delta_par2_seconds REAL NOT NULL,
 baseline_solved INTEGER NOT NULL, alternative_solved INTEGER NOT NULL,
 baseline_to_timeout_regression INTEGER NOT NULL,
 timeout_to_solved_gain INTEGER NOT NULL,
 PRIMARY KEY(source_run,original_sha256,repetition,mode));
CREATE TABLE artifact_lineage(
 source_run INTEGER NOT NULL, artifact_run INTEGER NOT NULL,
 artifact_name TEXT NOT NULL, artifact_id INTEGER NOT NULL,
 gh_digest TEXT, source_commit TEXT NOT NULL,
 PRIMARY KEY(source_run,artifact_run,artifact_name));
CREATE INDEX idx_mre_attempts_source ON mre_attempts(original_sha256,mode);
"""
def check(b,m):
 if not b:raise RuntimeError("MRE_EVIDENCE_FAIL_CLOSED: "+str(m))
def jload(path):return json.loads(path.read_text())
def digest(data):return hashlib.sha256(data).hexdigest()
def valnum(x):return float(x)
def quote(row):return json.dumps(row,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def rows_for(root,s,sh):
 p=root/s["prefix"]/("shard-%d.json"%sh)
 check(p.is_file(),"missing raw shard "+str(p))
 v=jload(p)
 check(isinstance(v,list) and len(v)==s["attempts_per_shard"],
       "incomplete shard / source attempts "+str(p))
 return v
def report_for(root,s):
 p=root/"audit"
 results=list(p.rglob("report.json"))
 check(len(results)==1,"expected exactly ONE independent audit report "+str(p))
 return jload(results[0]),digest(results[0].read_bytes())
def index_for(root):
 p=root.parent/"artifact_index.tsv"
 check(p.is_file(),"missing GH immutable artifact provenance index")
 values={}
 for l in p.read_text().splitlines():
  col=l.split("\t")
  check(len(col)>=5,"bad artifact_index TSV")
  run,art_run,name,aid,gh_sha=col[:5]
  check(name and int(aid)>0 and int(run)>0 and int(art_run)>0,"malformed artifact lineage")
  if gh_sha and gh_sha!="null":
   check(gh_sha.startswith("sha256:") and H64.match(gh_sha.removeprefix("sha256:")),
         "invalid GH artifact digest "+name)
  key=(int(run),int(art_run),name)
  check(key not in values,"duplicate artifact lineage row")
  values[key]=(int(aid),gh_sha.removeprefix("sha256:") if gh_sha.startswith("sha256:") else None)
 return values
def extract(r,cap):
 m=r.get("mode")
 source=r.get("original_sha256") or r.get("sha256")
 check(isinstance(source,str) and H64.match(source),"missing ORIGINAL CNF SHA")
 if "protocol" in r:
  status=r["status"]; wall=float(r["full_wall_s"])
  commit=r["github_sha"]; cohort=r["source_cohort"]
  original=r["source"]; expected=r["expected"]
  satcheck=bool(r.get("source_original_SAT_witness_verified"))
  cross=bool(r.get("official_UNSAT_status_crosschecked"))
  native={k:r.get("native_"+k) for k in ("conflicts","decisions","propagations")}
 else:
  status=r["verdict"];wall=float(r["wall_s"])
  commit=r["run_sha"];cohort=("MRE10B_EXTERNAL_REFERENCE_CONDITIONED" if r.get("source_precommitted_external") else "MRE10_PREVIOUSLY_USED")
  original=r["gbd"];expected=r["source_screen"]
  satcheck=bool(r.get("original_sat_verified"))
  cross=bool(r.get("UNSAT_agreement_CaDiCaL_no_independent_LRAT"))
  native=r.get("native") or {}
 check(status in ("SAT","UNSAT","TIMEOUT"),"bad solved status")
 check(expected in ("SAT","UNSAT"),"missing independent original expected status")
 check(status=="TIMEOUT" or status==expected,"contradicts official/cross-solver reference")
 check(status!="SAT" or satcheck,"SAT witness on ORIGINAL not checked")
 check(status!="UNSAT" or cross,"UNSAT without independent published/cross-solver status agreement")
 check(not r.get("independent_UNSAT_LRAT",False),"UNSAT LRAT unexpected scope drift")
 check(math.isfinite(wall) and wall>=0,"invalid full-wall value")
 p=float(r["par2_s"])
 check(math.isfinite(p) and p>=0,"nonfinite PAR2")
 check(abs(p-(2*cap if status=="TIMEOUT" else wall))<0.005,
       "PAR2 does not include full wall/timeout cap")
 check("rep" in r and "seed" in r,"missing source-paired seed")
 check(isinstance(r["rep"],int) and isinstance(r["seed"],int),"seed/rep not integer")
 gate=r.get("gate") or {}
 return dict(sha=source,original=str(original),status=status,expected=expected,
   cap=cap,wall=wall,par2=p,cohort=str(cohort),mode=str(m),commit=commit,
   satcheck=int(satcheck),cross=int(cross),
   rep=r["rep"],seed=r["seed"],gate=int(bool(gate.get("applied"))),
   eliminated=int(gate.get("eliminated_variables") or gate.get("variables_eliminated") or 0),
   removed=int(gate.get("clauses_removed") or 0),
   conflicts=native.get("conflicts"),decisions=native.get("decisions"),
   propagations=native.get("propagations"))
def ingest(db,root,index,source_label,s):
 run=s["run"]; audit=s["audit"]; cap=s["cap"]
 rr,sha_report=report_for(root,s)
 check(rr.get("protocol") is not None,"audit protocol missing")
 check(rr.get("total_trials",rr.get("attempts"))==s["shards"]*s["attempts_per_shard"],
       "audited attempt total mismatch")
 scores=rr.get("scores") or rr.get("modes")
 check(isinstance(scores,dict) and len(scores)==s["modes"],"audit modes not complete")
 data=[]
 for sh in range(s["shards"]):
  data.extend(rows_for(root,s,sh))
 check(len(data)==s["cases"]*s["reps"]*s["modes"],
       "wrong full source * rep * arm count")
 modes={r["mode"] for r in data}
 check(set(scores)==modes and s["baseline"] in modes,"reported mode names do not match raw")
 proto={r.get("proto",r.get("protocol")) for r in data}
 check(len(proto)==1 and rr["protocol"] in proto,"audit vs raw protocol drift")
 db.execute("INSERT INTO mre_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
  (run,source_label,run,audit,s["sha"],rr["protocol"],s["novelty"],
   s["holdout"],cap,s["cases"],s["reps"],s["modes"],s["baseline"],
   len(data),1,sha_report))
 seen=set(); pairs=collections.defaultdict(dict); source_map={}
 metrics=collections.defaultdict(lambda:dict(solved=0,par2=0.,n=0))
 for r in data:
  x=extract(r,cap)
  check(x["commit"]==s["sha"],"raw run commit SHA does not match pinned head")
  check(0<=x["rep"]<s["reps"],"repetition out of range")
  check(x["mode"] in modes,"unexpected arm")
  key=(x["sha"],x["rep"],x["mode"])
  check(key not in seen,"duplicate raw source/seed/mode within run")
  seen.add(key)
  if x["sha"] in source_map:
   check(source_map[x["sha"]]==(x["original"],x["cohort"],x["expected"]),
         "same source SHA used with contradictory metadata")
  else:
   source_map[x["sha"]]=(x["original"],x["cohort"],x["expected"])
   db.execute("INSERT OR IGNORE INTO original_sources VALUES(?,?,?)",
              (x["sha"],x["original"],s["novelty"]))
   db.execute("INSERT INTO run_original_sources VALUES(?,?,?,?,?)",
              (run,x["sha"],x["original"],x["cohort"],x["expected"]))
  k=(x["sha"],x["rep"])
  check(x["mode"] not in pairs[k],"duplicate seed/mode")
  pairs[k][x["mode"]]=x
  proof="SAT_VERIFIED_ORIGINAL" if x["status"]=="SAT" else "UNSAT_EXTERNAL_STATUS_NO_INDEPENDENT_LRAT" if x["status"]=="UNSAT" else "CAP_TIMEOUT_UNRESOLVED"
  j=quote(r)
  db.execute("INSERT INTO mre_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
     (run,x["sha"],x["mode"],x["rep"],x["seed"],x["status"],
      x["satcheck"],x["cross"],x["wall"],x["par2"],proof,x["gate"],
      x["eliminated"],x["removed"],x["conflicts"],x["decisions"],
      x["propagations"],digest(j.encode()),j))
  m=metrics[x["mode"]];m["n"]+=1;m["solved"]+=(x["status"]!="TIMEOUT");m["par2"]+=x["par2"]
 check(len(source_map)==s["cases"] and len(pairs)==s["cases"]*s["reps"],
       "source/seed cohort incomplete")
 for k,group in pairs.items():
  check(set(group)==modes,"missing mode in source-paired set")
  check(len({x["seed"] for x in group.values()})==1,"native seed not paired")
  baseline=group[s["baseline"]]
  for mode,x in group.items():
   if mode==s["baseline"]:continue
   base_done=baseline["status"]!="TIMEOUT";other_done=x["status"]!="TIMEOUT"
   db.execute("INSERT INTO mre_paired VALUES(?,?,?,?,?,?,?,?,?,?)",
     (run,k[0],k[1],mode,s["baseline"],baseline["par2"]-x["par2"],
      int(base_done),int(other_done),int(base_done and not other_done),
      int((not base_done) and other_done)))
 for mode,score in scores.items():
  m=metrics[mode]
  check(m["n"]==s["cases"]*s["reps"],"missing raw arm attempts")
  check(m["solved"]==int(score.get("solved")),"raw solved count disagrees with independent audit "+mode)
  published=score.get("par2_s",score.get("PAR2_total_s"))
  check(published is not None and abs(m["par2"]-float(published))<=.006,
        "raw PAR2 total disagrees with signed audit "+mode)
 # Provenance index must include every original shard and audited artifact.
 related={(int(k[1]),k[2]):v for k,v in index.items() if k[0]==run}
 check(any(k[0]==audit for k in related),"missing audit artifact index")
 check(len([z for z in related if z[0]==run and "shard-" in z[1]])>=s["shards"],
       "missing any shard artifact provenance")
 for (artifact_run,art_name),(aid,gh_sha) in related.items():
  db.execute("INSERT INTO artifact_lineage VALUES(?,?,?,?,?,?)",
   (run,artifact_run,art_name,aid,gh_sha,s["sha"]))
 result=dict(run_id=run,audit_run=audit,labels=source_label,attempts=len(data),
             sources=len(source_map),paired=len(pairs)*(s["modes"]-1),
             cohort=s["novelty"],reference=s["baseline"],
             scores={mode:dict(attempts=v["n"],solved=v["solved"],
               par2_s=round(v["par2"],6),speedup_vs_baseline_x=round(
                 metrics[s["baseline"]]["par2"]/v["par2"],6)) for mode,v in metrics.items()})
 return result

def writecsv(path,rows):
 check(bool(rows),"CSV cannot be empty "+str(path))
 with path.open("w",newline="") as o:
  w=csv.DictWriter(o,fieldnames=list(rows[0]))
  w.writeheader();w.writerows(rows)

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--input",type=pathlib.Path,required=True)
 p.add_argument("--out",type=pathlib.Path,required=True)
 p.add_argument("--historical-sqlite",type=pathlib.Path,required=True)
 p.add_argument("--historical-sha",type=pathlib.Path,required=True)
 a=p.parse_args()
 a.out.mkdir(parents=True,exist_ok=True)
 # Historical database is read-only. Never UPDATE existing V15.3.1 tables or
 # mutate the historical .sqlite / .gz. Extend it with ATTACH of this sidecar.
 hash_expected=a.historical_sha.read_text().strip().split()[0]
 check(H64.match(hash_expected),"historical baseline SHA file missing")
 check(digest(a.historical_sqlite.read_bytes())==hash_expected,
       "historical compressed SQLite immutable SHA mismatch")
 old=sqlite3.connect("file:"+str(a.historical_sqlite.resolve())+"?mode=ro",uri=True)
 try:
  check(old.execute("PRAGMA integrity_check").fetchone()[0]=="ok","historical SQLite corrupt")
  counts=tuple(old.execute("SELECT COUNT(*) FROM "+x).fetchone()[0] for x in
               ("datasets","formulas","attempts"))
  check(counts==CORE_COUNTS,"V15.3.1 historical core counts changed "+str(counts))
 finally:old.close()
 lineage=index_for(a.input)
 dbpath=a.out/"mre_evidence.sqlite"
 if dbpath.exists():dbpath.unlink()
 db=sqlite3.connect(dbpath)
 try:
  db.executescript(DDL)
  results=[]
  for label,s in SPEC.items():
   check((a.input/label).is_dir(),"missing whole experiment "+label)
   results.append(ingest(db,a.input/label,lineage,label,s))
  db.commit()
  check(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","new MRE SQLite corrupt")
  expected_total=sum(s["cases"]*s["reps"]*s["modes"] for s in SPEC.values())
  count=db.execute("SELECT COUNT(*) FROM mre_attempts").fetchone()[0]
  check(count==expected_total==1624,"not exactly 1624 complete attempts")
  counts=dict(benchmark_runs=db.execute("SELECT COUNT(*) FROM mre_runs").fetchone()[0],
    unique_original_shas=db.execute("SELECT COUNT(*) FROM original_sources").fetchone()[0],
    run_formula_memberships=db.execute("SELECT COUNT(*) FROM run_original_sources").fetchone()[0],
    attempts=count,paired=db.execute("SELECT COUNT(*) FROM mre_paired").fetchone()[0],
    source_lineage_artifacts=db.execute("SELECT COUNT(*) FROM artifact_lineage").fetchone()[0])
  rows=[dict(run_id=t[0],label=t[1],source=t[2],audit=t[3],
        original=t[4],attempts=t[5],solved=t[6],par2=round(t[7],6))
     for t in db.execute("""SELECT r.run_id,r.label,r.source_commit,r.audited_run,
       a.mode,COUNT(*),SUM(a.verdict!='TIMEOUT'),SUM(a.par2_seconds)
       FROM mre_runs r JOIN mre_attempts a ON r.run_id=a.source_run
       GROUP BY r.run_id,a.mode ORDER BY r.run_id,a.mode""")]
  writecsv(a.out/"mre_run_modes.csv",rows)
  pairrows=[dict(run_id=t[0],source_sha256=t[1],mode=t[2],
          baseline_par2=round(t[3],6),mode_par2=round(t[4],6),
          solved_base=t[5],solved_mode=t[6],
          regression_count=t[7],new_solved_count=t[8])
    for t in db.execute("""SELECT a.source_run,a.original_sha256,a.mode,
    SUM(b.par2_seconds),SUM(a.par2_seconds),
    SUM(b.verdict!='TIMEOUT'),SUM(a.verdict!='TIMEOUT'),
    SUM(b.verdict!='TIMEOUT' AND a.verdict='TIMEOUT'),
    SUM(b.verdict='TIMEOUT' AND a.verdict!='TIMEOUT')
    FROM mre_attempts a JOIN mre_runs r ON a.source_run=r.run_id
    JOIN mre_attempts b ON b.source_run=a.source_run
      AND b.original_sha256=a.original_sha256 AND b.repetition=a.repetition
      AND b.mode=r.baseline
    WHERE a.mode!=r.baseline GROUP BY a.source_run,a.original_sha256,a.mode
    ORDER BY a.source_run,a.original_sha256,a.mode""")]
  writecsv(a.out/"mre_source_paired.csv",pairrows)
  overlaps=[dict(source_sha256=t[0],appears_in_runs=t[1],runs=t[2])
    for t in db.execute("""SELECT original_sha256,COUNT(DISTINCT source_run),
    GROUP_CONCAT(DISTINCT source_run) FROM run_original_sources
    GROUP BY original_sha256 HAVING COUNT(DISTINCT source_run)>1
    ORDER BY COUNT(DISTINCT source_run) DESC""")]
  if overlaps:writecsv(a.out/"mre_cross_run_reused_sources.csv",overlaps)
  summary=dict(protocol="DRNAS-MRE-20261108-CERTIFIED-ADDITIVE-SIDECAR-v1",
   historical_sqlite_sha256=hash_expected,
   historical_core_counts=dict(zip(("datasets","formulas","attempts"),CORE_COUNTS)),
   historical_tables_modified=False,
   disjoint_repeated_trials_not_new_originals=True,
   independent_unsat_LRAT=False,
   signed_audit_reports_crosschecked_to_every_raw_shard=True,
   result=counts,runs=results)
  (a.out/"mre_ingest_audit.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
 finally:db.close()
 with dbpath.open("rb") as fi,gzip.GzipFile(filename=str(a.out/"mre_evidence.sqlite.gz"),mode="wb",mtime=0) as fo:
  shutil.copyfileobj(fi,fo)
 (a.out/"mre_evidence.sqlite.sha256").write_text(digest(dbpath.read_bytes())+"\n")
 print("MRE_CUMULATIVE_EVIDENCE_PASS",json.dumps(counts,sort_keys=True),flush=True)

if __name__=="__main__":main()
