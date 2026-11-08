#!/usr/bin/env python3
"""DRNAS S2. Fixed S1-derived routing, tested on 12 disjoint C3 originals.
S1 trained cohort: 20 other source SHAs. C3 SHA12 test has historical
reference outcomes, so NOT a global blind evaluation.
Five arms: native CMS, Kissat, CaDiCaL, S2 conservative, S2 CMS-guarded.
Original SAT model verification, CaDiCaL cross-check, 12s wall cap, 4 repeats.
"""
from __future__ import annotations
import argparse,collections,json,pathlib,random,statistics,subprocess,time,os
import drnas_s1_structural_router as s1
import c3_dedup_sha12_validation as c3
import c2_cnf_clean_ablation as c2
import r195_native_cms_benchmark as cms
PROTO="DRNAS-S2-C3SHA12-5ARM-4REP-12S-S1TRAINED-v1"
ROOT=pathlib.Path("s2_router")
MODES=("cpp_native","kissat","cadical","s2_conservative","s2_cms_guarded")
REPS=4;SHARDS=4;CAP=12.0
def need(x,msg):
    if not x:raise RuntimeError("S2_FAIL_CLOSED "+msg)
def save(p,obj):s1.save(p,obj)
def sources():
    cs=c3.original_cases()
    need(len(cs)==12 and len({x["sha256"] for x in cs})==12,"C3 original SHA12 drift")
    for c in cs:need(s1.sha(c3.SRC/c["filename"])==c["sha256"],"C3 source SHA drift")
    return cs
def route(mode,f):
    """Pre-registered from 20 S1 cases, before any S2 runs.
    Default CaDiCaL to eliminate S1 CMS false positives. Kissat only on
    strong structural patterns; CMS-guarded adds a tiny fast-case rule.
    This is a research hypothesis, NOT learned or optimized on C3 cases."""
    need(mode in ("s2_conservative","s2_cms_guarded"),"unknown S2 route")
    if mode=="s2_cms_guarded" and f["observed"]<=12000 and (
        f["binary_frac"]>=0.96 and f["horn_frac"]>=0.96 and f["duplicate_frac"]<0.005
    ):
        return "cpp_native","high_binary_high_horn_low_dup_CMS_hypothesis"
    if f["binary_frac"]>=0.95 and f["horn_frac"]<0.90:
        return "kissat","binary_dominant_nonhorn_Kissat"
    if f["observed"]<2000 and f["binary_frac"]<0.2 and 0.45<=f["horn_frac"]<=0.60 and f["duplicate_frac"]<0.01:
        return "kissat","small_lowbinary_mixedhorn_Kissat"
    return "cadical","safe_CaDiCaL_default"
def selftest():
    x=dict(observed=5000,binary_frac=.7,horn_frac=.7,duplicate_frac=0)
    need(route("s2_conservative",x)[0]=="cadical","default")
    x["binary_frac"]=.98;x["horn_frac"]=.8
    need(route("s2_conservative",x)[0]=="kissat","kissat")
    x["horn_frac"]=.99
    need(route("s2_cms_guarded",x)[0]=="cpp_native","cms")
    need(route("s2_conservative",x)[0]=="cadical","no cms in conservative")
    print("S2_RULES_FROZEN_SELFTEST_PASS",flush=True)
def trial(c,rep,mode):
    need(rep in range(REPS) and mode in MODES,"wrong rep/mode")
    src=c3.SRC/c["filename"];need(s1.sha(src)==c["sha256"],"source drift")
    start=time.perf_counter();f=None;backend=mode;why="reference"
    if mode.startswith("s2_"):
        f=s1.features(src)
        backend,why=route(mode,f)
    prep=time.perf_counter()-start
    remaining=CAP-prep
    if remaining<=0:
        return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],rep=rep,
          mode=mode,backend=backend,reason=why,features=f,preprocess_s=round(prep,6),
          status="TIMEOUT",wall_s=round(prep,6),par2_s=2*CAP,cap_s=CAP)
    if backend=="cpp_native":
        cmd=[str(pathlib.Path("c2/bin/native").resolve()),str(src.resolve()),
             "cpp_native",str(c3.seed(c,rep))]
    elif backend=="kissat":
        cmd=[str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),str(src.resolve())]
    else:
        need(backend=="cadical","unknown backend")
        cmd=["/usr/bin/cadical",str(src.resolve())]
    env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
    try:p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                         timeout=remaining,check=False,env=env)
    except subprocess.TimeoutExpired:p=None
    elapsed=time.perf_counter()-start
    status="TIMEOUT";verified=False
    if p is not None:
        if backend=="cpp_native":
            need(p.returncode==0,"native subprocess failed "+p.stderr[-200:])
            gate=c2.parse_native_gate(p.stdout,"cpp_native")
            need(not gate["applied"],"native changed source")
            status,model,_=cms.parsed_native(p.stdout)
        else:
            status,model=c2.ref.external_parse(p)
        if status=="SAT":
            cms.verify_model(src,model);verified=True
    if status not in ("SAT","UNSAT") or elapsed>CAP:
        status="TIMEOUT";verified=False
    if status!="TIMEOUT":
        need(status==c["reference_screen_status"],"contradiction with original reference")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],rep=rep,
       mode=mode,backend=backend,reason=why,features=f,
       preprocess_s=round(prep if f else 0,6),
       status=status,SAT_witness_original_verified=verified,
       UNSAT_prior_CaDiCaL_without_LRAT=(status=="UNSAT"),
       wall_s=round(elapsed,6),
       par2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),cap_s=CAP)
def shard(index):
    need(index in range(SHARDS),"invalid shard")
    cases=sources()[index::SHARDS];need(len(cases)==3,"not 3 sources")
    rows=[]
    for c in cases:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                x=trial(c,rep,mode)
                rows.append(x)
                save(ROOT/f"shard-{index}.json",rows)
                print("S2_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==60,"incomplete shard")
    print("S2_SHARD_PASS",index,len(rows),flush=True)
def audit():
    cases=sources();by_sha={c["sha256"]:c for c in cases}
    rows=[];seen=set();pairs=collections.defaultdict(dict)
    for i in range(SHARDS):
        p=ROOT/f"shard-{i}.json"
        need(p.exists(),"missing shard")
        r=json.loads(p.read_text())
        need(len(r)==60,"partial shard")
        rows+=r
    need(len(rows)==240,"missing 240 trials")
    for r in rows:
        c=by_sha.get(r["sha256"])
        need(c and r["gbd"]==c["gbd"] and r["protocol"]==PROTO and
             r["cap_s"]==CAP and r["rep"] in range(REPS) and r["mode"] in MODES,
             "source or protocol mismatch")
        if r["mode"].startswith("s2_"):
            need(r["features"] is not None and route(r["mode"],r["features"])[0]==r["backend"],
                 "router decision changed")
        else:need(r["mode"]==r["backend"],"reference backend mismatch")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
        if r["status"]=="SAT":need(r["SAT_witness_original_verified"],"SAT not verified")
        if r["status"]=="UNSAT":need(r["UNSAT_prior_CaDiCaL_without_LRAT"],"UNSAT missing crosscheck")
        need(abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT" else r["wall_s"]))<0.000003,
             "PAR2 mismatch")
        key=(r["sha256"],r["rep"],r["mode"])
        need(key not in seen,"duplicate trial");seen.add(key)
        pairs[(r["sha256"],r["rep"])][r["mode"]]=r
    need(len(seen)==240 and len(pairs)==48 and all(set(x)==set(MODES) for x in pairs.values()),
         "incomplete paired matrix")
    for pair in pairs.values():
        need(len({r["status"] for r in pair.values() if r["status"]!="TIMEOUT"})<=1,
             "cross-solver SAT/UNSAT contradiction")
    scores={}
    for m in MODES:
        a=[r for r in rows if r["mode"]==m]
        scores[m]=dict(trials=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
          timeouts=sum(r["status"]=="TIMEOUT" for r in a),
          SAT=sum(r["status"]=="SAT" for r in a),
          UNSAT_no_independent_LRAT=sum(r["status"]=="UNSAT" for r in a),
          PAR2_s=round(sum(r["par2_s"] for r in a),6),
          preprocessing_s=round(sum(r["preprocess_s"] for r in a),6),
          backend_counts=dict(collections.Counter(r["backend"] for r in a)))
    base=scores["cadical"]["PAR2_s"]
    for s in scores.values():s["speedup_vs_CaDiCaL_x"]=round(base/s["PAR2_s"],6)
    per=[]
    for c in cases:
        a=[r for r in rows if r["sha256"]==c["sha256"]]
        per.append(dict(SHA=c["sha256"],GBD=c["gbd"],
          by_mode={m:dict(PAR2_s=round(sum(r["par2_s"] for r in a if r["mode"]==m),6),
              solved=sum(r["status"]!="TIMEOUT" for r in a if r["mode"]==m))
              for m in MODES}))
    report=dict(protocol=PROTO,status="S2_AUDIT_PASS",trials=240,
      original_SHA12_disjoint_from_S1=True,
      historical_C3_results_known_not_globally_blind=True,
      rule_frozen_before_benchmark=True,
      no_pilot_solver_before_route=True,
      full_wall_includes_feature_scan=True,
      Kissat_and_CaDiCaL_default_seed_repeated=True,
      original_SAT_witness_verified=True,UNSAT_no_independent_LRAT=True,
      no_auto_promotion=True,scores=scores,per_source=per)
    save(ROOT/"report.json",report)
    print("S2_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},sort_keys=True),flush=True)
    for c in per:print("S2_CASE",json.dumps(c,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("verify","selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="verify":print("S2_C3_SHA12_PASS",len(sources()),flush=True)
    elif a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard)
    else:audit()
