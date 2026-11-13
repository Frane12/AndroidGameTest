#!/usr/bin/env python3
"""Offline REAL2 material/learning safety tests. No remote archive access."""
import argparse
import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"research"))
import drnas_real_learn2_material as M
import drnas_real_learn2_fit as F

def source(s):
    return ("c source\np cnf 3 3\n1 -2 0\n-1 3 0\n"+s+" 0\n").encode()

class RealLearn2Tests(unittest.TestCase):
    def test_full_dimacs_and_whitespace_normalization(self):
        raw=b"c source A\np cnf 3 2\n1 -2 0\n3 0\n"
        d=M.validate_complete_dimacs(raw)
        self.assertEqual((d["nvars"],d["nclauses"],d["n_literals"],d["max_width"]),(3,2,3,2))
        other=b"c renamed\np cnf 3 2\n1   -2   0\n3 0\n"
        self.assertEqual(d["semantic_sha"],M.validate_complete_dimacs(other)["semantic_sha"])
    def test_truncated_missing_zero_rejected(self):
        for raw in (b"p cnf 3 2\n1 0\n2 3\n",
                    b"p cnf 3 2\n1 0\n2 0\n3 0\n",
                    b"p cnf 3 1\n4 0\n",
                    b"p cnf 3 1\n1 0\np cnf 3 1\n",
                    b"p cnf 0 1\n0\n"):
            with self.subTest(raw=raw):
                with self.assertRaises((ValueError,UnicodeError)):
                    M.validate_complete_dimacs(raw)
    def test_decode_bounded_gzip(self):
        raw=b"p cnf 1 1\n1 0\n"
        self.assertEqual(M.decode("t.cnf.gz",gzip.compress(raw)),raw)
        with self.assertRaises(ValueError):
            M.decode("t.cnf.xz",b"this-is-not-xz")
    def test_old_roles_and_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            old={"sources":[{"sha256":"a"*64,"split":"holdout","family":"F"}]}
            state={"sources":[{"sha256":"b"*64,"semantic_sha":"c"*64,
                               "split":"train","family":"G"}]}
            (root/"old.json").write_text(json.dumps(old))
            (root/"state.json").write_text(json.dumps(state))
            sha,sem,roles=M.prior_sets(root/"state.json",root/"old.json")
            self.assertEqual(roles,{"F":"holdout","G":"train"})
            self.assertIn("a"*64,sha)
            self.assertIn("c"*64,sem)
            self.assertEqual(M.split_for_family("F",roles),"holdout")
            self.assertEqual(M.split_for_family("G",roles),"train")
    def test_prev_validation_never_in_training(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"1").mkdir()
            a={"protocol":F.MODEL_VERSION,"cap_s":15.0}
            (root/"1"/"training_audit.json").write_text(json.dumps(a))
            trainrow={"split":"train","sha256":"a"*64,"features":{"density":1},
                      "PAR2":30.0,"e2e_s":15.0,"accepted":False,
                      "verified":False}
            with gzip.open(root/"1"/"train.jsonl.gz","wt") as fd:
                fd.write(json.dumps(trainrow)+"\n")
            catalog={"sources":[{"sha256":"a"*64,"split":"holdout"}]}
            with self.assertRaisesRegex(RuntimeError,"not explicitly assigned train"):
                F.load_prior(root,set(),catalog,15.)
    def test_cumulative_duplicate_protection(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/"1").mkdir()
            (root/"1"/"training_audit.json").write_text(json.dumps({
                "protocol":F.MODEL_VERSION,"cap_s":15.0}))
            row={"split":"train","sha256":"a"*64,"features":{"density":1},
                 "PAR2":30.0,"e2e_s":15.0,"accepted":False,"verified":False}
            with gzip.open(root/"1"/"train.jsonl.gz","wt") as fd:fd.write(json.dumps(row)+"\n")
            with self.assertRaisesRegex(RuntimeError,"overlap"):
                F.load_prior(root,{"a"*64},{"sources":[{"sha256":"a"*64,"split":"train"}]},15.)

if __name__=="__main__":
    unittest.main()
