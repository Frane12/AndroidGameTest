#!/usr/bin/env python3
"""Safety, confidence and split-contract tests for DRNAS global learning."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import drnas_global_learning as L

class GateTests(unittest.TestCase):
    def sample(self,improve=.1,low=.04):
        return {
            "input_overlap":False,
            "validation":{"labelled":180,"audit_reduction":.02},
            "holdout":{
                "sources":80,"families":5,
                "incumbent_verified":160,"candidate_verified":160,"core_verified":160,
                "vs_incumbent":{"reduction":improve,"lower95":low,"upper95":.2},
                "vs_core":{"reduction":improve,"lower95":low,"upper95":.2},
                "severe_regressions":0,
                "families_regressed_10pct":0,"incorrect_outputs":0
            }
        }

    def test_passing_candidate_requires_strict_multiple_gates(self):
        self.assertEqual(L.candidate_gate(self.sample()),(True,[]))

    def test_noisy_small_positive_mean_is_rejected(self):
        ok,reasons=L.candidate_gate(self.sample(.1,-.01))
        self.assertFalse(ok)
        self.assertIn("paired_PAR2_gain_not_confident_5pct",reasons)

    def test_fewer_solved_invalid_and_tail_regressions_rejected(self):
        m=self.sample()
        m["holdout"]["candidate_verified"]=158
        m["holdout"]["incorrect_outputs"]=1
        m["holdout"]["families_regressed_10pct"]=1
        m["holdout"]["severe_regressions"]=20
        ok,reasons=L.candidate_gate(m)
        self.assertFalse(ok)
        for s in ("fewer_verified_sat","incorrect_output",
                  "too_many_source_regressions","family_regression_over_10pct"):
            self.assertIn(s,reasons)

    def test_split_overlap_rejected(self):
        db=sqlite3.connect(":memory:")
        db.executescript("""
            CREATE TABLE legacy_experiences (source_sha TEXT, split TEXT, payload TEXT);
            CREATE TABLE observations (source_sha TEXT, role TEXT);
        """)
        L.init_tables(db)
        db.execute("INSERT INTO legacy_experiences VALUES ('a','train','{}')")
        db.execute("INSERT INTO observations VALUES ('a','holdout')")
        with self.assertRaisesRegex(RuntimeError,"holdout"):
            L.inspect_splits(db)
        db.close()

    def test_pair_bootstrap_has_independent_source_units(self):
        x=L.strict_bootstrap([1.]*80,[.7]*80,draws=200)
        self.assertAlmostEqual(x["reduction"],.3)
        self.assertGreater(x["lower95"],.29)
        bad=L.strict_bootstrap([1.]*80,[1.]*80,draws=200)
        self.assertEqual(bad["lower95"],0.)
        with self.assertRaises(ValueError):
            L.strict_bootstrap([1.],[1.,2.])

    def test_train_rows_require_verified_label_and_feature_vector(self):
        r={"sha256":"b"*64,"features":[0.]*24,"label":.6,
           "base":{"verified":True,"work_cost":100},
           "flip":{"verified":False,"work_cost":200}}
        with self.assertRaises(AssertionError):
            L.check_row(r)
        r["flip"]["verified"]=True
        self.assertEqual(L.check_row(r),r)

if __name__=="__main__":
    unittest.main()
