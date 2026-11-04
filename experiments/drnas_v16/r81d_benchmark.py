#!/usr/bin/env python3
"""R81D exploratory replay on the SHA-frozen 16 official SATComp2025 originals.

The source cohort was freshly selected by R81C blind run BEFORE any R81D work,
but has now been analyzed in R81C: R81D is a mechanistic replay, not new blind
validation. Compare 6 frozen policies on the same original CNFs and CPU core:
Kissat, R28, R65, R81C, R81D passive, R81D active; cap 30s incl scan/prep.
Only exact XOR-derived unit/binary lemmas, with source-checkable proof witnesses.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import os
import random
import subprocess
import tempfile
import time
from pathlib import Path

import r81d_partial_xor_cdcl as r81d
import r81c_exact_algebra as r81c
import r78_xor_adaptive_prospective as r78

PROTO="DRNAS-R81D-PARTIAL-XOR-CDCL-MECHANISM-20261104-v1"
R81C_SOURCE_PROTOCOL="DRNAS-R81C-SAT2025-SOURCE-HOLDOUT-20261104-v1"
SHARDS=8
REPS=2
CAP=30.0
MODES=("clean_kissat","r28_gf2","r65_full","r81c_exact",
       "r81d_passive","r81d_active")

def check(v,message):
    if not v:raise RuntimeError("R81D_BENCHMARK_FAIL_CLOSED "+message)

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()

def load_sources(root):
    m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==R81C_SOURCE_PROTOCOL and m["ready"]==16 and
          len(m["cases"])==16,"wrong or incomplete frozen R81C input source")
    check(len({x["sha256"] for x in m["cases"]})==16,"duplicate sources")
    for c in m["cases"]:
        check(digest(root/c["filename"])==c["sha256"],
              "input source SHA drift")
    return m

def measure(args):
    root=Path(args.sources)
    manifest=load_sources(root)
    check(0<=args.shard<SHARDS,"invalid shard")
    binroot=Path(args.binaries).resolve()
    v=subprocess.run(["sha256sum","-c","binary.sha256"],cwd=binroot,
                     capture_output=True,text=True)
    check(v.returncode==0,"solver binary SHA mismatch "+v.stderr)
    kissat=(binroot/"kissat").resolve()
    gf2=(binroot/"r28_gf2").resolve()
    check(digest(kissat)==manifest["registry"]["binary_sha"],
          "frozen upstream Kissat SHA drift")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    r78.r65.MAX_PREP_S=2.0
    rows=[]
    for case in manifest["cases"][args.shard::SHARDS]:
        source=root/case["filename"]
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(hashlib.sha256(
                (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
            for mode in order:
                start=time.monotonic()
                target=source
                argv=[kissat,source]
                route="kissat"
                direct=None
                derived=None
                n_added=0
                with tempfile.TemporaryDirectory(prefix="drnas-r81d-") as temp:
                    if mode=="r28_gf2":
                        argv=[gf2,source,kissat]
                        route="r28"
                    elif mode=="r65_full":
                        _,_,lemmas,_,_=r78.r71.prepare(root,case)
                        n_added=len(lemmas)
                        if lemmas:
                            target=Path(temp)/"augmented_r65.cnf"
                            r78.r64.augment(source,target,case["variables"],
                                             case["clauses"],lemmas)
                            argv=[kissat,target]
                        route="r65"
                    elif mode=="r81c_exact":
                        direct=r81c.solve(source,case,max_budget_s=3.0)
                        route="r81c_"+direct["route"]
                    elif mode in ("r81d_passive","r81d_active"):
                        derived=r81d.prepare(source,case,max_budget=3.5,verify=True)
                        route=("passive_" if mode=="r81d_passive" else "active_")+derived["route"]
                        if mode=="r81d_active" and derived["proven_clauses"]:
                            target=Path(temp)/"augmented_r81d.cnf"
                            r78.r64.augment(source,target,case["variables"],case["clauses"],
                                            derived["proven_clauses"])
                            argv=[kissat,target]
                            n_added=len(derived["proven_clauses"])
                    overhead=time.monotonic()-start
                    remain=CAP-overhead
                    if direct and direct.get("solved"):
                        answer=direct["answer"]
                        solver_wall=0.0
                        timeout=False
                        solver_route=direct["route"]
                    else:
                        answer,solver_wall,timeout,solver_route=r78.run_solver(
                            argv,source,remain)
                    elapsed=time.monotonic()-start
                    solved=(not timeout and answer in ("SAT","UNSAT") and elapsed<=CAP)
                    row=dict(source_id=case["gbd"],source_sha256=case["sha256"],
                        group=case["group"],source_variables=case["variables"],
                        source_clauses=case["clauses"],rep=rep,mode=mode,
                        answer=answer,solved=solved,
                        end_to_end_s=round(elapsed,6),
                        overhead_s=round(overhead,6),
                        native_solver_s=round(solver_wall,6),
                        par2_s=round(elapsed if solved else CAP*2,6),
                        route=route,solver_route=solver_route,added=n_added,
                        r81d_source_equations=derived["equations"] if derived else None,
                        r81d_selected_equations=derived.get("selected_equations") if derived else None,
                        r81d_unit_premises=derived["units"] if derived else None,
                        r81d_rank=derived["rank"] if derived else None,
                        r81d_certificates=derived["certificates"] if derived else None,
                        r81c_route=direct["route"] if direct else None,
                        r81c_model_hex=hex(direct["model"]) if direct and direct.get("solved") and answer=="SAT" else None,
                        r81c_proof=direct.get("proof") if direct and direct.get("solved") and answer=="UNSAT" else None,
                        runner=os.environ.get("RUNNER_NAME",""),
                        commit=os.environ.get("GITHUB_SHA",""),
                        run_id=os.environ.get("GITHUB_RUN_ID",""),
                        binary_sha256=digest(gf2 if mode=="r28_gf2" else kissat))
                    rows.append(row)
                    print("R81D_TRIAL",json.dumps({k:row[k] for k in
                        ("source_id","rep","mode","answer","end_to_end_s",
                         "par2_s","route","added","r81d_source_equations")}),flush=True)
    check(len(rows)==len(manifest["cases"][args.shard::SHARDS])*REPS*len(MODES),
          "incomplete measurement shard")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"r81d-shard.json").write_text(json.dumps(dict(
        protocol=PROTO,shard=args.shard,source_manifest_sha256=digest(root/"manifest.json"),
        binaries=dict(kissat=digest(kissat),r28_gf2=digest(gf2)),
        cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:2400],
        rows=rows),indent=2)+"\n")
    print("R81D_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    root=Path(args.sources)
    manifest=load_sources(root)
    cases={x["sha256"]:x for x in manifest["cases"]}
    rows=[];pins=[];cpus=[]
    for shard in range(SHARDS):
        path=Path(args.combined)/f"r81d-shard-{shard}"/"results"/"r81d-shard.json"
        check(path.is_file(),"missing shard "+str(shard))
        d=json.loads(path.read_text())
        check(d["protocol"]==PROTO and d["shard"]==shard and
              d["source_manifest_sha256"]==digest(root/"manifest.json"),
              "shard mismatched input sources")
        check(len(d["rows"])==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
              "incomplete shard")
        pins.append(tuple(sorted(d["binaries"].items())))
        cpus.append(dict(shard=shard,cpu=d["cpu"].splitlines()[:10]))
        rows.extend(d["rows"])
    check(len(rows)==16*REPS*len(MODES) and len(set(pins))==1,
          "incomplete 192 trials or binary drift")
    paired=collections.defaultdict(list)
    for row in rows:
        check(row["source_sha256"] in cases and
              row["runner"] and row["commit"] and
              row["rep"] in range(REPS) and
              row["source_id"]==cases[row["source_sha256"]]["gbd"],
              "trial source/provenance mismatch")
        paired[(row["source_sha256"],row["rep"])].append(row)
    check(len(paired)==16*REPS,"unpaired source/seed")
    # Independent source-premise audit of every actual R81D lemma.
    cnf_cache={}
    proof_count=0;active_count=0
    for (sha,rep),group in paired.items():
        check(len(group)==len(MODES) and
              {r["mode"] for r in group}==set(MODES),
              "missing paired method")
        verdicts={r["answer"] for r in group if r["answer"]!="UNKNOWN"}
        check(len(verdicts)<=1,"contradictory solver answers")
        src=root/cases[sha]["filename"]
        for r in group:
            if r["mode"]=="r81c_exact":
                if r["r81c_route"]=="gf2_sat_model_verified":
                    check(r["answer"]=="SAT" and r81c.verify_sat_model(
                        src,int(r["r81c_model_hex"],16),cases[sha]["variables"]),
                        "R81C original SAT model rejected")
                if r["r81c_route"]=="gf2_unsat_certified":
                    check(r["answer"]=="UNSAT" and r81c.verify_unsat_certificate(
                        src,r["r81c_proof"]),"R81C UNSAT certificate rejected")
            if r["mode"] not in ("r81d_passive","r81d_active"):continue
            certs=r["r81d_certificates"] or []
            if certs and sha not in cnf_cache:
                _,cnf=r81d.r28.load_clauses(src)
                cnf_cache[sha]=cnf
            for cert in certs:
                check(r81d.verified_row_witness(
                    cnf_cache[sha],cert["proof"],cert["vs"],cert["rhs"]),
                    "R81D derived clause proof invalid on ORIGINAL CNF")
                check(tuple(cert["clause"]) in {
                    tuple(c) for c in r81d._clauses_from_row(cert["vs"],cert["rhs"])},
                    "R81D claimed clause does not follow from proved XOR row")
                proof_count+=1
            if r["mode"]=="r81d_active":
                check(r["added"]==len(certs),"R81D active lemma/proof count mismatch")
                active_count+=bool(r["added"])
    summary={}
    for mode in MODES:
        arr=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(solved=sum(r["solved"] for r in arr),
            attempts=len(arr),par2_s=round(sum(r["par2_s"] for r in arr),6),
            added=sum(r["added"] for r in arr))
    formula_totals=collections.defaultdict(lambda:collections.defaultdict(float))
    paired_export=[]
    for (sha,rep),group in sorted(paired.items()):
        record=dict(source_id=cases[sha]["gbd"],source_sha256=sha,rep=rep,
                    group=cases[sha]["group"])
        record.update({r["mode"]:r["par2_s"] for r in group})
        paired_export.append(record)
        for r in group:formula_totals[sha][r["mode"]]+=r["par2_s"]
    rng=random.Random(8104)
    bootstrap=[]
    items=list(formula_totals.values())
    for _ in range(5000):
        chosen=[items[rng.randrange(len(items))] for _ in items]
        base=sum(x["clean_kissat"] for x in chosen)
        new=sum(x["r81d_active"] for x in chosen)
        bootstrap.append(100*(base-new)/base)
    bootstrap.sort()
    ci=[round(bootstrap[int(0.025*len(bootstrap))],5),
        round(bootstrap[int(0.975*len(bootstrap))],5)]
    routes=dict(collections.Counter(r["route"] for r in rows
                if r["mode"] in ("r81d_passive","r81d_active")))
    report=dict(protocol=PROTO,status="PASS_UNOFFICIAL_EXPLORATORY_REPLAY",
        official_competition_score=False,
        new_blind_holdout=False,
        source_count=16,trial_count=len(rows),repeats=REPS,cap_s=CAP,
        source_manifest_sha256=digest(root/"manifest.json"),
        binary_sha256=dict(pins[0]),proofs_independently_verified=proof_count,
        active_interventions=active_count,route_counts=routes,summary=summary,
        bootstrap_formula_ci_gain_over_kissat_pct=ci,paired=paired_export,
        cpus=cpus,rows=rows,
        limitations=[
            "Retrospective mechanism replay on 16 formerly blind SATComp2025 originals after R81C analysis",
            "R81D uses separate pre-processing and adds short certified clauses; NOT in-process live XOR/CDCL communication",
            "Verified original SAT models; UNSAT from Kissat without third-party proof is provisional",
            "A sound learned clause can alter CDCL decisions and cause regressions",
            "Host CPU class and GitHub environment variability may influence small timing differences",
            "No solver was selected based on timing results for this R81D run"])
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"r81d-final.json").write_text(json.dumps(report,indent=2)+"\n")
    with (out/"paired.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["source_id","source_sha256","rep","group"]+list(MODES))
        writer.writeheader();writer.writerows(paired_export)
    md=["# DRNAS R81D certified partial XOR/CDCL — exploratory replay",
        "16 SHA-pinned original official SATCompetition2025 formulas × 2 repeats × 6 methods = 192 native trials.",
        "30s cap; PAR-2; source selection predates R81D but is no longer blind.",
        f"Verified {proof_count} original-CNF clause derivation certificates, {active_count} active attempts with new lemmas.",
        f"R81D route counts: {routes}",
        f"95% bootstrap by formula: {ci} percentage points gain vs Kissat.","",
        "| Method | Solved/32 | PAR-2 (s) | Added clauses |",
        "|---|---:|---:|---:|"]
    for method,vals in summary.items():
        md.append(f"| {method} | {vals['solved']} | {vals['par2_s']:.6f} | {vals['added']} |")
    md+=["","## Limitations"]+["- "+s for s in report["limitations"]]
    (out/"r81d-final.md").write_text("\n".join(md)+"\n")
    print("R81D_FINAL_AUDIT_PASS",json.dumps(dict(trials=len(rows),
        summary=summary,route_counts=routes,proofs_verified=proof_count,
        active_interventions=active_count,bootstrap_ci=ci)),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    measure_parser=sub.add_parser("measure")
    for key in ("sources","binaries","out"):measure_parser.add_argument("--"+key,required=True)
    measure_parser.add_argument("--shard",type=int,required=True)
    audit_parser=sub.add_parser("audit")
    for key in ("sources","combined","out"):audit_parser.add_argument("--"+key,required=True)
    args=p.parse_args()
    if args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":main()
