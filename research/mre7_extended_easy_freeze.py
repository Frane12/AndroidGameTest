#!/usr/bin/env python3
"""MRE7E extend frozen six SAT24/SAT25 originals with SAT21-23 sources.

The first six are untouched bytes/SHAs from the failed (underpopulated)
20-source freeze. Additional originals are chosen ONLY from official
GBD source identifiers and independent `minisat1m=yes` metadata BEFORE any
MRE gate evaluation. CMS 0.08-5s screening is a declared sampling criterion.
Not globally blind: extension was motivated by a six-case earlier pilot.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,pathlib,random,re,urllib.parse,urllib.request
import mre7_reference_easy_freeze as f
import mre6b_blind_freeze as old

PROTO="DRNAS-MRE7E-OLDER2021-2023-EXTENDED-EASY-20261108-v1"
SALT="DRNAS-MRE7E-OLDER-MINISAT1M-SOURCE-ONLY-FROZEN-20261108"
BASE="https://benchmark-database.de/getinstances?context=cnf&query="
YEARS=("2021","2022","2023")
MAX_ATTEMPTS=240
TARGET=24
MIN_REQUIRED=20
MAX_PER_YEAR=12
ROOT=f.ROOT
# Preserve the original reference-only 0.08–5 second eligibility rule.
f.MIN_REFERENCE_S=0.08
f.MAX_REFERENCE_S=5.0
def need(v,msg):
    if not v:raise RuntimeError("MRE7E_FAIL_CLOSED "+str(msg))
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def getids(query):
    url=BASE+urllib.parse.quote(query,safe="")
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-MRE7E-Source-Pool/1.0"})
    with urllib.request.urlopen(req,timeout=55) as stream:
        raw=stream.read(400000)
    ids=[line.rsplit("/",1)[-1].strip() for line in raw.decode().splitlines() if line.strip()]
    need(all(re.fullmatch("[0-9a-f]{32}",x) for x in ids),"GBD source index not GBD hashes")
    need(len(ids)==len(set(ids)),"GBD repeated URI within one query")
    return ids,hashlib.sha256(raw).hexdigest()

def pool():
    allids=set()
    groups=[];snap={}
    for year in YEARS:
        ids_all,hash_all=getids("track=main_"+year)
        ids_easy,hash_easy=getids("track=main_"+year+" and minisat1m=yes")
        need(len(ids_all)==400 and set(ids_easy)<=set(ids_all),"GBD index drift")
        allids.update(ids_all)
        snap[year]=dict(original_count=400,mini_yes_count=len(ids_easy),
                       source_index_sha=hash_all,mini_yes_sha=hash_easy)
        groups +=[(year,g,0) for g in ids_easy]
        groups +=[(year,g,1) for g in ids_all if g not in set(ids_easy)]
    prior_ids=set(x.strip() for x in old.PRIOR.read_text().splitlines()
                   if re.fullmatch("[0-9a-f]{32}",x.strip()))
    repo,_=old.inspect_repo_ids(allids)
    existing=json.loads((ROOT/"manifest.json").read_text())
    need(existing["protocol"]=="DRNAS-MRE7-SAT24SAT25-REFERENCE-SELECTED-EASY-v1" and len(existing["selected_cases"])==6,
         "expected precisely earlier six-source SHA-locked pilot cohort")
    prior_ids.update(c["gbd"] for c in existing["selected_cases"])
    prior_ids.update(repo)
    ranked=sorted((x for x in groups if x[1] not in prior_ids),
        key=lambda x:(x[2],sha(SALT+"|"+x[0]+"|"+x[1])))
    seen=set(); result=[]
    for group in ranked:
        if group[1] in seen:continue
        seen.add(group[1]);result.append(group)
    return result,existing,dict(indexes=snap,prior_exclusion_count=len(allids&prior_ids),
        source_pool_count=len(result),minisat1m_priority=True)

def extend(binary,cadical):
    ROOT.mkdir(parents=True,exist_ok=True)
    current,oldmeta,metadata=pool()
    old_sha=f.sha((ROOT/"manifest.json").read_bytes())
    keep=list(oldmeta["selected_cases"])
    trace=list(oldmeta["screen_trace"])
    old_selected=len(keep)
    count=collections.Counter(x["year"] for x in keep)
    f.prior.r32p.CNF_LIMIT=f.MAX_PLAIN
    (ROOT/"empty.tsv").write_text("")
    tried=0
    for year,g,kind in current:
        if tried>=MAX_ATTEMPTS or len(keep)>=TARGET:break
        tried+=1
        row=dict(year=year,gbd=g,rank_extension=tried,mini_label="yes" if kind==0 else "unknown_or_no")
        target=ROOT/(g+".cnf")
        if count[year]>=MAX_PER_YEAR:
            row["reason"]="fixed_year_quota"
            trace.append(row);continue
        try:
            raw=f.get("https://benchmark-database.de/file/"+g,f.MAX_RAW,seconds=18)
            plain,compression=f.prior.r32p.decode(raw)
            need(len(plain)<=f.MAX_PLAIN,"plain CNF size budget")
            n,m=f.prior.r32p.parse_dimacs_metadata(plain)
            need(n<=f.MAX_VARS and m<=f.MAX_CLAUSES,"CNF geometry budget")
            digest=f.sha(plain)
            need(not any(k["sha256"]==digest for k in keep),"already-frozen source SHA collision")
            target.write_bytes(plain)
            reference=f.screen(target,binary,cadical)
            row.update(sha256=digest,vars=n,clauses=m,
                reference=reference,compression=compression,bytes=len(plain))
            if reference["status"] not in ("SAT","UNSAT"):
                row["reason"]="reference_not_solved_or_cross_checked"
            elif not(f.MIN_REFERENCE_S<=reference["runtime_s"]<=f.MAX_REFERENCE_S):
                row["reason"]="reference_outside_precommitted_easy_band"
            else:
                row["reason"]="READY"
                keep.append(dict(year=year,gbd=g,filename=target.name,sha256=digest,
                    vars=n,clauses=m,bytes=len(plain),source_url="https://benchmark-database.de/file/"+g,
                    reference_screen_s=reference["runtime_s"],
                    reference_screen_status=reference["status"],
                    witness_checked=reference["witness_checked"],
                    unsat_cross_solver=reference["unsat_cross_solver"],
                    independent_unsat_lrat=False,
                    selection_metadata="minisat1m=yes" if kind==0 else "SHA_ranked_all"))
                count[year]+=1
        except Exception as e:
            row["reason"]="source_download_or_reference_error"
            row["detail"]=(type(e).__name__+": "+str(e))[:180]
        if row["reason"]!="READY":target.unlink(missing_ok=True)
        trace.append(row)
        print("MRE7E_SCREEN",json.dumps(row,sort_keys=True),flush=True)
    new_manifest=dict(protocol=PROTO,
        parent_freeze_protocol=oldmeta["protocol"],
        parent_manifest_sha256=old_sha,
        parent_six_SHA_untouched=True,previous_selected=old_selected,
        indexes=metadata,reference_band_s=[f.MIN_REFERENCE_S,f.MAX_REFERENCE_S],
        original_source_count=len(keep),target=TARGET,
        selected=len(keep),additional_selected=len(keep)-old_selected,
        attempt_extension=tried,counts_by_year=dict(count),
        source_selection_before_mre7e_gate=True,
        minisat1m_independent_reference_prefilter=True,
        source_selection_is_baseline_conditioned=True,
        extension_after_previous_pilot=True,
        not_globally_blind=True,not_universally_disjoint_from_unrecorded_history=True,
        independent_unsat_LRAT=False,selected_cases=keep,screen_trace=trace)
    (ROOT/"manifest.json").write_text(json.dumps(new_manifest,sort_keys=True,indent=2)+"\n")
    (ROOT/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in keep))
    print("MRE7E_FREEZE_FINAL",json.dumps({k:v for k,v in new_manifest.items()
        if k not in ("selected_cases","screen_trace")},sort_keys=True),flush=True)
    need(len(keep)>=MIN_REQUIRED,"still fewer than twenty reference-easy originals; no 20-case claims")
def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO,"wrong MRE7E version")
    need(m["parent_six_SHA_untouched"] and m["previous_selected"]==6,"changed pilot cohort")
    for c in m["selected_cases"]:
        need(f.sha((ROOT/c["filename"]).read_bytes())==c["sha256"],
            "original GBD SHA mismatch")
    print("MRE7E_VERIFY_PASS",len(m["selected_cases"]),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify"))
    p.add_argument("--binary",default="mre5/native")
    p.add_argument("--cadical",default="/usr/bin/cadical")
    a=p.parse_args()
    if a.action=="freeze":extend(a.binary,a.cadical)
    else:verify()
