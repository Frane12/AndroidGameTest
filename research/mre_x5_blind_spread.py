#!/usr/bin/env python3
"""DRNAS MRE X5: prospective SAT2026 SHA-disjoint holdout for frozen X4 spread_shifted.

Sources frozen using ONLY published official identities and SAT/UNSAT status
quotas, SHA ranking, and input size; NO duplicate count, runtime, trial runs,
or candidate hints. Historic registry is conservative but not exhaustive.
Frozen source SHA and all strategy parameters precede all timed trials.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, pathlib, re, random, subprocess, time, os, statistics
import mre6b_blind_freeze as previous
import mre_x_benchmark as xbase
import mre_x2_clause_order_causal as x2
import mre_x4_early_divergence as x4

OUT=pathlib.Path("mre_x5_blind")
PROTO="DRNAS-MRE-X5-SAT2026-PROSPECTIVE-SHIFTED-SPREAD-3ARMS-4SEED-18S-v1"
SALT="MRE-X5-LOCKED-BEFORE-2026-RESULTS-20261108-STRICT-EXCLUDE-MRE6B"
MODES=("original","spread100","spread_shifted")
TARGET=10
MIN_READY=3
MAX_FETCH=125
MAX_RAW=10*1024*1024
MAX_PLAIN=12*1024*1024
MAX_VARS=12000
MAX_CLAUSES=85000
REPS=4
SHARDS=4
CAP=18.0
STATUS={"sat-verified":"SAT","unsat-verified":"UNSAT"}
PREVIOUS_MANIFEST=pathlib.Path("x5_previous_mre6b/manifest.json")

def need(ok,why):
    if not ok:raise RuntimeError("MRE_X5_FAIL_CLOSED "+str(why))
def sha(b):return hashlib.sha256(b).hexdigest()
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def existing_exclusions(index):
    prior=previous.PRIOR
    need(prior.is_file(),"missing historical source registry")
    ids={s.strip().lower() for s in prior.read_text().splitlines()
         if re.fullmatch(r"[0-9a-f]{32}",s.strip().lower())}
    recorded,old_sha=previous.inspect_repo_ids(set(index))
    ids|=recorded
    # R82 pre-emptively excluded 220 candidates even though only a small
    # subset was actually fetched/evaluated. Load the immutable R82 FINAL
    # published manifest and exclude its ACTUAL attempted and frozen originals.
    # This unlocks previously untouched IDs without revisiting tested data.
    r82_path=pathlib.Path("x5_previous_r82/world/manifest.json")
    need(r82_path.is_file(),"R82 final attempted-source registry unavailable")
    r82=json.loads(r82_path.read_text())
    need(r82.get("protocol")=="DRNAS-R82-WIDE-OFFICIAL-2025-2026-NOSCREEN-20261104-v1",
         "R82 frozen historic manifest protocol changed")
    r82_attempts=[x for x in r82.get("source_selection_attempts",[])
                  if x.get("year")==2026]
    r82_cases=[x for x in r82.get("cases",[]) if x.get("year")==2026]
    need(len(r82_cases)>=4 and len(r82_attempts)>=len(r82_cases),
         "R82 original source history incomplete")
    for row in r82_attempts+r82_cases:
        ids.add(row["gbd"])
    old_sha.update(x["sha256"] for x in r82_cases)
    need(PREVIOUS_MANIFEST.is_file(),"previous MRE6b freeze manifest unavailable; no blind claim")
    prev=json.loads(PREVIOUS_MANIFEST.read_text())
    old=prev.get("cases") or prev.get("source_cases")
    need(old and len(old)>=4,"previous MRE6b source lock is incomplete")
    for x in old:
        ids.add(x["gbd"]);old_sha.add(x["sha256"])
    need(len(ids.intersection(index))>=len(r82_cases),"actual R82 official source exclusion failed")
    return ids,old_sha,prev

def freeze():
    OUT.mkdir(exist_ok=True)
    import sys
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"experiments"/"drnas_v16"))
    import r32p_real_satcomp26_benchmark as r32p
    import r52_prospective_2026_toprefs as r52
    raw_index=r52.fetch_bytes(r52.URI,100000)
    official=[x.strip().rsplit("/",1)[-1] for x in raw_index.decode().strip().splitlines()]
    need(len(official)==400 and len(set(official))==400,
         "unexpected 2026 official original index")
    csv_bytes=r52.fetch_bytes(r52.SCORES,24*1024*1024)
    official_status={r["instanceid"]:STATUS.get(r["status"]) for r in
       csv.DictReader(io.StringIO(csv_bytes.decode()))
       if r.get("solverid")=="biere_cadical3[main]"}
    need(len(official_status)==400,"missing published reference status for official 2026")
    exclusions,old_sha,previous_manifest=existing_exclusions(official)
    ranked=sorted((g for g in official if g not in exclusions),
       key=lambda g:sha((SALT+"|"+g).encode()))
    need(len(ranked)>=MIN_READY,"prior registry leaves too few official sources")
    r32p.CNF_LIMIT=MAX_PLAIN
    chosen=[];trace=[];counts=collections.Counter()
    for g in ranked[:MAX_FETCH]:
        if len(chosen)>=TARGET:break
        status=official_status.get(g)
        log=dict(gbd=g,published_status=status)
        if status not in ("SAT","UNSAT"):
            log["action"]="skip_status_not_published_verified"
            trace.append(log);continue
        if counts[status]>=TARGET//2:
            log["action"]="skip_published_status_quota"
            trace.append(log);continue
        path=OUT/(g+".cnf")
        try:
            compressed,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,MAX_RAW,seconds=25)
            plain,kind=r32p.decode(compressed)
            need(len(plain)<=MAX_PLAIN,"plain DIMACS above fixed size limit")
            n,m=r32p.parse_dimacs_metadata(plain)
            need(0<n<=MAX_VARS and 0<m<=MAX_CLAUSES,"source geometry size bound")
            d=sha(plain)
            need(d not in old_sha,"known historical original source digest")
            need(d not in {c["sha256"] for c in chosen},"duplicate original source SHA")
            path.write_bytes(plain)
            chosen.append(dict(gbd=g,filename=path.name,sha256=d,
                bytes=len(plain),variables=n,clauses=m,
                published_status=status,year=2026,
                source_url="https://benchmark-database.de/file/"+g,
                raw_sha256=sha(compressed),compression=kind))
            counts[status]+=1
            log.update(action="FROZEN_UNSOLVED",sha256=d,variables=n,clauses=m)
        except Exception as e:
            path.unlink(missing_ok=True)
            log.update(action="exclude_before_any_solver",
                       reason=(type(e).__name__+": "+str(e))[:150])
        trace.append(log)
        print("MRE_X5_SOURCE_SCAN",json.dumps(log,sort_keys=True),flush=True)
    need(len(chosen)>=MIN_READY,"not enough new official 2026 sources under fixed bounds")
    need(len({c["sha256"] for c in chosen})==len(chosen),"duplicate source hash")
    data=dict(protocol=PROTO,salt=SALT,original_source_count=len(chosen),
       target=TARGET,min_ready=MIN_READY,MAX_FETCH=MAX_FETCH,
       source_filter="salted official 2026 GBD ranked ID, published status 50/50, fixed size only",
       year=2026,official_index=r52.URI,index_sha256=sha(raw_index),
       official_reference_status_table=r52.SCORES,status_table_sha256=sha(csv_bytes),
       previously_excluded_ids=len(exclusions.intersection(official)),
       previous_MRE6b_manifest_sha256=sha(PREVIOUS_MANIFEST.read_bytes()),
       previous_R82_manifest_sha256=sha(pathlib.Path("x5_previous_r82/world/manifest.json").read_bytes()),
       history_registry_not_guaranteed_globally_exhaustive=True,
       not_X4_X3_X2_development_sources=True,
       no_source_selection_by_duplicate_features_or_timing=True,
       frozen_shift_rule="X4 same source-only offset=max(1,len(unique)//(2*(duplicates+1)))",
       modes=list(MODES),seed_repeats=REPS,cap_s=CAP,
       cases=chosen,statuses=dict(counts),selection_trace=trace,
       original_SHA_frozen_before_any_solver=True,
       SAT_model_checked_on_original=True,UNSAT_reference_only_no_LRAT=True,
       auto_promote=False)
    save(OUT/"manifest.json",data)
    (OUT/"source.sha256").write_text("".join(x["sha256"]+"  "+x["filename"]+"\n"
                                               for x in chosen))
    print("MRE_X5_FROZEN",json.dumps(dict(n=len(chosen),status=dict(counts),
        excluded=len(exclusions.intersection(official)),
        hash=sha((OUT/"manifest.json").read_bytes())),
        sort_keys=True),flush=True)

def cases():
    m=json.loads((OUT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["cap_s"]==CAP and
         m["modes"]==list(MODES) and m["seed_repeats"]==REPS,
         "wrong protocol or benchmark parameters")
    arr=m["cases"]
    need(MIN_READY<=len(arr)<=TARGET and
         len({c["sha256"] for c in arr})==len(arr),"source count/sha changed")
    for c in arr:
        p=OUT/c["filename"]
        need(p.is_file() and len(p.read_bytes())==c["bytes"] and
             sha(p.read_bytes())==c["sha256"],"source SHA differs from freeze")
    return arr

def seed(c,rep):
    need(rep in range(REPS),"invalid replicate")
    return int(sha((PROTO+"|PAIRSEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)

def path(c,mode):
    return OUT/(c["gbd"]+"."+mode+".cnf")

def selftest():
    tests=[(4,[(1,-2),(1,-2),(-1,2),(1,3),(1,3),(4,)]),
           (3,[(1,),(-1,),(-2,3),(-2,3)])]
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        for nv,original in tests:
            src=pathlib.Path(td)/"before.cnf"
            x2.write(src,nv,original)
            for mode in MODES:
                changed=([tuple(c) for c in original] if mode=="original"
                         else x4.transform(original,mode))
                need(collections.Counter(changed)==collections.Counter(original),
                     "not identical original clause multiset")
                dst=pathlib.Path(td)/"after.cnf"
                x2.write(dst,nv,changed)
                need(xbase.brute(src)==xbase.brute(dst),"SAT truth changed")
    print("MRE_X5_SELFTEST_PASS",flush=True)

def variants():
    source=cases()
    manifest=[]
    for c in source:
        nv,raw=x2.parse(OUT/c["filename"])
        modes={}
        for mode in MODES:
            changed=x4.transform(raw,mode)
            need(collections.Counter(raw)==collections.Counter(changed),
                 "source original CNF multiset changed")
            dst=path(c,mode)
            x2.write(dst,nv,changed)
            modes[mode]=sha(dst.read_bytes())
            need(x2.parse(dst)==(nv,changed),"emitted DIMACS differs")
        manifest.append(dict(gbd=c["gbd"],sha256=c["sha256"],
                             duplicate_count=len(x2.split_duplicates(raw)[1]),
                             modes=modes))
    save(OUT/"variants.json",manifest)
    print("MRE_X5_VARIANTS_PASS",len(source),flush=True)

def verify():
    source=cases()
    arr=json.loads((OUT/"variants.json").read_text())
    need(len(arr)==len(source),"missing generated mode")
    bysha={x["sha256"]:x for x in arr}
    for c in source:
        need(c["sha256"] in bysha,"source missing from variant table")
        nv,original=x2.parse(OUT/c["filename"])
        for m in MODES:
            p=path(c,m)
            need(p.exists() and sha(p.read_bytes())==bysha[c["sha256"]]["modes"][m],
                 "variant SHA mismatch")
            n,clauses=x2.parse(p)
            need(n==nv and collections.Counter(clauses)==collections.Counter(original),
                 "not exact raw clause multiset")
            need(clauses==x4.transform(original,m),"shift rule changed after freeze")
    print("MRE_X5_VERIFY_PASS",len(source),flush=True)

def run(c,rep,mode,binary):
    original=OUT/c["filename"];trans=path(c,mode)
    cmd=[str(pathlib.Path(binary).resolve()),str(trans.resolve()),
         "x_native",str(seed(c,rep))]
    env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
    start=time.perf_counter();p=None
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
          check=False,timeout=CAP,env=env)
    except subprocess.TimeoutExpired:pass
    elapsed=time.perf_counter()-start
    status="TIMEOUT";stat=None;witness=False
    if p is not None:
        need(p.returncode==0,"native crashed: "+p.stderr[-700:])
        gate=xbase.parse_gate(p.stdout,"x_native")
        need(not gate["applied"] and gate["clauses_removed"]==0,
             "native changed input beyond allowed clause order")
        status,model,stat=xbase.cms.parsed_native(p.stdout)
        need(status in ("SAT","UNSAT","UNKNOWN","BUDGET"),
             "invalid CMS terminal status")
        if status=="SAT":
            xbase.cms.verify_model(original,model)
            witness=True
        if status in ("SAT","UNSAT"):
            need(status==c["published_status"],"official SAT/UNSAT disagreement")
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],
      year=2026,rep=rep,seed=seed(c,rep),mode=mode,
      status=status,published_reference=c["published_status"],
      elapsed_s=round(elapsed,6),
      PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
      SAT_original_witness_verified=witness,UNSAT_independent_LRAT=False,
      native_stats=stat)

def shard(idx,binary):
    need(idx in range(SHARDS),"invalid shard")
    rows=[]
    cs=[c for i,c in enumerate(cases()) if i%SHARDS==idx]
    # Emit an explicit empty JSON artifact for an unused shard when the strict
    # historical exclusion leaves fewer sources than the fixed shard count.
    save(OUT/("shard-%d.json"%idx),rows)
    for c in cs:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(sha((PROTO+"|ORDER|"+c["sha256"]+"|"+str(rep)).encode())[:16],16)).shuffle(modes)
            for mode in modes:
                row=run(c,rep,mode,binary)
                rows.append(row)
                save(OUT/("shard-%d.json"%idx),rows)
                print("MRE_X5_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(MODES),"missing case/seed/arm")
    print("MRE_X5_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    cs=cases();bysha={c["sha256"]:c for c in cs}
    allrows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i)
        need(p.exists(),"missing shard file")
        allrows+=json.loads(p.read_text())
    need(len(allrows)==len(cs)*REPS*len(MODES),"incomplete blind results")
    seen=set()
    for r in allrows:
        c=bysha.get(r["sha256"])
        need(c is not None and r["gbd"]==c["gbd"] and r["protocol"]==PROTO and
             r["mode"] in MODES and r["rep"] in range(REPS) and
             r["seed"]==seed(c,r["rep"]),"unpaired original formula/seed/arm")
        key=(r["sha256"],r["rep"],r["mode"])
        need(key not in seen,"duplicate trial");seen.add(key)
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"illegal verdict")
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"] and
                 c["published_status"]=="SAT","SAT source model not verified")
        if r["status"]=="UNSAT":
            need(c["published_status"]=="UNSAT" and
                 not r["UNSAT_independent_LRAT"],"UNSAT reference not logged correctly")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==2*CAP,"bad PAR2 penalty")
    score={}
    for mode in MODES:
        rows=[r for r in allrows if r["mode"]==mode]
        score[mode]=dict(n=len(rows),solved=sum(r["status"]!="TIMEOUT" for r in rows),
          SAT=sum(r["status"]=="SAT" for r in rows),
          UNSAT_reference_no_independent_LRAT=sum(r["status"]=="UNSAT" for r in rows),
          timeouts=sum(r["status"]=="TIMEOUT" for r in rows),
          PAR2_s=round(sum(r["PAR2_s"] for r in rows),6))
    control=score["original"]["PAR2_s"]
    for v in score.values():v["speedup_vs_original"]=round(control/v["PAR2_s"],6)
    per_source=[]
    for c in cs:
        rows=[r for r in allrows if r["sha256"]==c["sha256"]]
        per_source.append(dict(gbd=c["gbd"],sha256=c["sha256"],
          published_status=c["published_status"],
          PAR2_s={mode:round(sum(r["PAR2_s"] for r in rows if r["mode"]==mode),6)
                  for mode in MODES},
          solved={mode:sum(r["status"]!="TIMEOUT" for r in rows if r["mode"]==mode)
                  for mode in MODES}))
    variants=json.loads((OUT/"variants.json").read_text())
    summary=dict(protocol=PROTO,n=len(allrows),source_count=len(cs),
      seed_count=REPS,cap_s=CAP,
      prospective_source_SHA_frozen_before_test=True,
      historical_exclusions_not_globally_exhaustive=True,
      exact_clause_multiset_checked=True,source_only_fixed_shift_no_tuning=True,
      SAT_original_witness_verified=True,UNSAT_published_reference_no_independent_LRAT=True,
      no_automatic_promotion=True,
      structural_grouping_post_hoc=True,score=score,per_source=per_source,
      source_structural_post_test=variants)
    save(OUT/"report.json",summary)
    print("MRE_X5_FINAL",json.dumps({k:v for k,v in summary.items()
       if k not in ("per_source","source_structural_post_test")},sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","variants","verify","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--native",default="mre_x3/bin/native")
    opts=parser.parse_args()
    if opts.action=="selftest":selftest()
    elif opts.action=="freeze":freeze()
    elif opts.action=="variants":variants()
    elif opts.action=="verify":verify()
    elif opts.action=="shard":shard(opts.shard,opts.native)
    else:audit()
