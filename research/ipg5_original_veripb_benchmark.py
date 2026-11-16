#!/usr/bin/env python3
"""IPG5: ORIGINAL weighted Petersen PCMAX -> VeriPB WITHOUT invoking CDCL.

A. SHA-frozen original CNF (45v,300c); 90 derived graph mutex clauses;
   independent 59-step Petersen parity proof appended.
B. Externally verify the source RUP trace with drat-trim.
C. Independently replay every RUP clause and convert to standard VeriPB3.
D. Externally verify entire VeriPB trace on unchanged original CNF.
E. Independently reconstruct the 300-clause source and graph fractional
   obstruction; reject tampered source / truncated RUP / SAT control.
No SAT solver process is invoked. Source-informed DPLL branching is bounded
and EXPONENTIAL in general, so this is NOT a polynomial PCMAX breakthrough.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg5_original"
GEN=ROOT/"research/ipg5_structural_original_rup.py"
CONV=ROOT/"research/ipg5_rup_to_veripb.py"
GAP=ROOT/"research/ipg4_fractional_gap_checker.py"
DRAT=ROOT/"drat-trim/drat-trim"
VERIPB=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research"))
from ipg1_fixtures import petersen,pack

def cmd(args,timeout=90):
    start=time.perf_counter()
    try:
        result=subprocess.run(list(map(str,args)),capture_output=True,text=True,
                              timeout=timeout)
        return result.returncode,round(time.perf_counter()-start,6),result.stdout+"\n"+result.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-start,6),"TIMEOUT"

def execute(name,args,timeout=90):
    rc,s,out=cmd(args,timeout)
    (OUT/(name+".log")).write_text(out)
    return rc,s,out

def require(x,reason):
    if not x:raise AssertionError(reason)

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    original=OUT/"original_weighted_45v300c.cnf"
    original.write_bytes(petersen().encode("ascii"))
    source_sha=hashlib.sha256(original.read_bytes()).hexdigest()
    require(source_sha=="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70",
            "original SHA-256 mismatch")
    graph=OUT/"equivalent_graph_45v150c.cnf"
    rup=OUT/"IPG5_DIRECT_ORIGINAL_NO_CDCL.rup"
    frac=OUT/"fractional_gap_source_bound.json"
    meta=OUT/"native_source_generator.json"
    rc,gen_s,out=execute("source_generator",[
        sys.executable,GEN,"--original",original,"--graph-out",graph,
        "--rup-out",rup,"--metadata",meta,"--fractional",frac],60)
    require(rc==0 and rup.exists() and graph.exists(),"source guided proof generation failed")
    gen=json.loads(meta.read_text())
    require(gen["total_graph_mutex_clauses"]==90 and
            gen["missing_graph_mutex_derived"]+gen["graph_mutex_already_original"]==90 and
            gen["odd_cycle_parity_RUP_steps"]==59,
            "original->graph parity structural bridge incomplete")
    require(gen["source_sha256"]==source_sha,"generator source hash mismatch")

    rc,gap_s,out=execute("source_equivalence_check",[
        sys.executable,GAP,"--weighted-cnf",original,
        "--graph-cnf",graph,"--fractional-certificate",frac],35)
    require(rc==0 and "IPG4_GAP_ACCEPT " in out,
            "independent source->graph/fractional proof checker rejected")
    rc,drat_s,out=execute("independent_DRAT_trim",[
        DRAT,original,rup],60)
    require(rc==0 and "s VERIFIED" in out,
            "independent DRAT-trim rejected original source parity trace")

    pb=OUT/"IPG5_ORIGINAL_DIRECT_VERIPB_3_0.pbp"
    meta2=OUT/"independent_rup_replay.json"
    rc,replay_s,out=execute("independent_source_rup_replay",[
        sys.executable,CONV,"--original",original,"--rup",rup,
        "--veripb",pb,"--metadata",meta2],120)
    require(rc==0 and pb.exists(),"independent RUP step replay/VeriPB conversion failed")
    reviewed=json.loads(meta2.read_text())
    require(reviewed["rup_steps_replayed"]==gen["RUP_steps_locally_replayed"],
            "independent replay step count mismatch")
    rc,veripb_s,out=execute("independent_VerIPB_3_0_2",[
        VERIPB,"--cnf",original,pb],120)
    require(rc==0 and "s VERIFIED UNSATISFIABLE" in out,
            "independent VeriPB 3.0.2 rejected direct original non-CDCL proof")

    # Adversarial input/proof mutations. Never rely on the source filename.
    modified=OUT/"tampered_original.cnf"
    modified.write_bytes(original.read_bytes()+b"c altered source bytes\n")
    badrup=OUT/"invalid_source.rup"
    rc,_,_=execute("tampered_original_rejection",[
        sys.executable,GEN,"--original",modified,
        "--graph-out",OUT/"bad_graph.cnf","--rup-out",badrup,
        "--metadata",OUT/"bad_meta.json","--fractional",OUT/"bad_frac.json"],20)
    require(rc!=0 and not badrup.exists(),"tampered source got a proof")
    steps=rup.read_text().splitlines()
    require(steps and steps[-1].strip()=="0","no terminal empty clause")
    truncated=OUT/"truncated_trace.rup"
    truncated.write_text("\n".join(steps[:-1])+"\n")
    badpb=OUT/"invalid_truncated.pbp"
    rc,_,_=execute("truncated_trace_rejection",[
        sys.executable,CONV,"--original",original,
        "--rup",truncated,"--veripb",badpb,
        "--metadata",OUT/"bad_trace_meta.json"],30)
    require(rc!=0 and not badpb.exists(),"truncated RUP was accepted")
    # In scope only for exact Petersen-source family. A SAT input must
    # produce no proof, not an overconfident structural conclusion.
    nv,controls=pack(6,2)
    sat=OUT/"independent_SAT_control.cnf"
    sat.write_text(f"p cnf {nv} {len(controls)}\n"+
        "".join(" ".join(map(str,c))+" 0\n" for c in controls))
    failrup=OUT/"sat_fake.rup"
    rc,_,_=execute("SAT_control_rejection",[
        sys.executable,GEN,"--original",sat,
        "--graph-out",OUT/"sat_fake_graph.cnf",
        "--rup-out",failrup,"--metadata",OUT/"sat_fake_meta.json",
        "--fractional",OUT/"sat_fake_frac.json"],20)
    require(rc!=0 and not failrup.exists(),"SAT control got false UNSAT")
    summary={
        "status":"PASS",
        "original_source_sha256":source_sha,
        "original_variables":45,"original_clauses":300,
        "new_source_graph_mutex_lemmas":gen["missing_graph_mutex_derived"],
        "original_graph_mutex_already_present":gen["graph_mutex_already_original"],
        "structural_DPLL_branch_nodes":gen["lemma_tree_nodes"],
        "structural_source_RUP_steps":gen["graph_mutex_RUP_steps"],
        "parity_RUP_steps":gen["odd_cycle_parity_RUP_steps"],
        "total_original_source_RUP_steps":gen["RUP_steps_locally_replayed"],
        "generator_no_CDCL":True,
        "source_generator_s":gen_s,
        "independent_fractional_gap_verified":True,
        "independent_gap_checker_s":gap_s,
        "independent_drat_verified":True,
        "drat_checker_s":drat_s,
        "independent_RUP_replay_verified":True,
        "rup_replay_s":replay_s,
        "external_veripb_verified":True,
        "veripb_checker_s":veripb_s,
        "rup_bytes":rup.stat().st_size,"veripb_bytes":pb.stat().st_size,
        "source_tamper_rejected":True,
        "truncated_proof_rejected":True,
        "sat_control_rejected":True,
        "scope":"Non-CDCL mathematically guided DPLL source lemma construction + odd-cycle parity, standard VeriPB original source. Bounded EXPONENTIAL search, NOT polynomial general PCMAX or generic IPG-BDD3 converter.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("IPG5_DIRECT_ORIGINAL_VERIPB "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError,AssertionError,KeyError,TypeError) as error:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/"failure.json").write_text(json.dumps({"status":"FAIL","reason":str(error)})+"\n")
        print("IPG5_BENCHMARK_FAILED "+str(error),flush=True)
        sys.exit(1)
