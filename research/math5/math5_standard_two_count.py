#!/usr/bin/env python3
"""Two-source fixed-archive count-family MATH5 standard VeriPB E2E benchmark.

No new blind claim: these exact SAT2026 originals previously produced MATH5
custom certificates in GRAND-UNIFIED run 43853390060.
"""
import hashlib,json,os,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"/"math5"))
import math5_standard_pilot as pilot

SOURCES={
    25:("25-fbd9968f5067604694f11f14c07c5527.cnf",
        "28b9b934f492f135dd00c3771d7670703daeb2fa03f98cf21ea8b7286958af4e"),
    31:("31-b0142b06940fb02e2b4ddb7a2101a3d6.cnf",
        "8020990ff906e9b2f7ec72652da7db736d90db4170e104a888454dffa583aa88")}
OUT=ROOT/"results/math5_standard_two_count"

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    controls=pilot.negative_tests()
    rows=[]
    for id,(basename,sha) in SOURCES.items():
        pilot.SOURCE=ROOT/"unified_realblind100_inputs/cnf"/basename
        pilot.EXPECTED=sha
        if hashlib.sha256(pilot.SOURCE.read_bytes()).hexdigest()!=sha:
            raise ValueError("frozen source identity changed on id "+str(id))
        for rep in (0,1):
            row=pilot.one(rep)
            row["source_id"]=id
            rows.append(row)
            print("MATH5_TWO_COUNT_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    summary={
      "status":"PASS","source_count":len(SOURCES),
      "original_sha256":{str(i):v[1] for i,v in SOURCES.items()},
      "verified_standard_proofs":len(rows),
      "trials":len(rows),"8s_e2e_cap":True,
      "per_source_e2e_sum_s":{str(i):round(sum(r["par2_s"] for r in rows if r["source_id"]==i),6) for i in SOURCES},
      "total_e2e_s":round(sum(r["par2_s"] for r in rows),6),
      "controls":controls,
      "scope":"RETROSPECTIVE previously observed 2026 count family; source-frozen solver and external VeriPB; no blind/world-ranking claim"}
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("MATH5_TWO_COUNT_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
