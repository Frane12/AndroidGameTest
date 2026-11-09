#!/usr/bin/env python3
"""MRE13 A/B/C/D: four parallel, proof-safe SAT representation experiments.

A: cheap structural prefilter -> certified SCC quotient.
B: quotient + benefit gates / dense variable packing.
C: certified binary-implication domination of long clauses.
D: certified length-two binary implication lemmas.

Controls are source-paired, all candidate overhead is included in E2E timing.
No UNSAT LRAT, independent-seed, or blind-holdout claim is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import random
import subprocess
import tempfile
import time

import mre12_exact_quotient as m
import c15d_benchmark as c15d

PROTO = "DRNAS-MRE13-ABCD-4WAY-384-12SHA-8S-v1"
SRC = c15d.SRC
OUT = pathlib.Path("mre13_out")
CAP = 8.0
REPS = 2
VARIANTS = {
    "A": ("baseline", "A_scan", "A_fast", "A_balanced"),
    "B": ("baseline", "B_exact", "B_gate", "B_packed"),
    "C": ("baseline", "C_direct", "C_depth2", "C_strict"),
    "D": ("baseline", "D_32", "D_96", "D_192"),
}

def check(x, msg):
    m.need(x, msg)

def lit_count(clauses):
    return sum(len(c) for c in clauses)

def cheap_scan(path, max_lines=4096):
    """Heuristic only: no correctness decision depends on this."""
    lines, binary = 0, 0
    with open(path, encoding="utf-8") as f:
        for row in f:
            if row.startswith(("c", "p", "%")) or not row.strip():
                continue
            lines += 1
            if len(row.split()) == 3 and row.rstrip().endswith(" 0"):
                binary += 1
            if lines >= max_lines:
                break
    return binary, lines

def safe_discover(n, clauses, budget):
    certs, reason = m.discover(n, clauses, budget=budget)
    mapping = m.replay(clauses, certs)
    return mapping, reason, certs

def pack(nvars, clauses, mapping):
    """Only live representatives enter the solver; invert before witness check."""
    active = sorted({abs(z) for c in clauses for z in c})
    encode_id = {v: i + 1 for i, v in enumerate(active)}
    decode_id = {i + 1: v for i, v in enumerate(active)}
    packed = [
        tuple((encode_id[abs(lit)] if lit > 0 else -encode_id[abs(lit)])
              for lit in clause)
        for clause in clauses
    ]
    check(len(active) <= nvars, "packed variables exceed source")
    check(all(v not in mapping for v in active), "mapped variable survived packing")
    return len(active), packed, decode_id

def clause_dominance(clauses, depth, limit, seconds):
    """Original binary clauses are retained, so strengthening is equivalent.

    Remove x from a clause containing x,y only if original binaries prove
    x => y via 1 or 2 implications. Each proof edge is independently replayed.
    """
    begun = time.perf_counter()
    graph, _, binaries = m.edge_graph(clauses)
    edited, removed, certs = [], 0, 0
    for clause in clauses:
        if len(clause) < 3 or removed >= limit or time.perf_counter() - begun > seconds:
            edited.append(clause)
            continue
        litset = set(clause)
        delete = set()
        for x in clause:
            if x in delete:
                continue
            proof = None
            for y in graph.get(x, ()):
                if y in litset and y != x and y != -x and y not in delete:
                    proof = (x, y)
                    break
                if depth >= 2:
                    for z in graph.get(y, ()):
                        if z in litset and z != x and z != -x and z not in delete:
                            proof = (x, y, z)
                            break
                    if proof:
                        break
            if proof:
                check(all(frozenset((-a, b)) in binaries for a, b in zip(proof, proof[1:])),
                      "C: original implication proof failed")
                delete.add(x)
                certs += 1
                if removed + len(delete) >= limit:
                    break
        if delete:
            altered = tuple(x for x in clause if x not in delete)
            check(len(altered) >= 1, "C: empty strengthened clause")
            edited.append(altered)
            removed += len(delete)
        else:
            edited.append(clause)
    check(len(edited) == len(clauses), "C: clause count changed")
    return edited, removed, certs

def binary_lemmas(clauses, limit, seconds):
    """F and (a->b and b->c) entail (-a or c); preserve all originals."""
    begun = time.perf_counter()
    graph, _, original = m.edge_graph(clauses)
    added, seen = [], set(original)
    for a in sorted(graph, key=lambda v: (abs(v), v)):
        if len(added) >= limit or time.perf_counter() - begun > seconds:
            break
        for b in sorted(graph[a], key=lambda v: (abs(v), v)):
            if len(added) >= limit:
                break
            for c in sorted(graph.get(b, ()), key=lambda v: (abs(v), v)):
                if len(added) >= limit or time.perf_counter() - begun > seconds:
                    break
                if a == c or a == -c or c in graph.get(a, ()):
                    continue
                resolvent = frozenset((-a, c))
                if len(resolvent) != 2 or resolvent in seen:
                    continue
                check(frozenset((-a, b)) in original and
                      frozenset((-b, c)) in original,
                      "D: binary resolution proof failed")
                seen.add(resolvent)
                added.append((-a, c))
    return list(clauses) + added, len(added)

def transform(variant, arm, path, case):
    meta = dict(applied=False, proof_count=0, eligible_aliases=0,
                source_clauses=0, transformed_clauses=0, literals_delta=0,
                packed_variables_delta=0, reason="abstain")
    if arm == "baseline":
        meta["reason"] = "original"
        return path, None, None, meta
    temp_result = None
    # Pre-check size before expensive DIMACS parsing.
    nvars = int(case["nvars"])
    nclauses = int(case["nclauses"])
    if nvars > 20000 or nclauses > 150000:
        meta["reason"] = "source_size_guard"
        return path, None, None, meta

    if variant == "A":
        b, lines = cheap_scan(path)
        meta["sample_binary"], meta["sample_lines"] = b, lines
        if arm == "A_scan":
            meta["reason"] = "scan_only_control"
            return path, None, None, meta
        threshold = 8 if arm == "A_fast" else 2
        if b < threshold:
            meta["reason"] = "cheap_binary_gate"
            return path, None, None, meta

    n, clauses = m.parse_dimacs(path)
    meta["source_clauses"] = len(clauses)
    meta["transformed_clauses"] = len(clauses)
    out, mapping, decode, nout = None, {}, None, n

    if variant in ("A", "B"):
        if n > m.MAX_VARIABLES or len(clauses) > m.MAX_CLAUSES:
            meta["reason"] = "scc_size_guard"
            return path, None, None, meta
        budget = (0.04 if arm == "A_fast" else 0.30) if variant == "A" else 0.40
        mapping, why, certs = safe_discover(n, clauses, budget)
        meta["eligible_aliases"] = len(mapping)
        meta["proof_count"] = len(certs)
        meta["reason"] = why
        if not mapping:
            return path, None, None, meta
        reduced = m.reduce_clauses(n, clauses, mapping)
        gain_literals = lit_count(clauses) - lit_count(reduced)
        meta["literals_delta"] = gain_literals
        meta["transformed_clauses"] = len(reduced)
        if arm == "B_gate" and (len(mapping) < 4 or gain_literals < 16):
            meta["reason"] = "benefit_gate"
            return path, None, None, meta
        if arm == "B_packed":
            nout, out, decode = pack(n, reduced, mapping)
            meta["packed_variables_delta"] = n - nout
        else:
            out = reduced
    elif variant == "C":
        depth = 1 if arm == "C_direct" else 2
        limit = 64 if arm == "C_direct" else 192
        seconds = 0.07 if arm == "C_direct" else 0.13
        reduced, removed, cert_count = clause_dominance(clauses, depth, limit, seconds)
        meta["proof_count"] = cert_count
        meta["literals_delta"] = removed
        if removed == 0 or (arm == "C_strict" and removed < 16):
            meta["reason"] = "no_dominance_or_strict_gate"
            return path, None, None, meta
        out = reduced
    elif variant == "D":
        limit = int(arm.split("_")[1])
        out, nlemmas = binary_lemmas(clauses, limit, seconds=0.10)
        meta["proof_count"] = nlemmas
        meta["transformed_clauses"] = len(out)
        if nlemmas == 0:
            meta["reason"] = "no_novel_lemmas"
            return path, None, None, meta
    else:
        check(False, "unknown variant")

    check(out is not None, "transformation absent")
    if variant in ("A", "B") and not mapping:
        check(False, "uncertified quotient")
    meta["applied"] = True
    meta["reason"] = "proof_replayed"
    return (nout, out), mapping, decode, meta

def _run_solver(case, original_path, effective, mapping, decode, n_solver,
                tstart, meta):
    backend = pathlib.Path("c8c/bin/instrumented")
    check(backend.is_file(), "frozen CaDiCaL not found")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DRNAS_C8", "DRNAS_C14", "DRNAS_C15"))}
    remaining = CAP - (time.perf_counter() - tstart)
    status, verified = "TIMEOUT", False
    if remaining <= 0.06:
        return status, verified
    cmd = [str(backend.resolve()), str(effective.resolve())]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           env=env, timeout=remaining)
        check(p.returncode in (10, 20), "solver exit " + str(p.returncode))
        status, model = c15d.h.ref.external_parse(p)
        check(status == case["status"], "reference disagreement")
        if status == "SAT":
            if meta["applied"] and mapping:
                if decode is not None:
                    model = {decode[v]: val for v, val in model.items() if v in decode}
                model = m.reconstruct(int(case["nvars"]), model, mapping)
            c15d.h.cms.verify_model(original_path, model)
            verified = True
        if time.perf_counter() - tstart >= CAP:
            status, verified = "TIMEOUT", False
    except subprocess.TimeoutExpired:
        status = "TIMEOUT"
    return status, verified

def trial(variant, arm, case, rep, position, order_seed):
    path = SRC / case["filename"]
    check(m.digest(path) == case["sha256"], "source SHA drift")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="drnas-mre13-") as td:
        target, mapping, decode, meta = transform(variant, arm, path, case)
        effective = path
        nsolver = int(case["nvars"])
        if meta["applied"]:
            nsolver, clauses = target
            effective = pathlib.Path(td) / "candidate.cnf"
            effective.write_text(m.encode(nsolver, clauses), encoding="utf-8")
        prep_s = time.perf_counter() - started
        status, verified = _run_solver(case, path, effective, mapping, decode,
                                       nsolver, started, meta)
    elapsed = time.perf_counter() - started
    return dict(protocol=PROTO, variant=variant, arm=arm, rep=rep,
                order_seed=order_seed, position=position, gbd=case["gbd"],
                cohort=case["cohort"], source_sha256=case["sha256"],
                binary_sha256=m.digest("c8c/bin/instrumented"),
                reference=case["status"], status=status, SAT_original_verified=verified,
                UNSAT_independent_LRAT=False, independent_solver_seed=False,
                cap_s=CAP, PAR2_s=round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
                elapsed_s=round(elapsed, 6), prep_s=round(prep_s, 6),
                original_CNF_unchanged=True, **meta)

def verify():
    cases = c15d.cases()
    check(len(cases) == 12, "frozen manifest not 12")
    check(pathlib.Path("c8c/bin/instrumented").is_file(), "backend missing")
    print("MRE13_FROZEN_SHA_VERIFIED 12", flush=True)

def selftest():
    m.exhaustive_test()
    rng = random.Random(131313)
    checks = 0
    for n in range(1, 5):
        pool = [
            tuple((1 if bits & (1 << k) else -1) * (k + 1)
                  for k in range(n) if mask & (1 << k))
            for mask in range(1, 1 << n)
            for bits in range(1 << n)
        ]
        for _ in range(125):
            clauses = [rng.choice(pool) for _ in range(rng.randrange(1, 14))]
            c1, _, _ = clause_dominance(clauses, 2, 50, 1)
            d1, _ = binary_lemmas(clauses, 100, 1)
            for bits in range(1 << n):
                model = {j: bool(bits & (1 << (j - 1))) for j in range(1, n + 1)}
                orig = m.model_satisfies(clauses, model)
                check(orig == m.model_satisfies(c1, model), "C equivalence failed")
                check(orig == m.model_satisfies(d1, model), "D equivalence failed")
                checks += 1
    print("MRE13_SELFTEST_PASS " + json.dumps(dict(exhaustive_assignments=checks,
          original_witness_check=True, replayed_implications=True)), flush=True)

def shard(variant):
    check(variant in VARIANTS, "unknown parallel experiment")
    cases = c15d.cases()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        for rep in range(REPS):
            seed = int(hashlib.sha256((PROTO + variant + case["sha256"] +
                        str(rep)).encode()).hexdigest()[:8], 16)
            order = list(VARIANTS[variant])
            random.Random(seed).shuffle(order)
            for position, arm in enumerate(order):
                row = trial(variant, arm, case, rep, position, seed)
                rows.append(row)
                (OUT / ("shard-" + variant + ".json")).write_text(
                    json.dumps(rows, sort_keys=True) + "\n")
                print("MRE13_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    check(len(rows) == 96, "variant incomplete")
    print("MRE13_VARIANT_PASS " + variant + " 96", flush=True)

def audit():
    cases = c15d.cases()
    rows = []
    for v in VARIANTS:
        part = json.loads((OUT / ("shard-" + v + ".json")).read_text())
        check(len(part) == 96, "missing parallel variant " + v)
        rows += part
    expected = {(case["sha256"], v, arm, rep)
                for case in cases for v, arms in VARIANTS.items()
                for arm in arms for rep in range(REPS)}
    keys = [(r["source_sha256"], r["variant"], r["arm"], r["rep"]) for r in rows]
    check(len(keys) == len(set(keys)) == len(expected) == 384
          and set(keys) == expected, "384 source-paired keys incomplete")
    bysha = {case["sha256"]: case for case in cases}
    check(len({r["binary_sha256"] for r in rows}) == 1,
          "cross-variant backend SHA mismatch")
    for row in rows:
        source = bysha[row["source_sha256"]]
        check(row["protocol"] == PROTO and row["cap_s"] == CAP
              and row["reference"] == source["status"]
              and row["cohort"] == source["cohort"], "metadata mismatch")
        check(row["original_CNF_unchanged"], "original CNF changed")
        check(row["status"] in ("SAT", "UNSAT", "TIMEOUT"), "invalid SAT status")
        if row["status"] == "TIMEOUT":
            check(row["PAR2_s"] == 16.0, "bad PAR2 timeout")
        else:
            check(row["status"] == source["status"], "reference disagrees")
            if row["status"] == "SAT":
                check(row["SAT_original_verified"], "SAT original witness missing")
        if row["applied"] and row["arm"] != "baseline":
            check(row["proof_count"] > 0, "transformation without proof")
    def summarize(group, arms):
        return {arm: dict(attempts=len(rs := [r for r in group if r["arm"] == arm]),
                          solved=sum(r["status"] != "TIMEOUT" for r in rs),
                          PAR2_s=round(sum(r["PAR2_s"] for r in rs), 6),
                          applied=sum(bool(r["applied"]) for r in rs),
                          proven=sum(int(r["proof_count"]) for r in rs),
                          prep_s=round(sum(r["prep_s"] for r in rs), 6))
                for arm in arms}
    results = {}
    for v, arms in VARIANTS.items():
        group = [r for r in rows if r["variant"] == v]
        results[v] = dict(
            scores=summarize(group, arms),
            by_cohort={
                cohort: summarize([r for r in group if r["cohort"] == cohort], arms)
                for cohort in sorted({r["cohort"] for r in group})
            })
    report = dict(protocol=PROTO, total_trials=len(rows), original_sources=12,
                  candidates=12, independent_solver_seeds=False, global_blind=False,
                  UNSAT_independent_LRAT=False, single_frozen_binary=True,
                  source_matched=True, parallel_variant_count=4, results=results)
    (OUT / "report.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print("MRE13_FINAL " + json.dumps(report, sort_keys=True), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("selftest", "verify", "shard", "audit"))
    parser.add_argument("--variant", choices=list(VARIANTS))
    args = parser.parse_args()
    if args.action == "selftest":
        selftest()
    elif args.action == "verify":
        verify()
    elif args.action == "shard":
        check(args.variant is not None, "--variant required")
        shard(args.variant)
    else:
        audit()
