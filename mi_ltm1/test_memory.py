import tempfile
import unittest
from pathlib import Path
from memory import Memory, signature

class TestMemory(unittest.TestCase):
    def test_renaming_invariant(self):
        self.assertEqual(signature([[1,2],[-1,3]]),
                         signature([[11,12],[-11,13]]))

    def test_learning_and_frozen_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp)/"memory.sqlite"
            sig = signature([[1,2],[-1,3]])
            m = Memory(db)
            for i in range(6):
                m.record(cohort="train", formula_sha=str(i), signature=sig,
                         arm="cheap_probe", baseline_e2e=1.0,
                         candidate_e2e=0.8, baseline_solved=True,
                         candidate_solved=True, cap_s=5, verified=True,
                         probe_s=0.01)
            self.assertEqual(m.recommend(sig)["arm"], "cheap_probe")
            self.assertIsNone(m.recommend(sig, excluded_cohort="train"))
            m.close()
            frozen = Memory(db, readonly=True)
            self.assertEqual(frozen.recommend(sig)["matched_cases"], 6)
            with self.assertRaises(PermissionError):
                frozen.record(cohort="test", formula_sha="x", signature=sig,
                              arm="cheap_probe", baseline_e2e=1,
                              candidate_e2e=0.8, baseline_solved=True,
                              candidate_solved=True, cap_s=5,
                              verified=True, probe_s=0.01)
            frozen.close()

    def test_solved_regression_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = Memory(Path(tmp)/"memory.sqlite")
            for i in range(5):
                m.record(cohort="train",formula_sha=str(i),signature="s",
                         arm="bad",baseline_e2e=1,candidate_e2e=0.1,
                         baseline_solved=True,candidate_solved=False,
                         cap_s=5,verified=True,probe_s=0.01)
            self.assertIsNone(m.recommend("s"))
            m.close()

if __name__ == "__main__":
    unittest.main()
