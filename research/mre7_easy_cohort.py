#!/usr/bin/env python3
"""MRE7 source-locked prospective easy SAT2026 cohort, metadata scouting.

Official CaDiCaL3 published original runtime is allowed ONLY for complexity
stratification, not DRNAS selector training. This scout DOES NOT solve inputs,
read source structure, or select based on DRNAS performance. Past visible
source IDs and all 220 formerly attempted R82 main-track IDs are excluded.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,pathlib,sys
import mre6b_blind_freeze as old

PROTO="DRNAS-MRE7-PROSPECTIVE-EASY-2026-SCORES-20261108-v1"
SALT="DRNAS-MRE7-SAT2026-EASY-HOLDOUT-SALT-FROZEN-BEFORE-SOLVES-20261108-v1"
BANDS=((0.1,5.0),(0.1,10.0),(0.0,20.0))
ROOT=pathlib.Path("mre7")
def need(test,msg):
    if not test:raise RuntimeError("MRE7_SCORES_FAIL_CLOSED "+str(msg))
def hashkey(v):return hashlib.sha256((SALT+"|"+v).encode()).hexdigest()

def scout():
    uri=old.r52.fetch_bytes(old.r52.URI,100000)
    scores=old.r52.fetch_bytes(old.r52.SCORES,24*1024*1024)
    official=[u.strip().rsplit("/",1)[-1] for u in uri.decode().splitlines() if u.strip()]
    need(len(official)==400 and len(set(official))==400,"unexpected official 2026 index")
    rows=list(csv.DictReader(io.StringIO(scores.decode())))
    baseline=[r for r in rows if r.get("solverid")=="biere_cadical3[main]"]
    need(len(baseline)==400,"not exactly 400 official CaDiCaL3 results")
    known=set(x.strip() for x in old.PRIOR.read_text().splitlines()
              if len(x.strip())==32 and not x.startswith("#"))
    repo_ids,_=old.inspect_repo_ids(set(official))
    r82_220=set(sorted(official,key=lambda g:hashlib.sha256(
        ("DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1/2026/"+g).encode()).hexdigest())[:220])
    old_manifest=old.ROOT/"manifest.json"
    need(old_manifest.is_file(),"missing MRE6b prior experimental manifest")
    previous=json.loads(old_manifest.read_text())
    known.update(c["gbd"] for c in previous["cases"])
    exclude=known|repo_ids|r82_220
    needs=[]
    for low,high in BANDS:
        arr=[]
        for r in baseline:
            g=r.get("instanceid","")
            if g not in official or r.get("status") not in ("sat-verified","unsat-verified"):continue
            try:t=float(r["runtime"])
            except (ValueError,KeyError):continue
            if low<=t<=high and g not in exclude:
                arr.append(dict(gbd=g,reference_runtime_s=t,
                    verified_status="SAT" if r["status"]=="sat-verified" else "UNSAT",
                    official_score_source="biere_cadical3[main]"))
        arr.sort(key=lambda x:hashkey(x["gbd"]))
        needs.append(dict(band=[low,high],total=len(arr),
            SAT=sum(x["verified_status"]=="SAT" for x in arr),
            UNSAT=sum(x["verified_status"]=="UNSAT" for x in arr),
            top_ids=[x["gbd"] for x in arr[:32]],
            candidates=arr))
    ROOT.mkdir(exist_ok=True)
    summary=dict(protocol=PROTO,scores_sha256=hashlib.sha256(scores).hexdigest(),
        uri_sha256=hashlib.sha256(uri).hexdigest(),
        historical_excluded=len(exclude & set(official)),
        old_mre6b_count=len(previous["cases"]),
        bands=needs,registry_exhaustive=False,
        prospective_development_exclusions=True)
    (ROOT/"scout.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("MRE7_SCOUT_FINAL",json.dumps({k:v if k!="bands" else
        [{z:y for z,y in b.items() if z!="candidates"} for b in needs]
        for k,v in summary.items()},sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("scout",))
    args=parser.parse_args()
    if args.action=="scout":scout()
