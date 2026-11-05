#!/usr/bin/env python3
"""R133b experimental live CNF<->GF(2) DPLL bridge.
NOT Kissat integration; exact exhaustive differential correctness gate.
Every XOR reason is checked as an implication of its source equation.
"""
import itertools, json, random, time

def clause_sat(clause, assignment):
    return any(assignment[abs(l)] == (l > 0) for l in clause)

def xor_sat(eq, assignment):
    vars_, rhs = eq
    return (sum(assignment[v] for v in vars_) & 1) == rhs

def brute(n, clauses, eqs):
    for bits in itertools.product((False, True), repeat=n):
        a = {i + 1: bits[i] for i in range(n)}
        if all(clause_sat(c, a) for c in clauses) and all(xor_sat(e, a) for e in eqs):
            return a
    return None

def solve(n, clauses, eqs, bridge=True):
    metrics = dict(nodes=0, xor_units=0, xor_conflicts=0, cnf_units=0, backtracks=0, reason_checks=0)
    def reason_valid(eq, reason):
        # Check XOR entails emitted clause for all its variables, independent of search assignment.
        vs = eq[0]
        for bits in itertools.product((False, True), repeat=len(vs)):
            a = dict(zip(vs, bits))
            if xor_sat(eq, a) and not clause_sat(reason, a):
                return False
        return True
    def propagate(a):
        while True:
            changed = False
            for clause in clauses:
                if any((abs(l) in a and a[abs(l)] == (l > 0)) for l in clause):
                    continue
                unassigned = [l for l in clause if abs(l) not in a]
                if not unassigned:
                    return False
                if len(unassigned) == 1:
                    lit = unassigned[0]
                    a[abs(lit)] = lit > 0
                    metrics["cnf_units"] += 1
                    changed = True
            if bridge:
                for eq in eqs:
                    vs, rhs = eq
                    missing = [v for v in vs if v not in a]
                    parity = sum(a[v] for v in vs if v in a) & 1
                    if len(missing) <= 1:
                        reason = [(-v if a[v] else v) for v in vs if v in a]
                        if missing:
                            v = missing[0]
                            value = bool(parity ^ rhs)
                            reason.append(v if value else -v)
                        assert reason_valid(eq, reason), ("invalid XOR reason", eq, reason)
                        metrics["reason_checks"] += 1
                        if not missing:
                            if parity != rhs:
                                metrics["xor_conflicts"] += 1
                                return False
                        else:
                            a[v] = value
                            metrics["xor_units"] += 1
                            changed = True
            if not changed:
                return True
    def search(a):
        metrics["nodes"] += 1
        a = dict(a)
        if not propagate(a):
            return None
        if len(a) == n:
            return a if all(xor_sat(eq, a) for eq in eqs) else None
        v = next(i for i in range(1, n + 1) if i not in a)
        for val in (False, True):
            b = dict(a)
            b[v] = val
            result = search(b)
            if result is not None:
                return result
            metrics["backtracks"] += 1
        return None
    # Baseline represents XORs as exact CNF truth-table clauses, so no GF(2) propagation.
    if not bridge:
        expanded = list(clauses)
        for vs, rhs in eqs:
            for bits in itertools.product((False, True), repeat=len(vs)):
                if (sum(bits) & 1) != rhs:
                    expanded.append(tuple(-v if bit else v for v, bit in zip(vs, bits)))
        return solve(n, expanded, [], True)
    return search({}), metrics

def main():
    rng = random.Random(133)
    counts = dict(cases=0, sat=0, unsat=0, xor_units=0, xor_conflicts=0, reason_checks=0, baseline_nodes=0, bridge_nodes=0)
    start = time.perf_counter()
    for n in range(3, 8):
        for case in range(100):
            clauses = []
            for _ in range(rng.randrange(0, 9)):
                vs = rng.sample(range(1, n + 1), rng.randrange(1, min(3, n) + 1))
                clauses.append(tuple(v if rng.randrange(2) else -v for v in vs))
            eqs = []
            for _ in range(rng.randrange(1, 6)):
                vs = tuple(sorted(rng.sample(range(1, n + 1), rng.randrange(2, min(5, n) + 1))))
                eqs.append((vs, rng.randrange(2)))
            expected = brute(n, clauses, eqs)
            actual, met = solve(n, clauses, eqs)
            baseline, bm = solve(n, clauses, eqs, False)
            assert (actual is None) == (expected is None) == (baseline is None), (n, case)
            if actual is not None:
                assert all(clause_sat(c, actual) for c in clauses)
                assert all(xor_sat(e, actual) for e in eqs)
            counts["cases"] += 1
            counts["sat" if expected else "unsat"] += 1
            for key in ("xor_units", "xor_conflicts", "reason_checks"):
                counts[key] += met[key]
            counts["baseline_nodes"] += bm["nodes"]
            counts["bridge_nodes"] += met["nodes"]
    counts["elapsed_s"] = round(time.perf_counter() - start, 4)
    counts["scope"] = "toy DPLL exact differential; NOT native Kissat, NOT performance benchmark"
    print("R133B_DIFFERENTIAL_PASS", json.dumps(counts, sort_keys=True))

if __name__ == "__main__":
    main()
