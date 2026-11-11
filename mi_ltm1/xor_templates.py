"""Proof-preserving XOR relational templates for MI-LTM1.

Equations are (variable-set, rhs-bit), with XOR over GF(2).
This module derives consequences only from explicit source equations.
No cross-formula clauses or unverified learned deductions are imported.
"""
from collections import defaultdict

def normalize(variables, rhs=0):
    parity = set()
    for v in variables:
        v = int(v)
        if v <= 0:
            raise ValueError("XOR variable IDs must be positive")
        if v in parity:
            parity.remove(v)
        else:
            parity.add(v)
    return frozenset(parity), int(rhs) & 1

def eliminate_pair(first, second):
    """XOR two equations. The output follows algebraically from both."""
    av, ar = first
    bv, br = second
    return (av ^ bv, ar ^ br)

def derive_bounded(equations, *, max_rows=128, max_width=8):
    """Bounded pairwise inference. Includes provenance indices for audit.

    Empty row with rhs=1 is contradiction; unit row is forced assignment.
    Derived rows are consequences of source rows, not external memories.
    """
    rows = [(normalize(vars_, rhs), (i,)) for i, (vars_, rhs) in enumerate(equations)]
    if len(rows) > max_rows:
        rows = rows[:max_rows]
    known = {row for row, _ in rows}
    conclusions = []
    for row, origin in rows:
        vs, rhs = row
        if len(vs) <= 1:
            conclusions.append((row, origin))
    for i, (left, lo) in enumerate(rows):
        for right, ro in rows[i+1:]:
            out = eliminate_pair(left, right)
            if len(out[0]) > max_width or out in known:
                continue
            known.add(out)
            if len(out[0]) <= 2:
                conclusions.append((out, lo+ro))
    return conclusions

def classify_consequence(row):
    variables, rhs = row
    if not variables:
        return ("conflict" if rhs else "tautology", None)
    if len(variables) == 1:
        return ("unit", (next(iter(variables)), rhs))
    if len(variables) == 2:
        return ("binary_xor", (tuple(sorted(variables)), rhs))
    return ("other", None)

def pattern_key(eq1, eq2):
    """Renaming-invariant structural relation; never a proof by itself."""
    a, _ = normalize(*eq1)
    b, _ = normalize(*eq2)
    return (len(a), len(b), len(a & b), len(a ^ b))
