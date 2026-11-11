"""Deterministic original-CNF MI-LTM1 probe benchmark.

This is a proof/diagnostic study, NOT a native CDCL speed benchmark.
A tiny exhaustive SAT oracle validates every derived relation on n<=10 vars.
"""
import itertools
import json
import random
import statistics
import time
from collections import defaultdict

try:
    from .probe import probe_cnf
except ImportError:
    from probe import probe_cnf


def xor_cnf(variables, rhs):
    return [tuple(-v if mask & (1 << i) else v for i, v in enumerate(variables))
            for mask in range(1 << len(variables))
            if mask.bit_count() % 2 != rhs]


def dimacs(clauses, n):
    return "p cnf %d %d\n" % (n, len(clauses)) + "".join(
        " ".join(map(str, clause)) + " 0\n" for clause in clauses)


def satisfies(clauses, assignment):
    return all(any(assignment[abs(lit)] == (lit > 0) for lit in clause)
               for clause in clauses)


def oracle(clauses, n):
    for bits in itertools.product((False, True), repeat=n):
        assignment = {v + 1: bits[v] for v in range(n)}
        if satisfies(clauses, assignment):
            yield assignment


def cases():
    rng = random.Random(11012026)
    for i in range(8):
        # XOR with overlapping 3-variable equations: relational opportunity
        a, b, c, d = rng.sample(range(1, 9), 4)
        rhs1, rhs2 = i % 2, (i // 2) % 2
        yield ("xor_overlap", i, 8,
               xor_cnf([a, b, c], rhs1) + xor_cnf([b, c, d], rhs2))
    for i in range(8):
        # Pure random 3-CNF with no assumed structural consequence.
        cls = []
        for _ in range(9):
            vs = rng.sample(range(1, 9), 3)
            cls.append(tuple(v if rng.randrange(2) else -v for v in vs))
        yield ("random_3sat", i, 8, cls)
    for i in range(8):
        # Incomplete XOR encoding; must never infer the missing equation.
        cls = xor_cnf([1, 2, 3], i % 2)
        del cls[i % len(cls)]
        yield ("incomplete_xor", i, 8, cls)
    for i in range(4):
        # Two logically inconsistent fully encoded equations.
        yield ("xor_unsat", i, 8,
               xor_cnf([1, 2, 3], 0) + xor_cnf([1, 2, 3], 1))
    for i in range(4):
        # Three XOR equations with inconsistent parity; detect a possible conflict.
        yield ("xor_cycle_unsat", i, 8,
               xor_cnf([1, 2], i % 2) + xor_cnf([2, 3], 0) +
               xor_cnf([1, 3], 1 - (i % 2)))


def consequence_holds(consequence, assignment):
    vs = consequence["variables"]
    rhs = consequence["rhs"]
    return sum(assignment[x] for x in vs) % 2 == rhs


def run(repetitions=3):
    results = []
    for family, case_id, n, clauses in cases():
        text = dimacs(clauses, n)
        models = list(oracle(clauses, n))
        reports = []
        for _ in range(repetitions):
            reports.append(probe_cnf(text))
        report = reports[0]
        assert all(r["xor_equations"] == report["xor_equations"] and
                   r["consequences"] == report["consequences"] for r in reports)
        for eq in report["xor_equations"]:
            assert all(consequence_holds(eq, assignment) for assignment in models)
        for derived in report["consequences"]:
            assert all(consequence_holds(derived, assignment) for assignment in models), (
                family, case_id, derived)
        if family == "incomplete_xor":
            assert not report["xor_equations"], (family, case_id)
        if family == "xor_unsat":
            assert not models
            assert any(d["kind"] == "conflict" for d in report["consequences"])
        results.append({
            "family": family, "id": case_id, "clauses": len(clauses),
            "models": len(models), "sat": bool(models),
            "xor_equations": len(report["xor_equations"]),
            "derived": len(report["consequences"]),
            "probe_median_ms": round(
                1000 * statistics.median(r["elapsed_s"] for r in reports), 4),
            "oracle_verified": True
        })
    summary = {}
    for family in sorted({x["family"] for x in results}):
        subset = [x for x in results if x["family"] == family]
        summary[family] = {
            "formulas": len(subset),
            "sat": sum(x["sat"] for x in subset),
            "unsat": sum(not x["sat"] for x in subset),
            "derived": sum(x["derived"] for x in subset),
            "median_probe_ms": round(statistics.median(
                x["probe_median_ms"] for x in subset), 4)
        }
    return {"study": "MI-LTM1 original-CNF diagnostic, exhaustive small-instance oracle",
            "repetitions": repetitions, "formulas": len(results),
            "summary": summary, "trials": results,
            "native_cdcl_e2e": False, "par2": None,
            "note": "Oracle validates consequences; this does not demonstrate speedup."}


if __name__ == "__main__":
    output = run()
    with open("mi_ltm1_benchmark.json", "w") as fh:
        json.dump(output, fh, indent=2, sort_keys=True)
    print("MI_LTM1_SUMMARY", json.dumps(output["summary"], sort_keys=True))
    print("MI_LTM1_FORMULAS", output["formulas"])
    print("MI_LTM1_ORACLE_VALIDATED", all(
        x["oracle_verified"] for x in output["trials"]))
