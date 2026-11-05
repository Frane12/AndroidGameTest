#!/usr/bin/env python3
"""R136B paired native CaDiCaL online GF2 feedback audit.

No hidden solver modifications: R133c implementation is included unchanged,
monitor reads IPASIR-UP events and a safe guard only suppresses added clauses.
6 REUSED SATLIB PARITY originals, 2 reps x 5 modes, 10-second cap;
not blind and not independently UNSAT-proven.
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
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
import r133c_native_gf2_benchmark as frozen

PROTO="DRNAS-R136B-NATIVE-IPASIR-UP-ONLINE-FEEDBACK-20261105-v1"
CAP=10.0
REPS=2
MODES=("clean","active","gf2","feedback","guard")
FIELDS=("source_rows","derived_rows","clauses_emitted","rows_scanned",
        "watch_lookups","row_literal_reads","callbacks","assignments",
        "backtracks","feedback_callbacks","feedback_candidates",
        "unit_messages","conflict_messages","width_sum","short_messages",
        "observed_after_emit_matches","observed_after_emit_opposites",
        "observed_after_emit_expired","observed_after_emit_backtracks",
        "feedback_unresolved","feedback_guard_stops","bridge_budget_off")

def need(cond,msg):
    if not cond:raise RuntimeError("R136B_AUDIT_FAIL_CLOSED "+msg)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()

def run_solver(binary,mode,source,rows,preprocess_s=0.0):
    cmd=[str(binary.resolve()),mode,str(source.resolve()),str(rows.resolve())]
    started=time.perf_counter()
    proc=None
    try:
        remain=CAP-preprocess_s
        if remain<=0:raise subprocess.TimeoutExpired(cmd,CAP)
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=remain)
        duration=time.perf_counter()-started
    except subprocess.TimeoutExpired:
        duration=max(0,CAP-preprocess_s)
        data={f:0 for f in FIELDS}
        data.update(status="TIMEOUT",par2_s=2*CAP,solver_s=round(duration,6),
                    preprocessing_s=round(preprocess_s,6),
                    total_s=round(CAP,6),
                    independently_verified_unsat=False)
        return data
    if proc.returncode not in (10,20):
        raise RuntimeError(f"R136B native solver exit={proc.returncode} mode={mode} src={source.name}: "+
                           proc.stderr[-800:]+proc.stdout[-800:])
    line=next((x for x in proc.stdout.splitlines()
               if x.startswith("R136B_RESULT ")),None)
    need(line is not None,"missing R136B_RESULT telemetry: "+proc.stdout[-500:])
    tokens=dict(re.findall(r"(\w+)=([^\s]+)",line))
    need(tokens.get("mode")==mode,"mode telemetry drift")
    need(tokens.get("disabled")=="0","native bridge invariant disabled")
    status="SAT" if proc.returncode==10 else "UNSAT"
    need(tokens.get("status")==status,"status telemetry drift")
    if status=="SAT":
        need(tokens.get("source_sat_witness_checked")=="1","SAT witness unchecked")
    data={f:int(tokens[f]) for f in FIELDS}
    need(data["feedback_candidates"]<=data["clauses_emitted"],"feedback count greater than clauses")
    need(data["unit_messages"]+data["conflict_messages"]==data["feedback_candidates"],
         "incomplete feedback event classification")
    need(data["observed_after_emit_matches"]+data["observed_after_emit_opposites"]<=data["unit_messages"],
         "feedback matching impossible")
    if mode in ("clean","active","gf2"):
        need(data["feedback_candidates"]==0,"feedback accidentally enabled")
    if mode in ("feedback","guard"):
        need(data["feedback_candidates"]==data["clauses_emitted"],"unrecorded native message")
    if mode!="guard":
        need(data["feedback_guard_stops"]==0,"guard unexpectedly active")
    total=duration+preprocess_s
    if total>=CAP:status="TIMEOUT"
    data.update(status=status,par2_s=round(2*CAP if status=="TIMEOUT" else total,6),
                solver_s=round(duration,6),
                preprocessing_s=round(preprocess_s,6),
                total_s=round(min(total,CAP),6),
                independently_verified_unsat=False)
    return data

def prepare(source,out,stem):
    rows=out/(stem+".tsv")
    proof=out/(stem+"-source-proof.json")
    start=time.perf_counter()
    proc=subprocess.run([sys.executable,"research/r93_export_verified_rows.py",
                         "export","--cnf",str(source),"--rows",str(rows),
                         "--evidence",str(proof)],
                        check=True,capture_output=True,text=True,timeout=45)
    prep_s=time.perf_counter()-start
    evidence=json.loads(proof.read_text())
    need(evidence["source_sha256"]==sha(source),"source proof hash mismatch")
    need(evidence["protocol"]=="R93-LIVE-XOR-PROOF-CERTS-v1","parity proof protocol mismatch")
    return rows,proof,evidence,prep_s

def paired_fixture(binary,out):
    source=frozen.fixture(out)
    rows,proof,evidence,prep=prepare(source,out,"fixture")
    need(evidence["exported"]>=2,"fixture lacks independent certified XOR rows")
    results={}
    for mode in MODES:
        results[mode]=run_solver(binary,mode,source,rows,
                                prep if mode!="clean" else 0)
        need(results[mode]["status"]=="SAT","fixture status mismatch "+mode)
    need(results["feedback"]["derived_rows"]>=1,"GF2 derived closure unused")
    need(results["feedback"]["feedback_candidates"]>0,"no emitted feedback messages")
    need(results["guard"]["feedback_guard_stops"]==0,"guard stopped fixture unexpectedly")
    (out/"fixture-results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    print("R136B_FIXTURE_PASS",json.dumps(results,sort_keys=True),flush=True)

def aggregate(rows,mode):
    x=[r for r in rows if r["mode"]==mode]
    return dict(trials=len(x),solved=sum(r["status"]!="TIMEOUT" for r in x),
                par2_s=round(sum(r["par2_s"] for r in x),6),
                **{key:sum(r[key] for r in x) for key in FIELDS})

def bootstrap(formulas,rows,mode,reference,n=2000):
    rng=random.Random(13620261105)
    pair={(r["sha256"],r["rep"],r["mode"]):r for r in rows}
    groups=[]
    for item in formulas:
        s=item["sha256"]
        groups.append((sum(pair[(s,rep,reference)]["par2_s"] for rep in range(REPS)),
                       sum(pair[(s,rep,mode)]["par2_s"] for rep in range(REPS))))
    values=[]
    for _ in range(n):
        draw=[groups[rng.randrange(len(groups))] for __ in groups]
        a=sum(x for x,y in draw);b=sum(y for x,y in draw)
        values.append(100*(a-b)/a if a else 0)
    values.sort()
    return [round(values[int(.025*(n-1))],5),round(values[int(.975*(n-1))],5)]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,required=True)
    ap.add_argument("--satlib",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    a.binary=a.binary.resolve()
    a.out.mkdir(parents=True,exist_ok=True)
    need(a.binary.is_file(),"no native binary")
    if hasattr(os,"sched_getaffinity"):
        permitted=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(permitted)})
    runner_cpu=next((line for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")),"unavailable")
    binary_sha=sha(a.binary)
    paired_fixture(a.binary,a.out)
    controls=frozen.select_controls(a.satlib)
    manifest=[dict(name=p.name,sha256=sha(p)) for p in controls]
    need(len(controls)==6 and len({x["sha256"] for x in manifest})==6,
         "invalid frozen development manifest")
    (a.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    rows=[]
    for source in controls:
        digest=sha(source)
        rows_path,proof,evidence,prep=prepare(source,a.out,digest[:12])
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+digest+str(rep)).shuffle(modes)
            for mode in modes:
                result=run_solver(a.binary,mode,source,rows_path,
                                  prep if mode!="clean" else 0)
                result.update(formula=source.name,sha256=digest,rep=rep,
                              mode=mode,exported_parity_rows=evidence["exported"],
                              source_proof_sha256=sha(proof),
                              binary_sha256=binary_sha,runner_cpu=runner_cpu)
                rows.append(result)
        print("R136B_CASE",source.name,"certified",evidence["exported"],
              "prep_s",round(prep,5),flush=True)
    need(len(rows)==6*REPS*len(MODES)==60,"incomplete paired trials")
    for item in manifest:
        for rep in range(REPS):
            votes={r["status"] for r in rows if r["sha256"]==item["sha256"]
                   and r["rep"]==rep and r["status"]!="TIMEOUT"}
            need(len(votes)<=1,"SAT/UNSAT contradiction among native modes")
    with (a.out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    summary={mode:aggregate(rows,mode) for mode in MODES}
    clean=summary["clean"]["par2_s"]
    gf2=summary["gf2"]["par2_s"]
    feedback=summary["feedback"]["par2_s"]
    guard=summary["guard"]["par2_s"]
    report=dict(protocol=PROTO,
        data_scope="REUSED SATLIB PARITY known development controls: not new holdout",
        source_verified=True,source_cnf_unmodified=True,
        source_sha256_manifest=sha(a.out/"manifest.json"),
        binary_sha256=binary_sha,runner_cpu=runner_cpu,
        matched_runner=True,affinity_pinned_if_available=True,
        formulas=6,repetitions=2,measured_trials=60,cap_s=CAP,
        verified_cnf_sat_witness=True,independent_unsat_proof=False,
        observed_assignment_matches_are_not_causal_reason_proofs=True,
        actual_cdcl_conflict_and_decision_metrics_not_available=True,
        selector_policy_frozen=True,all_preprocessing_charged=True,
        modes=summary,
        feedback_vs_gf2_gain_pct=round(100*(gf2-feedback)/gf2,5),
        guard_vs_feedback_gain_pct=round(100*(feedback-guard)/feedback,5),
        guard_vs_clean_gain_pct=round(100*(clean-guard)/clean,5),
        bootstrap_guard_vs_clean=bootstrap(manifest,rows,"guard","clean"),
        bootstrap_guard_vs_feedback=bootstrap(manifest,rows,"guard","feedback"),
        verdict="DEVELOPMENT_ONLY_NO_PROMOTION")
    (a.out/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R136B_NATIVE_FEEDBACK_AUDIT",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
