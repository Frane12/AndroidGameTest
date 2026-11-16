#!/usr/bin/env python3
"""IPG4 source-frozen non-scalar Petersen dual formal proof audit.

Two COMPLEMENTARY independent VeriPB 3.0.2 checks:
 A. A mathematical graph-matching/odd-cycle RUP proof (59 clauses)
    against a generated 45v/150c edge-coloring CNF.
 B. A fresh, fully checked native MG7-CDCL RUP trace converted verbatim
    (not heuristically) into standard PB-RUP, and independently checked
    against the *original* 45v/300c weighted PCMAX CNF.

The generator ALSO proves from source that six weight-feasible Petersen
matchings, each incident twice per job, make ALL nonnegative weighted
capacity separation inequalities impossible. The proof does not rely
on any floating-point LP approximation or an expected UNSAT label.

This is NOT a full 3D-IPG-to-VeriPB compiler or polynomial general PCMAX.
The direct-original VeriPB trace is derived from CDCL; the parity-guided
proof is for a separately source-checked mathematically equivalent encoding.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg4_nonscalar_petersen"
GRAPH_PRODUCER=ROOT/"research/ipg4_petersen_parity_proof.py"
GAP_CHECKER=ROOT/"research/ipg4_fractional_gap_checker.py"
CONVERTER=ROOT/"research/ipg4_rup_drat_to_veripb.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
DRAT_CHECK=ROOT/"drat-trim/drat-trim"
NATIVE=ROOT/"build/drnas-mg7-scc"
SOURCE_SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"
sys.path.insert(0,str(ROOT/"research"))
from ipg1_fixtures import petersen

def invoke(args,timeout=80):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(a) for a in args],capture_output=True,
                         text=True,timeout=timeout)
        return p.returncode,round(time.perf_counter()-start,6),p.stdout or "",p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-start,6),"","TIMEOUT"

def record(path,args,timeout=80):
    rc,sec,out,err=invoke(args,timeout)
    path.write_text(out+"\n"+err)
    return rc,sec,out+"\n"+err

def require(ok,msg):
    if not ok:raise AssertionError(msg)

def verify_pbp(label,source,proof):
    rc,t,out=record(OUT/(label+".veripb.log"),
                    [VERIPB,"--cnf",source,proof],90)
    return {
        "veripb_rc":rc,
        "veripb_checker_s":t,
        "veripb_verified":rc==0 and "s VERIFIED UNSATISFIABLE" in out,
        "pbp_bytes":proof.stat().st_size,
    }

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    weighted=OUT/"petersen_weighted_original_45v300c.cnf"
    weighted.write_bytes(petersen().encode("ascii"))
    require(hashlib.sha256(weighted.read_bytes()).hexdigest()==SOURCE_SHA,
            "native weighted input byte identity mismatch")
    graph=OUT/"petersen_graph_edge_coloring_45v150c.cnf"
    graph_pb=OUT/"petersen_graph_PARITY_59rup.pbp"
    fraction=OUT/"petersen_non_scalar_gap.json"
    graph_meta=OUT/"petersen_graph_proof_meta.json"
    gc,gt,gout=record(OUT/"graph_producer.log",
        [sys.executable,GRAPH_PRODUCER,
         "--weighted-original",weighted,"--graph-cnf",graph,
         "--veripb",graph_pb,"--fractional-certificate",fraction,
         "--meta",graph_meta],25)
    require(gc==0 and graph.exists() and graph_pb.exists(),
            "parity graph proof generation failed")
    source_check,source_time,source_log=record(
        OUT/"independent_fractional_source.log",
        [sys.executable,GAP_CHECKER,
         "--weighted-cnf",weighted,"--graph-cnf",graph,
         "--fractional-certificate",fraction],25)
    require(source_check==0 and "IPG4_GAP_ACCEPT " in source_log,
            "independent non-scalar/original-to-graph source verification failed")
    parity_pb=verify_pbp("graph_parity",graph,graph_pb)
    require(parity_pb["veripb_verified"],"external VeriPB rejected source odd-cycle parity proof")
    graph_info=json.loads(graph_meta.read_text())
    require(graph_info["RUP_steps"]==59,"unexpected parity proof steps")

    drat=OUT/"petersen_weighted_native_mg7.drat"
    drat_r,drat_s,drat_out=record(OUT/"native_mg7.log",
        [NATIVE,weighted,"--mode","core","--time","5",
         "--residual-scc","--proof",drat,"--stats"],9)
    require(drat_r==20 and "s UNSATISFIABLE" in drat_out and
            drat.exists() and drat.stat().st_size>0,
            "native MG7 did not produce original weighted UNSAT DRAT source trace")
    check_rc,check_time,check_log=record(
        OUT/"independent_drat_trim.log",
        [DRAT_CHECK,weighted,drat],30)
    require(check_rc==0 and "s VERIFIED" in check_log,
            "original weighted source DRAT independently rejected")

    weighted_pb=OUT/"petersen_WEIGHTED_original_VerIPB_from_RUP.pbp"
    convert_meta=OUT/"weighted_rup_conversion.json"
    cv,cv_s,cvlog=record(OUT/"weighted_rup_conversion.log",
        [sys.executable,CONVERTER,"--cnf",weighted,"--drat",drat,
         "--veripb",weighted_pb,"--meta",convert_meta],40)
    require(cv==0 and weighted_pb.exists(),
            "fresh weighted DRAT trace is not all-RUP or converter failed")
    weighted_veripb=verify_pbp("original_weighted",weighted,weighted_pb)
    require(weighted_veripb["veripb_verified"],
            "external VeriPB rejected original weighted 300-clause PB proof")
    converted=json.loads(convert_meta.read_text())

    # Check failing source bindings. Original source cannot be silently
    # replaced with a same-name CNF, even by adding a harmless comment.
    modified=OUT/"modified_original.cnf"
    modified.write_bytes(weighted.read_bytes()+b"c changed source bytes\n")
    m_rc,_,_=record(OUT/"tamper_weighted.log",
        [sys.executable,CONVERTER,"--cnf",modified,"--drat",drat,
         "--veripb",OUT/"invalid_weighted.pbp",
         "--meta",OUT/"invalid_weighted.json"],20)
    require(m_rc!=0 and not (OUT/"invalid_weighted.pbp").exists(),
            "converter accepted mutated source SHA")
    corrupted=json.loads(fraction.read_text())
    corrupted["perfect_matching_configurations"]=[]
    corrupted_file=OUT/"forged_fractional_gap.json"
    corrupted_file.write_text(json.dumps(corrupted)+"\n")
    f_rc,_,_=record(OUT/"tamper_fractional.log",
        [sys.executable,GAP_CHECKER,"--weighted-cnf",weighted,
         "--graph-cnf",graph,"--fractional-certificate",corrupted_file],20)
    require(f_rc!=0,"independent mathematical checker accepted forged fractional certificate")

    summary={
        "status":"PASS",
        "weighted_original_sha256":SOURCE_SHA,
        "weighted_original_vars":45,
        "weighted_original_clauses":300,
        "edge_coloring_vars":45,
        "edge_coloring_clauses":150,
        "nonnegative_scalar_separation_possible":False,
        "perfect_matchings":6,
        "fractional_coverage_per_job":2,
        "integer_3_machine_UNSAT":True,
        "mathematical_gap_independently_checked":True,
        "graph_parity_RUP_steps":graph_info["RUP_steps"],
        "graph_oddcycle_matching_cases":graph_info["odd_cycle_parity_witnesses"],
        "graph_veripb":parity_pb,
        "graph_producer_s":gt,
        "original_mg7_drat_bytes":drat.stat().st_size,
        "original_mg7_drat_time_s":drat_s,
        "original_drat_trim_s":check_time,
        "original_verified_RUP_steps":converted["all_RUP_steps_locally_replayed"],
        "original_VerIPB":weighted_veripb,
        "original_RUP_converter_s":cv_s,
        "source_gap_checker_s":source_time,
        "tamper_source_rejected":m_rc!=0,
        "tamper_fractional_cert_rejected":f_rc!=0,
        "scope":"The graph proof is explicitly odd-cycle/parity-guided. The original weighted PB proof is native CDCL-RUP translated to VeriPB and NOT produced by IPG1/IPG-BDD3. This does not claim polynomial general PCMAX or a general 3D cutting-plane compiler.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("IPG4_NONSCALAR_VERIPB_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (AssertionError,ValueError,KeyError,OSError) as e:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/"failure.json").write_text(json.dumps({"status":"FAIL","reason":str(e)})+"\n")
        print("IPG4_NONSCALAR_FAILED "+str(e),flush=True)
        raise SystemExit(1)
