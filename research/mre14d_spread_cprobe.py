#!/usr/bin/env python3
"""DRNAS MRE14D: distributed C certificate probe, matched to MRE14C seeds.

Seven arms: CaDiCaL, Kissat, C only, D32 only, ungated CD32,
original MRE14C gate and spread-sampling MRE14D gate. All transform
changes independently replay certified. Signed seeds, original SHA
and binaries are frozen across arms; match seeds to MRE14C for
diagnostic replication. SAT witness checked on ORIGINAL CNF.
UNSAT is published reference agreement, NOT independent LRAT.
This is development research, NOT a blind holdout.
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

PROTO = "DRNAS-MRE14D-SPREAD-C2-D32-7ARM-12SHA-2SEED-30S-v1"
FROZEN_SEED_PROTO = "DRNAS-MRE14C-GATED-C2-D32-6ARM-12SHA-2SEED-30S-v1"
OUT = pathlib.Path("mre14d_out")
SRC = c15d.SRC
CAP, REPS, SHARDS = 30.0, 2, 6
ARMS = ("cadical", "kissat", "C_only", "D32_only", "CD32", "GATE_CD32", "GATE_SPREAD")
BINARY = {
    "cadical": pathlib.Path("c8c/bin/instrumented"),
    "kissat": pathlib.Path("built/bin/kissat_4_0_4"),
}
MAX_VARS, MAX_CLAUSES, MAX_BYTES = 30000, 125000, 16 * 1024 * 1024

def need(condition, message):
    if not condition:
        raise RuntimeError("MRE14D_FAIL_CLOSED: " + str(message))

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

def gate_probe(clauses, budget_s=0.035):
    """Bounded structural yield predictor, never a correctness oracle.

    C signal: candidate literal implied by another literal in a long clause.
    D signal: new binary resolvent on a two-edge implication path.
    The 512-clause and 4096-walk budgets can cause FALSE NEGATIVES.
    """
    begun = time.perf_counter()
    graph, _, binaries = m12.edge_graph(clauses)
    c_hit, d_hit = False, False
    long_seen, walks = 0, 0
    for clause in clauses:
        if len(clause) < 3:
            continue
        if long_seen >= 512 or time.perf_counter() - begun > budget_s * 0.55:
            break
        long_seen += 1
        literals = set(clause)
        for x in clause[:24]:
            for y in itertools.islice(graph.get(x, ()), 32):
                if y in literals and y != x and y != -x:
                    c_hit = True
                    break
                for z in itertools.islice(graph.get(y, ()), 32):
                    if z in literals and z != x and z != -x:
                        c_hit = True
                        break
                if c_hit:
                    break
            if c_hit:
                break
        if c_hit:
            break
    if time.perf_counter() - begun < budget_s:
        for a in sorted(graph, key=lambda z: (abs(z), z)):
            if walks >= 4096 or time.perf_counter() - begun > budget_s:
                break
            for b in itertools.islice(sorted(graph.get(a, ()), key=lambda z: (abs(z), z)), 32):
                if walks >= 4096 or time.perf_counter() - begun > budget_s:
                    break
                for c in itertools.islice(sorted(graph.get(b, ()), key=lambda z: (abs(z), z)), 32):
                    walks += 1
                    if a == c or a == -c or c in graph.get(a, ()):
                        continue
                    if frozenset((-a, c)) not in binaries:
                        d_hit = True
                        break
                    if walks >= 4096:
                        break
                if d_hit:
                    break
            if d_hit:
                break
    return dict(gate_c_hit=c_hit, gate_d_hit=d_hit,
                gate_long_examined=long_seen, gate_walks=walks,
                gate_s=round(time.perf_counter() - begun, 6))


def spread_gate_probe(clauses, budget_s=0.06):
    """Bounded, stratified C certificate search with a D novelty check.

    Look at first, center, final and evenly-spaced long clauses, up to
    2304 unique candidates; this is a predictor, not a complete solver
    and false negatives are counted against the full C/D treatment.
    """
    begun = time.perf_counter()
    graph, _, binaries = m12.edge_graph(clauses)
    long_ids = [idx for idx, clause in enumerate(clauses) if len(clause) >= 3]
    nlong = len(long_ids)
    slots = []
    slots.extend(range(min(384, nlong)))
    slots.extend(range(max(0, nlong // 2 - 384), min(nlong, nlong // 2 + 384)))
    slots.extend(range(max(0, nlong - 768), nlong))
    if nlong:
        slots.extend(min(nlong - 1, (i * nlong + nlong // 2) // 768)
                     for i in range(min(768, nlong)))
    c_hit, d_hit, sampled = False, False, 0
    visited = set()
    for rank in slots:
        if rank in visited:
            continue
        visited.add(rank)
        if time.perf_counter() - begun > budget_s * 0.83:
            break
        sampled += 1
        clause = clauses[long_ids[rank]]
        literal_set = set(clause)
        for x in clause[:24]:
            for y in itertools.islice(graph.get(x, ()), 32):
                if y != x and y != -x and y in literal_set:
                    c_hit = True
                    break
                for z in itertools.islice(graph.get(y, ()), 32):
                    if z != x and z != -x and z in literal_set:
                        c_hit = True
                        break
                if c_hit:
                    break
            if c_hit:
                break
        if c_hit:
            break
    walks = 0
    if time.perf_counter() - begun < budget_s:
        for a in sorted(graph, key=lambda v: (abs(v), v)):
            if walks >= 4096 or time.perf_counter() - begun > budget_s:
                break
            for b in itertools.islice(sorted(graph.get(a, ()), key=lambda v: (abs(v), v)), 32):
                if walks >= 4096 or time.perf_counter() - begun > budget_s:
                    break
                for c in itertools.islice(sorted(graph.get(b, ()), key=lambda v: (abs(v), v)), 32):
                    walks += 1
                    if a == c or a == -c or c in graph.get(a, ()):
                        continue
                    if frozenset((-a, c)) not in binaries:
                        d_hit = True
                        break
                    if walks >= 4096:
                        break
                if d_hit:
                    break
            if d_hit:
                break
    return dict(gate_c_hit=c_hit, gate_d_hit=d_hit,
                gate_long_examined=sampled, gate_long_population=nlong,
                gate_walks=walks, gate_s=round(time.perf_counter() - begun, 6),
                gate_policy="stratified_3regions_plus_uniform")


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
    if arm in ("GATE_CD32", "GATE_SPREAD"):
        info.update(gate_probe(clauses) if arm == "GATE_CD32"
                    else spread_gate_probe(clauses))
        if not (info["gate_c_hit"] or info["gate_d_hit"]):
            info["reason"] = "gate_skip_no_structural_yield"
            return None, info
    ops = {
        "C_only": ["C"], "D32_only": ["D32"],
        "CD32": ["C", "D32"],
        "GATE_CD32": (["C", "D32"] if info.get("gate_c_hit", False) else ["D32"]),
        "GATE_SPREAD": (["C", "D32"] if info.get("gate_c_hit", False) else ["D32"]),
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
    # Paired across seven arms AND MRE14C, different actual seeds across repetitions.
    raw = sha((FROZEN_SEED_PROTO + "|" + case["sha256"] + "|" + str(rep)).encode())
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
    with tempfile.TemporaryDirectory(prefix="mre14d-") as tmp:
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
    with tempfile.TemporaryDirectory(prefix="mre14d-smoke-") as tmp:
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
    print("MRE14D_SMOKE_PASS two frozen solvers and two numeric seeds", flush=True)

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
            for ops in (("C", "D32"), ("C",), ("D32",)):
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
    positive = gate_probe([(-1, 2), (-2, 3), (1, 2, 4)], budget_s=1.0)
    negative = gate_probe([(1, 2, 3), (-2, 3, 4)], budget_s=1.0)
    need(positive["gate_c_hit"] and positive["gate_d_hit"], "gate positive control")
    need(not negative["gate_c_hit"] and not negative["gate_d_hit"],
         "gate negative control")
    filler = [(10, 11, 12)] * 4000
    planted = [(-1, 2), (-2, 3)] + filler[:2000] + [(1, 3, 4)] + filler[2000:]
    near = gate_probe(planted, budget_s=0.5)
    spread = spread_gate_probe(planted, budget_s=1.0)
    need(not near["gate_c_hit"], "original near-only gate did not miss remote C")
    need(spread["gate_c_hit"], "spread gate missed planted center C")
    need(verify_c(planted, m13.clause_dominance(planted, 2, 192, 1.0)[0]) >= 1,
         "independent certified C control")
    print("MRE14D_SELFTEST_PASS " + json.dumps(dict(
        Boolean_assignments=checks, gate_positive_and_negative_controls=True,
        distributed_probe_detects_planted_remote_C=True,
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
                print("MRE14D_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == 28, "incomplete shard")
    print("MRE14D_SHARD_PASS " + str(index) + " 28", flush=True)

def audit():
    cases = originals()
    rows = []
    for i in range(SHARDS):
        part = json.loads((OUT / ("shard-" + str(i) + ".json")).read_text())
        need(len(part) == 28, "missing shard results " + str(i))
        rows.extend(part)
    expected = {(c["sha256"], rep, arm)
                for c in cases for rep in range(REPS) for arm in ARMS}
    keys = [(r["source_sha256"], r["rep"], r["arm"]) for r in rows]
    need(len(rows) == len(expected) == len(set(keys)) == 168
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
                prep_s=round(sum(r["prep_s"] for r in group), 6),
                gate_skips=sum(r["reason"] == "gate_skip_no_structural_yield" for r in group),
                gate_c_hits=sum(r.get("gate_c_hit", False) for r in group),
                gate_d_hits=sum(r.get("gate_d_hit", False) for r in group))
            for arm in ARMS
        }
    bypair = {(r["source_sha256"], r["rep"], r["arm"]): r for r in rows}
    misses = sum(
        bypair[(c["sha256"], rep, "GATE_CD32")]["reason"] == "gate_skip_no_structural_yield"
        and bypair[(c["sha256"], rep, "CD32")]["applied"]
        for c in cases for rep in range(REPS))
    def missed_c(arm):
        return sum(
            bypair[(c["sha256"], rep, "CD32")]["c_deleted"] > 0
            and not bypair[(c["sha256"], rep, arm)].get("gate_c_hit", False)
            and bypair[(c["sha256"], rep, arm)].get("reason") != "resource_guard"
            for c in cases for rep in range(REPS))
    def missed_d(arm):
        return sum(
            bypair[(c["sha256"], rep, "CD32")]["d_lemmas"] > 0
            and not bypair[(c["sha256"], rep, arm)].get("gate_d_hit", False)
            and bypair[(c["sha256"], rep, arm)].get("reason") != "resource_guard"
            for c in cases for rep in range(REPS))
    pairs = [
        dict(source_sha256=c["sha256"], rep=rep, gbd=c["gbd"],
             full_c_deleted=bypair[(c["sha256"], rep, "CD32")]["c_deleted"],
             full_d_lemmas=bypair[(c["sha256"], rep, "CD32")]["d_lemmas"],
             old_gate_c_hit=bypair[(c["sha256"], rep, "GATE_CD32")].get("gate_c_hit"),
             spread_gate_c_hit=bypair[(c["sha256"], rep, "GATE_SPREAD")].get("gate_c_hit"),
             old_gate_PAR2=bypair[(c["sha256"], rep, "GATE_CD32")]["PAR2_s"],
             spread_gate_PAR2=bypair[(c["sha256"], rep, "GATE_SPREAD")]["PAR2_s"],
             full_CD32_PAR2=bypair[(c["sha256"], rep, "CD32")]["PAR2_s"])
        for c in cases for rep in range(REPS)]
    result = dict(protocol=PROTO, trials=len(rows), original_sources=len(cases),
                  gate_false_negative_paired_count=misses,
                  gate_c_misses_old=missed_c("GATE_CD32"),
                  gate_c_misses_spread=missed_c("GATE_SPREAD"),
                  gate_d_misses_old=missed_d("GATE_CD32"),
                  gate_d_misses_spread=missed_d("GATE_SPREAD"),
                  paired_certificate_diagnostics=pairs,
                  gate_is_heuristic_not_correctness_oracle=True,
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
    print("MRE14D_FINAL " + json.dumps(result, sort_keys=True), flush=True)

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
        print("MRE14D_SOURCE_SHA_PASS 12", flush=True)
    elif args.action == "shard":
        shard(args.shard)
    else:
        audit()
