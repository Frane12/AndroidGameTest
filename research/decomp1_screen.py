#!/usr/bin/env python3
"""DRNAS DECOMP1: SHA-frozen, source-only exact incidence separator screening.

No SAT/UNSAT claims and no PAR2 benchmarks in this phase. Separation is
conditional: for a variable x whose removal disconnects incidence components,
F|x=b is a conjunction of independent subformulae, for each b in {0,1}.
Only an algebraic/structural opportunity, not guaranteed runtime improvement.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

SOURCE=pathlib.Path("mre_x20")
OUT=pathlib.Path("mre_decomp1")
NATIVE=OUT/"bin/decomp1_incidence"
CAP_MS=2500
EXTERNAL_TIMEOUT=4.0
PROTO="DRNAS-DECOMP1-INCIDENCE-SEPARATOR-SHA-SCREEN-v1"

def need(cond,msg):
    if not cond:raise RuntimeError("DECOMP1_FAIL_CLOSED "+msg)
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def freeze():
    m=json.loads((SOURCE/"manifest.json").read_text())
    need(len(m["cases"])==24,"frozen EQUIV2 registry mismatch")
    need(NATIVE.is_file(),"missing native graph scanner")
    source=list(sorted(m["cases"],key=lambda c:c["sha256"]))
    need(len({x["sha256"] for x in source})==len(source),
         "duplicate original SHA")
    return source

def run():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for c in freeze():
        path=SOURCE/c["filename"]
        need(path.is_file() and sha(path)==c["sha256"],"source SHA changed")
        start=time.perf_counter()
        try:
            proc=subprocess.run([str(NATIVE),str(path),str(CAP_MS)],
                     capture_output=True,text=True,errors="replace",
                     timeout=EXTERNAL_TIMEOUT,check=False)
            msg=[x.split(" ",1)[1] for x in proc.stdout.splitlines()
                 if x.startswith(("DECOMP1_SCAN ","DECOMP1_ABSTAIN "))]
            need(len(msg)==1,"native protocol result ambiguous or missing")
            data=json.loads(msg[0])
            need(proc.returncode in (0,75),"native crashed "+proc.stderr[-300:])
            status=data.get("status","ABSTAIN")
            need((proc.returncode==0)==(status=="OK"),"status mismatch")
        except subprocess.TimeoutExpired:
            status="ABSTAIN"
            data={"reason":"external_timeout"}
        wall=time.perf_counter()-start
        row={"protocol":PROTO,"original_sha256":c["sha256"],
             "gbd":c.get("gbd"),"filename":c["filename"],
             "original_SHA_verified":sha(path)==c["sha256"],
             "status":status,"analysis_wall_s":round(wall,6),
             "native_budget_ms":CAP_MS,"graph":data,
             "SAT_solved":False,"UNSAT_solved":False,
             "bounded_CDCL":False,"E2E_SAT_benchmark":False}
        need(row["original_SHA_verified"],"SHA drift after analysis")
        rows.append(row)
        (OUT/"screen.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
        print("DECOMP1_CASE "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==24,"incomplete structural screen")
    ok=[r for r in rows if r["status"]=="OK"]
    candidate=[r for r in ok if r["graph"]["best_separator_var"]>0]
    disconnected=[r for r in ok if r["graph"]["clause_components"]>1]
    summary={"protocol":PROTO,"original_sources":len(rows),
             "original_SHA_verified":all(r["original_SHA_verified"] for r in rows),
             "analyzed":len(ok),"abstained":len(rows)-len(ok),
             "source_disconnected":len(disconnected),
             "with_meaningful_articulation_10_clause_min":len(candidate),
             "total_analysis_wall_s":round(sum(r["analysis_wall_s"] for r in rows),6),
             "SAT_solved":0,"UNSAT_solved":0,
             "PAR2_s":None,"one_CPU":True,
             "no_original_or_frozen_mutation":True,
             "not_globally_unseen":True,
             "candidate_top":[{"sha256":r["original_sha256"],
                              "best_var":r["graph"]["best_separator_var"],
                              "second_part_clauses":r["graph"]["best_second_largest_part"],
                              "parts":r["graph"]["best_clause_parts"]}
                              for r in sorted(candidate,key=lambda x:
                               -x["graph"]["best_second_largest_part"])[:8]]}
    (OUT/"audit.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("DECOMP1_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":
    run()
