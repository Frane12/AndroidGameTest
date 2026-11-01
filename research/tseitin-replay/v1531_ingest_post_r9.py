#!/usr/bin/env python3
"""Append verified post-R9 R10/learned-selector/SC2023 measurements, never solver code.

All new datasets have immutable GitHub run/commit/artifact provenance. Original
SC2023 formulas are official *sources*, not an official competition submission.
R10/selector generated test formulas are not globally independent evidence.
"""
import argparse,csv,hashlib,json,sqlite3,statistics
from collections import defaultdict
from pathlib import Path
import v1531_analytics_db as base
import v1531_ingest_new as old
import v1531_ingest_r7_crossfamily as r7

R10_RUN="41357285023";R10_SHA="553340f1bcd1e72813e2aadd52b61372cd439676"
SEL_RUN="41357661885";REAL_RUN="41357661925"
SEL_SHA="2a377025e690a414dfb06992e91ead7b0b497a1f"
R10_SHARDS=[f"n{n}_{fold}{i}" for n in (200,220,240) for fold in ("development","test") for i in range(2)]
SEL_CATS=("random3","graphcolor","xor","external_satlib")
R10_MODES=("original_kissat","stable_v1531","monitor","forced_restart25","structure_gate")
SEL_MODES=("monitor","stable_v1531","selector")
REAL_MODES=("monitor","stable_v1531","selector","kissat_original")
R10_AIDS={
"n200_development0":13103667812,"n200_development1":13104280055,
"n200_test0":13103174820,"n200_test1":13103961852,
"n220_development0":13103389315,"n220_development1":13103862077,
"n220_test0":13104055833,"n220_test1":13103752777,
"n240_development0":13104355524,"n240_development1":13103578858,
"n240_test0":13104022359,"n240_test1":13103528856}
SEL_AIDS={"random3":13103509012,"graphcolor":13103786851,"xor":13104300579,"external_satlib":13104051163}
REAL_AIDS={0:13104450483,1:13103728204,2:13104201356,3:13104295882,4:13104350707,5:13104420242}

def check(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
 with p.open(newline="") as f:return list(csv.DictReader(f))
def traces(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def num(x):return float(x)
def asint(x):
 try:return int(x)
 except (ValueError,TypeError):return None
def flag(x):
 return 1 if str(x).lower() in ("true","1") else 0 if str(x).lower() in ("false","0") else None
def rowsha(r):return hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def validate_sha(s):return isinstance(s,str) and len(s)==64 and all(c in "0123456789abcdef" for c in s.lower())

def ingest_one(db,kind,shard,folder,run,commit,aid,cap,modes,provenance,report_path,
               expected_file_hashes=None,real_cases=None):
 csvp=folder/"measurements.csv";mp=folder/"manifest.json";tp=folder/"traces.jsonl"
 check(all(p.is_file() for p in (csvp,mp,tp)),"Missing measured shard "+str(folder))
 if expected_file_hashes:
  for fn,key in (("measurements.csv","measurements_sha256"),
                 ("manifest.json","manifest_sha256"),("traces.jsonl","traces_sha256")):
   check(sha(folder/fn)==expected_file_hashes[key],"Published R10 SHA mismatch "+shard+"/"+fn)
 manifest=json.loads(mp.read_text());rs=rows(csvp);ts=traces(tp)
 check(manifest["source_commit"]==commit,"Source commit mismatch "+shard)
 cases={c["formula"]:c for c in manifest["cases"]}
 check(len(cases)==(2 if kind=="SC2023" else 10 if kind=="R10" else 25),
       "Formula count mismatch "+shard)
 check(len({c.get("formula_sha256",c.get("sha256")) for c in cases.values()})==len(cases),
       "Duplicate formula SHA within shard")
 check(len(rs)==len(cases)*3*len(modes),"Attempt count mismatch "+shard)
 check(len(ts)==len(rs),"Trace count mismatch "+shard)
 key=lambda r:(r["formula"],r["mode"],int(r["repeat"]))
 keys={key(r) for r in rs}
 check(keys=={(name,mode,i) for name in cases for mode in modes for i in range(3)}
       and len(keys)==len(rs),"Incomplete or duplicate paired matrix "+shard)
 check({key(t) for t in ts}==keys and len({key(t) for t in ts})==len(ts),
       "Trace/attempt mismatch "+shard)
 if kind=="R10":
  check(manifest["category"]==shard and manifest["cap_seconds"]==cap and
        tuple(manifest["modes"])==modes and manifest["repeats"]==3,
        "R10 frozen protocol mismatch "+shard)
  check(len(manifest.get("executables",{}))==3,"R10 binary hashes missing")
 if kind=="SC2023":
  check(len(manifest.get("executables",{}))==4,"SC2023 executable hashes missing")
  check(real_cases is not None and
        {c["formula"] for c in manifest["cases"]}==set(real_cases),
        "SC2023 frozen case mismatch")
 bycase=defaultdict(set)
 for r in rs:
  f=cases[r["formula"]];s=r["status"];wall=num(r["wall_s"]);par2=num(r["par2_s"])
  check(not r.get("error") and s in ("SAT","UNSAT","TIMEOUT"),
        "Invalid status/error "+shard)
  check(r["formula_sha256"]==f.get("formula_sha256",f.get("sha256")) and
        validate_sha(r["formula_sha256"]),"Attempt/formula SHA mismatch "+shard)
  check(r["expected"]==f.get("expected") and
        (r["category"]==shard if kind=="R10" else
         r["category"]==f.get("family") if kind=="SC2023" else
         r["category"]==shard),"Category/expected mismatch "+shard)
  check(wall>=0 and par2>=0 and
        abs(par2-(wall if s!="TIMEOUT" else 2*cap))<.002,
        "Incorrect PAR-2 "+shard)
  if s in ("SAT","UNSAT"):
   bycase[r["formula"]].add(s)
   check(f.get("expected") in ("UNKNOWN",s),"Known label contradicted "+shard)
   if s=="SAT":check(flag(r.get("sat_model_checked"))==1,
                     "SAT witness not checked "+shard)
  if kind=="R10":
   check(r["runner"]==manifest["runner"],"R10 runner mismatch")
   check(r.get("structure_gate_selected") in ("0","1"),"R10 gate missing")
   check(int(r["structure_gate_selected"])==int(f["metadata"]["structure_gate_selected"]),
         "R10 frozen selection mismatch")
   if r["mode"]=="structure_gate":
    exp="forced_restart25" if f["metadata"]["structure_gate_selected"] else "monitor"
    check(r["actual_execution"]==exp,"R10 action mismatch")
   seed=f["metadata"]["seed"]
   check(str(r["seed"])==str(seed),"R10 seed mismatch")
  if kind=="SC2023":
   check(r["runner"]=="SC2023 paired worker "+shard,"SC2023 runner mismatch")
   if r["mode"]=="selector":
    check(r.get("route") in ("stable_v1531","monitor"),"SC2023 selector route invalid")
  check(not r.get("error"),"Nonempty solver error")
 check(all(len(v)<=1 for v in bycase.values()),"SAT/UNSAT disagreement "+shard)
 dataset="DRNAS-"+kind+"-"+shard
 runner=manifest.get("runner") or "SC2023 paired worker "+shard
 check(all(validate_sha(c.get("formula_sha256",c.get("sha256"))) for c in cases.values()),
       "Formula hash missing "+shard)
 existing=db.execute("SELECT source_run,source_sha,json_sha256 FROM datasets WHERE dataset=?",
                     (dataset,)).fetchone()
 if existing:
  check(tuple(existing)==(run,commit,sha(csvp)) and
        db.execute("SELECT COUNT(*) FROM attempts WHERE dataset=?",(dataset,)).fetchone()[0]==len(rs),
        "Changed prior dataset "+dataset)
 else:
  db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
    (dataset,provenance,kind+" measured paired run; nonofficial comparison; UNSAT labels are not independent proofs",
     run,commit,runner,cap,sha(csvp)))
  for name,f in cases.items():
   meta=f.get("metadata",{})
   db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",
    (dataset,name,shard if kind!="SC2023" else f.get("family"),f.get("expected"),
     f.get("formula_sha256",f.get("sha256")),
     f.get("canonical_sha256",meta.get("raw_source_sha256")),
     f.get("source_url",f.get("path")),f.get("n",f.get("variables")),
     f.get("clauses") if isinstance(f.get("clauses"),int) else meta.get("structural",{}).get("m")))
  for r in rs:
   case,mode,rep=key(r);status=r["status"]
   satok=flag(r.get("sat_model_checked"));unsatok=flag(r.get("native_unsat_certificate_checked"))
   verified=1 if (status=="SAT" and satok==1) or (status=="UNSAT" and unsatok==1) else (0 if status=="TIMEOUT" else None)
   tier="sat_witness" if satok==1 else "native_unsat_certificate" if unsatok==1 else "unsat_label_only" if status=="UNSAT" else "timeout"
   db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
    (dataset,case,mode,rep,num(r["wall_s"]),status,verified,r.get("route"),satok,unsatok,
     num(r["par2_s"]),asint(r.get("exit_code"))))
   db.execute("INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",
    (dataset,case,mode,rep,r["runner"],r.get("seed"),r.get("source_revision"),
     r["formula_sha256"],rowsha(r),tier))
   db.execute("INSERT INTO r6_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    (dataset,case,mode,rep,asint(r.get("early_restarts")),r7.asfloat(r.get("early_g")),
     r7.asfloat(r.get("early_p")),r7.asfloat(r.get("early_d")),flag(r.get("gate_eligible")),
     flag(r.get("gate_action")),asint(r.get("switch_at")),
     asint(r.get("final_conflicts")),asint(r.get("final_restarts")),asint(r.get("trace_points"))))
  for t in ts:
   case,mode,rep=key(t)
   for idx,pt in enumerate(t.get("points",[])):
    db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,case,mode,rep,idx,None,asint(pt.get("conflict")),
      asint(pt.get("propagations")),asint(pt.get("restarts")),
      asint(pt.get("learned")),r7.asfloat(pt.get("glue"))))
 old.source(db,dataset,run,commit,aid,csvp,sha(report_path),runner,provenance,
  "Nonofficial paired test; SAT witnesses checked; UNSAT certificates may be absent. "+
  ("Official SC2023 source, selected by known difficulty, not a blind competition submission."
   if kind=="SC2023" else "Generated or public source; not a global novelty claim."))
 manifest_sha=sha(mp)
 for name,f in cases.items():
  meta=f.get("metadata",{})
  oldrow=db.execute("SELECT formula_sha256,manifest_sha256 FROM post_r9_formula_features WHERE dataset=? AND case_name=?",(dataset,name)).fetchone()
  feat=(dataset,name,f.get("formula_sha256",f.get("sha256")),manifest_sha,
        f.get("source",f.get("source_url")),f.get("source_revision"),
        json.dumps(meta,sort_keys=True))
  if oldrow:check(tuple(oldrow)==(feat[2],feat[3]),"Feature metadata conflict")
  else:db.execute("INSERT INTO post_r9_formula_features VALUES (?,?,?,?,?,?,?)",feat)
 return {"dataset":dataset,"new":not bool(existing),"formulas":len(cases),"attempts":len(rs),"provenance":provenance}

def ingest_all(db,root):
 db.execute("""CREATE TABLE IF NOT EXISTS post_r9_formula_features(
  dataset TEXT,case_name TEXT,formula_sha256 TEXT,manifest_sha256 TEXT,
  source TEXT,source_revision TEXT,metadata_json TEXT,
  PRIMARY KEY(dataset,case_name))""")
 info=[];r10=root/"r10";s=root/"selector";real=root/"real"
 r10report=json.loads((r10/"aggregate/results.json").read_text())
 check(r10report["count"]==1800 and r10report["formula_count"]==120 and
       len(r10report["raw_source_sha256"])==12,"R10 incomplete aggregate")
 r10src={x["shard"]:x for x in r10report["raw_source_sha256"]}
 check(set(r10src)==set(R10_SHARDS),"R10 source shard mismatch")
 for shard in R10_SHARDS:
  fold="development" if "_development" in shard else "test"
  info.append(ingest_one(db,"R10",shard,r10/"shards"/shard,R10_RUN,R10_SHA,
     R10_AIDS[shard],12,R10_MODES,"generated_prospective_"+fold,
     r10/"aggregate/results.json",r10src[shard]))
 selreport=json.loads((s/"aggregate/report.json").read_text())
 check(selreport["attempts"]==900 and selreport["formulas"]==100,
       "Learned selector aggregate incomplete")
 protocols=[]
 for cat in SEL_CATS:
  folder=s/"shards"/cat
  protocol=json.loads((folder/"protocol.json").read_text())
  check(protocol["formulas"]==100 and protocol["repeats"]==3 and
        tuple(protocol["modes"])==SEL_MODES and protocol["cap_seconds"]==8,
        "Learned selector frozen protocol mismatch")
  protocols.append(sha(folder/"protocol.json"))
  provenance="external_public_project_hash_new" if cat=="external_satlib" else "generated_holdout"
  info.append(ingest_one(db,"Selector",cat,folder/cat,SEL_RUN,SEL_SHA,
     SEL_AIDS[cat],8,SEL_MODES,provenance,s/"aggregate/report.json"))
 check(len(set(protocols))==1,"Learned selector protocol drift")
 realreport=json.loads((real/"aggregate/report.json").read_text())
 frozen=json.loads((real/"inputs/frozen_manifest.json").read_text())
 check(realreport["attempts"]==144 and realreport["formulas"]==12 and
       len(frozen["cases"])==12 and frozen["cap_seconds"]==15,
       "Real SC2023 source/report mismatch")
 seen=set()
 for i in range(6):
  folder=real/"shards"/str(i)
  manifest=json.loads((folder/"manifest.json").read_text())
  cases={c["formula"]:c for c in manifest["cases"]}
  check(len(cases)==2,"Real shard case count")
  for name,c in cases.items():
   match=next((f for f in frozen["cases"] if f["formula"]==name),None)
   check(match is not None and c["sha256"]==match["sha256"] and name not in seen,
         "SC2023 frozen input mismatch")
   seen.add(name)
  info.append(ingest_one(db,"SC2023",str(i),folder,REAL_RUN,SEL_SHA,
    REAL_AIDS[i],15,REAL_MODES,"official_source_project_new_not_competition",
    real/"aggregate/report.json",real_cases=cases))
 check(len(seen)==12,"SC2023 duplicate across shards")
 return info,{"R10":r10report["summary"],"selector":selreport,"SC2023":realreport,
              "frozen_SC2023_manifest_sha256":sha(real/"inputs/frozen_manifest.json")}

def export(db,out,info,reports,prior_summary):
 grouped,paired,telemetry=base.analytics(db,out)
 base.plot(out,paired,telemetry)
 old.extra(db,out)
 # Frozen R7 metrics are re-exported, without editing old R7 measurements.
 r7.new_pairs(db,out)
 pairs=old.rows(db,"""SELECT a.dataset,a.case_name,a.repeat,a.solver AS treatment,
  m.par2_seconds AS monitor_par2,a.par2_seconds AS treatment_par2,
  CASE WHEN a.par2_seconds>0 THEN m.par2_seconds/a.par2_seconds END AS speedup,
  f.category,d.provenance
  FROM attempts a JOIN attempts m ON m.dataset=a.dataset AND m.case_name=a.case_name
   AND m.repeat=a.repeat AND m.solver='monitor'
  JOIN formulas f ON f.dataset=a.dataset AND f.case_name=a.case_name
  JOIN datasets d ON d.dataset=a.dataset
  WHERE (a.dataset LIKE 'DRNAS-R10-%' OR a.dataset LIKE 'DRNAS-Selector-%'
     OR a.dataset LIKE 'DRNAS-SC2023-%') AND a.solver!='monitor'
  ORDER BY a.dataset,a.case_name,a.repeat,a.solver""")
 # Parenthesize predicate above explicitly: monitor rows should not appear as treatment.
 pairs=[r for r in pairs if r["treatment"]!="monitor"]
 check(len(pairs)==1440+600+108,"Post-R9 paired comparison count")
 base.export_csv(out/"post_r9_paired.csv",pairs,
  ["dataset","case_name","repeat","treatment","monitor_par2","treatment_par2",
   "speedup","category","provenance"])
 summary=[]
 for dataset,mode in sorted({(r["dataset"],r["treatment"]) for r in pairs}):
  rr=[r for r in pairs if r["dataset"]==dataset and r["treatment"]==mode]
  m=sum(r["monitor_par2"] for r in rr);t=sum(r["treatment_par2"] for r in rr)
  summary.append(dict(dataset=dataset,mode=mode,attempt_pairs=len(rr),
    monitor_par2=round(m,8),treatment_par2=round(t,8),speedup=round(m/t,8)))
 base.export_csv(out/"post_r9_paired_summary.csv",summary,
  ["dataset","mode","attempt_pairs","monitor_par2","treatment_par2","speedup"])
 feats=old.rows(db,"SELECT * FROM post_r9_formula_features ORDER BY dataset,case_name")
 check(len(feats)==232,"Post-R9 formula feature count mismatch")
 base.export_csv(out/"post_r9_formula_features.csv",feats,
  ["dataset","case_name","formula_sha256","manifest_sha256","source","source_revision","metadata_json"])
 import matplotlib
 matplotlib.use("Agg")
 import matplotlib.pyplot as plt
 for kind in ("R10","Selector","SC2023"):
  sub=[r for r in pairs if r["dataset"].startswith("DRNAS-"+kind+"-")]
  fig,ax=plt.subplots(figsize=(8,6))
  for mode in sorted({r["treatment"] for r in sub}):
   rr=[r for r in sub if r["treatment"]==mode]
   ax.scatter([r["monitor_par2"] for r in rr],[r["treatment_par2"] for r in rr],
    s=8,alpha=.35,label=mode)
  ax.set_xscale("log");ax.set_yscale("log")
  ax.set(xlabel="Monitor paired PAR-2 (s)",ylabel="Treatment paired PAR-2 (s)",
         title=kind+" post-R9 paired results (nonofficial)")
  ax.legend(fontsize=7);fig.tight_layout()
  fig.savefig(out/("scatter_post_r9_"+kind.lower()+".png"),dpi=145);plt.close(fig)
 r10=[f for f in feats if f["dataset"].startswith("DRNAS-R10-")]
 by=defaultdict(dict)
 for r in pairs:
  if r["dataset"].startswith("DRNAS-R10-"):
   by[(r["dataset"],r["case_name"],r["treatment"])][r["repeat"]]=r["speedup"]
 fig,ax=plt.subplots(figsize=(8,5))
 for fold in ("development","test"):
  x=[];y=[]
  for f in r10:
   if fold not in f["dataset"]:continue
   m=json.loads(f["metadata_json"])
   z=by[(f["dataset"],f["case_name"],"forced_restart25")]
   if len(z)!=3:continue
   x.append(m["structural"]["degree_cv"])
   y.append(statistics.median(z.values()))
  ax.scatter(x,y,label=fold,alpha=.7)
 ax.axhline(1,ls="--",color="black",lw=1)
 ax.set(xlabel="Pre-solve variable-degree CV",ylabel="Median forced-restart speedup",
        title="R10 prospective structure vs response (hypothesis only)")
 ax.legend();fig.tight_layout()
 fig.savefig(out/"scatter_post_r9_structure.png",dpi=145);plt.close(fig)
 counts={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0] for t in
   ("datasets","formulas","attempts","source_artifacts","attempt_context",
    "r7_formula_features","holdout_formula_features","post_r9_formula_features")}
 check(counts["datasets"]==57+12+4+6 and counts["formulas"]==1227+232 and
       counts["attempts"]==13406+2844 and
       counts["r7_formula_features"]==380 and
       counts["holdout_formula_features"]==200,"Historical totals changed "+str(counts))
 check(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite corruption")
 check(db.execute("""SELECT COUNT(*) FROM (SELECT dataset,case_name,solver,repeat,COUNT(*) AS n
  FROM attempts GROUP BY 1,2,3,4 HAVING n>1)""").fetchone()[0]==0,"Duplicate attempts")
 existing={r[0] for r in db.execute("""SELECT DISTINCT formula_sha256 FROM formulas
  WHERE dataset NOT LIKE 'DRNAS-R10-%' AND dataset NOT LIKE 'DRNAS-Selector-%'
    AND dataset NOT LIKE 'DRNAS-SC2023-%'""")}
 overlap=[f for f in feats if f["formula_sha256"] in existing]
 # Overlap is recorded, not silently counted as an independent new formula.
 for f in overlap:
  db.execute("UPDATE datasets SET provenance='previously_seen_hash_overlap' WHERE dataset=?",
             (f["dataset"],))
 db.commit()
 audit={"source_runs":{"R10":R10_RUN,"selector":SEL_RUN,"SC2023":REAL_RUN},
   "source_commits":{"R10":R10_SHA,"selector":SEL_SHA,"SC2023":SEL_SHA},
   "sources":info,"new_datasets":[x["dataset"] for x in info if x["new"]],
   "counts":counts,"post_r9_paired_rows":len(pairs),"new_formula_sha_overlap_old":len(overlap),
   "reports":reports,
   "cautions":["Generated holdouts not official; project-new SC2023 source is not official benchmark.",
     "All comparisons within runner and formula; repeated attempts not independent formulas.",
     "UNSAT labels without native certificates are not independent proofs.",
     "R10 structural gate 95% bootstrap interval spans zero; not a confirmed predictive law.",
     "Selector overhead may dominate very short formula timings.",
     "V15.3.1 solver and its frozen heuristics unchanged."]}
 (out/"post_r9_source_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
 summary_json=json.loads((out/"summary.json").read_text())
 for k,v in prior_summary.items():
  if k not in summary_json:summary_json[k]=v
 summary_json["post_r9"]=audit
 (out/"summary.json").write_text(json.dumps(summary_json,indent=2)+"\n")
 print(json.dumps({"new_datasets":audit["new_datasets"],"counts":counts,
   "paired":len(pairs),"r10_test":reports["R10"]["test"],
   "real_sc2023":reports["SC2023"]["summary"]},indent=2))

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True)
 p.add_argument("--input",type=Path,required=True)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 previous=json.loads((a.out/"summary.json").read_text()) if (a.out/"summary.json").is_file() else {}
 db=sqlite3.connect(a.db)
 try:
  old.schema(db)
  with db:info,reports=ingest_all(db,a.input)
  export(db,a.out,info,reports,previous)
 finally:db.close()
if __name__=="__main__":main()
