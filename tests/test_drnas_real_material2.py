import argparse, copy, hashlib, json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
import drnas_real_material2 as M
import drnas_real_train2 as T

class MaterialSafety(unittest.TestCase):
    def test_format_and_order_not_new_sources(self):
        a=M.parse(b'c first\np cnf 2 2\n1 -2 0\n2 0\n')
        b=M.parse(b'p cnf 5 3\n2 0\n-2 1 1 0\n2 0\n')
        self.assertEqual(a[3],b[3])
    def test_invalid_dimacs_rejected(self):
        for raw in (b'p cnf 1 1\n2 0\n',b'p cnf 1 2\n1 0\n',b'p cnf 1 1\n1',b'1 0\n',b'p cnf -1 0\n'):
            with self.assertRaises(ValueError): M.parse(raw)
    def test_empty_formula_and_empty_clause(self):
        self.assertNotEqual(M.parse(b'p cnf 0 0\n')[3],M.parse(b'p cnf 0 1\n0\n')[3])
    def test_archive_family_aliases(self):
        self.assertEqual(M.family('chip12-sc2014.cnf.xz'),M.family('chip31.cnf.xz'))
        self.assertEqual(M.family('device12-sat.cnf'),M.family('device20-unsat.cnf'))
    def test_family_split_stable(self):
        for i in range(100):
            f=M.family(f'circuit{i}.cnf.xz')
            self.assertEqual(M.split_for(f),M.split_for(M.family('circuit999-sc2024.cnf.xz')))
    def test_bounded_features_not_filename_labels(self):
        x=M.features(b'c unsat claim ignored\np cnf 3 3\n1 0\n1 -2 0\n-1 -2 3 0\n')
        self.assertEqual(x['horn'],1);self.assertEqual(x['binary'],1/3);self.assertEqual(x['width'],2)
        self.assertEqual(set(x),set(M.FEATURES))
    def test_witness_checker(self):
        self.assertTrue(T.witness([(1,-2),(3,)],'s SATISFIABLE\nv 1 3 0\n',3))
        self.assertFalse(T.witness([(1,)],'v -1 0\n',1))
        self.assertFalse(T.witness([(1,)],'v 1 -1 0\n',1))
        self.assertFalse(T.witness([()], 'v 1 0\n',1))
    def test_safe_fallback(self):
        self.assertEqual(T.choose(None,{}),'X5_NO_MIN')
        r={'kind':'threshold','arm':'CORE','feature':'density','threshold':3,'below':True}
        self.assertEqual(T.choose(r,{'density':2}),'CORE')
        self.assertEqual(T.choose(r,{'density':4}),'X5_NO_MIN')
    def rows(self, costs, solved):
        rows=[]
        for arm,c in zip(T.ARMS,costs):
            for rep in range(3):
                rows.append({'sha256':'s','arm':arm,'rep':rep,'PAR2':c,'accepted':arm in solved,
                             'features':dict.fromkeys(M.FEATURES,0),'family':'f'})
        return rows
    def test_all_timeouts_have_no_label(self):
        data,q=T.samples(self.rows([6,6,6],set()))
        self.assertEqual(data,[]);self.assertEqual(q['informative_sources'],0)
    def test_jitter_not_actionable(self):
        data,q=T.samples(self.rows([.004,.0038,.0042],set(T.ARMS)))
        self.assertEqual(q['informative_sources'],1);self.assertEqual(q['actionable_sources'],0)
    def test_verified_vs_censored_is_bound_not_exact_runtime(self):
        data,q=T.samples(self.rows([6,.1,6],{'CORE'}))
        self.assertEqual(q['informative_sources'],1)
        self.assertEqual(q['complete_three_arm_sources'],0)
        self.assertGreater(data[0]['gain']['CORE'],0)
    def test_repeat_counts_are_not_independent(self):
        rows=[]
        for f in ('a','b'):
            for rep in range(3):
                for arm,cost in ((T.BASE,2),('LEARNED',1)):
                    rows.append({'family':f,'arm':arm,'PAR2':cost})
        ci=T.interval(rows,draws=100)
        self.assertEqual(ci['family_units'],2);self.assertEqual(ci['reduction'],.5)
    def test_fit_does_not_invent_rule_without_support(self):
        self.assertEqual(T.fit_rule([]),(None,0.))
        data=[{'family':'same','features':dict.fromkeys(M.FEATURES,1),'gain':{T.BASE:0,'CORE':.5,'X5':0}} for _ in range(100)]
        self.assertIsNone(T.fit_rule(data)[0])
    def test_incomplete_trials_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);material=root/'material';material.mkdir();shard=root/'results';shard.mkdir()
            M.save(material/'manifest.json',{'sources':[{'sha256':'a','split':'train'}]})
            meta={'stage':'train','cpus':1,'protocol':M.PROTOCOL,'sources':['a'],'arms':list(T.ARMS),
                  'repeats':3,'shard':0,'shards':1,'binary_sha':{},'material_sha':M.sha((material/'manifest.json').read_bytes())}
            M.save(shard/'manifest.json',meta)
            (shard/'trials.jsonl').write_text(json.dumps({'sha256':'a','arm':T.BASE,'rep':0,'accepted':False})+'\n')
            with self.assertRaises(AssertionError):T.read_trials(shard,material,'train')

if __name__=='__main__':unittest.main()
