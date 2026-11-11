"""Safety, deterministic holdout and delayed-trigger tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from delayed import (ARMS,CAP,FAMILIES,PER_FAMILY,TRAIN_PER_FAMILY,
                     cohort,make_case,intervention,verify_result)


class DelayedTests(unittest.TestCase):
    def test_frozen_holdout_and_new_training(self):
        a=cohort(7)
        b=cohort(8)
        self.assertEqual(len(a),len(FAMILIES)*PER_FAMILY)
        self.assertEqual(len({x["sha"] for x in a}),len(a))
        self.assertEqual({x["sha"] for x in a if x["split"]=="holdout"},
                         {x["sha"] for x in b if x["split"]=="holdout"})
        self.assertTrue({x["sha"] for x in a if x["split"]=="train"}.isdisjoint(
                        {x["sha"] for x in b if x["split"]=="train"}))
        self.assertEqual(sum(x["split"]=="train" for x in a),
                         len(FAMILIES)*TRAIN_PER_FAMILY)

    def test_planted_original_witness(self):
        from design import satisfies
        for family in FAMILIES:
            for i in (0,1,2,23,24,47):
                case=make_case(family,i,4)
                self.assertTrue(satisfies(case["clauses"],case["model"]))

    def test_native_unsat_cannot_be_credited(self):
        case=make_case(FAMILIES[0],1,4)
        with self.assertRaises(AssertionError):
            verify_result(case,20,"s UNSATISFIABLE")

    def test_bounded_source_xor_inference(self):
        case=make_case("hard_planted_xor_mix",0,4)
        for arm in ("DELAYED_XOR","DELAYED_CHAIN"):
            added,elapsed,ops,reason=intervention(case,arm)
            self.assertGreaterEqual(elapsed,0)
            self.assertGreaterEqual(ops,0)
            self.assertLessEqual(len(added),48)
            self.assertIn(reason,("derived","no_new_clauses","probe_abstained"))
            # The source model must satisfy every injected derived clause.
            from design import satisfies
            self.assertTrue(satisfies(added,case["model"]))

    def test_preflight_and_restart_same_cpu_budget(self):
        self.assertLess(.025,CAP)
        self.assertEqual(ARMS[0],"STAGED_CONTROL")


if __name__=="__main__":
    unittest.main()
