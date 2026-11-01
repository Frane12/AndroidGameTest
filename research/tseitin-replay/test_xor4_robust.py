import itertools,random,unittest
from xor4_robust import certified_unsat

def xor_block(variables,rhs):
    result=[]
    for bits in itertools.product((0,1),repeat=len(variables)):
        if sum(bits)%2!=rhs:
            result.append(tuple(-v if bit else v for v,bit in zip(variables,bits)))
    return result

class Tests(unittest.TestCase):
    def test_contradiction(self):
        cnf=xor_block((1,2,3,4),0)+xor_block((1,2,3),0)+xor_block((4,),1)
        self.assertTrue(certified_unsat(cnf)[0])
        cnf.append((1,2,3,4,5))
        self.assertTrue(certified_unsat(cnf)[0])
        random.Random(5).shuffle(cnf)
        self.assertTrue(certified_unsat(cnf)[0])
    def test_sat_not_falsely_unsat(self):
        for seed in range(150):
            rng=random.Random(seed)
            model={v:rng.choice((False,True)) for v in range(1,7)}
            cnf=[]
            for _ in range(30):
                vs=rng.sample(range(1,7),rng.randint(1,4))
                clause=tuple(v if rng.choice((False,True)) else -v for v in vs)
                if any(model[abs(l)]==(l>0) for l in clause):cnf.append(clause)
            self.assertFalse(certified_unsat(cnf)[0],seed)
    def test_incomplete_xor(self):
        cnf=xor_block((1,2,3,4),0)[:-1]+xor_block((1,2,3),0)+xor_block((4,),1)
        self.assertFalse(certified_unsat(cnf)[0])
if __name__=='__main__':unittest.main()
