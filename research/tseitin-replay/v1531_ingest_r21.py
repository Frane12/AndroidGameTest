#!/usr/bin/env python3
"""Strict append-only R21 native SAT ingest. Frozen V15.3.1 is never touched."""
import argparse,csv,hashlib,json,math,sqlite3
from pathlib import Path
from collections import defaultdict

COMMIT="f7064bf14381e04ee35277b41226843d896fa05f"
PROTOCOL="dbceb4c5a52a57af8e6e660125e80e188e07f18b2dec752d9dbb8b8dae37a9e5"
KISSAT="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
STABLE="d280a2ffa28d72aec183323bbea40544d676112d"
MODES=("monitor","r11_2048_50","r16_live50","r20_local50","r21_mature_low50","r21_inverse50","original_kissat","stable_v1531")
SHARDS=[f"n{n}_{phase}{i}" for n in (200,220,240) for phase in ("development","test") for i in (0,1)]+[f"community_n{n}_{phase}0" for n in (220,240) for phase in ("development","test")]
FOLDS=("random3_development","random3_test","community3_development","community3_test")
def need(condition,message):
 if not condition:raise RuntimeError("R21_STRICT_INGEST_FAIL "+str(message))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def csvread(p):
 with p.open(newline="") as f:return list(csv.DictReader(f))
def export(p,rows):
 need(bool(rows),"empty CSV "+str(p))
 with p.open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def fold(shard):
 return ("community3_" if shard.startswith("community_") else "random3_")+("development" if "_development" in shard else "test")
def number(v):return float(v) if v not in ("",None) else None
def integer(v):return int(v) if v not in ("",None) else None
def flag(v):
 if str(v).lower() in ("true","1"):return 1
 if str(v).lower() in ("false","0"):return 0
 return None
def main():
 ap=argparse.ArgumentParser()
 for n in ("db","input","out"):ap.add_argument("--"+n,type=Path,required=True)
 ap.add_argument("--source-run",required=True)
 args=ap.parse_args();root=args.input;out=args.out;run=args.source_run
 need(run.isdigit(),"numeric run id")
 reportpath=root/"aggregate/results.json";report=json.loads(reportpath.read_text())
 need((report["attempts"],report["formulas"],report["shards"],report["repeats"])==(3840,160,16,3),"aggregate dimensions")
 need(tuple(report["modes"])==MODES and report["protocol_sha256"]==PROTOCOL,"frozen protocol and eight separate policies")
 need(report["historical_CNF_SHA_overlap"]==0 and report["C_Python_gate_mismatches"]==0 and report["preintervention_telemetry_mismatches"]==0,"source aggregate audits")
 sources={s["category"]:s for s in report["source_artifacts"]}
 need(len(sources)==16 and set(sources)==set(SHARDS),"source 16-shard set")
 features=csvread(root/"aggregate/formula_features.csv")
 paired=csvread(root/"aggregate/paired.csv")
 decisions=csvread(root/"aggregate/native_decisions.csv")
 need((len(features),len(paired),len(decisions))==(160,1120,960),"aggregate CSV row counts")
 fidx={r["formula"]:r for r in features}
 pidx={(r["formula"],r["strategy"]):r for r in paired}
 didx={(r["formula"],r["mode"],int(r["repeat"])):r for r in decisions}
 need((len(fidx),len(pidx),len(didx))==(160,1120,960),"aggregate CSV unique keys")
 index={}
 for line in (root/"artifact_index.tsv").read_text().splitlines():
  name,aid,expired=line.split("\t")[:3]
  need(name not in index and expired=="false","artifact duplicate or expired "+name)
  index[name]=int(aid)
 need(len(index)==17 and "DRNAS-R21-True-Clause-Age-LBD-Implication-Native-Analysis" in index,"17 exact live artifacts")
 need(set(index)=={"DRNAS-R21-True-Clause-Age-LBD-Implication-Native-Analysis"}|{"r21-"+s for s in SHARDS},"artifact names")
 db=sqlite3.connect(args.db)
 try:
  db.execute("PRAGMA foreign_keys=ON")
  need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","historical SQLite integrity")
  before=tuple(db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("datasets","formulas","attempts"))
  need(before==(215,2819,49490),"historical baseline changed "+str(before))
  prior={h for (h,) in db.execute("SELECT formula_sha256 FROM formulas") if h}
  need(len(prior)==2819,"prior SHA duplicates / missing")
  db.execute("""CREATE TABLE IF NOT EXISTS r21_native_details(
   dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,
   raw_row_sha256 TEXT,trace_sha256 TEXT,source_manifest_sha256 TEXT,
   source_commit TEXT,source_runner TEXT,source_seed TEXT,raw_json TEXT,
   PRIMARY KEY(dataset,case_name,solver,repeat))""")
  db.execute("""CREATE TABLE IF NOT EXISTS r21_native_decisions(
   dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,
   decision_json TEXT,PRIMARY KEY(dataset,case_name,solver,repeat))""")
  unique=set();source_audit=[];paired_out=[];n_attempts=0;truth=defaultdict(set)
  aggregate_sha=digest(reportpath)
  for shard in SHARDS:
   folder=root/"shards"/shard
   manifestpath=folder/"manifest.json";measurepath=folder/"measurements.csv";tracepath=folder/"traces.jsonl"
   for p in (manifestpath,measurepath,tracepath):need(p.is_file(),"missing raw "+str(p))
   manifest=json.loads(manifestpath.read_text());rows=csvread(measurepath)
   traces=[json.loads(line) for line in tracepath.read_text().splitlines() if line.strip()]
   source=sources[shard];fd=fold(shard)
   need(len(rows)==len(traces)==240 and len(manifest["cases"])==10,"incomplete shard "+shard)
   need(manifest["category"]==shard and manifest["fold"]==fd and manifest["source_commit"]==source["source_commit"]==COMMIT,"commit/fold "+shard)
   need(manifest["runner"]==source["runner"] and manifest["cpu_affinity"]==[manifest["cpu_core"]]==[source["cpu_core"]],"runner/CPU "+shard)
   need(manifest["protocol"]==report["protocol"] and manifest["protocol_sha256"]==PROTOCOL and tuple(manifest["modes"])==MODES,"mode/protocol "+shard)
   need(manifest["historic_count"]==2894 and manifest["kissat_pin"]==KISSAT and manifest["v1531_blob"]==STABLE,"source pins "+shard)
   need(manifest["cap_seconds"]==12 and manifest["repeats"]==3 and manifest["binaries"]==source["binary_sha256"],"binary/timeout "+shard)
   need(digest(manifestpath)==source["manifest_sha256"] and digest(measurepath)==source["measurements_sha256"] and digest(tracepath)==source["traces_sha256"],"raw SHA-256 "+shard)
   cases={c["formula"]:c for c in manifest["cases"]}
   need(len(cases)==10,"duplicate cases "+shard)
   raw={(r["formula"],r["mode"],int(r["repeat"])):r for r in rows}
   events={(t["formula"],t["mode"],int(t["repeat"])):t for t in traces}
   expected={(c,m,i) for c in cases for m in MODES for i in range(3)}
   need(len(raw)==len(events)==len(expected) and set(raw)==set(events)==expected,"paired matrix "+shard)
   dataset="DRNAS-R21-"+shard
   need(db.execute("SELECT COUNT(*) FROM datasets WHERE dataset=?",(dataset,)).fetchone()[0]==0,"dataset already exists "+dataset)
   provenance="generated_"+fd
   db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
    (dataset,provenance,"R21 true in-process clause-age/LBD/reason-role; synthetic NOT official; SAT witnesses checked, UNSAT uncertified",run,COMMIT,manifest["runner"],12,aggregate_sha))
   sums=defaultdict(float)
   for cname,c in cases.items():
    h=c["formula_sha256"];seed=c["metadata"]["seed"]
    need(len(h)==64 and h not in prior and h not in unique,"historical or within-R21 SHA duplicate "+h)
    need((folder/cname).is_file() and digest(folder/cname)==h,"CNF bytes SHA mismatch "+cname)
    need(c["dataset_type"]=="generated_prospective" and c["expected"]=="UNKNOWN","synthetic provenance "+cname)
    need(c["metadata"]["family"]==fd.split("_")[0] and c["metadata"]["fold"] in fd,"fold "+cname)
    unique.add(h)
    db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",
     (dataset,cname,fd,"UNKNOWN",h,None,c.get("path"),c["n"],c["metadata"]["features"].get("clauses")))
    f=fidx[cname]
    need(f["formula_sha256"]==h and f["seed"]==str(seed) and f["fold"]==fd,"aggregate features "+cname)
   for cname,mode,rep in sorted(expected):
    r=raw[(cname,mode,rep)];t=events[(cname,mode,rep)];c=cases[cname]
    need(r["formula_sha256"]==c["formula_sha256"] and r["seed"]==str(c["metadata"]["seed"]) and r["runner"]==manifest["runner"],"row formula/seed/runner")
    need(r["category"]==shard and r["fold"]==fd and r["mode"]==mode,"row category/mode/fold")
    need(r["r21_protocol_sha256"]==PROTOCOL and not r["error"] and not r["r21_error"] and not r["r16_decision_error"],"row native error or pin")
    status=r["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"invalid status "+status)
    if status=="SAT":need(flag(r["sat_model_checked"])==1,"unchecked SAT witness")
    if status!="TIMEOUT":truth[cname].add(status)
    wall=float(r["wall_s"]);par2=float(r["par2_s"])
    need(math.isfinite(wall) and wall>=0 and math.isfinite(par2) and abs(par2-(24 if status=="TIMEOUT" else wall))<1e-5,"PAR-2")
    need(t["formula"]==cname and t["mode"]==mode and int(t["repeat"])==rep and len(t["points"])==int(r["trace_points"]),"trace linkage")
    sums[(cname,mode)]+=par2
    sat=flag(r["sat_model_checked"]);unsat=flag(r.get("unsat_certificate_checked"))
    correct=1 if (status=="SAT" and sat==1) or (status=="UNSAT" and unsat==1) else 0 if status=="TIMEOUT" else None
    tier="sat_witness" if status=="SAT" else "unsat_label_only" if status=="UNSAT" else "timeout"
    db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,cname,mode,rep,wall,status,correct,r.get("expected_action"),sat,unsat,par2,integer(r.get("exit_code"))))
    db.execute("INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",
     (dataset,cname,mode,rep,manifest["runner"],r["seed"],c.get("source_revision"),c["formula_sha256"],canonical(r),tier))
    db.execute("INSERT INTO r21_native_details VALUES (?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,cname,mode,rep,canonical(r),canonical(t),digest(manifestpath),COMMIT,manifest["runner"],r["seed"],json.dumps(r,sort_keys=True)))
    for i,p in enumerate(t["points"]):
     db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (dataset,cname,mode,rep,i,None,integer(p.get("conflict")),integer(p.get("propagations")),integer(p.get("restarts")),integer(p.get("learned")),number(p.get("glue"))))
    if mode in ("r21_mature_low50","r21_inverse50"):
     d=didx[(cname,mode,rep)]
     need(d["formula_sha256"]==c["formula_sha256"] and d["C_Python_selected"]==r["r21_python_selected"] and d["actual_switch"]==r["switch_at"] and d["native_decision"]==r["r21_native_decision"],"R21 C/Python decision parity")
     db.execute("INSERT INTO r21_native_decisions VALUES (?,?,?,?,?)",(dataset,cname,mode,rep,json.dumps(d,sort_keys=True)))
    n_attempts+=1
   for cname,c in cases.items():
    f=fidx[cname]
    for mode in MODES:
     need(abs(float(f[mode])-sums[(cname,mode)])<.0002,"feature PAR2 "+cname+"/"+mode)
     if mode!="monitor":
      p=pidx[(cname,mode)]
      need(p["sha256"]==c["formula_sha256"] and p["fold"]==fd and abs(float(p["monitor_PAR2_s"])-sums[(cname,"monitor")])<.0002 and abs(float(p["treatment_PAR2_s"])-sums[(cname,mode)])<.0002,"paired PAR2 "+cname+"/"+mode)
      paired_out.append(dict(fold=fd,formula_sha256=c["formula_sha256"],solver=mode,monitor_par2=sums[(cname,"monitor")],treatment_par2=sums[(cname,mode)]))
   db.execute("INSERT INTO source_artifacts VALUES (?,?,?,?,?,?,?,?,?)",
    (dataset,run,COMMIT,index["r21-"+shard],digest(measurepath),aggregate_sha,manifest["runner"],provenance,"R21 real native synthetic, NOT official; UNSAT uncertified"))
   source_audit.append(dict(dataset=dataset,run=run,commit=COMMIT,runner=manifest["runner"],artifact_id=index["r21-"+shard],fold=fd,formulas=10,attempts=240,manifest_sha256=digest(manifestpath),measurements_sha256=digest(measurepath),traces_sha256=digest(tracepath),aggregate_sha256=aggregate_sha))
  need(all(len(s)<=1 for s in truth.values()),"SAT/UNSAT contradiction across repetitions")
  need(len(unique)==160 and n_attempts==3840 and len(paired_out)==1120,"final R21 dimensions")
  after=tuple(db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("datasets","formulas","attempts"))
  need(after==(231,2979,53330),"cumulative count mismatch "+str(after))
  need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","final SQLite integrity")
  need(db.execute("SELECT COUNT(DISTINCT formula_sha256) FROM formulas WHERE dataset LIKE 'DRNAS-R21-%'").fetchone()[0]==160,"R21 SHA dedup")
  db.commit()
 finally:db.close()
 out.mkdir(parents=True,exist_ok=True)
 export(out/"r21_source_audit.csv",source_audit)
 export(out/"r21_paired.csv",paired_out)
 export(out/"r21_formula_features.csv",features)
 export(out/"r21_native_decisions.csv",decisions)
 try:
  import matplotlib
  matplotlib.use("Agg")
  import matplotlib.pyplot as plt
  for fd in FOLDS:
   fig,ax=plt.subplots(figsize=(7,5))
   for mode in MODES:
    if mode=="monitor":continue
    points=[p for p in paired_out if p["fold"]==fd and p["solver"]==mode]
    ax.scatter([p["monitor_par2"] for p in points],[p["treatment_par2"] for p in points],label=mode,alpha=.65,s=12)
   maximum=max([1.]+[max(p["monitor_par2"],p["treatment_par2"]) for p in paired_out if p["fold"]==fd])
   ax.plot([0,maximum],[0,maximum],"k--",linewidth=1)
   ax.set(xlabel="Monitor formula PAR-2 (s)",ylabel="Treatment formula PAR-2 (s)",title="R21 "+fd+" (synthetic, not official)")
   ax.legend(fontsize=6);fig.tight_layout()
   fig.savefig(out/("scatter_r21_"+fd+".png"),dpi=130);plt.close(fig)
 except ImportError:
  raise RuntimeError("matplotlib missing; cannot publish required scatterplots")
 audit={"status":"VERIFIED_R21_ADDITIVE_NATIVE_INGEST","run":run,"commit":COMMIT,
  "before":{"datasets":before[0],"formulas":before[1],"attempts":before[2]},
  "after":{"datasets":after[0],"formulas":after[1],"attempts":after[2]},
  "unique_new_formula_sha256":len(unique),"new_native_attempts":n_attempts,
  "raw_shards":len(source_audit),"paired_formula_comparisons":len(paired_out),
  "aggregate_sha256":aggregate_sha,"protocol_sha256":PROTOCOL,
  "C_Python_gate_mismatches":0,"preintervention_telemetry_mismatches":0,
  "source_artifacts":source_audit,
  "limitations":["Synthetic random3/community3, not official","SAT witnesses checked; UNSAT not independently certified","R21 native policy live; no confirmed general speedup"]}
 (out/"r21_ingest_audit.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
 print("R21_VERIFIED_CUMULATIVE_SQLITE",json.dumps({"run":run,"before":before,"after":after,"sources":16,"formulas":160,"attempts":3840},sort_keys=True))
if __name__=="__main__":main()
