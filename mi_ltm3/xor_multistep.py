"""MI-LTM3 proof-carrying, bounded multi-step XOR relational closure.

Every exported equation is an XOR combination of explicit, source-CNF-certified
XOR equations. The source indices are a parity vector, not merely a list of
previously derived rules. Names of variables are never reused across formulas.
"""
import time


def normalized_row(variables, rhs, provenance):
    variables_set = set()
    for v in variables:
        v = int(v)
        if v <= 0:
            raise ValueError("XOR variable IDs must be positive")
        if v in variables_set:
            variables_set.remove(v)
        else:
            variables_set.add(v)
    return variables_set, int(rhs) & 1, set(provenance)


def xor_rows(left, right):
    a, ar, ap = left
    b, br, bp = right
    return a ^ b, ar ^ br, ap ^ bp


def closure(source_equations, *, max_rows=96, max_steps=25000,
            max_output=96, budget_s=0.01):
    """Derive unit/binary/empty rows by bounded GF(2) elimination + RREF.

    No guess is passed into the logical engine. All returned consequences
    have exact source indices; empty odd-parity row is an UNSAT certificate
    over certified source XORs. Inconclusive budgets are safe to abstain from.
    """
    t0 = time.perf_counter()
    basis = {}
    results = {}
    operations = 0
    truncated = len(source_equations) > max_rows
    deadline = t0 + budget_s

    def record(row):
        variables, rhs, provenance = row
        if len(variables) > 2:
            return
        if not variables and not rhs:
            return
        if not provenance:
            raise AssertionError("Nontrivial XOR inference without source")
        key = (tuple(sorted(variables)), int(rhs))
        if key not in results and len(results) < max_output:
            kind = ("conflict" if not variables else
                    "unit" if len(variables) == 1 else "binary_xor")
            results[key] = {
                "kind": kind, "variables": list(key[0]), "rhs": rhs,
                "source_equations": sorted(provenance)
            }

    for i, equation in enumerate(source_equations[:max_rows]):
        if time.perf_counter() >= deadline or operations >= max_steps:
            truncated = True
            break
        row = normalized_row(equation["variables"], equation["rhs"], {i})
        while row[0]:
            if time.perf_counter() >= deadline or operations >= max_steps:
                truncated = True
                break
            pivot = min(row[0])
            if pivot not in basis:
                basis[pivot] = row
                break
            row = xor_rows(row, basis[pivot])
            operations += 1
        if truncated:
            break
        record(row)
        if not row[0] and row[1]:
            # Contradiction is sufficient; extra elimination has no value.
            break

    if not truncated:
        # With smallest-variable pivots, high pivots occur in low-pivot rows.
        # Descending RREF clears those high variables without changing proof.
        pivots = sorted(basis, reverse=True)
        for pivot in pivots:
            for lower in pivots:
                if lower >= pivot:
                    continue
                if time.perf_counter() >= deadline or operations >= max_steps:
                    truncated = True
                    break
                if pivot in basis[lower][0]:
                    basis[lower] = xor_rows(basis[lower], basis[pivot])
                    operations += 1
                    record(basis[lower])
            if truncated:
                break

    for row in basis.values():
        record(row)

    return {
        "consequences": list(results.values()),
        "source_rows": min(len(source_equations), max_rows),
        "elimination_ops": operations,
        "truncated": truncated,
        "elapsed_s": time.perf_counter() - t0,
    }


def audit_provenance(source_equations, consequence):
    """Independent combinatorial check of a derived GF(2) row."""
    parity = 0
    variables = set()
    origin = consequence["source_equations"]
    if not origin or len(origin) != len(set(origin)):
        return False
    for index in origin:
        if not isinstance(index, int) or not 0 <= index < len(source_equations):
            return False
        row = source_equations[index]
        parity ^= row["rhs"]
        for v in row["variables"]:
            if v in variables:
                variables.remove(v)
            else:
                variables.add(v)
    return (sorted(variables) == consequence["variables"] and
            parity == consequence["rhs"])
