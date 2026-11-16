#!/usr/bin/env python3
"""Two-source fixed-archive count-family MATH5 standard VeriPB E2E benchmark.

No new blind claim: these exact SAT2026 originals previously produced MATH5
custom certificates in GRAND-UNIFIED run 43853390060.
"""
import hashlib,json,os,pathlib,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"/"math5"))
import math5_standard_pilot as pilot

SOURCES={
    25:("25-fbd9968f5067604694f11f14c07c5527.cnf",
        "28b9b934f492f135dd00c3771d7670703daeb2fa03f98cf21ea8b7286958af4e"),
    31:("31-b0142b06940fb02e2b4ddb7a2101a3d6.cnf",
        "8020990ff906e9b2f7ec72652da7db736d90db4170e104a888454dffa583aa88")}
OUT=ROOT/"results/math5_standard_two_count"

def kissat_one(source_id,rep):
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="strict-kissat-") as td:
        proof=pathlib.Path(td)/"proof.drat"
        r=pilot.execute([pilot.KISSAT,pilot.SOURCE,proof],pilot.CAP)
        verdict="TIMEOUT" if r["expired"] else "UNKNOWN"
        accepted=False
        checker_s=0.0
        if r["rc"]==20 and not r["expired"] and proof.exists():
            rem=pilot.CAP-(time.perf_counter()-started)
            if rem>0:
                checked=pilot.execute([pilot.DRAT,pilot.SOURCE,proof],rem)
                checker_s=checked["seconds"]
                accepted=checked["rc"]==0 and "VERIFIED" in checked["stdout"]+checked["stderr"]
                verdict="UNSAT_DRAT_VERIFIED" if accepted else "INVALID_OR_UNVERIFIED_PROOF"
        elif r["rc"]==10 and not r["expired"]:
            verdict="UNEXPECTED_SAT"
            raise RuntimeError("Kissat contradicts verified standard UNSAT source")
        elapsed=time.perf_counter()-started
        return {"source_id":source_id,"rep":rep,"arm":"Kissat",
          "status":verdict,"accepted":accepted,
          "solver_s":round(r["seconds"],6),
          "checker_s":round(checker_s,6),
          "e2e_s":round(elapsed,6),
          "par2_s":round(elapsed if accepted and elapsed<=pilot.CAP else 2*pilot.CAP,6)}

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    controls=pilot.negative_tests()
    rows=[]
    kissat_rows=[]
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
            reference=kissat_one(id,rep)
            kissat_rows.append(reference)
            print("MATH5_KISSAT_REFERENCE "+json.dumps(reference,sort_keys=True),flush=True)
    summary={
      "status":"PASS","source_count":len(SOURCES),
      "original_sha256":{str(i):v[1] for i,v in SOURCES.items()},
      "verified_standard_proofs":len(rows),
      "trials":len(rows),"8s_e2e_cap":True,
      "per_source_e2e_sum_s":{str(i):round(sum(r["par2_s"] for r in rows if r["source_id"]==i),6) for i in SOURCES},
      "total_e2e_s":round(sum(r["par2_s"] for r in rows),6),
      "controls":controls,
      "kissat_verified":sum(r["accepted"] for r in kissat_rows),
      "kissat_PAR2_s":round(sum(r["par2_s"] for r in kissat_rows),6),
      "scope":"RETROSPECTIVE previously observed 2026 count family; source-frozen solver and external VeriPB; no blind/world-ranking claim"}
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (OUT/"kissat_trials.json").write_text(json.dumps(kissat_rows,indent=2,sort_keys=True)+"\n")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("MATH5_TWO_COUNT_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
