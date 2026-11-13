#!/usr/bin/env python3
"""Protocol-level tests only; no SAT solvers or external downloads."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import drnas_real_speed_v1 as S

class SpeedProtocolTests(unittest.TestCase):
    def test_family_bootstrap_one_vs_one(self):
        rows=[]
        for i in range(24):
            family=f"family-{i}"
            sha=f"sha-{i}"
            for arm,cost in (("CORE",10.0),("X52_LBD",8.0)):
                for rep in (0,1):
                    rows.append({"family":family,"sha256":sha,"arm":arm,
                                 "PAR2_s":cost,"rep":rep})
        ci=S.bootstrap_family(rows,"X52_LBD","CORE",draws=300)
        self.assertGreater(ci["lower95"],.19)
        self.assertEqual(ci["family_units"],24)

    def test_stage_does_not_export_holdout(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);prepared=base/"prepared";src=prepared/"real2_source"
            src.mkdir(parents=True); entries=[]
            for i in range(104):
                role=("train" if i<72 else "validation" if i<92 else "holdout")
                raw=(f"c source {i}\np cnf 1 1\n1 0\n").encode()
                sha=hashlib.sha256(raw).hexdigest()
                filename=f"{i:04d}.cnf"
                (src/filename).write_bytes(raw)
                entries.append({"sha256":sha,"family":f"family-{i}",
                                "file":filename,"split":role,
                                "nvars":1,"nclauses":1})
            S.save(prepared/"real2_splits.json",{
                "sources":entries,"source_count":len(entries)})
            class A: pass
            args=A();args.prepared=prepared;args.out=base/"dev"
            S.stage(args)
            m=S.load(base/"dev"/"manifest.json")
            self.assertEqual(m["source_count"],92)
            self.assertEqual(m["sealed_holdout_count"],12)
            actual={p.stem for p in (base/"dev"/"cnf").glob("*.cnf")}
            self.assertEqual(actual,{s["sha256"] for s in entries if s["split"]!="holdout"})
            self.assertFalse(actual.intersection(m["sealed_holdout_sha256"]))

    def test_merge_rejects_family_role_collision(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            S.save(base/"a.json",{"sources":[{"sha256":"a","family":"f","split":"train"}]})
            S.save(base/"b.json",{"sources":[{"sha256":"b","family":"f","split":"holdout"}]})
            class A:pass
            args=A();args.real2_state=base/"a.json";args.speed_state=base/"b.json";args.out=base/"out.json"
            with self.assertRaises(RuntimeError):
                S.merge_state(args)

    def test_verdict_requires_credible_family_evidence(self):
        rows=[]
        for i in range(21):
            fam=f"f{i}"
            for arm,cost in (("CORE",10.0),("X52_LBD",10.0)):
                rows.append({"family":fam,"arm":arm,"PAR2_s":cost})
        ci=S.bootstrap_family(rows,"X52_LBD","CORE",draws=150)
        self.assertEqual(ci["reduction"],0.0)
        self.assertEqual(ci["lower95"],0.0)

if __name__=="__main__":
    unittest.main()
