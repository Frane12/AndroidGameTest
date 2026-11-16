#!/usr/bin/env python3
"""DRNAS TSP-SAT1: exact symmetric integer-EUC TSP -> SAT decision CNF.

One-hot Hamiltonian ORDER, explicit arc equivalences, Tseitin binary addition
for tour cost, and a fully constrained <=B comparator. SAT proves a route <=B;
UNSAT + independently checked DRAT proves absence of routes <=B *for the
encoded CNF*. Grounding of CNF in original TSP needs a trusted encoder, and
is explicitly NOT a formally verified end-to-end TSP proof yet.

Experimental pilot, bounded n<=10; no assertion of polynomial TSP complexity.
"""
import itertools
import json
import math
from pathlib import Path

class CNF:
    def __init__(self):
        self.nvars=0
        self.clauses=[]
        self.ops=[]
        self.TRUE=self.var()
        self.add(self.TRUE)
        self.FALSE=-self.TRUE

    def var(self):
        self.nvars+=1
        return self.nvars

    def add(self,*lits):
        assert all(isinstance(x,int) and x!=0 and abs(x)<=self.nvars for x in lits)
        self.clauses.append(tuple(lits))

    def AND(self,a,b):
        z=self.var()
        self.add(-z,a);self.add(-z,b);self.add(z,-a,-b)
        self.ops.append((z,"and",a,b))
        return z

    def OR(self,a,b):
        z=self.var()
        self.add(z,-a);self.add(z,-b);self.add(-z,a,b)
        self.ops.append((z,"or",a,b))
        return z

    def XOR(self,a,b):
        z=self.var()
        self.add(-a,-b,-z)
        self.add(a,b,-z)
        self.add(a,-b,z)
        self.add(-a,b,z)
        self.ops.append((z,"xor",a,b))
        return z

    def MAJ(self,a,b,c):
        z=self.var()
        self.add(-a,-b,z)
        self.add(-a,-c,z)
        self.add(-b,-c,z)
        self.add(a,b,-z)
        self.add(a,c,-z)
        self.add(b,c,-z)
        self.ops.append((z,"maj",a,b,c))
        return z

    def exactly_one(self,lits):
        self.add(*lits)
        for a,b in itertools.combinations(lits,2):
            self.add(-a,-b)

    def output(self,path):
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("w",encoding="ascii") as fd:
            fd.write("c DRNAS TSP-SAT1 exact permutation, arc AND/OR, binary PB <= bound\n")
            fd.write(f"p cnf {self.nvars} {len(self.clauses)}\n")
            for c in self.clauses:
                fd.write(" ".join(map(str,c))+" 0\n")


def distance(coords):
    n=len(coords)
    assert 4<=n<=10 and len(set(map(tuple,coords)))==n
    return [[0 if i==j else math.isqrt(
        4*((coords[i][0]-coords[j][0])**2+
           (coords[i][1]-coords[j][1])**2)+0) for j in range(n)]
        for i in range(n)]


def euc_distance(coords):
    """Exact TSPLIB EUC_2D round(sqrt(dx²+dy²)), integer arithmetic."""
    n=len(coords)
    D=[[0]*n for _ in range(n)]
    for i in range(n):
        for j in range(i):
            dx=coords[i][0]-coords[j][0]
            dy=coords[i][1]-coords[j][1]
            sq=dx*dx+dy*dy
            lo=math.isqrt(sq)
            # distance rounds to floor(sqrt(sq)+0.5), checked without floats
            w=lo+int(4*sq >= (2*lo+1)**2)
            D[i][j]=D[j][i]=w
    return D


def cost(route,D):
    n=len(route)
    assert len(set(route))==n and set(route)==set(range(n))
    return sum(D[route[i]][route[(i+1)%n]] for i in range(n))


def held_karp(D):
    n=len(D)
    state={(1<<(j-1),j):(D[0][j],(0,j)) for j in range(1,n)}
    for _ in range(2,n):
        later={}
        for (mask,last),(c,path) in state.items():
            for nxt in range(1,n):
                bit=1<<(nxt-1)
                if mask & bit:continue
                key=(mask|bit,nxt)
                candidate=(c+D[last][nxt],path+(nxt,))
                if key not in later or candidate<later[key]:
                    later[key]=candidate
        state=later
    full=(1<<(n-1))-1
    best=min(((value+D[last][0],path)
              for (mask,last),(value,path) in state.items()
              if mask==full),key=lambda x:(x[0],x[1]))
    assert cost(best[1],D)==best[0]
    return best


def encode(coords,bound, *, break_reversal=False):
    n=len(coords)
    D=euc_distance(coords)
    width=max(1,(n*max(max(row) for row in D)).bit_length())
    assert isinstance(bound,int) and 0<=bound<=n*max(max(row) for row in D)
    c=CNF()
    pos=[[c.var() for i in range(n)] for p in range(n)]
    for row in pos:c.exactly_one(row)
    for city in range(n):
        c.exactly_one([pos[p][city] for p in range(n)])
    c.add(pos[0][0]) # remove rotational symmetry
    if break_reversal:
        # Reversing a tour preserves symmetric cost; retain exactly one
        # orientation by requiring the next city to precede the last city.
        for a in range(1,n):
            for b in range(1,a):
                c.add(-pos[1][a],-pos[n-1][b])
    edges={(i,j):c.var() for i in range(n) for j in range(n) if i!=j}
    for i in range(n):
        for j in range(n):
            if i==j:continue
            edge=edges[i,j]
            options=[]
            for p in range(n):
                z=c.AND(pos[p][i],pos[(p+1)%n][j])
                options.append(z)
                c.add(-z,edge)
            c.add(-edge,*options)

    bits=[c.FALSE]*width
    # The permutation activates EXACTLY n distinct directed edges. Thus every
    # partial sum <= n*max_distance, so width never wraps on any legal tour.
    for (i,j),e in sorted(edges.items()):
        weight=D[i][j]
        term=[e if weight&(1<<k) else c.FALSE for k in range(width)]
        carry=c.FALSE
        next_bits=[]
        for a,b in zip(bits,term):
            u=c.XOR(a,b)
            next_bits.append(c.XOR(u,carry))
            carry=c.MAJ(a,b,carry)
        bits=next_bits

    less=c.FALSE
    equal=c.TRUE
    for k in reversed(range(width)):
        if (bound>>k)&1:
            less=c.OR(less,c.AND(equal,-bits[k]))
            equal=c.AND(equal,bits[k])
        else:
            equal=c.AND(equal,-bits[k])
    c.add(less,equal)
    return c,dict(pos=pos,edges=edges,D=D,bound=bound,width=width,n=n,break_reversal=break_reversal)


def eval_lit(lit,assignment):
    value=assignment[abs(lit)]
    return value if lit>0 else not value


def evaluate_tour(cnf,info,tour):
    """Evaluate every auxiliary Tseitin wire from a proposed TSP route.

    For n<=6 preflight, verify all 24/120 tours. This checks both directions
    of the bounded cost encoding for each original tour witness, rather than
    trusting the SAT solver or claimed optimum.
    """
    n=info["n"]
    order=tuple(tour)
    assert len(order)==n and set(order)==set(range(n)) and order[0]==0
    assignment={cnf.TRUE:True}
    for p in range(n):
        for city in range(n):
            assignment[info["pos"][p][city]]=order[p]==city
    selected={(order[p],order[(p+1)%n]) for p in range(n)}
    for edge,v in info["edges"].items():
        assignment[v]=edge in selected
    for output,op,*inputs in cnf.ops:
        a=[eval_lit(x,assignment) for x in inputs]
        assignment[output]={
            "and":lambda: a[0] and a[1],
            "or":lambda: a[0] or a[1],
            "xor":lambda: a[0]!=a[1],
            "maj":lambda: sum(a)>=2
        }[op]()
    assert len(assignment)==cnf.nvars,(len(assignment),cnf.nvars)
    satisfies=all(any(eval_lit(l,assignment) for l in clause)
                  for clause in cnf.clauses)
    predicted=(cost(order,info["D"])<=info["bound"] and
               (not info["break_reversal"] or order[1]<order[-1]))
    assert satisfies==predicted,(
        "CIRCUIT_MISMATCH",order,cost(order,info["D"]),
        info["bound"],satisfies,predicted)
    return satisfies


def parse_model(stdout):
    values={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for token in line[2:].split():
            lit=int(token)
            if not lit:continue
            old=values.get(abs(lit))
            if old is not None and old!=(lit>0):raise ValueError("contradictory model")
            values[abs(lit)]=lit>0
    return values


def verify_cnf_model(cnf_path,model):
    nvars=None
    declared=None
    count=0
    pending=[]
    with Path(cnf_path).open(encoding="ascii") as fd:
        for line in fd:
            tokens=line.split()
            if not tokens or tokens[0]=="c":continue
            if tokens[0]=="p":
                assert len(tokens)==4 and tokens[1]=="cnf" and nvars is None
                nvars,declared=map(int,tokens[2:])
                continue
            for token in tokens:
                lit=int(token)
                if abs(lit)>nvars: return False
                if lit:pending.append(lit)
                else:
                    if not any(model.get(abs(x))==(x>0) for x in pending):
                        return False
                    pending=[]
                    count+=1
    return nvars is not None and not pending and count==declared


def verify_sat(stdout,cnf_path,info):
    model=parse_model(stdout)
    if not model or not verify_cnf_model(cnf_path,model):
        raise ValueError("SAT witness does not satisfy original encoded CNF")
    route=[]
    for row in info["pos"]:
        chosen=[city for city,v in enumerate(row) if model.get(v) is True]
        if len(chosen)!=1:raise ValueError("not one city per tour position")
        route.append(chosen[0])
    if route[0]!=0 or len(set(route))!=len(route):
        raise ValueError("tour lacks one unique visit to each city")
    route_cost=cost(route,info["D"])
    if info["break_reversal"] and route[1]>=route[-1]:
        raise ValueError("SAT tour violates canonical reversal orientation")
    if route_cost>info["bound"]:
        raise ValueError("decoded tour exceeds declared budget")
    return dict(route=route,route_cost=route_cost)


def selftest():
    cases=[
        [[0,0],[2,0],[4,0],[1,3],[4,4]],
        [[0,0],[2,0],[4,0],[1,3],[4,4],[6,2]]
    ]
    trials=0
    for coords in cases:
        D=euc_distance(coords)
        optimum,_=held_karp(D)
        for budget in (optimum-1,optimum,optimum+1):
            for sym in (False,True):
                cnf,info=encode(coords,budget,break_reversal=sym)
                for route in itertools.permutations(range(1,len(coords))):
                    evaluate_tour(cnf,info,(0,)+route)
                    trials+=1
                exists=any(cost((0,)+r,D)<=budget
                           for r in itertools.permutations(range(1,len(coords))))
                exists_canonical=any(cost((0,)+r,D)<=budget and r[0]<r[-1]
                           for r in itertools.permutations(range(1,len(coords))))
                assert exists==exists_canonical, "reversal symmetry lost feasible tour"
    print("TSP_SAT1_ENCODING_SELFTEST_PASS "+json.dumps({
        "enumerated_tour_bound_pairs":trials,
        "independent_held_karp":True,
        "integer_euc_rounding":True,
        "standard_DDIMACS":True,
        "formal_encoder_proof":False},sort_keys=True),flush=True)


if __name__=="__main__":
    selftest()
