"""LTM4 safety and structural-transfer tests; no native solver required."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mi_ltm3.design import xor_cnf, dimacs
from mi_ltm4.trajectory import (
    canonical_trajectory, episode_from_proof, extract)
from mi_ltm4.trajectory_store import TrajectoryMemory, recommend


def xor_demo(renaming=None):
    renaming = renaming or {1: 1, 2: 2, 3: 3, 4: 4}
    clauses = (xor_cnf(tuple(renaming[x] for x in (1, 2, 3)), 0) +
               xor_cnf(tuple(renaming[x] for x in (2, 3, 4)), 1))
    return dimacs(max(renaming.values()), clauses)


class TrajectoryTests(unittest.TestCase):
    def test_renaming_invariant_real_source_formula(self):
        a = extract(xor_demo())
        b = extract(xor_demo({1: 17, 2: 4, 3: 11, 4: 2}))
        self.assertEqual(a["status"], "diagnostic_only")
        self.assertEqual(b["status"], "diagnostic_only")
        self.assertTrue(a["episodes"])
        self.assertEqual({e["key"] for e in a["episodes"]},
                         {e["key"] for e in b["episodes"]})
        self.assertTrue(all(e["verified"] for e in a["episodes"]))
        self.assertTrue(any(e["kind"] == "binary_xor" for e in a["episodes"]))

    def test_exact_invariance_under_row_order(self):
        rows = [
            dict(variables=[1, 2, 3], rhs=0),
            dict(variables=[2, 3, 4], rhs=1),
            dict(variables=[4, 5], rhs=0)]
        a = canonical_trajectory(rows, "unit")[0]
        b = canonical_trajectory(list(reversed(rows)), "unit")[0]
        self.assertEqual(a, b)

    def test_missing_xor_encoding_not_treated_as_proof(self):
        clauses = xor_cnf((1, 2, 3), 0)[:-1]
        out = extract(dimacs(3, clauses))
        self.assertEqual(out["episodes"], [])

    def test_three_step_conflict_has_verified_provenance(self):
        clauses = (xor_cnf((1, 2), 0) +
                   xor_cnf((2, 3), 0) +
                   xor_cnf((1, 3), 1))
        report = extract(dimacs(3, clauses))
        self.assertTrue(any(e["kind"] == "conflict" and
                            e["source_count"] == 3
                            for e in report["episodes"]))

    def test_forged_consequence_is_rejected(self):
        rows = [dict(variables=[1, 2, 3], rhs=0),
                dict(variables=[2, 3, 4], rhs=1)]
        forged = dict(kind="binary_xor", variables=[1, 4], rhs=0,
                      source_equations=[0, 1])
        self.assertIsNone(episode_from_proof(rows, forged))


class LongTermTests(unittest.TestCase):
    @staticmethod
    def result(sha, arm, *, rep=0, t=.02, solved=True):
        return dict(sha256=sha, rep=rep, arm=arm, par2_s=t,
                    solved=solved, trial_audited=True)

    def test_positive_memory_and_frozen_holdout(self):
        episodes = extract(xor_demo())["episodes"]
        self.assertTrue(episodes)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.sqlite"
            db = TrajectoryMemory(path)
            for i in range(9):
                sha = "training-%d" % i
                db.remember(sha, episodes)
                db.record_pair(sha, 0,
                               self.result(sha, "BASE", t=.05),
                               self.result(sha, "MI_CHAIN", t=.025))
            frozen = db.freeze({"holdout"})
            self.assertTrue(frozen["positive_motifs"])
            self.assertEqual(recommend(frozen, episodes)[0], "MI_CHAIN")
            self.assertEqual(recommend(frozen, [])[0], "BASE")
            db.close()
            reader = TrajectoryMemory(path, readonly=True)
            self.assertEqual(reader.freeze({"holdout"}), frozen)
            with self.assertRaises(PermissionError):
                reader.remember("holdout", episodes)
            reader.close()

    def test_holdout_leakage_is_rejected(self):
        episodes = extract(xor_demo())["episodes"]
        with tempfile.TemporaryDirectory() as td:
            db = TrajectoryMemory(Path(td) / "memory.sqlite")
            db.remember("holdout", episodes)
            with self.assertRaises(AssertionError):
                db.freeze({"holdout"})
            db.close()

    def test_no_unmeasured_motif_becomes_positive(self):
        episodes = extract(xor_demo())["episodes"]
        with tempfile.TemporaryDirectory() as td:
            db = TrajectoryMemory(Path(td) / "memory.sqlite")
            db.remember("some-training", episodes)
            frozen = db.freeze({"heldout"})
            self.assertFalse(frozen["positive_motifs"])
            self.assertEqual(recommend(frozen, episodes)[0], "BASE")
            db.close()

    def test_solved_regression_blocks_promotion(self):
        episodes = extract(xor_demo())["episodes"]
        with tempfile.TemporaryDirectory() as td:
            db = TrajectoryMemory(Path(td) / "memory.sqlite")
            for i in range(9):
                sha = "r%d" % i
                db.remember(sha, episodes)
                db.record_pair(
                    sha, 0, self.result(sha, "BASE", t=.05),
                    self.result(sha, "MI_CHAIN", t=.025,
                                solved=(i != 0)))
            policy = db.freeze(set())
            self.assertFalse(policy["positive_motifs"])
            db.close()


if __name__ == "__main__":
    unittest.main()
