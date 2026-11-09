#!/usr/bin/env python3
"""DRNAS MRE14B: isolate C-depth2 and D-32/96 synergy at 30 s E2E.

Eight paired policies: frozen CaDiCaL, Kissat 4.0.4, C alone, D32
alone, D96 alone, C->D32, C->D96 and D32->C.  Same source SHA
and actual solver seed within each (source, repetition) group.
Original SAT witnesses are always checked; UNSAT is reference agreement,
not independent LRAT.  All transformation and replay costs count in E2E.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import subprocess
import tempfile
import time

import mre12_exact_quotient as m12
import mre13_abcd_parallel as m13
import c15d_benchmark as c15d

PROTO = "DRNAS-MRE14B-C2-D32-D96-8ARM-12SHA-2SEED-30S-v1"
OUT = pathlib.Path("mre14b_out")
SRC = c15d.SRC
CAP, REPS, SHARDS = 30.0, 2, 6
ARMS = ("cadical", "kissat", "C_only", "D32_only", "D96_only",
        "CD32", "CD96", "DC32")
BINARY = {
    "cadical": pathlib.Path("c8c/bin/instrumented"),
    "kissat": pathlib.Path("built/bin/kissat_4_0_4"),
}
MAX_VARS, MAX_CLAUSES, MAX_BYTES = 30000, 125000, 16 * 1024 * 1024

def need(condition, message):
    if not condition:
        raise RuntimeError("MRE14B_FAIL_CLOSED: " + str(message))

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def digest(path):
    return m12.digest(path)

def originals():
    source = c15d.cases()
    need(len(source) == 12 and len({c["sha256"] for c in source}) == 12,
         "frozen originals changed")
    return source

def path_proven(graph, source, targets):
    """Independent bounded-search replay against graph built from certified clauses."""
    if source in targets:
        return True
    todo = collections.deque([source])
    seen = {source}
    while todo:
        here = todo.popleft()
        for nxt in graph.get(here, ()):
            if nxt in targets:
                return True
            if nxt not in seen:
                seen.add(nxt)
                need(len(seen) <= 250000, "implication replay budget exceeded")
                todo.append(nxt)
    return False

def verify_c(before, after):
    """Every deleted literal must imply a retained disjunct via binary clauses."""
    need(len(before) == len(after), "C clause count changed")
    graph, _, original_binary = m12.edge_graph(before)
    deleted = 0
    for old, new in zip(before, after):
        if old == new:
            continue
        need(len(new) >= 1 and len(new) < len(old), "C invalid shortening")
        need(collections.Counter(new) <= collections.Counter(old),
             "C introduced a literal")
        targets = set(new)
        for lit in set(old) - targets:
            need(path_proven(graph, lit, targets),
                 "C deleted literal without implication proof")
            deleted += 1
    return deleted

def verify_d(before, after):
    """Each added binary follows from two binary implications in current input."""
    need(len(after) >= len(before) and after[:len(before)] == before,
         "D changed existing clauses")
    graph, _, source_binary = m12.edge_graph(before)
    tail = after[len(before):]
    for a, b in tail:
        need(a != -b and a != b and
             any(b in graph.get(mid, ()) for mid in graph.get(-a, ())),
             "D added binary without a two-edge original proof")
        need(frozenset((a, b)) not in source_binary,
             "D did not add a novel binary")
    return len(tail)

def transform(case, arm):
    original_path = SRC / case["filename"]
    info = dict(applied=False, c_deleted=0, d_lemmas=0,
                input_clauses=case["nclauses"], output_clauses=case["nclauses"],
                reason="baseline", certificate_replayed=True)
    if arm in ("cadical", "kissat"):
        return None, info
    if (case["nvars"] > MAX_VARS or case["nclauses"] > MAX_CLAUSES or
            case["bytes"] > MAX_BYTES):
        info["reason"] = "resource_guard"
        return None, info
    n, original = m12.parse_dimacs(original_path)
    need(n == case["nvars"] and len(original) == case["nclauses"],
         "DIMACS metadata drift")
    clauses = list(original)
    ops = {
        "C_only": ["C"], "D32_only": ["D32"], "D96_only": ["D96"],
        "CD32": ["C", "D32"], "CD96": ["C", "D96"],
        "DC32": ["D32", "C"],
    }[arm]
    for operation in ops:
        prev = clauses
        if operation == "C":
            clauses, removed, _ = m13.clause_dominance(
                prev, depth=2, limit=192, seconds=0.13)
            need(verify_c(prev, clauses) == removed,
                 "C proof replay/count discrepancy")
            info["c_deleted"] += removed
        else:
            dose = int(operation[1:])
            clauses, added = m13.binary_lemmas(prev, dose, seconds=0.10)
            need(verify_d(prev, clauses) == added,
                 "D proof replay/count discrepancy")
            info["d_lemmas"] += added
    info["output_clauses"] = len(clauses)
    info["applied"] = bool(info["c_deleted"] or info["d_lemmas"])
    info["reason"] = "proof_replayed" if info["applied"] else "no_useful_certificates"
    return ((n, clauses) if info["applied"] else None), info

def seed_for(case, rep):
    # Paired across all 8 arms, different actual seeds across repetitions.
    raw = sha((PROTO + "|" + case["sha256"] + "|" + str(rep)).encode())
    return 1 + int(raw[:8], 16) % 900000

def binary_for(arm):
    return BINARY["kissat" if arm == "kissat" else "cadical"]

def run_one(case, arm, rep, position, seed):
    original = SRC / case["filename"]
    need(digest(original) == case["sha256"], "original source SHA changed")
    bin_path = binary_for(arm)
    need(bin_path.is_file(), "pinned solver binary missing")
    started = time.perf_counter()
    status, verified = "TIMEOUT", False
    with tempfile.TemporaryDirectory(prefix="mre14b-") as tmp:
        reduced, metrics = transform(case, arm)
        target = original
        if reduced is not None:
            n, clauses = reduced
            target = pathlib.Path(tmp) / "transformed.cnf"
            target.write_text(m12.encode(n, clauses), encoding="utf-8")
        prep = time.perf_counter() - started
        remaining = CAP - prep
        if remaining > 0.10:
            env = {k: v for k, v in os.environ.items() if not
                   k.startswith(("DRNAS_C8", "DRNAS_C14", "DRNAS_C15"))}
            cmd = [str(bin_path.resolve()), "--seed=" + str(seed),
                   str(target.resolve())]
            try:
                p = subprocess.run(cmd, env=env, capture_output=True, text=True,
                                   errors="replace", timeout=remaining)
                need(p.returncode in (10, 20),
                     "solver exit " + str(p.returncode) + ": " + p.stderr[-300:])
                status, model = c15d.h.ref.external_parse(p)
                need(status == case["status"],
                     "contradiction with frozen published SAT/UNSAT status")
                if status == "SAT":
                    c15d.h.cms.verify_model(original, model)
                    verified = True
                if time.perf_counter() - started >= CAP:
                    status, verified = "TIMEOUT", False
            except subprocess.TimeoutExpired:
                status = "TIMEOUT"
        elapsed = time.perf_counter() - started
    if elapsed >= CAP:
        status, verified = "TIMEOUT", False
    return dict(protocol=PROTO, source_sha256=case["sha256"], gbd=case["gbd"],
                cohort=case["cohort"], reference=case["status"], arm=arm,
                rep=rep, position=position, paired_solver_seed=seed,
                solver_seed_actually_passed=True, independent_UNSAT_LRAT=False,
                SAT_original_verified=verified,
                original_CNF_unchanged=True, cap_s=CAP,
                PAR2_s=round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
                elapsed_s=round(elapsed, 6), prep_s=round(prep, 6),
                status=status, backend_sha256=digest(bin_path), **metrics)

def smoke():
    for name, path in BINARY.items():
        need(path.is_file(), "missing " + name)
    with tempfile.TemporaryDirectory(prefix="mre14b-smoke-") as tmp:
        path = pathlib.Path(tmp) / "smoke.cnf"
        path.write_text("p cnf 2 2\n1 2 0\n-1 2 0\n")
        for name, binary in BINARY.items():
            for seed in (107, 613):
                p = subprocess.run([str(binary.resolve()), "--seed=" + str(seed),
                                    str(path.resolve())], capture_output=True,
                                   text=True, timeout=8)
                need(p.returncode == 10,
                     "solver seed unsupported by " + name + ": " + p.stderr[-300:])
                status, model = c15d.h.ref.external_parse(p)
                need(status == "SAT", "SAT smoke parse failed " + name)
                c15d.h.cms.verify_model(path, model)
    print("MRE14B_SMOKE_PASS two frozen solvers and two numeric seeds", flush=True)

def selftest():
    m13.selftest()
    rng = random.Random(2026110914)
    checks = 0
    for n in range(2, 6):
        pool = []
        for mask in range(1, 1 << n):
            for sign in range(1 << n):
                pool.append(tuple((v + 1) * (1 if sign & (1 << v) else -1)
                                  for v in range(n) if mask & (1 << v)))
        for _ in range(100):
            original = [rng.choice(pool) for _ in range(rng.randrange(1, 15))]
            for ops in (("C", "D32"), ("C", "D96"), ("D32", "C"),
                        ("C",), ("D32",), ("D96",)):
                clauses = original
                for op in ops:
                    prev = clauses
                    if op == "C":
                        clauses, removed, _ = m13.clause_dominance(prev, 2, 192, 1)
                        need(verify_c(prev, clauses) == removed, "selftest C proof")
                    else:
                        clauses, added = m13.binary_lemmas(prev, int(op[1:]), 1)
                        need(verify_d(prev, clauses) == added, "selftest D proof")
                for bits in range(1 << n):
                    model = {v: bool(bits & (1 << (v - 1))) for v in range(1, n + 1)}
                    need(m12.model_satisfies(original, model) ==
                         m12.model_satisfies(clauses, model),
                         "selftest exact Boolean equivalence failed")
                    checks += 1
    print("MRE14B_SELFTEST_PASS " + json.dumps(dict(
        Boolean_assignments=checks, includes_all_6_transformation_orders=True,
        original_truth_table_equivalence=True)), flush=True)

def shard(index):
    need(0 <= index < SHARDS, "bad shard")
    cases = originals()[index::SHARDS]
    need(len(cases) == 2, "source partition no longer frozen")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        for rep in range(REPS):
            seed = seed_for(case, rep)
            arms = list(ARMS)
            random.Random(seed).shuffle(arms)
            for position, arm in enumerate(arms):
                row = run_one(case, arm, rep, position, seed)
                rows.append(row)
                (OUT / ("shard-" + str(index) + ".json")).write_text(
                    json.dumps(rows, sort_keys=True) + "\n")
                print("MRE14B_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == 32, "incomplete shard")
    print("MRE14B_SHARD_PASS " + str(index) + " 32", flush=True)

def audit():
    cases = originals()
    rows = []
    for i in range(SHARDS):
        part = json.loads((OUT / ("shard-" + str(i) + ".json")).read_text())
        need(len(part) == 32, "missing shard results " + str(i))
        rows.extend(part)
    expected = {(c["sha256"], rep, arm)
                for c in cases for rep in range(REPS) for arm in ARMS}
    keys = [(r["source_sha256"], r["rep"], r["arm"]) for r in rows]
    need(len(rows) == len(expected) == len(set(keys)) == 192
         and set(keys) == expected, "incomplete paired set")
    bysha = {c["sha256"]: c for c in cases}
    for row in rows:
        case = bysha[row["source_sha256"]]
        need(row["protocol"] == PROTO and row["cohort"] == case["cohort"]
             and row["reference"] == case["status"] and
             row["original_CNF_unchanged"] and row["cap_s"] == CAP and
             row["solver_seed_actually_passed"], "audit provenance mismatch")
        need(row["paired_solver_seed"] == seed_for(case, row["rep"]),
             "unpaired numeric seed")
        need(row["backend_sha256"] == digest(binary_for(row["arm"])),
             "binary SHA drift")
        need(row["status"] in ("SAT", "UNSAT", "TIMEOUT"), "bad status")
        if row["status"] == "TIMEOUT":
            need(row["PAR2_s"] == 60, "timeout penalty error")
        else:
            need(row["status"] == case["status"] and
                 (row["status"] != "SAT" or row["SAT_original_verified"]),
                 "SAT witness/UNSAT reference failure")
        if row["applied"]:
            need(row["certificate_replayed"] and
                 (row["c_deleted"] > 0 or row["d_lemmas"] > 0),
                 "applied uncertified transformation")
    need(all(seed_for(case, 0) != seed_for(case, 1) for case in cases),
         "identical numerical seeds within source")
    def summary(values):
        return {
            arm: dict(
                attempts=len(group := [r for r in values if r["arm"] == arm]),
                solved=sum(r["status"] != "TIMEOUT" for r in group),
                SAT=sum(r["status"] == "SAT" for r in group),
                UNSAT_reference_only=sum(r["status"] == "UNSAT" for r in group),
                PAR2_s=round(sum(r["PAR2_s"] for r in group), 6),
                applied=sum(r["applied"] for r in group),
                c_deleted=sum(r["c_deleted"] for r in group),
                d_lemmas=sum(r["d_lemmas"] for r in group),
                prep_s=round(sum(r["prep_s"] for r in group), 6))
            for arm in ARMS
        }
    result = dict(protocol=PROTO, trials=len(rows), original_sources=len(cases),
                  repetitions=REPS, paired_numeric_solver_seeds=True,
                  globally_blind=False, independent_UNSAT_LRAT=False,
                  official_prospective_previously_used=True,
                  cap_s=CAP, scores=summary(rows),
                  by_cohort={c: summary([r for r in rows if r["cohort"] == c])
                             for c in sorted({r["cohort"] for r in rows})},
                  by_source={case["gbd"]: summary(
                      [r for r in rows if r["source_sha256"] == case["sha256"]])
                             for case in cases})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("MRE14B_FINAL " + json.dumps(result, sort_keys=True), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("selftest", "smoke", "verify", "shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    if args.action == "selftest":
        selftest()
    elif args.action == "smoke":
        smoke()
    elif args.action == "verify":
        originals()
        print("MRE14B_SOURCE_SHA_PASS 12", flush=True)
    elif args.action == "shard":
        shard(args.shard)
    else:
        audit()
