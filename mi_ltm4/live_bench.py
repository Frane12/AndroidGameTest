"""LTM4.1 native-passive trace pilot: actual CDCL events + certified XOR motifs.

Runs stock and instrumented binaries sequentially with the SAME source CNF,
seed and 1CPU limits. Trace-side output is diagnostic: tracing overhead and
offline motif detection must NOT be presented as an LTM speedup or fair PAR2.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import statistics
import subprocess
import sys
import time
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"mi_ltm1"))  # legacy native_paired absolute imports
from mi_ltm3.design import FAMILIES,make_case,satisfies,source_parity_unsat
from mi_ltm1.native_paired import parse_model
from mi_ltm4.live_cdcl import parse_native_log,aggregate_by_formula
from mi_ltm4.trajectory import extract
from mi_ltm4.live_store import NativeTraceMemory,recognize

BIN=ROOT/"mre_atlas15/bin/drnas_atlas15"
TRACE_BIN=ROOT/"mre_atlas15/bin/drnas_atlas15_trace"
CAP_S=2.0
MEM=2*1024**3


def run_binary(binary,case,rep,tmp):
    seed=int.from_bytes(hashlib.sha256(
        ("%s/%d"%(case["sha"],rep)).encode()).digest()[:8],"big")
    p=tmp/("source_"+case["sha"][:16]+".cnf")
    if not p.exists():
        p.write_text(case["raw"])
    argv=[str(binary),str(p),"--mode","A","--time",str(CAP_S),
          "--seed",str(seed)]
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(CAP_S)+1,
                                               math.ceil(CAP_S)+2))
        resource.setrlimit(resource.RLIMIT_AS,(MEM,MEM))
    started=time.perf_counter()
    try:
        proc=subprocess.run(argv,text=True,stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,timeout=CAP_S+0.25,
                            preexec_fn=limit,check=False)
        elapsed=time.perf_counter()-started
        rc=proc.returncode
        out=proc.stdout
        log=proc.stderr
    except subprocess.TimeoutExpired:
        return dict(status="UNKNOWN",verified=False,elapsed_s=time.perf_counter()-started,
                    native_exit=0,stderr="",reason="wall_timeout")
    if rc not in (0,10,20):
        raise RuntimeError("Native trace binary failure rc=%d %s"%(rc,log[-1200:]))
    if elapsed>CAP_S+0.25:
        rc=0
    if rc==10:
        if case["expect"]!="SAT_PLANTED":
            raise AssertionError("SAT contradicts independent XOR source")
        model=parse_model(out)
        if len(model)!=case["n"] or not satisfies(case["clauses"],model):
            raise AssertionError("SAT witness invalid on original CNF")
        status="SAT_ORIGINAL_VERIFIED"
    elif rc==20:
        valid, _=source_parity_unsat(case["clauses"])
        if case["expect"]!="UNSAT_GF2_PROVEN" or not valid:
            raise AssertionError("UNSAT not independently source-proven")
        status="UNSAT_SOURCE_GF2_VERIFIED"
    else:
        status="UNKNOWN"
    return dict(status=status,verified=status!="UNKNOWN",
                elapsed_s=round(elapsed,7),native_exit=rc,
                stderr=log, reason="completed")


def run(*,rep=0,smoke=True,generation=1):
    if not BIN.exists() or not TRACE_BIN.exists():
        raise FileNotFoundError("Build BOTH normal and MICRO_TRACE native binaries")
    # Every family contributes a distinct training and SHA-disjoint holdout.
    indices=(0,32) if smoke else (0,1,2,3,32,33,34,35)
    cases=[make_case(f,i,generation=generation if i<32 else 0)
           for f in FAMILIES for i in indices]
    cases.sort(key=lambda c:c["case"]>=32)  # all training before sealed holdout
    train_shas={c["sha"] for c in cases if c["case"]<32}
    holdout_shas={c["sha"] for c in cases if c["case"]>=32}
    assert train_shas.isdisjoint(holdout_shas)
    items=[]
    memory=NativeTraceMemory(ROOT/"mi_ltm4/native_training.sqlite")
    frozen=None
    holdout_recognized=0
    holdout_cross=0
    with TemporaryDirectory() as td:
        tmp=Path(td)
        for idx,case in enumerate(cases,1):
            # Native trace is measured separately, never used as speed claim.
            base=run_binary(BIN,case,rep,tmp)
            traced=run_binary(TRACE_BIN,case,rep,tmp)
            native=parse_native_log(traced["stderr"])
            algebra=extract(case["raw"])
            # Cross-representation intersection: observation only.
            algebraic=set(e["key"] for e in algebra["episodes"])
            cdcl=set(e["key"] for e in native["episodes"])
            if case["case"]<32:
                memory.remember(case["sha"],native,algebraic)
                recognition=None
            else:
                if frozen is None:
                    frozen=memory.freeze(holdout_shas)
                    memory.close()
                recognition=recognize(frozen,native,algebraic)
                holdout_recognized+=int(recognition["matched_native_motifs"]>0)
                holdout_cross+=recognition["matched_cross_patterns"]
            item=dict(sha256=case["sha"],family=case["family"],case=case["case"],
                      split="train" if case["case"]<32 else "holdout",
                      base_status=base["status"],
                      traced_status=traced["status"],
                      base_e2e_s=base["elapsed_s"],
                      trace_e2e_s=traced["elapsed_s"],
                      trace=native,
                      algebraic_motif_keys=sorted(algebraic),
                      algebraic_motifs=len(algebraic),
                      native_cdcl_motifs=len(cdcl),
                      joint_motif_pairs=len(algebraic)*len(cdcl),
                      trace_reason_graph_episodes=native["reason_graph_conflicts"],
                      cross_method_link="cooccurrence_only_not_causal",
                      holdout_recognition=recognition)
            items.append(item)
            print("MI_LTM41_TRIAL",json.dumps({
                "family":item["family"],"split":item["split"],
                "base_status":item["base_status"],
                "trace_status":item["traced_status"],
                "cdcl_events":native["total_native_micro_events"],
                "episodes":len(native["episodes"]),
                "reason_graphs":native["reason_graph_conflicts"],
                "algebraic_motifs":item["algebraic_motifs"]},sort_keys=True),
                flush=True)
    if frozen is None:
        frozen=memory.freeze(holdout_shas)
        memory.close()
    support=aggregate_by_formula(items)
    by_family={}
    for family in FAMILIES:
        selected=[i for i in items if i["family"]==family]
        by_family[family]=dict(
            formulas=len(selected),
            trace_episodes=sum(len(i["trace"]["episodes"]) for i in selected),
            trace_reason_graphs=sum(i["trace_reason_graph_episodes"] for i in selected),
            algebraic_motifs=sum(i["algebraic_motifs"] for i in selected))
    report=dict(project="DRNAS MI-LTM4.1 actual native trace",
                version=1,one_logical_cpu=True,rep=rep,
                cap_s=CAP_S,trace_cap_events=10000,
                source_sha_disjoint=True,training_generation=generation,
                frozen_memory_before_holdout=True,
                historical_training_sources=frozen["training_formula_count"],
                historical_native_motifs=len(frozen["native_support"]),
                historical_cross_patterns=len(frozen["cross_support"]),
                frozen_memory_sha256=frozen["snapshot_sha256"],
                holdout_formulas_recognized=holdout_recognized,
                holdout_cross_pattern_matches=holdout_cross,
                train_source_count=len(train_shas),
                holdout_source_count=len(holdout_shas),
                native_trace_motif_summary=support,
                same_verified_statuses=sum(i["base_status"]==i["traced_status"]
                                            for i in items),
                formulas=len(items),by_family=by_family,
                note="Trace is passive. Does not change CDCL and never learns from holdout.",
                performance_warning=("Trace build adds stderr overhead. BASE vs TRACE "
                  "time is NOT a speedup test. Offline XOR motif matching is outside "
                  "native E2E. No LTM4-controlled solver arm yet."),
                caveats=[
                  "Reason graph logged only for native n<=50, conflicts <=5 or 16..20",
                  "Temporal event episodes are not derivation certificates",
                  "No live cross-method routing or causal intervention",
                  "Only generated synthetic medium source CNFs",
                  "Native UNSAT source GF2 verified, not LRAT"],
                trials=items)
    name="MI_LTM41_SMOKE.json" if smoke else "MI_LTM41_FINAL.json"
    (ROOT/name).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MI_LTM41_FINAL",json.dumps({
        "formulas":len(items),"sha_disjoint":True,
        "native_motifs":support["unique_native_motifs"],
        "trace_episodes":sum(len(i["trace"]["episodes"]) for i in items),
        "reason_graphs":sum(i["trace_reason_graph_episodes"] for i in items),
        "matching_native_status":report["same_verified_statuses"],
        "historical_training_sources":report["historical_training_sources"],
        "historical_native_motifs":report["historical_native_motifs"],
        "holdout_formulas_recognized":holdout_recognized,
        "holdout_cross_pattern_matches":holdout_cross,
        "by_family":by_family,
        "performance_warning":report["performance_warning"]},
        sort_keys=True),flush=True)
    return report


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--full",action="store_true")
    parser.add_argument("--rep",type=int,default=0)
    parser.add_argument("--generation",type=int,
                        default=int(os.environ.get("GITHUB_RUN_NUMBER","1")))
    args=parser.parse_args()
    run(smoke=not args.full,rep=args.rep,generation=args.generation)
