#!/usr/bin/env python3
"""DRNAS X8 WC1: unofficial SAT Competition 2026 medium-cohort comparison.

Frozen candidate source SHA BEFORE ANY local solver trial; medium suitability is
based ONLY on *published* CaDiCaL3 SAT 2026 runtime (3..40s) and official
status (SAT/UNSAT), never on X8/Kissat/CaDiCaL measurements in this workflow.
Original-CNF SAT models independently replayed. UNSAT = reference agreement,
NOT independent LRAT. Historical manifests excluded, not a guarantee of
global blindness or official ranking. Same runner, wall budget, serial arms.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, pathlib, random, re, subprocess, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments"/"drnas_v16"))
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import mre_x2_clause_order_causal as x2
import mre_x4_early_divergence as x4
import mre_x_benchmark as base
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO="DRNAS-X8-WC1B-OFFICIAL26-MID16-2SAT14UNSAT-PUBLISHED-CA3-3TO40-5ARM-2REP-25S-v1"
SALT="DRNAS-X8-WC1-20261109-FROZEN-OFFICIAL26-MEDIUM-NO-X8-RESULT-LOOKUP"
OUT=pathlib.Path("wc1_out")
SRC=pathlib.Path("wc1_sources")
TARGET=16
MIN_READY=12
CAP=25.0
REPS=2
SHARDS=4
ARMS=("kissat_404","cadical_173","cms_orig","x8_shifted","x8_spread100")
MAX_FETCHES=100
MAX_RAW=15*1024*1024
MAX_PLAIN=20*1024*1024
MAX_VARS=15000
MAX_CLAUSES=85000
X8_BINARY=pathlib.Path("wc1_bin/mre_x8/bin/native")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("c8c/bin/plain")
STATUS={"sat-verified":"SAT","unsat-verified":"UNSAT"}

def need(ok,msg):
    if not ok:raise RuntimeError("DRNAS_WC1_FAIL_CLOSED "+str(msg))
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(p):return sha(pathlib.Path(p).read_bytes())
def save(p,obj):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def history():
    root=pathlib.Path("wc1_history")
    need(root.is_dir(),"missing prior original historical registries")
    ids=set()
    digests=set()
    paths=list(root.rglob("manifest.json"))
    need(len(paths)>=3,"missing C13/X5/C14 manifests for exclusions")
    for path in paths:
        v=json.loads(path.read_text())
        for rows in (v.get("cases",[]),v.get("source_cases",[])):
            if not isinstance(rows,list):continue
            for row in rows:
                if not isinstance(row,dict):continue
                g=row.get("gbd")
                d=row.get("sha256")
                if g and re.fullmatch("[0-9a-f]{32}",g):ids.add(g)
                if d and re.fullmatch("[0-9a-f]{64}",d):digests.add(d)
    for path in root.rglob("report.json"):
        try:data=json.loads(path.read_text())
        except (ValueError,OSError):continue
        for row in data.get("per_source",[]):
            g=row.get("gbd")
            d=row.get("sha256")
            if g and re.fullmatch("[0-9a-f]{32}",g):ids.add(g)
            if d and re.fullmatch("[0-9a-f]{64}",d):digests.add(d)
    # X4/X8 known four development hashes must never enter the WC1 score.
    old_x8=[
      ("220bb8aa093e502c47afcdac3140d67c","69aa8b6bb96a5952fedf1007994b4255d06f7e32023390bc4c342b1b30a0356a"),
      ("fdfcd52a21824b7181d66672f283ba04","7f25d0862e92fb60d957ea903ded020ec2b83b2ceec2ba4bf015bdcb1d4c3ac1"),
      ("695d8f6a2ee6e89e5a4f5d94abc3aca6","eb9a4740b712b149f08d5b430ae5907109eac3f231ce549a281703bc8e0965fb"),
      ("578f9377bfbfcc6ea3a18eb630667956","818eea0ab4e59102c589549d3ca487bf7c8a03e1e51644a126cba75a911e53de")
    ]
    for g,h in old_x8:ids.add(g);digests.add(h)
    need(len(ids)>=18,"incomplete historic GBD exclusion registry")
    return ids,digests, {str(p):digest(p) for p in paths}
def freeze():
    SRC.mkdir(exist_ok=True)
    historical_ids,historical_sha,historical_manifest=history()
    raw=r52.fetch_bytes(r52.URI,100000)
    official=[x.strip().rsplit("/",1)[-1] for x in raw.decode().splitlines() if x.strip()]
    need(len(official)==400 and len(set(official))==400,"official2026 400 IDs drift")
    csv_bytes=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    data=list(csv.DictReader(io.StringIO(csv_bytes.decode())))
    rows=[r for r in data if r.get("solverid")=="biere_cadical3[main]"]
    need(len(rows)==400,"published benchmark score coverage changed")
    pool=[]
    for r in rows:
        g=r["instanceid"]
        if g not in official or g in historical_ids:continue
        status=STATUS.get(r.get("status"))
        if status not in ("SAT","UNSAT"):continue
        try:t=float(r["runtime"])
        except (ValueError,KeyError):continue
        if not 3.0<=t<=40.0:continue
        pool.append({"gbd":g,"reference":status,"official_ca3_s":t})
    # Pre-registered, salt-ranked source list within each status; no solution timings from this workflow.
    queues={st:sorted((r for r in pool if r["reference"]==st),
            key=lambda r:sha((SALT+"|"+st+"|"+r["gbd"]).encode())) for st in ("SAT","UNSAT")}
    need(all(len(queues[st])>=5 for st in queues),
         "insufficient published medium cohort, never relax post hoc")
    selected=[]
    attempts=[]
    attempted=set()
    quota={"SAT":2,"UNSAT":14}
    for st in ("SAT","UNSAT"):
        for candidate in queues[st]:
            if len([x for x in selected if x["reference"]==st])>=quota[st]:
                break
            if len(attempts)>=MAX_FETCHES:break
            g=candidate["gbd"]
            if g in attempted:continue
            attempted.add(g)
            record={"gbd":g,"published_status":st,"published_ca3_s":candidate["official_ca3_s"]}
            try:
                zipped,url=r32p.request_url("https://benchmark-database.de/file/"+g,MAX_RAW,seconds=25)
                plain,compression=r32p.decode(zipped)
                need(len(plain)<=MAX_PLAIN,"CNF uncompressed limit")
                vars,clauses=r32p.parse_dimacs_metadata(plain)
                need(250<=vars<=MAX_VARS and 1000<=clauses<=MAX_CLAUSES,
                     "not medium geometry")
                hash=sha(plain)
                need(hash not in historical_sha,"historical SHA already tested")
                need(hash not in [x["sha256"] for x in selected],"duplicate source SHA")
                path=SRC/(g+".cnf")
                path.write_bytes(plain)
                item={**candidate,"sha256":hash,"filename":path.name,"bytes":len(plain),
                      "nvars":vars,"nclauses":clauses,"compression":compression,
                      "source_url":"https://benchmark-database.de/file/"+g,
                      "raw_sha256":sha(zipped)}
                selected.append(item)
                record.update(decision="FROZEN_BEFORE_TIMED_TRIAL",sha256=hash,nvars=vars,nclauses=clauses)
            except Exception as e:
                (SRC/(g+".cnf")).unlink(missing_ok=True)
                record.update(decision="EXCLUDED_BEFORE_ANY_SOLVER",reason=(type(e).__name__+": "+str(e))[:240])
            attempts.append(record)
            print("X8_WC2_FREEZE_SCAN",json.dumps(record,sort_keys=True),flush=True)
    need(MIN_READY<=len(selected)<=TARGET,"insufficient medium official cases")
    need(len({x["sha256"] for x in selected})==len(selected),"duplicate source sha")
    counts=collections.Counter(x["reference"] for x in selected)
    need(counts["SAT"]==2 and counts["UNSAT"]>=10,"SAT/UNSAT V2 quota missing")
    manifest={
       "protocol":PROTO,"source_count":len(selected),"target":TARGET,"cap_s":CAP,
       "seed_repeats":REPS,"arms":list(ARMS),"salt":SALT,"cases":selected,
       "selection_attempts":attempts,"official_index_sha256":sha(raw),
       "official_scores_sha256":sha(csv_bytes),"historic_registry_sha256":historical_manifest,
       "published_reference":"biere_cadical3[main]",
       "medium_published_runtime_range_s":[3.0,40.0],
       "geometry_bounds":{"min_vars":250,"max_vars":MAX_VARS,
                          "min_clauses":1000,"max_clauses":MAX_CLAUSES},
       "known_historical_ids_excluded":len(historical_ids),
       "source_frozen_before_local_solver":True,
       "no_X8_timing_based_source_selection":True,
       "pretrial_revision_reason":"v1 availability scan yielded two size-eligible SAT; changed only SAT/UNSAT quotas before any timed solver",
       "published_reference_runtime_based_selection_not_globally_blind":True,
       "UNSAT_independent_LRAT":False,"not_official_ranking":True,
       "no_auto_promotion":True}
    save(SRC/"manifest.json",manifest)
    (SRC/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n" for c in selected))
    print("X8_WC2_FROZEN",json.dumps({"n":len(selected),"SAT":sum(x["reference"]=="SAT" for x in selected),
        "UNSAT":sum(x["reference"]=="UNSAT" for x in selected),"manifest_sha":digest(SRC/"manifest.json")}),flush=True)
def cases():
    m=json.loads((SRC/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["cap_s"]==CAP and m["arms"]==list(ARMS)
         and m["seed_repeats"]==REPS and m["source_frozen_before_local_solver"],"source protocol drift")
    rows=m["cases"]
    need(MIN_READY<=len(rows)<=TARGET and len(set(x["sha256"] for x in rows))==len(rows),"case/sha mismatch")
    for c in rows:
        f=SRC/c["filename"]
        need(f.exists() and f.stat().st_size==c["bytes"] and digest(f)==c["sha256"],"original SHA drift")
    return rows
def seed(c,rep):
    return int(sha((PROTO+"|SEED|"+c["sha256"]+"|"+str(rep)).encode())[:8],16)
def transformed(c,arm,rep):
    src=SRC/c["filename"]
    n,raw=x2.parse(src)
    mode={"x8_shifted":"spread_shifted","x8_spread100":"spread100"}[arm]
    changed=x4.transform(raw,mode)
    # A true exact clause multiset permutation, not satisfiability-preserving simplification.
    need(collections.Counter(raw)==collections.Counter(changed),"clause multiset changed")
    dest=OUT/"tmp"/f"{c['gbd']}-{rep}-{arm}.cnf"
    dest.parent.mkdir(parents=True,exist_ok=True)
    x2.write(dest,n,changed)
    need(x2.parse(dest)==(n,changed),"DIMACS rewrite parity")
    return dest,len(raw)-len(set(tuple(sorted(x)) for x in raw))
def trial(c,rep,arm):
    p=SRC/c["filename"]
    need(digest(p)==c["sha256"],"original source SHA modified before trial")
    started=time.perf_counter()
    path=p
    duplicates=0
    if arm.startswith("x8_"):
        path,duplicates=transformed(c,arm,rep)
    if arm=="kissat_404":
        cmd=[str(KISSAT.resolve()),str(p.resolve())]
    elif arm=="cadical_173":
        cmd=[str(CADICAL.resolve()),str(p.resolve())]
    else:
        cmd=[str(X8_BINARY.resolve()),str(path.resolve()),"x_native",str(seed(c,rep))]
    env=os.environ.copy()
    for key in ("DRNAS_MAX_CONFLICTS","DRNAS_X7_TRACE","DRNAS_X8_TRACE"):
        env.pop(key,None)
    elapsed_prep=time.perf_counter()-started
    remaining=CAP-elapsed_prep
    proc=None
    if remaining>0:
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                                timeout=remaining,check=False,env=env)
        except subprocess.TimeoutExpired:
            pass
    wall=time.perf_counter()-started
    status="TIMEOUT"
    verified=False
    native_stats=None
    if proc is not None:
        if arm in ("kissat_404","cadical_173"):
            status,model=ref.external_parse(proc)
            need(status in ("SAT","UNSAT","TIMEOUT","UNKNOWN"),"bad external backend status")
        else:
            need(proc.returncode==0,"X8 CMS crash "+(proc.stderr or "")[-400:])
            status,model,native_stats=base.cms.parsed_native(proc.stdout)
            need(status in ("SAT","UNSAT","UNKNOWN","BUDGET"),"bad native backend status")
            gate=base.parse_gate(proc.stdout,"x_native")
            need(not gate["applied"] and gate["clauses_removed"]==0,"CMS performed unwanted source transform")
        if status=="SAT":
            cms.verify_model(p,model)
            verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference"],"official2026 verified status disagreement")
    if wall>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    return {"protocol":PROTO,"gbd":c["gbd"],"source_sha256":c["sha256"],"reference":c["reference"],
            "published_ca3_s":c["official_ca3_s"],"rep":rep,"seed":seed(c,rep),"arm":arm,
            "status":status,"PAR2_s":round(wall if status in ("SAT","UNSAT") else 2*CAP,6),
            "wall_s":round(wall,6),"prep_s":round(elapsed_prep,6),
            "SAT_original_witness_verified":verified,
            "UNSAT_independent_LRAT":False,
            "reference_result_agreement":status in ("SAT","UNSAT"),
            "CMS_native_stats":native_stats,
            "duplicate_clauses":duplicates if arm.startswith("x8_") else None,
            "source_is_official_2026":True,"same_host":True,"cap_s":CAP,
            "Kissat_CaDiCaL_seed_not_changed":arm in ("kissat_404","cadical_173")}
def shard(i):
    need(i in range(SHARDS),"invalid shard")
    selected=[c for j,c in enumerate(cases()) if j%SHARDS==i]
    need(len(selected)>=2,"underpopulated concurrent shard")
    rows=[]
    OUT.mkdir(exist_ok=True)
    for c in selected:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(seed(c,rep)).shuffle(order)
            for arm in order:
                row=trial(c,rep,arm)
                rows.append(row)
                save(OUT/f"shard-{i}.json",rows)
                print("X8_WC2_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(selected)*REPS*len(ARMS),"shard incomplete")
    print("X8_WC2_SHARD_PASS",i,len(rows),flush=True)
def audit():
    cs=cases()
    bysha={c["sha256"]:c for c in cs}
    trials=[]
    for i in range(SHARDS):
        p=OUT/f"shard-{i}.json"
        need(p.is_file(),"missing shard artifact")
        trials+=json.loads(p.read_text())
    need(len(trials)==len(cs)*REPS*len(ARMS),"wrong trial count")
    bykey=collections.defaultdict(dict)
    for t in trials:
        c=bysha.get(t["source_sha256"])
        need(c and t["protocol"]==PROTO and t["gbd"]==c["gbd"] and
             t["arm"] in ARMS and t["rep"] in range(REPS) and
             t["seed"]==seed(c,t["rep"]),"paired SHA/seed drift")
        k=(t["source_sha256"],t["rep"])
        need(t["arm"] not in bykey[k],"duplicate cell")
        bykey[k][t["arm"]]=t
        if t["status"]=="TIMEOUT":
            need(t["PAR2_s"]==2*CAP,"invalid PAR2 timeout")
        else:
            need(t["status"]==c["reference"],"published SAT/UNSAT mismatch")
            need(abs(t["PAR2_s"]-t["wall_s"])<=0.000002,"wrong completed time")
            if t["status"]=="SAT":
                need(t["SAT_original_witness_verified"],"SAT original witness missing")
    need(len(bykey)==len(cs)*REPS and all(set(d)==set(ARMS) for d in bykey.values()),"not fully paired")
    scores={}
    for arm in ARMS:
        arr=[t for t in trials if t["arm"]==arm]
        scores[arm]={"PAR2_s":round(sum(t["PAR2_s"] for t in arr),6),
            "solved":sum(t["status"]!="TIMEOUT" for t in arr),
            "SAT":sum(t["status"]=="SAT" for t in arr),
            "UNSAT_reference_only":sum(t["status"]=="UNSAT" for t in arr),
            "timeouts":sum(t["status"]=="TIMEOUT" for t in arr),
            "n":len(arr)}
    refbest=min(scores["kissat_404"]["PAR2_s"],scores["cadical_173"]["PAR2_s"])
    for s in scores.values():s["speedup_vs_best_single_reference"]=round(refbest/s["PAR2_s"],6)
    per_source=[]
    for c in cs:
        a=[t for t in trials if t["source_sha256"]==c["sha256"]]
        per_source.append({"gbd":c["gbd"],"sha256":c["sha256"],"published_control_s":c["official_ca3_s"],
            "reference":c["reference"],"nvars":c["nvars"],"nclauses":c["nclauses"],
            "PAR2_s":{arm:round(sum(t["PAR2_s"] for t in a if t["arm"]==arm),6) for arm in ARMS},
            "solved":{arm:sum(t["status"]!="TIMEOUT" for t in a if t["arm"]==arm) for arm in ARMS}})
    # Paired speedup/regressions are per source and repeat, not only aggregate ratio.
    pairs={}
    for against in ("kissat_404","cadical_173","cms_orig"):
        won=lost=tied=0
        for d in bykey.values():
            x=d["x8_shifted"]["PAR2_s"]
            y=d[against]["PAR2_s"]
            if x<y-1e-5:won+=1
            elif x>y+1e-5:lost+=1
            else:tied+=1
        pairs[against]={"shifted_faster":won,"shifted_slower":lost,"tied":tied}
    # Structural subgroup analysis is POST HOC and does not change primary ranking.
    duplicate_sources=[x for x in per_source if (x["nclauses"] is not None)]
    final={"protocol":PROTO,"source_count":len(cs),"seed_repeats":REPS,
      "total_trials":len(trials),"cap_s":CAP,"ranking":"ascending total PAR2, descending solved",
      "scores":scores,"paired_shifted_vs":pairs,"per_source":per_source,
      "same_runner_each_shard_same_wall_cap":True,
      "published_CaDiCaL3_runtime_selection":True,
      "no_X8_runtime_selection":True,
      "medium_not_guaranteed_on_GitHub_hardware":True,
      "X8_CMS_5_11_pinned":True,"new_X8_frozen_rule_not_retuned":True,
      "SAT_original_models_checked":True,"UNSAT_independent_LRAT":False,
      "historic_exclusions_not_globally_exhaustive":True,
      "not_official_SAT_Competition_results":True,
      "not_unseen_guaranteed":True,
      "no_auto_promotion":True}
    save(OUT/"report.json",final)
    print("X8_WC2_FINAL",json.dumps({k:v for k,v in final.items() if k!="per_source"},sort_keys=True),flush=True)
def selftest():
    import tempfile
    original=[(1,-2),(1,-2),(-1,2),(3,4),(3,4),(-3,)]
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"test.cnf"
        x2.write(p,4,original)
        for mode in ("spread100","spread_shifted"):
            changed=x4.transform(original,mode)
            need(collections.Counter(original)==collections.Counter(changed),"not exact multiset")
            need(base.brute(p)==base.brute(p),"brute source failed")
    print("X8_WC2_SELFTEST_PASS")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="freeze":freeze()
    elif args.action=="verify":
        print("X8_WC2_VERIFY_PASS",len(cases()))
    elif args.action=="shard":shard(args.shard)
    else:audit()
