#!/usr/bin/env python3
"""Offline guards: new-2025 cohort, learnable rule, proof-safe gate."""
import gzip
import json
import lzma
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"research"))
import drnas_global_material2025 as D
import drnas_global_router_v2 as R


def html_page(status="unknown"):
    headers=("hash","isohash","family","author","result",
             "proceedings","minisat1m","isohash2","filename","track")
    html="<table><tr>"+"".join("<th>"+h+"</th>" for h in headers)+"</tr>"
    for i in range(40):
        vals=["%032x"%i, "","family_%02d"%(i%20),"team",
              status,"","unknown","","case_%02d.cnf.xz"%i,
              "main_2025,submissions_2025"]
        html+="<tr>"+"".join("<td><span>"+v+"</span></td>" for v in vals)+"</tr>"
    html+="<tr>"+"".join("<td>"+v+"</td>" for v in
         ["a"*32,"","historic","team","sat","","","","historic.cnf.xz",
          "main_2025,submissions_2024"])+"</tr></table>"
    return html


class CohortTest(unittest.TestCase):
    def test_new_2025_selection_independent_of_answer(self):
        a=D.select_entries(html_page("sat"),30)
        b=D.select_entries(html_page("unsat"),30)
        self.assertEqual([(x["hash"],x["family"]) for x in a],
                         [(x["hash"],x["family"]) for x in b])
        self.assertEqual(len(a),30)
        self.assertTrue(all("submissions_2025" in x["track"] for x in a))
        self.assertGreaterEqual(len({x["family"] for x in a}),10)

    def test_compression_and_cap(self):
        raw=b"c comment\np cnf 1 1\n1 0\n"
        self.assertEqual(D.bounded_decompress(lzma.compress(raw)),raw)
        self.assertEqual(D.bounded_decompress(gzip.compress(raw)),raw)

    def test_fail_closed_small_index(self):
        with self.assertRaises(RuntimeError):
            D.select_entries("<table><tr><td>missing</td></tr></table>",24)


class RouterTest(unittest.TestCase):
    def test_region_and_safe_default(self):
        s={k:1. for k in R.M.FEATURES}
        rule=R.region([("binary",.5,True),("width",1.5,True)])
        self.assertEqual(R.decide(rule,s),"X5")
        s["binary"]=.3
        self.assertEqual(R.decide(rule,s),"X5_NO_MIN")
        self.assertEqual(R.decide(None,s),"X5")
        with self.assertRaises(ValueError):
            R.decide({"kind":"region","predicates":[],"fallback":"X5","target":"X5_NO_MIN"},s)

    def test_fit_learns_with_support_not_family_labels(self):
        samples=[]
        for i in range(50):
            feat={k:float(i) for k in R.M.FEATURES}
            feat["binary"]=.01 if i<20 else .85
            samples.append({"sha":"%064x"%i,"family":"family_%d"%i,
                            "features":feat,"gain":.28 if i<20 else -.25})
        rule,score=R.fit_rule(samples)
        self.assertIsNotNone(rule)
        self.assertGreater(score,0)
        self.assertEqual(R.decide(rule,samples[0]["features"]),"X5_NO_MIN")
        self.assertEqual(R.decide(rule,samples[-1]["features"]),"X5")

    def test_model_cannot_promote(self):
        model={"protocol":R.PROTOCOL,"promoted":False,"baseline":"X5",
               "train_only":True,"proposed_rule":None}
        R.validate_model(model)
        model["promoted"]=True
        with self.assertRaises(AssertionError):
            R.validate_model(model)

    def test_bootstrap_pairs_by_family(self):
        rows=[]
        for f in range(15):
            for a,t in [("X5",6.0),("GLOBAL_V2",5.0)]:
                rows.append({"family":str(f),"arm":a,"PAR2":t})
        r=R.bootstrap(rows,"GLOBAL_V2",reps=200)
        self.assertAlmostEqual(r["reduction"],1/6)
        self.assertEqual(r["family_units"],15)


if __name__=="__main__":
    unittest.main()
