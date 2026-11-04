#!/usr/bin/env python3
"""R110 paired SAT2025 development replay: pinned CaDiCaL vs certified ANF bridge.

All source CNFs are SHA-pinned from R106. No new holdout or official result
is claimed. The solver running time plus every preprocessing invocation
is charged to R110, with equal end-to-end wall time caps.
"""
import argparse
import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as checker
import r110_anf_bridge as bridge


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def run(binary, source, original, expected, cap):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary),str(source)],text=True,capture_output=True,
                         errors="replace",timeout=max(0.05,cap))
        elapsed=time.perf_counter()-start
        result=checker.status(p.stdout,p.returncode)
        if result!=expected:
            raise RuntimeError("R110_FAIL_CLOSED status mismatch "+str(source))
        if result=="SAT" and not checker.model_valid(p.stdout,original):
            raise RuntimeError("R110_FAIL_CLOSED invalid original SAT witness "+str(source))
        return result,elapsed
    except subprocess.TimeoutExpired:
        return "TIMEOUT",cap


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--solver",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--cap",type=float,default=6.)
    p.add_argument("--reps",type=int,default=2)
    args=p.parse_args()
    if not (1<=args.cap<=30 and 1<=args.reps<=5):
        raise RuntimeError("R110 invalid cap/reps")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=pathlib.Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    binary=pathlib.Path(args.solver).resolve()
    if not binary.is_file():
        raise RuntimeError("R110 missing pinned solver")
    manifest=json.loads(pathlib.Path(args.manifest).read_text())
    if len(manifest)!=8 or len({x["sha256"] for x in manifest})!=8:
        raise RuntimeError("R110 expected eight different R106 2025 SHA pins")
    full_manifest=json.loads(pathlib.Path("research/r106_manifest.json").read_text())
    assert {x["sha256"] for x in manifest}=={x[3] for x in full_manifest["cases"]}
    rows=[]
    structural=[]
    for case in manifest:
        source=(pathlib.Path(args.source_dir)/case["name"]).resolve()
        if sha(source)!=case["sha256"]:
            raise RuntimeError("R110_FAIL_CLOSED real source SHA mismatch")
        original=checker.cnf_clauses(source)
        prep_started=time.perf_counter()
        analysis=bridge.inspect(source)
        dest=out/(case["name"]+".augmented.cnf")
        bridge.augmented(source,dest,analysis)
        if checker.cnf_clauses(dest)[:len(original)]!=original:
            raise RuntimeError("R110_FAIL_CLOSED original CNF changed")
        prep=time.perf_counter()-prep_started
        # Include serialization, output validation and proof replay overhead.
        # wall clock measured independently: all preprocessing work is charged.
        structural.append(dict(name=case["name"],sha256=case["sha256"],
                               gates=analysis["gates"],windows=analysis["mixed_windows"],
                               lemmas=len(analysis["candidate_lemmas"]),
                               prep_s=prep,proof="local original-CNF exhaustive"))
        (out/(case["name"]+".proof.json")).write_text(json.dumps(analysis,indent=2)+"\n")
        for rep in range(args.reps):
            sequence=["clean_cadical","r110_mixed"]
            random.Random(int(hashlib.sha256((case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(sequence)
            for mode in sequence:
                if mode=="clean_cadical":
                    status,solver_s=run(binary,source,original,case["expected"],args.cap)
                    total=solver_s
                elif prep>=args.cap:
                    status,solver_s,total="TIMEOUT",0.,args.cap
                else:
                    status,solver_s=run(binary,dest,original,case["expected"],args.cap-prep)
                    total=min(args.cap,prep+solver_s)
                par2=2*args.cap if status=="TIMEOUT" else total
                entry=dict(formula=case["name"],source_sha256=case["sha256"],
                           source_type="SAT Competition 2025 GBD development replay",
                           mode=mode,rep=rep,status=status,
                           preparation_s=(prep if mode=="r110_mixed" else 0.),
                           solver_s=round(solver_s,6),
                           total_s=round(total,6),par2_s=round(par2,6),
                           cap_s=args.cap,cpu_cores=1,solver_sha256=sha(binary))
                rows.append(entry)
                print("R110_PAIRED_TRIAL",case["name"],rep,mode,status,
                      "PAR2",entry["par2_s"],"prep",entry["preparation_s"],flush=True)
    for case in manifest:
        for rep in range(args.reps):
            pair=[r for r in rows if r["source_sha256"]==case["sha256"] and r["rep"]==rep]
            if len(pair)!=2 or set(r["mode"] for r in pair)!={"clean_cadical","r110_mixed"}:
                raise RuntimeError("R110_FAIL_CLOSED pair missing")
            found={r["status"] for r in pair}-{"TIMEOUT"}
            if len(found)>1:
                raise RuntimeError("R110_FAIL_CLOSED contradictory SAT results")
    results={}
    for mode in ("clean_cadical","r110_mixed"):
        sel=[r for r in rows if r["mode"]==mode]
        results[mode]=dict(trials=len(sel),solved=sum(r["status"]!="TIMEOUT" for r in sel),
                           par2_s=round(sum(r["par2_s"] for r in sel),6))
    base=results["clean_cadical"]["par2_s"]
    report=dict(protocol="DRNAS-R110-ANF-MIXED-REAL2025-DEV",
        status="PASS_DEVELOPMENT_REPLAY",cases=len(manifest),total_trials=len(rows),
        repetitions=args.reps,cap_s=args.cap,solver_sha256=sha(binary),
        source_identity="R106 SHA-pinned 2025 reused, NOT blind unseen",
        correctness="SAT original CNF witnesses verified; UNSAT solver status only, no LRAT",
        comparison=results,gain_pct=round(100*(1-results["r110_mixed"]["par2_s"]/base),6),
        formulas=structural,rows=rows,
        limitations=["no live SAT two-way workers","bounded XOR3/AND gate windows only",
                     "not a general ANF nonlinear solver",
                     "selection not independent holdout; no world record claim"])
    (out/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R110_REAL2025_AUDIT_PASS",json.dumps({
        "trials":len(rows),"comparison":results,"gain_pct":report["gain_pct"]}),flush=True)

if __name__=="__main__":
    main()
