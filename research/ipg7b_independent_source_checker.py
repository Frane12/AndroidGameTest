#!/usr/bin/env python3
"""Independent IPG7B ORIGINAL-SOURCE configuration block proof checker.

Checks that the generator's no-good clauses are ACTUALLY source RUP,
that they correspond to EVERY exact-capacity first-machine source
configuration in the independently reconstructed original 3-machine
packing CNF, and that a complete original-source RUP contradiction
follows. The checker never calls a SAT solver or imports the producer.

The external DRAT-trim and VeriPB3.0.2 on EXACT ORIGINAL CNF remain
required; this second checker is an additional source/provenance audit.
"""
import argparse
import hashlib
import json
import pathlib
import sys

from ipg7_independent_master_checker import verify_source
from ipg4_rup_drat_to_veripb import parse_rup_trace,rup_unit_conflict

def check(original,master_cert,meta,trace):
    candidate=json.loads(master_cert.read_text())
    sha,nv,clauses,configs=verify_source(original,candidate)
    info=json.loads(meta.read_text())
    if info.get("format")!="DRNAS-IPG7B-ORIGINAL-CONFIG-RUP-V1":
        raise ValueError("unsupported original-source bridge proof format")
    if info.get("original_source_sha256")!=sha or (
         info.get("original_source_vars")!=nv or
         info.get("original_source_clauses")!=len(clauses)):
        raise ValueError("source original CNF mismatch")
    if info.get("weights")!=candidate.get("weights") or (
            info.get("capacity")!=candidate.get("machine_capacity")):
        raise ValueError("configuration weights differ from original source")
    if info.get("exact_capacity_masks")!=configs or (
            info.get("configurations_count")!=len(configs)):
        raise ValueError("incomplete original-source config enumeration")
    if any((a&b)==0 for a in configs for b in configs):
        raise ValueError("SAT source admits two disjoint full-bin configs")
    if hashlib.sha256(trace.read_bytes()).hexdigest()!=info.get("original_rup_sha256"):
        raise ValueError("RUP proof SHA altered after source binding")
    proof=parse_rup_trace(trace,nv)
    if not proof or proof[-1] or len(proof)!=info["total_original_RUP_steps"]:
        raise ValueError("no complete source RUP refutation")
    blocks=info.get("configuration_source_no_good_blocks")
    if not isinstance(blocks,list) or len(blocks)!=len(configs):
        raise ValueError("missing one of original configuration blockers")
    for n,(mask,block) in enumerate(zip(configs,blocks)):
        expected=[j for j in range(nv//3) if mask&(1<<j)]
        clause=tuple(-3*j-1 for j in expected)
        if (block.get("mask")!=mask or block.get("machine")!=0 or
                block.get("job_indices")!=expected or
                tuple(block.get("clause",[]))!=clause):
            raise ValueError("source configuration no-good does not match full-bin profile")
        pos=block.get("proof_position_1based")
        if type(pos)!=int or not 1<=pos<=len(proof) or proof[pos-1]!=clause:
            raise ValueError("source configuration block is absent from proof trace")
        prev_pos=blocks[n-1]["proof_position_1based"] if n else 0
        if pos-prev_pos!=block["source_case_steps"]:
            raise ValueError("source case-split step count metadata forged")
    expected_cases=blocks[-1]["proof_position_1based"]
    if info.get("configuration_case_rup_steps")!=expected_cases or (
        info["post_configuration_original_closure_rup_steps"] !=len(proof)-expected_cases):
        raise ValueError("original proof stage counts mismatch")
    database=list(clauses)
    for idx,c in enumerate(proof,1):
        if not rup_unit_conflict(database,(-lit for lit in c)):
            raise ValueError(f"RUP source proof rejected at original clause step {idx}")
        database.append(c)
    return {
        "status":"IPG7B_ORIGINAL_SOURCE_RUP_AND_CONFIGURATION_BRIDGE_VERIFIED",
        "source_sha256":sha,
        "source_original_clauses":len(clauses),
        "source_exact_configs":len(configs),
        "source_config_no_goods":len(blocks),
        "source_case_RUP_steps":expected_cases,
        "source_closing_RUP_steps":len(proof)-expected_cases,
        "source_all_RUP_steps_checked":len(proof),
        "source_standard_VerIPB_still_required":True,
        "used_bounded_DPLL_to_find_config_and_closing_lemmas":True,
    }
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",required=True,type=pathlib.Path)
    p.add_argument("--master-certificate",required=True,type=pathlib.Path)
    p.add_argument("--source-certificate",required=True,type=pathlib.Path)
    p.add_argument("--original-rup",required=True,type=pathlib.Path)
    a=p.parse_args()
    try:
        data=check(a.source,a.master_certificate,a.source_certificate,a.original_rup)
        print("IPG7B_ORIGINAL_SOURCE_ACCEPT "+json.dumps(data,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,UnicodeError,
            OverflowError) as exc:
        print("IPG7B_ORIGINAL_SOURCE_REJECT "+str(exc),flush=True)
        return 1
if __name__=="__main__":sys.exit(main())
