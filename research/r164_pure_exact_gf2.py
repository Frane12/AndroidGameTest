#!/usr/bin/env python3
"""R164 certified full-XOR CNF fast path (no unsound guessed parity).

A SAT/UNSAT answer is returned only if EVERY original CNF clause is either
a source unit or belongs to an exhaustive, source-complete parity truth-table
block of width 2..6. Otherwise return NOT_PURE (CDCL must handle the source).
No extraction max_rows, residual-frequency filtering, or 32-row selector.
UNSAT has a replay-checked linear XOR combination certificate over EXACT
CNF-equivalent source equations (not an LRAT/FRAT proof).
"""
import argparse
import collections
import hashlib
import json
import pathlib
import tempfile
import time

def need(ok, message):
    if not ok:
        raise ValueError("R164_CERT_FAIL: " + message)

def parse_dimacs(path):
    header = None
    clauses = []
    cur = []
    for line in pathlib.Path(path).read_text().splitlines():
        s = line.strip()
        if not s or s.startswith(("c", "%")):
            continue
        if s.startswith("p "):
            need(header is None and not cur, "duplicate/late p header")
            fields = s.split()
            need(len(fields) == 4 and fields[1] == "cnf", "bad DIMACS header")
            header = (int(fields[2]), int(fields[3]))
            continue
        need(header is not None, "clause before header")
        for tok in s.split():
            lit = int(tok)
            if lit:
                need(0 < abs(lit) <= header[0], "variable outside declared range")
                cur.append(lit)
            else:
                clauses.append(tuple(cur))
                cur = []
    need(header is not None and not cur, "missing header or unterminated clause")
    need(len(clauses) == header[1], "declared clause count mismatch")
    return header[0], clauses

def detect_exact(clauses):
    groups = collections.defaultdict(lambda: collections.defaultdict(list))
    covered = set()
    rows = []
    for idx, clause in enumerate(clauses):
        if len(clause) == 1:
            v = clause[0]
            rows.append(((abs(v),), int(v > 0)))
            covered.add(idx)
        if not 2 <= len(clause) <= 6:
            continue
        sorted_lits = sorted(clause, key=abs)
        vars_ = tuple(abs(v) for v in sorted_lits)
        if len(set(vars_)) != len(vars_):
            continue
        mask = sum(1 << k for k, v in enumerate(sorted_lits) if v < 0)
        groups[vars_][mask].append(idx)
    for vars_, masks in groups.items():
        count = 1 << len(vars_)
        for parity in (0, 1):
            forbidden = [mask for mask in range(count) if mask.bit_count() % 2 == parity]
            if all(mask in masks for mask in forbidden):
                rows.append((vars_, 1 - parity))
                for mask in forbidden:
                    covered.update(masks[mask])
    return (len(covered) == len(clauses)), rows, len(covered)

def verify_sat(clauses, model):
    for clause in clauses:
        if not any(bool((model >> (abs(lit) - 1)) & 1) == (lit > 0) for lit in clause):
            return False
    return True

def gaussian(rows):
    pivots = {}
    for idx, (vars_, rhs) in enumerate(rows):
        mask = sum(1 << (v-1) for v in vars_)
        bit = rhs
        combination = 1 << idx
        while mask:
            leading = (mask & -mask).bit_length()-1
            if leading not in pivots:
                pivots[leading] = (mask, bit, combination)
                break
            pivot_mask, pivot_rhs, pivot_comb = pivots[leading]
            mask ^= pivot_mask
            bit ^= pivot_rhs
            combination ^= pivot_comb
        else:
            if bit:
                # Independently reconstruct linear contradiction 0 = 1.
                lhs, parity = 0, 0
                involved = []
                for j, (vs, rhs0) in enumerate(rows):
                    if (combination >> j) & 1:
                        involved.append(j)
                        lhs ^= sum(1 << (v-1) for v in vs)
                        parity ^= rhs0
                need(lhs == 0 and parity == 1, "invalid UNSAT parity certificate")
                return dict(status="UNSAT", model=None, rank=len(pivots),
                            conflict_row_ids=involved)
    model = 0
    for p, (mask, rhs, _comb) in sorted(pivots.items(), reverse=True):
        remaining = mask & ~(1 << p)
        if rhs ^ ((remaining & model).bit_count() & 1):
            model |= 1 << p
    for vars_, rhs in rows:
        need((sum((model >> (v-1)) & 1 for v in vars_) & 1) == rhs,
             "Gaussian solution does not satisfy XOR rows")
    return dict(status="SAT", model=model, rank=len(pivots), conflict_row_ids=[])

def solve(path):
    start = time.perf_counter()
    n, clauses = parse_dimacs(path)
    exact, rows, covered = detect_exact(clauses)
    base = dict(source_sha256=hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest(),
                variables=n, clauses=len(clauses), xor_rows=len(rows),
                covered_clauses=covered, pure_exact=exact)
    if not exact:
        return dict(**base, status="NOT_PURE",
                    elapsed_s=time.perf_counter()-start,
                    proof="NO_FAST_PATH_MIXED_OR_UNSUPPORTED", rank=0,
                    model_sha256=None, certificate_rows=0)
    answer = gaussian(rows)
    if answer["status"] == "SAT":
        need(verify_sat(clauses, answer["model"]), "SAT witness invalid against original CNF")
        model_bytes = "".join("1" if (answer["model"] >> i) & 1 else "0" for i in range(n))
        digest = hashlib.sha256(model_bytes.encode()).hexdigest()
        proof = "EXACT_CNFEQUIV_GAUSS_SAT_MODEL_CHECKED"
    else:
        # UNSAT certificate checked in gaussian() and all clauses accounted for.
        digest = None
        proof = "EXACT_CNFEQUIV_GAUSS_UNSAT_XOR_CERT_REPLAYED_NO_LRAT"
    return dict(**base, status=answer["status"], elapsed_s=time.perf_counter()-start,
                rank=answer["rank"], proof=proof, model_sha256=digest,
                certificate_rows=len(answer["conflict_row_ids"]))

def selftest():
    cases = [
        ("xor2-sat", "p cnf 2 2\n1 2 0\n-1 -2 0\n", "SAT"),
        ("xor2-unsat", "p cnf 2 4\n1 2 0\n-1 -2 0\n1 -2 0\n-1 2 0\n", "UNSAT"),
        ("xor2-plus-unit", "p cnf 2 3\n1 2 0\n-1 -2 0\n1 0\n", "SAT"),
        ("nonpure-safety", "p cnf 3 2\n1 2 0\n-2 3 0\n", "NOT_PURE"),
        ("empty-clause-fallback", "p cnf 1 1\n0\n", "NOT_PURE"),
        ("no-clauses", "p cnf 2 0\n", "SAT")
    ]
    with tempfile.TemporaryDirectory() as directory:
        for name, cnf, expected in cases:
            file = pathlib.Path(directory)/(name+".cnf")
            file.write_text(cnf)
            result = solve(file)
            need(result["status"] == expected, name+" got "+result["status"])
            print("R164_PURE_SELFTEST", name, result["status"], flush=True)
    print("R164_PURE_SELFTEST_PASS", len(cases), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?")
    parser.add_argument("--selftest", action="store_true")
    options = parser.parse_args()
    if options.selftest:
        selftest()
    else:
        need(options.source is not None, "missing source")
        print("R164_EXACT_RESULT", json.dumps(solve(options.source), sort_keys=True))
