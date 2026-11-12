#!/usr/bin/env python3
"""DRNAS S5: proof-checked source shortcut + budget-aware serial solver cascade.

Small, controlled exploratory test with 20 original SAT Competition 2024 CNFs
and 8 reused planted SAT cases. No outcome-based source selection or routing.
All claimed SAT answers must verify on ORIGINAL CNF. Unverified UNSAT is NOT a
verified solve. No claim of globally blind performance or proof generality.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import tempfile
import time

import drnas_selective_reduce_s2_mid as S2

B=S2.B
ROOT=Path("drnas_s5_cascade")
ARMS=("S5_DIRECT","S5_KC","S5_KM","Kissat","CaDiCaL","CryptoMiniSat")
REFERENCE=("Kissat","CaDiCaL","CryptoMiniSat")
SYNTH_CAP=1.5
OFFICIAL_CAP=4.0
MAX_MATH_BYTES=64*1024
SEED=17

def emit(event,obj):
    print(event+" "+json.dumps(obj,separators=(",",":"),sort_keys=True),flush=True)

def cheap_features(path):
    """Fixed source-only cost-aware gate: header, byte size, first 48 clauses."""
    size=path.stat().st_size
    n=B.nvars(path)
    clause=0;done=0;binary=0;ternary=0
    if size<=256*1024:
        with path.open("r",encoding="ascii",errors="replace") as file:
            for raw in file:
                line=raw.strip()
                if not line or line.startswith(("c","p ","%")):continue
                for field in line.split():
                    if int(field):
                        clause+=1
                    else:
                        done+=1
                        binary+=int(clause<=2)
                        ternary+=int(clause==3)
                        clause=0
                    if done>=48:break
                if done>=48:break
    return dict(nvars=n,bytes=size,sampled_clauses=done,
                binary_sample=binary,ternary_sample=ternary)

def preset_path(arm,features,cap):
    """No results, SHA, labels, filenames, cohorts or IDs are prediction inputs."""
    if arm=="S5_DIRECT":
        if features["nvars"]>=300:return [("Kissat",1.0)]
        return [("CaDiCaL",1.0)]
    if arm=="S5_KC":
        return [("Kissat",.18),("CaDiCaL",1.0)]
    if arm=="S5_KM":
        return [("Kissat",.18),("CryptoMiniSat",1.0)]
    raise ValueError(arm)

def final(row,arm,source,seed,cap,started,**telemetry):
    e2e=time.monotonic()-started
    if row["status"] in ("ERROR","INVALID_SAT"):
        raise RuntimeError(f"{arm} invalid solution source {source['id']}")
    if e2e>cap:
        row.update(status="UNKNOWN",verified=False,php_math_certified=False)
    row.update(id=source["id"],arm=arm,split=source["split"],seed=seed,
               e2e_s=round(e2e,6),cap_s=cap,
               original_cnf_sha256=source["sha256"],**telemetry)
    row=B.with_metrics(row,cap)
    if source.get("known_sat") and row["status"].startswith("UNSAT"):
        raise RuntimeError("unverified UNSAT contradicts planted SAT source")
    return row

def empty():
    return dict(status="UNKNOWN",verified=False,php_math_certified=False,
                conflicts=None,decisions=None)

def run_arm(arm,source,seed,cap):
    started=time.monotonic()
    if arm in REFERENCE:
        remaining=max(.20,cap-.12)
        row=B.run_solver(arm,source,seed,remaining)
        return final(row,arm,source,seed,cap,started,solver_path=[arm],
                     math_operator=None,early_abstain=False,
                     attempts=1,unverified_unsat_seen=0)
    path=Path(source["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source["sha256"]:
        raise RuntimeError("SHA mismatch on original CNF")
    f=cheap_features(path)
    operator=None;shortcut_s=0.0
    if f["bytes"]<=MAX_MATH_BYTES and f["nvars"]<=512:
        t=time.monotonic()
        operator=S2.D.shortcut(path)  # independently checks complete witness
        shortcut_s=time.monotonic()-t
    if operator is not None:
        return final(dict(status="SAT_VERIFIED",verified=True,php_math_certified=False,
                          conflicts=0,decisions=0),
                     arm,source,seed,cap,started,
                     solver_path=[],math_operator=operator,early_abstain=False,
                     attempts=0,shortcut_s=round(shortcut_s,6),
                     unverified_unsat_seen=0)
    stages=preset_path(arm,f,cap)
    attempted=[]
    unknown_unsat=0
    row=empty()
    for idx,(solver,fraction) in enumerate(stages):
        available=cap-(time.monotonic()-started)-.12
        if available<=.20:break
        # Reserve most of the budget for the second solver, if present.
        budget=min(available,max(.20,cap*fraction)) if idx==0 and len(stages)>1 else available
        sub=B.run_solver(solver,source,seed,budget)
        attempted.append(dict(solver=solver,status=sub["status"],e2e_s=sub["e2e_s"]))
        unknown_unsat+=int(sub["status"]=="UNSAT_UNVERIFIED")
        row=sub
        if sub["verified"]:
            break
    return final(row,arm,source,seed,cap,started,
                 solver_path=[a["solver"] for a in attempted],
                 solver_attempts=attempted,math_operator=None,
                 early_abstain=len(attempted)==0,
                 attempts=len(attempted),
                 shortcut_s=round(shortcut_s,6),
                 unverified_unsat_seen=unknown_unsat)

def stats(rows,cap,arms=ARMS):
    totals=B.metrics(rows,cap,arms)
    best=min(REFERENCE,key=lambda a:totals[a]["PAR2_verified_s"])
    comparison={}
    paired={(r["id"],r["seed"],r["arm"]):r for r in rows}
    for arm in arms:
        if arm in REFERENCE:continue
        rs=[r for r in rows if r["arm"]==arm]
        b=totals[best]["PAR2_verified_s"];t=totals[arm]["PAR2_verified_s"]
        comparison[arm]=dict(
            gain_pct=round(100*(1-t/max(b,1e-9)),3),
            speedup_x=round(b/max(t,1e-9),5),
            new_solved=totals[arm]["SAT_verified"]+totals[arm]["UNSAT_math_certified"],
            reference_solved=totals[best]["SAT_verified"]+totals[best]["UNSAT_math_certified"],
            math_shortcut_solved=sum(r["math_operator"] is not None and r["verified"] for r in rs),
            first_solver_only=sum(r["attempts"]==1 and r["verified"] for r in rs),
            two_stage_attempts=sum(r["attempts"]==2 for r in rs),
            regressions_10pct=sum(
                r["PAR2_verified_s"]>paired[(r["id"],r["seed"],best)]["PAR2_verified_s"]*1.1+.002
                for r in rs),
            unverified_unsat_events=sum(r.get("unverified_unsat_seen",0) for r in rs))
    return dict(best_reference=best,totals=totals,candidates=comparison,
                one_logical_cpu=True,original_cnf_verification=True)

def write_row(fd,row):
    fd.write(json.dumps(row,sort_keys=True)+"\n");fd.flush()

def synthetic(root,seed):
    sources=S2.build_synthetic(root,seed)
    # Fixed stratification among existing 20, not chosen based on outcomes.
    chosen=[s for s in sources if s["id"] in (0,2,4,6,8,10,16,18)]
    assert len(chosen)==8
    rows=[]
    with (root/"trials.jsonl").open("w") as fd:
        for source in chosen:
            rotated=list(ARMS);k=source["id"]%len(ARMS)
            for arm in rotated[k:]+rotated[:k]:
                row=run_arm(arm,source,SEED,SYNTH_CAP)
                row.update(group=source["family"],tier=source["tier"],
                           nvars=source["nvars"])
                rows.append(row);write_row(fd,row)
    B.check_contradictions(rows)
    out=stats(rows,SYNTH_CAP)
    out.update(dataset="reused synthetic planted SAT",source_count=8,
               cap_s=SYNTH_CAP,exploratory=True)
    (root/"report.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    emit("S5_SYNTH_FINAL",out)
    return out

def official(root):
    root.mkdir(parents=True,exist_ok=False)
    B.ROOT=root
    sources=B.collect()
    # Purely compressed-size independent source selection: 14 smallest raw
    # plus 6 spread across the remaining 100-family pool.
    pool=sorted(sources,key=lambda s:(s["bytes"],s["sha256"]))
    front=pool[:14]
    tail=pool[14:]
    indices=[min(len(tail)-1,(2*i+1)*len(tail)//12) for i in range(6)]
    selected=front+[tail[i] for i in indices]
    assert len(selected)==20 and len({x["sha256"] for x in selected})==20
    (root/"selection.json").write_text(json.dumps(dict(
        archive=B.ARCHIVE,policy="14 smallest original bytes + 6 spread quantiles",
        source_count=len(selected),source_SHA=[x["sha256"] for x in selected],
        source_family_disjoint_heuristic=True,
        no_result_based_selection=True,prior_archive_usage=True,
        globally_blind=False,cap_s=OFFICIAL_CAP),indent=2)+"\n")
    rows=[]
    with (root/"trials.jsonl").open("w") as fd:
        for idx,source in enumerate(selected):
            feature=cheap_features(Path(source["path"]))
            rotated=list(ARMS);k=idx%len(ARMS)
            for arm in rotated[k:]+rotated[:k]:
                row=run_arm(arm,source,SEED,OFFICIAL_CAP)
                row.update(nvars=feature["nvars"],bytes=source["bytes"],
                           family=source["normalized_name_family"],
                           compressed_bytes=source["compressed_bytes"])
                rows.append(row);write_row(fd,row)
                emit("S5_OFFICIAL_TRIAL",dict(id=source["id"],arm=arm,
                     status=row["status"],PAR2_verified_s=row["PAR2_verified_s"],
                     math_operator=row.get("math_operator"),
                     solvers=row.get("solver_path")))
            emit("S5_OFFICIAL_PROGRESS",dict(completed=idx+1,total=20))
    B.check_contradictions(rows)
    out=stats(rows,OFFICIAL_CAP)
    out.update(dataset="SAT Competition 2024 ORIGINAL CNFs",source_count=20,
               cap_s=OFFICIAL_CAP,global_blind=False,
               validation_note="original CNFs; reused public archive and prior observations",
               size_buckets={
                   "smallest14":stats([r for r in rows if r["id"] in {s["id"] for s in front}],OFFICIAL_CAP),
                   "spread6":stats([r for r in rows if r["id"] in {s["id"] for s in selected[14:]}],OFFICIAL_CAP)
               })
    (root/"report.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    emit("S5_OFFICIAL_FINAL",out)
    return out

def selftest():
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory)/"cnf.cnf"
        p.write_text("p cnf 3 4\n1 2 3 0\n1 -2 -3 0\n-1 2 -3 0\n-1 -2 3 0\n")
        f=cheap_features(p)
        assert f["nvars"]==3
        assert preset_path("S5_DIRECT",f,4)==[("CaDiCaL",1.0)]
        assert preset_path("S5_KC",f,4)[1][0]=="CaDiCaL"
        assert S2.D.shortcut(p)=="gf2_elimination"
        assert B.sat_witness_valid(p,3,"v 1 1 1 0\n")==False
        assert B.sat_witness_valid(p,3,"v -1 -2 -3 0\n")
        p.write_text("p cnf 3 2\n1 2 0\n-2 3 0\n")
        assert B.sat_witness_valid(p,3,"v 1 -2 3 0\n")
    emit("S5_SELFTEST_PASS",dict(original_cnf_witness=True,source_only_router=True,
                                 complete_xor_shortcut=True,serial_stage_cap=True))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--seed",type=int,default=520261112)
    p.add_argument("--skip-official",action="store_true")
    args=p.parse_args()
    if args.selftest:
        selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=False)
    results={"synthetic":synthetic(ROOT/"synthetic",args.seed)}
    if not args.skip_official:
        results["official"]=official(ROOT/"official")
    summary={
        k:dict(best_reference=v["best_reference"],
               PAR2={a:m["PAR2_verified_s"] for a,m in v["totals"].items()},
               solved={a:m["SAT_verified"]+m["UNSAT_math_certified"] for a,m in v["totals"].items()},
               candidate=v["candidates"]) for k,v in results.items()}
    (ROOT/"combined.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    emit("S5_FINAL",dict(exploratory=True,sets=summary,
                          goal_30pct_status={k:{a:d["gain_pct"]>=30 for a,d in v["candidates"].items()}
                          for k,v in results.items()}))
if __name__=="__main__":main()
