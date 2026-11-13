#!/usr/bin/env python3
"""Regression for interrupted telemetry writes and whole-pair recovery."""
import copy,json,os,signal,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
from drnas_x5_family15 import ARMS,parse_diagnostic_stderr,retained_pairs

EVENT={'elapsed_s':1.0,'conflicts':123,'decisions':234,'propagations':567}
LINE='X5_PROGRESS '+json.dumps(EVENT)+'\n'
class Recovery(unittest.TestCase):
    def test_every_cut(self):
        for tag in ('X5_PROGRESS ','X41_STATS ','X5_STATS '):
            line=tag+json.dumps(EVENT)+'\n'
            for cut in range(1,len(line)):
                tail=line[:cut]
                events,stats,extra,audit=parse_diagnostic_stderr(LINE+tail,True)
                self.assertEqual(events[0],EVENT)
                if cut<len(line)-1:self.assertEqual(len(audit),1,(tag,cut))
                else:self.assertFalse(audit)
        self.assertEqual(parse_diagnostic_stderr(LINE,False)[0],[EVENT])
    def test_corruption_stays_fatal(self):
        for text,killed in [(LINE+'X5_PROGRESS {"x":',False),
                            (LINE+'X5_PROGRESS {"x":\n',True),
                            ('X5_PROGRESS {"x":\n'+LINE,True)]:
            with self.assertRaises(json.JSONDecodeError):parse_diagnostic_stderr(text,killed)
        with self.assertRaises(AssertionError):parse_diagnostic_stderr('X5_PROGRESS {',True)
    def test_real_process_killed_mid_write(self):
        code='import sys,time;sys.stderr.write('+repr(LINE+'X5_PROGRESS {"elapsed_s":')+');sys.stderr.flush();print("ready",flush=True);time.sleep(10)'
        p=subprocess.Popen([sys.executable,'-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        self.assertEqual(p.stdout.readline().strip(),'ready')
        with self.assertRaises(subprocess.TimeoutExpired):p.communicate(timeout=.03)
        os.killpg(p.pid,signal.SIGKILL);_,stderr=p.communicate()
        events,_,_,audit=parse_diagnostic_stderr(stderr,True)
        self.assertEqual(events,[EVENT]);self.assertEqual(len(audit),1)
    def test_retain_only_complete_pairs_with_matching_identity(self):
        m=dict(cohort='test',family='test',count=15,repeats=2,cap=15,arms=ARMS,shard=0,shards=5,
               source_manifest_sha256='source',candidate_sha256='candidate',diagnostic_source_sha256='diag',
               binary_sha256={'binary':'hash'},sources=[{'sha256':'abc','source_id':0}])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'manifest.json').write_text(json.dumps(m));(root/'telemetry').mkdir()
            (root/'telemetry/abc_0.jsonl').write_text(json.dumps(EVENT)+'\n')
            rows=[dict(sha256='abc',source_id=0,rep=0,arm=arm,family='test',shard=0,
                       accepted=False,verified=False,e2e_s=15.01,progress_samples=1,last_progress=EVENT) for arm in ARMS]
            rows += [{**rows[0],'rep':1}]
            path=root/'trials.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            keep,audit=retained_pairs(root,m)
            self.assertEqual(len(keep),6);self.assertEqual(audit['partial_group_trials_not_mixed'],1)
            self.assertTrue(all(r['retained_from_prior_run'] for r in keep))
            for key in ('cap','candidate_sha256','binary_sha256','sources'):
                changed=copy.deepcopy(m);changed[key]='changed'
                with self.assertRaises(AssertionError):retained_pairs(root,changed)
            path.write_text(path.read_text()+json.dumps(rows[0])+'\n')
            with self.assertRaises(AssertionError):retained_pairs(root,m)
if __name__=='__main__':unittest.main()
