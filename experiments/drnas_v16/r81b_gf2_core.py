#!/usr/bin/env python3
"""R81-B first native CDCL GF(2)-lemma experiment.

Only complete, independently identified parity encodings can supply equations.
A bounded GF(2) closure builds proof-traceable implied short XOR rows.
Their CNF explanations are ADDED BEFORE solve; native Kissat propagates and
learns from them at all decision levels.  Gaussian elimination itself is NOT
yet incrementally called in Kissat's inner loop.  This is an essential,
scientifically honest first R81-B implementation, not a full live GF(2) plugin.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import tempfile
import time
from pathlib import Path

import r28_exact_gf2_benchmark as r28
import r64_mixed_xor_implied as r64

MAX_INPUT_ROWS = 128
MAX_COMBINATIONS = 4500
MAX_DERIVED_CLAUSES = 96
MAX_WIDTH = 4

def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()

def _row_add(a, b):
    return (a[0] ^ b[0], a[1] ^ b[1], a[2] ^ b[2])

def _evidence(row, equations):
    support, rhs, ancestors = row
    parity = 0
    check_support = frozenset()
    for i in range(len(equations)):
        if (ancestors >> i) & 1:
            vs, b = equations[i]
            check_support = check_support ^ frozenset(vs)
            parity ^= b
    if (check_support, parity) != (support, rhs):
        raise RuntimeError("R81B_UNSOUND_GF2_ROW")
    return [i for i in range(len(equations)) if (ancestors >> i) & 1]

def _clauses(support, rhs):
    names = sorted(support)
    for mask in range(1 << len(names)):
        if mask.bit_count() % 2 != rhs:
            yield tuple(-v if (mask >> j) & 1 else v for j, v in enumerate(names))

def derive(original, case, budget_s=2.0):
    """Return sound derived CNF clauses plus independently auditable evidence.

    If any scanning or algebra budget is exceeded, fall back to unchanged
    original CNF. The charged preprocessing time is measured by the caller.
    """
    t0 = time.monotonic()
    if not case.get("supported") or not case.get("complete_blocks"):
        return [], dict(route="no_certified_xor", original_equations=0,
                        derived_rows=0, added_clauses=0, proof_sha256=None)
    if case.get("variables", 0) <= 0 or case.get("clauses", 0) <= 0:
        return [], dict(route="invalid_metadata_fallback", original_equations=0,
                        derived_rows=0, added_clauses=0, proof_sha256=None)
    try:
        original_eq, _ = r64.extract_equations(
            original, case["variables"], case["clauses"], t0)
    except TimeoutError:
        return [], dict(route="scan_timeout_fallback", original_equations=0,
                        derived_rows=0, added_clauses=0, proof_sha256=None)
    if time.monotonic() - t0 >= budget_s:
        return [], dict(route="scan_cost_fallback", original_equations=len(original_eq),
                        derived_rows=0, added_clauses=0, proof_sha256=None)
    # Every row below has a support and an exact parity certified by its
    # full 2^(width-1) original CNF sign-mask family.
    original_eq = sorted(set((tuple(vs), rhs) for vs, rhs in original_eq),
                         key=lambda item: (item[0], item[1]))
    if len(original_eq) > MAX_INPUT_ROWS:
        # Deterministic SHA ranking; restricting premises cannot invalidate
        # any GF(2) implication, it can only make the procedure weaker.
        original_eq = sorted(original_eq,
                             key=lambda item: _digest(repr(item)))[:MAX_INPUT_ROWS]
        original_eq.sort()
    if not original_eq:
        return [], dict(route="no_complete_equations", original_equations=0,
                        derived_rows=0, added_clauses=0, proof_sha256=None)
    originals = [(frozenset(vs), bit, 1 << i)
                 for i, (vs, bit) in enumerate(original_eq)]
    basis = {}
    for row in originals:
        if time.monotonic() - t0 >= budget_s:
            return [], dict(route="algebra_budget_fallback",
                            original_equations=len(original_eq),
                            derived_rows=0, added_clauses=0, proof_sha256=None)
        reduced = row
        while reduced[0]:
            pivot = min(reduced[0])
            if pivot not in basis:
                basis[pivot] = reduced
                break
            reduced = _row_add(reduced, basis[pivot])
        if not reduced[0] and reduced[1]:
            # Certified XOR inconsistency, but do not independently answer
            # UNSAT here. Let pinned Kissat check original and report status.
            return [], dict(route="gf2_contradiction_delegate",
                            original_equations=len(original_eq),
                            derived_rows=0, added_clauses=0, proof_sha256=None)
    candidates = {}
    def consider(row):
        support, rhs, _ = row
        if not 1 <= len(support) <= MAX_WIDTH:
            return
        key = (tuple(sorted(support)), rhs)
        if key not in candidates or row[2].bit_count() < candidates[key][2].bit_count():
            candidates[key] = row
    for r in originals:
        consider(r)
    reduced_rows = list(basis.values())
    # Gaussian row reduction, preserving XOR-of-originals derivations.
    for pivot in sorted(basis, reverse=True):
        r = basis[pivot]
        for p in sorted(basis):
            if p < pivot and pivot in basis[p][0]:
                basis[p] = _row_add(basis[p], r)
    reduced_rows += list(basis.values())
    for r in reduced_rows:
        consider(r)
    unique = {}
    for r in originals + reduced_rows:
        key = (tuple(sorted(r[0])), r[1])
        unique.setdefault(key, r)
    pool = sorted(unique.values(), key=lambda r: (len(r[0]), tuple(sorted(r[0])), r[1]))[:96]
    work = 0
    for a, b in itertools.combinations(pool, 2):
        if work >= MAX_COMBINATIONS or time.monotonic()-t0 >= budget_s:
            break
        work += 1
        consider(_row_add(a, b))
    # Check candidate provenance against ORIGINAL certified equations.
    # Shorter rows are more useful for Boolean propagation.
    ranked = sorted(candidates.values(),
                    key=lambda r: (len(r[0]), r[2].bit_count(),
                                   tuple(sorted(r[0])), r[1]))
    if time.monotonic()-t0 >= budget_s:
        return [], dict(route="algebra_budget_fallback",
                        original_equations=len(original_eq),
                        derived_rows=0, added_clauses=0, proof_sha256=None)
    # Normalize full DIMACS original to avoid duplicate clauses.
    _, cnf = r28.load_clauses(original)
    existing = {tuple(sorted(cl)) for cl in cnf if 1 <= len(cl) <= MAX_WIDTH}
    added = []
    evidence = []
    for row in ranked:
        if time.monotonic()-t0 >= budget_s:
            return [], dict(route="proof_budget_fallback",
                            original_equations=len(original_eq),
                            derived_rows=0, added_clauses=0, proof_sha256=None)
        derived = [cl for cl in _clauses(row[0], row[1])
                   if tuple(sorted(cl)) not in existing]
        if not derived:
            continue
        if len(added) + len(derived) > MAX_DERIVED_CLAUSES:
            continue  # Never encode only part of an XOR relationship.
        sources = _evidence(row, original_eq)
        for cl in derived:
            normalized = tuple(sorted(cl))
            existing.add(normalized)
            added.append(cl)
        evidence.append(dict(variables=sorted(row[0]), parity=row[1],
                             equation_sources=sources, clauses=len(derived)))
        if len(added) == MAX_DERIVED_CLAUSES:
            break
    payload = json.dumps(dict(equations=original_eq, evidence=evidence),
                         sort_keys=True, separators=(",", ":"))
    return added, dict(route="certified_native_cdcl_lemmas" if added else "no_new_short_rows",
                        original_equations=len(original_eq),
                        derived_rows=len(evidence), added_clauses=len(added),
                        pair_combinations=work, proof_sha256=_digest(payload),
                        proof_evidence=evidence)

def _make_cnf(n, eqs):
    clauses = []
    for vs, rhs in eqs:
        clauses += list(_clauses(vs, rhs))
    return "p cnf %d %d\n" % (n, len(clauses)) + "".join(
        " ".join(map(str, cl)) + " 0\n" for cl in clauses)

def selftest():
    # x1 xor x2 xor x3=0 and x2 xor x3 xor x4=1 entail x1 xor x4=1.
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)/"xor.cnf"
        p.write_text(_make_cnf(4, [((1,2,3),0), ((2,3,4),1)]))
        result, meta = derive(p, dict(supported=True, complete_blocks=2,
                                      variables=4, clauses=8), budget_s=15.0)
        if not result or meta["derived_rows"] < 1:
            raise RuntimeError("R81B_TEST_MISSING_DERIVED_BINARY")
        _, old = r28.load_clauses(p)
        for mask in range(1 << 4):
            def sat(cl):
                return any(bool(mask & (1 << (abs(lit)-1))) == (lit > 0) for lit in cl)
            if all(sat(cl) for cl in old) and not all(sat(cl) for cl in result):
                raise RuntimeError("R81B_TEST_UNSOUND_LEMMA")
        if not any(set(map(abs, cl)) == {1,4} for cl in result):
            raise RuntimeError("R81B_TEST_MISSING_CROSS_EQUATION_IMPLICATION")
        # A misleading incomplete XOR family must not yield false constraints.
        q = Path(tmp)/"decoy.cnf"
        q.write_text("p cnf 3 3\n1 2 3 0\n-1 -2 3 0\n-1 2 -3 0\n")
        fake, info = derive(q, dict(supported=True, complete_blocks=1,
                                   variables=3, clauses=3), budget_s=15.0)
        if fake:
            raise RuntimeError("R81B_TEST_INCOMPLETE_XOR_UNSAFE")
        print("R81B_CERTIFIED_LEMMAS_SELFTEST_PASS", json.dumps(
            dict(derived_binary=len(result), proof_sha256=meta["proof_sha256"],
                 decoy_route=info["route"])), flush=True)

if __name__ == "__main__":
    selftest()
