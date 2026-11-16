#!/usr/bin/env python3
"""IPG7B: one STANDARD original-CNF VeriPB source proof, config-guided.

The exact k-config master still has a separate pure POL proof, but the
NEW bridge issues source-RUP case blocks of each of those k exact-T
configurations. A further bounded DPLL closure yields original source
UNSAT, which is converted by the frozen exact RUP->POL translator into
ONE complete standard VeriPB 3.0 proof AGAINST THE ORIGINAL CNF.

This is NOT a replacement for DPLL-based source proof discovery:
source-case blocking and closure do perform bounded case splits. It is
a formal connection from IPG7 configuration invariants to a standard
original CNF proof, not a direct transcription of the k+1 pure master
POL proof. No CDCL, SAT portfolio, or extra solver process.

Controls include SAT model verification, unknown/source-gate and
adversarial forged or incomplete original-source/config certificates.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg7b_source"
MASTER=ROOT/"research/ipg7_config_master.py"
SOURCE_PRODUCER=ROOT/"research/ipg7b_original_config_bridge.py"
SOURCE_INDEPENDENT=ROOT/"research/ipg7b_independent_source_checker.py"
MASTER_INDEPENDENT=ROOT/"research/ipg7_independent_master_checker.py"
POL_CONVERTER=ROOT/"research/ipg5e_pure_pol_from_source_rup.py"
VP=ROOT/"veripb-tool/bin/veripb"
DRAT=ROOT/"drat-trim/drat-trim"
sys.path.insert(0,str(ROOT/"research"))
from ipg7_benchmark import originals

def call(args,limit=60):
    started=time.perf_counter()
    try:
        p=subprocess.run([str(z) for z in args],capture_output=True,text=True,timeout=limit)
        return p.returncode,round(time.perf_counter()-started,6),p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-started,6),"TIMEOUT"

def logged(folder,name,args,limit=60):
    rc,sec,output=call(args,limit)
    (folder/(name+".log")).write_text(output)
    return rc,sec,output

def demand(success,reason):
    if not success:raise AssertionError(reason)

def one(source_entry):
    name=source_entry["name"]
    original=ROOT/"results/ipg7_config/sources"/(name+".cnf")
    weights=ROOT/"results/ipg7_config/sources"/(name+".weights.json")
    sha=hashlib.sha256(original.read_bytes()).hexdigest()
    demand(sha==source_entry["source_sha256"],"original input manifest changed")
    dest=OUT/"cases"/name
    dest.mkdir(parents=True,exist_ok=True)
    master_prefix=dest/"global"
    rc,master_time,log=logged(dest,"master_producer",[
        sys.executable,MASTER,"--cnf",original,"--weights-json",weights,
        "--prefix",master_prefix],45)
    demand(rc==0,"original bounded global exact-T producer rejected")
    master_cert=master_prefix.with_suffix(".certificate.json")
    demand(master_cert.is_file(),"missing source configuration claim")
    cert=json.loads(master_cert.read_text())
    row={
        "name":name,"source_sha256":sha,
        "expected":source_entry["expected"],"family":source_entry["family"],
        "global_config_discovery_s":master_time,
        "status":"UNKNOWN",
    }
    if cert["status"]=="UNKNOWN":
        row["reason"]=cert.get("reason")
        print("IPG7B_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
        return row
    if cert["status"]=="SAT_MODEL_VERIFIED_BY_GENERATOR":
        rc,sec,out=logged(dest,"original_SAT_independent",[
            sys.executable,MASTER_INDEPENDENT,"--source",original,
            "--certificate",master_cert],35)
        if rc==0 and "IPG7_SOURCE_BRIDGE_ACCEPT " in out:
            row.update(status="ORIGINAL_SAT_MODEL_VERIFIED",source_model_checker_s=sec)
        else:row["status"]="ERROR_SAT_MODEL_REJECTED"
        # A SAT or even a UNKNOWN source must never get an erroneous
        # source UNSAT by configuration-guided branch proof.
        proof_prefix=dest/"forbidden_source_refutation"
        rc,_,out=logged(dest,"reject_SAT_original_bridge",[
            sys.executable,SOURCE_PRODUCER,"--cnf",original,
            "--weights-json",weights,"--prefix",proof_prefix,
            "--max-seconds","5"],15)
        if rc==0 or proof_prefix.with_suffix(".original.rup").exists():
            row["status"]="ERROR_FALSE_UNSAT_ON_SAT_CONTROL"
        print("IPG7B_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
        return row
    if cert["status"]!="UNSAT_SOURCE_STRUCTURAL_CANDIDATE_MASTER_VERIPB_UNCHECKED":
        row["status"]="ERROR_UNEXPECTED_GLOBAL_CONFIG_STATUS"
        return row
    master=master_prefix.with_suffix(".master.cnf")
    master_pb=master_prefix.with_suffix(".master.pbp")
    rc,ssc,output=logged(dest,"independent_original_to_master",[
        sys.executable,MASTER_INDEPENDENT,"--source",original,
        "--certificate",master_cert,
        "--master",master,"--proof",master_pb],40)
    if rc!=0 or "IPG7_SOURCE_BRIDGE_ACCEPT " not in output:
        row["status"]="ERROR_ORIGINAL_TO_MASTER_PROJECTION"
        return row
    rc,mver,output=logged(dest,"derived_master_VerIPB",[
        VP,"--cnf",master,master_pb],45)
    if rc!=0 or "s VERIFIED UNSATISFIABLE" not in output:
        row["status"]="ERROR_MASTER_VERIPB_REJECTED"
        return row
    bridge_prefix=dest/"source_bridge"
    rc,producer_s,out=logged(dest,"original_source_config_bridge_generator",[
        sys.executable,SOURCE_PRODUCER,"--cnf",original,
        "--weights-json",weights,"--prefix",bridge_prefix,
        "--max-seconds","25"],50)
    if rc!=0:
        row["status"]="ERROR_SOURCE_BRIDGE_GENERATOR"
        return row
    source_rup=bridge_prefix.with_suffix(".original.rup")
    bridge_certificate=bridge_prefix.with_suffix(".certificate.json")
    if not source_rup.is_file() or not bridge_certificate.is_file():
        row["status"]="ERROR_BRIDGE_PROOF_MISSING"
        return row
    bridge=json.loads(bridge_certificate.read_text())
    row.update(source_config_bridges=bridge["configurations_count"],
        source_config_case_steps=bridge["configuration_case_rup_steps"],
        source_final_case_steps=bridge["post_configuration_original_closure_rup_steps"],
        source_original_RUP_steps=bridge["total_original_RUP_steps"],
        original_proof_generator_s=producer_s,
        original_source_case_splitting=True)
    rc,source_verify_s,out=logged(dest,"independent_original_RUP_config_checker",[
        sys.executable,SOURCE_INDEPENDENT,
        "--source",original,"--master-certificate",master_cert,
        "--source-certificate",bridge_certificate,
        "--original-rup",source_rup],60)
    if rc!=0 or "IPG7B_ORIGINAL_SOURCE_ACCEPT " not in out:
        row["status"]="ERROR_INDEPENDENT_ORIGINAL_CONFIG_SOURCE_RUP"
        return row
    rc,drat_s,out=logged(dest,"independent_Drat_trim_original",[
        DRAT,original,source_rup],45)
    if rc!=0 or "s VERIFIED" not in out:
        row["status"]="ERROR_ORIGINAL_SOURCE_DRAT"
        return row
    original_pb=dest/"DIRECT_ORIGINAL_WEIGHTED_VerIPB.pbp"
    pol_metadata=dest/"original_pol_meta.json"
    rc,conv_s,out=logged(dest,"independent_RUP_to_POL_original",[
        sys.executable,POL_CONVERTER,"--cnf",original,
        "--source-rup",source_rup,
        "--pb-proof",original_pb,"--meta",pol_metadata,
        "--expected-sha256",sha],90)
    if rc!=0 or not original_pb.is_file():
        row["status"]="ERROR_ORIGINAL_POL_TRANSLATOR"
        return row
    pol=json.loads(pol_metadata.read_text())
    if pol["veripb_rup_lines"]!=0 or (
          pol["veripb_pol_lines"]!=bridge["total_original_RUP_steps"]):
        row["status"]="ERROR_SOURCE_POL_PROVENANCE"
        return row
    lines=original_pb.read_text().splitlines()
    if lines[:2]!=["pseudo-Boolean proof version 3.0",
                   f"f {bridge['original_source_clauses']} ;"]:
        row["status"]="ERROR_NOT_AN_ORIGINAL_SOURCE_CERTIFICATE"
        return row
    rc,proof_s,out=logged(dest,"external_VERIPB_ON_ORIGINAL_300_CLAUSES",[
        VP,"--cnf",original,original_pb],90)
    if rc!=0 or "s VERIFIED UNSATISFIABLE" not in out:
        row["status"]="ERROR_ORIGINAL_SOURCE_VERIPB_REJECTED"
        return row
    row.update(
        status="DIRECT_ORIGINAL_VERIPB_UNSAT_VERIFIED",
        source_independent_checker_s=source_verify_s,
        drat_trim_s=drat_s,
        pol_converter_s=conv_s,
        direct_original_VerIPB_s=proof_s,
        direct_original_POL_steps=pol["veripb_pol_lines"],
        direct_original_RUP_lines=0,
        direct_original_VerIPB_bytes=original_pb.stat().st_size,
        master_pure_POL_steps=cert["master_pure_POL_steps"],
        master_derived_VerIPB_verified=True,
        source_original_VerIPB_verified=True,
        original_configuration_source_bridge_verified=True,
        proof_discovery_uses_DPLL=True,
    )
    print("IPG7B_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row

def negative_tests(records):
    errors=[]
    name="petersen_original_45v300c"
    dest=OUT/"cases"/name
    master_cert=dest/"global.certificate.json"
    bridge_cert=dest/"source_bridge.certificate.json"
    trace=dest/"source_bridge.original.rup"
    original=ROOT/"results/ipg7_config/sources"/(name+".cnf")
    cert=json.loads(bridge_cert.read_text())
    # Prevent accidental acceptance of removed config blockers.
    forged=json.loads(json.dumps(cert))
    forged["configuration_source_no_good_blocks"].pop()
    fake=OUT/"removed_config_block.json"
    fake.write_text(json.dumps(forged)+"\n")
    rc,_,_=logged(OUT,"removed_config_rejection",[
        sys.executable,SOURCE_INDEPENDENT,
        "--source",original,"--master-certificate",master_cert,
        "--source-certificate",fake,"--original-rup",trace],30)
    if rc==0:errors.append("missing configuration blocker accepted")
    # Source SHA tampering must not be treated as the same original.
    changed=OUT/"modified_original.cnf"
    changed.write_bytes(original.read_bytes()+b"c different source bytes\n")
    rc,_,_=logged(OUT,"changed_source_rejection",[
        sys.executable,SOURCE_INDEPENDENT,
        "--source",changed,"--master-certificate",master_cert,
        "--source-certificate",bridge_cert,"--original-rup",trace],30)
    if rc==0:errors.append("source-byte tampering accepted")
    # A valid trace needs the final empty clause.
    truncated=OUT/"truncated_original.rup"
    truncated.write_text("\n".join(trace.read_text().splitlines()[:-1])+"\n")
    rc,_,_=logged(OUT,"truncated_proof_rejection",[
        sys.executable,SOURCE_INDEPENDENT,
        "--source",original,"--master-certificate",master_cert,
        "--source-certificate",bridge_cert,"--original-rup",truncated],30)
    if rc==0:errors.append("truncated original proof accepted")
    return errors

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    cases=originals()  # input manifest written BEFORE solver/proof trials
    records=[];errors=[]
    for case in cases:
        row=one(case)
        records.append(row)
        if row["status"].startswith("ERROR"):
            errors.append(row["name"]+": "+row["status"])
        (OUT/"rows.json").write_text(json.dumps(records,sort_keys=True,indent=2)+"\n")
    errors+=negative_tests(records)
    accepted=[r for r in records if r["status"]=="DIRECT_ORIGINAL_VERIPB_UNSAT_VERIFIED"]
    positives=[r for r in records if r["status"]=="ORIGINAL_SAT_MODEL_VERIFIED"]
    original=next(r for r in records if r["name"]=="petersen_original_45v300c")
    new=next(r for r in records if r["name"]=="new_five_job_intersecting_configs")
    if original["status"]!="DIRECT_ORIGINAL_VERIPB_UNSAT_VERIFIED":
        errors.append("no direct original 300-clause standard VeriPB proof")
    if new["status"]!="DIRECT_ORIGINAL_VERIPB_UNSAT_VERIFIED":
        errors.append("no direct independent five-job standard VeriPB proof")
    if len(positives)!=2:
        errors.append("SAT control originals lacked independently verified models")
    summary={
        "status":"PASS" if not errors else "FAIL",
        "source_cases":len(cases),
        "direct_original_CNF_VerIPB_verified":len(accepted),
        "original_300_clause_Petersen_VerIPB_verified":original["status"]=="DIRECT_ORIGINAL_VERIPB_UNSAT_VERIFIED",
        "petersen_k_exact_configs":original.get("source_config_bridges"),
        "petersen_config_no_good_source_RUP_steps":original.get("source_config_case_steps"),
        "petersen_final_source_closing_RUP_steps":original.get("source_final_case_steps"),
        "petersen_single_original_VerIPB_POL_steps":original.get("direct_original_POL_steps"),
        "petersen_original_VerIPB_proof_bytes":original.get("direct_original_VerIPB_bytes"),
        "master_separately_VerIPB_verified":original.get("master_derived_VerIPB_verified",False),
        "independent_new_five_job_direct_VerIPB_verified":new["status"]=="DIRECT_ORIGINAL_VERIPB_UNSAT_VERIFIED",
        "original_source_full_SAT_models":len(positives),
        "DPLL_used_to_bridge_exact_configurations":True,
        "CDCL_SAT_portfolio_calls":0,
        "source_disjoint_blind_competition_PAR2":False,
        "errors":errors,
        "scope":"IPG7B builds ONE STANDARD direct-original-CNF VeriPB proof using per-exact-config source RUP blocks plus bounded DPLL completion. Separately verified 7-line pure master is NOT literally the same proof. This closes direct original proof TARGET gap, NOT the search-free proof discovery gap. Exponential complexity.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("IPG7B_DIRECT_ORIGINAL_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if not errors else 1
if __name__=="__main__":raise SystemExit(main())
