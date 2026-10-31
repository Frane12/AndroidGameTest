"""New 2026-10-31 v9.3 SAT encodings; none was in earlier DRNAS SAT generator families."""
import itertools

class CNF:
    def __init__(self,n=0):
        self.n=n
        self.rows=[]
    def fresh(self):
        self.n+=1
        return self.n
    def clause(self,*lits):
        assert all(isinstance(z,int) and z!=0 for z in lits)
        self.rows.append(list(lits))
    def at_most_one(self,vs):
        for i,j in itertools.combinations(vs,2):
            self.clause(-i,-j)
    def exactly_one(self,vs):
        assert vs
        self.clause(*vs)
        self.at_most_one(vs)
    def and2(self,a,b):
        if a is None or b is None:return None
        z=self.fresh()
        self.clause(-a,-b,z)
        self.clause(a,-z)
        self.clause(b,-z)
        return z
    def or2(self,a,b):
        if a is None:return b
        if b is None:return a
        z=self.fresh()
        self.clause(a,b,-z)
        self.clause(-a,z)
        self.clause(-b,z)
        return z
    def xor2(self,a,b):
        if a is None:return b
        if b is None:return a
        z=self.fresh()
        self.clause(-a,-b,-z)
        self.clause(-a,b,z)
        self.clause(a,-b,z)
        self.clause(a,b,-z)
        return z

def queens(n,rng):
    c=CNF(n*n)
    V=lambda r,j:r*n+j+1
    for r in range(n):c.exactly_one([V(r,j) for j in range(n)])
    for j in range(n):c.at_most_one([V(r,j) for r in range(n)])
    for d in range(-n+1,n):
        c.at_most_one([V(r,j) for r in range(n) for j in range(n) if r-j==d])
    for d in range(2*n-1):
        c.at_most_one([V(r,j) for r in range(n) for j in range(n) if r+j==d])
    return c.n,c.rows,"SAT-by-N-queens-existence"

def planted_clique(n,rng):
    k=max(4,round(n*.20))
    planted=set(rng.sample(range(n),k))
    edges=set()
    for u,v in itertools.combinations(range(n),2):
        if (u in planted and v in planted) or rng.random()<.32:
            edges.add((u,v))
    c=CNF(k*n)
    at=lambda slot,v:slot*n+v+1
    for slot in range(k):c.exactly_one([at(slot,v) for v in range(n)])
    for v in range(n):c.at_most_one([at(slot,v) for slot in range(k)])
    for u,v in itertools.combinations(range(n),2):
        if (u,v) in edges:continue
        for slot in range(k):
            for other in range(slot+1,k):
                c.clause(-at(slot,u),-at(other,v))
                c.clause(-at(slot,v),-at(other,u))
    return c.n,c.rows,"SAT-by-planted-clique"

def latin_square(n,rng):
    c=CNF(n**3)
    cell=lambda r,col,val:((r*n+col)*n+val+1)
    for r in range(n):
        for col in range(n):
            c.exactly_one([cell(r,col,v) for v in range(n)])
    for r in range(n):
        for v in range(n):
            c.at_most_one([cell(r,col,v) for col in range(n)])
    for col in range(n):
        for v in range(n):
            c.at_most_one([cell(r,col,v) for r in range(n)])
    rows=list(range(n));cols=list(range(n));syms=list(range(n))
    rng.shuffle(rows);rng.shuffle(cols);rng.shuffle(syms)
    cells=list(itertools.product(range(n),repeat=2))
    rng.shuffle(cells)
    for r,col in cells[:max(n,round(n*n*.23))]:
        c.clause(cell(r,col,syms[(rows[r]+cols[col])%n]))
    return c.n,c.rows,"SAT-by-Latin-construction"

def subset_sum(n,rng):
    c=CNF(n)
    xs=list(range(1,n+1))
    weights=[rng.randrange(1,1<<(n-1)) for _ in xs]
    chosen=[rng.randrange(2) for _ in xs]
    if not any(chosen):chosen[0]=1
    target=sum(w*b for w,b in zip(weights,chosen))
    bits=max(1,sum(weights).bit_length())
    total=[None]*bits
    for x,w in zip(xs,weights):
        carry=None
        for bit in range(bits):
            in_bit=x if ((w>>bit)&1) else None
            left=total[bit]
            p=c.xor2(left,in_bit)
            total[bit]=c.xor2(p,carry)
            carry=c.or2(c.and2(left,in_bit),c.and2(p,carry))
        # With bits = bit_length(sum(weights)), overflow is impossible on\n        # any legitimate selection; constrain symbolic carry to zero.\n        if carry is not None:c.clause(-carry)
    for bit,z in enumerate(total):
        want=(target>>bit)&1
        if z is None:
            assert want==0
        else:
            c.clause(z if want else -z)
    return c.n,c.rows,"SAT-by-subset-sum-witness"

def exact_cover(n,rng):
    universe=3*n
    sets=[set(range(3*i,3*i+3)) for i in range(n)]
    for i in range(5*n):
        k=rng.randint(3,6)
        decoy=set(rng.sample(range(universe),k))
        if decoy not in sets:sets.append(decoy)
    rng.shuffle(sets)
    c=CNF(len(sets))
    for elem in range(universe):
        cover=[i+1 for i,s in enumerate(sets) if elem in s]
        assert cover
        c.exactly_one(cover)
    return c.n,c.rows,"SAT-by-exact-cover-witness"

def circuit_miter(n,rng):
    steps=n*4
    base=CNF(n)
    left=list(range(1,n+1))
    right=list(range(1,n+1))
    for i in range(steps):
        a,b=rng.sample(range(len(left)),2)
        A,B=left[a],left[b]
        C,D=right[a],right[b]
        op=rng.choice(("and","or","xor"))
        if op=="and":
            out_left=base.and2(A,B)
            out_right=-base.or2(-C,-D)
        elif op=="or":
            out_left=base.or2(A,B)
            out_right=-base.and2(-C,-D)
        else:
            out_left=base.xor2(A,B)
            out_right=base.or2(base.and2(C,-D),base.and2(-C,D))
        left.append(out_left)
        right.append(out_right)
    base.clause(left[-1],right[-1])
    base.clause(-left[-1],-right[-1])
    return base.n,base.rows,"UNSAT-by-equivalent-circuits"

GENS={"queens":queens,"planted_clique":planted_clique,
      "latin_square":latin_square,"subset_sum":subset_sum,
      "exact_cover":exact_cover,"circuit_miter":circuit_miter}
