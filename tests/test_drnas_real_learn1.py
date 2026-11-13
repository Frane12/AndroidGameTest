#!/usr/bin/env python3
"""Safety and learning-contract unit tests; no fabricated real-world benchmark."""
import argparse
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
import drnas_real_learn1 as L

class RealLearn1Tests(unittest.TestCase):
    def test_family_split_and_sha_isolation(self):
        entries=[{"sha256":hashlib.sha256(f"src-{i}".encode()).hexdigest(),
                  "family":f"f{i%30}","file":f"{i:03}.cnf"} for i in range(120)]
        res=L.assign_splits(entries)
        self.assertEqual(sum(len(x) for x in res.values()),120)
        self.assertTrue(all(len(res[s])>=12 for s in L.SPLITS))
        for i,a in enumerate(L.SPLITS):
            for b in L.SPLITS[i+1:]:
                self.assertFalse({r["family"] for r in res[a]} & {r["family"] for r in res[b]})
                self.assertFalse({r["sha256"] for r in res[a]} & {r["sha256"] for r in res[b]})

    def test_structural_sampling(self):
        f=L.structural_features("c note\np cnf 3 3\n1 0\n1 -2 0\n-1 -2 3 0\n",3,3)
        self.assertEqual(f["unit_fraction"],1/3)
        self.assertEqual(f["binary_fraction"],1/3)
        self.assertEqual(f["horn_fraction"],1)
        self.assertEqual(f["mean_width"],2)
        self.assertEqual(f["density"],1)

    def test_rule_threshold_and_safe_abstention(self):
        f={k:0.0 for k in L.FEATURES}
        rule={"kind":"threshold","arm":"X5_NO_MIN","feature":"density","threshold":5., "direction":"lt"}
        self.assertEqual(L.choose({"active_rule":rule},f),"X5_NO_MIN")
        f["density"]=10.
        self.assertEqual(L.choose({"active_rule":rule},f),"CORE")
        self.assertEqual(L.choose({"active_rule":None},f),"CORE")

    def test_censored_source_never_treated_as_solved(self):
        samples={"x":{"cost":{"CORE":6.,"X5_NO_MIN":6.,"X52_LBD":3.},
                      "solved":{"X52_LBD":1},"family":"f",
                      "features":{k:0. for k in L.FEATURES}}}
        outcome=L.rule_score(samples,{"kind":"fixed","arm":"X52_LBD"})
        self.assertEqual(outcome["core_solved"],0)
        self.assertEqual(outcome["candidate_solved"],1)
        self.assertAlmostEqual(outcome["relative_gain"],.5)

    def test_source_cluster_is_unit_not_repeat(self):
        groups={"x":{"CORE":[{"PAR2":4.},{"PAR2":4.}],
                     "LEARN1_ROUTED":[{"PAR2":2.},{"PAR2":2.}]},
                "y":{"CORE":[{"PAR2":6.},{"PAR2":6.}],
                     "LEARN1_ROUTED":[{"PAR2":5.},{"PAR2":5.}]}}
        out=L.cluster_ci(groups,"LEARN1_ROUTED","CORE",reps=100)
        self.assertEqual(out["independent_source_units"],2)
        self.assertAlmostEqual(out["reduction"],.3)

    def test_split_manifest_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); src=root/"sources";src.mkdir()
            sources=[]
            for i in range(120):
                raw=f"p cnf 3 2\n{i%3+1} 0\n-1 2 0\n".encode()
                # Repetitions of text are disallowed: vary comments to preserve exact SHA identities.
                raw=(f"c fixture {i}\n").encode()+raw
                fname=f"{i:03}.cnf";(src/fname).write_bytes(raw)
                sources.append({"file":fname,"sha256":L.digest(raw),"family":f"fam_{i%30}",
                                "nvars":3,"nclauses":2})
            (src/"source_manifest.json").write_text(json.dumps({"sources":sources,"dataset":"fixture",
                "selection":"fixture only"}))
            out=root/"split.json"
            L.split_sources(argparse.Namespace(sources=src,count=120,out=out))
            m,b=L.checked_manifest(argparse.Namespace(split_manifest=out))
            self.assertEqual(m["source_count"],120)
            self.assertEqual(len(b["holdout"]),m["split_counts"]["holdout"])
            self.assertGreater(m["split_families"]["holdout"],0)

if __name__=="__main__":
    unittest.main()
