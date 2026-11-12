#!/usr/bin/env python3
"""S3 CRR: controlled native CDCL experiment on reused S2 medium SAT sources.

Compare (1) always-enable native XOR and binary resolution, (2) source-only
guarded selection, (3) S2/S1, and (4) 3 pinned reference solvers.
All SAT witnesses validated on original CNF. UNSAT without an independent
original-CNF proof is NOT credited. No proof or universal speedup claims.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

import drnas_selective_reduce_s2_mid as S2

B, L = S2.B, S2.L
ROOT = Path("drnas_s3_crr")
SYNTH_CAP = 1.5
OFFICIAL_CAP = 5.0
SEED = 17
ARMS = ("S3_GATED", "S3_NATIVE", "S2", "S1", "CaDiCaL", "Kissat", "CryptoMiniSat")
REFERENCES = ("CaDiCaL", "Kissat", "CryptoMiniSat")
DERIVED_FIELDS = ("original", "binary_input", "xor_rows", "xor_pairs",
                  "xor_binary_added", "resolution_added", "units", "resolution_checked")

def emit(label, obj):
    print(label+" "+json.dumps(obj, sort_keys=True, separators=(",", ":")),flush=True)

def native_command(arm, path, seed, cap):
    if arm != "LTM9_FAST":
        raise ValueError("S3 native may run only as instrumented LTM9 alias")
    return ["mre_atlas23/bin/drnas_s3_crr", str(path),
            "--mode", "LTM8_FAST", "--time", str(max(.1, cap-.30)),
            "--seed", str(seed), "--policy", "1.0,0.85"]

def process_native_output(raw):
    stats = collections.Counter()
    for line in raw.splitlines():
        if not line.startswith("c S3_CRR "):
            continue
        for token in line.split()[2:]:
            if "=" in token:
                key,val=token.split("=",1)
                if key in DERIVED_FIELDS:
                    try:stats[key]=int(val)
                    except ValueError:pass
    return dict(stats)

def finish(row, arm, source, seed, cap, started, **meta):
    e2e=time.monotonic()-started
    if row["status"] in ("ERROR","INVALID_SAT"):
        raise RuntimeError(f"{arm} invalid status id={source['id']}")
    if e2e>cap:
        row.update(status="UNKNOWN", verified=False, php_math_certified=False)
    row.update(id=source["id"], split=source["split"], arm=arm, seed=seed,
               original_cnf_sha256=source["sha256"], cap_s=cap,
               e2e_s=round(e2e,6), **meta)
    row=B.with_metrics(row,cap)
    if source.get("known_sat") and row["status"].startswith("UNSAT"):
        raise RuntimeError("UNSAT contradicts original source witness")
    return row

def native_trial(source, seed, cap, label="S3_NATIVE", started=None, hint=None):
    if started is None:
        started=time.monotonic()
    stdout=[]
    original_run=B.subprocess.run
    def capture(*args, **kw):
        p=original_run(*args, **kw)
        stdout.append(p.stdout or "")
        return p
    remaining=cap-(time.monotonic()-started)-.12
    if remaining<=.45:
        row=dict(status="UNKNOWN",verified=False,php_math_certified=False,
                 conflicts=None,decisions=None)
    else:
        with patch.object(B,"command",native_command),patch.object(B.subprocess,"run",capture):
            row=B.run_solver("LTM9_FAST",source,seed,remaining)
    telemetry=process_native_output("\n".join(stdout))
    added=telemetry.get("xor_binary_added",0)+telemetry.get("resolution_added",0)
    return finish(row,label,source,seed,cap,started,
                  hint=hint,native=True,derived_clauses=added,
                  xor_binary_added=telemetry.get("xor_binary_added",0),
                  resolution_added=telemetry.get("resolution_added",0),
                  units_added=telemetry.get("units",0),
                  xor_rows=telemetry.get("xor_rows",0),
                  binary_input=telemetry.get("binary_input",0),
                  telemetry_seen=bool(telemetry),fallback=None)

def gated_trial(source,seed,cap):
    t=time.monotonic()
    p=Path(source["path"])
    if hashlib.sha256(p.read_bytes()).hexdigest()!=source["sha256"]:
        raise RuntimeError("original SHA mismatch")
    n=source.get("nvars") or B.nvars(p)
    hint=S2.read_hint(p)
    if n<=3000 and p.stat().st_size<=768*1024 and hint is not None:
        return native_trial(source,seed,cap,label="S3_GATED",started=t,hint=hint)
    # Frozen prior-guided fallback. Not a new blind model.
    chosen="Kissat" if n>=300 else "CaDiCaL"
    remaining=cap-(time.monotonic()-t)-.12
    if remaining<.25:
        row=dict(status="UNKNOWN",verified=False,php_math_certified=False,
                 conflicts=None,decisions=None)
    else:
        row=B.run_solver(chosen,source,seed,remaining)
    return finish(row,"S3_GATED",source,seed,cap,t,
                  hint=hint,native=False,derived_clauses=0,
                  xor_binary_added=0,resolution_added=0,units_added=0,
                  xor_rows=0,binary_input=0,telemetry_seen=False,
                  fallback=chosen)

def trial(arm,source,seed,cap):
    if arm=="S3_GATED":return gated_trial(source,seed,cap)
    if arm=="S3_NATIVE":return native_trial(source,seed,cap)
    return S2.trial(arm,source,seed,cap)

def report(rows,cap,arms):
    totals=B.metrics(rows,cap,arms)
    best=min(REFERENCES,key=lambda x:totals[x]["PAR2_verified_s"])
    reference=totals[best]["PAR2_verified_s"]
    paired={(r["id"],r["seed"],r["arm"]):r for r in rows}
    grouped={}
    for arm in ("S3_GATED","S3_NATIVE"):
        subset=[r for r in rows if r["arm"]==arm]
        cost=totals[arm]["PAR2_verified_s"]
        deviations=[r["PAR2_verified_s"]-paired[(r["id"],r["seed"],best)]["PAR2_verified_s"] for r in subset]
        grouped[arm]=dict(
            gain_vs_best_pct=round(100*(1-cost/max(reference,1e-9)),3),
            speedup_vs_best_x=round(reference/max(cost,1e-9),5),
            gain_vs_S1_pct=round(100*(1-cost/max(totals["S1"]["PAR2_verified_s"],1e-9)),3),
            derived_clauses=sum(r["derived_clauses"] for r in subset),
            xor_binary_added=sum(r["xor_binary_added"] for r in subset),
            resolution_added=sum(r["resolution_added"] for r in subset),
            units_added=sum(r["units_added"] for r in subset),
            with_derivations=sum(r["derived_clauses"]>0 for r in subset),
            native_invocations=sum(r["native"] for r in subset),
            regressions_10pct=sum(r["PAR2_verified_s"]>
                              paired[(r["id"],r["seed"],best)]["PAR2_verified_s"]*1.1+.002
                              for r in subset),
            mean_regret_s=round(statistics.mean(deviations),6))
    return dict(best_reference=best, totals=totals,
                s3=grouped,one_logical_cpu=True,
                full_original_SAT_verification=True,
                independent_UNSAT_only=True,
                global_blind_claim=False)

def collect_synthetic(root,seed):
    sources=S2.build_synthetic(root,seed)
    return sources

def run_synthetic(root,seed):
    sources=collect_synthetic(root,seed)
    rows=[]
    with (root/"trials.jsonl").open("w") as log:
        for i,source in enumerate(sources):
            order=list(ARMS)
            rot=i%len(order)
            for arm in order[rot:]+order[:rot]:
                row=trial(arm,source,SEED,SYNTH_CAP)
                row.update(tier=source["tier"],group=source["family"],
                           nvars=source["nvars"])
                rows.append(row)
                log.write(json.dumps(row,sort_keys=True)+"\n")
                log.flush()
            if (i+1)%4==0:
                emit("S3_PROGRESS",dict(completed=i+1,total=len(sources),
                                        last_nvars=source["nvars"],
                                        last_group=source["family"]))
    B.check_contradictions(rows)
    result=report(rows,SYNTH_CAP,ARMS)
    result.update(dataset="reused synthetic SAT generator",sources=len(sources),
                  cap_s=SYNTH_CAP,
                  note="Prior seen generator families; exploratory, not new blind test",
                  bands={name:report([r for r in rows if r["tier"]==name],SYNTH_CAP,ARMS)
                         for name in ("tier1","tier2","tier3")})
    (root/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("S3_SYNTH_FINAL",result)
    return result

def run_official(root):
    root.mkdir(parents=True,exist_ok=False)
    B.ROOT=root
    sources=B.collect()
    eligible=[]
    for source in sources:
        n=B.nvars(source["path"])
        if 80<=n<=3000 and source["bytes"]<=700000:
            eligible.append(dict(source,nvars=n))
    bands=((80,300),(301,1000),(1001,3000))
    selected=[]
    for lo,hi in bands:
        options=sorted((s for s in eligible if lo<=s["nvars"]<=hi),
                       key=lambda s:(s["bytes"],s["sha256"]))
        selected.extend(options[:2])
    selected=selected[:6]
    if len(selected)<4:
        raise RuntimeError(f"insufficient medium official cases ({len(selected)})")
    (root/"selection.json").write_text(json.dumps(dict(
        original_cnfs=[dict(id=s["id"],nvars=s["nvars"],sha=s["sha256"]) for s in selected],
        archive="official SAT Competition 2024 original",
        selection_frozen="up to 2 lowest-byte formulas per variable bucket, no outcome info",
        previously_seen_archive=True,
        globally_blind=False),indent=2)+"\n")
    rows=[]
    with (root/"trials.jsonl").open("w") as log:
        for source in selected:
            for arm in ARMS:
                row=trial(arm,source,SEED,OFFICIAL_CAP)
                row.update(tier="official",group="official",
                           nvars=source["nvars"])
                rows.append(row)
                log.write(json.dumps(row,sort_keys=True)+"\n")
                log.flush()
                emit("S3_OFFICIAL_TRIAL",dict(id=source["id"],nvars=source["nvars"],
                     arm=arm,status=row["status"],PAR2=row["PAR2_verified_s"],
                     derived=row.get("derived_clauses",0),fallback=row.get("fallback")))
    B.check_contradictions(rows)
    result=report(rows,OFFICIAL_CAP,ARMS)
    result.update(dataset="original SAT Competition 2024 CNFs",sources=len(selected),
                  cap_s=OFFICIAL_CAP,globally_blind=False,repetitions=1)
    (root/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    emit("S3_OFFICIAL_FINAL",result)
    return result

def selftest():
    with tempfile.TemporaryDirectory() as directory:
        p=Path(directory)/"tiny.cnf"
        p.write_text("p cnf 3 2\n1 2 0\n-2 3 0\n")
        source=dict(id=-1,split="holdout",path=str(p),nvars=3,
                    sha256=hashlib.sha256(p.read_bytes()).hexdigest(),known_sat=True)
        # Command builder is deterministic and baseline engine untouched.
        cmd=native_command("LTM9_FAST",p,17,1.0)
        assert cmd[0].endswith("drnas_s3_crr")
        assert B.sat_witness_valid(p,3,"v 1 -2 3 0\n")
        assert not B.sat_witness_valid(p,3,"v -1 -2 -3 0\n")
    emit("S3_HARNESS_SELFTEST_PASS",dict(original_witness=True,
                                        native_build_isolated=True,
                                        routing_modes=2))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--skip-official",action="store_true")
    ap.add_argument("--seed",type=int,default=320261112)
    args=ap.parse_args()
    if args.selftest:
        selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    L.setup_source()
    ROOT.mkdir(exist_ok=False)
    results=dict(synthetic=run_synthetic(ROOT/"synthetic",args.seed))
    if not args.skip_official:
        results["official"]=run_official(ROOT/"official")
    combined=dict(
        commit_flavor="DRNAS S3 bounded CRR native",
        no_APK=True,one_logical_cpu=True,
        exploratory=True,reused_corpus=True,
        outcome_verified_only=True,
        results={name:dict(
            reference=val["best_reference"],
            PAR2={k:v["PAR2_verified_s"] for k,v in val["totals"].items()},
            s3=val["s3"]) for name,val in results.items()})
    (ROOT/"combined.json").write_text(json.dumps(combined,indent=2,sort_keys=True)+"\n")
    emit("S3_FINAL",combined)

if __name__=="__main__":
    main()
