#!/usr/bin/env python3
"""Test global diagnostic policy identity, AB protocol and family-unit confidence."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import drnas_local_global_real_ab as A

class GlobalLocalTests(unittest.TestCase):
    def test_rejected_global_candidate_can_be_tested_but_not_promoted(self):
        candidate={"protocol":"DRNAS-REAL-LEARN1-MATERIAL2","baseline":"X5_NO_MIN",
                   "promoted":False,"rule":None,
                   "proposed_rule":{"kind":"threshold","arm":"X5","feature":"binary",
                                    "below":False,"threshold":.140625}}
        rule=A.verify_candidate(candidate)
        self.assertEqual(rule["arm"],"X5")
        self.assertEqual(candidate["rule"],None)
        self.assertEqual(A.T.choose(rule,{"binary":.3}),"X5")
        self.assertEqual(A.T.choose(rule,{"binary":.05}),"X5_NO_MIN")

    def test_bad_or_promoted_model_cannot_be_tested_as_rejected(self):
        candidate={"protocol":"DRNAS-REAL-LEARN1-MATERIAL2","baseline":"X5_NO_MIN",
                   "promoted":True,"proposed_rule":{"kind":"fixed","arm":"X5"}}
        with self.assertRaises(AssertionError):
            A.verify_candidate(candidate)
        candidate["promoted"]=False
        candidate["proposed_rule"]={"kind":"fixed","arm":"Kissat"}
        with self.assertRaises(AssertionError):
            A.verify_candidate(candidate)

    def test_cluster_bootstrap_not_repeated_trials(self):
        rows=[]
        for fam,local,glob in [("famA",6.0,5.0),("famB",6.0,4.0)]:
            for arm, val in [("LOCAL",local),("GLOBAL_PROPOSED",glob)]:
                rows.append({"family":fam,"arm":arm,"PAR2":val})
        ci=A.interval(rows,"GLOBAL_PROPOSED",reps=100)
        self.assertEqual(ci["family_units"],2)
        self.assertAlmostEqual(ci["reduction"],.25)
        self.assertGreater(ci["lower95"],0)

    def test_full_material_split_rejects_family_leakage(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            manifest={"protocol":"DRNAS-REAL-LEARN1-MATERIAL2","sources":[]}
            # Semantic SHAs distinct, but same family with conflicting role.
            for i,role in enumerate(("train","holdout")):
                manifest["sources"].append({"sha256":str(i)*64,"semantic_sha256":str(i+2)*64,
                    "split":role,"family":"identical_family"})
            (root/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaises(AssertionError):
                A.records(root)

if __name__=="__main__":
    unittest.main()
