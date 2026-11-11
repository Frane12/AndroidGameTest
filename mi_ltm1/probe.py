"""MI-LTM1 safe, bounded original-CNF XOR probe.

A complete CNF encoding of an XOR equation is required before it is used.
No heuristically guessed XOR is ever asserted as a logical fact.
Output is an advisory diagnostic for later CDCL integration.
"""
import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

try:
    from .xor_templates import derive_bounded, classify_consequence, pattern_key
    from .memory import signature
except ImportError:
    from xor_templates import derive_bounded, classify_consequence, pattern_key
    from memory import signature


def parse_dimacs(text):
    clauses, pending = [], []
    declared = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("c") or line.startswith("%"):
            continue
        if line.startswith("p"):
            fields = line.split()
            if len(fields) != 4 or fields[1] != "cnf":
                raise ValueError("Invalid DIMACS header")
            declared = (int(fields[2]), int(fields[3]))
            continue
        for token in line.split():
            lit = int(token)
            if lit:
                pending.append(lit)
            else:
                clauses.append(tuple(pending))
                pending = []
    if pending:
        raise ValueError("Unterminated DIMACS clause")
    if declared is None:
        raise ValueError("Missing DIMACS header")
    if len(clauses) != declared[1] or any(abs(x) > declared[0] for c in clauses for x in c):
        raise ValueError("DIMACS header does not match clauses")
    return clauses


def detect_xor(clauses, max_width=3, max_groups=20000):
    """Recognize full exact XOR CNF encodings of width 2 or 3.

    For variables V, all 2^(|V|-1) forbidden assignments for a
    particular parity must have their corresponding clause present.
    Extra clauses do not invalidate the logical consequence.
    """
    masks = defaultdict(set)
    for idx, clause in enumerate(clauses):
        variables = tuple(sorted(set(abs(v) for v in clause)))
        if not 2 <= len(variables) <= max_width or len(variables) != len(clause):
            continue
        if len(masks) >= max_groups and variables not in masks:
            continue
        literals = {abs(v): v for v in clause}
        # Assignment that falsifies clause: positive literal -> 0,
        # negative literal -> 1.
        mask = sum((1 << i) for i, v in enumerate(variables) if literals[v] < 0)
        masks[variables].add(mask)
    found = []
    for variables, observed in masks.items():
        n = len(variables)
        for rhs in (0, 1):
            required = {m for m in range(1 << n) if m.bit_count() % 2 != rhs}
            if required.issubset(observed):
                found.append((variables, rhs))
    return found


def probe_cnf(text, *, max_clauses=200000, max_rows=128, max_width=3):
    start = time.perf_counter()
    clauses = parse_dimacs(text)
    if len(clauses) > max_clauses:
        return {"status":"abstain","reason":"clause_budget","clauses":len(clauses),
                "elapsed_s":time.perf_counter()-start}
    eqs = detect_xor(clauses, max_width=max_width)
    conclusions = derive_bounded(eqs, max_rows=max_rows)
    results = []
    for row, source in conclusions:
        kind, payload = classify_consequence(row)
        if kind not in ("unit","binary_xor","conflict"):
            continue
        results.append({"kind":kind,"variables":sorted(row[0]),"rhs":row[1],
                        "source_equations":list(source)})
    return {"status":"diagnostic_only", "clauses":len(clauses),
            "formula_sha256":hashlib.sha256(text.encode()).hexdigest(),
            "coarse_signature":signature(clauses),
            "xor_equations":[{"variables":list(v),"rhs":rhs} for v,rhs in eqs],
            "consequences":results,
            "elapsed_s":time.perf_counter()-start,
            "warning":"No derived clauses injected. Consequences require independent proof audit before active CDCL use."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cnf", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = probe_cnf(args.cnf.read_text())
    payload = json.dumps(report,sort_keys=True,indent=2)
    if args.out:
        args.out.write_text(payload+"\n")
    else:
        print(payload)


if __name__ == "__main__":
    main()
