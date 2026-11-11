import tempfile
import unittest
from pathlib import Path

from design import (FAMILIES,PER_FAMILY,TRAIN_PER_FAMILY,
                    cohort,make_case,opportunity_key,
                    satisfies,source_parity_unsat,xor_cnf,dimacs)
from experiment import independently_audit_inferences
from policy import TrainingMemory, action
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"mi_ltm1"))
from probe import probe_cnf


class DesignTests(unittest.TestCase):
    def test_unique_sha_disjoint_frozen_holdout(self):
        a=cohort(training_generation=17)
        b=cohort(training_generation=18)
        self.assertEqual(len(a),384)
        self.assertEqual(len({x["sha"] for x in a}),384)
        self.assertEqual(sum(x["split"]=="train" for x in a),192)
        self.assertEqual(sum(x["split"]=="holdout" for x in a),192)
        ha={x["sha"] for x in a if x["split"]=="holdout"}
        hb={x["sha"] for x in b if x["split"]=="holdout"}
        self.assertEqual(ha,hb)
        self.assertTrue({x["sha"] for x in a if x["split"]=="train"}.isdisjoint(
                        {x["sha"] for x in b if x["split"]=="train"}))
        self.assertTrue(all(x["n"]>=48 for x in a))

    def test_ground_truth_and_independent_source_proofs(self):
        for family in FAMILIES:
            for i in (0,1,2,15,32,63):
                case=make_case(family,i,generation=12)
                if case["expect"]=="SAT_PLANTED":
                    self.assertTrue(satisfies(case["clauses"],case["planted"]))
                else:
                    unsat,_=source_parity_unsat(case["clauses"])
                    self.assertTrue(unsat)
                self.assertTrue(case["raw"].startswith("p cnf "))

    def test_cheap_signature_renaming_invariant(self):
        case=make_case("xor_overlap_planted",7,generation=5)
        n=case["n"]
        reversed_clauses=[tuple((n+1-abs(l))*(1 if l>0 else -1)
                                for l in c) for c in case["clauses"]]
        self.assertEqual(opportunity_key(case["clauses"],n),
                         opportunity_key(reversed_clauses,n))

    def test_audit_of_source_and_tampered_consequence(self):
        cls=xor_cnf((1,2,3),0)+xor_cnf((2,3,4),0)
        report=probe_cnf(dimacs(4,cls))
        independently_audit_inferences(cls,report)
        self.assertTrue(report["consequences"])
        report["consequences"][0]["rhs"] ^= 1
        with self.assertRaises(AssertionError):
            independently_audit_inferences(cls,report)


class PolicyTests(unittest.TestCase):
    @staticmethod
    def item(t,solved=True,conflicts=10):
        return dict(par2_s=t,solved=solved,
                    verified=True,conflicts=conflicts,probe_s=.0005)

    def test_positive_gate_and_negative_gate(self):
        with tempfile.TemporaryDirectory() as td:
            db=TrainingMemory(Path(td)/"policy.sqlite")
            for i in range(10):
                db.insert_pair(sha=str(i),rep=0,generation=1,
                               family="test",key="good",
                               base=self.item(.04),force=self.item(.02))
                db.insert_pair(sha="bad"+str(i),rep=0,generation=1,
                               family="test",key="bad",
                               base=self.item(.02),force=self.item(.04))
            db.insert_patterns("0",{"pair:3:3:shared2:out2:rhs0":"binary_xor"})
            frozen=db.freeze({"holdout"})
            self.assertEqual(action(frozen,"good")[0],"MI_XOR")
            self.assertEqual(action(frozen,"bad")[0],"BASE")
            self.assertEqual(action(frozen,"unknown")[0],"BASE")
            db.close()
            read=TrainingMemory(Path(td)/"policy.sqlite",readonly=True)
            self.assertEqual(read.freeze({"holdout"}),frozen)
            with self.assertRaises(PermissionError):
                read.insert_patterns("holdout",{"x":"unit"})
            read.close()

    def test_no_holdout_leakage(self):
        with tempfile.TemporaryDirectory() as td:
            db=TrainingMemory(Path(td)/"policy.sqlite")
            db.insert_pair(sha="heldout",rep=0,generation=1,family="x",
                           key="x",base=self.item(.1),force=self.item(.2))
            with self.assertRaises(AssertionError):
                db.freeze({"heldout"})
            db.close()


if __name__=="__main__":
    unittest.main()
