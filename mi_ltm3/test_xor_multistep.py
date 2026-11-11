"""Proof and budget regression checks for the MI-LTM3 multi-step arm."""
import unittest

from xor_multistep import closure, audit_provenance


class MultiStepProofTests(unittest.TestCase):
    def test_three_row_cycle_proves_unsat(self):
        equations=[
            {"variables":[1,2],"rhs":0},
            {"variables":[2,3],"rhs":1},
            {"variables":[1,3],"rhs":0},
        ]
        result=closure(equations,budget_s=1)
        conflict=[c for c in result["consequences"] if c["kind"]=="conflict"]
        self.assertTrue(conflict)
        self.assertEqual(conflict[0]["source_equations"],[0,1,2])
        self.assertTrue(audit_provenance(equations,conflict[0]))

    def test_long_chain_produces_binary(self):
        equations=[
            {"variables":[1,2],"rhs":1},
            {"variables":[2,3],"rhs":0},
            {"variables":[3,4],"rhs":1},
            {"variables":[4,5],"rhs":0},
        ]
        result=closure(equations,budget_s=1)
        derivations=result["consequences"]
        self.assertTrue(all(audit_provenance(equations,c) for c in derivations))
        wanted=[c for c in derivations if c["variables"]==[1,5]]
        self.assertTrue(wanted)
        self.assertEqual(wanted[0]["rhs"],0)

    def test_renamed_variables_same_mathematics(self):
        def derive(offset):
            eq=[{"variables":[offset+1,offset+2],"rhs":1},
                {"variables":[offset+2,offset+3],"rhs":0}]
            result=closure(eq,budget_s=1)
            self.assertTrue(all(audit_provenance(eq,c)
                                for c in result["consequences"]))
            return {(tuple(v-offset for v in c["variables"]),c["rhs"])
                    for c in result["consequences"]}
        self.assertEqual(derive(0),derive(100))

    def test_invalid_provenance_rejected(self):
        eq=[{"variables":[1,2],"rhs":0}]
        self.assertFalse(audit_provenance(eq,{
            "variables":[1,2],"rhs":1,"source_equations":[0]}))
        self.assertFalse(audit_provenance(eq,{
            "variables":[1,2],"rhs":0,"source_equations":[0,0]}))

    def test_bounded_truncation_remains_sound(self):
        eq=[{"variables":[i,i+1],"rhs":i%2} for i in range(1,40)]
        result=closure(eq,max_rows=5,max_steps=3,budget_s=1)
        self.assertTrue(result["truncated"])
        self.assertTrue(all(audit_provenance(eq,c)
                            for c in result["consequences"]))

    def test_unit_consequence(self):
        eq=[{"variables":[1,2],"rhs":1},
            {"variables":[2],"rhs":0}]
        result=closure(eq,budget_s=1)
        self.assertTrue(any(x["kind"]=="unit" and x["variables"]==[1] and
                            x["rhs"]==1 for x in result["consequences"]))

    def test_zero_row_no_false_conflict(self):
        eq=[{"variables":[1,2],"rhs":0},
            {"variables":[1,2],"rhs":0}]
        self.assertFalse(any(x["kind"]=="conflict" for x in
                             closure(eq,budget_s=1)["consequences"]))


if __name__=="__main__":
    unittest.main()
