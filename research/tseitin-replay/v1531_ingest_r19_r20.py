#!/usr/bin/env python3
"""Append only fully audited R19/R20 raw native SAT attempts; never edit solver."""
import argparse,csv,hashlib,json,math,sqlite3,statistics
from pathlib import Path
from collections import defaultdict

RUNS={19:("41492265486","4f5d5973fef71f932d942e8705e94e6d78eaec59",
 ("monitor","r11_2048_50","r16_live50","original_kissat"),1920),
 20:("41496548082","aaf685223d5438c16ebba749dd7ac91fae9d92b5",
 ("monitor","r11_2048_50","r16_live50","r20_local50","r20_inverse50","original_kissat","stable_v1531"),3360)}
SHARDS=[f"n{n}_{phase}{i}" for n in (200,220,240) for phase in ("development","test") for i in (0,1)]+[f"community_n{n}_{phase}0" for n in (220,240) for phase in ("development","test")]
FOLDS=("random3_development","random3_test","community3_development","community3_test")
KISSAT="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
STABLE="d280a2ffa28d72aec183323bbea40544d676112d"
def need(ok,msg):
 if not ok:raise RuntimeError("STRICT_R19_R20_INGEST_FAIL "+str(msg))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def csvread(p):
 with p.open(newline="") as f:return list(csv.DictReader(f))
def fold(shard):
 return ("community3_" if shard.startswith("community_") else "random3_")+("development" if "_development" in shard else "test")
def number(x):return float(x) if x not in ("",None) else None
def integer(x):return int(x) if x not in ("",None) else None
def flag(x):return 1 if str(x).lower() in ("true","1") else 0 if str(x).lower() in ("false","0") else None
def export(path,rows):
 if rows:
  with path.open("w",newline="") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 ap=argparse.ArgumentParser()
 for name in ("db","input","out"):ap.add_argument("--"+name,type=Path,required=True)
 ap.add_argument("--round",type=int,choices=(19,20),required=True)
 args=ap.parse_args();v=args.round;root=args.input;out=args.out
 run,commit,modes,count=RUNS[v]
 reportpath=root/"aggregate/results.json";report=json.loads(reportpath.read_text())
 need(report["attempts"]==count and report["formulas"]==160,"aggregate dimensions")
 need(len(report["source_artifacts"])==16,"source list incomplete")
 need(v!=19 or (report["model_kind"]=="OFF_POLICY_PREDICTIVE_VALIDATION_NOT_A_LIVE_R19_GATE" and report["preintervention_parity"] is True and report["no_overlapping_historical_formulas"] is True),"R19 replay labeling/prefix")
 need(v!=20 or (report["kind"]=="R20_TRUE_NATIVE_LOCAL_CLAUSE_REUSE_GATE_PROSPECTIVE" and report["repeats"]==3 and tuple(report["modes"])==modes and report["historical_hash_overlap"]==0 and report["preintervention_prefix_mismatch"]==0 and report["native_python_gate_mismatches"]==0 and len(report["manifests"])==16),"R20 native aggregate audit")
 index={}
 for line in (root/"artifact_index.tsv").read_text().splitlines():
  name,aid,expired=line.split("\t")[:3]
  need(name not in index and expired=="false","expired/duplicate artifact "+name)
  index[name]=int(aid)
 expected_artifacts=18 if v==19 else 17
 need(len(index)==expected_artifacts,"artifact index count")
 aggregate_name="DRNAS-R19-Blind-Snapshot-vs-Dynamics-Results" if v==19 else "DRNAS-R20-Local-Clause-Utility-Real-Native-Analysis"
 need(aggregate_name in index,"aggregate artifact absent")
 if v==19:
  need("R19-DEV-FROZEN-MODELS" in index,"R19 frozen training artifact absent")
  model=root/"aggregate/r19_frozen_models.json"
  need(digest(model)==report["frozen_model_sha256"],"R19 frozen model SHA")
  frozen=json.loads(model.read_text())
  need(frozen["training_fold"]=="random3_development" and frozen["training_formula_count"]==report["training_formula_count"] and len(frozen["models"])==2,"R19 training provenance")
  preds=csvread(root/"aggregate/predictions.csv")
  need(len(preds)==160 and len({r["formula_sha256"] for r in preds})==160,"R19 offpolicy predictions")
 else:
  features=csvread(root/"aggregate/formula_features.csv")
  paired=csvread(root/"aggregate/paired.csv")
  decisions=csvread(root/"aggregate/native_local_decisions.csv")
  need((len(features),len(paired),len(decisions))==(160,960,960),"R20 aggregate CSV dimensions")
  fidx={(r["shard"],r["formula"]):r for r in features}
  pidx={(r["formula"],r["mode"]):r for r in paired}
  need(len(fidx)==160 and len(pidx)==960,"R20 aggregate keys")
 source={r["shard"]:r for r in report["source_artifacts"]}
 need(set(source)==set(SHARDS),"16 exact source shards")
 if v==20:
  manifest_index={r["category"]:r for r in report["manifests"]}
  need(set(manifest_index)==set(SHARDS),"aggregate manifests")
 db=sqlite3.connect(args.db)
 try:
  db.execute("PRAGMA foreign_keys=ON")
  need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","historical SQLite integrity")
  before={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("datasets","formulas","attempts")}
  expected_before={19:(183,2499,44210),20:(199,2659,46130)}[v]
  need(tuple(before.values())==expected_before,"unexpected cumulative baseline "+str(before))
  prior={x for (x,) in db.execute("SELECT formula_sha256 FROM formulas") if x}
  db.execute("""CREATE TABLE IF NOT EXISTS r19_r20_raw_details(
    dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,round INTEGER,
    raw_row_sha256 TEXT,trace_sha256 TEXT,source_manifest_sha256 TEXT,
    source_commit TEXT,source_runner TEXT,source_seed TEXT,
    model_kind TEXT,raw_json TEXT,
    PRIMARY KEY(dataset,case_name,solver,repeat))""")
  if v==19:
   db.execute("""CREATE TABLE IF NOT EXISTS r19_offpolicy_predictions(
    dataset TEXT,case_name TEXT,formula_sha256 TEXT,model_sha256 TEXT,
    prediction_json TEXT,PRIMARY KEY(dataset,case_name))""")
  else:
   db.execute("""CREATE TABLE IF NOT EXISTS r20_native_local_decisions(
    dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,
    decision_json TEXT,PRIMARY KEY(dataset,case_name,solver,repeat))""")
  audit_sources=[];unique=set();total=0;paired_rows=[];raw_groups=defaultdict(dict)
  aggregate_sha=digest(reportpath)
  for shard in SHARDS:
   name=("r19-dev-" if "_development" in shard else "r19-test-")+shard if v==19 else "r20-"+shard
   need(name in index,"missing artifact "+name)
   folder=root/"shards"/shard
   manifestpath=folder/"manifest.json";measurepath=folder/"measurements.csv";tracepath=folder/"traces.jsonl"
   for path in (manifestpath,measurepath,tracepath):need(path.is_file(),"missing raw "+str(path))
   m=json.loads(manifestpath.read_text());rows=csvread(measurepath)
   traces=[json.loads(x) for x in tracepath.read_text().splitlines() if x.strip()]
   src=source[shard];nrows=10*3*len(modes)
   need(len(rows)==len(traces)==nrows and len(m["cases"])==10,"incomplete "+shard)
   need(m["category"]==shard and m["source_commit"]==src["source_commit"]==commit and m["runner"]==src["runner"],"commit/runner "+shard)
   need(m["fold"]==fold(shard) and m["cpu_affinity"]==[m["cpu_core"]] and m["cap_seconds"]==12 and m["repeats"]==3 and tuple(m["modes"])==modes,"CPU/mode/fold "+shard)
   need(m["kissat_pin"]==KISSAT and m["protocol"]==report["protocol"],"Kissat/protocol "+shard)
   need(m["protocol_sha256"]==(report.get("protocol_sha256") if v==20 else m["protocol_sha256"]),"protocol SHA "+shard)
   need(m["historic_count"]==(2574 if v==19 else 2734),"historic registry "+shard)
   if v==19:
    need(m["stable_source_blob"]==STABLE and m["executable_sha256"]==src["binaries"],"R19 binary SHA "+shard)
    need(digest(measurepath)==src["measures_sha256"] and digest(tracepath)==src["trace_sha256"] and digest(manifestpath)==src["manifest_sha256"],"R19 raw SHA "+shard)
    if "_test" in shard:need(m["frozen_model_sha256"]==report["frozen_model_sha256"],"R19 blind frozen pin")
   else:
    need(m["v1531_blob"]==STABLE and m["executables"]==src["binaries_sha256"],"R20 binary SHA "+shard)
    need(m==manifest_index[shard],"R20 aggregate manifest equality")
    need(digest(measurepath)==src["measurement_sha256"] and digest(tracepath)==src["trace_sha256"] and digest(manifestpath)==src["manifest_sha256"],"R20 raw SHA "+shard)
   cases={c["formula"]:c for c in m["cases"]}
   need(len(cases)==10,"duplicate case "+shard)
   rawidx={(r["formula"],r["mode"],int(r["repeat"])):r for r in rows}
   traceidx={(t["formula"],t["mode"],int(t["repeat"])):t for t in traces}
   keys={(c,mode,rep) for c in cases for mode in modes for rep in range(3)}
   need(len(rawidx)==len(traceidx)==len(keys) and set(rawidx)==set(traceidx)==keys,"paired matrix "+shard)
   statuses=defaultdict(set);sums=defaultdict(float)
   for c in cases.values():
    h=c["formula_sha256"]
    need(len(h)==64 and h not in prior and h not in unique,"SHA dedup "+h)
    need((folder/c["formula"]).is_file() and digest(folder/c["formula"])==h,"raw CNF SHA "+c["formula"])
    need(c["dataset_type"]=="generated_prospective" and c["expected"]=="UNKNOWN" and c["metadata"]["seed"] is not None,"formula provenance")
    need(c["metadata"]["family"]==fold(shard).split("_")[0] and c["metadata"]["fold"] in fold(shard),"family/fold")
    unique.add(h)
   dataset=f"DRNAS-R{v}-"+shard
   need(db.execute("SELECT COUNT(*) FROM datasets WHERE dataset=?",(dataset,)).fetchone()[0]==0,"duplicate dataset")
   provenance="generated_"+fold(shard)
   db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",(dataset,provenance,f"R{v} prospective native synthetic; R19 learned predictions offpolicy only; SAT witnesses checked, UNSAT uncertified",run,commit,m["runner"],12,aggregate_sha))
   for c in cases.values():
    db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",(dataset,c["formula"],fold(shard),"UNKNOWN",c["formula_sha256"],None,c.get("path"),c["n"],c["metadata"]["features"].get("clauses")))
   for key in sorted(keys):
    cname,mode,rep=key;r=rawidx[key];t=traceidx[key];c=cases[cname];status=r["status"]
    need(r["formula_sha256"]==c["formula_sha256"] and r["seed"]==str(c["metadata"]["seed"]) and r["runner"]==m["runner"],"row SHA/seed/runner")
    need(r["category"]==shard and r["fold"]==fold(shard) and status in ("SAT","UNSAT","TIMEOUT"),"row fold/status")
    need(not r["error"] and not r["r16_decision_error"],"native error")
    if v==19:need(r["r19_protocol_sha256"]==m["protocol_sha256"],"R19 protocol row")
    else:need(not r["r20_error"] and r["r20_protocol_sha256"]==m["protocol_sha256"],"R20 protocol row")
    if status=="SAT":need(flag(r["sat_model_checked"])==1,"SAT witness")
    if status!="TIMEOUT":statuses[cname].add(status)
    wall=float(r["wall_s"]);par2=float(r["par2_s"])
    need(math.isfinite(wall) and wall>=0 and math.isfinite(par2) and abs(par2-(24.0 if status=="TIMEOUT" else wall))<1e-5,"PAR2")
    need(len(t["points"])==int(r["trace_points"]),"raw trace link")
    sums[(cname,mode)]+=par2
    sat=flag(r["sat_model_checked"]);unsat=flag(r.get("unsat_certificate_checked"))
    verified=1 if (status=="SAT" and sat==1) or (status=="UNSAT" and unsat==1) else 0 if status=="TIMEOUT" else None
    tier="sat_witness" if status=="SAT" else "unsat_label_only" if status=="UNSAT" else "timeout"
    db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(dataset,cname,mode,rep,wall,status,verified,r.get("expected_action"),sat,unsat,par2,integer(r.get("exit_code"))))
    db.execute("INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",(dataset,cname,mode,rep,m["runner"],r["seed"],c.get("source_revision"),c["formula_sha256"],canonical(r),tier))
    db.execute("INSERT INTO r19_r20_raw_details VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",(dataset,cname,mode,rep,v,canonical(r),canonical(t),digest(manifestpath),commit,m["runner"],r["seed"],"R19_OFFPOLICY_ONLY" if v==19 else "R20_LIVE_NATIVE",json.dumps(r,sort_keys=True)))
    for i,pt in enumerate(t["points"]):
     db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",(dataset,cname,mode,rep,i,None,integer(pt.get("conflict")),integer(pt.get("propagations")),integer(pt.get("restarts")),integer(pt.get("learned")),number(pt.get("glue"))))
    raw_groups[(dataset,cname,rep)][mode]=r
   need(all(len(z)<=1 for z in statuses.values()),"SAT/UNSAT contradiction "+shard)
   for cname,c in cases.items():
    if v==20:
     f=fidx[(shard,cname)]
     need(f["formula_sha256"]==c["formula_sha256"] and f["fold"]==fold(shard) and f["seed"]==str(c["metadata"]["seed"]),"R20 features audit")
     for mode in modes:
      need(abs(float(f[mode])-sums[(cname,mode)])<.0002,"R20 aggregate PAR2")
      if mode!="monitor":
       p=pidx[(cname,mode)]
       need(p["formula_sha256"]==c["formula_sha256"] and p["fold"]==fold(shard) and abs(float(p["monitor_PAR2_s"])-sums[(cname,"monitor")])<.0002 and abs(float(p["treatment_PAR2_s"])-sums[(cname,mode)])<.0002,"R20 paired sums")
    else:
     p=next((x for x in preds if x["formula"]==cname),None)
     need(p is not None and p["formula_sha256"]==c["formula_sha256"] and p["fold"]==fold(shard),"R19 prediction linkage")
     need(abs(float(p["monitor_par2"])-sums[(cname,"monitor")])<.0002 and abs(float(p["force50_par2"])-sums[(cname,"r11_2048_50")])<.0002,"R19 native sums")
     db.execute("INSERT INTO r19_offpolicy_predictions VALUES (?,?,?,?,?)",(dataset,cname,c["formula_sha256"],report["frozen_model_sha256"],json.dumps(p,sort_keys=True)))
    for mode in modes:
     if mode!="monitor":paired_rows.append(dict(fold=fold(shard),formula_sha256=c["formula_sha256"],solver=mode,monitor_par2=sums[(cname,"monitor")],treatment_par2=sums[(cname,mode)]))
   db.execute("INSERT INTO source_artifacts VALUES (?,?,?,?,?,?,?,?,?)",(dataset,run,commit,index[name],digest(measurepath),aggregate_sha,m["runner"],provenance,f"R{v} generated prospective; NOT official; UNSAT no independent certificate"))
   audit_sources.append(dict(dataset=dataset,run=run,commit=commit,runner=m["runner"],artifact_id=index[name],fold=fold(shard),formulas=10,attempts=nrows,manifest_sha256=digest(manifestpath),measurements_sha256=digest(measurepath),traces_sha256=digest(tracepath),aggregate_sha256=aggregate_sha))
   total+=nrows
  need(len(unique)==160 and total==count and len(audit_sources)==16,"full verified dimensions")
  for (dataset,cname,rep),by in raw_groups.items():
   need(set(by)==set(modes),"missing paired mode")
   if v==20:
    # Cross-mode state equivalence before the frozen intervention at 1024 conflicts.
    shard=dataset.split(f"DRNAS-R{v}-",1)[1]
    folder=root/"shards"/shard
    # Exact per-row parity was checked in source R20 aggregate; independently require aggregate zero mismatches.
  if v==20:
   dmap={(r["formula"],r["arm"],int(r["repeat"])):r for r in decisions}
   need(len(dmap)==960,"R20 decision unique keys")
   for (dataset,cname,rep),by in raw_groups.items():
    for mode in ("r20_local50","r20_inverse50"):
     d=dmap[(cname,mode,rep)];r=by[mode]
     need(d["selected"]==r["r20_python_selected"] and d["actual_switch_at"]==r["switch_at"] and d["native_event"]==r["r20_native_decision"],"R20 C/Python decision parity")
     db.execute("INSERT INTO r20_native_local_decisions VALUES (?,?,?,?,?)",(dataset,cname,mode,rep,json.dumps(d,sort_keys=True)))
  after={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in ("datasets","formulas","attempts")}
  target={19:(199,2659,46130),20:(215,2819,49490)}[v]
  need(tuple(after.values())==target,"final cumulative counts "+str(after))
  need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","new SQLite integrity")
  need(db.execute("SELECT COUNT(DISTINCT formula_sha256) FROM formulas WHERE dataset LIKE ?",(f"DRNAS-R{v}-%",)).fetchone()[0]==160,"SHA uniqueness")
  db.commit()
  out.mkdir(parents=True,exist_ok=True)
  export(out/f"r{v}_source_audit.csv",audit_sources)
  export(out/f"r{v}_paired.csv",paired_rows)
  if v==19:export(out/"r19_offpolicy_predictions.csv",preds)
  else:
   export(out/"r20_formula_features.csv",features)
   export(out/"r20_native_local_decisions.csv",decisions)
  try:
   import matplotlib;matplotlib.use("Agg")
   import matplotlib.pyplot as plt
   for group in FOLDS:
    fig,ax=plt.subplots(figsize=(7,5))
    for mode in modes:
     if mode=="monitor":continue
     pp=[p for p in paired_rows if p["fold"]==group and p["solver"]==mode]
     ax.scatter([p["monitor_par2"] for p in pp],[p["treatment_par2"] for p in pp],s=10,alpha=.4,label=mode)
    ax.plot([.0001,24],[.0001,24],"--",color="black",linewidth=.7)
    ax.set(xscale="log",yscale="log",xlabel="Monitor paired PAR-2 (s)",ylabel="Treatment paired PAR-2 (s)",title=f"R{v} {group} — generated, not official")
    ax.legend(fontsize=7);fig.tight_layout()
    fig.savefig(out/f"scatter_r{v}_{group}.png",dpi=130);plt.close(fig)
  except ImportError:raise RuntimeError("matplotlib missing: scatterplots required")
  audit=dict(status=f"VERIFIED_R{v}_ADDITIVE_NATIVE_INGEST",run=run,commit=commit,baseline=before,after=after,unique_new_formula_sha256=160,new_native_attempts=count,raw_shards=16,paired_formula_comparisons=len(paired_rows),aggregate_sha256=aggregate_sha,source_artifacts=audit_sources,limitations="Synthetic generated random3/community3, not official. SAT witness verified, UNSAT no independent proof. R19 prediction replay not live acceleration." if v==19 else "Synthetic generated random3/community3, not official. SAT witness verified, UNSAT no independent proof. R20 real native gate.")
  (out/f"r{v}_ingest_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
  for table in ("datasets","formulas"):
   q=db.execute("SELECT * FROM "+table+" ORDER BY 1,2");cols=[x[0] for x in q.description]
   export(out/(table+".csv"),[dict(zip(cols,row)) for row in q])
  sp=out/"summary.json";summary=json.loads(sp.read_text()) if sp.exists() else {}
  summary[f"r{v}_verified_ingest"]={k:x for k,x in audit.items() if k!="source_artifacts"}
  q=db.execute("SELECT * FROM datasets ORDER BY dataset");cols=[x[0] for x in q.description]
  summary["datasets"]=[dict(zip(cols,row)) for row in q]
  sp.write_text(json.dumps(summary,indent=2)+"\n")
  print(f"R{v}_VERIFIED_CUMULATIVE_SQLITE_SUCCESS",json.dumps({"before":before,"after":after,"native_attempts":count}),flush=True)
 finally:db.close()
if __name__=="__main__":main()
