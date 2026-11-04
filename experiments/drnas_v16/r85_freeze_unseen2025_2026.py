#!/usr/bin/env python3
"""R85 original official SAT2025+2026 prospective NEW-ID freeze.

Revision of earlier impossible quota (3 unseen mixed-XOR 2026): NO solver
benchmark ran before this revision. We now freeze 4 fresh 2025 + 4 fresh 2026
without requiring XOR. Mixed XOR presence reported, not used to pick sources.
All IDs and SHA hashes disjoint from R63 R66 R67 R81 R82 records. Include
historical R72 first 100 2025 attempted candidates in exclusions.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,collections
from pathlib import Path
import r52_prospective_2026_toprefs as r52
import r73_fresh_quick_unseen_2025 as r73
import r32p_real_satcomp26_benchmark as r32p
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r83_live_xor_cdcl_wide as old

PROTO="DRNAS-R85-NEW-REAL-2025-2026-ABCD-20261104-v2"
SALT="DRNAS-R85-NEW-NOT-SPEED-SELECTED-2025-2026-ABCD-20261104-v2"
REPS,CAP,SHARDS=2,35.0,8
MODES=("clean","A_passive","B_active64","C_spread64","D_wide256")
MAX_2025,MAX_2026=145,130
def ck(ok,reason):
    if not ok:raise RuntimeError("R85_FREEZE_FAIL_CLOSED "+str(reason))
def sha(p):return old.sha(p)
def ordering(s):return hashlib.sha256((SALT+"/"+s).encode()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def old_sources(args):
    excluded=set();shas=set();provenance={}
    for name in ("r63","r66","r67","r81","r82"):
        path=Path(getattr(args,name));m=json.loads(path.read_text())
        provenance[name]={"protocol":m["protocol"],"sha256":sha(path)}
        for key in ("cases","source_selection_attempts","selection_attempts","attempts"):
            for c in m.get(key,[]):
                if c.get("gbd"):excluded.add(c["gbd"])
                if c.get("sha256"):shas.add(c["sha256"])
        if name=="r63":excluded.update(m["excludes_previously_seen_gbd"])
    ck(len(excluded)>=80,"incomplete history")
    return excluded,shas,provenance
def freeze(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    excluded,shas,hist=old_sources(a)
    idx25=r52.fetch_bytes(r73.SC2025,100000)
    idx26=r52.fetch_bytes(r52.URI,100000)
    ids25=[s.rsplit("/",1)[-1] for s in idx25.decode().strip().splitlines()]
    ids26=[s.rsplit("/",1)[-1] for s in idx26.decode().strip().splitlines()]
    ck(len(ids25)>=300 and len(ids26)==400 and len(set(ids26))==400,"competition official indices changed")
    old_r72_salt="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"
    old_r72_ranked=sorted((g for g in ids25 if g not in excluded and g not in set(ids26)),
       key=lambda g:hashlib.sha256((old_r72_salt+":"+g).encode()).hexdigest())
    excluded.update(old_r72_ranked[:100])
    scores=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    labels={x["instanceid"]:x["status"] for x in csv.DictReader(io.StringIO(scores.decode()))
        if x["solverid"]=="biere_cadical3[main]"}
    ck(len(labels)==400,"verified official 2026 reference statuses")
    ready=[];attempts=[];seen_sha=set()
    r32p.CNF_LIMIT=48*1024*1024
    for year,ids,limit in ((2025,ids25,MAX_2025),(2026,ids26,MAX_2026)):
        count=0;ordered=sorted((g for g in ids if g not in excluded),
            key=lambda g:ordering(str(year)+"/"+g))
        for g in ordered[:limit]:
            if count>=4:break
            rec={"year":year,"gbd":g}
            dest=out/(str(year)+"-"+g+".cnf")
            if year==2026 and labels.get(g) not in ("sat-verified","unsat-verified"):
                rec["state"]="not_verified_2026";attempts.append(rec);continue
            try:
                packed,redirect=r32p.request_url(
                    "https://benchmark-database.de/file/"+g,25*1024*1024,seconds=26)
                plain,compression=r32p.decode(packed)
                ck(len(plain)<=48*1024*1024,"uncompressed source over cap")
                n,m=r32p.parse_dimacs_metadata(plain)
                ck(n>0 and m>0,"invalid empty formula")
                dest.write_bytes(plain)
                hash_=sha(dest)
                ck(hash_ not in shas and hash_ not in seen_sha,
                   "not distinct from historical source SHA")
                feature=r63.inspect_exact_xor(dest,n,m)
                row=dict(year=year,gbd=g,filename=dest.name,sha256=hash_,
                    official_status=("UNKNOWN" if year==2025 else
                         ("SAT" if labels[g]=="sat-verified" else "UNSAT")),
                    source_verified_status=year==2026,
                    source_url="https://benchmark-database.de/file/"+g,
                    variables=n,clauses=m,bytes=len(plain),size_bytes=len(plain),
                    compression=compression,compressed_bytes=len(packed),
                    redirect=redirect,group=r64.group(feature),
                    stratum="UNSCREENED_ORIGINAL",prior_drnas_benchmarked=False,
                    **feature)
                ready.append(row);count+=1;seen_sha.add(hash_)
                rec.update(state="READY",sha256=hash_,group=row["group"],
                    vars=n,clauses=m)
            except Exception as e:
                dest.unlink(missing_ok=True)
                rec.update(state="source_unavailable_or_size_guard",
                    reason=(type(e).__name__+": "+str(e))[:160])
            attempts.append(rec)
            print("R85_SOURCE",json.dumps(rec,sort_keys=True),flush=True)
        ck(count==4,f"only {count}/4 fresh official {year} originals")
    ck(len(ready)==8,"wrong number of frozen sources")
    mf=dict(protocol=PROTO,source_description="4 real 2025 + 4 real verified 2026 Main originals",
       cases=ready,shards=SHARDS,reps=REPS,cap_s=CAP,modes=MODES,
       predeclared_selection="SHA-ranked official indices, no XOR or speed screening, excludes all known source ID/SHA history",
       selection_salt=SALT,index_sha256={"2025":hashlib.sha256(idx25).hexdigest(),
          "2026":hashlib.sha256(idx26).hexdigest()},
       verified_2026_scores_sha256=hashlib.sha256(scores).hexdigest(),
       historical_manifest_ids=hist,historical_exclusions=len(excluded),
       source_selection_attempts=attempts,
       groups=dict(collections.Counter(r["group"] for r in ready)),
       limitations=[
        "Revision occurred after first 2026 3-XOR quota freeze failed, BEFORE ANY new solver timing.",
        "These are official original CNFs new relative to documented R63/R66/R67/R81/R82 cohorts; unknown unrecorded runs cannot be excluded.",
        "2025 source SAT/UNSAT labels not imported; require agreement and validate SAT witnesses. UNSAT not independent LRAT proof.",
        "Only verified 2026 reference statuses are imported. UNSAT still lacks new proof replay.",
        "No XOR or runtime selection for this validation cohort; if it contains no XOR, measure no XOR benefit and do not infer it.",
        "Historical XOR-rich formulas (R84) are a separate clearly retrospective diagnostic cohort.",
        "Availability and 48MiB source limit bias selection; no global competition ranking.",
        "All runs matched by original SHA, same-source repetitions, same GitHub runner within shard."])
    dump(out/"manifest.json",mf)
    (out/"source.sha256").write_text("".join(r["sha256"]+"  "+r["filename"]+"\n" for r in ready))
    print("R85_NEW_REAL_UNSEEN_8_FREEZE_PASS",
        json.dumps(dict(n=8,years=dict(collections.Counter(r["year"] for r in ready)),
            groups=mf["groups"],previous_id_exclusions=len(excluded))),flush=True)
def main():
    p=argparse.ArgumentParser()
    for n in ("r63","r66","r67","r81","r82","out"):p.add_argument("--"+n,required=True)
    freeze(p.parse_args())
if __name__=="__main__":main()
