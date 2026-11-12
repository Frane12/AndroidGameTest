#!/usr/bin/env python3
"""DRNAS S6 DIVERSE REAL20: longer-cap original CNF, paired solver cascades.

20 SAT Competition 2024 original CNFs selected from the pre-existing 100-family
pool using ONLY source variable-count and byte-size, before solving; no outcome
filtering. Reuses the original S5/S2 runners. 8 low-variable, 7 medium, 5 high
variable CNFs; per-source cap 15/15/25 s respectively, IDENTICAL across arms.
Six short synthetic controls (3 s) from previously prepared generators.

All successful SAT results are checked against original CNF by B.run_solver or
D.shortcut. Unverified UNSAT never earns verified PAR2 credit.
This is exploratory: archive and generator families have been seen previously.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import statistics
import time

import drnas_s5_cascade as S5

B=S5.B
S2=S5.S2
ROOT=pathlib.Path("drnas_s6_diverse")
ARMS=("S6_CMS_KISSAT","S6_KISSAT_CMS","Kissat","CryptoMiniSat","CaDiCaL")
REFS=("Kissat","CryptoMiniSat","CaDiCaL")
SEED=17
CAPS={"small":15.0,"medium":15.0,"large":25.0}
SYNTH_CAP=3.0

def emit(label, obj):
    print(label+" "+json.dumps(obj,separators=(",",":"),sort_keys=True),flush=True)

def source_features(source):
    path=pathlib.Path(source["path"])
    n=B.nvars(path)
    raw_bytes=path.stat().st_size
    return dict(nvars=n,bytes=raw_bytes)

def quantiles(items,k):
    if len(items)<k:raise RuntimeError(f"insufficient entries {len(items)}<{k}")
    positions=[min(len(items)-1,(2*i+1)*len(items)//(2*k)) for i in range(k)]
    assert len(set(positions))==k
    return [items[i] for i in positions]

def official_selection(sources):
    """Source-only stratification, not benchmark-outcome-based cherry-picking."""
    enriched=[dict(s,**source_features(s)) for s in sources]
    enriched.sort(key=lambda s:(s["nvars"],s["bytes"],s["sha256"]))
    if len(enriched)!=100:raise RuntimeError("100 original SAT2024 sources required")
    groups={"small":enriched[:33],"medium":enriched[33:66],"large":enriched[66:]}
    # Favor small original CNFs in first band, spread across sizes elsewhere.
    chosen={}
    chosen["small"]=sorted(groups["small"],key=lambda s:(s["bytes"],s["sha256"]))[:8]
    chosen["medium"]=quantiles(groups["medium"],7)
    chosen["large"]=quantiles(groups["large"],5)
    out=[]
    for group in ("small","medium","large"):
        for source in chosen[group]:
            out.append(dict(source,size_group=group,cap_s=CAPS[group]))
    if len(out)!=20 or len({s["sha256"] for s in out})!=20:
        raise RuntimeError("invalid/duplicate 20-source selection")
    if len({s["normalized_name_family"] for s in out})!=20:
        raise RuntimeError("family leakage")
    return out

def run_one(arm,source,seed,cap):
    started=time.monotonic()
    path=pathlib.Path(source["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source["sha256"]:
        raise RuntimeError("original CNF changed")
    attempts=[]
    operator=None
    if arm in REFS:
        stages=[(arm,1.0)]
    else:
        # Fast math is sound only when a FULL satisfying assignment is
        # independently checked on original CNF.
        if path.stat().st_size<=64*1024 and B.nvars(path)<=512:
            operator=S2.D.shortcut(path)
        if operator is not None:
            row=dict(status="SAT_VERIFIED",verified=True,php_math_certified=False,
                     decisions=0,conflicts=0)
            return finalize(row,arm,source,seed,cap,started,operator,attempts)
        if arm=="S6_CMS_KISSAT":
            stages=[("CryptoMiniSat",.72),("Kissat",1.0)]
        elif arm=="S6_KISSAT_CMS":
            stages=[("Kissat",.18),("CryptoMiniSat",1.0)]
        else:
            raise ValueError(arm)
    row=dict(status="UNKNOWN",verified=False,php_math_certified=False,
             decisions=None,conflicts=None)
    for i,(name,fraction) in enumerate(stages):
        remaining=cap-(time.monotonic()-started)-.14
        if remaining<=.23:break
        budget=remaining
        if i==0 and len(stages)>1:
            budget=min(remaining,cap*fraction)
        result=B.run_solver(name,source,seed,budget)
        attempts.append(dict(solver=name,cap_s=round(budget,4),
                             e2e_s=result["e2e_s"],status=result["status"],
                             verified=result["verified"]))
        row=result
        if result["verified"]:
            break
    return finalize(row,arm,source,seed,cap,started,operator,attempts)

def finalize(row,arm,source,seed,cap,started,operator,attempts):
    elapsed=time.monotonic()-started
    if row["status"] in ("ERROR","INVALID_SAT"):
        raise RuntimeError(f"invalid solver result source={source['id']} arm={arm}")
    if elapsed>cap:
        row.update(status="UNKNOWN",verified=False,php_math_certified=False)
    row.update(arm=arm,id=source["id"],seed=seed,split=source["split"],
               original_cnf_sha256=source["sha256"],cap_s=cap,
               e2e_s=round(elapsed,6),
               math_operator=operator,solver_attempts=attempts,
               second_solver_attempted=len(attempts)>1,
               first_solver_solved=len(attempts)==1 and attempts[0]["verified"])
    row=B.with_metrics(row,cap)
    if source.get("known_sat") and row["status"].startswith("UNSAT"):
        raise RuntimeError("reference UNSAT contradicts independently verified planted SAT")
    return row

def metrics(rows):
    out={}
    for arm in ARMS:
        part=[r for r in rows if r["arm"]==arm]
        out[arm]=dict(trials=len(part),
                     solved=sum(r["verified"] for r in part),
                     SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in part),
                     UNSAT_math_certified=sum(r["status"]=="UNSAT_MATH_CERTIFIED" for r in part),
                     UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in part),
                     PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in part),6),
                     PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in part),6),
                     e2e_s=round(sum(r["e2e_s"] for r in part),6),
                     math_shortcuts=sum(r["math_operator"] is not None and r["verified"] for r in part),
                     second_stage=sum(r["second_solver_attempted"] for r in part),
                     second_stage_solved=sum(r["second_solver_attempted"] and r["verified"] for r in part))
    return out

def analyze(rows):
    total=metrics(rows)
    best=min(REFS,key=lambda a:total[a]["PAR2_verified_s"])
    pair={(r["id"],r["seed"],r["arm"]):r for r in rows}
    comparisons={}
    for arm in ("S6_CMS_KISSAT","S6_KISSAT_CMS"):
        cost=total[arm]["PAR2_verified_s"];ref=total[best]["PAR2_verified_s"]
        candidate=[r for r in rows if r["arm"]==arm]
        deltas=[r["PAR2_verified_s"]-pair[(r["id"],r["seed"],best)]["PAR2_verified_s"] for r in candidate]
        comparisons[arm]=dict(
            speedup_x=round(ref/max(cost,1e-9),5),
            PAR2_reduction_pct=round(100*(1-cost/max(ref,1e-9)),3),
            regressions_over_10pct=sum(
                r["PAR2_verified_s"]>1.10*pair[(r["id"],r["seed"],best)]["PAR2_verified_s"]+.002
                for r in candidate),
            improved_cases=sum(d<-.002 for d in deltas),
            mean_delta_s=round(statistics.mean(deltas),5))
    return dict(best_reference=best,totals=total,comparisons=comparisons)

def paired(root,sources,kind):
    root.mkdir(parents=True,exist_ok=False)
    rows=[]
    (root/"selection.json").write_text(json.dumps(dict(
        dataset=kind,official=(kind=="SAT2024 original"),
        prior_archive_used=True,globally_blind=False,
        selected=[dict(id=s["id"],sha=s["sha256"],nvars=s["nvars"],
                       bytes=s["bytes"],group=s["size_group"],cap=s["cap_s"])
                  for s in sources]),indent=2)+"\n")
    with (root/"trials.jsonl").open("w") as handle:
        for i,source in enumerate(sources):
            order=list(ARMS)
            p=i%len(order)
            for arm in order[p:]+order[:p]:
                row=run_one(arm,source,SEED,source["cap_s"])
                row.update(size_group=source["size_group"],nvars=source["nvars"],
                           family=source.get("normalized_name_family",source.get("family","unknown")))
                rows.append(row)
                handle.write(json.dumps(row,sort_keys=True)+"\n");handle.flush()
                emit("S6_TRIAL",dict(dataset=kind,group=source["size_group"],
                     id=source["id"],arm=arm,status=row["status"],
                     e2e_s=row["e2e_s"],PAR2_verified_s=row["PAR2_verified_s"],
                     cascade=row["second_solver_attempted"]))
            emit("S6_PROGRESS",dict(dataset=kind,completed=i+1,total=len(sources)))
    B.check_contradictions(rows)
    overall=analyze(rows)
    overall.update(dataset=kind,source_count=len(sources),
                   one_logical_cpu=True,source_only_selection=True,
                   globally_blind=False,
                   groups={g:analyze([r for r in rows if r["size_group"]==g])
                           for g in sorted({r["size_group"] for r in rows})})
    (root/"report.json").write_text(json.dumps(overall,indent=2,sort_keys=True)+"\n")
    emit("S6_"+("OFFICIAL" if kind=="SAT2024 original" else "SYNTH")+"_FINAL",overall)
    return overall

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"tiny.cnf"
        p.write_text("p cnf 3 3\n1 2 0\n-2 3 0\n-3 0\n")
        s=dict(id=0,path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
               split="holdout",known_sat=True)
        assert B.sat_witness_valid(p,3,"v 1 -2 -3 0\n")==False
        assert B.sat_witness_valid(p,3,"v 1 -2 3 0\n")
        assert len(quantiles(list(range(12)),5))==5
        for arm in ARMS:
            assert arm in REFS or arm.startswith("S6_")
    emit("S6_SELFTEST_PASS",dict(original_witness=True,source_only_selection=True,
                                 stage_budgets_monotonic=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--seed",type=int,default=620261112)
    parser.add_argument("--skip-official",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=False)
    synth=S2.build_synthetic(ROOT/"prepared_synthetic",args.seed)
    subs=[s for s in synth if s["id"] in (0,3,7,9,15,18)]
    assert len(subs)==6
    synthetic=[dict(s,size_group="control",cap_s=SYNTH_CAP,
                    nvars=s["nvars"],bytes=pathlib.Path(s["path"]).stat().st_size)
               for s in subs]
    result={"synthetic":paired(ROOT/"synthetic",synthetic,"reused synthetic SAT")}
    if not args.skip_official:
        B.ROOT=ROOT/"official_sources"
        selected=official_selection(B.collect())
        result["official"]=paired(ROOT/"official",selected,"SAT2024 original")
    summary={name:dict(reference=r["best_reference"],
        verified_PAR2={arm:m["PAR2_verified_s"] for arm,m in r["totals"].items()},
        solved={arm:m["solved"] for arm,m in r["totals"].items()},
        comparisons=r["comparisons"]) for name,r in result.items()}
    (ROOT/"combined.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    emit("S6_FINAL",dict(datasets=summary,
         note="longer-cap exploratory SAT2024; not globally blind; one CPU; no APK"))
if __name__=="__main__":main()
