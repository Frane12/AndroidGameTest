#!/usr/bin/env python3
"""Prospective GBD SAT2021-23 originals: published MiniSat1m YES source IDs.
8 original SHAs selected by frozen salted GBD identity, year quotas and
resource limits BEFORE any candidate solver evaluation. Not globally blind.
"""
import argparse,collections,hashlib,json,pathlib,re
import mre7_extended_easy_freeze as oldpool
import mre7_reference_easy_freeze as getsrc
import mre6b_blind_freeze as prev
ROOT=pathlib.Path("mre11b_blind")
PROTO="DRNAS-MRE11B-MINISAT1M-SOURCELOCK-2021-23-8SHA-20261108-v1"
SALT="MRE11B-EIGHT-ORIGINAL-NOT-CMS-SELECTED-20261108"
YEARS=("2021","2022","2023")
TARGET=8
CAP=35
REPS=2
MODES=("cpp_native","cpp_rename","cpp_clean","cpp_joint","cpp_route","cpp_ref_6f","kissat","cadical")
LIMIT=12*1024*1024
def need(ok,msg):
    if not ok:raise RuntimeError("MRE11B_FREEZE_FAIL_CLOSED "+msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def previously_seen():
    m=json.loads(pathlib.Path("mre7_easy/manifest.json").read_text())
    need(m["protocol"]==oldpool.PROTO and len(m["selected_cases"])==16,
         "missing previous MRE7e 16 SHA registry")
    ids={c["gbd"] for c in m["selected_cases"]}
    ids.update(s.strip() for s in prev.PRIOR.read_text().splitlines()
               if re.fullmatch("[0-9a-f]{32}",s.strip()))
    return ids
def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    excluded=previously_seen()
    pool=[];indexes={}
    for yr in YEARS:
        allids,h1=oldpool.getids("track=main_"+yr)
        mini,h2=oldpool.getids("track=main_"+yr+" and minisat1m=yes")
        need(len(allids)==400 and set(mini)<=set(allids),"GBD published index drift")
        pool.extend((yr,g) for g in mini)
        indexes[yr]=dict(original_count=len(allids),minisat_eligible=len(mini),all_sha=h1,mini_sha=h2)
    more,_=prev.inspect_repo_ids({g for yr,g in pool})
    excluded.update(more)
    cand=sorted(set((yr,g) for yr,g in pool if g not in excluded),
                key=lambda z:sha((SALT+"|"+z[0]+"|"+z[1]).encode()))
    need(len(cand)>=TARGET,"not enough new published source IDs")
    source_limit=LIMIT
    getsrc.prior.r32p.CNF_LIMIT=source_limit
    years=collections.Counter()
    cases=[];trace=[]
    # Phase 0 fixes two viable source SHA per year before filling the last two
    # slots from the same SHA-ranked pool. All ordering is metadata-only.
    ordered=[(0,yr,g) for yr in YEARS for y,g in cand if y==yr]
    ordered +=[(1,yr,g) for yr,g in cand]
    attempted=set()
    for phase,yr,g in ordered:
        if len(cases)>=TARGET:break
        if (yr,g) in attempted:continue
        if phase==0 and years[yr]>=2:continue
        if phase==1 and any(years[y]<2 for y in YEARS):continue
        if years[yr]>=4:continue
        attempted.add((yr,g))
        dst=ROOT/(g+".cnf")
        try:
            compressed=getsrc.get("https://benchmark-database.de/file/"+g,LIMIT,seconds=25)
            raw,kind=getsrc.prior.r32p.decode(compressed)
            need(len(raw)<=LIMIT,"uncompressed DIMACS over fixed bound")
            n,m=getsrc.prior.r32p.parse_dimacs_metadata(raw)
            need(n<=12000 and m<=85000,"fixed source geometry exceeds MRE10")
            d=sha(raw)
            need(d not in {x["sha256"] for x in cases},"duplicate source SHA")
            dst.write_bytes(raw)
            item=dict(year=yr,gbd=g,sha256=d,filename=dst.name,bytes=len(raw),
                vars=n,clauses=m,compression=kind,official_status="UNKNOWN",
                MiniSat1m_external_metadata=True)
            cases.append(item);years[yr]+=1
            log=dict(year=yr,gbd=g,source_sha256=d,selection="FROZEN_UNSOLVED")
            print("MRE11B_SOURCE",json.dumps(log,sort_keys=True),flush=True)
        except Exception as e:
            dst.unlink(missing_ok=True)
            log=dict(year=yr,gbd=g,selection="EXCLUDED_BEFORE_SOLVE_SIZE_OR_FETCH",
                     why=(type(e).__name__+": "+str(e))[:120])
        trace.append(log)
    need(len(cases)==TARGET and min(years[yr] for yr in YEARS)>=2,
         "less than eight source-only SHA or year quota shortage")
    manifest=dict(protocol=PROTO,source_cases=cases,original_count=TARGET,
        index_snapshot=indexes,salt=SALT,source_exclusion_count=len(excluded),
        years=dict(years),original_SHA_frozen_before_any_solver=True,
        status_not_selection_criterion=True,
        selection="published minisat1m=yes plus SHA rank fixed source geometry and year quota",
        selected_no_mre_timing_or_structure=True,
        fixed_phase_year_quota_two_each_then_two_SHA_ranked=True,
        historical_register_not_globally_complete=True,
        cap_s=CAP,reps=REPS,arms=list(MODES),trace=trace,
        no_production_promotion=True)
    (ROOT/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    (ROOT/"source.sha256").write_text("".join(x["sha256"]+"  "+x["filename"]+"\n" for x in cases))
    print("MRE11B_FROZEN",json.dumps({k:v for k,v in manifest.items()
            if k not in ("trace","source_cases")},sort_keys=True),flush=True)
def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["original_count"]==TARGET and
         m["cap_s"]==CAP and m["reps"]==REPS and m["arms"]==list(MODES),
         "frozen source or protocol altered")
    for c in m["source_cases"]:
        raw=(ROOT/c["filename"]).read_bytes()
        need(len(raw)==c["bytes"] and sha(raw)==c["sha256"],"source SHA drift")
    print("MRE11B_SHA_VERIFY_PASS",len(m["source_cases"]),flush=True)
    return m
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("freeze","verify"))
    x=ap.parse_args()
    if x.action=="freeze":freeze()
    else:verify()
