#!/usr/bin/env python3
"""V15.8 independent mathematical preflight unit/property validation."""
import importlib.util,itertools,random,sys,time
from pathlib import Path
p=Path("research/tseitin-replay/v158_math_relations.py")
spec=importlib.util.spec_from_file_location("rel",p)
rel=importlib.util.module_from_spec(spec);spec.loader.exec_module(rel)
def xor(vs,rhs):
    return [tuple(-v if mask>>i&1 else v for i,v in enumerate(vs))
            for mask in range(1<<len(vs)) if mask.bit_count()%2!=rhs]
def entails(n,cls,vs,rhs):
    for bits in itertools.product((False,True),repeat=n):
        if all(any(bits[abs(l)-1]==(l>0) for l in c) for c in cls):
            if sum(bits[v-1] for v in vs)%2!=rhs:return False
    return True
tests=0
for seed in range(160):
    rng=random.Random(158_2026_1101+seed)
    n=rng.randrange(3,11);vs=rng.sample(list(range(1,n+1)),rng.randint(2,min(6,n)))
    rhs=rng.randrange(2)
    cls=xor(vs,rhs)
    # Add unrelated clauses that are entailed by clauses in XOR CNF.
    for _ in range(seed%4):
        cl=list(rng.choice(cls));w=rng.randrange(1,n+1)
        if w not in list(map(abs,cl)):cl.append(w if rng.randrange(2) else -w)
        cls.append(tuple(cl))
    rng.shuffle(cls)
    d=rel.relations(n,cls)
    matching=[x for x in d["xor_relations"] if x["vars"]==tuple(sorted(vs))]
    assert matching and matching[0]["rhs"]==rhs,(seed,vs,rhs,d)
    for entry in d["xor_relations"]:
        assert entails(n,cls,entry["vars"],entry["rhs"]),(seed,entry)
    tests+=1
# Hall candidates, NOT certified contradictions.
hall=[(1,2,3),(4,5,6),(7,8,9),(-1,-4),(-2,-5),(-3,-6)]
d=rel.relations(9,hall)
assert d["signals"]["positive_alo"]==3
assert d["signals"]["negative_amo"]==3
assert d["gate"]["hall_check"]
# 2SAT implication graph
d=rel.relations(3,[(-1,2),(-2,3),(1,-3)])
assert d["signals"]["binary_clauses"]==3
assert d["signals"]["implication_edges"]>=6
# Dense unsat XOR complement should not claim SAT/UNSAT, only an exact relation.
cls=xor([1,2,3],0)+xor([1,2,3],1)
d=rel.relations(3,cls)
assert not d["xor_relations"] and d["gate"]["binary_scc"] is False
print("V158_MATH_PREFLIGHT_PASS",tests+3,
      "exhaustive entailment checks, Hall candidate, binary graph, complementary parity")
