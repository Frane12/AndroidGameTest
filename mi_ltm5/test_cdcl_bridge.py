import unittest
from mi_ltm5.cdcl_bridge import derived_clauses
def xor(v,rhs):
 return [tuple(-x if mask>>i&1 else x for i,x in enumerate(v))
         for mask in range(1<<len(v)) if mask.bit_count()%2!=rhs]
class BridgeTests(unittest.TestCase):
 def test_provenance_and_derived_binary(self):
  a,st=derived_clauses(xor((1,2,3),0)+xor((2,3,4),1))
  self.assertEqual(set(a),{(-4,-1),(1,4)})
  self.assertEqual(st["proof_checked"],1)
 def test_no_incomplete_xor(self):
  a,st=derived_clauses(xor((1,2,3),0)[:-1]+xor((2,3,4),1))
  self.assertEqual(a,[])
 def test_no_fake_global_unit(self):
  a,st=derived_clauses(xor((1,2,3),0))
  self.assertEqual(a,[])
if __name__=="__main__":unittest.main()
