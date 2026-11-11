import tempfile
import unittest
from pathlib import Path

from memory import Memory
from memory_experiment import FAMILIES, catalog, freeze_policy, make_case


class TestMemoryExperiment(unittest.TestCase):
    def test_320_source_distinct_training_and_holdout(self):
        rows = catalog()
        self.assertEqual(len(rows), 320)
        self.assertEqual(len({r["sha"] for r in rows}), 320)
        self.assertEqual(sum(r["split"] == "train" for r in rows), 192)
        self.assertEqual(sum(r["split"] == "holdout" for r in rows), 128)
        for family in FAMILIES:
            self.assertEqual(sum(r["family"] == family for r in rows), 40)

    def test_never_train_from_current_holdout_sha(self):
        with tempfile.TemporaryDirectory() as td:
            db = Memory(Path(td) / "history.sqlite")
            train = [{"sha": "training_sha", "signature": "shared"}]
            holdout = [{"sha": "holdout_sha", "signature": "shared"}]
            for sha in ("training_sha", "holdout_sha"):
                db.record(cohort="training_rep_0",
                          formula_sha=sha, signature="shared", arm="MI_XOR",
                          baseline_e2e=.010, candidate_e2e=.005,
                          baseline_solved=True, candidate_solved=True,
                          cap_s=2, verified=True, probe_s=.0001)
            policy = freeze_policy(db, train, holdout)
            self.assertEqual(policy["training_shas"], ["training_sha"])
            self.assertEqual(policy["seen"]["shared"]["training_formulas"], 1)
            db.close()

if __name__ == "__main__":
    unittest.main()
