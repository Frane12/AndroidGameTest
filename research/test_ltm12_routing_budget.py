"""Deterministic regressions for the outer routing clock and disabled policy."""
import unittest
from unittest.mock import patch
import drnas_ltm12_progressive as L


class RoutingBudgetTest(unittest.TestCase):
    source = dict(id=80, split="holdout", path="unused.cnf", sha256="source-hash")

    def run_route(self, times, enabled=False):
        model = L.blank("HYBRID")
        if enabled:
            model.update(enabled=True, feature="binary", threshold=.5,
                         alternate="CaDiCaL")
        row = dict(status="SAT_VERIFIED", verified=True,
                   php_math_certified=False, e2e_s=.1)
        with patch.object(L.time, "monotonic", side_effect=times), \
             patch.object(L.F, "extract", return_value={"binary":.1}) as extract, \
             patch.object(L, "run_checked", return_value=row) as solver:
            result = L.run_routed(self.source, 17, "HYBRID", {"models":{"HYBRID":model}})
        return result, extract, solver

    def test_disabled_policy_never_scans_cnf(self):
        row, extract, solver = self.run_route([0, .001, .2])
        extract.assert_not_called()
        self.assertEqual(row["chosen_solver"], "Kissat")
        self.assertEqual(row["PAR2_verified_s"], .2)
        self.assertEqual(row["cap_s"], 12)
        self.assertEqual(row["original_cnf_sha256"], "source-hash")
        self.assertAlmostEqual(solver.call_args.args[-1], 11.999)

    def test_enabled_policy_pays_feature_cost(self):
        row, extract, solver = self.run_route([0, 2, 3], True)
        extract.assert_called_once()
        self.assertEqual(row["chosen_solver"], "CaDiCaL")
        self.assertEqual(row["PAR2_verified_s"], 3)
        self.assertEqual(solver.call_args.args[-1], 10)

    def test_outer_deadline_cannot_earn_verified_reward(self):
        row, _, _ = self.run_route([0, .001, 12.000001])
        self.assertEqual(row["status"], "UNKNOWN")
        self.assertFalse(row["verified"])
        self.assertEqual(row["PAR2_verified_s"], 24)

    def test_exhausted_feature_budget_does_not_launch_solver(self):
        row, _, solver = self.run_route([0, 13, 13.01], True)
        solver.assert_not_called()
        self.assertEqual(row["e2e_s"], 13.01)
        self.assertEqual(row["PAR2_verified_s"], 24)

    def test_reference_coverage(self):
        self.assertTrue(set(("Kissat", "CaDiCaL", "CryptoMiniSat")) <= set(L.TEST_ARMS))


if __name__ == "__main__":
    unittest.main()
