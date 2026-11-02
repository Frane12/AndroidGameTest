#!/usr/bin/env python3
"""Strictly additive R18 true-native SAT ingest; frozen V15.3.1 is immutable."""
import argparse,csv,hashlib,json,math,sqlite3
from pathlib import Path
from collections import defaultdict

RUN="41454823999"
COMMIT="16e2f64e38c8d4da3e6eec3b57127676f58ec58b"
MODEL="3ac5e05ef62a5d5632f3493dcc19638bc75fdaecb186ad8aaf9324eca7b29602"
PROTOCOL="ef374a8bc33484096864035efe0ce5dd771337937c1a682118a2da4778bd1386"
STABLE="9e2b04e2e32b7320bd89757486b93ad0d5bc0ef10c28bdd54dd98c4bb14fb89c"
KISSAT="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MODES=("monitor","r11_2048_50","r16_live50","r17_risk30","r17_risk45","r18_lcb","r18_mean","original_kissat","stable_v1531")
NEW=("r18_lcb","r18_mean")
SHARDS=[f"n{n}_{fold}{i}" for n in (200,220,240) for fold in ("development","test") for i in (0,1)]+[f"community_n{n}_{fold}0" for n in (220,240) for fold in ("development","test")]

def check(ok,msg):
 if not ok:raise ValueError("R18 source integrity failure: "+msg)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def rowsha(row):return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def readcsv(path):
 with path.open(newline="") as f:return list(csv.DictReader(f))
def integer(x):return int(x) if x not in ("",None) else None
def number(x):return float(x) if x not in ("",None) else None
def flag(x):
 return 1 if str(x).lower() in ("true","1") else 0 if str(x).lower() in ("false","0") else None
def export(path,rows):
 if rows:
  with path.open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def foldof(cat):
 return ("community3_" if cat.startswith("community_") else "random3_")+("development" if "_development" in cat else "test")

def main():
 p=argparse.ArgumentParser()
 for key in ("db","input","out"):p.add_argument("--"+key,type=Path,required=True)
 a=p.parse_args();root=a.input;out=a.out;out.mkdir(parents=True,exist_ok=True)
 report_path=root/"aggregate/results.json";report=json.loads(report_path.read_text())
 check(report["status"]=="R18_TRUE_PROSPECTIVE_NATIVE_FROZEN_DIRECT_EFFECT_UNCERTAINTY_NOT_REPLAY","native R18 status")
 check((report["attempts"],report["formulas"],report["repeats"])==(4320,160,3),"aggregate dimensions")
 check(tuple(report["arms"])==MODES,"frozen 9-policy matrix")
 check(report["model_sha256"]==MODEL and report["protocol_sha256"]==PROTOCOL,"model/protocol SHA")
 check(report["historical_formula_collisions"]==0 and report["preintervention_mismatches"]==0,"aggregate history/prefix audit")
 check(len(report["source_artifacts"])==len(report["manifests"])==16,"16 complete shards")
 check(sha(root/"aggregate/netbenefit_model.json")==MODEL,"frozen R18 model")
 model_audit=json.loads((root/"aggregate/model_audit.json").read_text())
 check(isinstance(model_audit,dict),"model audit")
 index={}
 for line in (root/"artifact_index.tsv").read_text().splitlines():
  name,aid,expired=line.split("\t")[:3]
  check(name not in index and expired=="false","duplicate/expired artifact "+name)
  index[name]=int(aid)
 check(len(index)==17 and "DRNAS-R18-Frozen-Direct-Effect-Prospective-Native-Analysis" in index,"artifact index")
 source={s["category"]:s for s in report["source_artifacts"]}
 manifests={m["category"]:m for m in report["manifests"]}
 check(set(source)==set(manifests)==set(SHARDS),"shard identity")
 feats=readcsv(root/"aggregate/formula_features.csv")
 paired=readcsv(root/"aggregate/paired.csv")
 decisions=readcsv(root/"aggregate/native_decisions.csv")
 check((len(feats),len(paired),len(decisions))==(160,1280,960),"aggregate CSV dimensions")
 fidx={(f["category"],f["formula"]):f for f in feats}
 pidx={(f["category"],f["formula"],f["mode"]):f for f in paired}
 didx={(f["category"],f["formula"],int(f["repeat"]),f["mode"]):f for f in decisions}
 check((len(fidx),len(pidx),len(didx))==(160,1280,960),"unique aggregate CSV keys")
 db=sqlite3.connect(a.db)
 try:
  before={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("datasets","formulas","attempts")}
  check(before==dict(datasets=167,formulas=2339,attempts=39890),"immutable baseline "+str(before))
  check(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","historical SQLite")
  prior={h for (h,) in db.execute("SELECT formula_sha256 FROM formulas") if h}
  db.execute("CREATE TABLE IF NOT EXISTS r18_formula_features(dataset TEXT,case_name TEXT,formula_sha256 TEXT,manifest_sha256 TEXT,fold TEXT,seed INTEGER,source_revision TEXT,metadata_json TEXT,aggregate_features_sha256 TEXT,PRIMARY KEY(dataset,case_name))")
  db.execute("CREATE TABLE IF NOT EXISTS r18_native_details(dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,cpu_seconds REAL,switch_at INTEGER,raw_row_sha256 TEXT,mean_native REAL,mean_python REAL,sigma_native REAL,sigma_python REAL,lower_native REAL,lower_python REAL,selected INTEGER,model_sha256 TEXT,protocol_sha256 TEXT,PRIMARY KEY(dataset,case_name,solver,repeat))")
  unique=set();sources=[];nrows=0;aggregate_sha=sha(report_path);max_parity=0.0
  for cat in SHARDS:
   folder=root/"shards"/cat
   m=json.loads((folder/"manifest.json").read_text());s=source[cat]
   rows=readcsv(folder/"measurements.csv")
   traces=[json.loads(x) for x in (folder/"traces.jsonl").read_text().splitlines() if x.strip()]
   check("r18-"+cat in index,"missing raw artifact "+cat)
   for filename,key in (("manifest.json","manifest_sha256"),("measurements.csv","measurements_sha256"),("traces.jsonl","traces_sha256")):
    check(sha(folder/filename)==s[key],"raw SHA "+cat+"/"+filename)
   check(m==manifests[cat] and m["source_commit"]==s["source_commit"]==COMMIT,"manifest/commit "+cat)
   check(m["runner"]==s["runner"] and m["executables"]==s["binary_sha256"],"runner/binary pin "+cat)
   check(m["executables"]["stable_v1531"]==STABLE and m["kissat_pin"]==KISSAT,"immutable solver pin "+cat)
   check(m["model_sha256"]==s["frozen_model_sha256"]==MODEL and m["protocol_sha256"]==PROTOCOL,"frozen R18 pin "+cat)
   check(m["cpu_affinity"]==[m["cpu_core"]]==[s["cpu_core"]],"CPU pin "+cat)
   check(tuple(m["modes"])==MODES and m["repeats"]==3 and m["cap_seconds"]==12,"modes/repeats/cap "+cat)
   check(len(m["cases"])==10 and len(rows)==len(traces)==270,"raw dimensions "+cat)
   fold=foldof(cat);family=fold.split("_")[0]
   check(m["fold"]==fold and m["family"]==family,"fold/family "+cat)
   cases={c["formula"]:c for c in m["cases"]}
   check(len(cases)==10,"unique cases "+cat)
   key=lambda r:(r["formula"],r["mode"],int(r["repeat"]))
   expected={(name,mode,rep) for name in cases for mode in MODES for rep in range(3)}
   check(len(rows)==len(expected) and {key(r) for r in rows}==expected,"raw 9x3 matrix "+cat)
   check(len(traces)==len(expected) and {key(t) for t in traces}==expected,"trace matrix "+cat)
   trace_map={key(t):t for t in traces}
   totals=defaultdict(float);statuses=defaultdict(set);row_map={key(r):r for r in rows}
   for name,c in cases.items():
    h=c["formula_sha256"]
    check((folder/name).is_file() and sha(folder/name)==h,"CNF SHA "+name)
    check(len(h)==64 and h not in prior and h not in unique,"cross-history SHA duplicate "+name)
    check(c["dataset_type"]=="generated_prospective" and c["expected"]=="UNKNOWN","nonofficial provenance "+name)
    check(c["metadata"]["family"]==family and c["metadata"]["fold"] in fold and c["metadata"]["seed"] is not None,"seed/fold "+name)
    f=fidx[(cat,name)]
    check(f["formula_sha256"]==h and f["fold"]==fold and f["family"]==family and int(f["seed"])==c["metadata"]["seed"],"aggregate features "+name)
    unique.add(h)
   for r in rows:
    name,mode,rep=key(r);c=cases[name];t=trace_map[(name,mode,rep)]
    check(r["formula_sha256"]==c["formula_sha256"] and r["seed"]==str(c["metadata"]["seed"]),"row SHA/seed "+name)
    check(r["runner"]==m["runner"] and r["fold"]==fold and r["r18_model_sha256"]==MODEL and r["r18_protocol_sha256"]==PROTOCOL,"row pin "+name)
    status=r["status"]
    check(not r["error"] and not r["r18_error"] and not r["r17_risk_error"] and not r["r16_decision_error"] and status in ("SAT","UNSAT","TIMEOUT"),"error/status "+name)
    wall=float(r["wall_s"]);par2=float(r["par2_s"])
    check(math.isfinite(wall) and wall>=0 and math.isfinite(par2) and abs(par2-(24. if status=="TIMEOUT" else wall))<1e-5,"PAR-2 "+name)
    if status=="SAT":check(flag(r["sat_model_checked"])==1,"SAT witness "+name)
    if status!="TIMEOUT":statuses[name].add(status)
    check(len(t["points"])==int(r["trace_points"]),"trace linkage "+name)
    if mode in NEW and r["r18_native_mean"]:
     for x,y in (("r18_native_mean","r18_python_mean"),("r18_native_sigma","r18_python_sigma"),("r18_native_lower","r18_python_lower")):
      delta=abs(float(r[x])-float(r[y]));max_parity=max(max_parity,delta)
      check(delta<2e-5,"R18 C/Python parity "+name+"/"+x)
    if r["switch_at"]:
     check(mode not in ("monitor","original_kissat","stable_v1531") and int(r["switch_at"])>=2048 and r["learned_before"]==r["learned_after"],"native switch "+name)
    totals[(name,mode)]+=par2
   check(all(len(v)<=1 for v in statuses.values()),"SAT/UNSAT contradiction "+cat)
   for name in cases:
    f=fidx[(cat,name)]
    for mode in MODES:
     check(abs(totals[(name,mode)]-float(f[mode]))<.0002,"aggregate formula PAR2 "+name+"/"+mode)
     if mode!="monitor":
      pair=pidx[(cat,name,mode)]
      check(pair["formula_sha256"]==cases[name]["formula_sha256"] and abs(float(pair["monitor_par2_s"])-totals[(name,"monitor")])<.0002 and abs(float(pair["treatment_par2_s"])-totals[(name,mode)])<.0002,"paired PAR2 "+name+"/"+mode)
    for rep in range(3):
     for mode in NEW:
      d=didx[(cat,name,rep,mode)];r=row_map[(name,mode,rep)]
      check(d["fold"]==fold and d["mean_native"]==r["r18_native_mean"] and d["sigma_native"]==r["r18_native_sigma"] and d["lower_native"]==r["r18_native_lower"] and d["selected"]==r["r18_selected"] and d["actual_switch_at"]==r["switch_at"],"native decision audit "+name+"/"+mode)
   dataset="DRNAS-R18-"+cat
   check(db.execute("SELECT COUNT(*) FROM datasets WHERE dataset=?",(dataset,)).fetchone()[0]==0,"dataset dedup "+dataset)
   provenance="generated_"+family+"_"+fold.split("_")[-1]
   db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",(dataset,provenance,"R18 prospective native direct-gain uncertainty; synthetic NOT official; UNSAT uncertified",RUN,COMMIT,m["runner"],12,aggregate_sha))
   for name,c in cases.items():
    db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",(dataset,name,fold,"UNKNOWN",c["formula_sha256"],None,c.get("path"),c["n"],c["metadata"]["features"]["clauses"]))
    db.execute("INSERT INTO r18_formula_features VALUES (?,?,?,?,?,?,?,?,?)",(dataset,name,c["formula_sha256"],sha(folder/"manifest.json"),fold,c["metadata"]["seed"],c["source_revision"],json.dumps(c["metadata"],sort_keys=True),sha(root/"aggregate/formula_features.csv")))
   for r in rows:
    name,mode,rep=key(r);status=r["status"];sat=flag(r["sat_model_checked"]);unsat=flag(r["unsat_certificate_checked"])
    verified=1 if (status=="SAT" and sat==1) or (status=="UNSAT" and unsat==1) else 0 if status=="TIMEOUT" else None
    tier="sat_witness" if status=="SAT" else "independent_unsat_certificate" if unsat==1 else "unsat_label_only" if status=="UNSAT" else "timeout"
    db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(dataset,name,mode,rep,float(r["wall_s"]),status,verified,r.get("expected_action"),sat,unsat,float(r["par2_s"]),integer(r["exit_code"])))
    db.execute("INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",(dataset,name,mode,rep,m["runner"],r["seed"],cases[name]["source_revision"],r["formula_sha256"],rowsha(r),tier))
    db.execute("INSERT INTO r6_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(dataset,name,mode,rep,None,number(r["early_g"]),number(r["early_p"]),number(r["early_d"]),None,int(bool(r["switch_at"])),integer(r["switch_at"]),integer(r["final_conflicts"]),integer(r["final_restarts"]),integer(r["trace_points"])))
    db.execute("INSERT INTO r18_native_details VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(dataset,name,mode,rep,number(r["cpu_s"]),integer(r["switch_at"]),rowsha(r),number(r["r18_native_mean"]),number(r["r18_python_mean"]),number(r["r18_native_sigma"]),number(r["r18_python_sigma"]),number(r["r18_native_lower"]),number(r["r18_python_lower"]),integer(r["r18_selected"]),MODEL,PROTOCOL))
   for t in traces:
    name,mode,rep=key(t)
    for i,pt in enumerate(t["points"]):
     db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",(dataset,name,mode,rep,i,None,integer(pt.get("conflict")),integer(pt.get("propagations")),integer(pt.get("restarts")),integer(pt.get("learned")),number(pt.get("glue"))))
   db.execute("INSERT INTO source_artifacts VALUES (?,?,?,?,?,?,?,?,?)",(dataset,RUN,COMMIT,index["r18-"+cat],sha(folder/"measurements.csv"),aggregate_sha,m["runner"],provenance,"R18 native synthetic; SAT witness verified; UNSAT uncertified"))
   sources.append(dict(dataset=dataset,run=RUN,commit=COMMIT,runner=m["runner"],artifact_id=index["r18-"+cat],fold=fold,formulas=10,attempts=270,measurements_sha256=sha(folder/"measurements.csv"),manifest_sha256=sha(folder/"manifest.json"),traces_sha256=sha(folder/"traces.jsonl"),aggregate_sha256=aggregate_sha))
   nrows+=len(rows)
  check((len(unique),nrows,len(sources))==(160,4320,16),"final 16-shard dimensions")
  after={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("datasets","formulas","attempts")}
  check(after==dict(datasets=183,formulas=2499,attempts=44210),"cumulative counts "+str(after))
  check(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","new SQLite integrity")
  check(db.execute("SELECT COUNT(*) FROM r18_native_details").fetchone()[0]==4320,"R18 raw details")
  check(db.execute("SELECT COUNT(*) FROM (SELECT formula_sha256 FROM formulas WHERE dataset LIKE 'DRNAS-R18-%' GROUP BY formula_sha256 HAVING COUNT(*)>1)").fetchone()[0]==0,"R18 SHA dedup")
  db.commit()
  export(out/"r18_source_audit.csv",sources)
  export(out/"r18_formula_features.csv",feats)
  export(out/"r18_paired.csv",paired)
  export(out/"r18_native_decisions.csv",decisions)
  for table in ("datasets","formulas"):
   q=db.execute("SELECT * FROM "+table+" ORDER BY 1,2");cols=[c[0] for c in q.description]
   export(out/(table+".csv"),[dict(zip(cols,r)) for r in q])
  try:
   import matplotlib;matplotlib.use("Agg");import matplotlib.pyplot as plt
   for fold in ("random3_development","random3_test","community3_development","community3_test"):
    fig,ax=plt.subplots(figsize=(8,6))
    for mode in ("r16_live50","r17_risk30","r17_risk45",*NEW):
     rr=[r for r in paired if r["fold"]==fold and r["mode"]==mode]
     ax.scatter([float(r["monitor_par2_s"]) for r in rr],[float(r["treatment_par2_s"]) for r in rr],s=12,alpha=.45,label=mode)
    ax.plot([.0001,24],[.0001,24],"--",linewidth=.7,color="black")
    ax.set(xscale="log",yscale="log",xlabel="Monitor paired PAR-2 (s)",ylabel="R18 paired PAR-2 (s)",title="R18 "+fold+" synthetic, not official")
    ax.legend();fig.tight_layout();fig.savefig(out/("scatter_r18_"+fold+".png"),dpi=130);plt.close(fig)
  except ImportError:pass
  audit=dict(status="VERIFIED_R18_TRUE_NATIVE_INGEST",run=RUN,commit=COMMIT,baseline=before,after=after,unique_new_formula_sha256=160,new_native_attempts=4320,paired_formula_comparisons=1280,raw_shards=16,model_sha256=MODEL,protocol_sha256=PROTOCOL,max_native_python_delta=max_parity,source_artifacts=sources,limitations="Generated random3/community3, not official. SAT witnesses verified; UNSAT without independent certificate. R18 native live, not off-policy replay.")
  (out/"r18_ingest_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
  sp=out/"summary.json";summary=json.loads(sp.read_text()) if sp.exists() else {}
  summary["r18_verified_ingest"]={k:v for k,v in audit.items() if k!="source_artifacts"}
  q=db.execute("SELECT * FROM datasets ORDER BY dataset");cols=[c[0] for c in q.description]
  summary["datasets"]=[dict(zip(cols,r)) for r in q]
  sp.write_text(json.dumps(summary,indent=2)+"\n")
  print("R18_VERIFIED_CUMULATIVE_SQLITE_SUCCESS",json.dumps({"before":before,"after":after,"new_native_attempts":4320,"unique_new_formula_sha256":160,"max_C_Python_delta":max_parity}),flush=True)
 finally:db.close()
if __name__=="__main__":main()
