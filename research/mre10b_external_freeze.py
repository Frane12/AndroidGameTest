#!/usr/bin/env python3
"""MRE10b: prospective external-solver-selected NEW official SAT2023-25 originals.

Select exactly 4 per year, independently of DRNAS/MRE10/CMS results.
Candidates are SHA-salted ranks from the official Main Track GBD indices
with independently published minisat1m=yes label. Only CaDiCaL reference
runtime/status, file size, original SHA, per-year quotas and previous
tracked exclusion registries can affect selection.

NOT a globally exhaustive source novelty claim. No source is retained or
excluded after MRE10b has solved or timed out on it.
"""
from __future__ import annotations
import argparse,hashlib,json,pathlib,re,subprocess,sys,time,urllib.parse,urllib.request
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre6b_blind_freeze as prior
import r164_pure_exact_gf2 as exact

PROTO="DRNAS-MRE10B-12FRESH2023TO2025-EXTERNAL-CADICAL-15S-3SEED-4ARM"
SALT="DRNAS-MRE10B-20261108-PROACTIVE-ORIGINAL-GBD-2023-2025-SHA"
ROOT=pathlib.Path("mre10b_sources")
OLD=pathlib.Path("mre7_easy")
YEARS=("2023","2024","2025")
PER_YEAR=4
MAX_SCAN_PER_YEAR=90
MIN_REFERENCE_S=.07
MAX_REFERENCE_S=10.0
MAX_VARS=50000
MAX_CLAUSES=85000
MAX_RAW=5*1024**2
MAX_DIMACS=9*1024**2
BASE="https://benchmark-database.de/getinstances?context=cnf&query="

def need(b,msg):
    if not b:raise RuntimeError("MRE10B_FREEZE_FAIL_CLOSED "+str(msg))
def sha(x):return hashlib.sha256(x).hexdigest()
def get(url,maxbytes,seconds=30):
    q=urllib.request.Request(url,headers={"User-Agent":"DRNAS-MRE10B-external-reference-freeze/1.0"})
    with urllib.request.urlopen(q,timeout=seconds) as u:
        data=u.read(maxbytes+1)
    need(len(data)<=maxbytes,"source exceeds frozen compressed size cap")
    return data

def list_year(year):
    all_blob=get(BASE+urllib.parse.quote("track=main_"+year,safe=""),150000)
    mini_blob=get(BASE+urllib.parse.quote("track=main_"+year+" and minisat1m=yes",safe=""),150000)
    all_ids=[x.strip().split("/")[-1] for x in all_blob.decode().splitlines() if x.strip()]
    minis=[x.strip().split("/")[-1] for x in mini_blob.decode().splitlines() if x.strip()]
    need(len(all_ids)==400 and len(set(all_ids))==400 and
         set(minis)<=set(all_ids) and len(minis)>=PER_YEAR,
         "official 400 GBD index/minisat metadata missing")
    need(all(re.fullmatch(r"[0-9a-f]{32}",x) for x in all_ids),
         "unexpected official GBD identifier")
    return sorted(minis,key=lambda g:sha((SALT+"|"+year+"|"+g).encode())),dict(
        year=year,all_count=len(all_ids),minisat1m_yes_count=len(minis),
        official_index_sha=sha(all_blob),minisat1m_index_sha=sha(mini_blob))

def reference_status(path):
    start=time.perf_counter()
    try:
        p=subprocess.run(["cadical",str(path.resolve())],
           capture_output=True,text=True,errors="replace",
           timeout=MAX_REFERENCE_S+1.0,check=False)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",seconds=round(time.perf_counter()-start,6))
    seconds=time.perf_counter()-start
    out=p.stdout
    if p.returncode==20 and re.search(r"^s UNSATISFIABLE\s*$",out,re.M):
        status="UNSAT"
    elif p.returncode==10 and re.search(r"^s SATISFIABLE\s*$",out,re.M):
        status="SAT"
    else:
        status="UNKNOWN_OR_REFERENCE_ERROR"
    return dict(status=status,seconds=round(seconds,6),returncode=p.returncode)

def previous_exclusion():
    old=json.loads((OLD/"manifest.json").read_text())
    need(len(old["selected_cases"])>=16,"missing MRE10 prior 16 development sources")
    ids={c["gbd"] for c in old["selected_cases"]}
    digests={c["sha256"] for c in old["selected_cases"]}
    registry=pathlib.Path("research/mre6b_official_prior_gbd.txt")
    need(registry.exists(),"missing historical original source registry")
    ids.update(x.strip() for x in registry.read_text().splitlines()
               if re.fullmatch(r"[0-9a-f]{32}",x.strip()))
    return ids,digests,sha((OLD/"manifest.json").read_bytes())

def freeze():
    ROOT.mkdir(exist_ok=True)
    ex,prior_sha,old_manifest_sha=previous_exclusion()
    cases=[];attempts=[];indices=[]
    for year in YEARS:
        pool,meta=list_year(year)
        indices.append(meta)
        count=0
        for rank,g in enumerate(pool[:MAX_SCAN_PER_YEAR]):
            if count>=PER_YEAR:break
            if g in ex:continue
            filename=g+".cnf"
            target=ROOT/filename
            row=dict(year=year,gbd=g,rank=rank)
            try:
                compressed=get("https://benchmark-database.de/file/"+g,MAX_RAW,seconds=24)
                data,compression=prior.r32p.decode(compressed)
                need(len(data)<=MAX_DIMACS,"uncompressed source too big")
                n,m=prior.r32p.parse_dimacs_metadata(data)
                need(0<n<=MAX_VARS and 0<m<=MAX_CLAUSES,
                     "original formula outside frozen size geometry")
                digest=sha(data)
                need(digest not in prior_sha and
                     digest not in {z["sha256"] for z in cases},
                     "duplicate or previously benchmarked original source SHA")
                target.write_bytes(data)
                reference=reference_status(target)
                row.update(sha256=digest,clauses=m,vars=n,reference=reference,
                           bytes=len(data),compression=compression)
                need(reference["status"] in ("SAT","UNSAT"),
                     "CaDiCaL failed to finish in reference cap")
                need(MIN_REFERENCE_S<=reference["seconds"]<=MAX_REFERENCE_S,
                     "CaDiCaL time outside source eligibility window")
                cases.append(dict(filename=filename,gbd=g,year=year,vars=n,
                     clauses=m,bytes=len(data),sha256=digest,
                     reference_screen_status=reference["status"],
                     reference_screen_s=reference["seconds"],
                     source_class="NEW_EXTERNAL_CADICAL_SELECTED_NOT_DRNAS",
                     historical_exclusion_not_exhaustive=True,
                     compression=compression))
                count+=1;ex.add(g)
                row["reason"]="FROZEN"
            except Exception as exc:
                row["reason"]="REJECT_EXTERNAL_REFERENCE_OR_SIZE"
                row["detail"]=(type(exc).__name__+": "+str(exc))[:140]
                target.unlink(missing_ok=True)
            attempts.append(row)
            print("MRE10B_EXTERNAL_SCREEN",json.dumps(row,sort_keys=True),flush=True)
        need(count==PER_YEAR,"reference-only quota insufficient for "+year+
             ": accepted "+str(count)+", eligible ranked "+str(len(pool)))
    need(len(cases)==12 and len({c["sha256"] for c in cases})==12,"12 unique originals")
    manifest=dict(protocol=PROTO,freeze_salt=SALT,cases=cases,
        years=YEARS,per_year=PER_YEAR,source_selection_before_any_DRNAS_run=True,
        baseline_CMS_not_used_for_selection=True,
        external_CaDiCaL_reference_window_s=[MIN_REFERENCE_S,MAX_REFERENCE_S],
        comparison_DEV_not_full_global_blind=True,
        historical_exclusion_registry_not_complete=True,
        reference_cross_solver_unsat_no_independent_LRAT=True,
        old_16_manifest_sha256=old_manifest_sha,
        indexes=indices,scan_log=attempts)
    (ROOT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    (ROOT/"source.sha256").write_text("".join(c["sha256"]+"  "+c["filename"]+"\n" for c in cases))
    verify()
    print("MRE10B_FROZEN_PASS",len(cases),flush=True)

def verify():
    manifest=json.loads((ROOT/"manifest.json").read_text())
    need(manifest["protocol"]==PROTO and len(manifest["cases"])==12,"manifest changed")
    need(len({c["sha256"] for c in manifest["cases"]})==12,"duplicate source")
    for c in manifest["cases"]:
        p=ROOT/c["filename"]
        need(p.exists() and sha(p.read_bytes())==c["sha256"] and
             p.stat().st_size==c["bytes"],"SHA/source drift")
    need(all(sum(c["year"]==yr for c in manifest["cases"])==4 for yr in YEARS),
         "year-stratification drift")
    print("MRE10B_SOURCE_SHA_PASS",len(manifest["cases"]),flush=True)
    return manifest["cases"]

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("freeze","verify","selftest"))
    v=a.parse_args()
    if v.action=="selftest":
        need(PER_YEAR==4 and len(YEARS)==3 and MAX_REFERENCE_S==10.0 and
             MAX_CLAUSES==85000,"source freeze contract drift")
        print("MRE10B_SELFTEST_PASS",PROTO)
    elif v.action=="freeze":freeze()
    else:verify()
