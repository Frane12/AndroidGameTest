import tempfile
import unittest
from pathlib import Path

from bench_formulas import dimacs, xor_cnf
from relational_memory import (init, remember, trained_catalog,
                               diagnose_holdout, forbidden_sha_check,
                               extract_patterns)
import sqlite3


class RelationalMemoryTests(unittest.TestCase):
    def test_placeholder_is_variable_renaming_invariant(self):
        def build(vs):
            a,b,c,d=vs
            return dimacs(xor_cnf([a,b,c],0) + xor_cnf([b,c,d],1),max(vs))
        a=extract_patterns(build([1,2,3,4]))
        b=extract_patterns(build([6,7,8,9]))
        self.assertEqual(a,b)
        self.assertIn("pair:3:3:shared2:out2:rhs1",a)

    def test_incomplete_xor_not_remembered(self):
        clauses=xor_cnf([1,2,3],0)
        self.assertEqual(extract_patterns(dimacs(clauses[:-1],3)),{})

    def test_train_memory_recall_without_holdout_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            con=sqlite3.connect(str(Path(td)/"relational.sqlite"))
            init(con)
            text=dimacs(xor_cnf([1,2],0)+xor_cnf([2,3],1),3)
            remember(con,"TRAIN_HASH",text)
            before=con.execute("SELECT count(*) FROM xor_templates").fetchone()[0]
            catalog=trained_catalog(con,excluded_sha=("HOLDOUT_HASH",))
            match=diagnose_holdout(
                [{"family":"test","raw":text,"sha":"HOLDOUT_HASH"}],catalog)
            self.assertEqual(match["holdout_recognized"],1)
            self.assertEqual(
                before,con.execute("SELECT count(*) FROM xor_templates").fetchone()[0])
            forbidden_sha_check(con,"HOLDOUT_HASH")
            con.close()

if __name__ == "__main__":
    unittest.main()
