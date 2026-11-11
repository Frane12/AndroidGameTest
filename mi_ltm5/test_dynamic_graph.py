import unittest
from dynamic_graph import GraphTrajectory,combine,restrict,audit


def xor(v,rhs):
    return [tuple(-x if mask&(1<<i) else x for i,x in enumerate(v))
            for mask in range(1<<len(v)) if mask.bit_count()%2 != rhs]


class DynamicGraphTests(unittest.TestCase):
    def test_pair_is_proved_and_conditional(self):
        x=GraphTrajectory(xor((1,2,3),0)+xor((2,3,4),1))
        self.assertEqual(len(x.sources),2)
        derived=x.derive_pair(0,1)
        self.assertTrue(audit(derived,x.sources))
        self.assertEqual(derived.variables,frozenset([1,4]))
        self.assertEqual(derived.rhs,1)
        conditioned=restrict(derived,{1:True})
        self.assertEqual(conditioned.variables,frozenset([4]))
        self.assertEqual(conditioned.rhs,0)

    def test_decision_propagation_backtracking(self):
        x=GraphTrajectory(xor((1,2,3),0))
        initial=x.events[-1]["state_signature"]
        x.decide(1,True)
        x.propagate(2,False)
        self.assertEqual(x.current()[0]["status"],"unit_candidate")
        self.assertEqual(x.current()[0]["rhs"],1)
        x.backtrack(0)
        self.assertEqual(x.events[-1]["state_signature"],initial)
        self.assertEqual(x.assignments,{})
        self.assertEqual(x.level,0)

    def test_conflict_is_conditional_not_formula_unsat(self):
        x=GraphTrajectory(xor((1,2,3),0))
        x.decide(1,True)
        x.propagate(2,False)
        x.propagate(3,False)
        self.assertEqual(x.current()[0]["status"],"conflict")
        x.backtrack(0)
        self.assertNotEqual(x.current()[0]["status"],"conflict")

    def test_two_renamed_graphs_share_trajectory_class(self):
        a=GraphTrajectory(xor((1,2,3),0)+xor((2,3,4),1))
        b=GraphTrajectory(xor((101,102,103),0)+xor((102,103,104),1))
        a.decide(1,True)
        b.decide(101,True)
        a.propagate(2,False)
        b.propagate(102,False)
        a.backtrack(0)
        b.backtrack(0)
        self.assertEqual(a.initial_signature,b.initial_signature)
        self.assertEqual(a.trajectory_key(),b.trajectory_key())
        self.assertEqual(a.transition_histogram(),b.transition_histogram())

    def test_incomplete_source_cannot_be_inferred(self):
        x=GraphTrajectory(xor((1,2,3),0)[:-1])
        self.assertEqual(x.sources,[])
        self.assertEqual(x.current(),[])

    def test_source_proof_tampering_fails(self):
        x=GraphTrajectory(xor((1,2,3),0)+xor((2,3,4),1))
        row=x.derive_pair(0,1)
        wrong=type(row)(row.variables,row.rhs^1,row.provenance)
        self.assertFalse(audit(wrong,x.sources))

    def test_invalid_backtrack_and_duplicate_decision(self):
        x=GraphTrajectory(xor((1,2),0))
        x.decide(1,True)
        with self.assertRaises(ValueError):
            x.decide(1,False)
        with self.assertRaises(ValueError):
            x.backtrack(1)


if __name__=="__main__":
    unittest.main()
