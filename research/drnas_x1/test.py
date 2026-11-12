#!/usr/bin/env python3
"""Deterministic differential, certificate and DIMACS regression tests."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile
import time
import check


def cnf(n, clauses):
    return f"p cnf {n} {len(clauses)}\n" + "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)


def brute(n, clauses):
    for bits in itertools.product((False, True), repeat=n):
        if all(any(bits[abs(l)-1] == (l > 0) for l in c) for c in clauses):
            return True
    return False


def cases(count):
    rng = random.Random(20261112)
    fixed = [(0, []), (0, [[]]), (1, [[1], [-1]]), (3, [[1, -1], [2, 2], [-2, 3]]),
             (3, [[a*1, b*2, c*3] for a in (-1, 1) for b in (-1, 1) for c in (-1, 1)])]
    seen = set()
    for n, clauses in fixed:
        text = cnf(n, clauses)
        seen.add(text)
        yield n, clauses, text
    while len(seen) < count:
        n = rng.randrange(1, 12)
        clauses = []
        for _ in range(rng.randrange(1, 6*n+1)):
            size = rng.choices([1, 2, 3, 4, 5], [1, 3, 9, 3, 1])[0]
            variables = rng.sample(range(1, n+1), min(n, size))
            clauses.append([v * rng.choice([-1, 1]) for v in variables])
        text = cnf(n, clauses)
        if text in seen:
            continue
        seen.add(text)
        yield n, clauses, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("binary", type=Path)
    ap.add_argument("--cases", type=int, default=600)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    binary = str(args.binary.resolve())
    started = time.monotonic()
    totals = {m: {"sat": 0, "unsat": 0, "checks": 0} for m in ("core", "auto", "factor")}
    source_hashes = []
    with tempfile.TemporaryDirectory(prefix="drnas-x1-test-") as td:
        root = Path(td)
        source, proof = root/"case.cnf", root/"proof.txt"
        for index, (n, clauses, text) in enumerate(cases(args.cases)):
            source.write_text(text)
            source_hashes.append(hashlib.sha256(text.encode()).hexdigest())
            expected = 10 if brute(n, clauses) else 20
            for mode in totals:
                cmd = [binary, "--mode", mode, "--seconds", "2", "--proof", str(proof), "--seed", str(index % 5 + 13), str(source)]
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
                if p.returncode != expected:
                    raise AssertionError({"index": index, "mode": mode, "expected": expected, "return": p.returncode,
                                          "out": p.stdout, "err": p.stderr, "cnf": text})
                checked = check.verify(source, p.stdout, proof, 3.0)
                if not checked["verified"]:
                    raise AssertionError({"index": index, "mode": mode, "check": checked, "proof": proof.read_text(), "cnf": text})
                totals[mode]["sat" if expected == 10 else "unsat"] += 1
                totals[mode]["checks"] += 1
            if (index + 1) % 100 == 0:
                print("X1_TEST_PROGRESS", index+1, flush=True)
        # Tokenization across lines, multiple clauses per line, very long DIMACS line.
        for text, result in [("c test\np cnf 3 2\n1\n-2 0 2 3 0\n", 10),
                             ("p cnf 1 1\n"+"1 "*10000+"0\n", 10)]:
            source.write_text(text)
            p = subprocess.run([binary, "--mode", "core", str(source)], capture_output=True, text=True, timeout=4)
            assert p.returncode == result and check.verify(source, p.stdout, None)["verified"]
        bad = ["p cnf 1 1\n1\n", "p cnf 1 1\n2 0\n", "p cnf 1 2\n1 0\n", "1 0\n",
               "p cnf -1 0\n", "p cnf 1 1\np cnf 1 1\n1 0\n", "p cnf 1 1\n1.2 0\n"]
        for text in bad:
            source.write_text(text)
            p = subprocess.run([binary, str(source)], capture_output=True, text=True, timeout=4)
            assert p.returncode == 1, (text, p.stdout, p.stderr)
        # Both independent certificate languages must reject a forged refutation of SAT.
        source.write_text("p cnf 2 1\n1 2 0\n")
        for text in ["0\n", "c X1_FACTOR_V1\nu\n", "c X1_FACTOR_V1\ne 1\nu\n",
                     "c X1_FACTOR_V1\ne 99\nu\n"]:
            proof.write_text(text)
            assert not check.verify(source, "s UNSATISFIABLE\n", proof)["verified"]
    result = {"unique_cnf": len(set(source_hashes)), "attempts": sum(x["checks"] for x in totals.values()),
              "modes": totals, "malformed_inputs_rejected": len(bad), "forged_proofs_rejected": 4,
              "elapsed_s": time.monotonic()-started, "oracle": "independent exhaustive enumeration",
              "proof_checker": "independent Python DRUP scan / relational elimination"}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2)+"\n")
    print("X1_TEST_PASS", json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
