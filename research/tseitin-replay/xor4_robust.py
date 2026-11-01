"""Sound XOR substructure extraction for DIMACS; never infer SAT from XOR alone.
Parity implications survive additional clauses on the same variable support.
UNSAT only when extracted entailed equations contradict over GF(2).
"""
from collections import defaultdict
from itertools import product

def extract(clauses, max_width=4):
    groups=defaultdict(list)
    for i,clause in enumerate(clauses):
        support=tuple(sorted({abs(x) for x in clause}))
        if 1<=len(support)<=max_width and len(support)==len(clause):
            groups[support].append((i,clause))
    equations=[]
    for support,items in groups.items():
        allowed=[]
        for bits in product((False,True),repeat=len(support)):
            env=dict(zip(support,bits))
            if all(any(env[abs(l)]==(l>0) for l in clause) for _,clause in items):
                allowed.append(bits)
        for rhs in (0,1):
            target=[b for b in product((False,True),repeat=len(support)) if sum(b)%2==rhs]
            if allowed and set(allowed).issubset(set(target)):
                equations.append((support,rhs,[i for i,_ in items]))
                break
    return equations

def contradiction(equations):
    basis={}
    for support,rhs,_ in equations:
        mask=sum(1<<(v-1) for v in support)
        while mask:
            pivot=mask.bit_length()-1
            if pivot not in basis:
                basis[pivot]=(mask,rhs)
                break
            m,b=basis[pivot];mask^=m;rhs^=b
        else:
            if rhs:return True
    return False

def certified_unsat(clauses):
    equations=extract(clauses)
    return contradiction(equations),len(equations)
