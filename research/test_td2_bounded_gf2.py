#!/usr/bin/env python3
"""Mathematical equivalence, real-source output identity and budget recovery."""
import contextlib
import io
import itertools
import json
import pathlib
import random
import signal
import tempfile
import time
import unittest
from unittest import mock

import td2_bounded_gf2 as method
import td2_cost_gate_benchmark as bench


class TD2Tests(unittest.TestCase):
    def test_random_satisfiable_and_unrestricted_matrices(self):
        rng = random.Random(20261107)
        for case in range(800):
            n = rng.randrange(2, 100)
            assignment = [rng.randrange(2) for _ in range(n)]
            rows = []
            for i in range(rng.randrange(1, 220)):
                variables = tuple(sorted(rng.sample(range(1, n + 1), rng.randrange(1, min(n, 9) + 1))))
                rhs = sum(assignment[v - 1] for v in variables) % 2 if case % 2 else rng.randrange(2)
                rows.append((variables, rhs, [i]))
            self.assertEqual(method.sparse_gaussian(rows),
                             method.certified.gf_src.gf.gaussian(rows), case)

    def test_small_matrices_against_exhaustive_assignments(self):
        rng = random.Random(73)
        for _ in range(100):
            n = 6
            rows = []
            for i in range(rng.randrange(1, 12)):
                variables = tuple(sorted(rng.sample(range(1, n + 1), rng.randrange(1, n + 1))))
                rows.append((variables, rng.randrange(2), [i]))
            valid = [bits for bits in itertools.product((0, 1), repeat=n)
                     if all(sum(bits[v - 1] for v in vs) % 2 == rhs for vs, rhs, _ in rows)]
            result = method.sparse_gaussian(rows)
            self.assertEqual(result["conflict"], not valid)
            if valid:
                expected = {v + 1: valid[0][v] for v in range(n)
                            if all(bits[v] == valid[0][v] for bits in valid)}
                self.assertEqual({v: rhs for v, (rhs, _trace) in result["units"].items()}, expected)

    def test_original_source_output_identity(self):
        families = ("cryptography-simon", "multiplier-circuits")
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            certified = method.certified
            with mock.patch.object(certified, "ROOT", root / "reference"), mock.patch.object(certified, "CAP", 20.0):
                for family in families:
                    source = next(pathlib.Path("r199/sources").glob("*-" + family + ".cnf"))
                    reference, meta, decision = certified.certified_preprocess(
                        source, "r193_hybrid4", 0, 0, time.perf_counter())
                    optimized, new_meta, new_decision = method.preprocess(source, 0, 0, root / "new", 5.0)
                    self.assertEqual(decision, new_decision)
                    self.assertEqual(reference.read_bytes(), optimized.read_bytes())
                    for key in ("gf2_units", "added_total_clauses", "augmented_sha256"):
                        self.assertEqual(meta[key], new_meta[key], key)

    def test_budget_expiry_discards_partial_output_and_restores_signal(self):
        source = next(pathlib.Path("r199/sources").glob("*-cryptography-simon.cnf"))
        digest = method.certified.sha(source)
        previous = signal.getsignal(signal.SIGALRM)
        with tempfile.TemporaryDirectory() as directory:
            # Force expiry during file creation, after mathematical certification.
            original_writer = method.certified.deriv.write_augmented
            def interrupted_writer(target, *args):
                original_writer(target, *args)
                signal.raise_signal(signal.SIGALRM)
            with mock.patch.object(method.certified.deriv, "write_augmented", interrupted_writer):
                work, meta, decision = method.preprocess(source, 0, 0, directory, 5.0)
            self.assertEqual(work, source)
            self.assertIsNone(decision)
            self.assertTrue(meta["preprocess_budget_exhausted"])
            self.assertEqual(meta["added_total_clauses"], 0)
            self.assertFalse(list(pathlib.Path(directory).rglob("*.cnf")))
        self.assertEqual(method.certified.sha(source), digest)
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        # Also exercise actual wall-clock expiry while executing Python.
        with self.assertRaises(method.PreparationExpired):
            with method.deadline(0.002):
                while True:
                    pass
        self.assertEqual(signal.getsignal(signal.SIGALRM), previous)

    def test_budget_fallback_reaches_original_solver(self):
        manifest = json.loads(pathlib.Path("r199/manifest.json").read_text())
        case = next(c for c in manifest["cases"] if c["family"] == "cryptography-simon")
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(bench, "ROOT", pathlib.Path(directory)):
            original = method.preprocess
            def expired(source, rep, shard, output_root, budget_s):
                return original(source, rep, shard, output_root, 0.000001)
            with mock.patch.object(method, "preprocess", expired), contextlib.redirect_stdout(io.StringIO()):
                result = bench.trial(case, "kissat_sparse_budget", 0, 0)
            self.assertEqual(result["status"], "SAT")
            self.assertEqual(result["proof"], "SAT_WITNESS_ORIGINAL_VERIFIED")
            self.assertTrue(result["preprocess_budget_exhausted"])
            self.assertEqual(result["added_total_clauses"], 0)

    def test_completed_pilot_skips_preparation(self):
        manifest = json.loads(pathlib.Path("r199/manifest.json").read_text())
        case = next(c for c in manifest["cases"] if c["family"] == "cryptography-simon")
        with mock.patch.object(method, "PILOT_CAP_S", 1.0), mock.patch.object(
                method, "preprocess", side_effect=AssertionError("pilot should finish")):
            with contextlib.redirect_stdout(io.StringIO()):
                result = bench.trial(case, "kissat_pilot_sparse_budget", 0, 0)
        self.assertEqual(result["status"], "SAT")
        self.assertTrue(result["pilot_solved"])
        self.assertEqual(result["preprocess_s"], 0)

    def test_incomplete_xor_is_not_a_source_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "incomplete.cnf"
            source.write_text("p cnf 3 3\n1 2 3 0\n1 -2 -3 0\n-1 2 -3 0\n")
            work, meta, decision = method.preprocess(source, 0, 0, directory)
            self.assertEqual(work, source)
            self.assertEqual(meta["xor_rows"], 0)
            self.assertEqual(meta["added_total_clauses"], 0)
            self.assertIsNone(decision)


if __name__ == "__main__":
    unittest.main(verbosity=2)
