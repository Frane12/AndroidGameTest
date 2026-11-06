#!/usr/bin/env python3
"""R166 independent source-CNF verifier for exact-XOR dispatcher certificates.

Does not import the fast-path detector or gaussian elimination implementation.
Every generated XOR row must be ENTailed by a COMPLETE original source CNF
parity block; every original clause must be covered by unit/row implications.
For UNSAT, independently replay XOR-row combination to obtain 0 = 1.
For SAT, independently validate each original CNF clause and model digest.
"""
import collections
import hashlib
import json
import pathlib
import sys

def fail(message):
    raise AssertionError("R166_INDEPENDENT_PROOF_FAIL " + str(message))

def read_dimacs(path):
    header = None
    clauses = []
    current = []
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("c", "%")):
            continue
        if line.startswith("p "):
            if header is not None or current:
                fail("duplicate/late header")
            fields = line.split()
            if len(fields) != 4 or fields[1] != "cnf":
                fail("invalid header")
            header = (int(fields[2]), int(fields[3]))
            continue
        if header is None:
            fail("clause before header")
        for token in line.split():
            literal = int(token)
            if literal == 0:
                clauses.append(tuple(current))
                current = []
            else:
                if not (0 < abs(literal) <= header[0]):
                    fail("out-of-range literal")
                current.append(literal)
    if header is None or current or len(clauses) != header[1]:
        fail("invalid clause count or unterminated clause")
    return header[0], clauses

def verify(source, proof):
    sha = hashlib.sha256(pathlib.Path(source).read_bytes()).hexdigest()
    if sha != proof["source_sha256"]:
        fail("CNF source SHA drift")
    variables, clauses = read_dimacs(source)
    if variables != proof["source_vars"] or len(clauses) != proof["source_clauses"]:
        fail("CNF metadata mismatch")
    indexed = collections.defaultdict(lambda: collections.defaultdict(set))
    for idx, clause in enumerate(clauses):
        if not 2 <= len(clause) <= 6:
            continue
        order = sorted(clause, key=abs)
        variables_in_clause = tuple(abs(lit) for lit in order)
        if len(set(variables_in_clause)) != len(order):
            continue
        assignment = sum((1 << j) for j, lit in enumerate(order) if lit < 0)
        indexed[variables_in_clause][assignment].add(idx)
    covered = set()
    rows = []
    for row in proof["rows"]:
        vs, rhs = row
        vs = tuple(vs)
        if rhs not in (0, 1) or not vs or len(vs) > 6:
            fail("invalid row")
        if len(vs) == 1:
            lit = vs[0] if rhs else -vs[0]
            matching = [i for i, clause in enumerate(clauses) if clause == (lit,)]
            if not matching:
                fail("unit not from original CNF")
            covered.update(matching)
        else:
            if len(set(vs)) != len(vs) or tuple(sorted(vs)) != vs:
                fail("row variable ordering malformed")
            patterns = indexed.get(vs, {})
            for mask in range(1 << len(vs)):
                if mask.bit_count() % 2 != (1 - rhs):
                    continue
                if not patterns.get(mask):
                    fail("row not implied by complete parity CNF source block")
                covered.update(patterns[mask])
        rows.append((vs, rhs))
    if len(covered) != len(clauses):
        fail("original CNF contains clauses not covered by exact rows")
    if proof["status"] == "SAT":
        positive = proof["model_true_vars"]
        positive = set(positive)
        if any(not 1 <= v <= variables for v in positive):
            fail("out of range SAT assignment")
        for clause in clauses:
            if not any(((lit > 0) == (abs(lit) in positive)) for lit in clause):
                fail("SAT assignment violates original CNF clause")
        model_bits = "".join("1" if i in positive else "0"
                             for i in range(1, variables + 1))
        if hashlib.sha256(model_bits.encode()).hexdigest() != proof["model_sha256"]:
            fail("SAT model digest mismatch")
    elif proof["status"] == "UNSAT":
        lhs, rhs = 0, 0
        ids = proof["conflict_row_ids"]
        if len(set(ids)) != len(ids):
            fail("duplicate parity certificate rows")
        for index in ids:
            if not 0 <= index < len(rows):
                fail("invalid contradiction row index")
            variables_in_row, bit = rows[index]
            for v in variables_in_row:
                lhs ^= 1 << (v - 1)
            rhs ^= bit
        if lhs != 0 or rhs != 1:
            fail("XOR contradiction 0=1 not proven")
    else:
        fail("non-proof status in exact path")
    return {"status":proof["status"], "clauses":len(clauses),
            "verified_rows":len(rows), "source_sha256":sha,
            "independent_exact_source_check":True,
            "certificate_replayed":True}

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("proof_json")
    args = ap.parse_args()
    proof = json.loads(pathlib.Path(args.proof_json).read_text())
    print("R166_INDEPENDENT_PROOF_PASS",
          json.dumps(verify(args.source, proof), sort_keys=True))
