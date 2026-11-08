#!/usr/bin/env python3
"""DRNAS MRE6: auditable CPU-feedback learning for certified math principles.

This module trains from PREVIOUS MRE5 source-paired CPU experiments, freezes
a conservative selection policy BEFORE new seed holdout, and then appends
holdout measurements to a compact SQLite evidence base.

Never treat a seed split on one formula as source-disjoint validation.
Never include the CPU cost of measurement of an unseen target inside the
online gate. With one training source the deployment policy MUST abstain.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sqlite3
import statistics

PROTO="DRNAS-MRE6-CERTIFIED-CPU-FEEDBACK-v1"
BASE_MODES={"xor":"xor_off","a":"a_off","b":"b_off","both":"both_off"}
PRINCIPLES={
    "xor":dict(kind="baseline",principle="source_certified_parity",clauses=0),
    "a":dict(kind="implication",principle="x12_implies_x224",clauses=1),
    "b":dict(kind="implication",principle="x224_implies_x12",clauses=1),
    "both":dict(kind="equivalence_as_lemmas",principle="x12_equals_x224_as_two_watchers",clauses=2),
    "canonical":dict(kind="representation",principle="remove_CNF_tautology_and_duplicates",clauses=0),
    "quotient":dict(kind="representation",principle="certified_equality_variable_quotient",clauses=0),
    "quotient_no_xor":dict(kind="representation",principle="certified_equality_quotient_no_XOR_import",clauses=0),
}
MIN_SOURCE_DISJOINT=3
MIN_SEEDS_PER_SOURCE=3
MIN_CPU_MARGIN_PCT=3.0


def need(ok,msg):
    if not ok:raise RuntimeError("MRE6_FEEDBACK_FAIL_CLOSED "+str(msg))

def create_db(conn):
    conn.executescript("""
CREATE TABLE IF NOT EXISTS principle (
  code TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  description TEXT NOT NULL,
  imported_clauses INTEGER NOT NULL,
  proof_required INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS observation (
  source_sha256 TEXT NOT NULL,
  split TEXT NOT NULL,
  seed INTEGER NOT NULL,
  repeat INTEGER NOT NULL,
  mode TEXT NOT NULL,
  trace_enabled INTEGER NOT NULL,
  process_cpu_s REAL NOT NULL,
  solve_wall_s REAL NOT NULL,
  wrapper_wall_s REAL NOT NULL,
  native_decisions INTEGER NOT NULL,
  native_conflicts INTEGER NOT NULL,
  native_propagations INTEGER NOT NULL,
  watch_visits INTEGER,
  watch_units INTEGER,
  watch_conflicts INTEGER,
  watch_satisfied INTEGER,
  tag_visits INTEGER,
  tag_units INTEGER,
  status TEXT NOT NULL,
  witness_verified INTEGER NOT NULL,
  source_commit TEXT NOT NULL,
  PRIMARY KEY(source_sha256,split,seed,repeat,mode,trace_enabled));
CREATE TABLE IF NOT EXISTS cpu_feedback (
  principle_code TEXT NOT NULL,
  split TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  seed INTEGER NOT NULL,
  baseline_cpu_s REAL NOT NULL,
  candidate_cpu_s REAL NOT NULL,
  cpu_saved_pct REAL NOT NULL,
  watcher_pressure_pct REAL,
  decision_savings_pct REAL,
  cpu_per_million_direct_tag_units REAL,
  PRIMARY KEY(principle_code,split,source_sha256,seed));
""")
    for code,p in PRINCIPLES.items():
        conn.execute("INSERT OR IGNORE INTO principle VALUES (?,?,?,?,?)",
                     (code,p["kind"],p["principle"],p["clauses"],int(code!="xor")))

def convert_mre5(row):
    need(row["protocol"]=="DRNAS-MRE5-CPU-TRUE-BCP-COST-1SAT2026-2SEED-2REP-8ARMS-v1",
         "not a pinned MRE5 calibration record")
    need(row["status"]=="SAT" and row["sat_witness_checked"],"calibration SAT invalid")
    need(row["instrumented_CMS_upstream_sha"]==
         "3b709118fd08eb1d15f25e0e239dbc596f967b60","native source drift")
    mode,trace=row["mode"].rsplit("_",1)
    need(mode in ("xor","a","b","both") and trace in ("on","off"),"bad MRE5 arm")
    return dict(sha=row["source_sha256"],split="calibration",seed=row["seed"],
                repeat=row["repeat"],mode=mode,trace_enabled=int(trace=="on"),
                cpu=row["cpu"]["process_cpu_s"],solve_wall=row["cpu"]["solve_wall_s"],
                wrapper_wall=row["wall_s"],decisions=row["native_cdcl_decisions"],
                conflicts=row["native_cdcl_conflicts"],
                propagations=row["native_cdcl_propagations"],
                watch=row["all_binary_watchers"],
                tagged=row["tag_watchers"],status=row["status"],
                witness=row["sat_witness_checked"],
                source_commit=row["instrumented_CMS_upstream_sha"])

def convert_mre6(row):
    need(row["protocol"]=="DRNAS-MRE6-QUOTIENT-CPU-HOLDOUT-v1",
         "not a pinned MRE6 holdout record")
    need(row["status"]=="SAT" and row["original_sat_witness_verified"],
         "holdout SAT witness failed")
    need(row["otf_gauss"] is False,"OTF Gauss changed")
    need(row["instrumented_CMS_upstream_sha"]==
         "3b709118fd08eb1d15f25e0e239dbc596f967b60","native source drift")
    return dict(sha=row["source_sha256"],split="holdout_seed_only",
                seed=row["seed"],repeat=row["repeat"],mode=row["mode"],
                trace_enabled=int(row["trace_enabled"]),
                cpu=row["cpu"]["process_cpu_s"],
                solve_wall=row["cpu"]["solve_wall_s"],
                wrapper_wall=row["wrapper_wall_s"],
                decisions=row["native_cdcl_decisions"],conflicts=row["native_cdcl_conflicts"],
                propagations=row["native_cdcl_propagations"],
                watch=row["all_binary_watchers"],tagged=row["tag_watchers"],
                status=row["status"],witness=row["original_sat_witness_verified"],
                source_commit=row["instrumented_CMS_upstream_sha"])

def insert(conn,r):
    need(r["mode"] in PRINCIPLES,"unknown principle code")
    w=r.get("watch") or {}
    tagged=r.get("tagged") or {}
    total_visits=sum(z["visits"] for z in tagged.values()) if tagged else 0
    total_units=sum(z["units"] for z in tagged.values()) if tagged else 0
    conn.execute("""INSERT INTO observation VALUES
      (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (r["sha"],r["split"],r["seed"],r["repeat"],r["mode"],r["trace_enabled"],
         r["cpu"],r["solve_wall"],r["wrapper_wall"],r["decisions"],
         r["conflicts"],r["propagations"],w.get("visits"),w.get("units"),
         w.get("conflicts"),w.get("satisfied"),total_visits,total_units,
         r["status"],int(r["witness"]),r["source_commit"]))

def annotate(conn,split):
    samples=conn.execute(
      """SELECT source_sha256,seed,repeat,mode,trace_enabled,process_cpu_s,
                native_decisions,watch_visits,tag_units
         FROM observation WHERE split=?""",(split,)).fetchall()
    groups=collections.defaultdict(list)
    for sha,seed,rep,mode,tr,cpu,dec,vis,tag in samples:
        groups[(sha,seed,mode,tr)].append(
          dict(rep=rep,cpu=cpu,dec=dec,vis=vis,tag=tag))
    for (sha,seed,mode,tr),base_rows in groups.items():
        if mode=="xor" or tr!=0:continue
        baseline=groups.get((sha,seed,"xor",0),[])
        need(len(baseline)==len(base_rows),"incomplete CPU feedback pairing")
        b_cpu=statistics.mean(x["cpu"] for x in baseline)
        x_cpu=statistics.mean(x["cpu"] for x in base_rows)
        b_dec=statistics.mean(x["dec"] for x in baseline)
        x_dec=statistics.mean(x["dec"] for x in base_rows)
        borig=groups.get((sha,seed,"xor",1),[])
        targ=groups.get((sha,seed,mode,1),[])
        pressure=None
        if borig and targ:
            b_vis=statistics.mean(x["vis"] for x in borig)
            c_vis=statistics.mean(x["vis"] for x in targ)
            pressure=100.0*(c_vis-b_vis)/max(1,b_vis)
        tagcpu=None
        if targ:
            tag_units=statistics.mean(x["tag"] for x in targ)
            tagcpu=x_cpu/(tag_units/1e6) if tag_units>0 else None
        conn.execute("""INSERT OR REPLACE INTO cpu_feedback
         VALUES (?,?,?,?,?,?,?,?,?,?)""",
          (mode,split,sha,seed,b_cpu,x_cpu,
           100.0*(b_cpu-x_cpu)/max(1e-9,b_cpu),pressure,
           100.0*(b_dec-x_dec)/max(1,b_dec),tagcpu))

def fit(conn):
    observed=conn.execute("""SELECT principle_code,source_sha256,seed,
      cpu_saved_pct,watcher_pressure_pct,decision_savings_pct
      FROM cpu_feedback WHERE split='calibration' ORDER BY principle_code,seed""").fetchall()
    grouped=collections.defaultdict(list)
    for name,sha,seed,cpu,watch,decisions in observed:
        grouped[name].append(dict(sha=sha,seed=seed,cpu_saved_pct=cpu,
                                 extra_watch_pct=watch,decisions_saved_pct=decisions))
    sources={x[0] for x in conn.execute(
        "SELECT DISTINCT source_sha256 FROM observation WHERE split='calibration'")}
    result=dict(protocol=PROTO,training_sources=len(sources),
      min_source_disjoint_required=MIN_SOURCE_DISJOINT,
      min_seeds_per_source_required=MIN_SEEDS_PER_SOURCE,
      min_cpu_margin_pct=MIN_CPU_MARGIN_PCT,
      baseline="xor",
      scored={},
      novel_principle="quotient",
      rule_frozen_before_new_seeds=True,
      never_use_target_cpu_in_online_gate=True)
    for name in ("a","b","both","canonical","quotient","quotient_no_xor"):
        rows=grouped.get(name,[])
        unique_sources={r["sha"] for r in rows}
        unique_seed_pairs={(r["sha"],r["seed"]) for r in rows}
        signed=[r["cpu_saved_pct"] for r in rows]
        watch=[r["extra_watch_pct"] for r in rows if r["extra_watch_pct"] is not None]
        supported=(len(unique_sources)>=MIN_SOURCE_DISJOINT and
              len(unique_seed_pairs)>=MIN_SEEDS_PER_SOURCE*MIN_SOURCE_DISJOINT and
              signed and min(signed)>=MIN_CPU_MARGIN_PCT)
        result["scored"][name]=dict(kind=PRINCIPLES[name]["kind"],
           seen_sources=len(unique_sources),distinct_seed_pairs=len(unique_seed_pairs),
           observed_cpu_saved_pct=signed,
           mean_cpu_saved_pct=(statistics.mean(signed) if signed else None),
           worst_seed_cpu_saved_pct=(min(signed) if signed else None),
           mean_extra_watch_pct=(statistics.mean(watch) if watch else None),
           certified_for_online_use=bool(supported),
           reason=("not_yet_measured" if not signed else
                    "insufficient_source_disjoint_CPU_evidence" if len(unique_sources)<MIN_SOURCE_DISJOINT else
                    "unstable_or_insufficient_positive_CPU_margin" if not supported else
                    "conservatively_validated"))
    eligible=[(k,v) for k,v in result["scored"].items()
              if v["certified_for_online_use"]]
    result["online_policy"]=max(eligible,key=lambda kv:kv[1]["worst_seed_cpu_saved_pct"])[0] if eligible else "xor"
    result["deploy_requires_fresh_source_disjoint_holdout"]=True
    return result

def train(path,out,db):
    need(not pathlib.Path(db).exists(),"DB already exists; calibration must freeze once")
    files=[pathlib.Path(path)/("seed-%d.json" % i) for i in range(2)]
    data=[]
    for filename in files:
        need(filename.exists(),"calibration shard missing: "+str(filename))
        data+=json.loads(filename.read_text())
    need(len(data)==32,"MRE5 calibration expected exactly 32 trials")
    pathlib.Path(db).parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(db)
    create_db(conn)
    for item in data:insert(conn,convert_mre5(item))
    annotate(conn,"calibration")
    rule=fit(conn)
    need(rule["online_policy"]=="xor","unsafe CPU rule promoted on one source")
    conn.commit()
    conn.close()
    pathlib.Path(out).write_text(json.dumps(rule,sort_keys=True,indent=2)+"\n")
    print("MRE6_CPU_FEEDBACK_FROZEN",json.dumps(rule,sort_keys=True),flush=True)

def audit(holdout_dir,calib,db,out):
    rule=json.loads(pathlib.Path(calib).read_text())
    need(rule["online_policy"]=="xor" and rule["rule_frozen_before_new_seeds"],
         "unsafe rule before holdout")
    conn=sqlite3.connect(db)
    create_db(conn)
    holdouts=[]
    for shard in range(4):
        path=pathlib.Path(holdout_dir)/("seed-%d.json"%shard)
        need(path.exists(),"missing shard "+str(shard))
        holdouts+=json.loads(path.read_text())
    need(len(holdouts)==4*7*3==84,"incomplete planned 84 holdout trials")
    known={(x[0],x[1]) for x in conn.execute(
        "SELECT DISTINCT source_sha256,seed FROM observation WHERE split='calibration'")}
    distinct_sha={x["source_sha256"] for x in holdouts}
    need(len(distinct_sha)==1,"multi-source cohort changed unexpectedly")
    need(all((x["source_sha256"],x["seed"]) not in known for x in holdouts),
         "calibration and holdout seeds overlapped")
    groups=collections.defaultdict(set)
    for item in holdouts:
        r=convert_mre6(item)
        key=(r["sha"],r["seed"])
        need((r["mode"],r["repeat"],r["trace_enabled"]) not in groups[key],
             "duplicate mode/repetition/trace")
        groups[key].add((r["mode"],r["repeat"],r["trace_enabled"]))
        insert(conn,r)
    need(len(groups)==4,"expected 4 distinct new holdout seeds")
    for arms in groups.values():
        need(len(arms)==21,"missing 7 modes x (off 2 + on 1)")
        for mode in PRINCIPLES:
            need(all((mode,rep,0) in arms for rep in (0,1)) and
                 (mode,0,1) in arms,"mode pair missing: "+mode)
    annotate(conn,"holdout_seed_only")
    summary=collections.defaultdict(list)
    rows=conn.execute("""SELECT principle_code,seed,cpu_saved_pct,
       watcher_pressure_pct,decision_savings_pct
       FROM cpu_feedback WHERE split='holdout_seed_only'
       ORDER BY seed""").fetchall()
    for name,seed,cpu,watch,dec in rows:
        summary[name].append(dict(seed=seed,cpu_saved_pct=cpu,
            watch_extra_pct=watch,decisions_saved_pct=dec))
    all_modes={}
    for mode in PRINCIPLES:
        records=conn.execute("""SELECT process_cpu_s,wrapper_wall_s,
            native_decisions,native_propagations,watch_visits,watch_units,
            watch_satisfied,trace_enabled
            FROM observation WHERE split='holdout_seed_only' AND mode=?""",(mode,)).fetchall()
        off=[x for x in records if x[-1]==0]
        on=[x for x in records if x[-1]==1]
        need(len(off)==8 and len(on)==4,"mode missing off/on")
        all_modes[mode]=dict(
          off_trials=8,on_trials=4,
          off_solve_cpu_sum_s=round(sum(x[0] for x in off),6),
          off_solve_cpu_mean_s=round(statistics.mean(x[0] for x in off),6),
          off_total_wrapper_wall_s=round(sum(x[1] for x in off),6),
          mean_native_decisions=round(statistics.mean(x[2] for x in off),2),
          mean_native_propagations=round(statistics.mean(x[3] for x in off),2),
          mean_binary_watch_visits=round(statistics.mean(x[4] for x in on),2),
          mean_binary_watch_units=round(statistics.mean(x[5] for x in on),2),
          mean_binary_watch_satisfied=round(statistics.mean(x[6] for x in on),2))
    report=dict(protocol=PROTO,source_count=1,source_disjoint_holdout=False,
       fresh_seed_holdout=True,
       total_measurements=len(holdouts),original_SAT_witness_checked_all=True,
       cpu_effect_is_full_native_solve_not_per_watcher_cycles=True,
       prep_and_proof_cost_excluded_from_solve_cpu=True,
       proof_certified_equivalence_required=True,
       frozen_calibration_policy=rule["online_policy"],
       no_auto_promotion_from_one_formula=True,
       principle_feedback={k:dict(kind=PRINCIPLES[k]["kind"],
             results=v,seed_wins=sum(x["cpu_saved_pct"]>0 for x in v),
             seed_count=len(v)) for k,v in summary.items()},
       by_mode=all_modes)
    conn.commit()
    conn.close()
    pathlib.Path(out).write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE6_FINAL",json.dumps(report,sort_keys=True),flush=True)

def selftest():
    need(len(PRINCIPLES)==7 and MIN_SOURCE_DISJOINT>=3,"gate safety constants")
    c=sqlite3.connect(":memory:")
    create_db(c)
    x=fit(c)
    need(x["online_policy"]=="xor" and
         x["scored"]["quotient"]["reason"]=="not_yet_measured",
         "unproven mathematical principle incorrectly promoted")
    c.close()
    print("MRE6_FEEDBACK_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","train","audit"))
    p.add_argument("--calibration-dir",default="mre6/calibration")
    p.add_argument("--holdout-dir",default="mre6")
    p.add_argument("--feedback",default="mre6/frozen_feedback.json")
    p.add_argument("--db",default="mre6/principles.sqlite")
    p.add_argument("--report",default="mre6/report.json")
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="train":train(args.calibration_dir,args.feedback,args.db)
    else:audit(args.holdout_dir,args.feedback,args.db,args.report)
