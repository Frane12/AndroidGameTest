#!/usr/bin/env python3
"""MRE8f — MRE6f-reference certified equality gate, no unsound XOR guesses.

Bounded source-locked SAT2026 experiments REUSE MRE6f's exact pinned binary,
same per-source seeds, original source manifests and four previous safety rules.
A separate SAT2024/2025 reference-selected pilot measures actual solver verdict
PAR2 on six locked sources using the existing full-solving native CMS bridge.

All wall times include parse, front gate, CNF rewrite, subprocess and model audit.
Neither cohort is a new blind holdout. Do not promote to production.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import pathlib
import random
import statistics
import subprocess
import tempfile
import time

import mre6d_paired as d
import mre6d_all_equalities as equal
import mre6e_conflict_diagnostic as diagnostic
import mre6f_repeat_causal as ref6f
import mre6b_blind_freeze as frozen6
import mre7_reference_easy_freeze as frozen7
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195
import mre1_cross_representation as mre1

PROTO = "DRNAS-MRE8F-MRE6F-REFERENCE-LOCKED7-BUDGET-PLUS-PILOT6-v1"
ROOT = pathlib.Path("mre8f")
MODES = ("cms_native", "mre6f_all", "mre8f_gate")
CAP_BOUNDED = 6.0
CAP_VERDICT = 8.0
CONFLICT_CAPS = (1000, 5000)
REPS_BOUNDED = 3
REPS_VERDICT = 2
SHARDS_BOUNDED = 4
SHARDS_VERDICT = 3

# Frozen before new results. Structural evidence, NEVER learned from a target run.
MIN_MERGES = 128
MIN_CLAUSES_REMOVED = 256
MIN_REMOVED_FRACTION = 0.08
MAX_CLAUSES = 85000


def need(cond, reason):
    if not cond:
        raise RuntimeError("MRE8F_FAIL_CLOSED " + str(reason))


def source_set(dataset):
    if dataset == "bounded":
        cases = diagnostic.cases()
        need(len(cases) == 7, "original MRE6f reference cohort changed")
        return [(c, d.ROOT / c["filename"]) for c in cases]
    need(dataset == "verdict", "unknown dataset")
    m = frozen7.verify()
    need(len(m["selected_cases"]) == 6, "MRE7 pilot six SHA set changed")
    need(m["source_selection_before_mre_gate"], "source selection leak")
    return [(c, frozen7.ROOT / c["filename"]) for c in m["selected_cases"]]


def expected_status(case):
    return case.get("original_verified_status", case.get("reference_screen_status"))


def gate_prepare(source, root):
    """Cheap original-CNF certificate preflight; full quotient ONLY if promising.

    d.find_direct_equalities verifies BOTH actual source binary implications.
    A second complete original-CNF quotient replays every equivalence edge.
    Unprofitable candidate falls back to original CNF without writing it.
    """
    n, original = exact.parse_dimacs(source)
    clauses = len(original)
    need(n > 0 and 0 < clauses <= MAX_CLAUSES, "invalid CNF geometry")
    pairs = d.find_direct_equalities(original)
    report = dict(kind="ORIGINAL_TWO_BINARY_CLAUSE_EQUIVALENCE",
                  source_direct_pairs=len(pairs),
                  min_merges=MIN_MERGES,
                  min_clauses_removed=MIN_CLAUSES_REMOVED,
                  min_removed_fraction=MIN_REMOVED_FRACTION,
                  before_clauses=clauses, after_clauses=clauses,
                  variables_eliminated=0, removed_clauses=0,
                  removed_fraction=0.0, applied=False,
                  reason="ABSTAIN_INSUFFICIENT_DIRECT_PAIRS")
    if len(pairs) < MIN_MERGES:
        return source, {}, report
    rewritten, rows, mapping, evidence = equal.quotient(original)
    need(not rows, "unexpected XOR import in equality-only arm")
    eliminated = len(mapping)
    removed = clauses - len(rewritten)
    need(removed >= 0 and eliminated >= 0, "invalid quotient accounting")
    report.update(after_clauses=len(rewritten),
                  variables_eliminated=eliminated,
                  removed_clauses=removed,
                  removed_fraction=round(removed / clauses, 8),
                  certificate_edges=evidence["pairs"])
    eligible = (eliminated >= MIN_MERGES and
                removed >= MIN_CLAUSES_REMOVED and
                removed / clauses >= MIN_REMOVED_FRACTION)
    if not eligible:
        report["reason"] = "ABSTAIN_UNPROFITABLE_ACTUAL_QUOTIENT"
        return source, {}, report
    target = root / "certified-quotient.cnf"
    mre1.write_cnf(target, n, rewritten, [])
    report["reason"] = "APPLY_CERTIFIED_SOURCE_EQUIVALENCES"
    report["applied"] = True
    return target, mapping, report


def run_one(case, source, rep, mode, dataset, conflict_cap, binary):
    need(mode in MODES, "unrecognized arm")
    need(dataset in ("bounded", "verdict"), "unrecognized benchmark dataset")
    need(rep in range(REPS_BOUNDED if dataset == "bounded" else REPS_VERDICT),
         "seed index outside precommitted design")
    if dataset == "bounded":
        need(conflict_cap in CONFLICT_CAPS, "unlocked conflict budget")
    else:
        need(conflict_cap is None, "full-solving attempt got conflict limit")
    need(frozen6.sha256(source.read_bytes()) == case["sha256"],
         "original source SHA mismatched")
    cap = CAP_BOUNDED if dataset == "bounded" else CAP_VERDICT
    seed = d.seed_of(case["sha256"], rep)
    start = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="drnas-mre8f-") as temp:
        folder = pathlib.Path(temp)
        cnf = source
        mapping = {}
        gate = dict(reason="NATIVE_UNMODIFIED", applied=False)
        prep_start = time.perf_counter()
        if mode == "cms_native":
            # Preserve exact MRE6f baseline's parser and source-input code path.
            cnf, _, _, _, _ = d.build_arm(source, "native_no_xor", folder)
        elif mode == "mre6f_all":
            # Preserve exact MRE6f full certified equality implementation.
            cnf, _, _, meta, proof = d.build_arm(source, "all_no_xor", folder)
            mapping = proof["mapping"] if proof else {}
            gate = dict(reason=meta["gate"], applied=bool(mapping),
                        variables_eliminated=len(mapping),
                        before_clauses=meta["cnf_before"],
                        after_clauses=meta["cnf_after"],
                        removed_clauses=meta["cnf_before"] - meta["cnf_after"])
        else:
            cnf, mapping, gate = gate_prepare(source, folder)
        prep = time.perf_counter() - prep_start

        empty = folder / "empty.tsv"
        empty.write_text("")
        env = os.environ.copy()
        env["DRNAS_TRACE_ENABLED"] = "0"
        env["DRNAS_TAG_0"] = ""
        env["DRNAS_TAG_1"] = ""
        if conflict_cap is None:
            env.pop("DRNAS_MAX_CONFLICTS", None)
        else:
            env["DRNAS_MAX_CONFLICTS"] = str(conflict_cap)
        left = cap - (time.perf_counter() - start)
        status, native, verified = "TIMEOUT", None, False
        process_wall = None
        if left > 0.05:
            native_start = time.perf_counter()
            try:
                p = subprocess.run(
                    [str(pathlib.Path(binary).resolve()),
                     str(pathlib.Path(cnf).resolve()),
                     str(empty.resolve()), str(empty.resolve()),
                     "source_xor_no_gauss", str(seed)],
                    text=True, capture_output=True, errors="replace",
                    timeout=left, env=env, check=False)
            except subprocess.TimeoutExpired:
                p = None
            process_wall = time.perf_counter() - native_start
            if p is not None:
                need(p.returncode == 0, "native CMS failed: " + p.stderr[-900:])
                status, native, model = diagnostic.parse(p.stdout)
                if status == "SAT":
                    if mapping:
                        model = equal.reconstruct(model, mapping)
                    r195.verify_model(source, model)
                    verified = True
                if status in ("SAT", "UNSAT"):
                    need(status == expected_status(case),
                         "solver verdict contradicts frozen reference")
                elif status == "BUDGET":
                    need(conflict_cap is not None and native["conflicts"] > 0,
                         "invalid bounded solver UNKNOWN")
                else:
                    need(False, "unexpected native status")
        elapsed = time.perf_counter() - start
        if elapsed >= cap:
            status, verified = "TIMEOUT", False
        result = dict(protocol=PROTO, dataset=dataset,
                      study_source_sha256=case["sha256"],
                      official_gbd=case["gbd"],
                      original_reference_status=expected_status(case),
                      source_year=case.get("year", 2026),
                      mode=mode, rep=rep, seed=seed,
                      conflict_cap=conflict_cap, status=status,
                      total_wall_s=round(elapsed, 6),
                      preprocessing_s=round(prep, 6),
                      cms_subprocess_wall_s=(round(process_wall, 6)
                                             if process_wall is not None else None),
                      par2_s=round(elapsed if status in ("SAT", "UNSAT")
                                   else 2 * cap, 6),
                      counters=native, gate=gate,
                      quotient_applied=bool(mapping),
                      sat_original_model_verified=verified,
                      unsat_independent_LRAT=False,
                      originally_sha_verified=True,
                      same_CMS_source_commit=d.SOURCE_CMS_SHA,
                      original_clauses=case["clauses"],
                      original_vars=case["vars"],
                      reference_MRE6f_run=42499854392,
                      pilot_not_new_blind_holdout=True)
        if status == "SAT":
            need(verified, "unchecked original SAT witness")
        return result


def shard(dataset, idx, binary):
    num = SHARDS_BOUNDED if dataset == "bounded" else SHARDS_VERDICT
    need(0 <= idx < num, "invalid shard")
    cases = [p for i, p in enumerate(source_set(dataset)) if i % num == idx]
    need(cases, "no frozen source in shard")
    reps = REPS_BOUNDED if dataset == "bounded" else REPS_VERDICT
    limits = CONFLICT_CAPS if dataset == "bounded" else (None,)
    folder = ROOT / dataset
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for case, source in cases:
        for rep in range(reps):
            for limit in limits:
                order = list(MODES)
                random.Random(PROTO + case["sha256"] + "|" + str(rep)
                              + "|" + str(limit)).shuffle(order)
                for mode in order:
                    row = run_one(case, source, rep, mode, dataset, limit, binary)
                    rows.append(row)
                    (folder / ("shard-%d.json" % idx)).write_text(
                        json.dumps(rows, sort_keys=True) + "\n")
                    print("MRE8F_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == len(cases) * reps * len(limits) * len(MODES),
         "incomplete full source-paired shard")
    print("MRE8F_SHARD_PASS", dataset, idx, len(rows), flush=True)


def audit(dataset):
    cases = source_set(dataset)
    num = SHARDS_BOUNDED if dataset == "bounded" else SHARDS_VERDICT
    reps = REPS_BOUNDED if dataset == "bounded" else REPS_VERDICT
    limits = CONFLICT_CAPS if dataset == "bounded" else (None,)
    expected = {c["sha256"]: c for c, _ in cases}
    pairs = collections.defaultdict(dict)
    rows = []
    for idx in range(num):
        p = ROOT / dataset / ("shard-%d.json" % idx)
        need(p.exists(), "missing source shard " + str(idx))
        rows.extend(json.loads(p.read_text()))
    need(len(rows) == len(cases) * reps * len(limits) * len(MODES),
         "missing attempts across immutable sources")
    for r in rows:
        c = expected.get(r["study_source_sha256"])
        need(c is not None and r["official_gbd"] == c["gbd"],
             "unknown or substituted source")
        need(r["protocol"] == PROTO and r["dataset"] == dataset,
             "unexpected benchmark protocol")
        need(r["originally_sha_verified"] and
             r["same_CMS_source_commit"] == d.SOURCE_CMS_SHA,
             "wrong source or CMS provenance")
        need(r["rep"] in range(reps) and r["conflict_cap"] in limits,
             "invalid repetition or conflict budget")
        if r["status"] == "SAT":
            need(r["sat_original_model_verified"],
                 "SAT witness was not checked against original source")
        if r["status"] == "UNSAT":
            need(expected_status(c) == "UNSAT", "unsupported UNSAT")
        if r["status"] == "BUDGET":
            need(dataset == "bounded" and r["counters"] and
                 r["counters"]["conflicts"] > 0, "fake bounded CDCL sample")
        key = (r["study_source_sha256"], r["rep"], r["conflict_cap"])
        need(r["mode"] not in pairs[key], "duplicate paired arm")
        pairs[key][r["mode"]] = r
    need(len(pairs) == len(cases) * reps * len(limits), "missing paired group")
    for arms in pairs.values():
        need(set(arms) == set(MODES), "missing paired mode")
        need(len({r["seed"] for r in arms.values()}) == 1,
             "paired seed mismatch")
    by_mode = {}
    for mode in MODES:
        arr = [r for r in rows if r["mode"] == mode]
        by_mode[mode] = dict(
            attempts=len(arr),
            solved=sum(r["status"] in ("SAT", "UNSAT") for r in arr),
            sat=sum(r["status"] == "SAT" for r in arr),
            unsat_crosschecked_no_LRAT=sum(r["status"] == "UNSAT" for r in arr),
            bounded_unknown=sum(r["status"] == "BUDGET" for r in arr),
            timeouts=sum(r["status"] == "TIMEOUT" for r in arr),
            par2_s=round(sum(r["par2_s"] for r in arr), 6),
            total_wall_s=round(sum(r["total_wall_s"] for r in arr), 6),
            total_prep_s=round(sum(r["preprocessing_s"] for r in arr), 6),
            gate_activated=sum(r["gate"]["applied"] for r in arr))
    per_source = []
    for c, _ in cases:
        arr = [r for r in rows if r["study_source_sha256"] == c["sha256"]]
        per_source.append(dict(
            gbd=c["gbd"], expected=expected_status(c),
            source_sha256=c["sha256"],
            by_mode={mode: dict(
                par2_s=round(sum(r["par2_s"] for r in arr if r["mode"] == mode), 6),
                wall_s=round(sum(r["total_wall_s"] for r in arr if r["mode"] == mode), 6),
                gate_reasons=[r["gate"]["reason"] for r in arr if r["mode"] == mode],
                solved=sum(r["status"] in ("SAT", "UNSAT") for r in arr
                           if r["mode"] == mode))
                for mode in MODES}))
    report = dict(protocol=PROTO, dataset=dataset,
                  exact_source_count=len(cases), measurements=len(rows),
                  expected_all_arms=MODES,
                  reference_MRE6f_run=42499854392,
                  same_original_SHA_and_seed_in_each_pair=True,
                  frozen_gate_before_results=True,
                  thresholds=dict(min_merges=MIN_MERGES,
                                  min_removed_clauses=MIN_CLAUSES_REMOVED,
                                  min_removed_fraction=MIN_REMOVED_FRACTION),
                  source_selection_not_new_blind_holdout=True,
                  full_wall_includes_prep_native_and_original_model_check=True,
                  no_independent_UNSAT_LRAT=True,
                  bounded_unknown_not_a_solver_verdict=True,
                  bounded_PAR2_not_a_solution_speed_ranking=(dataset == "bounded"),
                  promotion_allowed=False,
                  modes=by_mode, per_source=per_source)
    if dataset == "bounded":
        known = {c["gbd"][:8]: c["sha256"] for c, _ in cases}
        need(all(x in known for x in ref6f.CASE_LABELS),
             "MRE6f three control cases missing from seven-source comparison")
        for prefix in ("2fcd8533", "a45aefde", "de8c42d5"):
            gated = [r for r in rows
                     if r["official_gbd"].startswith(prefix)
                     and r["mode"] == "mre8f_gate"]
            need(len(gated) == REPS_BOUNDED * len(CONFLICT_CAPS),
                 "incomplete positive/control repetitions")
            expected_apply = prefix == "2fcd8533"
            need(all(r["gate"]["applied"] == expected_apply for r in gated),
                 "gate did not distinguish the original MRE6f positive/control")
    path = ROOT / dataset / "report.json"
    path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    line = "MRE8F_BOUNDED_FINAL" if dataset == "bounded" else "MRE8F_VERDICT_FINAL"
    print(line, json.dumps({k: v for k, v in report.items()
                            if k != "per_source"}, sort_keys=True), flush=True)


def selftest():
    d.all_eq.selftest()
    need(MODES == ("cms_native", "mre6f_all", "mre8f_gate"),
         "changed frozen arm list")
    # Certified large equality is selected; small/no equality abstains.
    with tempfile.TemporaryDirectory() as t:
        root = pathlib.Path(t)
        def test(n, with_pair):
            src = root / "selftest.cnf"
            clauses = []
            for i in range(2, n + 1):
                if with_pair:
                    clauses.extend([(-1, i), (1, -i)])
                clauses.append((1, i))
            clauses.extend([(1, 2)] * 300)
            mre1.write_cnf(src, n, clauses, [])
            return gate_prepare(src, root)[2]
        strong = test(260, True)
        need(strong["applied"] and strong["variables_eliminated"] >= 128,
             "profitable certified quotient skipped")
        weak = test(8, True)
        need(not weak["applied"], "unprofitable equality wrongly applied")
        none = test(260, False)
        need(not none["applied"], "no certificate must abstain")
    print("MRE8F_SELFTEST_PASS", PROTO, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "shard", "audit"))
    p.add_argument("--dataset", choices=("bounded", "verdict"), default="bounded")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--binary", default="mre6e/native")
    a = p.parse_args()
    if a.action == "selftest":
        selftest()
    elif a.action == "shard":
        shard(a.dataset, a.shard, a.binary)
    else:
        audit(a.dataset)
