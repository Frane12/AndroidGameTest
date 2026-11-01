#!/usr/bin/env python3
"""DRNAS V13.12: bounded, auditable, sparse GF(2) processing of V13.11 XOR equations.

Read-only observational study on frozen SAT Competition 2024 CNFs.
No SAT/UNSAT prediction from labels. No old solver modified.
A local XOR equation is implied by four EXACT CNF clauses; a parity contradiction
is valid for global CNF ONLY with a replay-verified subset proof.
Partial elimination is never interpreted as SAT.
"""
import argparse
import collections
import hashlib
import json
import random
import sys
import tempfile
import time
from pathlib import Path

import official_shortlong_select as source
import v1311_local_xor as prior

PROTOCOL = "DRNAS-V1312-BOUNDED-SPARSE-GF2-20261101-v1"
SOURCE_RUN = 41261415700
PRIOR_RUN = 41262480333

# These bounds are explicit for reproducible partial analysis, not theorem limits.
MAX_INPUT_EQUATIONS = 115000
MAX_STEPS_PER_COMPONENT = 240000
MAX_BASIS_ROWS = 110000
MAX_ROW_WIDTH = 128
MAX_PROVENANCE = 512
MAX_VERIFIED_CERTIFICATES = 32

source.RAW_CAP = 96 * 1024**2
source.CNF_CAP = 96 * 1024**2
source.VARIABLE_CAP = 1000000
source.CLAUSE_CAP = 4000000


def insist(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(Path(path).read_text())


def dump(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")


def baseline_v1311_coverage(equations, components):
    """Reconstruct previous conservative caps exactly, without new solving."""
    budget = prior.MAX_ANALYZED_EQS
    scanned = 0
    skipped = 0
    skipped_eqs = 0
    for ids in components:
        variables = len({v for k in ids for v in equations[k][0]})
        if (len(ids) > prior.MAX_COMPONENT_EQS or
                variables > prior.MAX_COMPONENT_VARS or len(ids) > budget):
            skipped += 1
            skipped_eqs += len(ids)
        else:
            budget -= len(ids)
            scanned += len(ids)
    return {"examined_equations": scanned, "skipped_equations": skipped_eqs,
            "skipped_components": skipped}


def eliminate_component(equations, ids, budget):
    """Incremental exact GF(2) with source-row provenance for soundness.

    Sparse sets grow only within fixed row / provenance / step bounds. A skipped
    equation is NEVER assumed redundant and the component is marked incomplete.
    """
    pivots = {}  # min variable -> (frozenset variable support, rhs, frozenset source IDs)
    visited = 0
    accepted = 0
    rejected = 0
    zero_rows = 0
    xor_ops = 0
    max_width = 0
    max_provenance = 0
    certificates = []
    verified_units = 0
    contradictions = 0
    exhausted = False
    t0 = time.monotonic()

    for idx in ids:
        if visited >= budget or xor_ops >= MAX_STEPS_PER_COMPONENT:
            exhausted = True
            break
        visited += 1
        support, rhs = equations[idx]
        row = set(support)
        val = rhs
        certificate = {idx}
        success = True
        while row:
            pivot = min(row)
            old = pivots.get(pivot)
            if old is None:
                if len(pivots) >= MAX_BASIS_ROWS:
                    success = False
                elif len(row) > MAX_ROW_WIDTH or len(certificate) > MAX_PROVENANCE:
                    success = False
                else:
                    pivots[pivot] = (frozenset(row), val, frozenset(certificate))
                break
            if xor_ops >= MAX_STEPS_PER_COMPONENT:
                success = False
                exhausted = True
                break
            base_row, base_rhs, base_proof = old
            newrow = row.symmetric_difference(base_row)
            newcert = certificate.symmetric_difference(base_proof)
            xor_ops += 1
            if len(newrow) > MAX_ROW_WIDTH or len(newcert) > MAX_PROVENANCE:
                success = False
                break
            row = newrow
            val ^= base_rhs
            certificate = newcert
        if not success:
            rejected += 1
            if exhausted:
                break
            continue
        accepted += 1
        max_width = max(max_width, len(row))
        max_provenance = max(max_provenance, len(certificate))
        if row:
            if len(row) == 1 and len(certificates) < MAX_VERIFIED_CERTIFICATES:
                source_ids = sorted(certificate)
                variable = next(iter(row))
                insist(prior.proof_valid(equations, source_ids, (variable,), val),
                       "unsound implied unit certificate")
                verified_units += 1
                certificates.append({"kind": "implied_literal", "variable": variable,
                                     "value": val, "equation_indices": source_ids,
                                     "replay_verified": True})
        else:
            zero_rows += 1
            if val:
                source_ids = sorted(certificate)
                insist(prior.proof_valid(equations, source_ids, (), 1),
                       "unsound UNSAT contradiction certificate")
                contradictions += 1
                if len(certificates) < MAX_VERIFIED_CERTIFICATES:
                    certificates.append({"kind": "unsat_subset_proof",
                                         "equation_indices": source_ids,
                                         "replay_verified": True})
                # Once a certified contradiction is found, more work is unnecessary.
                exhausted = True
                break

    return {"input_equations": len(ids), "visited_equations": visited,
            "accepted_equations": accepted, "rejected_equations": rejected,
            "unvisited_equations": len(ids) - visited, "basis_rank_lower_bound": len(pivots),
            "zero_rows": zero_rows, "xor_steps": xor_ops,
            "max_basis_row_width": max_width, "max_provenance_size": max_provenance,
            "certified_contradictions": contradictions,
            "certified_units": verified_units, "certificates": certificates,
            "complete_elimination": not exhausted and rejected == 0 and visited == len(ids),
            "elapsed_s": round(time.monotonic()-t0, 6)}


def analyze(path):
    t0 = time.monotonic()
    n, m, equations, extraction = prior.extract(path)
    comps = prior.components(equations)
    previous = baseline_v1311_coverage(equations, comps)
    budget = MAX_INPUT_EQUATIONS
    agg = collections.Counter()
    proofs = []
    incomplete = 0
    cases = []
    for ids in comps:
        if budget <= 0:
            agg["unvisited_equations"] += len(ids)
            agg["components_not_attempted"] += 1
            incomplete += 1
            continue
        outcome = eliminate_component(equations, ids, budget)
        budget -= outcome["visited_equations"]
        for key in ("visited_equations", "accepted_equations", "rejected_equations",
                    "unvisited_equations", "basis_rank_lower_bound", "zero_rows",
                    "xor_steps", "certified_contradictions", "certified_units"):
            agg[key] += outcome[key]
        agg["components_attempted"] += 1
        if outcome["complete_elimination"]:
            agg["components_fully_eliminated"] += 1
        else:
            incomplete += 1
        if outcome["certificates"] and len(proofs) < MAX_VERIFIED_CERTIFICATES:
            proofs.extend(outcome["certificates"][:MAX_VERIFIED_CERTIFICATES-len(proofs)])
        if len(cases) < 12 and (not outcome["complete_elimination"] or
                                outcome["certified_contradictions"]):
            cases.append({k: v for k,v in outcome.items() if k != "certificates"})
    insist(agg["visited_equations"] + agg["unvisited_equations"] == len(equations),
           "some XOR equations were lost")
    insist(agg["accepted_equations"] + agg["rejected_equations"] <=
           agg["visited_equations"], "invalid sparse accounting")
    return {"variables": n, "clauses": m, "xor_equations": len(equations),
            "components": len(comps), "prior_v1311": previous,
            "sparse": dict(agg), "incomplete_components": incomplete,
            "extraction": extraction, "certificates": proofs,
            "incomplete_component_examples": cases,
            "total_wall_s": round(time.monotonic()-t0, 6),
            "observational_only": True}


def selftest():
    # Validate every claimed certificate using exact brute force on small CNFs,
    # including redundant equations, contradictory subsystems and mixed clauses.
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/"trial.cnf"
        rng=random.Random(1312)
        for trial in range(65):
            triples=list(__import__("itertools").combinations(range(1, 8), 3))
            rng.shuffle(triples)
            selected=[(tri, rng.randrange(2)) for tri in triples[:rng.randint(2,12)]]
            raw=prior.synthetic(selected, extras=[(1,-2), (4,5)])
            path.write_bytes(raw)
            out=analyze(path)
            models=prior.brute_models(raw)
            for cert in out["certificates"]:
                if cert["kind"] == "unsat_subset_proof":
                    insist(len(models)==0, "false UNSAT inference")
                else:
                    v, bit=cert["variable"],cert["value"]
                    insist(all(((model>>(v-1))&1)==bit for model in models),
                           "invalid forced literal")
            insist(out["sparse"]["visited_equations"] == out["xor_equations"] or
                   out["sparse"]["certified_contradictions"] > 0,
                   "small instance stopped without proof")
        # Direct complete contradiction from overlapping 3-XOR equations.
        eq=[((1,2,3),0),((1,2,4),0),((1,3,4),0),((2,3,4),1)]
        path.write_bytes(prior.synthetic(eq))
        result=analyze(path)
        # Do not impose a contradiction on an otherwise underdetermined system.
        models=prior.brute_models(path.read_bytes())
        if result["sparse"]["certified_contradictions"]:
            insist(not models,"contradiction not real")
        # Large connected and sparse, no exponential branching.
        eq=[((i,i+1,i+2), i%2) for i in range(1,4001)]
        r=eliminate_component(eq,list(range(len(eq))), len(eq))
        insist(r["visited_equations"]==len(eq) and r["rejected_equations"]==0,
               "failed large sparse complete instance")
        insist(r["certified_contradictions"]==0,
               "wrong unsatisfiable certificate in chain")
    print("V1312_SELFTEST_PASS 65 brute-force mixed trials; 4000-equation connected chain",flush=True)


def run(args):
    manifest=read(args.manifest)
    insist(manifest["protocol"] == "DRNAS-V139-FRESH-EXTERNAL-SC2024-12-20261101",
           "unrecognized frozen V13.9 manifest")
    insist(len(manifest["cases"])==12 and 0<=args.shard<6, "wrong shard")
    folder=Path(args.out)
    folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    for entry in manifest["cases"][args.shard::6]:
        fn=folder/(entry["id"]+".cnf")
        actual=source.download_and_features(entry["id"],fn)
        insist(actual["sha256"]==entry["sha256"] and
               actual["features"]==entry["features"], "SHA/feature drift")
        try:
            result=analyze(fn)
        finally:
            fn.unlink(missing_ok=True)
        insist(result["variables"]==entry["variables"] and
               result["clauses"]==entry["clauses"],"DIMACS identity mismatch")
        rows.append({"id":entry["id"],"sha256":entry["sha256"],
                     "official_label_for_audit_only":entry["official_label"],
                     "metrics":result})
        dump(folder/"rows.json",rows)
        q=result["sparse"]
        print("V1312_CASE",args.shard,entry["id"][:10],
              "eq",result["xor_equations"],
              "old",result["prior_v1311"]["examined_equations"],
              "new",q["accepted_equations"],
              "visited",q["visited_equations"],
              "skipped",q["rejected_equations"]+q["unvisited_equations"],
              "contradictions",q["certified_contradictions"],
              "certified_units",q["certified_units"],
              "wall_s",result["total_wall_s"],flush=True)
    insist(len(rows)==2, "incomplete frozen shard")
    print("V1312_SHARD_PASS",args.shard,flush=True)


def audit(args):
    manifest=read(args.manifest)
    prior_report=read(args.prior)
    insist(manifest["protocol"]=="DRNAS-V139-FRESH-EXTERNAL-SC2024-12-20261101",
           "bad frozen manifest")
    insist(prior_report["protocol"]=="DRNAS-V1311-CERTIFIED-LOCAL-XOR-20261101-v1",
           "bad V13.11 audit")
    old={entry["id"]: entry for entry in prior_report["rows"]}
    rows=[]
    for shard in range(6):
        folder=Path(args.combined)/f"v1312-sparse-shard-{shard}"
        part=read(folder/"rows.json")
        expected=manifest["cases"][shard::6]
        insist(len(part)==2 and [x["sha256"] for x in part]==
               [x["sha256"] for x in expected],"shard identity failure")
        rows+=part
    total=collections.Counter()
    for item in rows:
        m=item["metrics"]
        oldrow=old[item["id"]]
        insist(item["sha256"]==oldrow["sha256"],"prior mismatch")
        insist(m["xor_equations"]==oldrow["metrics"]["complete_local_3xor_equations"],
               "different equation identification from V13.11")
        insist(m["prior_v1311"]["examined_equations"]==
               oldrow["metrics"]["examined_equations"], "incorrect baseline reconstruction")
        insist(m["prior_v1311"]["skipped_equations"]==
               oldrow["metrics"]["skipped_equations"],"incorrect prior skip accounting")
        total["xor_equations"]+=m["xor_equations"]
        total["old_examined_equations"]+=m["prior_v1311"]["examined_equations"]
        total["old_skipped_equations"]+=m["prior_v1311"]["skipped_equations"]
        total["components"]+=m["components"]
        total["incomplete_components"]+=m["incomplete_components"]
        for key,value in m["sparse"].items():
            total[key]+=value
        total["cases_with_contradiction"]+=int(m["sparse"].get("certified_contradictions",0)>0)
        total["cases_with_certified_unit"]+=int(m["sparse"].get("certified_units",0)>0)
        insist(all(c["replay_verified"] for c in m["certificates"]),
               "unverified stored proof")
    insist(total["xor_equations"]==prior_report["totals"]["complete_local_3xor_equations"],
           "prior XOR population mismatch")
    report={"protocol":PROTOCOL,"frozen_v139_run":SOURCE_RUN,
            "prior_v1311_run":PRIOR_RUN,"cases":len(rows),
            "totals":dict(total),"per_case":rows,
            "limits":{"input_equations":MAX_INPUT_EQUATIONS,
                      "max_steps_per_component":MAX_STEPS_PER_COMPONENT,
                      "max_basis_rows":MAX_BASIS_ROWS,
                      "max_row_width":MAX_ROW_WIDTH,
                      "max_provenance_rows":MAX_PROVENANCE},
            "limitations":[
              "Frozen 12 public 2024 SAT CNFs are a biased sample, not a world ranking.",
              "Sparse GF2 is an exploratory certified analysis, not a SAT solver.",
              "Large components with fill/provenance/step budgets may remain incomplete.",
              "0 contradictions or 0 units does not imply SAT or absence of other useful inference.",
              "No solver timings were collected; no speedup or theorem demonstrated.",
              "Strict XOR blocks are subsets of mixed CNF; only replay-certified conclusions can be applied globally."
            ]}
    dump(args.json,report)
    lines=["# DRNAS V13.12 — bounded sparse GF(2) on real 2024 CNFs","",
           "**12 SHA-frozen V13.9 cases; exact V13.11 equation identities validated.**","",
           "| Metric | V13.11 | V13.12 |",
           "|---|---:|---:|",
           f"| XOR equations identified | {total['xor_equations']} | {total['xor_equations']} |",
           f"| Equations examined/accepted | {total['old_examined_equations']} | {total['accepted_equations']} |",
           f"| Not accepted | {total['old_skipped_equations']} | {total['rejected_equations'] + total['unvisited_equations']} |",
           f"| Components fully processed | {total['components'] - prior_report['totals']['skipped_components']} | {total['components_fully_eliminated']} |",
           f"| Verified contradictions | {prior_report['totals']['certified_xor_contradictions']} | {total['certified_contradictions']} |",
           f"| Verified forced literals | {prior_report['totals']['certified_forced_literals']} | {total['certified_units']} |",
           "",
           f"Sparse engine GF(2) XOR operations: {total['xor_steps']}",
           f"Incomplete components: {total['incomplete_components']}",
           "", "## Scope / limitations"] + ["- "+s for s in report["limitations"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V1312_AUDIT_PASS",json.dumps(dict(total),sort_keys=True),flush=True)


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("selftest")
    x=sub.add_parser("run")
    for name in ("manifest","out"): x.add_argument("--"+name,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("audit")
    for name in ("manifest","prior","combined","json","md"):
        x.add_argument("--"+name,required=True)
    args=parser.parse_args()
    if args.command=="selftest": selftest()
    elif args.command=="run":run(args)
    else:audit(args)


if __name__=="__main__":
    main()
