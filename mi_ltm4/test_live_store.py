import tempfile
import unittest
from pathlib import Path
from live_store import NativeTraceMemory,recognize


def trace():
    return {"kind":"passive_native_cdcl_trace",
            "episodes":[{"key":"cdcl4:example1","observational_only":True,
                         "reason_graph_available":True}]}


class LiveMemoryTests(unittest.TestCase):
    def test_reopen_and_recognize_never_route_to_unverified_action(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"training.sqlite"
            db=NativeTraceMemory(p)
            for i in range(4):
                db.remember("sha-"+str(i),trace(),["traj4:algebra"])
            frozen=db.freeze({"holdout"})
            self.assertEqual(frozen["training_formula_count"],4)
            self.assertEqual(frozen["native_support"]["cdcl4:example1"],4)
            self.assertEqual(len(frozen["cross_support"]),1)
            db.close()
            ro=NativeTraceMemory(p,readonly=True)
            self.assertEqual(ro.freeze({"holdout"}),frozen)
            self.assertEqual(recognize(frozen,trace(),["traj4:algebra"])
                             ["proposed_action"],"BASE")
            with self.assertRaises(PermissionError):
                ro.remember("holdout",trace(),[])
            ro.close()

    def test_holdout_forbidden_both_tables(self):
        with tempfile.TemporaryDirectory() as td:
            db=NativeTraceMemory(Path(td)/"mem.sqlite")
            db.remember("holdout",trace(),["traj4:algebra"])
            with self.assertRaises(AssertionError):
                db.freeze({"holdout"})
            db.close()

    def test_reject_unaudited_and_unsafely_named_observations(self):
        with tempfile.TemporaryDirectory() as td:
            db=NativeTraceMemory(Path(td)/"mem.sqlite")
            bad={"kind":"passive_native_cdcl_trace",
                 "episodes":[{"key":"clause:1,-2", "observational_only":True}]}
            with self.assertRaises(ValueError):
                db.remember("train",bad,[])
            db.close()


if __name__ == "__main__":
    unittest.main()
