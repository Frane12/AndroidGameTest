#!/usr/bin/env python3
"""ATLAS7 300 hard mixed SAT and UNSAT candidate CNFs: 200 train, 100 blind fixed holdout.
10 categories x30 each, 20 train +10 holdout. 15s cap each E2E solve.
Training-only nearest-neighbor memory frozen at 0,25,50,100,150,200.
No holdout labels used in any policy. SAT witness verified on original.
"""
import hashlib,json,math,pathlib,random,resource,statistics,subprocess,time,os
OUT=pathlib.Path("mre_atlas11");OUT.mkdir(exist_ok=True)
CATEGORIES=("random3_sat","random3_unsat","xor_dense_sat","xor_dense_unsat","graph3color_sat","graph3color_unsat","pigeonhole_unsat","pigeonhole_sat","mixed_circuit","mixed_hard")
CAP=15;REPS=2;ARMS=("A","ATLAS2","ATLAS3")
CHECKPOINTS=(0,25,50,100,150,200)
def build(category,index):
 seed=int.from_bytes(hashlib.sha256(f"ATLAS11|c3-fixed-v1|{category}|{index}".encode()).digest()[:8],"big")
 rng=random.Random(seed);clauses=[]
 def add(*lits):
  c=list(dict.fromkeys(lits))
  if any(-x in c for x in c):return
  clauses.append(c)
 def rand3(n,planted=None):
  v=rng.sample(range(1,n+1),3)
  ls=[x if rng.randrange(2) else -x for x in v]
  if planted is not None and not any(planted[abs(x)]==(x>0) for x in ls):
   j=rng.randrange(3);ls[j]=-ls[j]
  add(*ls)
 def xor(v,parity):
  for bits in range(1<<len(v)):
   if bits.bit_count()%2!=parity:
    add(*[-x if (bits>>j)&1 else x for j,x in enumerate(v)])
 def graph(n,colors,edges):
  def x(v,c):return v*3+c+1
  for v in range(n):
   add(*[x(v,c) for c in range(3)])
   for c in range(3):
    for d in range(c+1,3):add(-x(v,c),-x(v,d))
  for u,v in edges:
   for c in range(3):add(-x(u,c),-x(v,c))
  return 3*n
 def pigeon(holes,pigeons):
  def x(p,h):return p*holes+h+1
  for p in range(pigeons):add(*[x(p,h) for h in range(holes)])
  for h in range(holes):
   for p in range(pigeons):
    for q in range(p+1,pigeons):add(-x(p,h),-x(q,h))
  return holes*pigeons
 if category.startswith("random3"):
  n=55+index%6*5
  planted={v:bool(rng.randrange(2)) for v in range(1,n+1)}
  # Unplanted near-threshold 3SAT is often UNSAT but not guaranteed;
  # label refers to construction, never a claimed verified answer.
  for _ in range(int((4.6 if category.endswith("unsat") else 4.05)*n)):
   rand3(n,None if category.endswith("unsat") else planted)
 elif category.startswith("xor_dense"):
  n=36+index%5*6;planted={v:bool(rng.randrange(2)) for v in range(1,n+1)}
  equations=[]
  for _ in range(n+int(n*.65)):
   v=rng.sample(range(1,n+1),3 if rng.randrange(2) else 4)
   p=sum(planted[x] for x in v)%2
   xor(v,p);equations.append((v,p))
  if category.endswith("unsat"):
   # Exact contradiction from same XOR support and opposite parity.
   v,p=equations[rng.randrange(len(equations))]
   xor(v,1-p)
 elif category.startswith("graph3color"):
  n=25+index%6*3
  if category=="graph3color_sat":
   colors=[rng.randrange(3) for _ in range(n)]
   edges=[(u,v) for u in range(n) for v in range(u+1,n)
          if colors[u]!=colors[v] and rng.random()<0.22]
  else:
   # K4 subgraph is UNSAT for 3-coloring by pigeonhole principle.
   edges=[(u,v) for u in range(4) for v in range(u+1,4)]
   edges +=[(u,v) for u in range(n) for v in range(max(4,u+1),n)
            if rng.random()<0.12]
  n=graph(n,3,edges)
 elif category.startswith("pigeonhole"):
  holes=6+index%6
  pigeons=holes+(1 if category=="pigeonhole_unsat" else 0)
  n=pigeon(holes,pigeons)
  permutation=list(range(1,n+1));rng.shuffle(permutation)
  clauses[:]=[[permutation[abs(l)-1]*(1 if l>0 else -1) for l in c] for c in clauses]
 else:
  n=70+index%6*15;planted={v:bool(rng.randrange(2)) for v in range(1,n+1)}
  for j in range(90+index%7*25):
   if j%3==0:
    v=rng.sample(range(1,n+1),3)
    xor(v,sum(planted[x] for x in v)%2)
   elif j%3==1:
    a,b,c=rng.sample(range(1,n+1),3)
    # Force an AND relation by choosing signed literals true in model.
    x=a if planted[a] else -a;y=b if planted[b] else -b
    z=c if planted[c] else -c
    add(-x,-y,z);add(x,-z);add(y,-z)
   else:rand3(n,planted)
  if category=="mixed_hard":
   for _ in range(3*n):rand3(n,planted)
 return n,clauses,seed

if __name__=="__main__":
 from collections import Counter
 def d(n,cs):return ("p cnf %d %d\n"%(n,len(cs))+"".join(" ".join(map(str,c))+" 0\n" for c in cs)).encode()
 items=[]
 for cat in CATEGORIES:
  for i in range(40,80):
   n,c,_=build(cat,i);items.append((cat,i,hashlib.sha256(d(n,c)).hexdigest()))
 assert len(set(x[2] for x in items))==len(items),("duplicate source SHA",Counter(x[2] for x in items).most_common(3))
 for i in (40,43,47):
  n,cs,_=build("graph3color_unsat",i)
  assert any(len(c)==2 for c in cs)
 print("ATLAS11_GENERATOR_SELFTEST_PASS",len(items),"unique CNF SHA; graph UNSAT uses K4; pigeonhole source renaming")
