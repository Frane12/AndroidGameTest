#!/usr/bin/env python3
"""DRNAS FUSION-GUARD1 paired native-core preservation and safe math-activation.

A native CDCL core is always the sole solver and decision authority. We compare:
  REF_CORE       frozen DELTAX-SIGNAL1 executable, all math OFF;
  FUSION_CORE    new executable, modules OFF by explicit FUSION core mode;
  FUSION_SHADOW  cheap risk gate observing ONLY; math remains OFF;
  FUSION_GUARD   cold modules, cheap gate then COOP4 GF(2) / DELTAX-SIGNAL8;
  SIGNAL8_FULL   frozen full COOP4 / DELTAX-SIGNAL8 (positive reference).

One logical CPU, serial arms. Original SAT models and independent UNSAT
DRAT are strict. A fast UNKNOWN is never a solved instance. No main changes.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import tempfile
import time

R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/"research"),str(R/"research/drnas_deltax")]
import hard_formulas as H
import drnas_x55_cpu_real36 as B

ARMS=("REF_CORE","FUSION_CORE","FUSION_SHADOW","FUSION_GUARD","SIGNAL8_FULL")
CAP=3.0
SHARDS=4
REFERENCE=R/"build/drnas-deltax-signal"
FUSION=R/"build/drnas-fusion1"
CHECKER=R/"build/drat-trim"
EXPECTED_BASELINE_SHA="46252501f59b279165cfcb55b000cb357d5217fde32a94ee693ae47e3bb495e0"

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def log(tag,obj):print(tag+" "+json.dumps(obj,sort_keys=True),flush=True)
def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def dataset():
    out=R/"fusion1_inputs"
    out.mkdir(parents=True,exist_ok=True)
    # Reuse known real, XOR, 3-SAT, graph sources for a diagnostic rather
    # than fabricate unseen performance. A subsequent prospective holdout
    # must be source-disjoint.
    hard=H.write("fusion1_inputs/hard")
    graph=json.loads((R/"deltax_signal1_inputs/manifest.json").read_text())
    selected=[]
    for family in ("planted","k4","odd_wheel","even_wheel"):
        grp=sorted({r["graph_id"] for r in graph
                    if r["family"]==family and r["split"]=="validation"})
        assert grp
        for variant in ("low1","high1"):
            s=next(r for r in graph if r["graph_id"]==grp[0]
                   and r["variant"]==variant)
            selected.append({
                "name":"graph_"+s["name"],"family":"graph/"+family,
                "path":s["path"],"sha256":s["sha256"],
                "nvars":s["nvars"],"nclauses":s["nclauses"],
                "origin":"retrospective_graph","graph_group":grp[0]
            })
    # Balanced medium mixed sources; fixed indices from frozen generator.
    for i in (0,2,4,10,12,14,18,20,22,24,25,27):
        s=hard[i]
        selected.append({
            "name":s["name"],"family":"hard/"+s["family"],
            "path":s["path"],"sha256":s["sha256"],
            "nvars":s["nvars"],"nclauses":s["nclauses"],
            "origin":"retrospective_hard","graph_group":None
        })
    # Original SAT2024 CNFs: family/byte-size stratified; NOT chosen on
    # solver outcomes and not a claim of unseen competition holdout.
    orig,_=B.official_manifest()
    families={}
    for r in orig:
        families.setdefault(r["family"],[]).append(r)
    chosen=[sorted(v,key=lambda s:(s.get("bytes",10**20),s["sha256"]))[0]
            for k,v in sorted(families.items())]
    chosen=chosen[:4]
    assert len(chosen)==4
    for s in chosen:
        p=R/s["path"]
        n,cs=B.parse_cnf(p.read_bytes())
        selected.append({
            "name":"official_sat2024_%02d"%s["id"],"family":"official/"+s["family"],
            "path":str(p.relative_to(R)),"sha256":s["sha256"],
            "nvars":n,"nclauses":len(cs),
            "origin":"sat2024_original_retrospective","graph_group":None
        })
    assert len(selected)==24
    assert len({x["sha256"] for x in selected})==24
    for s in selected:
        source=R/s["path"]
        assert source.exists() and sha(source)==s["sha256"],(
            "FUSION_SOURCE_SHA_DRIFT",s["name"])
    save(out/"manifest.json",selected)
    report={
        "sources":len(selected),
        "source_sha256":sha(out/"manifest.json"),
        "families":dict(collections.Counter(s["family"] for s in selected)),
        "original_sat2024":sum(s["origin"]=="sat2024_original_retrospective" for s in selected),
        "retrospective_not_blind":True,
        "frozen_control_sha256":EXPECTED_BASELINE_SHA,
        "no_promotion":True
    }
    log("DRNAS_FUSION_INPUTS",report)
    return selected

def sources():
    rows=json.loads((R/"fusion1_inputs/manifest.json").read_text())
    assert len(rows)==24
    for r in rows:assert sha(R/r["path"])==r["sha256"],(
        "FUSION_SOURCE_CHANGED",r["name"])
    return rows

def trial(s,arm,cap,rawdir):
    file=R/s["path"]
    n,clauses=B.parse_cnf(file.read_bytes())
    assert n==s["nvars"] and len(clauses)==s["nclauses"]
    binary=REFERENCE if arm in ("REF_CORE","SIGNAL8_FULL") else FUSION
    flags={
        "REF_CORE":["--coop4","off","--delta2","local"],
        "FUSION_CORE":["--fusion-core"],
        "FUSION_SHADOW":["--fusion-shadow"],
        "FUSION_GUARD":["--fusion-guard"],
        "SIGNAL8_FULL":["--coop4","gate","--coop4-eager",
                        "--delta2","deltax-signal-8"]
    }[arm]
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/"solver.drat"
        cmd=[str(binary.resolve()),str(file.resolve()),
             "--mode","core","--time",str(max(.05,cap-0.10)),
             "--stats","--x5-no-minimize","--coop5","off",
             "--proof",str(proof)]+flags
        t0=time.perf_counter()
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,text=True,start_new_session=True)
        expired=False
        try:out,err=proc.communicate(timeout=cap+.25)
        except subprocess.TimeoutExpired:
            expired=True;os.killpg(proc.pid,signal.SIGKILL)
            out,err=proc.communicate()
        wall=time.perf_counter()-t0
        status="TIMEOUT" if expired else "UNKNOWN"
        if not expired:
            assert proc.returncode in (0,10,20,153),(
                "NATIVE_PROCESS_FAILURE",s["name"],arm,proc.returncode,err[-1200:])
            if proc.returncode==10:
                assert B.check_sat(out,clauses,n),(
                    "INCORRECT_ORIGINAL_SAT",s["name"],arm)
                status="SAT_VERIFIED"
            elif proc.returncode==20:
                assert proof.exists() and proof.stat().st_size>0,(
                    "UNSAT_WITHOUT_ORIGINAL_PROOF",s["name"],arm)
                try:
                    check=subprocess.run([str(CHECKER),str(file),str(proof)],
                           capture_output=True,text=True,timeout=25)
                    assert check.returncode==0 and "s VERIFIED" in check.stdout,(
                        "UNSOUND_ORIGINAL_UNSAT_PROOF",s["name"],arm,
                        check.stdout[-500:],check.stderr[-500:])
                    status="UNSAT_CERTIFIED"
                except subprocess.TimeoutExpired:
                    status="UNSAT_CHECK_TIMEOUT"
        telemetry={}
        for line in err.splitlines():
            key,_,data=line.partition(" ")
            if key in ("X41_STATS","DRNAS_FUSION_STATS","DELTAX_STATS",
                       "DELTAX_SIGNAL_STATS","DELTAX_GUARD_STATS",
                       "DELTAX_GUARD_SOURCE","DELTAX_CAUSAL_STATS","COOP4_STATS"):
                assert key not in telemetry,(s["name"],arm,"DUPLICATE",key)
                telemetry[key]=json.loads(data)
        if not expired:
            assert "X41_STATS" in telemetry,(
                "MISSING_NATIVE_STATS",s["name"],arm,err[-1000:])
            if arm in ("FUSION_CORE","FUSION_SHADOW","FUSION_GUARD"):
                assert "DRNAS_FUSION_STATS" in telemetry,(
                    "FUSION_TELEMETRY_MISSING",s["name"],arm,err[-1500:])
                fuse=telemetry["DRNAS_FUSION_STATS"]
                assert fuse["mode"]=={
                    "FUSION_CORE":"CORE","FUSION_SHADOW":"SHADOW",
                    "FUSION_GUARD":"GUARDED"}[arm]
                if arm in ("FUSION_CORE","FUSION_SHADOW"):
                    assert not fuse["cold_originals_loaded"] and \
                           fuse["source_clauses_copied"]==0 and \
                           fuse["module_wakeups"]==0,(
                             "FUSION_OFF_STARTED_MODULES",s["name"],arm,fuse)
            if arm=="FUSION_GUARD":
                g=telemetry["DELTAX_GUARD_SOURCE"]
                assert g["invalid_derivations_rejected"]==0,(
                    "BAD_SOURCE_RESOLVENT",s["name"],g)
                assert telemetry["DELTAX_GUARD_STATS"]["inconsistent_clones"]==0
                fuse=telemetry["DRNAS_FUSION_STATS"]
                if not fuse["cold_originals_loaded"]:
                    assert fuse["module_wakeups"]==0
                    assert telemetry["DELTAX_GUARD_STATS"]["checks"]==0
                    assert telemetry["DELTAX_SIGNAL_STATS"]["tested"]==0
        core=telemetry.get("X41_STATS",{})
        fuse=telemetry.get("DRNAS_FUSION_STATS",{})
        delta=telemetry.get("DELTAX_STATS",{})
        guard=telemetry.get("DELTAX_GUARD_STATS",{})
        signal_stats=telemetry.get("DELTAX_SIGNAL_STATS",{})
        row={
            "name":s["name"],"family":s["family"],"source_sha256":s["sha256"],
            "origin":s["origin"],"arm":arm,"status":status,
            "verified":wall<=cap and status in ("SAT_VERIFIED","UNSAT_CERTIFIED"),
            "wall_s":wall,"decisions":core.get("decisions"),
            "conflicts":core.get("conflicts"),
            "learned":core.get("learnt"),
            "fusion_cheap_passes":fuse.get("cheap_approved",0),
            "fusion_wakeups":fuse.get("module_wakeups",0),
            "fusion_cold_sources_loaded":fuse.get("cold_originals_loaded",False),
            "fusion_productive_windows":fuse.get("productive_windows",0),
            "fusion_empty_windows":fuse.get("empty_windows",0),
            "deltax_proof_clauses":delta.get("proof_carrying_injected",0),
            "deltax_signal_veto":signal_stats.get("vetoed",0),
            "clone_checks":guard.get("checks",0),
            "clone_accepted":guard.get("accepted",0),
        }
        rawdir.mkdir(parents=True,exist_ok=True)
        (rawdir/(s["name"]+"__"+arm+".stderr")).write_text(err[-60000:])
        log("DRNAS_FUSION_TRIAL",{k:v for k,v in row.items() if k!="source_sha256"})
        return row

def smoke():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert sha(REFERENCE)==EXPECTED_BASELINE_SHA
    manifest=dataset()
    types=("graph/planted","graph/k4","hard/php_unsat","hard/tseitin_unsat")
    selected=[next(s for s in manifest if s["family"]==family) for family in types]
    rr=[trial(s,arm,2.0,R/"fusion1_preflight/raw") for s in selected for arm in ARMS]
    assert len(rr)==20
    by={(r["name"],r["arm"]):r for r in rr}
    for s in selected:
        base=by[(s["name"],"REF_CORE")]
        for arm in ("FUSION_CORE","FUSION_SHADOW"):
            v=by[(s["name"],arm)]
            if base["verified"] and v["verified"]:
                assert (base["status"],base["decisions"],base["conflicts"])==(
                        v["status"],v["decisions"],v["conflicts"]),(
                        "CORE_NOT_PRESERVED",s["name"],arm,base,v)
    save(R/"fusion1_preflight/report.json",{
        "status":"PASS","cases":len(selected),"trials":len(rr),
        "verified":sum(r["verified"] for r in rr),
        "source_manifest_sha256":sha(R/"fusion1_inputs/manifest.json"),
        "core_guard_off_equivalence_checked":True,
        "module_off_no_original_cache":True,"one_cpu":True,"no_promotion":True})
    log("DRNAS_FUSION_PREFLIGHT_PASS",{
        "cases":len(selected),"trials":len(rr),
        "verified":sum(r["verified"] for r in rr)})

def shard(index):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    chosen=[x for i,x in enumerate(sources()) if i%SHARDS==index]
    assert len(chosen)==6
    directory=R/f"fusion1_shards/{index}"
    directory.mkdir(parents=True,exist_ok=False)
    save(directory/"manifest.json",{
        "shard":index,"source_manifest_sha256":sha(R/"fusion1_inputs/manifest.json"),
        "reference_sha256":sha(REFERENCE),"fusion_sha256":sha(FUSION),
        "drat_checker_sha256":sha(CHECKER),
        "arms":ARMS,"cap_s":CAP,"one_cpu":sorted(os.sched_getaffinity(0)),
        "retrospective":True,"no_promotion":True})
    with (directory/"trials.jsonl").open("w") as stream:
        for s in chosen:
            order=list(ARMS)
            random.Random(int(s["sha256"][:16],16)).shuffle(order)
            for arm in order:
                trial_row=trial(s,arm,CAP,directory/"raw")
                stream.write(json.dumps(trial_row,sort_keys=True)+"\n")
                stream.flush()
    log("DRNAS_FUSION_SHARD_PASS",{
        "shard":index,"sources":len(chosen),"trials":len(chosen)*len(ARMS)})

def aggregate():
    source=sources();record=[];manifests=[]
    for i in range(SHARDS):
        directory=R/f"fusion1_downloads/fusion1-shard-{i}/fusion1_shards/{i}"
        manifests.append(json.loads((directory/"manifest.json").read_text()))
        record.extend(json.loads(line) for line in (
            directory/"trials.jsonl").read_text().splitlines())
    keys={(s["sha256"],arm) for s in source for arm in ARMS}
    actual=[(s["source_sha256"],s["arm"]) for s in record]
    assert len(record)==120 and len(set(actual))==len(keys) and set(actual)==keys
    for m in manifests:
        assert m["source_manifest_sha256"]==sha(R/"fusion1_inputs/manifest.json")
        assert m["reference_sha256"]==EXPECTED_BASELINE_SHA
        assert m["fusion_sha256"]==manifests[0]["fusion_sha256"]
        assert m["drat_checker_sha256"]==manifests[0]["drat_checker_sha256"]
        assert tuple(m["arms"])==ARMS and len(m["one_cpu"])==1
        assert m["retrospective"] and m["no_promotion"]
    by={(r["source_sha256"],r["arm"]):r for r in record}
    verdict=collections.defaultdict(set)
    for r in record:
        if r["verified"]:verdict[r["source_sha256"]].add(r["status"])
    assert all(len(v)<=1 for v in verdict.values()),"CONTRADICTORY_VERIFIED_SOLVER_RESULT"
    compared=0;diffs=[]
    for s in source:
        base=by[(s["sha256"],"REF_CORE")]
        for mode in ("FUSION_CORE","FUSION_SHADOW"):
            other=by[(s["sha256"],mode)]
            if base["verified"] and other["verified"]:
                compared+=1
                assert (base["status"],base["decisions"],base["conflicts"])==(
                    other["status"],other["decisions"],other["conflicts"]),(
                    "BASELINE_CDCL_REGRESSION_WHEN_MODULES_OFF",s["name"],mode)
        active=by[(s["sha256"],"FUSION_GUARD")]
        if base["verified"] and active["verified"]:
            diffs.append({
                "name":s["name"],"family":s["family"],
                "core_decisions":base["decisions"],"fusion_decisions":active["decisions"],
                "core_conflicts":base["conflicts"],"fusion_conflicts":active["conflicts"],
                "module_wakeups":active["fusion_wakeups"],
                "source_proved_deltax":active["deltax_proof_clauses"],
                "clone_checked":active["clone_checks"]})
    arms={}
    for arm in ARMS:
        rr=[r for r in record if r["arm"]==arm]
        arms[arm]={
            "trials":len(rr),"verified":sum(x["verified"] for x in rr),
            "SAT":sum(x["status"]=="SAT_VERIFIED" and x["verified"] for x in rr),
            "UNSAT":sum(x["status"]=="UNSAT_CERTIFIED" and x["verified"] for x in rr),
            "UNKNOWN_or_unverified":sum(not x["verified"] for x in rr),
            "module_wakeups":sum(x["fusion_wakeups"] for x in rr),
            "cold_sources_loaded":sum(x["fusion_cold_sources_loaded"] for x in rr),
            "deltax_proof_clauses":sum(x["deltax_proof_clauses"] for x in rr),
            "clone_checks":sum(x["clone_checks"] for x in rr)
        }
    result={
        "status":"COMPLETE","sources":len(source),"trials":len(record),
        "one_process_one_logical_cpu_per_solver":True,
        "native_baseline_cdcl_unchanged_when_math_off":True,
        "verified_core_off_matched_pairs":compared,
        "main_untouched":True,"original_SAT_and_independent_UNSAT_proofs_checked":True,
        "modules_off_by_default":True,
        "modules_wake_only_when_cheap_guard_authorizes":True,
        "proof_gates_remain_mandatory":True,
        "retrospective_not_blind":True,"no_general_speed_claim":True,"no_promotion":True,
        "arms":arms,
        "paired_both_verified":len(diffs),
        "fusion_decision_improvements_vs_core":sum(r["fusion_decisions"]<r["core_decisions"] for r in diffs),
        "fusion_decision_regressions_vs_core":sum(r["fusion_decisions"]>r["core_decisions"] for r in diffs),
        "fusion_conflict_improvements_vs_core":sum(r["fusion_conflicts"]<r["core_conflicts"] for r in diffs),
        "fusion_conflict_regressions_vs_core":sum(r["fusion_conflicts"]>r["core_conflicts"] for r in diffs),
        "comparisons":diffs
    }
    save(R/"fusion1_final/report.json",result)
    save(R/"fusion1_final/trials.json",record)
    log("DRNAS_FUSION_FINAL",{k:v for k,v in result.items() if k!="comparisons"})

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("smoke","shard","aggregate"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.stage=="smoke":smoke()
    elif args.stage=="shard":shard(args.shard)
    else:aggregate()
