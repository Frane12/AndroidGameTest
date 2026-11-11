import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from itertools import product
from mi_ltm5.cdcl_bridge import derived_clauses, write_derived
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

 def test_derived_cnf_equisatisfiable_and_source_unchanged(self):
  source=xor((1,2,3),0)+xor((2,3,4),1)
  original=("p cnf 4 %d\\n"%len(source)+"".join(" ".join(map(str,c))+" 0\\n" for c in source))
  with TemporaryDirectory() as folder:
   inp=Path(folder)/"original.cnf"
   out=Path(folder)/"reduced.cnf"
   inp.write_text(original)
   stats=write_derived(inp,out)
   self.assertEqual(inp.read_text(),original)
   self.assertEqual(stats["added"],2)
   lines=out.read_text().splitlines()
   self.assertEqual(lines[0],"p cnf 4 10")
   clauses=[tuple(int(x) for x in line.split()[:-1]) for line in lines[1:]]
   for bits in product((False,True),repeat=4):
    model={v+1:bits[v] for v in range(4)}
    sat=lambda cs:all(any(model[abs(l)]==(l>0) for l in c) for c in cs)
    self.assertEqual(sat(source),sat(clauses))
if __name__=="__main__":unittest.main()
