#!/usr/bin/env python3
"""C3 SHA12 native, C3 source-only dedup vs pinned Kissat 4.0.4.
12 EXACT previously frozen original CNFs, 4 fresh repetitions, 12-s wall cap,
original-CNF SAT witness verified; UNSAT concordance w/ prior CaDiCaL.
Kissat runs default seed unless --seed support is independently proven.
Prior C3 results serve context only; all reported three-arm times run fresh.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,statistics,subprocess,time
import c3_dedup_sha12_validation as c3
import c2_cnf_clean_ablation as c2
import r195_native_cms_benchmark as cms

PROTO="DRNAS-C3-VS-KISSAT4.0.4-EXACT-SHA12-3ARM-4REP-12S-PAR2-v1"
ROOT=pathlib.Path("c3_kissat")
SHARDS=4
REPS=4
CAP=12.0
MODES=("cpp_native","cpp_dedup","kissat")
def need(b,msg):
    if not b:raise RuntimeError("C3_KISSAT_FAIL_CLOSED "+msg)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def sources():
    return c3.original_cases()
def seed(case,rep):
    return c3.seed(case,rep)
def trial(c,rep,mode,kissat):
    need(0<=rep<REPS and mode in MODES,"wrong repetition/mode")
    src=c3.SRC/c["filename"]
    need(sha(src)==c["sha256"],"source drift "+c["gbd"])
    s=seed(c,rep)
    # Kissat is explicitly default-seeded, matching the established MRE11B
    # Kissat reference policy. Four Kissat repeats are not four independent seeds.
    cmd=([str(pathlib.Path(kissat).resolve()),str(src.resolve())] if mode=="kissat"
         else [str(pathlib.Path("c2/bin/native").resolve()),
               str(src.resolve()),mode,str(s)])
    env=os.environ.copy()
    env.pop("DRNAS_MAX_CONFLICTS",None)
    st=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                         check=False,timeout=CAP,env=env)
    except subprocess.TimeoutExpired:
        p=None
    elapsed=time.perf_counter()-st
    status="TIMEOUT";gate={};verified=False;native=None
    if p is not None:
        if mode=="kissat":
            status,model=c2.ref.external_parse(p)
        else:
            need(p.returncode==0,"C2 native subprocess exited badly "+p.stderr[-400:])
            gate=c2.parse_native_gate(p.stdout,mode)
            status,model,native=cms.parsed_native(p.stdout)
        if status=="SAT":
            cms.verify_model(src,model)
            verified=True
        need(status in ("SAT","UNSAT","UNKNOWN"),"unexpected solver status")
    if status not in ("SAT","UNSAT") or elapsed>CAP:
        status="TIMEOUT";verified=False
    if status!="TIMEOUT":
        need(status==c["reference_screen_status"],
             "contradiction with prior CaDiCaL original reference")
    if mode=="cpp_native" and status!="TIMEOUT":
        need(not gate["applied"],"native unexpectedly modified original")
    if mode=="cpp_dedup" and status!="TIMEOUT":
        need(gate["duplicate_literals_removed"]==0
             and gate["taut_clauses_removed"]==0
             and gate["variables_eliminated"]==0,
             "dedup changed mechanisms beyond exact duplicates")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
       year=c["year"],rep=rep,
       native_seed=s if mode!="kissat" else None,
       kissat_default_seed=(mode=="kissat"),mode=mode,
       status=status,SAT_original_witness_verified=verified,
       UNSAT_prior_CaDiCaL_crosschecked_no_independent_LRAT=(status=="UNSAT"),
       wall_s=round(elapsed,6),
       par2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
       native_stats=native,gate=gate,cap_s=CAP,
       native_C2_binary_pinned=True,kissat_pinned_4_0_4=True)
def shard(idx,kissat):
    cases=sources()
    need(0<=idx<SHARDS,"invalid shard")
    ss=[c for i,c in enumerate(cases) if i%SHARDS==idx]
    need(len(ss)==3,"shard must have 3 frozen CNFs")
    rows=[]
    for c in ss:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,rep,mode,kissat)
                rows.append(r)
                save(ROOT/f"shard-{idx}.json",rows)
                print("C3_KISSAT_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==3*REPS*len(MODES),"incomplete shard")
    print("C3_KISSAT_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cases=sources()
    by_sha={c["sha256"]:c for c in cases}
    rows=[];seen=set()
    for i in range(SHARDS):
        f=ROOT/f"shard-{i}.json"
        need(f.exists(),"missing shard "+str(i))
        x=json.loads(f.read_text())
        need(len(x)==36,"incomplete 36-trial shard "+str(i))
        rows+=x
    need(len(rows)==12*REPS*len(MODES),"wrong measurement total")
    for r in rows:
        c=by_sha.get(r["sha256"])
        need(c is not None and r["gbd"]==c["gbd"] and r["protocol"]==PROTO
            and r["mode"] in MODES and r["rep"] in range(REPS)
            and r["cap_s"]==CAP,"alien CNF or protocol")
        need(r["native_seed"]==(seed(c,r["rep"]) if r["mode"]!="kissat" else None),
             "native seed pairing mismatch")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid status")
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"]
                 and c["reference_screen_status"]=="SAT","bad SAT witness")
        if r["status"]=="UNSAT":
            need(r["UNSAT_prior_CaDiCaL_crosschecked_no_independent_LRAT"]
                 and c["reference_screen_status"]=="UNSAT","bad UNSAT")
        expected=(2*CAP if r["status"]=="TIMEOUT" else r["wall_s"])
        need(abs(r["par2_s"]-expected)<0.000003,"invalid PAR2")
        k=(c["sha256"],r["rep"],r["mode"])
        need(k not in seen,"duplicate source-repeat-mode");seen.add(k)
    need(len(seen)==144,"missing trial")
    def score(rr):
        result={}
        for mode in MODES:
            v=[r for r in rr if r["mode"]==mode]
            result[mode]=dict(trials=len(v),
                solved=sum(r["status"]!="TIMEOUT" for r in v),
                SAT=sum(r["status"]=="SAT" for r in v),
                UNSAT_no_independent_LRAT=sum(r["status"]=="UNSAT" for r in v),
                timeouts=sum(r["status"]=="TIMEOUT" for r in v),
                PAR2_total_s=round(sum(r["par2_s"] for r in v),6),
                sum_observed_wall_s=round(sum(r["wall_s"] for r in v),6),
                median_observed_wall_s=round(statistics.median(r["wall_s"] for r in v),6)
                   if v else None)
        native=result["cpp_native"]["PAR2_total_s"]
        for x in result.values():
            x["speedup_vs_native_x"]=round(native/x["PAR2_total_s"],6) if x["PAR2_total_s"]>0 else None
        return result
    per_source=[]
    for c in cases:
        rr=[r for r in rows if r["sha256"]==c["sha256"]]
        by_mode={}
        for mode in MODES:
            v=[r for r in rr if r["mode"]==mode]
            by_mode[mode]=dict(PAR2_total_s=round(sum(r["par2_s"] for r in v),6),
                              PAR2_mean_s=round(sum(r["par2_s"] for r in v)/REPS,6),
                              solved=sum(r["status"]!="TIMEOUT" for r in v),
                              SAT=sum(r["status"]=="SAT" for r in v),
                              UNSAT=sum(r["status"]=="UNSAT" for r in v),
                              median_wall_s=round(statistics.median(r["wall_s"] for r in v),6))
        per_source.append(dict(label=c["sha256"][:8],GBD=c["gbd"],
                               SHA=c["sha256"],status=c["reference_screen_status"],
                               source_year=c["year"],by_mode=by_mode))
    result=dict(protocol=PROTO,source_count=12,repetitions=REPS,
        source_seed_pairs=48,cap_s=CAP,total_trials=144,
        same_original_source_SHA_as_C3=True,
        exact_pinned_C2_native_and_dedup=True,kissat_pinned_version="4.0.4",
        Kissat_default_seed_repeated_not_four_independent_seeds=True,
        native_sha_seeds_repeated_with_same_source=True,
        measured_new_in_same_runner_type=True,
        cohort_development_reused_not_blind=True,
        SAT_original_witness_verified=True,
        UNSAT_prior_CaDiCaL_agreement_without_independent_LRAT=True,
        no_auto_promotion=True,
        scores=score(rows),per_source=per_source)
    save(ROOT/"report.json",result)
    print("C3_KISSAT_FINAL",json.dumps({k:v for k,v in result.items() if k!="per_source"},
                                      sort_keys=True),flush=True)
    for c in per_source:print("C3_KISSAT_CASE",json.dumps(c,sort_keys=True),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--kissat",default="built/bin/kissat_4_0_4")
    args=ap.parse_args()
    if args.action=="verify":
        print("C3_KISSAT_SHA12_FROZEN_PASS",len(sources()),flush=True)
    elif args.action=="shard":shard(args.shard,args.kissat)
    else:audit()
