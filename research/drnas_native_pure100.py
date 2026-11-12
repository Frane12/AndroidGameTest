#!/usr/bin/env python3
"""DRNAS PURE NATIVE 100: 100 original SAT2024 CNFs, 3s/5s, no reference solvers.

Only locally built DRNAS native CDCL binaries:
  LTM8_FAST, LTM8_CHAOS, LTM9_FAST (LTM9 native + PHP counting certificate).
NO Kissat, CaDiCaL, CMS, hybrid, router, or fallback. One logical CPU, serial.
SAT models independently verified on ORIGINAL CNF. UNSAT gets verified PAR2
credit ONLY if original-CNF PHP counting certificate is independently checked.
Reused SAT2024 archive (NOT globally blind). Source selection is outcome-free.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import statistics
import time

import drnas_ltm11_real2 as B

ROOT=pathlib.Path("drnas_native_pure100")
ARMS=("LTM8_FAST","LTM8_CHAOS","LTM9_FAST")
SEED=17

def emit(label,data):
    print(label+" "+json.dumps(data,sort_keys=True,separators=(",",":")),flush=True)

def features(source):
    n=B.nvars(source["path"])
    size=pathlib.Path(source["path"]).stat().st_size
    return dict(nvars=n,bytes=size)

def prepare(sources):
    if len(sources)!=100:raise RuntimeError("expected 100 original CNFs")
    enriched=[dict(s,**features(s)) for s in sources]
    if len({s["sha256"] for s in enriched})!=100:raise RuntimeError("duplicate source")
    if len({s["normalized_name_family"] for s in enriched})!=100:raise RuntimeError("family duplicate")
    ordered=sorted(enriched,key=lambda s:(s["nvars"],s["bytes"],s["sha256"]))
    # Quantile split, fixed before seeing any outcome: 50 cases at 3s, 50 at 5s.
    # All three native variants get the exact same per-source limit.
    for i,s in enumerate(ordered):
        s["group"]="small" if i<50 else "medium_large"
        s["cap_s"]=3.0 if i<50 else 5.0
    return ordered

def score(rows):
    byarm={}
    for arm in ARMS:
        trials=[r for r in rows if r["arm"]==arm]
        byarm[arm]=dict(
            trials=len(trials),
            SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in trials),
            UNSAT_math_certified=sum(r["status"]=="UNSAT_MATH_CERTIFIED" for r in trials),
            UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in trials),
            UNKNOWN=sum(r["status"]=="UNKNOWN" for r in trials),
            solved_verified=sum(r["verified"] for r in trials),
            PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in trials),6),
            PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in trials),6),
            e2e_s=round(sum(r["e2e_s"] for r in trials),6),
            decisions_sum=sum(r["decisions"] or 0 for r in trials),
            conflicts_sum=sum(r["conflicts"] or 0 for r in trials),
            trials_with_cdcl_counters=sum(r["decisions"] is not None for r in trials))
    return byarm

def compare(rows):
    totals=score(rows)
    best=min(ARMS,key=lambda a:totals[a]["PAR2_verified_s"])
    paired={(r["id"],r["arm"]):r for r in rows}
    changes={}
    for arm in ARMS:
        if arm==best:continue
        part=[r for r in rows if r["arm"]==arm]
        improvements=sum(r["PAR2_verified_s"]+0.002<paired[(r["id"],best)]["PAR2_verified_s"] for r in part)
        regressions=sum(r["PAR2_verified_s"]>1.1*paired[(r["id"],best)]["PAR2_verified_s"]+0.002 for r in part)
        changes[arm]=dict(
            speedup_best_over_arm_x=round(totals[arm]["PAR2_verified_s"]/max(totals[best]["PAR2_verified_s"],1e-9),5),
            improvements=improvements,regressions_over_10pct=regressions)
    return dict(best_native=best,totals=totals,comparisons=changes)

def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as td:
        p=pathlib.Path(td)/"test.cnf"
        p.write_text("p cnf 3 2\n1 2 0\n-2 3 0\n")
        assert B.sat_witness_valid(p,3,"v 1 -2 3 0\n")
        assert not B.sat_witness_valid(p,3,"v -1 -2 -3 0\n")
        for arm in ARMS:
            command=B.command(arm,p,17,3)
            assert command[0].startswith("mre_atlas23/bin/drnas_"),command
            assert not any("kissat" in part.lower() or "cadical" in part.lower() or "cryptominisat" in part.lower() for part in command)
    emit("PURE100_SELFTEST_PASS",dict(arms=ARMS,pure_native=True,original_CNF_validation=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=False)
    B.ROOT=ROOT/"source_archive"
    sources=prepare(B.collect())
    (ROOT/"selection.json").write_text(json.dumps(dict(
        archive=B.ARCHIVE,selection="100 original SAT2024, variable-count median split",
        caps=dict(first_50=3.0,last_50=5.0),
        arms=ARMS,reference_solvers=0,hybrid_fallbacks=0,
        original_CNF_SHA=[s["sha256"] for s in sources],
        prior_archive_seen=True,globally_blind=False),indent=2)+"\n")
    rows=[]
    with (ROOT/"trials.jsonl").open("w") as out:
        for i,source in enumerate(sources):
            # Rotate order to reduce temporal/thermal bias.
            rotated=list(ARMS);offset=i%len(rotated)
            for arm in rotated[offset:]+rotated[:offset]:
                start=time.monotonic()
                cap=source["cap_s"]
                result=B.run_solver(arm,source,SEED,max(.1,cap-.08))
                elapsed=time.monotonic()-start
                if elapsed>cap:
                    result.update(status="UNKNOWN",verified=False,php_math_certified=False)
                result.update(arm=arm,cap_s=cap,e2e_s=round(elapsed,6),
                              group=source["group"],nvars=source["nvars"],
                              original_cnf_sha256=source["sha256"],
                              source_file=source["source_file"])
                result=B.with_metrics(result,cap)
                rows.append(result)
                out.write(json.dumps(result,sort_keys=True)+"\n");out.flush()
                emit("PURE100_TRIAL",dict(id=source["id"],group=source["group"],
                     nvars=source["nvars"],arm=arm,status=result["status"],
                     e2e_s=result["e2e_s"],PAR2_verified_s=result["PAR2_verified_s"],
                     decisions=result["decisions"],conflicts=result["conflicts"]))
            if (i+1)%10==0:
                emit("PURE100_PROGRESS",dict(completed=i+1,total=100,
                    partial=compare(rows)))
    B.check_contradictions(rows)
    result=compare(rows)
    result.update(
        source_count=100,trials=300,
        groups={g:compare([r for r in rows if r["group"]==g])
                for g in ("small","medium_large")},
        one_logical_cpu=True,original_CNF_verification=True,
        independent_PHP_UNSAT_certificate=True,
        globally_blind=False,no_reference_or_fallback=True)
    (ROOT/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("PURE100_FINAL",result)

if __name__=="__main__":main()
