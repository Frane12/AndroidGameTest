#!/usr/bin/env python3
"""V13.13: prospective 30 fresh public SC2024 CNF sparse GF(2) holdout.

Selection is frozen by v1313_freeze_30.py before this script reads any formula.
This is a real-data *mathematical diagnostic*, NOT a SAT solving speed benchmark.
We apply unchanged v1312_sparse_gf2.analyze and compare its coverage to the
unchanged V13.11 caps on each identical CNF. Never use official labels for routing.
"""
import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

import official_shortlong_select as source
import v1312_sparse_gf2 as sparse

PROTOCOL="DRNAS-V1313-THIRTY-UNSEEN-CNF-SPARSE-AUDIT-20261101-v1"
FREEZE="DRNAS-V1313-SC2024-THIRTY-SHA-DISJOINT-20261101-v1"
SHARDS=10
CASES=30
source.RAW_CAP=96*1024**2
source.CNF_CAP=64*1024**2
source.VARIABLE_CAP=500000
source.CLAUSE_CAP=1000000

def require(c,m):
    if not c:
        raise RuntimeError(m)

def read(p):
    return json.loads(Path(p).read_text())

def save(p,obj):
    p=Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def verify_manifest(manifest):
    require(manifest["protocol"]==FREEZE and len(manifest["cases"])==CASES and
            manifest["n"]==CASES and manifest["shards"]==SHARDS,
            "manifest mismatch")
    require(len({c["id"] for c in manifest["cases"]})==CASES and
            len({c["sha256"] for c in manifest["cases"]})==CASES,
            "duplicate case id or SHA")
    require(sum(c["official_label"]=="SAT" for c in manifest["cases"])==15 and
            sum(c["official_label"]=="UNSAT" for c in manifest["cases"])==15,
            "unbalanced official groups")
    require(manifest["excluded_prior_shas"] is True and
            manifest["unseen_excluded_shas"]>=144,
            "missing previous experiments SHA exclusion")

def run(args):
    m=read(args.manifest)
    verify_manifest(m)
    require(0<=args.shard<SHARDS,"invalid shard")
    cases=m["cases"][args.shard::SHARDS]
    require(len(cases)==3,"wrong shard size")
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in cases:
        fname=out/(case["id"]+".cnf")
        original=source.download_and_features(case["id"],fname)
        require(original["sha256"]==case["sha256"] and
                original["features"]==case["features"] and
                original["variables"]==case["variables"] and
                original["clauses"]==case["clauses"],
                "source SHA, metadata or feature drift")
        try:
            metrics=sparse.analyze(fname)
        finally:
            fname.unlink(missing_ok=True)
        require(metrics["variables"]==case["variables"] and
                metrics["clauses"]==case["clauses"], "header drift")
        require(metrics["sparse"]["visited_equations"]+
                metrics["sparse"]["unvisited_equations"]==
                metrics["xor_equations"], "coverage accounting mismatch")
        row={"id":case["id"],"sha256":case["sha256"],"family":case["family"],
             "published_label_for_audit_only":case["official_label"],
             "metrics":metrics}
        rows.append(row)
        save(out/"rows.json",rows)
        z=metrics["sparse"]
        print("V1313_CASE",args.shard,case["id"][:12],
              "label",case["official_label"],
              "equations",metrics["xor_equations"],
              "prior_examined",metrics["prior_v1311"]["examined_equations"],
              "sparse_accepted",z["accepted_equations"],
              "unaccepted",z["rejected_equations"]+z["unvisited_equations"],
              "units",z["certified_units"],"contradictions",z["certified_contradictions"],
              "wall",metrics["total_wall_s"],flush=True)
    require(len(rows)==3,"incomplete shard")
    print("V1313_SHARD_PASS",args.shard,flush=True)

def audit(args):
    manifest=read(args.manifest)
    verify_manifest(manifest)
    history=read(args.v139)
    require(history["protocol"]=="DRNAS-V139-SC2024-NEW-SHA-DISJOINT-20261101-v1",
            "not original V13.9 selection")
    old_ids={c["id"] for c in history["cases"]}
    old_shas={c["sha256"] for c in history["cases"]}
    require(not (old_ids & {c["id"] for c in manifest["cases"]}) and
            not (old_shas & {c["sha256"] for c in manifest["cases"]}),
            "formula overlaps V13.9")
    combined=[]
    for shard in range(SHARDS):
        part=read(Path(args.combined)/f"v1313-shard-{shard}"/"rows.json")
        selected=manifest["cases"][shard::SHARDS]
        require(len(part)==3 and
                [r["id"] for r in part]==[c["id"] for c in selected] and
                [r["sha256"] for r in part]==[c["sha256"] for c in selected],
                "case identity mismatch")
        combined.extend(part)
    require(len(combined)==CASES,"missing results")
    total=collections.Counter()
    per_class=collections.defaultdict(lambda:collections.Counter())
    duration=[]
    for row in combined:
        res=row["metrics"]
        z=res["sparse"]
        group=per_class[row["published_label_for_audit_only"]]
        for count in (total,group):
            count["formulas"]+=1
            count["xor_equations"]+=res["xor_equations"]
            count["v1311_examined"]+=res["prior_v1311"]["examined_equations"]
            count["v1311_skipped"]+=res["prior_v1311"]["skipped_equations"]
            count["v1312_accepted"]+=z["accepted_equations"]
            count["v1312_unaccepted"]+=z["rejected_equations"]+z["unvisited_equations"]
            count["components"]+=res["components"]
            count["components_incomplete"]+=res["incomplete_components"]
            count["certified_forced_literals"]+=z["certified_units"]
            count["certified_contradictions"]+=z["certified_contradictions"]
            count["equations_visited"]+=z["visited_equations"]
            count["xor_operations"]+=z["xor_steps"]
            count["formulas_with_xor"]+=bool(res["xor_equations"])
            count["formulas_with_implied_unit"]+=bool(z["certified_units"])
            count["formulas_with_contradiction"]+=bool(z["certified_contradictions"])
        require(all(cert["replay_verified"] for cert in res["certificates"]),
                "unverified certificate")
        duration.append(res["total_wall_s"])
    require(total["xor_equations"]==total["v1311_examined"]+total["v1311_skipped"],
            "prior coverage discrepancy")
    require(total["xor_equations"]==total["v1312_accepted"]+total["v1312_unaccepted"],
            "sparse coverage discrepancy")
    require(total["formulas"]==CASES, "sample count discrepancy")
    report={"protocol":PROTOCOL,"sample":{"formulas":CASES,"shards":SHARDS,
             "official_main_track_year":2024,"prior_ids_sha_excluded":True,
             "historical_manifest_hashes":manifest["historic_manifest_digests"],
             "source_meta_sha256":manifest["metadata_sha256"],
             "source_results_sha256":manifest["results_zip_sha256"],
             "selection_rule":manifest["selection_rule"],
             "source_selected_pretest":True},
            "totals":dict(total),
            "by_official_label":{k:dict(v) for k,v in per_class.items()},
            "analysis_wall_s":{"median":round(statistics.median(duration),6),
                               "max":round(max(duration),6),
                               "min":round(min(duration),6)},
            "cases":combined,
            "limitations":[
               "This is SHA-disjoint from the listed prior manifests, not guaranteed never examined by anyone or in other unlisted DRNAS studies.",
               "Selection is stratified by official SAT/UNSAT labels and families; it is not representative of the whole track.",
               "No solver speed comparisons or official world ranks measured.",
               "XOR subsystems are constraints of the mixed CNF; no SAT claim is possible from their consistency.",
               "Only independently replay-verified XOR contradiction or forced literal implies a logically valid result.",
               "Metrics describe sparse elimination coverage, not SAT performance.",
               "Formulas without XOR may remain difficult; absence of detected XOR proof says nothing about SAT/UNSAT."
            ]}
    save(args.json,report)
    lines=["# DRNAS V13.13 — thirty newly selected SC2024 real CNFs","",
        "**New to listed SHA-frozen DRNAS cohorts; 15 official SAT and 15 UNSAT.**","",
        "| Metric | Outcome |","|---|---:|",
        f"| CNFs | {total['formulas']} |",
        f"| CNFs containing complete local XOR | {total['formulas_with_xor']} |",
        f"| XOR equations extracted | {total['xor_equations']} |",
        f"| V13.11 would examine | {total['v1311_examined']} |",
        f"| V13.12 accepted | {total['v1312_accepted']} |",
        f"| V13.12 not accepted | {total['v1312_unaccepted']} |",
        f"| Complete XOR components | {total['components']-total['components_incomplete']} / {total['components']} |",
        f"| Verified forced literals | {total['certified_forced_literals']} |",
        f"| Verified contradictions | {total['certified_contradictions']} |",
        f"| GF2 XOR elimination operations | {total['xor_operations']} |",
        f"| Median per-formula analysis wall time | {statistics.median(duration):.4f} s |",
        "",
        "## By official outcome (labels only for reporting)","",
        "| Label | CNFs | XOR equations | Sparse accepted | Certified units | Contradictions |",
        "|---|---:|---:|---:|---:|---:|"]
    for label in ("SAT","UNSAT"):
        v=per_class[label]
        lines.append(f"| {label} | {v['formulas']} | {v['xor_equations']} | {v['v1312_accepted']} | {v['certified_forced_literals']} | {v['certified_contradictions']} |")
    lines.extend(["","## Interpretation limits"]+["- "+s for s in report["limitations"]])
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V1313_30_AUDIT_PASS",json.dumps(dict(total),sort_keys=True),flush=True)

def selftest():
    # Binary check of interface and comparison cap behavior on mixed CNF;
    # also run the full V13.12 differential preflight separately.
    import tempfile
    import v1311_local_xor as xor
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"cnf"
        p.write_bytes(xor.synthetic([((1,2,3),0)], extras=[(4,)]))
        res=sparse.analyze(p)
        require(res["xor_equations"]==1 and
                res["prior_v1311"]["examined_equations"]==1 and
                res["sparse"]["accepted_equations"]==1,"basic XOR regression")
    print("V1313_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("selftest")
    cmd=sub.add_parser("run")
    for k in ("manifest","out"):cmd.add_argument("--"+k,required=True)
    cmd.add_argument("--shard",type=int,required=True)
    cmd=sub.add_parser("audit")
    for k in ("manifest","v139","combined","json","md"):
        cmd.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="run":run(args)
    else:audit(args)

if __name__=="__main__":
    main()
