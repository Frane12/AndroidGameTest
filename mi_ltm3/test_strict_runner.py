import os
import tempfile
import unittest
from pathlib import Path

from strict_runner import run_strict


class StrictWallRunnerTests(unittest.TestCase):
    def make_program(self, directory, body):
        path=Path(directory)/"mock_solver"
        path.write_text("#!/usr/bin/env python3\n"+body+"\n")
        path.chmod(0o755)
        return path

    def test_budget_exhausted_never_launches(self):
        rc,output,elapsed,status=run_strict(
            Path("/nonexistent"),Path("/nonexistent"),0,0)
        self.assertEqual(rc,0)
        self.assertEqual(status,"budget_exhausted")

    def test_timeout_does_not_fake_result(self):
        with tempfile.TemporaryDirectory() as td:
            prog=self.make_program(td,"import time\ntime.sleep(0.3)")
            rc,output,elapsed,status=run_strict(
                prog,Path(td)/"x.cnf",1,.04)
            self.assertEqual(rc,0)
            self.assertEqual(output,"")
            self.assertIn(status,("wall_timeout","wall_budget_overrun"))

    def test_valid_sat_return_code(self):
        with tempfile.TemporaryDirectory() as td:
            prog=self.make_program(
                td,"import sys\nprint('s SATISFIABLE')\nsys.exit(10)")
            rc,output,elapsed,status=run_strict(
                prog,Path(td)/"x.cnf",1,2.0)
            self.assertEqual(rc,10)
            self.assertEqual(status,"finished")
            self.assertIn("SATISFIABLE",output)


if __name__=="__main__":
    unittest.main()
