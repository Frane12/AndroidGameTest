#!/usr/bin/env python3
"""DRNAS Medical R10: SHA-frozen cross-engine replication and held-out FBA audit.

Same 24/48/96/192/384 iML1515 bacterial gene cohorts as completed R9.
Compare identical R9 GPR/flux witness method under PySAT CaDiCaL195,
Glucose4 and MiniSat22.  No modification to R9 solver semantics except
choosing the SAT core.  Two opposite-order repetitions, 150s hard cap.
Cross-check every returned solution against frozen R9 result sets and
independent COBRA gene/reaction knockout FBA.  Add deterministic
stratified FBA spot checks across untested candidate interventions.
This is NOT an independent exhaustive proof above 48 genes; NOT native
DRNAS SAT, a cancer model, or a direct published gMCSpy/Gurobi comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import pathlib
import random
import statistics
import subprocess
import sys
import time
from unittest.mock import patch

import gmispy_r9_scaling as r9
import gmispy_r8_iml1515 as r8

PROTO = "DRNAS-MEDICAL-R10-CROSSENGINE-IML1515-20261106-v1"
REFERENCE_RUN = 42239472392
ENGINES = ("cadical195", "g4", "m22")
SIZES = (24, 48, 96, 192, 384)
REPS = 2
CAP = 150.0

def need(ok, why):
    if not ok:
        raise RuntimeError("R10_FAIL_CLOSED " + str(why))

def load(p):
    return json.loads(pathlib.Path(p).read_text())

def save(p, data):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

def canonical(sets):
    return tuple(sorted(tuple(sorted(x)) for x in sets))

def digest(sets):
    return hashlib.sha256(json.dumps(canonical(sets)).encode()).hexdigest()

def reference_check(path, n, source, freeze):
    ref = load(path)
    manifest = r9.check_manifest(source, freeze)
    need(n in SIZES and ref["n"] == n, "wrong reference cohort")
    need(ref["protocol"] == r9.PROTO and ref["source_SHA256"] == r9.SOURCE_SHA,
         "R9 source or protocol drift")
    need(ref["gene_SHA256"] == r9.hgenes(manifest["cohorts"][str(n)]),
         "frozen gene set hash drift")
    need(ref["complete"] is True and len(ref["trials"]) == 3,
         "R9 reference not completed with three trials")
    trials = ref["trials"]
    need(all(t["status"] == "SOLVED" and t["correct"] and
             t["SAT_UNSAT_stages"] == 3 for t in trials),
         "R9 reference contains failed trial")
    sets = canonical(trials[0]["minimal_sets"])
    need(all(canonical(t["minimal_sets"]) == sets for t in trials),
         "R9 reference trial solutions not identical")
    if n in (24, 48):
        o = ref.get("oracle")
        need(bool(o and o["exhaustively_verified"] and
                  o["candidates"] == r9.ncomb(n) and
                  canonical(o["minimal_interventions"]) == sets),
             "R9 independent exhaustive reference missing")
    else:
        need(ref.get("oracle") is None, "unexpected large-cohort exhaustive claim")
    return ref, manifest

def run_solver(source, freeze, ref_path, n, engine, rep, out):
    need(engine in ENGINES and 0 <= rep < REPS, "invalid engine or repetition")
    ref, manifest = reference_check(ref_path, n, source, freeze)
    genes = manifest["cohorts"][str(n)]
    model, src_manifest = r8.load_frozen(source)
    rules = r8.all_rules(model)
    threshold = float(src_manifest["wildtype_biomass"]) * .01
    from pysat.solvers import Solver as original_solver

    # The only intervention is SAT backend choice: R9.solve remains frozen.
    def selected_solver(*args, **kwargs):
        need(kwargs.get("name") == "cadical195", "unexpected R9 SAT API")
        kwargs["name"] = engine
        return original_solver(*args, **kwargs)

    with patch("pysat.solvers.Solver", new=selected_solver):
        result = r9.solve(model, genes, rules, threshold, CAP)
    validation = r9.verify_sets(model, genes, rules, threshold,
                                result["minimal_sets"])
    match = canonical(result["minimal_sets"]) == canonical(
        ref["trials"][0]["minimal_sets"])
    need(result["status"] == "SOLVED" and
         result["SAT_UNSAT_stages"] == 3 and
         validation["sound_minimal"] and match,
         "alternative SAT engine output does not match frozen reference")
    result.update({
        "protocol": PROTO, "R9_reference_run": REFERENCE_RUN,
        "engine": engine, "n": n, "rep": rep,
        "source_SHA256": r9.SOURCE_SHA,
        "gene_SHA256": r9.hgenes(genes),
        "reference_solution_SHA256": digest(ref["trials"][0]["minimal_sets"]),
        "result_solution_SHA256": digest(result["minimal_sets"]),
        "reference_match": match,
        "independent_minimality": validation,
        "R9_exhaustive_proof_inherited_only": n in (24, 48),
        "independent_exhaustive_completeness_R10": False,
        "native_drnas": False,
        "published_gMCSpy_comparison": False,
        "human_cancer_model": False,
    })
    save(out, result)
    print("R10_INTERNAL", json.dumps({
        "engine": engine, "n": n, "rep": rep,
        "wall_s": result["wall_s"],
        "solutions": len(result["minimal_sets"]),
        "lp_calls": result["lp_calls"],
        "reference_match": match
    }, sort_keys=True), flush=True)

def subprocess_trial(cfg, path):
    path = pathlib.Path(path)
    config = path.with_suffix(".config.json")
    save(config, cfg)
    start = time.perf_counter()
    try:
        p = subprocess.run([sys.executable, __file__, "internal",
                            "--config", str(config), "--out", str(path)],
                           capture_output=True, text=True, timeout=CAP + 75)
        outer = round(time.perf_counter() - start, 6)
        path.with_suffix(".stdout.log").write_text(p.stdout[-25000:])
        path.with_suffix(".stderr.log").write_text(p.stderr[-25000:])
        if p.returncode:
            return {"status": "ERROR", "outer_wall_s": outer,
                    "error": (p.stderr or p.stdout)[-3000:]}
        result = load(path)
        result["outer_wall_s"] = outer
        return result
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "outer_wall_s":
                round(time.perf_counter() - start, 6)}

def deterministic_audit(source, n, genes, expected_sets, out):
    """Independent FBA spot checks; sampled completeness, not a certificate."""
    model, src = r8.load_frozen(source)
    rules = r8.all_rules(model)
    threshold = float(src["wildtype_biomass"]) * .01
    seed = hashlib.sha256(
        (r9.SOURCE_SHA + r9.hgenes(genes) + "R10-heldout").encode()
    ).hexdigest()
    rng = random.Random(int(seed, 16))
    candidates = set()
    targets = {1: min(n, 32), 2: 64, 3: 128}
    for k, target in targets.items():
        total = math.comb(n, k)
        while sum(len(c) == k for c in candidates) < min(target, total):
            candidates.add(tuple(sorted(rng.sample(range(n), k))))
    # Add all known minima and structured one-gene replacements (near misses).
    index = {g: i for i, g in enumerate(genes)}
    for s in expected_sets:
        combo = tuple(sorted(index[g] for g in s))
        candidates.add(combo)
        for j in combo:
            replacement = (j + n // 2) % n
            if replacement in combo:
                replacement = next(x for x in range(n) if x not in combo)
            candidates.add(tuple(sorted((set(combo) - {j}) | {replacement})))
    mins = [set(s) for s in expected_sets]
    checked, positives, negatives = 0, 0, 0
    for combo in sorted(candidates, key=lambda c: (len(c), c)):
        knockout = {genes[i] for i in combo}
        predicted = any(m.issubset(knockout) for m in mins)
        first = r9.growth(model, genes, combo, rules, "gene")
        second = r9.growth(model, genes, combo, rules, "reaction")
        need(abs(first - second) <= 1e-6, "independent FBA paths differ")
        actual = first < threshold
        need(actual == predicted,
             "R9 solution-set prediction contradicted by independent FBA " +
             str(combo))
        checked += 1
        if actual:
            positives += 1
        else:
            negatives += 1
    record = {"protocol": PROTO, "n": n, "seed_SHA256": seed,
              "checked": checked, "lethal": positives, "viable": negatives,
              "two_FBA_paths_per_case": True, "status": "SAMPLE_PASS",
              "not_exhaustive": True}
    save(out, record)
    print("R10_SAMPLED_AUDIT", json.dumps(record, sort_keys=True), flush=True)
    return record

def cohort(source, freeze, ref_path, n, out):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    ref, manifest = reference_check(ref_path, n, source, freeze)
    genes = manifest["cohorts"][str(n)]
    rows = []
    for rep in range(REPS):
        order = ENGINES if rep == 0 else tuple(reversed(ENGINES))
        for engine in order:
            cfg = {"source": str(pathlib.Path(source).resolve()),
                   "freeze": str(pathlib.Path(freeze).resolve()),
                   "reference": str(pathlib.Path(ref_path).resolve()),
                   "n": n, "engine": engine, "rep": rep}
            row = subprocess_trial(cfg, out / f"{engine}-rep{rep}.json")
            row.update({"engine": engine, "rep": rep})
            row["verified"] = (row["status"] == "SOLVED" and
                               row.get("reference_match") is True and
                               row["wall_s"] <= CAP)
            rows.append(row)
            print("R10_RESULT", json.dumps({
                "n": n, "rep": rep, "engine": engine,
                "status": row["status"], "wall_s": row.get("wall_s"),
                "verified": row["verified"], "error": row.get("error", "")[-200:]
            }, sort_keys=True), flush=True)
            save(out / "summary.json", {
                "protocol": PROTO, "n": n, "rows": rows, "partial": True
            })

    sample = deterministic_audit(source, n, genes,
        ref["trials"][0]["minimal_sets"], out / "independent_sample.json")
    medians = {}
    for engine in ENGINES:
        good = [row["wall_s"] for row in rows
                if row["engine"] == engine and row["verified"]]
        medians[engine] = round(statistics.median(good), 6) \
            if len(good) == REPS else None
    ratios = {}
    if medians["cadical195"] is not None:
        for engine in ENGINES[1:]:
            if medians[engine] is not None:
                ratios[engine] = round(
                    medians["cadical195"] / medians[engine], 5)
    record = {
        "protocol": PROTO, "n": n, "source_SHA256": r9.SOURCE_SHA,
        "gene_SHA256": r9.hgenes(genes), "R9_reference_run": REFERENCE_RUN,
        "reference_minimal_count": len(ref["trials"][0]["minimal_sets"]),
        "R9_exhaustive_reference_only_for_24_48": n in (24, 48),
        "R10_independent_exhaustive_completeness": False,
        "cap_s": CAP, "repetitions": REPS, "rows": rows,
        "medians_s": medians, "speedup_vs_cadical195": ratios,
        "sample_audit": sample, "partial": False,
        "all_engine_trials_verified": all(x["verified"] for x in rows),
        "not_native_drnas": True, "not_human_cancer_model": True,
        "not_published_gMCSpy_comparison": True
    }
    save(out / "summary.json", record)
    print("R10_COHORT_FINAL", json.dumps({
        "n": n, "all_verified": record["all_engine_trials_verified"],
        "medians_s": medians, "speedup_vs_cadical195": ratios,
        "sampled": sample["checked"]
    }, sort_keys=True), flush=True)

def audit(paths, output):
    need(len(paths) == len(SIZES), "all five independent cohort reports required")
    records = [load(p) for p in paths]
    need([r["n"] for r in records] == list(SIZES),
         "missing or out of order cohort")
    for r in records:
        n = r["n"]
        need(r["protocol"] == PROTO and r["source_SHA256"] == r9.SOURCE_SHA
             and r["R9_reference_run"] == REFERENCE_RUN and
             r["partial"] is False and len(r["rows"]) == REPS * len(ENGINES),
             "incomplete data")
        need(r["sample_audit"]["status"] == "SAMPLE_PASS" and
             r["sample_audit"]["checked"] >= 100,
             "FBA independent sample audit missing")
        need({(x["rep"], x["engine"]) for x in r["rows"]} ==
             set(itertools.product(range(REPS), ENGINES)),
             "missing paired engine trial")
        for e in ENGINES:
            rows = [x for x in r["rows"] if x["engine"] == e]
            if r["medians_s"][e] is not None:
                need(all(x["verified"] and x["status"] == "SOLVED"
                         and x["reference_match"] for x in rows),
                     "invalid timing entered into medians")
        if n in (24, 48):
            need(r["R9_exhaustive_reference_only_for_24_48"],
                 "small exact reference requirement")
        else:
            need(not r["R9_exhaustive_reference_only_for_24_48"],
                 "large cohort overclaims completeness")
    result = {
        "protocol": PROTO, "status": "PASS_AUDIT_WITH_LIMITATIONS",
        "source_SHA256": r9.SOURCE_SHA, "R9_reference_run": REFERENCE_RUN,
        "cohorts": [{
            "n": r["n"],
            "median_s": r["medians_s"],
            "speedup_vs_cadical195": r["speedup_vs_cadical195"],
            "all_engine_trials_verified": r["all_engine_trials_verified"],
            "sampled_FBA_pairs": r["sample_audit"]["checked"]
        } for r in records],
        "conclusions_scope": {
            "only_backend_changed": True,
            "independent_exhaustive_completeness_R10": False,
            "R9_independent_exhaustive_reference_24_48": True,
            "larger_cohorts_cross_engine_and_sampled_only": True,
            "original_published_gMCSpy_not_compared": True,
            "not_native_DRNAS": True,
            "not_a_human_cancer_model": True,
            "no_general_complexity_proof": True
        }
    }
    save(output, result)
    print("R10_FINAL", json.dumps(result, sort_keys=True), flush=True)

def selftest():
    need(ENGINES == ("cadical195", "g4", "m22"), "backend drift")
    need(r9.SOURCE_SHA ==
         "9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28",
         "R9 source drift")
    need(r9.ncomb(384) == 9437504, "combinatoric drift")
    need(digest([["b0001", "b0002"], ["b0003"]]) ==
         digest([["b0003"], ["b0002", "b0001"]]),
         "set equality mismatch")
    print("R10_SELFTEST_PASS", json.dumps({
        "engines": ENGINES, "sizes": SIZES, "reps": REPS
    }), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "internal", "cohort", "audit"))
    p.add_argument("--source", default="r10/r9/source")
    p.add_argument("--freeze", default="r10/r9/frozen")
    p.add_argument("--reference", default="r10/ref/summary.json")
    p.add_argument("--n", type=int, default=24)
    p.add_argument("--out", default="r10/results")
    p.add_argument("--config")
    p.add_argument("--inputs", nargs="*")
    a = p.parse_args()
    if a.action == "selftest":
        selftest()
    elif a.action == "internal":
        need(bool(a.config), "missing config")
        c = load(a.config)
        run_solver(c["source"], c["freeze"], c["reference"],
                   c["n"], c["engine"], c["rep"], a.out)
    elif a.action == "cohort":
        need(a.n in SIZES, "unexpected n")
        cohort(a.source, a.freeze, a.reference, a.n, a.out)
    else:
        audit(a.inputs or [], a.out)
