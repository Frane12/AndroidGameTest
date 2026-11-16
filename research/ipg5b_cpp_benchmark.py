#!/usr/bin/env python3
"""IPG5-B source-frozen C++ ternary-job proof vs previous IPG5-A DPLL.

ONE logical CPU, serial, no CDCL solver invoked. Native proof claims
are independently checked on ORIGINAL CNF with DRAT-TRIM, separate
Python source-RUP replay, and external VeriPB 3.0.2.

The new native proof generator requires exact source SHA-256; unrelated
sources, modified bytes and SAT controls must return UNKNOWN without
a RUP file. Old Python IPG5 proof is an explicit frozen baseline and
is not misrepresented as a standard cutting-plane-only proof.

All performance numbers include the proof verifier components and are
single-run retrospective research, not prospective blind PAR2.
"""
import hashlib
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg5b_jobbranch"
NATIVE=ROOT/"build/drnas-ipg5b-jobbranch"
OLD=ROOT/"research/ipg5_structural_original_rup.py"
CONV=ROOT/"research/ipg5_rup_to_veripb.py"
DRAT=ROOT/"drat-trim/drat-trim"
VERIPB=ROOT/"veripb-tool/bin/veripb"
SOURCE_SHA="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"
sys.path.insert(0,str(ROOT/"research"))
from ipg1_fixtures import petersen,pack

def run(command,limit=40):
    begin=time.monotonic()
    try:
        proc=subprocess.run([str(x) for x in command],capture_output=True,
                            text=True,timeout=limit)
        return proc.returncode,round(time.monotonic()-begin,6),proc.stdout+"\n"+proc.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.monotonic()-begin,6),"TIMEOUT"

def invoked(logfile,argv,limit=40):
    rc,seconds,output=run(argv,limit)
    logfile.write_text(output)
    return rc,seconds,output

def assert_ok(condition,message):
    if not condition:raise AssertionError(message)

def proof_case(arm,source):
    folder=OUT/arm;folder.mkdir(exist_ok=True)
    rup=folder/"original_source.rup"
    meta=folder/"generator.json"
    if arm=="IPG5B_CPP":
        rc,producer_s,out=invoked(folder/"generator.log",
                [NATIVE,source,"--output",rup],10)
        mark="IPG5B_NATIVE "
        report=json.loads(next((line[len(mark):] for line in out.splitlines()
                      if line.startswith(mark)), "{}"))
        assert_ok(rc==0 and report.get("status")=="RUP_EMITTED_NEEDS_EXTERNAL_CHECK",
                  "native C++ source proof not produced")
        meta.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    else:
        rc,producer_s,out=invoked(folder/"generator.log",[
                sys.executable,OLD,"--original",source,
                "--graph-out",folder/"equivalent_graph.cnf",
                "--rup-out",rup,"--metadata",meta,
                "--fractional",folder/"fractional.json"],50)
        assert_ok(rc==0,"old IPG5 baseline generator failed")
        report=json.loads(meta.read_text())
        assert_ok(report.get("origin")=="MATHEMATICALLY_GUIDED_DPLL_NO_CDCL_NO_CONFLICT_LEARNING",
                  "prior proof origin changed")
    assert_ok(rup.is_file() and rup.stat().st_size>0 and rup.read_text().splitlines()[-1].strip()=="0",
              "no completed original RUP proof")
    if arm=="IPG5B_CPP":
        assert_ok(report["proof_steps"]==100 and report["proof_replayed"]==100,
                  "unexpected C++ 3-way original job-branch proof length")
    rows=sum(bool(line.strip()) for line in rup.read_text().splitlines())
    rc,drat_s,log=invoked(folder/"independent_drat.log",
              [DRAT,source,rup],30)
    assert_ok(rc==0 and "s VERIFIED" in log,"independent DRAT proof rejected")
    pb=folder/"original_source_3_0.pbp"
    audit=folder/"independent_rup_replay.json"
    rc,replay_s,log=invoked(folder/"independent_replay.log",
              [sys.executable,CONV,
               "--original",source,"--rup",rup,
               "--veripb",pb,"--metadata",audit],60)
    assert_ok(rc==0 and pb.exists(),"independent source-RUP replay rejected")
    checked=json.loads(audit.read_text())
    assert_ok(checked["rup_steps_replayed"]==rows,
              "independent RUP step count mismatch")
    rc,pb_s,log=invoked(folder/"veripb_external.log",
              [VERIPB,"--cnf",source,pb],65)
    assert_ok(rc==0 and "s VERIFIED UNSATISFIABLE" in log,
              "external VeriPB 3.0.2 rejected ORIGINAL source")
    result={
       "arm":arm,"status":"EXTERNALLY_VERIPB_UNSAT_VERIFIED",
       "original_sha256":SOURCE_SHA,
       "rup_steps":rows,
       "rup_bytes":rup.stat().st_size,
       "pbp_bytes":pb.stat().st_size,
       "generation_s":producer_s,
       "drat_trim_s":drat_s,
       "independent_rup_replay_s":replay_s,
       "veripb_s":pb_s,
       "e2e_verified_s":round(producer_s+drat_s+replay_s+pb_s,6),
       "source_bound":True,"no_cdcl":True
    }
    print("IPG5B_PROOF "+json.dumps(result,sort_keys=True),flush=True)
    return result

def controls(source):
    tests={}
    bad_source=OUT/"changed_byte_source.cnf"
    bad_source.write_bytes(source.read_bytes()+b"c this is a different source\n")
    for label,path in [("source_sha_mutated",bad_source)]:
        proof=OUT/(label+".rup")
        rc,sec,out=invoked(OUT/(label+".log"),
                          [NATIVE,path,"--output",proof],10)
        tests[label]=(rc==0 and not proof.exists() and
                      "UNKNOWN" in out)
    nv,cs=pack(6,2) # SAT: six jobs, three bins, capacity 2
    positive=OUT/"satisfiable_control.cnf"
    positive.write_text(f"p cnf {nv} {len(cs)}\n"+
             "".join(" ".join(map(str,c))+" 0\n" for c in cs))
    proof=OUT/"incorrect_sat.rup"
    rc,sec,out=invoked(OUT/"sat_control.log",
                      [NATIVE,positive,"--output",proof],10)
    tests["sat_control_refused"]=(rc==0 and "UNKNOWN" in out and not proof.exists())
    # The converter must never accept an edited/truncated proof.
    p=OUT/"IPG5B_CPP"/"original_source.rup"
    lines=p.read_text().splitlines()
    invalid=OUT/"truncated.rup"
    invalid.write_text("\n".join(lines[:-1])+"\n")
    fake=OUT/"bad_truncated.pbp"
    rc,sec,out=invoked(OUT/"truncated_replay.log",
                     [sys.executable,CONV,"--original",source,
                      "--rup",invalid,"--veripb",fake,
                      "--metadata",OUT/"bad_truncated.json"],30)
    tests["truncated_rejected"]=(rc!=0 and not fake.exists())
    return tests

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    source=OUT/"original_petersen_45v300c.cnf"
    source.write_bytes(petersen().encode("ascii"))
    assert_ok(hashlib.sha256(source.read_bytes()).hexdigest()==SOURCE_SHA,
              "frozen original SHA-256 unexpectedly changed")
    old=proof_case("IPG5A_PYTHON",source)
    new=proof_case("IPG5B_CPP",source)
    checks=controls(source)
    assert_ok(all(checks.values()),"adversarial source/proof controls failed")
    summary={
        "status":"PASS",
        "source_sha256":SOURCE_SHA,
        "original_variables":45,
        "original_clauses":300,
        "old_steps":old["rup_steps"],
        "new_steps":new["rup_steps"],
        "proof_step_reduction":round(old["rup_steps"]/new["rup_steps"],3),
        "old_pbp_bytes":old["pbp_bytes"],
        "new_pbp_bytes":new["pbp_bytes"],
        "old_e2e_s":old["e2e_verified_s"],
        "new_e2e_s":new["e2e_verified_s"],
        "old_generator_s":old["generation_s"],
        "new_native_generator_s":new["generation_s"],
        "old_veripb_accepted":True,
        "new_veripb_accepted":True,
        "independent_drat_accepted":True,
        "adversarial_tests":checks,
        "historical_retrospective_only":True,
        "scope":"C++ structural three-way job branch and independent VeriPB original source. This is bounded exponential DPLL, not pure algebraic cutting planes and not a general polynomial PCMAX solver. One original source only; no blind PAR2.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("IPG5B_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    try:main()
    except (AssertionError,ValueError,OSError,KeyError,TypeError,IndexError) as error:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/"failure.json").write_text(json.dumps({
            "status":"FAIL","reason":str(error)},indent=2)+"\n")
        print("IPG5B_AUDIT_FAILED "+str(error),flush=True)
        sys.exit(1)
