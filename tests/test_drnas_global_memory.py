#!/usr/bin/env python3
"""Offline correctness and contamination tests for DRNAS global memory v1."""
import gzip
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
import drnas_global_memory as M


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        M.create_schema(self.db)
        self.sha1 = "a" * 64
        self.sha2 = "b" * 64

    def tearDown(self):
        self.db.close()

    def test_manifest_evidence_does_not_become_training(self):
        m = {
            "cohort": "synthetic", "split": "train",
            "originals": [{"sha256": self.sha1, "family": "php_structural_unsat",
                           "cert": "PHP_STRUCTURAL_CORE"}],
        }
        rows = [
            {"sha256": self.sha1, "arm": "CORE", "rep": 0, "status": "UNSAT",
             "verified": True, "PAR2": 0.04},
            {"sha256": self.sha1, "arm": "X46_LEARNED_8", "rep": 0,
             "status": "UNSAT", "verified": True, "PAR2": 0.02},
        ]
        total = M.import_pair_rows(self.db, 1, 10, "trials.jsonl",
                                   "\n".join(json.dumps(r) for r in rows), m)
        self.assertEqual(total, 2)
        self.assertEqual(M.import_pair_rows(self.db, 1, 10, "trials.jsonl",
                                             "\n".join(json.dumps(r) for r in rows), m), 0)
        actual = self.db.execute(
            "SELECT DISTINCT role FROM observations").fetchall()
        self.assertEqual(actual, [("holdout",)])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM eligible_training").fetchone()[0], 0)

    def test_sharded_zip_extract_and_provenance(self):
        m = {"originals": [{"sha256": self.sha1, "family": "php_structural_unsat"}],
             "cohort": "synthetic"}
        t = {"sha256": self.sha1, "arm": "CORE", "rep": 1,
             "status": "UNSAT", "verified": True, "PAR2": 0.005}
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("x47_shard_0/manifest.json", json.dumps(m))
            z.writestr("x47_shard_0/trials.jsonl", json.dumps(t) + "\n")
            z.writestr("x47_shard_0/report.json", json.dumps({"total_trials": 1}))
            z.writestr("disallowed.exe", "payload")
        reports, trials = M.import_zip(self.db, 9, 27, b.getvalue())
        self.assertEqual((reports, trials), (2, 1))
        self.assertEqual(self.db.execute(
            "SELECT role,verified_claim,par2_s FROM observations").fetchone(),
            ("holdout", 1, 0.005))
        self.assertEqual(M.import_zip(self.db, 9, 27, b.getvalue()), (2, 0))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 1)

    def test_legacy_train_import_with_holdout_taint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "legacy.sqlite"
            old = sqlite3.connect(f)
            old.executescript("""
                CREATE TABLE experiences(sha TEXT,protocol TEXT,split TEXT,regime TEXT,payload TEXT);
                CREATE TABLE checkpoints(id INTEGER,cycle INTEGER,model TEXT,tune_cost INTEGER,accepted INTEGER);
                CREATE TABLE sealed_tests(id INTEGER,payload TEXT);
            """)
            for sha, split in [(self.sha1, "train"), (self.sha2, "validation")]:
                old.execute("INSERT INTO experiences VALUES (?,?,?,?,?)",
                            (sha, "x47", split, "xor", json.dumps({
                                "meta": {"namespace": "X47-LONG-30K-v1", "split": split},
                                "sha256": sha
                            })))
            old.execute("INSERT INTO checkpoints VALUES (1,1,'{}',5,1)")
            old.execute("INSERT INTO sealed_tests VALUES (1,'{}')")
            old.commit()
            old.close()
            archive = root / "memory.sqlite.gz"
            archive.write_bytes(gzip.compress(f.read_bytes()))
            latest = root / "latest.json"
            latest.write_text(json.dumps({
                "namespace": "X47-LONG-30K-v1",
                "run": "43361933084", "stage": "completed-holdout-sealed",
                "model": {"deployment_allowed": True},
            }))
            result = M.import_legacy(self.db, archive, latest)
            self.assertEqual(result["experiences"], 2)
            self.assertEqual(self.db.execute(
                "SELECT COUNT(*) FROM eligible_training").fetchone()[0], 1)
            self.assertEqual(self.db.execute(
                "SELECT COUNT(*) FROM sealed_reports").fetchone()[0], 1)
            self.assertEqual(self.db.execute(
                "SELECT promotion_status FROM model_registry").fetchone()[0],
                "evidence_only")
            M.import_pair_rows(self.db, 9, 2, "trial", json.dumps({
                "sha256": self.sha1, "arm": "CORE", "rep": 0,
                "status": "SAT", "verified": True, "PAR2": 0.1
            }), {"originals": []})
            self.assertEqual(self.db.execute(
                "SELECT COUNT(*) FROM eligible_training").fetchone()[0], 0)
            self.assertEqual(M.import_legacy(self.db, archive, latest)["state"], "unchanged")

    def test_invalid_sha_and_unverified_not_trusted(self):
        self.assertFalse(M.valid_sha("not a SHA"))
        self.assertIsNone(M.safe_num(float("nan")))
        self.assertIsNone(M.safe_num(-4.0))
        good = {"sha256": self.sha1, "arm": "CORE", "rep": 0,
                "status": "UNSAT", "verified": False, "PAR2": 10}
        bad = dict(good, sha256="not a SHA")
        self.assertEqual(M.import_pair_rows(
            self.db, 3, 4, "trial", "\n".join(map(json.dumps, [bad, good])),
            {"originals": []}), 1)
        self.assertEqual(self.db.execute(
            "SELECT verified_claim FROM observations").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
