"""Deadline and fail-closed checks; exhaustive equivalence lives in selftest()."""
import os, pathlib, tempfile, time, unittest
from unittest.mock import patch
import drnas_turn1_representation as t

class DeadlineTests(unittest.TestCase):
    def setup_case(self,d):
        root=pathlib.Path(d)/'turn'; source=root/'sources'; source.mkdir(parents=True)
        p=source/'toy.cnf';t.write_cnf(p,2,[[1]])
        return root,source,dict(id='toy',sha256=t.sha(p))
    def test_deadline_kills_descendant(self):
        with tempfile.TemporaryDirectory() as d:
            root,source,case=self.setup_case(d); marker=pathlib.Path(d)/'escaped'
            fake=pathlib.Path(d)/'slow-solver'
            fake.write_text('#!/usr/bin/env python3\nimport subprocess,sys,time\nsubprocess.Popen([sys.executable,"-c",'+repr('import time,pathlib;time.sleep(.6);pathlib.Path('+repr(str(marker))+').touch()')+'])\ntime.sleep(20)\n')
            fake.chmod(0o755)
            with patch.object(t,'ROOT',root),patch.object(t,'SOURCE',source),patch.object(t,'CAP',.15),patch.dict(os.environ,{'TURN1_KISSAT':str(fake)}):
                start=time.perf_counter();row=t.trial(case,'kissat_plain',0,0)
            self.assertEqual(row['status'],'TIMEOUT'); self.assertAlmostEqual(row['par2_s'],.3)
            self.assertLess(time.perf_counter()-start,.8)
            time.sleep(.8);self.assertFalse(marker.exists(),'solver descendant escaped deadline')
    def test_worker_error_is_not_timeout(self):
        with tempfile.TemporaryDirectory() as d:
            root,source,case=self.setup_case(d)
            with patch.object(t,'ROOT',root),patch.object(t,'SOURCE',source),patch.dict(os.environ,{'TURN1_KISSAT':'/does/not/exist'}):
                with self.assertRaisesRegex(RuntimeError,'worker failed'):t.trial(case,'kissat_plain',0,0)

if __name__=='__main__': unittest.main()
