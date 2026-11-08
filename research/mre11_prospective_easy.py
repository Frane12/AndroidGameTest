#!/usr/bin/env python3
"""DRNAS MRE11-PROSP-EASY12 — newly source-disjoint to DECLARED registries,
official SAT Competition 2021–2023 Main originals, SHA-frozen before evaluation.
The source-only first stage uses GBD published 'minisat1m=yes' metadata;
the ONLY screening CPU criterion is original unmodified cpp_native CMS at
fixed seed 117 (0.12–3 s), SAT witness checked / UNSAT CaDiCaL crosschecked.
The other C++ arms and MRE11 gate are NEVER run during selection.
This is prospective BASELINE-CONDITIONED, not globally blind: exhaustive
exclusion of unpublished prior experiments cannot be promised. No fitting
selector thresholds; EXACT frozen 2026 MRE11 C++ CMS binary, no recompilation.
Four new frozen SHA-paired seeds per selected source and 12s end-to-end PAR2.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, re, subprocess
import time, urllib.parse, urllib.request
import mre11_easy_benchmark as base
import mre11_holdout as pinned
import mre6b_blind_freeze as history
import r195_native_cms_benchmark as ref

PROTO="DRNAS-MRE11-PROSP-GBD2021-23-INDEX-FALLBACK-REFEASY-12-5ARM-4SEED-12S-v2"
SALT="DRNAS-MRE11-PROSPECTIVE-EASY-SOURCE-INDEX-FALLBACK-GBD2021-23-20261108-V2"
ROOT=pathlib.Path("mre11_prospective")
PRIOR=pathlib.Path("old_ref/mre7_easy")
YEARS=(2021,2022,2023)
TARGET=12
MIN_READY=8
ATTEMPT_LIMIT=180
MAX_RAW=5*1024*1024
MAX_PLAIN=9*1024*1024
MAX_VARS=30000
MAX_CLAUSES=85000
MIN_BASELINE=0.12
MAX_BASELINE=3.0
SCREEN_TIMEOUT=4.0
CAP=12.0
REPS=4
SHARDS=4
MODES=base.MODES
INDEX="https://benchmark-database.de/getinstances?context=cnf&query="
SOURCE="https://benchmark-database.de/file/"
KNOWN_2026_ORIGINAL_SEVEN={
"15456f0d13b26f0b4b21525ef7d0d711",
"a45aefde8bb26edb9634004146d0de89",
"782b29d2d691fdc94e0ec5b899390e10",
"de8c42d50f1dbf43a731f1916dc6bf01",
"416e33a8463911546e4cd87d282a7e1e",
"db099269d468029b70419bf4a49e99a1",
"6ad453d6174581d982c4e75e37a38d79"
}
def need(ok,msg):
    if not ok: raise RuntimeError("MRE11_PROSP_FAIL_CLOSED "+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def save(path, obj):
    pathlib.Path(path).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def get(url,limit,seconds=28):
    q=urllib.request.Request(url,headers={"User-Agent":"DRNAS-MRE11-PROSPECTIVE-EASY/1.0"})
    with urllib.request.urlopen(q,timeout=seconds) as r:data=r.read(limit+1)
    need(len(data)<=limit,"resource cap on external original/index")
    return data
def frozen_manifest():
    f=PRIOR/"manifest.json"
    need(f.exists(),"missing original MRE7E registered development cohort")
    m=json.loads(f.read_text())
    need(m["protocol"]=="DRNAS-MRE7E-OLDER2021-2023-EXTENDED-EASY-20261108-v1" and
         m["selected"]==16,"unexpected historical MRE7E manifest")
    need(len(m["selected_cases"])==16,"incomplete historical list")
    for c in m["selected_cases"]:
        need(sha((PRIOR/c["filename"]).read_bytes())==c["sha256"],
             "original MRE7E SHA drift")
    return m
def pool():
    # Index-only: do not inspect MRE11 transform gates, ranking by independent
    # salt first, then baseline-only screen. No CPU/size results used in ranking.
    m=frozen_manifest()
    prior_ids={c["gbd"] for c in m["selected_cases"]}|KNOWN_2026_ORIGINAL_SEVEN
    if history.PRIOR.exists():
        for row in history.PRIOR.read_text().splitlines():
            row=row.strip()
            if re.fullmatch("[a-f0-9]{32}",row):prior_ids.add(row)
    all_entries=[]
    snapshots={}
    for year in YEARS:
        q_all="track=main_"+str(year)
        q_easy=q_all+" and minisat1m=yes"
        raw_all=get(INDEX+urllib.parse.quote(q_all,safe=""),400000,seconds=45)
        raw_easy=get(INDEX+urllib.parse.quote(q_easy,safe=""),400000,seconds=45)
        all_ids=[r.strip().rsplit("/",1)[-1] for r in raw_all.decode().splitlines() if r.strip()]
        easy=[r.strip().rsplit("/",1)[-1] for r in raw_easy.decode().splitlines() if r.strip()]
        need(len(all_ids)==400 and len(set(all_ids))==400,
             "official index "+str(year)+" not 400 unique GBDs")
        need(set(easy)<=set(all_ids),
             "minisat1m metadata source contains non-official GBDs")
        need(all(re.fullmatch(r"[0-9a-f]{32}",g) for g in all_ids),"bad official GBD ID")
        # Several older tracks have no useful published minisat1m=yes index.
        # Deterministic fallback: ALL official originals, baseline CMS screened
        # under exactly the same 0.12-3s criterion, never an MRE gate.
        use_easy=len(easy)>=15
        snapshots[str(year)]={"index_sha256":sha(raw_all),
            "minisat1m_yes_index_sha256":sha(raw_easy),
            "official_400":len(all_ids),"minisat1m_yes":len(easy),
            "index_easy_prefilter_available":use_easy,
            "fallback_to_salted_full_official":not use_easy}
        all_entries +=[(year,g,0) for g in easy] if use_easy else [(year,g,1) for g in all_ids]
    all_ids={g for year,g,tier in all_entries}
    repo_ids,old_shas=history.inspect_repo_ids(all_ids)
    prior_ids.update(repo_ids)
    ranked=sorted((y,g,tier) for y,g,tier in all_entries if g not in prior_ids)
    ranked.sort(key=lambda x:(x[2],sha((SALT+"|"+str(x[0])+"|"+x[1]).encode())))
    # One GBD source can appear in more than one competition; freeze it once.
    eligible=[];used=set()
    for year,g,tier in ranked:
        if g in used:continue
        used.add(g);eligible.append((year,g))
    need(len(eligible)>=ATTEMPT_LIMIT//3,"too few source-disjoint official inputs")
    return eligible,old_shas,{"indices":snapshots,
         "prior_original_gbds":len(prior_ids),
         "source_candidates":len(eligible),
         "known_prior_registry_not_globally_exhaustive":True,
         "minisat1m_index_used_when_available_else_full_official_fallback":True}

def screen(src,binary,cadical):
    # This is the ORIGINAL native CMS arm, not a DRNAS gate.
    start=time.perf_counter()
    env=os.environ.copy()
    p=None
    try:
        p=subprocess.run([str(pathlib.Path(binary).resolve()),str(src.resolve()),
            "cpp_native","117"],capture_output=True,text=True,timeout=SCREEN_TIMEOUT,
            check=False,errors="replace",env=env)
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":None}
    wall=time.perf_counter()-start
    need(p.returncode==0,"pinned original native failed "+p.stderr[-300:])
    gate=pinned.parse_gate(p.stdout)
    need(not gate["applied"],"baseline source selection accidentally transformed input")
    status,model,stats=ref.parsed_native(p.stdout)
    need(status in ("SAT","UNSAT","UNKNOWN","BUDGET"),"unexpected baseline result")
    if status=="SAT":ref.verify_model(src,model)
    if status=="UNSAT":
        try:
            check=subprocess.run([str(pathlib.Path(cadical).resolve()),str(src.resolve())],
                  capture_output=True,text=True,timeout=6.0,check=False)
        except subprocess.TimeoutExpired:
            return {"status":"UNSAT_CADICAL_CHECK_TIMEOUT","seconds":round(wall,6)}
        need(check.returncode in (10,20),"independent CaDiCaL process failed")
        if check.returncode!=20 or "UNSATISFIABLE" not in check.stdout:
            return {"status":"UNSAT_CADICAL_DISAGREEMENT","seconds":round(wall,6)}
    return {"status":status,"seconds":round(wall,6),
        "witness_checked":status=="SAT",
        "unsat_cross_solver":status=="UNSAT",
        "independent_lrat":False,"native_stats":stats}

def freeze(binary,cadical):
    ROOT.mkdir(exist_ok=True)
    entries,prior_shas,meta=pool()
    need(pathlib.Path(binary).exists() and pathlib.Path(cadical).exists(),
         "required CMS or independent CaDiCaL missing")
    selected=[];audit=[];statuses=collections.Counter(); years=collections.Counter()
    history.r32p.CNF_LIMIT=MAX_PLAIN
    for rank,(year,g) in enumerate(entries[:ATTEMPT_LIMIT]):
        if len(selected)>=TARGET:break
        row={"rank":rank,"year":year,"gbd":g}
        path=ROOT/(g+".cnf")
        try:
            if years[year]>=6:
                row["reason"]="fixed_max_six_per_year"
                audit.append(row);continue
            # No MRE11 gate is run during freeze, by design.
            raw=get(SOURCE+g,MAX_RAW,seconds=24)
            plain,method=history.r32p.decode(raw)
            need(len(plain)<=MAX_PLAIN,"plain DIMACS exceeds 9MiB")
            n,m=history.r32p.parse_dimacs_metadata(plain)
            need(n<=MAX_VARS and m<=MAX_CLAUSES,"original source geometry budget")
            digest=sha(plain)
            need(digest not in prior_shas and digest not in {v["sha256"] for v in selected},
                 "prior source digest or duplicate exact CNF")
            path.write_bytes(plain)
            verdict=screen(path,binary,cadical)
            row.update(vars=n,clauses=m,sha256=digest,compression=method,
                       original_baseline_screen=verdict)
            status=verdict["status"]
            # Precommitted balanced max 8 per status, not MRE response based.
            if status not in ("SAT","UNSAT"):
                row["reason"]="baseline_not_verified"
            elif statuses[status]>=8:
                row["reason"]="precommitted_status_quota"
            elif not (MIN_BASELINE<=verdict["seconds"]<=MAX_BASELINE):
                row["reason"]="outside_baseline_screen_band"
            else:
                row["reason"]="READY"
                c={"gbd":g,"filename":path.name,"sha256":digest,
                   "bytes":len(plain),"year":year,"variables":n,"clauses":m,
                   "reference_screen_status":status,
                   "reference_screen_s":verdict["seconds"],
                   "SAT_original_witness_reference_checked":status=="SAT",
                   "UNSAT_CaDiCaL_reference_crosschecked_no_LRAT":status=="UNSAT",
                   "source_url":SOURCE+g}
                selected.append(c);years[year]+=1;statuses[status]+=1
        except Exception as e:
            row.update(reason="fetch_resource_or_reference_error",
                       error=(type(e).__name__+": "+str(e))[:200])
        if row["reason"]!="READY":path.unlink(missing_ok=True)
        audit.append(row)
        print("MRE11_PROSP_SOURCE_SCAN",json.dumps(row,sort_keys=True),flush=True)
    need(len(selected)>=MIN_READY,"fewer than 8 previously unused baseline-easy originals")
    need(min(statuses.get("SAT",0),statuses.get("UNSAT",0))>=2,
         "cannot claim balanced SAT/UNSAT test")
    manifest={"protocol":PROTO,"cases":selected,"original_source_count":len(selected),
         "target":TARGET,"min_required":MIN_READY,"repetitions":REPS,
         "cap_s":CAP,"expected_trials":len(selected)*len(MODES)*REPS,
         "modes":list(MODES),"SAT_UNSAT_counts":dict(statuses),
         "year_counts":dict(years),"source_pool_metadata":meta,
         "rank_and_selection_before_DRNAS_gate":True,
         "reference_only_CMS_original_seed":117,
         "reference_only_runtime_band":[MIN_BASELINE,MAX_BASELINE],
         "selection_baseline_conditioned_not_unbiased_global_blind":True,
         "known_historical_registry_disjoint_not_exhaustive":True,
         "MRE11_selector_and_native_CMS_binary_frozen_from_run":42513542283,
         "independent_UNSAT_LRAT":False,
         "no_auto_promotion":True,"selection_trace":audit}
    save(ROOT/"manifest.json",manifest)
    (ROOT/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in selected))
    print("MRE11_PROSP_FREEZE_FINAL",json.dumps({
        "protocol":PROTO,"selected":len(selected),"target":TARGET,
        "status_counts":dict(statuses),"year_counts":dict(years),
        "baseline_band":[MIN_BASELINE,MAX_BASELINE],
        "trials":manifest["expected_trials"],
        "source_screen_only_no_gate":True,
        "global_blind_claim":False},sort_keys=True),flush=True)

def cases():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and MIN_READY<=len(m["cases"])<=TARGET,
         "source manifest changed")
    cc=m["cases"]
    need(m["expected_trials"]==len(cc)*REPS*len(MODES),"expected trial count drift")
    need(len({x["gbd"] for x in cc})==len(cc) and
         len({x["sha256"] for x in cc})==len(cc),"duplicated original")
    for c in cc:
        src=ROOT/c["filename"]
        need(src.exists() and sha(src.read_bytes())==c["sha256"] and
             src.stat().st_size==c["bytes"],"frozen original SHA wrong")
        need(c["reference_screen_status"] in ("SAT","UNSAT"),"unverified original")
    return cc

# Reuse proven MRE11-EASY12 runner with a new, separately-frozen official source
# cohort and distinct paired seeds. The original program/selector are untouched.
base.PROTO=PROTO
base.ROOT=ROOT
base.CAP=CAP
base.TARGET=TARGET
base.cases=cases

def seed(c,rep):
    need(rep in range(REPS),"repetition out of range")
    return int(sha((PROTO+"|SEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)
base.seed=seed

def diagnostic(binary):
    cc=cases()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="mre11-prosp-gate-") as td:
        target=pathlib.Path(td)/"rewrite.cnf"
        report=[]
        for c in cc:
            x={"gbd":c["gbd"],"sha256":c["sha256"],"year":c["year"],"modes":{}}
            for mode in MODES:
                g=pinned.subprocess_gate(ROOT/c["filename"],mode,target,binary)
                x["modes"][mode]=g
            report.append(x)
            print("MRE11_PROSP_GATE",json.dumps(x,sort_keys=True),flush=True)
    save(ROOT/"gate_diagnostics.json",report)
    print("MRE11_PROSP_GATE_AUDIT_PASS",len(cc),flush=True)

def shard(idx,binary):
    need(idx in range(SHARDS),"shard index invalid")
    cc=cases()
    todo=[c for i,c in enumerate(cc) if i%SHARDS==idx]
    need(len(todo)>=2,"empty or undersized shard")
    rows=[]
    for c in todo:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(sha((PROTO+c["sha256"]+str(rep)).encode())).shuffle(modes)
            for mode in modes:
                row=base.trial(c,rep,mode,binary)
                rows.append(row)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("MRE11_PROSP_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(todo)*len(MODES)*REPS,"shard missing trials")
    print("MRE11_PROSP_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cc=cases()
    rows=[]
    for s in range(SHARDS):
        path=ROOT/("shard-%d.json"%s)
        need(path.exists(),"absent shard "+str(s))
        rows+=json.loads(path.read_text())
    need(len(rows)==len(cc)*len(MODES)*REPS,"incomplete paired results")
    seen={}
    cmap={c["sha256"]:c for c in cc}
    for r in rows:
        c=cmap.get(r["original_sha256"])
        need(c is not None and r["gbd"]==c["gbd"] and r["protocol"]==PROTO,
             "alien original in benchmark")
        need(r["rep"] in range(REPS) and r["mode"] in MODES and
             r["seed"]==seed(c,r["rep"]),"unpaired original seed")
        key=(c["sha256"],r["rep"],r["mode"])
        need(key not in seen,"duplicated trial")
        seen[key]=r
        if r["verdict"]=="SAT":
            need(r["SAT_original_witness_verified"] and
                 c["reference_screen_status"]=="SAT","bad SAT result")
        if r["verdict"]=="UNSAT":
            need(r["UNSAT_prior_CaDiCaL_crosschecked_no_LRAT"] and
                 c["reference_screen_status"]=="UNSAT","bad UNSAT concordance")
        need(r["verdict"] in ("SAT","UNSAT","TIMEOUT"),"unsupported solver result")
    groups=collections.defaultdict(set)
    for original,rep,mode in seen:groups[(original,rep)].add(mode)
    need(len(groups)==len(cc)*REPS and all(x==set(MODES) for x in groups.values()),
         "incomplete source-SHA-seed pairing")
    score={}
    for mode in MODES:
        xs=[r for r in rows if r["mode"]==mode]
        score[mode]={"count":len(xs),
           "solved":sum(r["verdict"] in ("SAT","UNSAT") for r in xs),
           "SAT":sum(r["verdict"]=="SAT" for r in xs),
           "UNSAT_no_LRAT":sum(r["verdict"]=="UNSAT" for r in xs),
           "timeouts":sum(r["verdict"]=="TIMEOUT" for r in xs),
           "PAR2_total_s":round(sum(r["par2_s"] for r in xs),6),
           "certified_gate_applied":sum(bool((r["gate"] or {}).get("applied")) for r in xs)}
    baseline=score["cpp_native"]["PAR2_total_s"]
    for x in score.values():x["PAR2_speedup_vs_native_x"]=round(baseline/x["PAR2_total_s"],6)
    per_case=[]
    for c in cc:
        subset=[r for r in rows if r["original_sha256"]==c["sha256"]]
        per_case.append({"gbd":c["gbd"],"year":c["year"],"source_SHA":c["sha256"],
            "reference_screen_s":c["reference_screen_s"],
            "original_status":c["reference_screen_status"],
            "arms":{mode:{"PAR2_s":round(sum(r["par2_s"] for r in subset if r["mode"]==mode),6),
                          "solved":sum(r["verdict"] in ("SAT","UNSAT") for r in subset if r["mode"]==mode)}
                          for mode in MODES}})
    report={"protocol":PROTO,"source_selection":"new official 2021-23 source IDs, original CMS reference screen only",
         "source_disjoint_to_declared_prior_registry":True,
         "not_guaranteed_globally_blind":True,"baseline_conditioned":True,
         "no_selector_training_on_new_sources":True,
         "native_CPP_exact_frozen_binary_from_MRE11":True,
         "source_count":len(cc),"seed_count":REPS,"cap_s":CAP,
         "real_end_to_end":True,"total_trials":len(rows),
         "SAT_model_original_verified":True,
         "UNSAT_cross_solver_without_independent_LRAT":True,
         "no_auto_promotion":True,"scores":score,"per_source":per_case}
    save(ROOT/"report.json",report)
    print("MRE11_PROSP_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
         sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","diagnostic","shard","audit"))
    p.add_argument("--native",default="mre11/bin/native")
    p.add_argument("--standalone",default="mre11/bin/standalone")
    p.add_argument("--cadical",default="/usr/bin/cadical")
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="freeze":freeze(a.native,a.cadical)
    elif a.action=="verify":
        print("MRE11_PROSP_VERIFY_PASS",len(cases()),flush=True)
    elif a.action=="diagnostic":diagnostic(a.standalone)
    elif a.action=="shard":shard(a.shard,a.native)
    else:audit()
