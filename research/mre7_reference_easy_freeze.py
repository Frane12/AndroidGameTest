#!/usr/bin/env python3
"""DRNAS MRE7: prospective, source-disjoint reference-selected easy originals.

SAT2024 and SAT2025 official Main Track originals. No source is selected by
MRE reductions or DRNAS timing. Reference-only CMS screens complexity 0.08-5s;
every rejected input and source SHA is audited. SAT witnesses independently
checked against the exact original. UNSAT requires CaDiCaL agreement; it is
marked CROSS-SOLVER only, NOT an independently checked LRAT proof.
"""
from __future__ import annotations
import argparse,collections,hashlib,io,json,os,pathlib,random,re,subprocess,sys,time,urllib.request
import mre6b_blind_freeze as prior
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE7-SAT24SAT25-REFERENCE-SELECTED-EASY-v1"
SALT="DRNAS-MRE7-EASY-SOURCE-PROSPECTIVE-20261108-LOCKED-v1"
ROOT=pathlib.Path("mre7_easy")
TARGET=24
MAX_TRIES=180
MAX_RAW=5*1024*1024
MAX_PLAIN=9*1024*1024
MAX_VARS=30000
MAX_CLAUSES=85000
MIN_REFERENCE_S=0.08
MAX_REFERENCE_S=5.0
YEAR_MAX={"2024":16,"2025":16}
SRC24="https://raw.githubusercontent.com/satcompetition/2024/main/downloads/meta.csv"
SRC25="https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri"

def need(b,msg):
    if not b:raise RuntimeError("MRE7_FREEZE_FAIL_CLOSED "+str(msg))
def sha(raw):return hashlib.sha256(raw).hexdigest()
def get(url,limit,seconds=45):
    q=urllib.request.Request(url,headers={"User-Agent":"DRNAS-MRE7-Original-SAT-Locked/1.0"})
    with urllib.request.urlopen(q,timeout=seconds) as resp:
        data=resp.read(limit+1)
    need(len(data)<=limit,"source larger than fixed metadata/download cap")
    return data
def locate_inputs():
    txt24=get(SRC24,120000).decode()
    ids24=[]
    for l in txt24.splitlines()[1:]:
        fields=l.split()
        if fields and re.fullmatch("[0-9a-f]{32}",fields[0]):ids24.append(fields[0])
    txt25=get(SRC25,120000).decode()
    ids25=[l.strip().split("/")[-1] for l in txt25.splitlines() if l.strip()]
    need(len(ids24)>=350 and len(ids25)==400,"official index source coverage changed")
    need(len(set(ids24))==len(ids24) and len(set(ids25))==len(ids25),"official GBD duplicates")
    allids=set(ids24)|set(ids25)
    historical=set(s.strip() for s in prior.PRIOR.read_text().splitlines()
                  if re.fullmatch("[0-9a-f]{32}",s.strip()))
    repo_ids,_=prior.inspect_repo_ids(allids)
    m=prior.ROOT/"manifest.json"
    need(m.exists(),"earlier MRE6b source freeze not mounted")
    historical.update(c["gbd"] for c in json.loads(m.read_text())["cases"])
    # R82 previous 2025 random source-pair selection can include its top 220.
    # Exclude that entire block, not only files successfully benchmarked.
    early2025=set(sorted(ids25,key=lambda g:sha(
        ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2025/"+g).encode()))[:220])
    exclude=historical|repo_ids|early2025
    a24=[("2024",g) for g in ids24 if g not in exclude]
    a25=[("2025",g) for g in ids25 if g not in exclude]
    a24.sort(key=lambda p:sha((SALT+"|"+p[0]+"|"+p[1]).encode()))
    a25.sort(key=lambda p:sha((SALT+"|"+p[0]+"|"+p[1]).encode()))
    merged=[]
    for j in range(max(len(a24),len(a25))):
        if j<len(a24):merged.append(a24[j])
        if j<len(a25):merged.append(a25[j])
    return merged,dict(index24_sha=sha(txt24.encode()),index25_sha=sha(txt25.encode()),
        count24=len(ids24),count25=len(ids25),prior_excluded24=len(set(ids24)&exclude),
        prior_excluded25=len(set(ids25)&exclude),eligible24=len(a24),eligible25=len(a25),
        existing_registry_not_proven_exhaustive=True)

def screen(candidate,binary,cadical):
    t0=time.perf_counter()
    env=os.environ.copy()
    env["DRNAS_TRACE_ENABLED"]="0"
    env["DRNAS_ORIG_COUNT"]="0"
    env["DRNAS_TAG_0"]=""
    env["DRNAS_TAG_1"]=""
    empty=ROOT/"empty.tsv"
    try:
        p=subprocess.run([str(pathlib.Path(binary).resolve()),
             str(candidate.resolve()),str(empty.resolve()),str(empty.resolve()),
             "cms_native","117"],capture_output=True,text=True,timeout=MAX_REFERENCE_S+0.5,env=env)
    except subprocess.TimeoutExpired:return {"status":"TIMEOUT","runtime_s":None}
    elapsed=time.perf_counter()-t0
    need(p.returncode==0,"CMS reference binary failure: "+p.stderr[-250:])
    result,model,stats=r195.parsed_native(p.stdout)
    if result=="SAT":r195.verify_model(candidate,model)
    if result=="UNSAT":
        try:
            q=subprocess.run([str(pathlib.Path(cadical).resolve()),str(candidate.resolve())],
                capture_output=True,text=True,timeout=MAX_REFERENCE_S+0.5)
        except subprocess.TimeoutExpired:return {"status":"UNSAT_CROSSCHECK_TIMEOUT","runtime_s":elapsed}
        need(q.returncode in (10,20),"CaDiCaL error "+q.stderr[-200:])
        if q.returncode!=20 or "UNSATISFIABLE" not in q.stdout:
            return {"status":"UNSAT_CROSSCHECK_FAILED","runtime_s":elapsed}
    return dict(status=result,runtime_s=round(elapsed,6),
        conflicts=stats["conflicts"],decisions=stats["decisions"],
        propagations=stats["propagations"],
        witness_checked=(result=="SAT"),
        unsat_cross_solver=(result=="UNSAT"),
        independent_unsat_lrat=False)

def freeze(binary="mre5/native",cadical="/usr/bin/cadical"):
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"empty.tsv").write_text("")
    pool,indices=locate_inputs()
    need(len(pool)>80,"insufficient original untouched official GBD pool")
    selected=[];trace=[];counts=collections.Counter()
    prior.r32p.CNF_LIMIT=MAX_PLAIN
    for pos,(year,gbd) in enumerate(pool[:MAX_TRIES]):
        if len(selected)>=TARGET:break
        row=dict(rank=pos,year=year,gbd=gbd)
        if counts[year]>=YEAR_MAX[year]:
            row["reason"]="fixed_per_year_quota"
            trace.append(row);continue
        target=ROOT/(gbd+".cnf")
        try:
            compressed= get("https://benchmark-database.de/file/"+gbd,MAX_RAW,seconds=18)
            plain,compression=prior.r32p.decode(compressed)
            need(len(plain)<=MAX_PLAIN,"plain size budget")
            vars_,clauses=prior.r32p.parse_dimacs_metadata(plain)
            need(vars_<=MAX_VARS and clauses<=MAX_CLAUSES,"CNF geometry budget")
            digest=sha(plain)
            target.write_bytes(plain)
            baseline=screen(target,binary,cadical)
            row.update(sha256=digest,vars=vars_,clauses=clauses,
                reference=baseline,bytes=len(plain),compression=compression)
            if baseline["status"] not in ("SAT","UNSAT"):
                row["reason"]="reference_not_solved_or_cross_checked"
            elif not(MIN_REFERENCE_S<=baseline["runtime_s"]<=MAX_REFERENCE_S):
                row["reason"]="reference_outside_precommitted_easy_band"
            else:
                row["reason"]="READY"
                selected.append(dict(year=year,gbd=gbd,filename=target.name,
                    sha256=digest,vars=vars_,clauses=clauses,bytes=len(plain),
                    reference_screen_s=baseline["runtime_s"],
                    reference_screen_status=baseline["status"],
                    witness_checked=baseline["witness_checked"],
                    unsat_cross_solver=baseline["unsat_cross_solver"],
                    independent_unsat_lrat=False,
                    source_url="https://benchmark-database.de/file/"+gbd))
                counts[year]+=1
        except Exception as e:
            row["reason"]="source_download_or_reference_error"
            row["detail"]=(type(e).__name__+": "+str(e))[:170]
        if row["reason"]!="READY":target.unlink(missing_ok=True)
        trace.append(row)
        print("MRE7_SCREEN",json.dumps(row,sort_keys=True),flush=True)
    manifest=dict(protocol=PROTO,indexes=indices,target=TARGET,selected=len(selected),
        attempts=len(trace),counts_by_year=dict(counts),reference_band_s=[MIN_REFERENCE_S,MAX_REFERENCE_S],
        source_selection_before_mre_gate=True,source_disjoint_declared_registry=True,
        source_selection_is_baseline_conditioned=True,not_global_random_holdout=True,
        official_status_2024_2025_not_retrieved=True,
        SAT_original_witness_verified=True,UNSAT_cross_solver_not_LRAT=True,
        methods_predeclared=True,selected_cases=selected,screen_trace=trace)
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    (ROOT/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in selected))
    print("MRE7_FREEZE_FINAL",json.dumps({k:v for k,v in manifest.items()
        if k not in ("screen_trace","selected_cases")},sort_keys=True),flush=True)
    need(len(selected)>=20,"fewer than 20 easy source-disjoint cases: audit pilot; never fabricate full sample")

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO,"manifest mismatch")
    for c in m["selected_cases"]:
        need(sha((ROOT/c["filename"]).read_bytes())==c["sha256"],
             "original source bytes changed")
    return m

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify"))
    p.add_argument("--binary",default="mre5/native")
    p.add_argument("--cadical",default="/usr/bin/cadical")
    a=p.parse_args()
    if a.action=="freeze":freeze(a.binary,a.cadical)
    else:print("MRE7_VERIFY_PASS",verify()["selected"],flush=True)
