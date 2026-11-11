import unittest
from xor_templates import normalize, eliminate_pair, derive_bounded, classify_consequence, pattern_key

class XORTemplates(unittest.TestCase):
    def test_placeholder_equality(self):
        # A xor B = C => A xor B xor C = 0
        # B xor C = D => B xor C xor D = 0
        e1=normalize([1,2,3],0)
        e2=normalize([2,3,4],0)
        result=eliminate_pair(e1,e2)
        self.assertEqual(result,normalize([1,4],0))
        self.assertEqual(classify_consequence(result)[0],"binary_xor")
        self.assertEqual(pattern_key(([1,2,3],0),([2,3,4],0)),
                         pattern_key(([10,20,30],0),([20,30,40],0)))

    def test_conflict(self):
        rows=derive_bounded([([1,2],0),([1,2],1)])
        self.assertTrue(any(classify_consequence(row)[0]=="conflict"
                            for row,_ in rows))

    def test_unit(self):
        rows=derive_bounded([([1,2],0),([2],1)])
        self.assertTrue(any(classify_consequence(row)==("unit",(1,1))
                            for row,_ in rows))

    def test_duplicate_cancellation(self):
        self.assertEqual(normalize([1,1,2],1),normalize([2],1))

if __name__=="__main__":
    unittest.main()
