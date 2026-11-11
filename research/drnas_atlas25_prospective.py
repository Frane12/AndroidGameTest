#!/usr/bin/env python3
"""Prospective ATLAS25: 64 new SHA, 8 structural families, 2 reps, 6 arms.
Frozen source selection before outcomes; do not tune on this cohort.
Generated CNFs are original inputs, NOT external competition instances.
"""
import hashlib,json,pathlib,sys
sys.path.insert(0,"research")
import drnas_atlas25_benchmark as B
import drnas_atlas_wide500 as W
from drnas_atlas25_benchmark import run,summarize
ARMS=("A","C7_ADAPT","V24_LIVE","V25_B","V25_C","KISSAT","CMS")
B.ARMS=ARMS
B.Old.ARMS=ARMS
ROOT=pathlib.Path("mre_atlas25")
CATS=("random3_uniform","random3_planted","xor3_sat","xor4_sat",
      "xor_chain_unsat","xor_hybrid","color3_unsat","pigeonhole_unsat")
INDICES=(330,331,332,333,334,335,336,337)
CAP=10
def main():
    sources=[]
    for family in CATS:
        for idx in INDICES:
            n,clauses=W.synth_one(family,idx)
            raw=W.canonical(n,clauses)
            path=ROOT/"prospective"/f"{family}_{idx}.cnf"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
            sources.append(dict(id=len(sources),family=family,index=idx,
                sha256=hashlib.sha256(raw).hexdigest(),
                archive_entry=f"generated:WIDE500:{family}:{idx}",
                source_kind="PROSPECTIVE_DETERMINISTIC_GENERATED",path=str(path),
                bytes=len(raw),cohort="prospective"))
    assert len(sources)==64 and len({s["sha256"] for s in sources})==64
    # SHA are frozen before solver runs; separate family/indices from ATLAS25 previous fresh.
    manifest=dict(sources=sources,arms=ARMS,cap_s=CAP,reps=2,
                  policy_frozen=True,previous_indices=(130,131),
                  prospective_indices=INDICES,one_logical_cpu=True,
                  independent_UNSAT_LRAT=False)
    (ROOT/"prospective"/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2))
    print("ATLAS25P_MANIFEST "+json.dumps(dict(n=64,arms=ARMS,indices=INDICES),sort_keys=True),flush=True)
    legacy=B.BIN/"drnas_atlas23"
    if not legacy.exists():legacy.symlink_to("drnas_atlas25")
    rows=[]
    for source in sources:
        for rep in range(2):
            verdicts=set()
            for arm in ARMS:
                r=run(source,arm,rep,CAP)
                rows.append(r)
                print("ATLAS25P_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
                if r["status"]!="UNKNOWN":verdicts.add(r["status"])
            if {"SAT_VERIFIED","UNSAT_UNVERIFIED"}<=verdicts:
                raise AssertionError("contradictory SAT/UNSAT "+source["sha256"])
    result=dict(manifest=manifest,rows=rows,summary=summarize(rows),
                original_SHA_verified=True,independent_UNSAT_LRAT=False)
    (ROOT/"prospective"/"results.json").write_text(json.dumps(result,sort_keys=True,indent=2))
    print("ATLAS25P_FINAL "+json.dumps(dict(sources=64,trials=len(rows),summary=result["summary"]),sort_keys=True),flush=True)
if __name__=="__main__":main()
