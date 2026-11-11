import tempfile
import unittest
from pathlib import Path

from graph_shadow import graph,shadow_snapshot,source_rows,sample_snapshots
from memory import StructuralMemory


def xor3(a,b,c,rhs):
    vars_=(a,b,c)
    return [tuple(-v if mask&(1<<j) else v for j,v in enumerate(vars_))
            for mask in range(8) if mask.bit_count()%2 != rhs]


class GraphShadowTests(unittest.TestCase):
    def test_source_certified_and_incomplete_rejected(self):
        original=xor3(1,2,3,0)
        self.assertEqual(len(source_rows(original)),1)
        self.assertEqual(source_rows(original[:-1]),[])

    def test_relational_overlap_and_rename(self):
        clauses=xor3(1,2,3,0)+xor3(2,3,4,1)
        graph1=graph(clauses)
        self.assertEqual(len(graph1["rows"]),2)
        self.assertEqual(len(graph1["edges"]),1)
        self.assertEqual(graph1["edges"][0]["reduced_width"],2)
        renamed=[tuple((abs(x)+100)*(1 if x>0 else -1)
                       for x in c) for c in clauses]
        self.assertEqual(graph1["signature"],graph(renamed)["signature"])

    def test_trail_context_and_duplicate_bcp(self):
        rows=source_rows(xor3(1,2,3,0))
        x=shadow_snapshot(rows,{1:True,2:False},bcp_known={3})
        self.assertEqual(x["measurements"]["already_known_to_BCP"],1)
        self.assertEqual(x["candidates"][0]["literal"],3)
        y=shadow_snapshot(rows,{1:True,2:False})
        self.assertEqual(y["measurements"]["candidate_unconfirmed_BCP"],1)
        self.assertFalse(y["native_bcp_closure_confirmed"])

    def test_conflict_candidate(self):
        rows=source_rows(xor3(1,2,3,0))
        x=shadow_snapshot(rows,{1:True,2:False,3:False})
        self.assertEqual(x["measurements"]["candidate_conflict"],1)

    def test_synthetic_is_not_live(self):
        x=sample_snapshots(xor3(1,2,3,0))
        self.assertTrue(x)
        self.assertTrue(all(not item["native_bcp_closure_confirmed"] for item in x))


class MemoryTests(unittest.TestCase):
    def test_negative_and_positive_training(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"memory.sqlite"
            m=StructuralMemory(path)
            obs=dict(native_bcp_closure_confirmed=True,candidate_events=2,
                     bcp_confirmed_new=1,bcp_already_known=1)
            for i in range(10):
                base=dict(par2_s=.1,solved=True,audited=True)
                better=dict(par2_s=.06,solved=True,audited=True)
                worse=dict(par2_s=.14,solved=True,audited=True)
                self.assertEqual(m.record(formula_sha=str(i),rep=0,motif="good",
                                          observed=obs,base=base,trial=better,
                                          intervention_cost_s=.001),"positive")
                self.assertEqual(m.record(formula_sha=str(i),rep=0,motif="bad",
                                          observed=obs,base=base,trial=worse,
                                          intervention_cost_s=.001),"negative")
            p=m.freeze({"holdout"})
            self.assertTrue(p["good"]["permit_intervention"])
            self.assertFalse(p["bad"]["permit_intervention"])
            m.close()
            ro=StructuralMemory(path,readonly=True)
            self.assertEqual(ro.freeze({"holdout"}),p)
            with self.assertRaises(PermissionError):
                ro.record(formula_sha="x",rep=0,motif="x",observed=obs,
                          base=base,trial=better,intervention_cost_s=0)
            ro.close()

    def test_no_holdout_and_no_synthetic_training(self):
        with tempfile.TemporaryDirectory() as td:
            m=StructuralMemory(Path(td)/"memory.sqlite")
            obs=dict(native_bcp_closure_confirmed=False,candidate_events=1,
                     bcp_confirmed_new=0,bcp_already_known=0)
            base=dict(par2_s=1,solved=True,audited=True)
            with self.assertRaises(ValueError):
                m.record(formula_sha="a",rep=0,motif="m",observed=obs,
                         base=base,trial=base,intervention_cost_s=0)
            obs["native_bcp_closure_confirmed"]=True
            with self.assertRaises(ValueError):
                m.record(formula_sha="holdout",rep=0,motif="m",observed=obs,
                         base=base,trial=base,intervention_cost_s=0,
                         cohort="holdout")
            m.record(formula_sha="holdout",rep=0,motif="m",observed=obs,
                     base=base,trial=base,intervention_cost_s=0)
            with self.assertRaises(AssertionError):
                m.freeze({"holdout"})
            m.close()


if __name__=="__main__":
    unittest.main()
