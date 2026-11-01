#!/usr/bin/env python3
"""V13.17 blind 30 real SAT CNFs: byte-identical V13.15 policies, 20s instead of 8s.

V13.15 source and fixed gate are left untouched. This wrapper changes ONLY
the shared time horizon for 4 policies; includes every gate/prepass/fallback
second in each method's wall clock, preserves proof replay, binary hash,
one-core CPU affinity and error fail-closed behavior of V13.15.

Fresh 30-case SHA manifest is frozen before benchmark, separate from V13.13/16.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import v1315_selective_xor as fixed
import v1314_timed_ab as fallback

PROTOCOL="DRNAS-V1317-FRESH30-CAP20-V1315-FIXED-20261101-v1"
COHORT_PROTOCOL="DRNAS-V1317-NEW30-SC2024-FIXED20-V1315-20261101-v1"
PREVIOUS_V1315_BLOB="2b1b14d9d58459e350a0906d356c5003a6105d64"
NEW_CAP=20.0

def require(test,msg):
    if not test:raise RuntimeError(msg)

def configure():
    # This is only a shared duration parameter; all V13.15 policy functions
    # and gates are imported from the exact original source file.
    fixed.CAP=NEW_CAP
    fallback.CAP=NEW_CAP
    require(fixed.GATE_MAX_BYTES==96*1024 and fixed.GATE_MIN_XOR==16,
            "V13.15 fixed gate changed")
    require(fixed.MODES==("Kissat404","DRNAS_Legacy",
                          "V1312_XOR_Kissat","V1315_SELECTIVE_XOR"),
            "V13.15 policies changed")
    require(fixed.CAP==fallback.CAP==20.0,"nonidentical timeout cap")

def verify_freeze(path):
    m=json.loads(Path(path).read_text())
    fixed.prev.validate_manifest(m)
    require(m["holdout_protocol"]==COHORT_PROTOCOL,
            "not blind frozen V13.17 cohort")
    require(m["unseen_excluded_shas"]>=204 and
            m["excluded_prior_shas"] is True,
            "insufficient historical exclusion")
    require(len(m["cases"])==30 and
            len({c["id"] for c in m["cases"]})==30 and
            len({c["sha256"] for c in m["cases"]})==30,
            "identity duplicates")
    return m

def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()

def selftest():
    configure()
    fixed.selftest()
    print("V1317_SELFTEST_PASS: unchanged gate, two horizons both 20s",flush=True)

def run(args):
    configure()
    verify_freeze(args.manifest)
    fixed.run(args)

def audit(args):
    configure()
    m=verify_freeze(args.manifest)
    # v1315-shard-N artifact directory names maintained by CI symlinks.
    fixed.audit(args)
    data=json.loads(Path(args.json).read_text())
    require(data["sample"]==30 and data["attempts"]==240 and
            data["policies"]==list(fixed.MODES),
            "incomplete audit")
    require(set(data["summary"])=={"all","SAT","UNSAT"},
            "bad report groups")
    data["original_v1315_protocol"]=data["protocol"]
    data["protocol"]=PROTOCOL
    data["previous_v1315_blob"]=PREVIOUS_V1315_BLOB
    data["source_cohort_protocol"]=m["holdout_protocol"]
    data["source_sha256"]=sha_file(args.manifest)
    data["new_2024_formulas"]=30
    data["timeout_s"]=NEW_CAP
    data["par2_timeout_penalty_s"]=2*NEW_CAP
    data["source_excluded_historical_shas"]=m["unseen_excluded_shas"]
    data["fresh_sha_disjoint_from"]=m["historic_manifest_digests"]
    data["interpretation"]={
        "scope":"30 new SHA-frozen 2024 Main Track formulas, 15 SAT / 15 UNSAT.",
        "policies":"Byte-identical V13.15 policies, only timeout extended 8s to 20s.",
        "limitations":[
            "New formula cohort is SHA-disjoint from all seven historical manifest sources, including V13.13 and V13.16.",
            "No model/UNSAT proof independent check for baseline binaries; answers only cross-checked to published labels.",
            "Github runner is one pinned core at 3 GiB; this is not official SAT Competition ranking.",
            "The 20s horizon is an additional experiment, not directly comparable as a raw PAR2 number with 8s cohorts.",
            "Preselected class-balanced formulas and size caps are not representative of full competition.",
            "Only structural XOR contradiction certificates are independently replayed."
        ]
    }
    Path(args.json).write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    lines=[
        "# DRNAS V13.17 — BLIND third 30-CNF test, 20-second SAT cutoff","",
        "30 new SHA-frozen official SAT Competition 2024 Main Track formulas, 15 SAT and 15 UNSAT.",
        "Original V13.15 gate and other policy code is untouched; all four modes share 20 s wall limit, 3 GiB and one core.",
        "2 repetitions per formula; 240 fully audited attempts; PAR2 timeout penalty 40 s.","",
        "| Class | Policy | Solved / attempts | PAR2 seconds | Mean solved seconds |",
        "|---|---|---:|---:|---:|"
    ]
    for cohort in ("all","SAT","UNSAT"):
        for mode in fixed.MODES:
            item=data["summary"][cohort][mode]
            mean=("n/a" if item["mean_solved_s"] is None
                  else f'{item["mean_solved_s"]:.4f}')
            lines.append(f'| {cohort} | {mode} | {item["solved"]}/{item["attempts"]} | '
                         f'{item["PAR2_s"]:.4f} | {mean} |')
    lines += ["","## Selective routing"]
    for key,count in sorted(data["selective_routes"].items()):
        lines.append(f"- {key}: {count}/60 attempts")
    lines += ["",f'Certified early UNSAT: {data["certified_early_unsat_trials"]} attempts '
                  f'on {data["certified_early_unsat_distinct_cases"]} distinct formulas.',"",
              "## Limitations"]
    lines += ["- "+s for s in data["interpretation"]["limitations"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V1317_AUDIT_PASS",json.dumps(data["summary"]["all"],sort_keys=True),
          "routes",json.dumps(data["selective_routes"],sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("selftest")
    x=sub.add_parser("run")
    for key in ("manifest","kissat","drnas","out"):
        x.add_argument("--"+key,required=True)
    x.add_argument("--shard",required=True,type=int)
    x=sub.add_parser("audit")
    for key in ("manifest","combined","json","md"):
        x.add_argument("--"+key,required=True)
    a=p.parse_args()
    if a.command=="selftest":selftest()
    elif a.command=="run":run(a)
    else:audit(a)

if __name__=="__main__":
    main()
