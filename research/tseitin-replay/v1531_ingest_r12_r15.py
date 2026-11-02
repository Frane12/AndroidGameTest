#!/usr/bin/env python3
"""Strict, additive R12-R15 native SAT measurement ingest into historical SQLite.

Only verified GitHub Actions *raw* shard artifacts are accepted. The published
aggregate reports are checksums and independent summaries, not substitute
attempts. Never modify frozen solver source, existing datasets, or prior rows.
R15 learned snapshot/trajectory results are OFF-POLICY REPLAY, never live attempts.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,sqlite3,statistics
from collections import defaultdict,Counter
from pathlib import Path
import v1531_analytics_db as base
import v1531_ingest_new as old

RUNS={
 12:("41412313004","123d90302524e067a0abb20b4ce7a2497230053d","DRNAS-R12-Frozen-Hybrid-Analysis",3240,120,9),
 13:("41415250855","8ce764c9e21be5833926fdcf275a28db6a71ddff","DRNAS-R13-Frozen-Rescue-Analysis",3600,120,10),
 14:("41417754698","718bb44d1ba2d27b85a84f83b04e102b0282473f","DRNAS-R14-Dual-Transfer-Analysis",4800,160,10),
 15:("41421780846","a7f60079ece4b291d2fe47d0ec1cd44c57eacd53","DRNAS-R15-Trajectory-Learned-Model-Analysis",3840,160,8)
}
STABLE="9e2b04e2e32b7320bd89757486b93ad0d5bc0ef10c28bdd54dd98c4bb14fb89c"
KISSAT="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
FOLDS_OLD=("development","test")
FOLDS_NEW=("random3_development","random3_test","community3_development","community3_test")
def check(condition,why):
 if not condition:raise ValueError("R12-R15 ANALYTICS AUDIT FAILED: "+why)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csvrows(p):
 with p.open(newline="") as f:return list(csv.DictReader(f))
def jsonlines(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()]
def int_opt(x):
 try:return int(x) if x not in ("",None) else None
 except (TypeError,ValueError):return None
def float_opt(x):
 try:return float(x) if x not in ("",None) else None
 except (TypeError,ValueError):return None
def flag(x):
 if str(x).lower() in ("true","1"):return 1
 if str(x).lower() in ("false","0"):return 0
 return None
def validsha(s):return isinstance(s,str) and len(s)==64 and all(x in "0123456789abcdef" for x in s)
def rowsha(r):return hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def export(out,name,rows):
 if not rows:return
 with (out/name).open("w",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction="ignore")
  writer.writeheader();writer.writerows(rows)

def shards(version):
 cats=[f"n{n}_{fold}{i}" for n in (200,220,240) for fold in FOLDS_OLD for i in (0,1)]
 if version>=14:
  cats.extend(f"community_n{n}_{fold}0" for n in (220,240) for fold in FOLDS_OLD)
 return cats

def expected_fold(version,cat):
 fam="community3" if cat.startswith("community_") else "random3"
 fold="development" if "_development" in cat else "test"
 return fam+"_"+fold if version>=14 else fold
def expected_n(cat):
 return int(cat.split("_")[1][1:]) if cat.startswith("community_") else int(cat[1:4])

def verify_aggregate(version,root):
 run,commit,aggname,attempts,formulas,modes=RUNS[version]
 folder=root/("r"+str(version))
 path=folder/"aggregate"/"results.json"
 check(path.is_file(),"missing aggregate results.json R"+str(version))
 report=json.loads(path.read_text())
 if version==15:
  check(report.get("attempts")==attempts and report.get("formula_count")==formulas
    and report.get("repeats")==3 and report.get("monitor_prefix_mismatches")==0
    and report.get("model_training_development_only") is True
    and "off-policy" in report.get("status","").lower(),"R15 replay/report validation")
  names=report["source_config"]["arms"]
  check(len(names)==modes and "snapshot_replay" not in names
    and "trajectory_replay" not in names,"R15 replay mistakenly called native solver")
 else:
  check(report.get("run_attempts")==attempts and report.get("formula_count")==formulas
    and report.get("repeats")==3 and report.get("pre_intervention_counter_mismatch_count")==0,
    "incomplete native aggregate R"+str(version))
  names=report["comparison_modes"]
  check(len(names)==modes,"native mode count R"+str(version))
  check(len(report.get("manifests",[]))==len(shards(version)),"aggregate manifest count")
 check(len(report.get("source_artifacts",[]))==len(shards(version)),"aggregate shard hash count")
 check(set(x["shard"] for x in report["source_artifacts"])==set(shards(version)),
       "aggregate missing/duplicate source shards")
 paired=csvrows(folder/"aggregate"/"paired.csv")
 features=csvrows(folder/"aggregate"/"formula_features.csv")
 check(len(features)==formulas and len({r["formula_sha256"] for r in features})==formulas,
       "aggregate formula feature SHA uniqueness R"+str(version))
 check(len(paired)==formulas*(modes-1),"aggregate paired row count R"+str(version))
 check(len({(r["shard"],r["formula"],r["mode"]) for r in paired})==len(paired),
       "aggregate paired key duplicates")
 return report,names,paired,features

def verify_and_ingest(db,version,root,global_seen,agg):
 run,commit,aggname,expected_attempts,expected_formulas,nmodes=RUNS[version]
 folder=root/("r"+str(version));report,modes,paired,features=agg
 source={s["shard"]:s for s in report["source_artifacts"]}
 report_sha=sha(folder/"aggregate"/"results.json")
 artifact_index={}
 for line in (folder/"artifact_index.tsv").read_text().splitlines():
  a=line.split("\t")
  check(len(a)>=3,"bad artifact index R"+str(version))
  name,aid,expired=a[:3]
  check(name not in artifact_index,"duplicate artifact name")
  check(expired=="false","expired GitHub source artifact "+name)
  artifact_index[name]=int(aid)
 check(aggname in artifact_index,"missing GitHub aggregate artifact index")
 feat_by={(r["shard"],r["formula"]):r for r in features}
 pair_by={(r["shard"],r["formula"],r["mode"]):r for r in paired}
 check(len(feat_by)==expected_formulas and len(pair_by)==len(paired),"duplicate aggregate keys")
 new_records=[];all_rows=[];all_traces=[];formula_set=set()
 for cat in shards(version):
  src=source[cat];sp=folder/"shards"/cat
  artifact="r"+str(version)+"-"+cat
  check(artifact in artifact_index,"missing GitHub raw shard artifact "+artifact)
  csvp,mp,tp=[sp/p for p in ("measurements.csv","manifest.json","traces.jsonl")]
  check(all(p.is_file() for p in (csvp,mp,tp)),"raw measurements/manifest/traces missing "+artifact)
  for path,field in ((csvp,"measurements_sha256"),(mp,"manifest_sha256"),(tp,"traces_sha256")):
   check(sha(path)==src[field],"raw artifact checksum mismatch "+artifact+"/"+path.name)
  m=json.loads(mp.read_text());rs=csvrows(csvp);ts=jsonlines(tp)
  check(m["source_commit"]==commit and src["source_commit"]==commit
     and m["category"]==cat and m["runner"]==src["runner"]
     and m["cap_seconds"]==12 and m["repeats"]==3
     and m["stable_blob"] and m["kissat_pin"]==KISSAT
     and m["executables"]==src["binary_sha256"]
     and tuple(m["modes"])==tuple(modes),"pinned source/runner/binary/protocol "+artifact)
  check(m["fold"]==expected_fold(version,cat),"fold classification mismatch "+artifact)
  if version<14:check(m["fold"] in FOLDS_OLD,"bad R12/13 fold")
  else:check(m["family"]==("community3" if cat.startswith("community_") else "random3"),
             "R14/15 family mismatch")
  check(m["stable_blob"] and m["executables"]["stable_v1531"]==STABLE,
        "frozen stable binary hash drift")
  if version==15:
   check(m["r15_protocol_sha256"]==report["frozen_protocol_sha256"] and
      m["historical_registry_sha256"]==report["historical_registry_sha256"],
      "R15 frozen protocol/history mismatch")
  else:
   check(m["frozen_rule_sha256"]==report["frozen_rule_sha256"],
         "frozen rule changed "+artifact)
  check(len(m["cases"])==10 and len(rs)==30*nmodes and len(ts)==len(rs),
        "incomplete 10-formula/3-repeat paired raw shard "+artifact)
  cases={x["formula"]:x for x in m["cases"]}
  check(len(cases)==10,"duplicate raw formula name")
  key=lambda r:(r["formula"],r["mode"],int(r["repeat"]))
  expected_keys={(name,mode,rep) for name in cases for mode in modes for rep in range(3)}
  check({key(r) for r in rs}==expected_keys and len({key(r) for r in rs})==len(rs),
        "incomplete or duplicate raw attempt matrix "+artifact)
  check({key(t) for t in ts}==expected_keys and len({key(t) for t in ts})==len(ts),
        "incomplete or duplicate raw trace matrix "+artifact)
  case_status=defaultdict(set);per_case_mode=defaultdict(float)
  for name,f in cases.items():
   h=f["formula_sha256"]
   check(validsha(h) and h not in global_seen and h not in formula_set,
         "reused CNF SHA256 (historical or within R12-R15) "+h)
   check(f["n"]==expected_n(cat) and f["metadata"]["fold"] in FOLDS_OLD
         and f["metadata"]["fold"] in cat and
         f["metadata"].get("seed") is not None and f["expected"]=="UNKNOWN",
         "bad generator seed or source "+artifact)
   check(f["dataset_type"]=="generated_prospective","unverified external/official provenance")
   formula_set.add(h)
   feat=feat_by.get((cat,name))
   check(feat is not None and feat["formula_sha256"]==h
     and int(feat["n"])==f["n"]
     and str(feat["seed"])==str(f["metadata"]["seed"])
     and feat["fold"]==expected_fold(version,cat),
     "aggregate formula features disagree with raw manifest "+artifact)
  trace_map={key(t):t for t in ts}
  for r in rs:
   name,mode,rep=key(r);f=cases[name];status=r["status"]
   check(r["category"]==cat and r["formula_sha256"]==f["formula_sha256"]
      and r["runner"]==m["runner"] and r["seed"]==str(f["metadata"]["seed"])
      and r["expected"]=="UNKNOWN" and not r.get("error")
      and status in ("SAT","UNSAT","TIMEOUT"),
      "raw result/seed/runner/status error "+artifact)
   if version>=14:check(r["fold"]==expected_fold(version,cat),"row fold mismatch")
   else:check(r["fold"]==expected_fold(version,cat),"row fold mismatch")
   wall=float(r["wall_s"]);par2=float(r["par2_s"])
   check(math.isfinite(wall) and wall>=0 and math.isfinite(par2)
      and abs(par2-(24.0 if status=="TIMEOUT" else wall))<=.0011,
      "invalid PAR-2 "+artifact)
   if status=="SAT":
    check(flag(r["sat_model_checked"])==1,"SAT assignment unverified "+artifact)
   if status in ("SAT","UNSAT"):case_status[name].add(status)
   if r.get("switch_at"):
    check(mode not in ("monitor","original_kissat","stable_v1531")
      and int(r["switch_at"])>=2048
      and r.get("learned_before")==r.get("learned_after"),
      "invalid native intervention or learned-clause reset "+artifact)
   if version==15:
    check(r["r15_config_sha256"]==report["frozen_protocol_sha256"],
          "R15 source config changed in raw attempt")
   t=trace_map[key(r)]
   check(t["category"]==cat and t["formula"]==name
      and int(t["repeat"])==rep and t["mode"]==mode
      and len(t["points"])==int(r["trace_points"]),
      "trace/attempt linkage mismatch "+artifact)
   per_case_mode[(name,mode)]+=par2
  check(all(len(x)<=1 for x in case_status.values()),"contradictory SAT/UNSAT within formula")
  for name in cases:
   f=feat_by[(cat,name)]
   for mode in modes:
    total=per_case_mode[(name,mode)]
    check(abs(total-float(f[mode]))<.0002,
          "published formula_features total differs from raw "+artifact+" "+mode)
    if mode!="monitor":
     p=pair_by.get((cat,name,mode))
     check(p is not None and p["formula_sha256"]==cases[name]["formula_sha256"]
       and abs(float(p["monitor_par2"])-per_case_mode[(name,"monitor")])<.0002
       and abs(float(p["treatment_par2"])-total)<.0002,
       "aggregate paired.csv differs from raw measurements "+artifact+" "+mode)
  dataset="DRNAS-R"+str(version)+"-"+cat
  check(db.execute("SELECT COUNT(*) FROM datasets WHERE dataset=?",(dataset,)).fetchone()[0]==0,
        "dataset already exists; refusing to overwrite "+dataset)
  fold=expected_fold(version,cat)
  provenance=("generated_community3_"+fold.split("_")[-1] if fold.startswith("community3")
    else "generated_prospective_"+fold.split("_")[-1])
  description=("Synthetic community-biased 3-CNF; NOT official external"
      if cat.startswith("community_") else "Prospectively generated random3; NOT official external")
  if version==15:description+="; ridge trajectory/snapshot is OFF-POLICY REPLAY only"
  db.execute("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?)",
    (dataset,provenance,description,run,commit,m["runner"],12,report_sha))
  for name,f in cases.items():
   meta=f["metadata"];h=f["formula_sha256"]
   db.execute("INSERT INTO formulas VALUES (?,?,?,?,?,?,?,?,?)",
    (dataset,name,fold,"UNKNOWN",h,None,f.get("path"),f["n"],meta["features"]["clauses"]))
   db.execute("INSERT INTO r12_r15_formula_features VALUES (?,?,?,?,?,?,?,?,?)",
    (dataset,name,h,sha(mp),fold,meta["seed"],f.get("source_revision"),
     json.dumps(meta,sort_keys=True),sha(folder/"aggregate"/"formula_features.csv")))
   global_seen.add(h)
  for r in rs:
   name,mode,rep=key(r);status=r["status"];sat=flag(r["sat_model_checked"])
   unsat=flag(r.get("unsat_certificate_checked"))
   verified=(1 if status=="SAT" and sat==1 else
             1 if status=="UNSAT" and unsat==1 else
             0 if status=="TIMEOUT" else None)
   tier=("sat_witness" if sat==1 else
         "independent_unsat_certificate" if unsat==1 else
         "unsat_label_only" if status=="UNSAT" else "timeout")
   db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,name,mode,rep,float(r["wall_s"]),status,verified,
      r.get("route"),sat,unsat,float(r["par2_s"]),int_opt(r.get("exit_code"))))
   db.execute("INSERT INTO attempt_context VALUES (?,?,?,?,?,?,?,?,?,?)",
     (dataset,name,mode,rep,m["runner"],r["seed"],cases[name].get("source_revision"),
      r["formula_sha256"],rowsha(r),tier))
   db.execute("INSERT INTO r6_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,name,mode,rep,int_opt(r.get("early_r")),float_opt(r.get("early_g")),
      float_opt(r.get("early_p")),float_opt(r.get("early_d")),
      None,int(bool(r.get("switch_at"))),int_opt(r.get("switch_at")),
      int_opt(r.get("final_conflicts")),int_opt(r.get("final_restarts")),
      int_opt(r.get("trace_points"))))
   db.execute("INSERT INTO r12_r15_attempt_details VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
     (dataset,name,mode,rep,float(r["cpu_s"]),int_opt(r.get("switch_at")),
      int_opt(r.get("restart_before")),int_opt(r.get("restart_after")),
      int_opt(r.get("learned_before")),int_opt(r.get("learned_after")),
      float_opt(r.get("early_p")),float_opt(r.get("early_g")),rowsha(r)))
  for t in ts:
   name,mode,rep=key(t)
   for i,pt in enumerate(t.get("points",[])):
    db.execute("INSERT INTO telemetry VALUES (?,?,?,?,?,?,?,?,?,?,?)",
      (dataset,name,mode,rep,i,None,int_opt(pt.get("conflict")),
       int_opt(pt.get("propagations")),int_opt(pt.get("restarts")),
       int_opt(pt.get("learned")),float_opt(pt.get("glue"))))
  old.source(db,dataset,run,commit,artifact_index[artifact],csvp,report_sha,
             m["runner"],provenance,
             "Only synthetic 3CNF, not official. UNSAT no independent proof. "+
             ("R15 learned predictors are off-policy replay." if version==15 else "Frozen native policies."))
  new_records.append({"dataset":dataset,"version":version,"source_run":run,
    "source_commit":commit,"artifact_id":artifact_index[artifact],
    "runner":m["runner"],"fold":fold,"formulas":10,"attempts":len(rs),
    "manifest_sha256":sha(mp),"measurements_sha256":sha(csvp),
    "traces_sha256":sha(tp),"aggregate_sha256":report_sha})
  all_rows.extend(rs);all_traces.extend(ts)
 check(len(all_rows)==expected_attempts and len(formula_set)==expected_formulas,
       "incomplete full R"+str(version)+" raw ingest")
 return new_records,all_rows,report

def initialize(db):
 db.execute("""CREATE TABLE IF NOT EXISTS r12_r15_formula_features(
  dataset TEXT,case_name TEXT,formula_sha256 TEXT,manifest_sha256 TEXT,
  fold TEXT,seed INTEGER,source_revision TEXT,metadata_json TEXT,
  aggregate_features_sha256 TEXT,PRIMARY KEY(dataset,case_name))""")
 db.execute("""CREATE TABLE IF NOT EXISTS r12_r15_attempt_details(
  dataset TEXT,case_name TEXT,solver TEXT,repeat INTEGER,cpu_seconds REAL,
  switch_at INTEGER,restart_before INTEGER,restart_after INTEGER,
  learned_before INTEGER,learned_after INTEGER,early_p REAL,early_g REAL,
  raw_row_sha256 TEXT,PRIMARY KEY(dataset,case_name,solver,repeat))""")

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",type=Path,required=True)
 p.add_argument("--out",type=Path,required=True)
 p.add_argument("--input",type=Path,required=True)
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(a.db)
 try:
  old.schema(db)
  initialize(db)
  counts_before={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
    for t in ("datasets","formulas","attempts","source_artifacts","attempt_context")}
  check(counts_before["datasets"]==79 and counts_before["formulas"]==1459
    and counts_before["attempts"]==16250,
    "baseline cumulative database has changed; refuse to rebuild/overwrite history")
  baseline=counts_before.copy()
  prior={h for (h,) in db.execute("SELECT formula_sha256 FROM formulas") if h}
  check(all(validsha(h) for h in prior),"historical formulas include invalid SHA")
  all_info=[];all_rows=[];reports={}
  for v in (12,13,14,15):
   agg=verify_aggregate(v,a.input)
   with db:
    info,rows,report=verify_and_ingest(db,v,a.input,prior,agg)
   all_info.extend(info);all_rows.extend(rows);reports["R"+str(v)]=report
   print("R12_R15_VERIFIED_AND_INGESTED",v,len(info),len(rows),flush=True)
  check(len(all_info)==56 and len(all_rows)==15480,
        "unexpected number of new datasets/attempts")
  counts_after={t:db.execute("SELECT COUNT(*) FROM "+t).fetchone()[0]
    for t in ("datasets","formulas","attempts","source_artifacts","attempt_context",
       "r12_r15_formula_features","r12_r15_attempt_details")}
  check(counts_after["datasets"]==135 and counts_after["formulas"]==2019
    and counts_after["attempts"]==31730
    and counts_after["r12_r15_formula_features"]==560
    and counts_after["r12_r15_attempt_details"]==15480,
    "cumulative final count mismatch "+str(counts_after))
  check(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","SQLite integrity check failed")
  check(db.execute("""SELECT COUNT(*) FROM
    (SELECT dataset,case_name,solver,repeat,COUNT(*) n
    FROM attempts GROUP BY 1,2,3,4 HAVING n>1)""").fetchone()[0]==0,
    "duplicate attempt primary keys")
  check(db.execute("""SELECT COUNT(*) FROM
    (SELECT formula_sha256,COUNT(*) n FROM formulas
    WHERE dataset LIKE 'DRNAS-R12-%' OR dataset LIKE 'DRNAS-R13-%'
      OR dataset LIKE 'DRNAS-R14-%' OR dataset LIKE 'DRNAS-R15-%'
    GROUP BY formula_sha256 HAVING n>1)""").fetchone()[0]==0,
    "duplicate new formula hashes")
  check(db.execute("SELECT COUNT(*) FROM formulas WHERE dataset NOT LIKE 'DRNAS-R12-%' AND dataset NOT LIKE 'DRNAS-R13-%' AND dataset NOT LIKE 'DRNAS-R14-%' AND dataset NOT LIKE 'DRNAS-R15-%'").fetchone()[0]==baseline["formulas"],
    "historical formula rows changed")
  check(db.execute("SELECT COUNT(*) FROM attempts WHERE dataset NOT LIKE 'DRNAS-R12-%' AND dataset NOT LIKE 'DRNAS-R13-%' AND dataset NOT LIKE 'DRNAS-R14-%' AND dataset NOT LIKE 'DRNAS-R15-%'").fetchone()[0]==baseline["attempts"],
    "historical attempt rows changed")
  # Preserve old R8/R9 and post-R9 reports before base.analytics regenerates summary.json.
  prior_summary=json.loads((a.out/'summary.json').read_text()) if (a.out/'summary.json').is_file() else {}
  # Export all existing analytics with additive records, preserving old historical
  # source and fold metadata and old post-R9 specialized tables.
  grouped,paired,telemetry=base.analytics(db,a.out)
  old.extra(db,a.out)
  feats=[dict(zip([c[0] for c in db.execute("SELECT * FROM r12_r15_formula_features LIMIT 1").description],row))
    for row in db.execute("SELECT * FROM r12_r15_formula_features ORDER BY dataset,case_name")]
  export(a.out,"r12_r15_formula_features.csv",feats)
  srcs=[dict(zip([c[0] for c in db.execute("SELECT * FROM r12_r15_attempt_details LIMIT 1").description],row))
    for row in db.execute("SELECT * FROM r12_r15_attempt_details ORDER BY dataset,case_name,solver,repeat")]
  export(a.out,"r12_r15_attempt_details.csv",srcs)
  summary=[]
  matched=[]
  for v in (12,13,14,15):
   data=reports["R"+str(v)]
   for fold,sub in data["report"].items():
    modes=sub.get("by_strategy",sub.get("modes"))
    for mode,m in modes.items():
     summary.append({"version":"R"+str(v),"fold":fold,"mode":mode,
       "formulas":sub.get("formulas",sub.get("formula_count")),
       "par2_s":m.get("total_par2_s",m.get("par2_total_s")),
       "gain_percent":m.get("gain_percent",m.get("gain_percent_vs_monitor")),
       "ci_95":json.dumps(m.get("bootstrap_95_formula_CI",m.get("formula_bootstrap_95_CI"))),
       "evaluation_type":"OFF_POLICY_REPLAY" if mode in ("snapshot_replay","trajectory_replay") else "REAL_NATIVE_SOLVER"})
  export(a.out,"r12_r15_frozen_report_summary.csv",summary)
  for r in all_rows:
   if r["mode"]=="monitor":continue
   matched.append({"version":"R"+r["formula"].split("_")[0][1:],
     "shard":r["category"],"fold":r["fold"],"formula":r["formula"],
     "formula_sha256":r["formula_sha256"],"repeat":r["repeat"],
     "mode":r["mode"],"par2_s":r["par2_s"]})
  export(a.out,"r12_r15_raw_treatments.csv",matched)
  # Actual paired attempt data from SQLite; R15 replay is never inserted here.
  q=db.execute("""SELECT a.dataset,a.case_name,a.repeat,a.solver AS treatment,
    m.par2_seconds AS monitor_par2,a.par2_seconds AS treatment_par2,
    f.formula_sha256,f.category,d.provenance,
    a.par2_seconds/m.par2_seconds AS ratio
    FROM attempts a JOIN attempts m
      ON m.dataset=a.dataset AND m.case_name=a.case_name
      AND m.repeat=a.repeat AND m.solver='monitor'
    JOIN formulas f ON f.dataset=a.dataset AND f.case_name=a.case_name
    JOIN datasets d ON d.dataset=a.dataset
    WHERE (a.dataset LIKE 'DRNAS-R12-%' OR a.dataset LIKE 'DRNAS-R13-%'
      OR a.dataset LIKE 'DRNAS-R14-%' OR a.dataset LIKE 'DRNAS-R15-%')
      AND a.solver!='monitor'
    ORDER BY a.dataset,a.case_name,a.repeat,a.solver""")
  cols=[c[0] for c in q.description];pairs=[dict(zip(cols,row)) for row in q]
  check(len(pairs)==15480-3*560,"missing R12-R15 same-formula/same-runner pairs")
  export(a.out,"r12_r15_paired_attempts.csv",pairs)
  try:
   import matplotlib
   matplotlib.use("Agg")
   import matplotlib.pyplot as plt
   for v in (12,13,14,15):
    rows=[r for r in pairs if r["dataset"].startswith("DRNAS-R"+str(v)+"-")
      and ("_test" in r["dataset"])]
    fig,ax=plt.subplots(figsize=(8,6))
    for mode in sorted({r["treatment"] for r in rows}):
     rr=[r for r in rows if r["treatment"]==mode]
     ax.scatter([r["monitor_par2"] for r in rr],[r["treatment_par2"] for r in rr],
       s=7,alpha=.30,label=mode)
    ax.plot([.0001,24],[.0001,24],"--",linewidth=.7,color="black")
    ax.set(xscale="log",yscale="log",xlabel="Same-runner monitor PAR-2 (s)",
      ylabel="Treatment PAR-2 (s)",title=f"R{v} prospective generated TEST (not official)")
    ax.legend(fontsize=7,ncol=2);fig.tight_layout()
    fig.savefig(a.out/f"scatter_r{v}_paired_test.png",dpi=130);plt.close(fig)
  except ImportError:pass
  audit={"status":"verified raw artifact ingest success; not replay",
    "source_runs":{str(v):RUNS[v][0] for v in RUNS},
    "source_commits":{str(v):RUNS[v][1] for v in RUNS},
    "historical_counts_before":baseline,"counts_after":counts_after,
    "new_datasets":56,"new_unique_sha":560,"new_native_attempts":15480,
    "paired_native_attempts":len(pairs),
    "all_new_sources":all_info,
    "R15_replay_warning":"Snapshot/trajectory are off-policy counterfactual replay; never native measured solver attempts.",
    "provenance_warning":"R12/R13 random3 and R14/R15 random3/community3 are synthetic generated prospective holdouts, NOT official competition benchmarks.",
    "verification_warning":"SAT witnesses validated by source runner; UNSAT raw Kissat labels lack independent certificates.",
    "novelty_warning":"SHA256 deduplicated against historical database and all 560 new formulas; not global novelty.",
    "immutable_baseline":"V15.3.1 solver and all 16250 historical attempts untouched."}
  (a.out/"r12_r15_ingest_audit.json").write_text(json.dumps(audit,indent=2)+"\n")
  path=a.out/"summary.json"
  full=json.loads(path.read_text())
  for key,value in prior_summary.items():
   if key not in full:full[key]=value
  full["r12_r15_verified_ingest"]={k:v for k,v in audit.items() if k!="all_new_sources"}
  path.write_text(json.dumps(full,indent=2)+"\n")
  db.commit()
  print("R12_R15_VERIFIED_CUMULATIVE_SQLITE_SUCCESS",json.dumps({
   "new_native_attempts":15480,"new_formulas":560,"datasets":135,
   "attempts":31730,"r15_off_policy_only":True}),flush=True)
 finally:db.close()

if __name__=="__main__":main()
