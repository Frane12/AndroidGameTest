#!/usr/bin/env python3
"""DRNAS S1: SHA-held-out source-only router, 2-way and 3-way fixed structural rules.
C3 SHA12 is development/training inspiration only, never benchmarked in S1.
Validate on 8 MRE11B + 12 MRE10B previously frozen actual original sources.
Both cohorts have PRIOR published benchmark results; this is NOT globally blind.
Route cannot look at solver outcomes, source IDs, seed, or timer.
Exact C3 C2 native CMS + pinned Kissat 4.0.4 + CaDiCaL; 15s full end-to-end.
SAT original model replay; UNSAT cross solver agreement, not independent LRAT.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,statistics,subprocess,time
import c2_cnf_clean_ablation as c2
import c3_dedup_sha12_validation as c3
import r195_native_cms_benchmark as cms

PROTO="DRNAS-S1-20EXTERNAL-SHA-DISJOINT-C3-3BACKENDS-2ROUTERS-2REP-15S-PAR2-v1"
ROOT=pathlib.Path("s1_router")
SOURCES=ROOT/"sources"
REPS=2; SHARDS=5; CAP=15.0
MODES=("cpp_native","kissat","cadical","s1_route2","s1_route3")
MAX_SCAN_BYTES=1024*1024
MAX_CLAUSES=12000
def need(ok,msg):
    if not ok:raise RuntimeError("DRNAS_S1_FAIL_CLOSED "+msg)
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for x in iter(lambda:f.read(1<<20),b""):h.update(x)
    return h.hexdigest()
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def seed(case,rep):
    return int(hashlib.sha256((PROTO+"|native-seed|"+case["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)

def freeze():
    SOURCES.mkdir(parents=True,exist_ok=True)
    j11=json.loads(pathlib.Path("s1_import11/mre11b_blind/manifest.json").read_text())
    j10=json.loads(pathlib.Path("s1_import10/mre10b_sources/manifest.json").read_text())
    need(j11["protocol"]=="DRNAS-MRE11B-MINISAT1M-SOURCELOCK-2021-23-8SHA-20261108-v1",
         "unexpected MRE11B cohort")
    need(j10["protocol"]=="DRNAS-MRE10B-12FRESH2023TO2025-EXTERNAL-CADICAL-15S-3SEED-4ARM",
         "unexpected MRE10B cohort")
    need(len(j11["source_cases"])==8 and len(j10["cases"])==12,"source cohort size drift")
    c3shas={c["sha256"] for c in c3.original_cases()}
    items=[]
    for cohort,cases,source_dir in (
      ("MRE11B_SOURCELOCK",j11["source_cases"],pathlib.Path("s1_import11/mre11b_blind")),
      ("MRE10B_EXTERNAL",j10["cases"],pathlib.Path("s1_import10/mre10b_sources"))):
        for c in cases:
            raw=source_dir/c["filename"]
            need(raw.is_file() and sha(raw)==c["sha256"],"source SHA mismatch")
            name=cohort+"-"+c["sha256"][:20]+".cnf"
            target=SOURCES/name;target.write_bytes(raw.read_bytes())
            items.append(dict(name=name,sha256=c["sha256"],gbd=c["gbd"],
              year=c["year"],bytes=target.stat().st_size,cohort=cohort,
              prior_reference_status=c.get("reference_screen_status","UNKNOWN")))
    need(len(items)==20 and len({c["sha256"] for c in items})==20,
         "20 original source SHA not disjoint across reference cohorts")
    need(not ({c["sha256"] for c in items}&c3shas),
         "holdout source overlaps prior C3 router-development SHA")
    for c in items:need(sha(SOURCES/c["name"])==c["sha256"],"copied source drift")
    save(ROOT/"manifest.json",dict(protocol=PROTO,cases=items,total_cases=20,
        modes=list(MODES),cap_s=CAP,reps=REPS,planned_trials=200,
        old_C3_SHA12_excluded=True,source_outcome_not_used_for_routing=True,
        source_cohorts_prior_tested_not_blind=True,proof_independent_LRAT=False,
        no_auto_promotion=True,rule_version="S1-LOCKED-r0-no-calibration",
        source_only_limit_bytes=MAX_SCAN_BYTES,source_only_limit_clauses=MAX_CLAUSES))
    (ROOT/"sources.sha256").write_text("".join(
        c["sha256"]+"  sources/"+c["name"]+"\n" for c in items))
    print("S1_FROZEN_20_SHA_DISJOINT_PASS",json.dumps(dict(
      cases=20,overlap_C3=0,reps=REPS,arms=MODES),sort_keys=True),flush=True)

def cases():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["total_cases"]==20 and
         m["cap_s"]==CAP and m["reps"]==REPS and
         m["modes"]==list(MODES),"manifest changed")
    cc=m["cases"]
    need(len(cc)==20 and len({c["sha256"] for c in cc})==20,"SHA duplicated")
    for c in cc:
        p=SOURCES/c["name"]
        need(p.is_file() and sha(p)==c["sha256"] and
             p.stat().st_size==c["bytes"],"SHA mismatch")
    return cc

def features(path):
    """Hard capped, deterministic original-CNF prefix; no Python solver or probe."""
    started=time.perf_counter()
    nvars=None;count=0;horn=0;binary=0;units=0;dups=0;seen=set()
    scanned=0
    with pathlib.Path(path).open("rb") as f:
        for raw in f:
            scanned+=len(raw)
            if scanned>MAX_SCAN_BYTES or count>=MAX_CLAUSES:break
            s=raw.strip()
            if not s or s.startswith(b"c"):continue
            if s.startswith(b"p "):
                parts=s.split()
                need(len(parts)==4 and parts[1]==b"cnf","invalid header")
                nvars=int(parts[2]);continue
            need(nvars is not None,"missing original header")
            try:lit=[int(v) for v in s.split()]
            except ValueError:raise RuntimeError("DRNAS_S1_FAIL_CLOSED invalid source integer")
            need(lit and lit[-1]==0 and all(0<abs(x)<=nvars for x in lit[:-1]),
                 "noncanonical source line in bounded scanner")
            clause=lit[:-1];count+=1
            if len(clause)==2:binary+=1
            if len(clause)==1:units+=1
            if sum(l>0 for l in clause)<=1:horn+=1
            key=tuple(sorted(set(clause)))
            if key in seen:dups+=1
            else:seen.add(key)
    need(nvars is not None and count>0,"insufficient source features")
    return dict(nvars=nvars,observed=count,
                binary_frac=round(binary/count,6),
                horn_frac=round(horn/count,6),
                duplicate_frac=round(dups/count,6),
                unit_frac=round(units/count,6),
                scanned_bytes=min(scanned,MAX_SCAN_BYTES),
                cost_s=round(time.perf_counter()-started,8),
                truncated=(scanned>MAX_SCAN_BYTES or count>=MAX_CLAUSES))
def select(mode,f):
    """Rules frozen based on C3 qualitative pattern and R135 structural criteria.
    No source SHA or input name used in the routing decision."""
    need(mode in ("s1_route2","s1_route3"),"invalid router")
    if f["duplicate_frac"]>=0.025 or f["binary_frac"]>=0.42:
        return "cpp_native","dense_binary_or_duplicates_use_CMS"
    if mode=="s1_route2":
        return "kissat","otherwise_use_Kissat"
    if f["observed"]>=32 and f["binary_frac"]<0.25 and f["horn_frac"]<0.55:
        return "cadical","sparse_nonhorn_use_CaDiCaL"
    return "kissat","otherwise_use_Kissat"
def selftest():
    # Rule has neither source SHA/GBD nor previous outcome as input.
    f=dict(nvars=100,observed=100,binary_frac=0.6,horn_frac=0.7,
           duplicate_frac=0.0,unit_frac=0.0,scanned_bytes=1000,cost_s=0,truncated=False)
    need(select("s1_route2",f)[0]=="cpp_native","router2 dense")
    need(select("s1_route3",f)[0]=="cpp_native","router3 dense")
    f["binary_frac"]=0.05;f["horn_frac"]=0.2
    need(select("s1_route2",f)[0]=="kissat","router2 light")
    need(select("s1_route3",f)[0]=="cadical","router3 sparse")
    f["horn_frac"]=0.9
    need(select("s1_route3",f)[0]=="kissat","router3 horn")
    print("S1_SOURCE_ONLY_SELECTOR_SELFTEST_PASS",flush=True)
def trial(c,rep,mode):
    need(rep in range(REPS) and mode in MODES,"bad mode/repeat")
    src=SOURCES/c["name"];need(sha(src)==c["sha256"],"SHA changed")
    start=time.perf_counter()
    profile=None;selected=mode;reason="reference_arm"
    if mode.startswith("s1_route"):
        profile=features(src)
        selected,reason=select(mode,profile)
    prep_s=time.perf_counter()-start
    remaining=CAP-prep_s
    need(remaining>0,"nonpositive full-wall budget")
    env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
    if selected=="cpp_native":
        cmd=[str(pathlib.Path("c2/bin/native").resolve()),
             str(src.resolve()),"cpp_native",str(seed(c,rep))]
    elif selected=="kissat":
        cmd=[str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),str(src.resolve())]
    else:
        need(selected=="cadical","unregistered backend")
        cmd=["/usr/bin/cadical",str(src.resolve())]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,check=False,errors="replace",
                         timeout=remaining,env=env)
    except subprocess.TimeoutExpired:p=None
    elapsed=time.perf_counter()-start
    verdict="TIMEOUT";model={};native=None
    if p is not None:
        if selected=="cpp_native":
            need(p.returncode==0,"C2 native process failure "+p.stderr[-250:])
            gate=c2.parse_native_gate(p.stdout,"cpp_native")
            need(not gate["applied"],"CMS control transformed original")
            verdict,model,native=cms.parsed_native(p.stdout)
        else:
            verdict,model=c2.ref.external_parse(p)
        if verdict=="SAT":cms.verify_model(src,model)
    if verdict not in ("SAT","UNSAT") or elapsed>CAP:verdict="TIMEOUT"
    prior=c["prior_reference_status"]
    if verdict in ("SAT","UNSAT") and prior!="UNKNOWN":
        need(prior==verdict,"source status disagrees with source-only CaDiCaL pretest")
    return dict(protocol=PROTO,source_sha256=c["sha256"],cohort=c["cohort"],
      gbd=c["gbd"],rep=rep,mode=mode,backend=selected,selection_reason=reason,
      seed=seed(c,rep),external_default_seed=(selected!="cpp_native"),
      status=verdict,original_SAT_witness_checked=(verdict=="SAT"),
      UNSAT_without_LRAT=(verdict=="UNSAT"),
      gate_source_only=profile,preprocess_s=round(prep_s if profile else 0,6),
      wall_s=round(elapsed,6),
      par2_s=round(elapsed if verdict!="TIMEOUT" else 2*CAP,6),cap_s=CAP)
def shard(index):
    need(index in range(SHARDS),"bad shard")
    ss=cases()[index::SHARDS];need(len(ss)==4,"unexpected shard source count")
    rows=[]
    for c in ss:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                rec=trial(c,rep,mode);rows.append(rec)
                save(ROOT/f"shard-{index}.json",rows)
                print("S1_TRIAL",json.dumps(rec,sort_keys=True),flush=True)
    need(len(rows)==40,"shard trial shortfall")
    print("S1_SHARD_PASS",index,len(rows),flush=True)
def audit():
    cc=cases();by_sha={c["sha256"]:c for c in cc};rows=[]
    for i in range(SHARDS):
        r=json.loads((ROOT/f"shard-{i}.json").read_text())
        need(len(r)==40,"incomplete shard")
        rows+=r
    need(len(rows)==200,"incorrect 200-trial benchmark count")
    paired=collections.defaultdict(dict)
    for r in rows:
        c=by_sha.get(r["source_sha256"])
        need(c is not None and r["gbd"]==c["gbd"] and r["cohort"]==c["cohort"]
             and r["protocol"]==PROTO and r["cap_s"]==CAP
             and r["rep"] in range(REPS) and r["mode"] in MODES
             and r["seed"]==seed(c,r["rep"]),"SHA/seed/protocol mismatch")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"unknown status")
        if r["status"]=="SAT":need(r["original_SAT_witness_checked"],"bad SAT")
        if r["status"]=="UNSAT":need(r["UNSAT_without_LRAT"],"bad UNSAT provenance")
        expected=2*CAP if r["status"]=="TIMEOUT" else r["wall_s"]
        need(abs(r["par2_s"]-expected)<0.000002,"PAR2 mismatch")
        if r["mode"].startswith("s1_route"):
            need(r["gate_source_only"] is not None and
                 select(r["mode"],r["gate_source_only"])[0]==r["backend"],
                 "router decision changed after measurement")
        else:
            need(r["mode"]==r["backend"],"reference route changed")
        key=(r["source_sha256"],r["rep"])
        need(r["mode"] not in paired[key],"duplicate mode")
        paired[key][r["mode"]]=r
    need(len(paired)==40 and all(set(z)==set(MODES) for z in paired.values()),
         "incomplete 40 five-arm source-rep pairs")
    # Ensure terminal answer consistency; timed out allowed.
    for ss in paired.values():
        outcomes={r["status"] for r in ss.values() if r["status"]!="TIMEOUT"}
        need(len(outcomes)<=1,"contradictory solver SAT/UNSAT")
    def scores(rs):
        out={}
        for m in MODES:
            v=[x for x in rs if x["mode"]==m]
            out[m]=dict(trials=len(v),solved=sum(x["status"]!="TIMEOUT" for x in v),
              SAT=sum(x["status"]=="SAT" for x in v),
              UNSAT_without_independent_LRAT=sum(x["status"]=="UNSAT" for x in v),
              timeouts=sum(x["status"]=="TIMEOUT" for x in v),
              PAR2_s=round(sum(x["par2_s"] for x in v),6),
              preprocess_s=round(sum(x["preprocess_s"] for x in v),6),
              selected_backends=dict(collections.Counter(x["backend"] for x in v)))
        n=out["cpp_native"]["PAR2_s"]
        for x in out.values():
            x["speedup_vs_native_x"]=round(n/x["PAR2_s"],6) if x["PAR2_s"] else None
        return out
    groups={"all":rows}
    for cohort in sorted({r["cohort"] for r in rows}):
        groups[cohort]=[r for r in rows if r["cohort"]==cohort]
    result=dict(status="S1_AUDIT_PASS",protocol=PROTO,cases=len(cc),trials=len(rows),
       cap_s=CAP,repetitions=REPS,
       matched_source_seed=40,
       trained_on_C3_not_in_this_cohort=True,
       source_reused_development_not_global_blind=True,
       no_solver_probe_before_route=True,
       full_wall_preprocess_charged=True,
       original_SAT_verified=True,
       UNSAT_no_independent_LRAT=True,
       external_default_seeds_not_independent=True,
       no_auto_promotion=True,
       scores=scores(rows),by_cohort={k:scores(v) for k,v in groups.items() if k!="all"})
    per=[]
    for c in cc:
        rr=[r for r in rows if r["source_sha256"]==c["sha256"]]
        by_mode={m:dict(PAR2_s=round(sum(z["par2_s"] for z in rr if z["mode"]==m),6),
                        solved=sum(z["status"]!="TIMEOUT" for z in rr if z["mode"]==m))
                 for m in MODES}
        per.append(dict(SHA=c["sha256"],cohort=c["cohort"],GBD=c["gbd"],by_mode=by_mode))
    result["per_source"]=per
    save(ROOT/"report.json",result)
    print("S1_FINAL",json.dumps({k:v for k,v in result.items() if k!="per_source"},sort_keys=True),flush=True)
    for row in per:print("S1_CASE",json.dumps(row,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","selftest","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="freeze":freeze()
    elif a.action=="verify":print("S1_SOURCE_VERIFY_PASS",len(cases()),flush=True)
    elif a.action=="selftest":selftest()
    elif a.action=="shard":shard(a.shard)
    else:audit()
