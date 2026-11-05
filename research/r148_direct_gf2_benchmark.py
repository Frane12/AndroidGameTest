#!/usr/bin/env python3
"""R148: direct IPASIR-UP GF(2) propagation vs frozen same-CaDiCaL controls.

Known SATLIB PARITY development formulas: NOT blind and NOT an official ranking.
Six original CNFs, two repetitions, six modes = 72 paired measurements.
All SAT models checked on original CNF in C++. No independent UNSAT proof yet.
"""
import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
import r133c_native_gf2_benchmark as frozen

PROTO="DRNAS-R148-DIRECT-GF2-IPASIR-UP-PAIRED-20261105-v1"
CAP=10.0
REPS=2
MODES=("clean","freeze","watch","clause","direct0","direct")
FIELDS=("source_rows","derived_rows","original_clauses","assignments",
        "backtracks","watch_lookups","rows_scanned","clauses_emitted",
        "direct_proposals","direct_reason_requests","direct_reason_lits",
        "direct_ready_checks","direct_no_units","reason_cache_peak")

def need(ok,msg):
    if not ok: raise RuntimeError("R148_AUDIT_FAIL_CLOSED "+msg)

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            h.update(chunk)
    return h.hexdigest()

def prepare(source,out,tag):
    rows=out/(tag+".tsv")
    proof=out/(tag+"-proof.json")
    t=time.perf_counter()
    cmd=[sys.executable,"research/r93_export_verified_rows.py",
         "export","--cnf",str(source),"--rows",str(rows),"--evidence",str(proof)]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
    need(p.returncode==0,"source parity certificate: "+p.stderr[-500:])
    prep=time.perf_counter()-t
    ev=json.loads(proof.read_text())
    need(ev.get("source_sha256")==sha(source),"original CNF SHA mismatch")
    need(ev.get("protocol")=="R93-LIVE-XOR-PROOF-CERTS-v1","wrong parity exporter")
    need(isinstance(ev.get("exported"),int),"no verified exporter count")
    return rows,ev,prep

def solve(binary,mode,source,rows,prep):
    charge=0.0 if mode=="clean" else prep
    cmd=[str(binary.resolve()),mode,str(source.resolve()),str(rows.resolve())]
    if charge>=CAP:
        return dict(mode=mode,status="TIMEOUT",par2_s=2*CAP,
                    total_s=CAP,solver_s=0.0,preprocessing_s=charge,
                    **{k:0 for k in FIELDS})
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP-charge)
        elapsed=time.perf_counter()-start
    except subprocess.TimeoutExpired:
        return dict(mode=mode,status="TIMEOUT",par2_s=2*CAP,
                    total_s=CAP,solver_s=CAP-charge,preprocessing_s=charge,
                    **{k:0 for k in FIELDS})
    need(p.returncode in (10,20),
         "binary failure mode="+mode+" rc="+str(p.returncode)+
         " stderr="+p.stderr[-1200:]+" stdout="+p.stdout[-400:])
    match=next((l for l in p.stdout.splitlines() if l.startswith("R148_RESULT ")),None)
    need(match is not None,"missing native telemetry "+mode)
    tokens=dict(re.findall(r"(\w+)=([^\s]+)",match))
    need(tokens.get("mode")==mode,"mode telemetry mismatch")
    need(tokens.get("disabled")=="0","XOR watch invariant violated")
    status="SAT" if p.returncode==10 else "UNSAT"
    need(tokens.get("status")==status,"native status drift")
    if status=="SAT":
        need(tokens.get("sat_witness_checked")=="1","original SAT witness not checked")
    fields={k:int(tokens[k]) for k in FIELDS}
    if mode not in ("direct","direct0"):
        need(fields["direct_proposals"]==0,"other mode proposed direct propagation")
    if mode=="clean":
        need(fields["source_rows"]==0,"clean mode has active rows")
    if mode=="freeze":
        need(fields["watch_lookups"]==0 and fields["clauses_emitted"]==0,"freeze mode modifies search")
    if mode in ("watch","direct","direct0"):
        need(fields["clauses_emitted"]==0,"no-external-clauses mode added clauses")
    need(fields["direct_reason_lits"]<=fields["direct_reason_requests"],
         "malformed reason telemetry")
    total=elapsed+charge
    if total>=CAP: status="TIMEOUT"
    return dict(mode=mode,status=status,par2_s=2*CAP if status=="TIMEOUT" else round(total,6),
                total_s=round(min(CAP,total),6),solver_s=round(elapsed,6),
                preprocessing_s=round(charge,6),**fields)

def fixture_test(binary,out):
    source=frozen.fixture(out)
    rows,ev,prep=prepare(source,out,"fixture")
    need(ev["exported"]>=2,"no certified original fixture XOR rows")
    result={}
    for mode in MODES:
        result[mode]=solve(binary,mode,source,rows,prep)
        need(result[mode]["status"]=="SAT","fixture not SAT in "+mode)
    need(result["direct"]["derived_rows"]>0,"GF2 derived closure missing")
    (out/"fixture.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("R148_FIXTURE_PASS",json.dumps(result,sort_keys=True),flush=True)

def summarize(records,mode):
    selected=[r for r in records if r["mode"]==mode]
    solved=[r for r in selected if r["status"]!="TIMEOUT"]
    return dict(trials=len(selected),solved=len(solved),timeouts=len(selected)-len(solved),
                par2_s=round(sum(r["par2_s"] for r in selected),6),
                wall_s=round(sum(r["total_s"] for r in selected),6),
                median_solved_s=round(statistics.median(r["total_s"] for r in solved),6) if solved else None,
                **{k:sum(r[k] for r in selected) for k in FIELDS})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--satlib",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    args.binary=args.binary.resolve()
    args.out.mkdir(parents=True,exist_ok=True)
    need(args.binary.is_file(),"missing pinned native executable")
    if hasattr(os,"sched_getaffinity"):
        allowed=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(allowed)})
    native_sha=sha(args.binary)
    fixture_test(args.binary,args.out)
    controls=frozen.select_controls(args.satlib)
    need(len(controls)==6,"expected exactly six known SATLIB PARITY original CNFs")
    manifest=[dict(name=s.name,sha256=sha(s)) for s in controls]
    need(len(set(m["sha256"] for m in manifest))==6,"duplicate formula SHA")
    (args.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    records=[]
    for source in controls:
        digest=sha(source)
        rows,ev,prep=prepare(source,args.out,digest[:12])
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+digest+str(rep)).shuffle(order)
            answers=set()
            for mode in order:
                result=solve(args.binary,mode,source,rows,prep)
                result.update(sha256=digest,file=source.name,rep=rep,
                              original_parity_rows=ev["exported"],
                              binary_sha256=native_sha)
                records.append(result)
                if result["status"]!="TIMEOUT": answers.add(result["status"])
                need(len(answers)<=1,"contradicting SAT/UNSAT outcomes on "+source.name)
                print("R148_PAIRED",json.dumps(result,sort_keys=True),flush=True)
        print("R148_CASE_DONE",source.name,"rows",ev["exported"],
              "preprocessing_s",round(prep,6),flush=True)
    need(len(records)==6*REPS*len(MODES),"missing paired trials")
    with (args.out/"paired.csv").open("w",newline="") as file:
        w=csv.DictWriter(file,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
    summary={mode:summarize(records,mode) for mode in MODES}
    base=summary["clean"]["par2_s"]
    direct=summary["direct"]["par2_s"]
    legacy=summary["clause"]["par2_s"]
    report=dict(protocol=PROTO,formulas=6,repetitions=REPS,measurements=len(records),
                cap_s=CAP,bench_scope="SIX REUSED SATLIB PARITY (development; non-blind)",
                original_cnf_unchanged=True,certified_source_rows=True,
                independent_unsat_proof=False,sat_original_model_checked=True,
                pinned_native_sha256=native_sha,source_manifest=manifest,
                paired_randomized_order=True,prep_cost_included=True,
                core_affinity_pinned_if_available=True,
                actual_internal_cdcl_decisions_and_conflicts_not_available=True,
                modes=summary,
                direct_vs_clean_gain_pct=round(100*(base-direct)/base,5),
                direct_vs_clause_gain_pct=round(100*(legacy-direct)/legacy,5),
                direct0_vs_freeze_gain_pct=round(100*(summary["freeze"]["par2_s"]-
                    summary["direct0"]["par2_s"])/summary["freeze"]["par2_s"],5),
                verdict="EXPERIMENTAL_ONLY_NO_PROMOTION")
    (args.out/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R148_FINAL_AUDIT",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
