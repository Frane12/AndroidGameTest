#!/usr/bin/env python3
"""R158 targeted fail-closed tests, including provenance and test leakage."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import r158_features as f
import r158_experiment as e

ROOT=Path(__file__).resolve().parent.parent

class R158Tests(unittest.TestCase):
    def test_entropy(self):
        self.assertAlmostEqual(f.entropy([1,1,1,1]),1)
        self.assertEqual(f.entropy([1,0,0,0]),0)
        self.assertEqual(f.entropy([0,0]),0)
        with self.assertRaises(FileNotFoundError):f.parse_dimacs(Path('/definitely/missing.cnf'))

    def test_prefix_strict_1024(self):
        points=[]
        for c in (32,64,96,128,192,256,384,512,768,1024,1536):
            points.append(dict(conflict=str(c),propagations=str(c*11),
                               restarts='0',glue='1.00' if c<=1024 else '500'))
        before=f.prefix(dict(points=points[:10]))
        after=f.prefix(dict(points=points))
        self.assertEqual(before,after,'post-decision data must never affect features')
        self.assertIsNone(f.prefix(dict(points=points[:8])))

    def test_graph_features_with_hand_cnf(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'small.cnf'
            path.write_text('p cnf 5 3\n1 -2 3 0\n-2 4 0\n3 5 0\n')
            graph=f.parse_dimacs(path)
            self.assertEqual(len(graph),5)
            feats=f.static_features(graph)
            self.assertIn('graph_modularity',feats)
            self.assertTrue(0<=feats['graph_degree_entropy']<=1)
            self.assertEqual(feats,f.static_features(graph))
            path.write_text('p cnf 5 3\n1 -2 3 0\n')
            with self.assertRaises(ValueError):f.parse_dimacs(path)

    def test_real_shards_and_training_leakage(self):
        aggregate=Path(os.environ.get('R158_AGGREGATE',str(ROOT/'aggregate')))
        raw=Path(os.environ.get('R158_RAW',str(ROOT/'raw')))
        if not aggregate.is_dir() or not raw.is_dir():self.skipTest('download R17 pinned data')
        report,features,hashes,cost=e.verify_extract(aggregate,raw)
        self.assertEqual(len(features),160)
        self.assertEqual(len(hashes),208)
        self.assertEqual(len(cost),160)
        self.assertEqual(sum(bool(x['graph_box_valid']) for x in features),0)
        self.assertTrue(all(x['source_class']=='generated_R17_reused_not_official' for x in features))
        a=e.fit_models(features)
        forged=copy.deepcopy(features)
        for r in forged:
            if r['fold'].endswith('_test'):
                r['monitor']='987654'
                r['r17_guarded50']='0.1'
        self.assertEqual(a,e.fit_models(forged))
        self.assertTrue(all(not x['promotion_allowed'] for x in a.values()))
        with self.assertRaises(RuntimeError):e.fit(features,'graph_modularity')

if __name__=='__main__':unittest.main(verbosity=2)