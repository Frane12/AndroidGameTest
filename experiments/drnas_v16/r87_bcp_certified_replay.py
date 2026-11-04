#!/usr/bin/env python3
"""R87b: correction ONLY to the independent source GF2 certificate checker.

Same SHA-frozen original CNFs, original Kissat/native binaries, R87 adaptive
policy, arms/seeds/cap as the R87 holdout. Original BCP unit premises are
independently proved and included in the GF2 span. If any row is NOT proved,
fail closed. R87b is AUDIT-CORRECTED REPLAY, not a new independent holdout.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import r87_unseen_official as original
import r87_root_bcp_proof as independent
import r83_live_xor_cdcl_wide as world

def ck(ok,msg):
    if not ok:raise RuntimeError("R87B_BCP_FAIL_CLOSED "+str(msg))

def independently_prove_bcp_and_xor(source,emitted):
    proof=independent.proof_with_bcp(source,emitted)
    ck(proof["sound"] and proof["native_rows"]==len(emitted),
       "original CNF plus independently replayed BCP DOES NOT imply native XOR rows")
    return len(emitted)

def measure(a):
    world.source_prove_rows=independently_prove_bcp_and_xor
    original.measure(a)
    # The original source/runner/commit/seed/solver pins and paired data
    # remain byte-for-byte the original experimental protocol.
    p=Path(a.out)/"shard.json"
    data=json.loads(p.read_text())
    for row in data["rows"]:
        if row["mode"]!="clean":
            ck(row["telemetry"]["verified"],"source row not independently proved")
        row["source_certifier"]="original_CNF_plus_independent_root_BCP_v1"
    data["certification_only_patch"]="R87b_BCP_proof_correction_no_solver_change"
    original.write(p,data)
    print("R87B_SHARD_BCP_PROOF_PASS",a.shard,len(data["rows"]),flush=True)

def audit(a):
    m=original.manifest(Path(a.sources))
    for i,c in enumerate(m["cases"]):
        p=Path(a.combined)/f"r87-holdout-shard-{i}"/"results"/"shard.json"
        ck(p.exists(),"missing fully paired auditable shard "+str(i))
        j=json.loads(p.read_text())
        ck(j.get("certification_only_patch")==
           "R87b_BCP_proof_correction_no_solver_change","wrong certifier protocol")
        ck(all(r.get("source_certifier")==
           "original_CNF_plus_independent_root_BCP_v1" for r in j["rows"]),
           "missing per-trial independent BCP trace protocol")
    original.audit(a)
    p=Path(a.out)/"r87-holdout-final.json"
    obj=json.loads(p.read_text())
    obj["status"]="PASS_UNOFFICIAL_BCP_CORRECTED_REPLAY_NOT_NEW_HOLDOUT"
    obj["precommitted_claim_interpretation"]="DESCRIPTIVE_ONLY_AFTER_AUDIT_FIX"
    obj["limitations"].append(
        "R87b reuses the already exposed exact R87 frozen cohort after audit-correction; it is NOT a new blind replicate.")
    obj["limitations"].append(
        "Independent checker combines original complete XOR clauses with original-CNF root BCP unit reason chains; no changes to solver/heuristics.")
    original.write(p,obj)
    md=Path(a.out)/"r87-holdout-final.md"
    md.write_text(md.read_text()+"\n**Audit correction:** R87b proof certifier "+
      "includes independently replayed root-BCP premises; same original "+
      "formula and solver SHA. Not a fresh blind replicate.\n")
    print("R87B_FULL_AUDIT_CORRECTED_REPLAY_PASS",
          len(obj["rows"]),obj["summary"]["ALL"],flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();ss=p.add_subparsers(dest="cmd",required=True)
    ss.add_parser("selftest")
    m=ss.add_parser("measure")
    for name in ("sources","compiled","out"):m.add_argument("--"+name,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=ss.add_parser("audit")
    for name in ("sources","combined","out"):a.add_argument("--"+name,required=True)
    args=p.parse_args()
    if args.cmd=="selftest":
        ck(original.SHARDS==8 and original.MODES==("clean","active4","active64","adaptive"),
           "frozen holdout modes changed")
        print("R87B_INDEPENDENT_BCP_CERTIFIER_ONLY_SELFTEST_PASS",flush=True)
    elif args.cmd=="measure":measure(args)
    else:audit(args)
