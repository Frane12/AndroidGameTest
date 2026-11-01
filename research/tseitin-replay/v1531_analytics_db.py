#!/usr/bin/env python3
"""Non-invasive V15.3.1 SQLite analytics for archived benchmark artifacts."""
import argparse, csv, hashlib, json, sqlite3, statistics
from pathlib import Path
from collections import defaultdict

ORIGINS = {
 "DRNAS-V1531-Regression-168": ("generated_development","structural"),
 "DRNAS-V1531-Mixed-96": ("generated_development","xor"),
 "DRNAS-V1531-SATLIB-40-Regression": ("external_previously_seen","SATLIB F"),
 "DRNAS-V1531-NoHang-Stress": ("generated_stress","stress"),
 "DRNAS-V1531-External-Short40": ("external_holdout_relative_to_v1531","SATLIB short40"),
 "v1531-regression-168": ("generated_development","structural"),
 "v1531-mixed-96": ("generated_development","xor"),
 "v1531-satlib-f": ("external_previously_seen","SATLIB F"),
 "v1531-nohang-stress": ("generated_stress","stress"),
}
DDL = """
PRAGMA foreign_keys=ON;
CREATE TABLE datasets (dataset TEXT PRIMARY KEY, provenance TEXT, description TEXT,
 source_run TEXT, source_sha TEXT, runner TEXT, timeout REAL, json_sha256 TEXT);
CREATE TABLE formulas (dataset TEXT, case_name TEXT, category TEXT, expected TEXT,
 formula_sha256 TEXT, original_sha256 TEXT, original_path TEXT,
 variables INTEGER, clauses INTEGER, PRIMARY KEY(dataset,case_name));
CREATE TABLE attempts (dataset TEXT, case_name TEXT, solver TEXT, repeat INTEGER,
 seconds REAL, status TEXT, correct INTEGER, route TEXT, sat_model_checked INTEGER,
 unsat_proof_checked INTEGER, par2_seconds REAL, exit_code INTEGER,
 PRIMARY KEY(dataset,case_name,solver,repeat));
CREATE TABLE telemetry (dataset TEXT, case_name TEXT, solver TEXT, repeat INTEGER,
 event INTEGER, elapsed_seconds REAL, conflicts INTEGER, propagations INTEGER,
 restarts INTEGER, learned_clauses INTEGER, avg_lbd REAL,
 PRIMARY KEY(dataset,case_name,solver,repeat,event));
CREATE INDEX idx_attempts ON attempts(dataset,solver,case_name);
"""

def sha(path):
 return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def boolean(x):
 return None if x is None else int(bool(x))

def num(x):
 try: return float(x) if x is not None else None
 except (TypeError,ValueError): return None

def ingest(db, path, run, commit, runner):
 data=json.loads(path.read_text())
 dataset=path.parent.name
 provenance,description=ORIGINS.get(dataset,("unclassified","not verified as official or unseen"))
 meta=data.get("dataset_meta",{}) if isinstance(data,dict) else {}
 provenance=meta.get("provenance",provenance)
 description=meta.get("benchmark",description)
 source_run=meta.get("source_run") or run
 source_sha=meta.get("source_sha") or commit
 runner_name=meta.get("runner") or runner
 cap=next((num(data[k]) for k in ("timeout_seconds","seconds_cap","timeout") if isinstance(data,dict) and k in data),None)
 if dataset.lower().endswith(("nohang-stress","nohang-stress")): cap=5.0
 manifest={r["id"]:r for r in data.get("manifest",[])} if isinstance(data,dict) else {}
 rows=data if isinstance(data,list) else data.get("results",[])
 if not isinstance(rows,list): raise ValueError("Invalid results list: "+str(path))
 db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
            (dataset,provenance,description,source_run,source_sha,runner_name,cap,sha(path)))
 seen=set()
 for row in rows:
  case=str(row["case"]); solver=str(row["solver"])
  if case not in seen:
   meta=manifest.get(case,{})
   category=str(row.get("family") or ("xor_w"+str(row["width"]) if "width" in row else description))
   db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",
    (dataset,case,category,row.get("expected") or meta.get("expected"),
     meta.get("sha256_normalized") or sha(path.parent/case),meta.get("sha256_source"),
     meta.get("source"),meta.get("n"),meta.get("clauses")))
   seen.add(case)
  reps=row.get("reps",row.get("runs"))
  if reps is None: reps=[row]
  for k,r in enumerate(reps):
   sec=num(r.get("seconds"))
   if sec is not None and sec<0: raise ValueError("Negative time")
   status=str(r.get("status","UNKNOWN")).upper()
   valid=boolean(r.get("correct"))
   par2=(sec if valid==1 and status in ("SAT","UNSAT") else 2*cap) if cap is not None else None
   db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    (dataset,case,solver,int(r.get("rep",k)),sec,status,valid,r.get("route"),
     boolean(r.get("sat_witness_ok",r.get("model_ok",r.get("model_valid")))),
     boolean(r.get("native_proof_ok",r.get("proof_ok",r.get("proof_valid")))),
     par2,r.get("exit",r.get("exit_code"))))
 return {"dataset":dataset,"provenance":provenance,"cases":len(seen),"rows":len(rows),"timeout":cap}

def export_csv(path,rows,columns):
 with path.open("w",newline="") as f:
  wr=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore")
  wr.writeheader(); wr.writerows(rows)

def analytics(db,out):
 db.row_factory=sqlite3.Row
 def sql(q): return [dict(x) for x in db.execute(q)]
 datasets=sql("SELECT * FROM datasets ORDER BY dataset")
 formulas=sql("SELECT * FROM formulas ORDER BY dataset,category,case_name")
 attempts=sql("""SELECT d.provenance,f.category,a.*,f.formula_sha256
              FROM attempts a JOIN formulas f USING(dataset,case_name)
              JOIN datasets d USING(dataset)
              ORDER BY a.dataset,a.case_name,a.solver,a.repeat""")
 telem=sql("SELECT * FROM telemetry ORDER BY dataset,case_name,solver,repeat,event")
 for filename,rows,cols in (
  ("datasets.csv",datasets,["dataset","provenance","description","source_run","source_sha","runner","timeout","json_sha256"]),
  ("formulas.csv",formulas,["dataset","case_name","category","expected","formula_sha256","original_sha256","original_path","variables","clauses"]),
  ("attempts.csv",attempts,["provenance","category","dataset","case_name","solver","repeat","seconds","status","correct","route","sat_model_checked","unsat_proof_checked","par2_seconds","exit_code","formula_sha256"]),
  ("telemetry.csv",telem,["dataset","case_name","solver","repeat","event","elapsed_seconds","conflicts","propagations","restarts","learned_clauses","avg_lbd"])):
  export_csv(out/filename,rows,cols)
 groups=defaultdict(list); cases=defaultdict(list)
 for r in attempts:
  groups[(r["dataset"],r["provenance"],r["category"],r["solver"])].append(r)
  cases[(r["dataset"],r["case_name"],r["solver"])].append(r)
 grouped=[]
 for (d,p,c,s),rs in sorted(groups.items()):
  times=[r["seconds"] for r in rs if r["seconds"] is not None]
  ps=[r["par2_seconds"] for r in rs if r["par2_seconds"] is not None]
  grouped.append(dict(dataset=d,provenance=p,category=c,solver=s,
   formulas=len({r["case_name"] for r in rs}),attempts=len(rs),
   correct=sum(r["correct"]==1 for r in rs),
   timeouts=sum(r["status"]=="TIMEOUT" for r in rs),
   missing_par2=len(rs)-len(ps),
   par2_sum=round(sum(ps),9) if len(ps)==len(rs) else None,
   median_seconds=statistics.median(times) if times else None))
 export_csv(out/"grouped.csv",grouped,
  ["dataset","provenance","category","solver","formulas","attempts","correct","timeouts","missing_par2","par2_sum","median_seconds"])
 paired=[]
 for (d,c,s),rs in sorted(cases.items()):
  baseline=cases.get((d,c,"kissat"))
  if s=="kissat" or not baseline: continue
  a=[r["par2_seconds"] for r in rs]; b=[r["par2_seconds"] for r in baseline]
  if any(v is None for v in a+b):continue
  x=statistics.median(b); y=statistics.median(a)
  paired.append(dict(dataset=d,case_name=c,category=rs[0]["category"],
   provenance=rs[0]["provenance"],solver=s,kissat_par2_median=x,
   solver_par2_median=y,speedup=x/y if y>0 else None,
   gain_percent=100*(x-y)/x if x>0 else None))
 export_csv(out/"paired.csv",paired,
  ["dataset","case_name","category","provenance","solver","kissat_par2_median","solver_par2_median","speedup","gain_percent"])
 (out/"summary.json").write_text(json.dumps({"datasets":datasets,"grouped":grouped,
  "paired_formula_rows":len(paired),"telemetry_events":len(telem)},indent=2))
 return grouped,paired,telem

def plot(out,paired,telemetry):
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
 except ImportError:
  print("No matplotlib: exported tables and SQLite only");return []
 files=[]
 for s in sorted({r["solver"] for r in paired}):
  rs=[r for r in paired if r["solver"]==s]
  fig,ax=plt.subplots(figsize=(8,6))
  for provenance in sorted({r["provenance"] for r in rs}):
   zz=[r for r in rs if r["provenance"]==provenance]
   ax.scatter([r["kissat_par2_median"] for r in zz],
              [r["solver_par2_median"] for r in zz],label=provenance,alpha=.7)
  limit=max([1]+[r["kissat_par2_median"] for r in rs]+[r["solver_par2_median"] for r in rs])
  ax.plot([0,limit],[0,limit],"--",linewidth=1)
  ax.set(xlabel="Kissat median PAR-2 (s)",ylabel=s+" median PAR-2 (s)",
         title="Paired formula performance; below diagonal = faster")
  ax.legend(fontsize=8);fig.tight_layout()
  file="scatter_paired_"+s+".png";fig.savefig(out/file,dpi=150);plt.close(fig);files.append(file)
  fig,ax=plt.subplots(figsize=(8,5))
  for category in sorted({r["category"] for r in rs}):
   zz=[r for r in rs if r["category"]==category]
   ax.scatter(range(len(zz)),[r["gain_percent"] for r in zz],label=category,alpha=.7)
  ax.axhline(0,linestyle="--",linewidth=1)
  ax.set(xlabel="Index within category",ylabel="PAR-2 improvement (%)",
         title=s+" improvement by category")
  ax.legend(fontsize=6,ncol=2);fig.tight_layout()
  file="scatter_gain_"+s+".png";fig.savefig(out/file,dpi=150);plt.close(fig);files.append(file)
 valid=[r for r in telemetry if r["conflicts"] is not None and r["elapsed_seconds"] is not None]
 if valid:
  fig,ax=plt.subplots(figsize=(8,5))
  for solver in sorted({r["solver"] for r in valid}):
   zz=[r for r in valid if r["solver"]==solver]
   ax.scatter([r["elapsed_seconds"] for r in zz],[r["conflicts"] for r in zz],label=solver,alpha=.6)
  ax.set(xlabel="Elapsed seconds",ylabel="Cumulative conflicts",title="Measured conflict dynamics")
  ax.legend();fig.tight_layout();fig.savefig(out/"scatter_conflicts.png",dpi=150)
  plt.close(fig);files.append("scatter_conflicts.png")
 return files

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--input",type=Path,required=True)
 ap.add_argument("--out",type=Path,default=Path("sat-analysis"))
 ap.add_argument("--source-run",default="unknown")
 ap.add_argument("--source-sha",default="unknown")
 ap.add_argument("--runner",default="unknown")
 args=ap.parse_args()
 files=sorted([p for p in args.input.rglob("*.json")
              if p.name in ("results.json","stress.json")])
 if not files:raise SystemExit("No results JSON found")
 args.out.mkdir(parents=True,exist_ok=True)
 dbpath=args.out/"sat_analytics.sqlite"
 if dbpath.exists(): dbpath.unlink()
 db=sqlite3.connect(dbpath)
 try:
  db.executescript(DDL)
  info=[ingest(db,p,args.source_run,args.source_sha,args.runner) for p in files]
  db.commit()
  grouped,paired,telemetry=analytics(db,args.out)
  png=plot(args.out,paired,telemetry)
 finally:db.close()
 print(json.dumps({"inputs":info,"groups":len(grouped),"paired":len(paired),
                   "charts":png,"sqlite":str(dbpath)},indent=2))

if __name__=="__main__":main()
