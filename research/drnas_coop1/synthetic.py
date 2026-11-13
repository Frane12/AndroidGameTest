"""Synthetic discovery benchmark. CNF is the only input given to solvers."""
import itertools,random

def encode(vs,allowed):
 return [[-v if bits[i] else v for i,v in enumerate(vs)] for bits in itertools.product((0,1),repeat=len(vs)) if not allowed(bits)]
def xor(vs,rhs):return encode(vs,lambda b:sum(b)%2==rhs)
def and_xor(vs,rhs):return encode(vs,lambda b:((b[0]&b[1])^b[2]^b[3])==rhs)
def text(n,cs):return f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)
def model_ok(n,cs,stdout):
 vals={}
 for line in stdout.splitlines():
  if line.startswith('v '):
   for s in line.split()[1:]:
    l=int(s)
    if l:
     if abs(l) in vals and vals[abs(l)]!=(l>0):return False
     vals[abs(l)]=l>0
 return all(i in vals for i in range(1,n+1)) and all(any(vals.get(abs(l))==(l>0) for l in c) for c in cs)
def oracle(n,cs):
 return any(all(any(bool(x&(1<<(abs(l)-1)))==(l>0) for l in c) for c in cs) for x in range(1<<n))
def linear_consistent(rows):
 piv={}
 for vs,r in rows:
  m=sum(1<<(v-1) for v in vs)
  while m:
   p=m.bit_length()-1
   if p not in piv:piv[p]=(m,r);break
   a,b=piv[p];m^=a;r^=b
  if not m and r:return False
 return True
FAMILIES=['xor_sparse_sat','xor_sparse_unsat','and_xor_sat','and_xor_unsat','random3_planted','random3_random','php_unsat']
def make(family,level,seed,scale="smoke"):
 rng=random.Random(seed);cs=[];expected=None
 if family.startswith('xor_sparse'):
  n=([128,256,512] if scale=="stress" else [32,64,96])[level];w=[0]+[rng.randrange(2) for _ in range(n)];rows=[]
  for _ in range(n+16):
   vs=sorted(rng.sample(range(1,n+1),3));rows.append((vs,sum(w[v] for v in vs)%2))
  if family.endswith('unsat'):
   for i in range(len(rows)-1,-1,-1):
    vs,r=rows[i];rows[i]=(vs,r^1)
    if not linear_consistent(rows):break
    rows[i]=(vs,r)
   else:raise AssertionError('no dependent row')
   expected=False
  else:expected=True
  cs=[c for vs,r in rows for c in xor(vs,r)]
 elif family.startswith('and_xor'):
  cells=([32,64,96] if scale=="stress" else [8,16,24])[level];n=5*cells;w=[0]+[rng.randrange(2) for _ in range(n)]
  for j in range(cells):
   a,b,c,d,e=range(5*j+1,5*j+6)
   r1=(w[a]&w[b])^w[c]^w[d];r2=(w[a]&w[b])^w[d]^w[e]
   cs+=and_xor([a,b,c,d],r1)+and_xor([a,b,d,e],r2)
   if family.endswith('unsat') and j==cells//2:cs+=xor([c,e],r1^r2^1)
  # Connect components using additional planted clauses, not generator hints.
  for _ in range(n):
   vs=rng.sample(range(1,n+1),3);c=[v*rng.choice([-1,1]) for v in vs]
   if not any(w[abs(l)]==(l>0) for l in c):c[0]*=-1
   cs.append(c)
  expected=family.endswith('_sat')
 elif family.startswith('random3'):
  n=([128,256,512] if scale=="stress" else [32,64,96])[level];w=[0]+[rng.randrange(2) for _ in range(n)]
  for _ in range(round(4.25*n)):
   c=[v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),3)]
   if family=='random3_planted' and not any(w[abs(l)]==(l>0) for l in c):c[0]*=-1
   cs.append(c)
  if family=='random3_planted':expected=True
 else:
  pigeons=([8,9,10] if scale=="stress" else [5,6,7])[level];holes=pigeons-1;n=pigeons*holes
  var=lambda p,h:1+p*holes+h
  cs=[[var(p,h) for h in range(holes)] for p in range(pigeons)]
  cs += [[-var(p,h),-var(q,h)] for h in range(holes) for p in range(pigeons) for q in range(p)]
  expected=False
 # Freeze random variable/sign permutation and clause ordering before solving.
 perm=list(range(1,n+1));rng.shuffle(perm);sign=[rng.choice([-1,1]) for _ in range(n)]
 cs=[[perm[abs(l)-1]*sign[abs(l)-1]*(1 if l>0 else -1) for l in c] for c in cs]
 rng.shuffle(cs)
 return n,cs,expected
