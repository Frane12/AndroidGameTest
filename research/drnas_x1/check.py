#!/usr/bin/env python3
"""Independent X1 checker: original-CNF SAT, scan-based DRUP, relational elimination.

This deliberately does not reuse the solver's watchers, heap, bitset tables or parser.
A checker timeout means UNVERIFIED, never UNSAT. No external SAT solver is called.
"""
from __future__ import annotations
import argparse
import itertools
import json
from pathlib import Path
import time


class Deadline:
    def __init__(self, seconds: float = 10.0):
        self.end = time.monotonic() + seconds
    def check(self):
        if time.monotonic() > self.end:
            raise TimeoutError("independent check budget exhausted")


def parse(path: Path) -> tuple[int, list[tuple[int, ...]]]:
    n = expected = None
    tokens: list[int] = []
    for line in path.read_text().splitlines():
        text = line.strip()
        if not text or text.startswith("c"):
            continue
        parts = text.split()
        if parts[0] == "p":
            if n is not None or tokens or len(parts) != 4 or parts[1] != "cnf":
                raise ValueError("bad DIMACS header")
            n, expected = map(int, parts[2:])
            if n < 0 or expected < 0:
                raise ValueError("negative DIMACS dimensions")
        else:
            if n is None:
                raise ValueError("missing DIMACS header")
            tokens.extend(map(int, parts))
    if n is None:
        raise ValueError("missing header")
    clauses, current = [], []
    for lit in tokens:
        if abs(lit) > n:
            raise ValueError("literal outside header")
        if lit:
            current.append(lit)
        else:
            clauses.append(tuple(current))
            current = []
    if current or len(clauses) != expected:
        raise ValueError("clause count/terminator mismatch")
    return n, clauses


def check_model(n: int, clauses: list[tuple[int, ...]], output: str) -> bool:
    values: dict[int, bool] = {}
    for line in output.splitlines():
        if line.startswith("v ") or line == "v":
            for item in line[1:].split():
                lit = int(item)
                if lit == 0:
                    continue
                v = abs(lit)
                if v > n or (v in values and values[v] != (lit > 0)):
                    return False
                values[v] = lit > 0
    return (len(values) == n and all(any(values.get(abs(l)) == (l > 0) for l in c) for c in clauses))


def normalized(clauses):
    out = []
    for c in clauses:
        s = set(c)
        if any(-l in s for l in s):
            continue
        out.append(tuple(sorted(s)))
    return out


def rup(database, proposed, deadline: Deadline) -> bool:
    """Unit-propagation contradiction under negation of a proposed clause."""
    assignment = {}
    for l in proposed:
        v, b = abs(l), l < 0
        if v in assignment and assignment[v] != b:
            return True  # Tautological proposed clause.
        assignment[v] = b
    changed = True
    while changed:
        deadline.check()
        changed = False
        for i, clause in enumerate(database):
            if not (i & 1023):
                deadline.check()
            satisfied, unset = False, []
            for l in clause:
                v = abs(l)
                if v not in assignment:
                    unset.append(l)
                elif assignment[v] == (l > 0):
                    satisfied = True
                    break
            if satisfied:
                continue
            if not unset:
                return True
            if len(unset) == 1:
                l = unset[0]
                assignment[abs(l)] = l > 0
                changed = True
    return False


def check_drup(n, clauses, lines, deadline):
    database = normalized(clauses)
    empty = False
    for line in lines:
        deadline.check()
        if not line.strip() or line.startswith("c"):
            continue
        if empty:
            return False
        items = list(map(int, line.split()))
        if not items or items[-1] != 0 or 0 in items[:-1] or any(abs(l) > n for l in items):
            return False
        proposed = tuple(sorted(set(items[:-1])))
        if not rup(database, proposed, deadline):
            return False
        database.append(proposed)
        empty = not proposed
    return empty


def check_factor(n, clauses, lines, deadline):
    # Representation is sets of boolean tuples, NOT solver-style integer bitsets.
    factors = []
    for clause in normalized(clauses):
        deadline.check()
        scope = tuple(sorted({abs(l) for l in clause}))
        if len(scope) > 16:
            return False
        pos = {v: j for j, v in enumerate(scope)}
        table = {bits for bits in itertools.product((False, True), repeat=len(scope))
                 if any(bits[pos[abs(l)]] == (l > 0) for l in clause)}
        factors.append((scope, table))
    eliminated, accepted = set(), False
    for line in lines:
        deadline.check()
        words = line.split()
        if not words or words[0] == "c":
            continue
        if accepted:
            return False
        if words == ["u"]:
            accepted = any(not table for _, table in factors)
            if not accepted:
                return False
        elif len(words) == 2 and words[0] == "e":
            var = int(words[1])
            if not 1 <= var <= n or var in eliminated:
                return False
            eliminated.add(var)
            bucket = [(s, t) for s, t in factors if var in s]
            if not bucket:
                return False
            union = tuple(sorted({v for s, _ in bucket for v in s}))
            if len(union) > 16:
                return False
            output_scope = tuple(v for v in union if v != var)
            mappings = [tuple(union.index(v) for v in s) for s, _ in bucket]
            output_positions = tuple(union.index(v) for v in output_scope)
            table = set()
            for i, bits in enumerate(itertools.product((False, True), repeat=len(union))):
                if not (i & 255):
                    deadline.check()
                if all(tuple(bits[k] for k in m) in t for (_, t), m in zip(bucket, mappings)):
                    table.add(tuple(bits[k] for k in output_positions))
            factors = [(s, t) for s, t in factors if var not in s]
            factors.append((output_scope, table))
        else:
            return False
    return accepted


def verify(cnf: Path, output: str, proof: Path | None, seconds: float = 10.0) -> dict:
    started = time.monotonic()
    deadline = Deadline(seconds)
    n, clauses = parse(cnf)
    deadline.check()
    statuses = [l for l in output.splitlines() if l.startswith("s ")]
    if statuses == ["s SATISFIABLE"]:
        ok, kind = check_model(n, clauses, output), "SAT_ORIGINAL_CNF"
    elif statuses == ["s UNSATISFIABLE"] and proof and proof.is_file():
        if proof.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("oversize proof")
        lines = proof.read_text().splitlines()
        factor = bool(lines and lines[0] == "c X1_FACTOR_V1")
        ok = (check_factor if factor else check_drup)(n, clauses, lines, deadline)
        kind = "UNSAT_FACTOR_REPLAY" if factor else "UNSAT_DRUP"
    else:
        ok, kind = False, "NO_CERTIFICATE"
    deadline.check()
    return {"verified": ok, "kind": kind, "check_s": time.monotonic() - started}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cnf", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--proof", type=Path)
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()
    try:
        result = verify(args.cnf, args.output.read_text(), args.proof, args.seconds)
    except (ValueError, OSError, TimeoutError) as e:
        result = {"verified": False, "kind": "CHECK_FAILED", "error": str(e)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
