#!/usr/bin/env python3
"""EQUIV7: diagnostic signed SCC cycle screening + original SHA Native SAT replication.
NO solver selection is trained on these previously seen EQUIV6 formulas.
Binary SCC graph is a SOUND source-only diagnostic, not a certified LRAT UNSAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import statistics
import subprocess
import tempfile
import time

import drnas_x22_parallel_reducer as x22
import drnas_x16_singlecore_dual as x16
import drnas_x14_adaptive_portfolio as x14

ROOT=pathlib.Path("mre_equiv7")
SOURCE=pathlib.Path("mre_equiv6/cases")
PRIOR=pathlib.Path("mre_equiv6/manifest.json")
CPP=ROOT/"bin/scc"
CAD3=pathlib.Path("mre_equiv6/bin/cadical_3_0_1")
CAD=pathlib.Path("/usr/bin/cadical")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
NATIVE=pathlib.Path("mre_x4/bin/native")
TARGET_GBD="5ea9d54e4eb8eeab1ff058471b9c83ca"
TARGET_SHA="c28e829957911baee4a9218f952f87f2c3d776669d3ac176a09dc47ee5729371"
PROTO="DRNAS-EQUIV7-SIGNED-SCC-SCREEN16-NATIVE-REPRO36-30S-v1"
CAP=30.0
REPS=6
ARMS=("native1","kissat1","cadical173","cadical301",
      "cadical301_no_congruence","cadical301_both")

def need(ok,why):
    if not ok:raise RuntimeError("EQUIV7_FAIL_CLOSED "+str(why))
def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def save(p,value):
    p=pathlib.Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
def command(arm,src,seed):
    if arm=="native1":return x16.command("native",src,seed)
    if arm=="kissat1":return x16.command("kissat",src,seed)
    cfg={
        "cadical173":(CAD,[]),
        "cadical301":(CAD3,[]),
        "cadical301_no_congruence":(CAD3,["--no-congruence"]),
        "cadical301_both":(CAD3,["--no-congruence","--no-reluctant"]),
    }
    exe,opts=cfg[arm]
    return [str(exe),*opts,str(src)]

def freeze():
    ROOT.mkdir(exist_ok=True)
    m=json.loads(PRIOR.read_text())
    need(len(m["cases"])==16 and m["expected_trials"]==288,"EQUIV6 manifest changed")
    hashes={str(p):digest(p) for p in (CPP,CAD,CAD3,KISSAT,NATIVE)}
    for c in m["cases"]:
        need(digest(SOURCE/c["filename"])==c["sha256"],"original SHA drift")
    target=[c for c in m["cases"] if c["gbd"]==TARGET_GBD]
    need(len(target)==1 and target[0]["sha256"]==TARGET_SHA,"target identity drift")
    save(ROOT/"manifest.json",dict(
        protocol=PROTO,mode="diagnostic plus independent source-SHA E2E reproduction",
        source_manifest_sha256=digest(PRIOR),source_gbds=[c["gbd"] for c in m["cases"]],
        source_sha256=[c["sha256"] for c in m["cases"]],
        code_sha256=digest(__file__),
        native_cpp_sha256=digest("research/drnas_equiv7_signed_scc.cpp"),
        frozen_binaries=hashes,target=target[0],reps=REPS,arms=ARMS,
        CAP_s=CAP,expected_repro_trials=REPS*len(ARMS),
        holdout=False,previously_observed_native_SAT=True,
        UNSAT_LRAT=False,UNSAT_requires_reference_agreement=True,
        cpu_policy="one pinned logical CPU per trial",no_auto_promotion=True))
    verify()
    print("EQUIV7_FROZEN",json.dumps(dict(sources=16,target=TARGET_GBD,
          reps=REPS,trials=REPS*len(ARMS)),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["expected_repro_trials"]==REPS*len(ARMS),"protocol drift")
    need(m["code_sha256"]==digest(__file__) and
         m["native_cpp_sha256"]==digest("research/drnas_equiv7_signed_scc.cpp"),
         "code drift")
    need(m["source_manifest_sha256"]==digest(PRIOR),"source cohort drift")
    for p,h in m["frozen_binaries"].items():
        need(digest(p)==h,"binary drift "+p)
    c=json.loads(PRIOR.read_text())["cases"]
    need(len(c)==16,"source number drift")
    for case in c:
        need(digest(SOURCE/case["filename"])==case["sha256"],"source SHA drift")
    need(sum(x["sha256"]==TARGET_SHA and x["gbd"]==TARGET_GBD for x in c)==1,
         "target changed")
    return m

def run_scc(path):
    r=subprocess.run([str(CPP),str(path)],capture_output=True,
                     text=True,check=True,timeout=10)
    lines=[x[len("SCC7_DIAGNOSTIC "):] for x in r.stdout.splitlines()
           if x.startswith("SCC7_DIAGNOSTIC ")]
    need(len(lines)==1,"no unique SCC diagnostic")
    return json.loads(lines[0])
def selftest():
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"toy.cnf"
        p.write_text("p cnf 3 3\n-1 2 0\n-2 3 0\n-3 1 0\n")
        a=run_scc(p)
        need(a["scc_size_ge3"]>=2 and a["max_scc_size"]==3 and
             a["binary_unsat_conflicting_vars"]==0,
             "length-3 binary SCC cycle not detected")
        p.write_text("p cnf 1 2\n1 1 0\n-1 -1 0\n")
        b=run_scc(p)
        need(b["binary_unsat_conflicting_vars"]==1,
             "literal plus complement SCC not detected")
        p.write_text("p cnf 3 3\n1 2 0\n2 3 0\n-1 -3 0\n")
        c=run_scc(p)
        need(c["nontrivial_scc"]==0,"false SCC")
    print("EQUIV7_SELFTEST_PASS",flush=True)

def screen():
    m=verify()
    cohort=json.loads(PRIOR.read_text())["cases"]
    result=[]
    for c in cohort:
        p=SOURCE/c["filename"]
        measurements=[run_scc(p) for _ in range(4)]
        keys=[k for k in measurements[0] if not k.endswith("_ms")]
        need(all({k:r[k] for k in keys}==
                 {k:measurements[0][k] for k in keys}
                 for r in measurements),"non-deterministic SCC counts")
        data=dict(measurements[0])
        data["median_total_ms"]=round(statistics.median(r["total_ms"] for r in measurements),6)
        data["median_scc_ms"]=round(statistics.median(r["scc_ms"] for r in measurements),6)
        data["median_parse_ms"]=round(statistics.median(r["cnf_parse_ms"] for r in measurements),6)
        signal=c["source_signals"]
        need(data["vars"]==signal["vars"] and
             data["clauses"]==signal["clauses"],"CNF geometry mismatch")
        data.update(gbd=c["gbd"],sha256=c["sha256"],
            direct_reciprocal=signal["reciprocal_binary_edges"],
            source_binary_ratio=signal["binary_ratio"],
            source_horn_ratio=signal["horn_ratio"],
            # A cheap source-only prefilter to AVOID SCC for likely immediate solves.
            # It is an exploratory policy, not an outcome-trained classifier.
            early_abstain=(signal["vars"]<1000 and
                           signal["binary_ratio"]>.95 and
                           signal["horn_ratio"]>.95),
            not_an_E2E_solver_time=True)
        result.append(data)
        save(ROOT/"screen.json",result)
        print("EQUIV7_SCC",json.dumps(data,sort_keys=True),flush=True)
    summary=dict(sources=len(result),
        with_nontrivial_SCC=sum(x["nontrivial_scc"]>0 for x in result),
        with_length_ge3_SCC=sum(x["scc_size_ge3"]>0 for x in result),
        previous_reciprocal_zero_and_long_scc=sum(
            x["direct_reciprocal"]==0 and x["scc_size_ge3"]>0 for x in result),
        true_binary_graph_conflict_cases=sum(x["binary_unsat_conflicting_vars"]>0 for x in result),
        early_abstain_count=sum(x["early_abstain"] for x in result),
        early_abstain_missed_nontrivial_SCC=sum(
            x["early_abstain"] and x["nontrivial_scc"]>0 for x in result),
        median_total_scan_ms=round(statistics.median(x["median_total_ms"] for x in result),6),
        screening_only_no_SAT_UNSAT_benchmark_claim=True)
    save(ROOT/"screen-summary.json",summary)
    print("EQUIV7_SCREEN_FINAL",json.dumps(summary,sort_keys=True),flush=True)

def repro(rep):
    m=verify();need(0<=rep<REPS,"rep index")
    c=m["target"]
    src=SOURCE/c["filename"]
    seed=int(hashlib.sha256((TARGET_SHA+"|equiv7|"+str(rep)).encode()).hexdigest()[:7],16)
    cpu=sorted(os.sched_getaffinity(0))[0]
    n,clauses=x22.read_cnf(src)
    need(n==c["source_signals"]["vars"],"source geometry drift")
    rows=[]
    order=list(ARMS);random.Random(seed).shuffle(order)
    for arm in order:
        start=time.perf_counter()
        before=x22.child_cpu()
        status="TIMEOUT";witness=False
        with tempfile.TemporaryDirectory(dir=ROOT) as td:
            e=x22.launch(arm,command(arm,src,seed),cpu,td)
            try:
                while e["p"].poll() is None and time.perf_counter()-start<CAP-.02:
                    time.sleep(.005)
                if e["p"].poll() is not None:
                    stdout,stderr=x22.read_output(e)
                    if arm=="native1":
                        status=x14.outcome_of("native",e["p"].returncode,
                                              stdout,stderr,src)
                        witness=(status=="SAT")
                    elif arm=="kissat1":
                        status=x14.outcome_of("kissat",e["p"].returncode,
                                              stdout,stderr,src)
                        witness=(status=="SAT")
                    else:
                        status,witness=x22.solver_result("cadical",
                                      e["p"].returncode,stdout,clauses,{})
            finally:
                x22.cleanup([e])
        elapsed=time.perf_counter()-start
        if elapsed>CAP or status not in ("SAT","UNSAT"):
            status="TIMEOUT";witness=False
        need(status!="SAT" or witness,"SAT original source witness invalid")
        row=dict(protocol=PROTO,arm=arm,rep=rep,seed=seed,cap_s=CAP,
            original_sha256=TARGET_SHA,gbd=TARGET_GBD,status=status,
            SAT_original_witness_verified=witness,UNSAT_independent_LRAT=False,
            E2E_s=round(elapsed,6),
            child_CPU_s=round(x22.child_cpu()-before,6),pinned_cpu=cpu)
        rows.append(row)
        save(ROOT/("repro-%d.json"%rep),rows)
        print("EQUIV7_REPRO",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(ARMS),"incomplete replicate")
    print("EQUIV7_REPRO_PASS",rep,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for rep in range(REPS):
        f=ROOT/("repro-%d.json"%rep)
        a=json.loads(f.read_text())
        need(len(a)==len(ARMS),"missing trial "+str(f))
        rows+=a
    keys={(x["rep"],x["arm"]) for x in rows}
    need(len(rows)==len(keys)==REPS*len(ARMS),"duplicate/missing trials")
    need(keys=={(rep,arm) for rep in range(REPS) for arm in ARMS},
         "invalid trial keys")
    statuses={x["status"] for x in rows if x["status"]!="TIMEOUT"}
    need(len(statuses)<=1,"contradictory original SHA verdict")
    # UNSAT is accepted only if both unchanged Kissat and CaDiCaL agree.
    ref_unsat=any(x["arm"]=="kissat1" and x["status"]=="UNSAT" for x in rows) and \
        any(x["arm"] in ("cadical173","cadical301") and x["status"]=="UNSAT" for x in rows)
    def accepted(x):
        return x["status"]=="SAT" or (x["status"]=="UNSAT" and ref_unsat)
    scores={}
    for arm in ARMS:
        a=[x for x in rows if x["arm"]==arm]
        for x in a:
            need(x["protocol"]==PROTO and x["cap_s"]==CAP and
                 x["original_sha256"]==TARGET_SHA,"trial drift")
            need(x["status"]!="SAT" or x["SAT_original_witness_verified"],
                 "unverified SAT")
        scores[arm]=dict(
            attempts=len(a),SAT_verified=sum(x["status"]=="SAT" for x in a),
            UNSAT_consensus_no_LRAT=sum(x["status"]=="UNSAT" and accepted(x) for x in a),
            solved=sum(accepted(x) for x in a),
            timeouts=sum(x["status"]=="TIMEOUT" for x in a),
            PAR2_s=round(sum(x["E2E_s"] if accepted(x) else 2*CAP for x in a),6),
            actual_child_CPU_s=round(sum(x["child_CPU_s"] for x in a),6),
            individual=[dict(rep=x["rep"],status=x["status"],E2E_s=x["E2E_s"])
                        for x in sorted(a,key=lambda y:y["rep"])])
    report=dict(protocol=PROTO,gbd=TARGET_GBD,original_sha256=TARGET_SHA,
       previously_seen_formula_not_blind=True,independent_UNSAT_LRAT=False,
       sources=1,reps=REPS,trials=len(rows),cap_s=CAP,
       E2E_original_SAT_witness_verified=True,
       accepted_UNSAT_requires_two_original_backends=True,
       scores=scores,screen_summary=json.loads((ROOT/"screen-summary.json").read_text()),
       no_auto_promotion=True)
    save(ROOT/"report.json",report)
    print("EQUIV7_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","verify","selftest","screen","repro","audit"))
    p.add_argument("--rep",type=int,default=0)
    a=p.parse_args()
    if a.action=="repro":repro(a.rep)
    else:
        globals()[a.action]()
        if a.action=="verify":print("EQUIV7_VERIFY_PASS",flush=True)
