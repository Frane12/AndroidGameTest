import unittest
from probe import parse_dimacs,detect_xor,probe_cnf

def encode_xor(variables,rhs):
    clauses=[]
    for mask in range(1<<len(variables)):
        if mask.bit_count()%2 != rhs:
            clauses.append(tuple(-v if mask & (1<<i) else v
                                 for i,v in enumerate(variables)))
    return clauses

def dimacs(clauses):
    n=max((abs(x) for c in clauses for x in c),default=0)
    return "p cnf %d %d\n"%(n,len(clauses))+"".join(
        " ".join(str(x) for x in c)+" 0\n" for c in clauses)

class TestProbe(unittest.TestCase):
    def test_exact_detection_and_relational_equality(self):
        clauses=encode_xor([1,2,3],0)+encode_xor([2,3,4],0)
        report=probe_cnf(dimacs(clauses))
        self.assertEqual(len(report["xor_equations"]),2)
        self.assertTrue(any(x["kind"]=="binary_xor" and
                            x["variables"]==[1,4] and x["rhs"]==0
                            for x in report["consequences"]))

    def test_incomplete_pattern_must_not_be_claimed(self):
        clauses=encode_xor([1,2,3],0)[:-1]
        self.assertEqual(detect_xor(clauses),[])

    def test_rhs_one(self):
        clauses=encode_xor([1,2],1)
        self.assertEqual(detect_xor(clauses),[((1,2),1)])

    def test_conflicting_equations(self):
        clauses=encode_xor([1,2],0)+encode_xor([1,2],1)
        report=probe_cnf(dimacs(clauses))
        self.assertTrue(any(x["kind"]=="conflict" for x in report["consequences"]))

    def test_negative_control(self):
        clauses=[(1,2),(-1,3),(2,-3)]
        self.assertEqual(probe_cnf(dimacs(clauses))["xor_equations"],[])

    def test_budget_abstention(self):
        report=probe_cnf(dimacs([(1,),(2,)]),max_clauses=1)
        self.assertEqual(report["status"],"abstain")

    def test_header_rejects_malformed(self):
        with self.assertRaises(ValueError):
            parse_dimacs("p cnf 2 2\n1 0\n")

if __name__=="__main__":
    unittest.main()
