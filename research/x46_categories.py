"""Thirty deterministic GENERATED SAT structural profiles; not industrial originals.
Hidden witnesses validate generation only; never passed to solver or controller.
Profiles are grouped into broader domains to avoid calling parameter variants
independent problem domains. SHA uniqueness does not prove non-isomorphism.
"""
from __future__ import annotations
import hashlib, itertools, json, random
from pathlib import Path

# Independent fresh-source replication of the predeclared X4.6 GATE30 protocol.
NAMESPACE = 'x46-gate30-prospective-20261113-v2-independent-replication'
SPECS = [
 ('random3_uniform','random_cnf'), ('random3_balanced','random_cnf'),
 ('random3_dense','random_cnf'), ('random3_polarity','random_cnf'),
 ('modular20','modular_cnf'), ('modular40','modular_cnf'),
 ('hub3','random_cnf'), ('mix3_4','random_cnf'),
 ('planted_xor_mix','mixed_parity'), ('redundant3','random_cnf'),
 ('parity_sparse','parity'), ('parity_chain','parity'), ('parity_grid','parity'),
 ('implication_2sat','tractable'), ('horn','tractable'), ('dual_horn','tractable'),
 ('aig','circuits'), ('xor_and','circuits'), ('mux_network','circuits'),
 ('ripple_adder','arithmetic'), ('multiplier','arithmetic'),
 ('coloring3','graph'), ('coloring4','graph'), ('matching','assignment'),
 ('permutation_assignment','assignment'), ('independent_set','graph'),
 ('vertex_cover','graph'), ('set_cover','cover'), ('exact_cover','cover'),
 ('latin_square','latin'),
]

class CNF:
    def __init__(self, rng):
        self.rng=rng; self.values=[False]; self.clauses=[]
    def var(self, value=None):
        self.values.append(bool(self.rng.getrandbits(1)) if value is None else bool(value))
        return len(self.values)-1
    def val(self, literal):
        return self.values[abs(literal)] == (literal>0)
    def add(self, *lits):
        c=sorted(set(lits), key=lambda x:(abs(x),x))
        if any(-x in c for x in c): return
        if not c or not all(0<abs(x)<len(self.values) for x in c):
            raise ValueError('Empty or out-of-range clause')
        if not any(self.val(x) for x in c):
            raise AssertionError(('Planted witness violated',c))
        self.clauses.append(c)
    def gate(self, inputs, operation):
        out=self.var(operation([self.val(x) for x in inputs]))
        for bits in itertools.product((False,True),repeat=len(inputs)):
            wanted=bool(operation(bits))
            self.add(*[-x if b else x for x,b in zip(inputs,bits)], out if wanted else -out)
        return out
    def xor(self,a,b): return self.gate([a,b],lambda z:z[0]!=z[1])
    def and_(self,a,b): return self.gate([a,b],lambda z:z[0] and z[1])
    def or_(self,a,b): return self.gate([a,b],lambda z:z[0] or z[1])
    def parity(self, vs):
        target=sum(self.val(v) for v in vs)%2
        for bits in itertools.product((0,1),repeat=len(vs)):
            if sum(bits)%2!=target:
                self.add(*[-v if b else v for v,b in zip(vs,bits)])
    def exactly_one(self, vs):
        self.add(*vs)
        for a,b in itertools.combinations(vs,2): self.add(-a,-b)
    def at_least(self, vs, k):
        if k<=0: return
        if k>len(vs): raise ValueError('Impossible cardinality')
        t=self.var(True); f=self.var(False); self.add(t);self.add(-f)
        state=[t]+[f]*k
        for i,v in enumerate(vs):
            nxt=[t]+[f]*k
            for j in range(1,min(k,i+1)+1):
                nxt[j]=self.or_(state[j], self.and_(v,state[j-1]))
            state=nxt
        self.add(state[k])
    def finish(self):
        if not self.clauses: raise ValueError('No clauses')
        n=len(self.values)-1
        permutation=list(range(1,n+1)); self.rng.shuffle(permutation)
        clauses=[[permutation[abs(x)-1]*(1 if x>0 else -1) for x in c] for c in self.clauses]
        self.rng.shuffle(clauses)
        data=f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
        return n, len(clauses), data


def generate(category, rep, root):
    if category not in dict(SPECS): raise ValueError(category)
    seed=int.from_bytes(hashlib.sha256(f'{NAMESPACE}:{category}:{rep}'.encode()).digest()[:8],'big')
    rng=random.Random(seed); b=CNF(rng)
    if category in [s[0] for s in SPECS[:10]]:
        n=200+17*(rep%5); vs=[b.var() for _ in range(n)]
        density=4.15+.10*(rep%4)+(.4 if category=='random3_dense' else 0)
        for i in range(int(n*density)):
            w=4 if category=='mix3_4' and i%9==0 else 3
            if category.startswith('modular') and rng.random()<.45:
                width=int(category[7:]); at=rng.randrange(0,n//width)*width
                picked=rng.sample(vs[at:at+width],w)
            elif category=='hub3' and rng.random()<.25:
                v=rng.choice(vs[:12]); picked=[v]+rng.sample([x for x in vs if x!=v],w-1)
            elif category=='random3_balanced' and i%2==0:
                v=vs[i%n];picked=[v]+rng.sample([x for x in vs if x!=v],w-1)
            else: picked=rng.sample(vs,w)
            neg=.8 if category=='random3_polarity' else .5
            c=[-x if rng.random()<neg else x for x in picked]
            if not any(b.val(x) for x in c):
                j=rng.randrange(w);c[j]=-c[j]
            b.add(*c)
        if category=='planted_xor_mix':
            for _ in range(n//20): b.parity(rng.sample(vs,3))
        if category=='redundant3':
            b.clauses.extend([list(c) for c in b.clauses[:n//4]])
    elif category.startswith('parity_'):
        n=96+8*(rep%5);vs=[b.var() for _ in range(n)]
        if category=='parity_sparse':
            for _ in range(n): b.parity(rng.sample(vs,3+(rng.random()<.2)))
        elif category=='parity_chain':
            rng.shuffle(vs)
            for i in range(n-2): b.parity(vs[i:i+3])
            for _ in range(n//8): b.parity(rng.sample(vs,3))
        else:
            width=8
            for i in range(n-width-1):
                if i%width!=width-1 and rng.random()<.85:
                    b.parity([vs[i],vs[i+1],vs[i+width],vs[i+width+1]])
            for _ in range(n//10): b.parity(rng.sample(vs,3))
    elif category in ('implication_2sat','horn','dual_horn'):
        vs=[b.var() for _ in range(160+rep%5*13)]
        while len(b.clauses)<4*len(vs):
            w=2 if category=='implication_2sat' else rng.choice((2,3,4))
            chosen=rng.sample(vs,w)
            if category=='implication_2sat': c=[x if rng.getrandbits(1) else -x for x in chosen]
            else:
                c=[-x for x in chosen]
                if rng.random()<.8:
                    j=rng.randrange(w);c[j]=-c[j]
                if category=='dual_horn': c=[-x for x in c]
            if any(b.val(x) for x in c): b.add(*c)
        for v in rng.sample(vs,5): b.add(v if b.val(v) else -v)
    elif category in ('aig','xor_and','mux_network'):
        pool=[b.var() for _ in range(48+rep%5*4)]
        for i in range(180+rep%5*20):
            if category=='mux_network':
                args=rng.sample(pool,3);out=b.gate(args,lambda z:z[1] if z[0] else z[2])
            else:
                a,c=rng.sample(pool,2)
                if rng.random()<.3: a=-a
                out=b.xor(a,c) if category=='xor_and' and i%2 else b.and_(a,c)
            pool.append(out)
        for v in pool[-12:]: b.add(v if b.val(v) else -v)
    elif category in ('ripple_adder','multiplier'):
        width=(20+rep%5*3) if category=='ripple_adder' else (7+rep%3)
        a=[b.var() for _ in range(width)];c=[b.var() for _ in range(width)]
        zero=b.var(False);b.add(-zero)
        def plus(x,y):
            carry=zero;out=[]
            for aa,bb in zip(x,y):
                out.append(b.xor(b.xor(aa,bb),carry))
                carry=b.gate([aa,bb,carry],lambda z:sum(z)>=2)
            return out+[carry]
        if category=='ripple_adder': out=plus(a,c)
        else:
            out=[zero]*(2*width)
            for j,cc in enumerate(c):
                row=[zero]*j+[b.and_(aa,cc) for aa in a]+[zero]*(width-j)
                out=plus(out,row)[:2*width]
        for v in out: b.add(v if b.val(v) else -v)
    elif category in ('coloring3','coloring4'):
        colors=int(category[-1]);n=70+rep%5*6
        hidden=[rng.randrange(colors) for _ in range(n)]
        x=[[b.var(hidden[i]==k) for k in range(colors)] for i in range(n)]
        for row in x:b.exactly_one(row)
        edges=[(i,j) for i in range(n) for j in range(i) if hidden[i]!=hidden[j]]
        for i,j in rng.sample(edges,min(len(edges),n*5)):
            for k in range(colors):b.add(-x[i][k],-x[j][k])
    elif category in ('matching','permutation_assignment'):
        n=16+rep%5;perm=list(range(n));rng.shuffle(perm)
        x=[[b.var(perm[i]==j) for j in range(n)] for i in range(n)]
        for row in x:b.exactly_one(row)
        for j in range(n):b.exactly_one([x[i][j] for i in range(n)])
        density=.32 if category=='matching' else .70
        for i in range(n):
            for j in range(n):
                if j!=perm[i] and rng.random()>density:b.add(-x[i][j])
    elif category in ('independent_set','vertex_cover'):
        n=30+rep%5*2;k=7+rep%3;chosen=set(rng.sample(range(n),k))
        x=[b.var((i in chosen) if category=='independent_set' else (i not in chosen)) for i in range(n)]
        edges=[(i,j) for i in range(n) for j in range(i) if not(i in chosen and j in chosen)]
        for i,j in rng.sample(edges,min(len(edges),n*3)):
            if category=='independent_set':b.add(-x[i],-x[j])
            else:b.add(x[i],x[j])
        b.at_least(x if category=='independent_set' else [-v for v in x],k)
    elif category in ('set_cover','exact_cover'):
        n=24+rep%4*4;items=list(range(n));rng.shuffle(items)
        parts=[set(items[i:i+4]) for i in range(0,n,4)]
        sets=parts+[set(rng.sample(range(n),rng.randrange(2,7))) for _ in range(24)]
        vs=[b.var(i<len(parts)) for i in range(len(sets))]
        for item in range(n):
            choices=[v for v,s in zip(vs,sets) if item in s]
            if category=='exact_cover':b.exactly_one(choices)
            else:b.add(*choices)
        if category=='set_cover': b.at_least([-v for v in vs],len(vs)-len(parts))
    elif category=='latin_square':
        n=6+rep%3;rp=list(range(n));cp=list(range(n));sp=list(range(n))
        rng.shuffle(rp);rng.shuffle(cp);rng.shuffle(sp)
        x=[[[b.var(k==sp[(rp[i]+cp[j])%n]) for k in range(n)] for j in range(n)] for i in range(n)]
        for i in range(n):
            for j in range(n):b.exactly_one(x[i][j])
        for k in range(n):
            for i in range(n):b.exactly_one([x[i][j][k] for j in range(n)])
            for j in range(n):b.exactly_one([x[i][j][k] for i in range(n)])
        for i,j in rng.sample(list(itertools.product(range(n),repeat=2)),n):
            b.add(x[i][j][sp[(rp[i]+cp[j])%n]])
    else: raise AssertionError(category)
    n,m,text=b.finish();root=Path(root);root.mkdir(parents=True,exist_ok=True)
    path=root/f'{category}_{rep:03d}.cnf';path.write_text(text)
    return {'category':category,'domain':dict(SPECS)[category],'replicate_id':rep,
            'seed':seed,'nvars':n,'nclauses':m,'path':str(path),
            'sha256':hashlib.sha256(text.encode()).hexdigest(),
            'source_kind':'GENERATED_SAT_NOT_COMPETITION','oracle':'HIDDEN_PLANTED_WITNESS'}


def make_manifest(root, each=20):
    rows=[generate(c,i,root) for c,_ in SPECS for i in range(each)]
    for i,r in enumerate(rows):r['id']=i
    if len(rows)!=30*each or len({r['sha256'] for r in rows})!=len(rows):
        raise RuntimeError('Wrong category count or duplicate SHA')
    text=json.dumps([{k:v for k,v in r.items() if k!='path'} for r in rows],sort_keys=True,separators=(',',':'))+'\n'
    return rows,text,hashlib.sha256(text.encode()).hexdigest()
