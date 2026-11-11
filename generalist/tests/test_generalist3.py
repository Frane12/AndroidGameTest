import hashlib
import tempfile
from pathlib import Path
import unittest
from generalist.generalist3 import fingerprint,learn,choose,BASE

class TestGeneralist3(unittest.TestCase):
 def test_fingerprint_and_no_name_leakage(self):
  with tempfile.TemporaryDirectory() as t:
   a=Path(t)/"crypto.cnf"; b=Path(t)/"random.cnf"
   a.write_text("c anything\\np cnf 3 3\\n1 -2 0\\n-1 3 0\\n2 3 0\\n")
   b.write_bytes(a.read_bytes())
   self.assertEqual(fingerprint(a),fingerprint(b))
 def test_safe_fallback_and_learning(self):
  rows=[]
  for i in range(10):
   sha=hashlib.sha256(str(i).encode()).hexdigest()
   for arm,score in (("A36_75",10.0),("A39_PROTECT",5.0),("A40_TREE",12.0)):
    rows.append({"sha256":sha,"feature_key":"d1_l1_b2_u0_h0",
     "arm":arm,"verified_par2_s":score,"cap_s":60,
     "original_verified":True})
  m=learn(rows)
  self.assertEqual(m["d1_l1_b2_u0_h0"]["arm"],"A39_PROTECT")
  self.assertEqual(choose({"key":"unknown"},m),BASE)
  self.assertEqual(learn(rows[:21])["d1_l1_b2_u0_h0"]["arm"],BASE)
 def test_no_unverified(self):
  with self.assertRaises(ValueError):
   learn([{"sha256":"a"*64,"feature_key":"any","arm":BASE,
           "original_verified":False,"cap_s":60,"verified_par2_s":1}])

if __name__=="__main__":unittest.main()
