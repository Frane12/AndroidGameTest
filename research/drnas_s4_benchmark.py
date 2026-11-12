#!/usr/bin/env python3
"""S4 SELECTIVE UTILITY: paired 16-v-32-clause native CDCL ablation, original CNFs.

Reuses S3/S2 frozen synthetic generators and SAT2024 archive selection.
All SAT outcomes are verified against the original CNF. UNSAT without an
independent original-CNF certificate has PAR2 timeout penalty. Exploratory:
generator families and SAT2024 corpus were used by prior DRNAS experiments.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import statistics
import tempfile
import time
from unittest.mock import patch

import drnas_s3_benchmark as S3

B,L,S2 = S3.B,S3.L,S3.S2
ROOT=Path("drnas_s4_utility")
CAP_SYNTH=1.5
CAP_OFFICIAL=4.0
ARMS=("S4_GATED","S4_16","S4_32","S3_NATIVE","S1","CaDiCaL","Kissat","CryptoMiniSat")
REFERENCES=("CaDiCaL","Kissat","CryptoMiniSat")
SEEDS=(17,)
FIELDS=("mode","original","candidates","eligible","selected","selected_xor",
        "selected_resolution","root_forcing","root_trail","xor_rows",
        "root_conflict","skipped")

def emit(k,v):
    print(k+" "+json.dumps(v,sort_keys=True,separators=(",",":")),flush=True)

def native_command(arm,path,seed,cap,limit):
    if arm!="LTM9_FAST":
        raise RuntimeError("unexpected alias "+arm)
    return [f"mre_atlas23/bin/drnas_s4_utility_{limit}",str(path),
            "--mode","LTM8_FAST","--time",str(max(.1,cap-.30)),
            "--seed",str(seed),"--policy","1.0,0.85"]

def telemetry_parse(out):
    result={}
    for line in out.splitlines():
        if not line.startswith("c S4_UTILITY "):continue
        for word in line.split()[2:]:
            if "=" not in word:continue
            key,value=word.split("=",1)
            if key in FIELDS:
                try:result[key]=int(value)
                except ValueError:pass
    return result

def final(row,arm,source,seed,cap,started,**kwargs):
    elapsed=time.monotonic()-started
    if row["status"] in ("ERROR","INVALID_SAT"):
        raise RuntimeError(f"invalid {arm} status on {source['id']}")
    if elapsed>cap:row.update(status="UNKNOWN",verified=False,php_math_certified=False)
    row.update(arm=arm,id=source["id"],split=source["split"],seed=seed,cap_s=cap,
               original_cnf_sha256=source["sha256"],e2e_s=round(elapsed,6),**kwargs)
    out=B.with_metrics(row,cap)
    if source.get("known_sat") and out["status"].startswith("UNSAT"):
        raise RuntimeError("UNSAT contradicts independently checked planted witness")
    return out

def native(source,seed,cap,limit,label=None,started=None,hint=None):
    if started is None:started=time.monotonic()
    label=label or f"S4_{limit}"
    path=Path(source["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source["sha256"]:
        raise RuntimeError("source hash mismatch")
    captured=[]
    old=B.subprocess.run
    def capture(*args,**kwargs):
        p=old(*args,**kwargs)
        captured.append(p.stdout or "")
        return p
    remaining=cap-(time.monotonic()-started)-.12
    if remaining<=.45:
        row=dict(status="UNKNOWN",verified=False,php_math_certified=False,
                 conflicts=None,decisions=None)
    else:
        def command(arm,path,seed,time_cap):
            return native_command(arm,path,seed,time_cap,limit)
        with patch.object(B,"command",command),patch.object(B.subprocess,"run",capture):
            row=B.run_solver("LTM9_FAST",source,seed,remaining)
    stats=telemetry_parse("\n".join(captured))
    return final(row,label,source,seed,cap,started,
                 strategy=f"native_{limit}",hint=hint,
                 derived_clauses=stats.get("selected",0),
                 root_forcing=stats.get("root_forcing",0),
                 derived_xor=stats.get("selected_xor",0),
                 derived_resolution=stats.get("selected_resolution",0),
                 considered=stats.get("candidates",0),
                 root_trail=stats.get("root_trail",0),
                 telemetry_seen=bool(stats),fallback=None)

def gated(source,seed,cap):
    started=time.monotonic()
    path=Path(source["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source["sha256"]:
        raise RuntimeError("source hash mismatch")
    n=source.get("nvars") or B.nvars(path)
    size=path.stat().st_size
    hint=S2.S2.read_hint(path) if hasattr(S2,"S2") else S2.read_hint(path)
    # Frozen source-only selection; no benchmark group, label or oracle input.
    # Larger cases bypass S3's costly native route completely.
    if n<=260 and size<=120000 and hint is not None:
        return native(source,seed,cap,16,label="S4_GATED",started=started,hint=hint)
    remaining=cap-(time.monotonic()-started)-.12
    if remaining<=.3:
        row=dict(status="UNKNOWN",verified=False,php_math_certified=False,
                 conflicts=None,decisions=None)
    else:
        row=B.run_solver("Kissat",source,seed,remaining)
    return final(row,"S4_GATED",source,seed,cap,started,
                 strategy="Kissat_fallback",hint=hint,derived_clauses=0,
                 root_forcing=0,derived_xor=0,derived_resolution=0,
                 considered=0,root_trail=0,telemetry_seen=False,fallback="Kissat")

def trial(arm,source,seed,cap):
    if arm=="S4_GATED":return gated(source,seed,cap)
    if arm=="S4_16":return native(source,seed,cap,16)
    if arm=="S4_32":return native(source,seed,cap,32)
    if arm=="S3_NATIVE":return S3.native_trial(source,seed,cap)
    return S2.trial(arm,source,seed,cap)

def report(rows,cap):
    totals=B.metrics(rows,cap,ARMS)
    best=min(REFERENCES,key=lambda a:totals[a]["PAR2_verified_s"])
    paired={(r["id"],r["seed"],r["arm"]):r for r in rows}
    scored={}
    for arm in ("S4_GATED","S4_16","S4_32","S3_NATIVE"):
        part=[r for r in rows if r["arm"]==arm]
        baseline=totals[best]["PAR2_verified_s"]
        current=totals[arm]["PAR2_verified_s"]
        deltas=[r["PAR2_verified_s"]-paired[(r["id"],r["seed"],best)]["PAR2_verified_s"]
                for r in part]
        scored[arm]=dict(
            PAR2_reduction_vs_best_pct=round(100*(1-current/baseline),3),
            speedup_vs_best_x=round(baseline/max(current,1e-9),5),
            PAR2_reduction_vs_S1_pct=round(
                100*(1-current/totals["S1"]["PAR2_verified_s"]),3),
            regressions_over_10pct=sum(
                r["PAR2_verified_s"]>
                paired[(r["id"],r["seed"],best)]["PAR2_verified_s"]*1.1+.002
                for r in part),
            mean_regret_s=round(statistics.mean(deltas),6),
            with_derived_clauses=sum(r.get("derived_clauses",0)>0 for r in part),
            derived_clauses=sum(r.get("derived_clauses",0) for r in part),
            root_forcing=sum(r.get("root_forcing",0) for r in part),
            xor_added=sum(r.get("derived_xor",0) for r in part),
            binary_resolution_added=sum(r.get("derived_resolution",0) for r in part),
            fallbacks=collections.Counter(r.get("fallback") for r in part
                                           if r.get("fallback")))
    return dict(best_reference=best,totals=totals,diagnostics=scored,
                tested_original_CNF=True,one_logical_CPU=True,
                not_globally_blind=True)

def synthetic(root,seed):
    sources=S2.build_synthetic(root,seed)
    rows=[]
    with (root/"trials.jsonl").open("w") as f:
        for i,source in enumerate(sources):
            order=list(ARMS)
            rot=i%len(order)
            for arm in order[rot:]+order[:rot]:
                row=trial(arm,source,SEEDS[0],CAP_SYNTH)
                row.update(tier=source["tier"],family=source["family"],
                           nvars=source["nvars"])
                rows.append(row);f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
            if (i+1)%4==0:
                emit("S4_PROGRESS",dict(completed=i+1,total=len(sources),
                                        nvars=source["nvars"]))
    B.check_contradictions(rows)
    out=report(rows,CAP_SYNTH)
    out.update(source_count=20,source_type="reused planted synthetic SAT",
               cap_s=CAP_SYNTH,
               tiers={tier:report([x for x in rows if x["tier"]==tier],CAP_SYNTH)
                      for tier in ("tier1","tier2","tier3")})
    (root/"report.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    emit("S4_SYNTH_FINAL",out)
    return out

def official(root):
    root.mkdir(parents=True,exist_ok=False)
    B.ROOT=root
    sources=B.collect()
    selected=[]
    for s in sources:
        n=B.nvars(s["path"])
        if 80<=n<=3000 and s["bytes"]<=700000:
            selected.append(dict(s,nvars=n))
    selected=sorted(selected,key=lambda s:(s["bytes"],s["sha256"]))[:4]
    if len(selected)<4:raise RuntimeError("need four medium official CNFs")
    (root/"selection.json").write_text(json.dumps(
        dict(sources=[dict(id=s["id"],nvars=s["nvars"],sha=s["sha256"])
                      for s in selected],
             preexisting_archive=True,outcome_filtering=False,
             not_globally_blind=True),indent=2)+"\n")
    rows=[]
    with (root/"trials.jsonl").open("w") as f:
        for source in selected:
            for arm in ARMS:
                row=trial(arm,source,SEEDS[0],CAP_OFFICIAL)
                row.update(nvars=source["nvars"],family="official",
                           tier="official")
                rows.append(row);f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
                emit("S4_OFFICIAL_TRIAL",dict(
                    id=source["id"],arm=arm,status=row["status"],
                    PAR2=row["PAR2_verified_s"],derived=row.get("derived_clauses",0)))
    B.check_contradictions(rows)
    out=report(rows,CAP_OFFICIAL)
    out.update(source_count=len(selected),
               source_type="official SAT Competition 2024 originals",
               cap_s=CAP_OFFICIAL,not_globally_blind=True)
    (root/"report.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    emit("S4_OFFICIAL_FINAL",out)
    return out

def selftest():
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"x.cnf"
        p.write_text("p cnf 3 2\n1 2 0\n-2 3 0\n")
        assert native_command("LTM9_FAST",p,17,1.,16)[0].endswith("16")
        assert native_command("LTM9_FAST",p,17,1.,32)[0].endswith("32")
        assert B.sat_witness_valid(p,3,"v 1 -2 3 0\n")
        assert telemetry_parse("c S4_UTILITY mode=16 selected=3 root_forcing=1 ")==dict(
            mode=16,selected=3,root_forcing=1)
    emit("S4_HARNESS_SELFTEST_PASS",dict(two_native_caps=True,source_witness=True))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--seed",type=int,default=420261112)
    parser.add_argument("--skip-official",action="store_true")
    args=parser.parse_args()
    if args.selftest:selftest();return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    L.setup_source()
    ROOT.mkdir(exist_ok=False)
    result={"synthetic":synthetic(ROOT/"synthetic",args.seed)}
    if not args.skip_official:
        result["official"]=official(ROOT/"official")
    combined=dict(experiment="S4 utility root and XOR",global_blind_claim=False,
                  original_CNF_verification=True,
                  results={name:dict(
                    reference=rep["best_reference"],
                    verified_PAR2={arm:metrics["PAR2_verified_s"]
                                   for arm,metrics in rep["totals"].items()},
                    s4=rep["diagnostics"]) for name,rep in result.items()})
    (ROOT/"combined.json").write_text(json.dumps(combined,indent=2,sort_keys=True)+"\n")
    emit("S4_FINAL",combined)

if __name__=="__main__":main()
