#!/usr/bin/env python3
"""DRNAS R81-C: fail-closed *exact* algebraic coverage on original DIMACS.

For a certified CNF consisting ONLY of full XOR parity encodings (width 2..6)
and unit clauses, solve all equations over GF(2) directly. SAT returns a
complete assignment, rechecked against every ORIGINAL clause. UNSAT returns an
independently checkable XOR-combination certificate made solely from original
full encodings and original unit clauses. Any noncovered clause, malformed
DIMACS or budget exceedance delegates to SHA-pinned unchanged Kissat. This is
not a general mixed-XOR solver and not a world-record claim.
"""
from __future__ import annotations
import collections
import hashlib
import json
import time
from pathlib import Path

import r28_exact_gf2_benchmark as r28

MAX_BYTES = 2_000_000
MAX_VARS = 6000
MAX_CLAUSES = 100000
MAX_WIDTH = 6

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def encode(vs, parity):
    """Full clauses that forbid assignments with XOR parity != parity."""
    for mask in range(1 << len(vs)):
        if (mask.bit_count() & 1) != parity:
            yield tuple(-v if (mask >> j) & 1 else v for j, v in enumerate(vs))

def _canonical(cl):
    return tuple(sorted(cl, key=lambda x: (abs(x), x < 0)))

def _support_sign(cl):
    ordered = _canonical(cl)
    vs = tuple(abs(x) for x in ordered)
    if len(set(vs)) != len(vs):
        return None
    return vs, sum(1 << i for i, x in enumerate(ordered) if x < 0)

def _mask(width, rhs):
    return sum(1 << mask for mask in range(1 << width)
               if (mask.bit_count() & 1) != rhs)

def extract(path, deadline):
    """Parse the original, fully account for every clause, certify each parity."""
    n, clauses = r28.load_clauses(path)
    if time.monotonic() >= deadline:
        return None, {"route": "scan_budget_fallback"}
    patterns = {}
    units = []
    for i, clause in enumerate(clauses):
        if (i & 4095) == 0 and time.monotonic() >= deadline:
            return None, {"route": "scan_budget_fallback"}
        if len(clause) == 1:
            lit = clause[0]
            units.append((abs(lit), int(lit > 0)))
        elif 2 <= len(clause) <= MAX_WIDTH:
            entry = _support_sign(clause)
            if entry is None:
                return None, {"route": "non_algebraic_fallback", "uncovered": 1}
            vs, sign = entry
            patterns[vs] = patterns.get(vs, 0) | (1 << sign)
        else:
            return None, {"route": "non_algebraic_fallback", "uncovered": 1}
    equations = []
    covered_masks = {}
    for vs, observed in sorted(patterns.items()):
        k = len(vs)
        covered = 0
        for rhs in (0, 1):
            complete = _mask(k, rhs)
            if observed & complete == complete:
                equations.append(dict(vs=list(vs), rhs=rhs, kind="xor"))
                covered |= complete
        covered_masks[vs] = covered
    unmatched = sum((patterns[vs] & ~covered).bit_count()
                    for vs, covered in covered_masks.items())
    if unmatched:
        return None, dict(route="non_algebraic_fallback", uncovered_masks=unmatched,
                          xor_equations=len(equations), units=len(units),
                          original_clauses=len(clauses))
    for v, value in sorted(set(units)):
        equations.append(dict(vs=[v], rhs=value, kind="unit"))
    return (n, clauses, equations), dict(
        route="certified_exact_xor_plus_units", variables=n,
        original_clauses=len(clauses), units=len(units),
        xor_equations=sum(x["kind"] == "xor" for x in equations),
        total_equations=len(equations), coverage_verified=True)

def verify_unsat_certificate(original, certificate):
    """Independent original-clause witness check; no trust in eliminator."""
    n, raw = r28.load_clauses(original)
    clauses = {_canonical(cl) for cl in raw}
    xor_varmask = 0
    rhs = 0
    if not isinstance(certificate, list) or not certificate:
        return False
    for row in certificate:
        vs, val, kind = row["vs"], row["rhs"], row["kind"]
        if (not vs or vs != sorted(set(vs)) or
            min(vs) < 1 or max(vs) > n or val not in (0,1)):
            return False
        if kind == "unit":
            if len(vs) != 1:
                return False
            v = vs[0] if val else -vs[0]
            if (v,) not in clauses:
                return False
        elif kind == "xor":
            if not 2 <= len(vs) <= MAX_WIDTH:
                return False
            for cl in encode(vs, val):
                if _canonical(cl) not in clauses:
                    return False
        else:
            return False
        for v in vs:
            xor_varmask ^= 1 << (v - 1)
        rhs ^= val
    return xor_varmask == 0 and rhs == 1

def verify_sat_model(original, model, n):
    """Check ALL original DIMACS clauses, not merely extracted XOR rows."""
    actual_n, clauses = r28.load_clauses(original)
    if actual_n != n:
        return False
    for clause in clauses:
        if not any(((model >> (abs(v)-1)) & 1) == int(v > 0) for v in clause):
            return False
    return True

def solve(path, case, max_budget_s=3.0):
    start = time.monotonic()
    size = Path(path).stat().st_size
    n = case.get("variables", 0)
    m = case.get("clauses", 0)
    if (not case.get("supported") or not case.get("complete_blocks")
        or n <= 0 or n > MAX_VARS or m <= 0 or m > MAX_CLAUSES
        or size > MAX_BYTES):
        return dict(route="guard_fallback", solved=False)
    deadline = start + max_budget_s
    try:
        result, info = extract(path, deadline)
    except (ValueError, AssertionError, UnicodeError, OSError):
        return dict(route="scan_error_fallback", solved=False)
    if result is None:
        return dict(solved=False, **info)
    source_n, clauses, eq = result
    if source_n != n or len(clauses) != m:
        return dict(route="metadata_mismatch_fallback", solved=False)
    basis = {}
    for i, row in enumerate(eq):
        if (i & 127) == 0 and time.monotonic() >= deadline:
            return dict(route="algebra_budget_fallback", solved=False)
        vector = sum(1 << (v - 1) for v in row["vs"])
        rhs = row["rhs"]
        ancestors = 1 << i
        while vector:
            pivot = vector.bit_length() - 1
            previous = basis.get(pivot)
            if previous is None:
                basis[pivot] = (vector, rhs, ancestors)
                break
            vector ^= previous[0]
            rhs ^= previous[1]
            ancestors ^= previous[2]
        if not vector and rhs:
            proof = [eq[j] for j in range(len(eq)) if (ancestors >> j) & 1]
            if not verify_unsat_certificate(path, proof):
                raise RuntimeError("R81C_INVALID_GF2_UNSAT_CERTIFICATE")
            return dict(route="gf2_unsat_certified", solved=True,
                        answer="UNSAT", proof=proof, proof_size=len(proof),
                        rank=len(basis), **info)
    # With highest-bit pivots, rows depend only on lower-index variables.
    # Free variables are zero. Ascending pivot back-substitution is exact.
    model = 0
    for pivot in sorted(basis):
        vector, rhs, _ = basis[pivot]
        other = vector ^ (1 << pivot)
        value = rhs ^ ((other & model).bit_count() & 1)
        if value:
            model |= 1 << pivot
    if time.monotonic() >= deadline:
        return dict(route="model_budget_fallback", solved=False)
    if not verify_sat_model(path, model, n):
        raise RuntimeError("R81C_GF2_MODEL_FAILED_ORIGINAL_CNF")
    # Check official known answer ONLY in benchmark; never infer from it.
    return dict(route="gf2_sat_model_verified", solved=True, answer="SAT",
                model=model, rank=len(basis), **info)

def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as folder:
        root = Path(folder)
        def run(name, cnf, expected):
            p = root / name
            p.write_text(cnf)
            n, clauses = r28.load_clauses(p)
            out = solve(p, dict(supported=True, complete_blocks=1,
                                variables=n, clauses=len(clauses)), 10)
            if expected is None:
                assert not out["solved"], out
            else:
                assert out["solved"] and out["answer"] == expected, out
                if expected == "UNSAT":
                    assert verify_unsat_certificate(p, out["proof"])
            return out
        def dimacs(n, equations, unit=None, other=None):
            clauses = [cl for vs, rhs in equations for cl in encode(vs, rhs)]
            if unit:
                clauses += [(v,) for v in unit]
            if other:
                clauses += other
            return f"p cnf {n} {len(clauses)}\n" + "".join(
                " ".join(map(str, c)) + " 0\n" for c in clauses)
        sat = run("sat.cnf", dimacs(4, [([1,2,3],0),([2,3,4],1)], [1]), "SAT")
        unsat = run("unsat.cnf", dimacs(4, [([1,2,3],0),([2,3,4],1)], [1,4]), "UNSAT")
        mixed = run("mixed.cnf", dimacs(4,[([1,2,3],0)],[1],[(2,4)]),None)
        partial = run("decoy.cnf", "p cnf 3 3\n1 2 3 0\n-1 -2 3 0\n-1 2 -3 0\n",None)
        print("R81C_EXACT_COVERAGE_SELFTEST_PASS",
              json.dumps(dict(sat_rank=sat["rank"],unsat_proof_size=unsat["proof_size"],
                              mixed=mixed["route"],decoy=partial["route"])),flush=True)

if __name__ == "__main__":
    selftest()
