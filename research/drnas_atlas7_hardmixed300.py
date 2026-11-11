#!/usr/bin/env python3
"""ATLAS7 300 hard mixed SAT and UNSAT candidate CNFs: 200 train, 100 blind fixed holdout.
10 categories x30 each, 20 train +10 holdout. 15s cap each E2E solve.
Training-only nearest-neighbor memory frozen at 0,25,50,100,150,200.
No holdout labels used in any policy. SAT witness verified on original.
"""
import hashlib,json,math,pathlib,random,resource,statistics,subprocess,time,os
OUT=pathlib.Path("mre_atlas7");OUT.mkdir(exist_ok=True)
CATEGORIES=("random3_sat","random3_unsat","xor_dense_sat","xor_dense_unsat","graph3color_sat","graph3color_unsat","pigeonhole_unsat","pigeonhole_sat","mixed_circuit","mixed_hard")
CAP=15;REPS=2;ARMS=("A","ATLAS2","ATLAS3")
CHECKPOINTS=(0,25,50,100,150,200)
def build(category,index):
 seed=int.from_bytes(hashlib.sha256(f"ATLAS7|hardmixed-v1|{category}|{index}".encode()).digest()[:8],"big")
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
  if category.endswith("sat"):
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
  pigeons=holes+(1 if category.endswith("unsat") else 0)
  n=pigeon(holes,pigeons)
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
def fingerprint(n,clauses):
 hist=[0]*6;degree=[0]*(n+1);edges=0
 for c in clauses:
  hist[min(5,len(c))]+=1
  for l in c:degree[abs(l)]+=1
 m=len(clauses)
 # Dimensionless and bounded source-only features, no source ID.
 return [math.log1p(n),math.log1p(m)]+[x/max(1,m) for x in hist]+[
  sum(d>0 for d in degree[1:])/n,max(degree)/max(1,m),
  sum(d*d for d in degree[1:])/max(1,sum(degree)**2)]
def dimacs(n,clauses):
 return ("p cnf %d %d\n"%(n,len(clauses))+"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
def verify(stdout,n,clauses):
 assign={}
 for line in stdout.splitlines():
  if line.startswith("v "):
   for token in line.split()[1:]:
    l=int(token)
    if not l:continue
    if not 1<=abs(l)<=n:return False
    if abs(l) in assign and assign[abs(l)]!=(l>0):return False
    assign[abs(l)]=l>0
 return len(assign)==n and all(any(assign[abs(l)]==(l>0) for l in c) for c in clauses)
def solve(mode,path,n,clauses):
 cmd=[str((OUT/"bin/drnas_atlas3").resolve()),str(path.resolve()),"--mode",mode,"--time",str(CAP)]
 def limits():
  resource.setrlimit(resource.RLIMIT_CPU,(CAP,CAP+1))
  resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
 t=time.monotonic()
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+1,preexec_fn=limits)
  rc,stdout,err=p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired:rc,stdout,err=124,"","timeout"
 e2e=time.monotonic()-t
 if rc==10:
  assert verify(stdout,n,clauses),("bad original SAT model",mode,err[-200:])
  status="SAT_VERIFIED"
 elif rc==20:status="UNSAT_UNVERIFIED"
 elif rc in (0,124,-9,-24):status="UNKNOWN"
 else:raise RuntimeError((mode,rc,err[-800:]))
 tele={}
 if rc==10:
  for line in stdout.splitlines():
   if line.startswith("ATLAS3_TRIAL "):
    tele=dict(part.split("=",1) for part in line.split()[1:] if "=" in part)
    break
 return dict(status=status,e2e_s=round(e2e,6),
   par2_s=round(e2e if status=="SAT_VERIFIED" else 2*CAP,6),
   conflicts=int(tele.get("conflicts",0)),modules=int(tele.get("modules",0)),
   gate_score=int(tele.get("gate_score",0)),decision=tele.get("decision",""))
def row(category,index):
 n,clauses,seed=build(category,index)
 raw=dimacs(n,clauses);p=OUT/"case.cnf";p.write_bytes(raw)
 feat=fingerprint(n,clauses);measure={}
 for rep in range(REPS):
  for mode in ARMS[rep:]+ARMS[:rep]:
   r=solve(mode,p,n,clauses)
   measure.setdefault(mode,[]).append(r)
 def median(mode):return statistics.median(x["par2_s"] for x in measure[mode])
 return dict(category=category,index=index,seed=seed,sha256=hashlib.sha256(raw).hexdigest(),
   vars=n,clauses=len(clauses),features=feat,measure=measure,
   median={mode:median(mode) for mode in ARMS})
def dist(a,b):return sum((x-y)**2 for x,y in zip(a,b))
def train_policy(rows):
 examples=[]
 for r in rows:
  base=r["median"]["A"]
  best=min(ARMS,key=lambda m:r["median"][m])
  # 5% AND 0.5ms improvement needed; no benefit -> abstain to A.
  winner=best if best!="A" and r["median"][best]<base*0.95 and base-r["median"][best]>0.0005 else "A"
  examples.append(dict(features=r["features"],winner=winner,category=r["category"],sha256=r["sha256"]))
 return dict(version=1,examples=examples,trained=len(examples))
def choose(model,feat):
 if len(model["examples"])<5:return "A"
 neighbors=sorted(model["examples"],key=lambda r:dist(feat,r["features"]))[:5]
 counts={mode:sum(r["winner"]==mode for r in neighbors) for mode in ARMS}
 best=max(ARMS,key=lambda m:counts[m])
 return best if best!="A" and counts[best]>=4 else "A"
def main():
 # Deterministic split is declared before any benchmark timing.
 train_cases=[(c,i) for c in CATEGORIES for i in range(20)]
 hold_cases=[(c,i) for c in CATEGORIES for i in range(20,30)]
 rng=random.Random(20261111);rng.shuffle(train_cases)
 manifest=dict(seed=20261111,categories=CATEGORIES,train=train_cases,holdout=hold_cases,
  cap_s=CAP,reps=REPS,checkpoints=CHECKPOINTS,policy="5NN supermajority 4/5, 5pct+0.5ms training margin")
 (OUT/"frozen_manifest.json").write_text(json.dumps(manifest,indent=2))
 print("ATLAS7_MANIFEST "+json.dumps(dict(train=len(train_cases),holdout=len(hold_cases),
  categories=len(CATEGORIES),sha256=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest())),flush=True)
 train=[]
 for k,(c,i) in enumerate(train_cases,1):
  r=row(c,i);train.append(r)
  if k%10==0:print("ATLAS7_TRAIN "+json.dumps(dict(done=k,total=200,
    categories=len(set(x["category"] for x in train)),
    positive=sum(train_policy(train)["examples"][j]["winner"]!="A" for j in range(len(train))))),flush=True)
 models={}
 for cp in CHECKPOINTS:
  model=train_policy(train[:cp])
  frozen=json.dumps(model,sort_keys=True,separators=(",",":")).encode()
  models[cp]=model
  (OUT/f"memory_{cp:03}.json").write_bytes(frozen)
  print("ATLAS7_MEMORY "+json.dumps(dict(checkpoint=cp,sha256=hashlib.sha256(frozen).hexdigest(),
    atlas_choices=sum(x["winner"]!="A" for x in model["examples"]))),flush=True)
 # Every model is frozen before ANY holdout solver execution.
 model_hashes={cp:hashlib.sha256((OUT/f"memory_{cp:03}.json").read_bytes()).hexdigest() for cp in CHECKPOINTS}
 hold=[]
 for k,(c,i) in enumerate(hold_cases,1):
  r=row(c,i);hold.append(r)
  if k%10==0:print("ATLAS7_HOLDOUT_PROGRESS "+json.dumps(dict(done=k,total=100,category=c)),flush=True)
 for cp in CHECKPOINTS:
  assert hashlib.sha256((OUT/f"memory_{cp:03}.json").read_bytes()).hexdigest()==model_hashes[cp]
 result=[]
 for cp in CHECKPOINTS:
  picks=[choose(models[cp],r["features"]) for r in hold]
  par2=sum(sum(x["par2_s"] for x in r["measure"][p]) for r,p in zip(hold,picks))
  percat={c:round(sum(sum(x["par2_s"] for x in r["measure"][p]) for r,p in zip(hold,picks) if r["category"]==c),6) for c in CATEGORIES}
  result.append(dict(trained=cp,PAR2_s=round(par2,6),
    choice_counts={m:picks.count(m) for m in ARMS},per_category=percat))
  print("ATLAS7_CURVE "+json.dumps(result[-1],sort_keys=True),flush=True)
 totals={m:round(sum(sum(x["par2_s"] for x in r["measure"][m]) for r in hold),6) for m in ARMS}
 solved={m:sum(x["status"]=="SAT_VERIFIED" for r in hold for x in r["measure"][m]) for m in ARMS}
 bycat={c:{m:round(sum(sum(x["par2_s"] for x in r["measure"][m]) for r in hold if r["category"]==c),6) for m in ARMS} for c in CATEGORIES}
 summary=dict(total=300,train=200,holdout=100,reps=REPS,cap_s=CAP,
  categories=CATEGORIES,baseline_PAR2_s=totals,verified_SAT=solved,
  learning_curve=result,baseline_per_category=bycat,
  warning="UNSAT statuses unverified without independent proof and count as PAR2 failures; policy replay excludes inference overhead; random3_unsat is unplanted not guaranteed UNSAT")
 (OUT/"audit.json").write_text(json.dumps(dict(summary=summary,training=train,holdout=hold),indent=2))
 print("ATLAS7_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":main()
