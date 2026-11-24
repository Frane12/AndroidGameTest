import os,sys,time,subprocess,hashlib,json
from pathlib import Path
from ortools.sat.python import cp_model
from pysat.solvers import Cadical195
from pysat.formula import CNF
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
data={
'la01':"""1 21 0 53 4 95 3 55 2 34
0 21 3 52 4 16 2 26 1 71
3 39 4 98 1 42 2 31 0 12
1 77 0 55 4 79 2 66 3 77
0 83 3 34 2 64 1 19 4 37
1 54 2 43 4 79 0 92 3 62
3 69 4 77 1 87 2 87 0 93
2 38 0 60 1 41 3 24 4 83
3 17 1 49 4 25 0 44 2 98
4 77 3 79 2 43 1 75 0 96""",
'la02':"""0 20 3 87 1 31 4 76 2 17
4 25 2 32 0 24 1 18 3 81
1 72 2 23 4 28 0 58 3 99
2 86 1 76 4 97 0 45 3 90
4 27 0 42 3 48 2 17 1 46
1 67 0 98 4 48 3 27 2 62
4 28 1 12 3 19 0 80 2 50
1 63 0 94 2 98 3 50 4 80
4 14 0 75 2 50 1 41 3 55
4 72 2 18 1 37 3 79 0 61""",
'la03':"""1 23 2 45 0 82 4 84 3 38
2 21 1 29 0 18 4 41 3 50
2 38 3 54 4 16 0 52 1 52
4 37 0 54 2 74 1 62 3 57
4 57 0 81 1 61 3 68 2 30
4 81 0 79 1 89 2 89 3 11
3 33 2 20 0 91 4 20 1 66
4 24 1 84 0 32 2 55 3 8
4 56 0 7 3 54 2 64 1 39
4 40 1 83 0 19 2 8 3 7"""}
# Full LA01, plus smaller certificate smoke case. Witness here is constructed from known source data:
# this tests the proof compiler, not raw geometry discovery.
def generate(name,n,H):
 rows=[list(map(int,l.split())) for l in data[name].splitlines()][:n];ops=[];nv=0
 for j,row in enumerate(rows):
  T=sum(row[1::2]);r=0
  for k,(m,p) in enumerate(zip(row[::2],row[1::2])):
   w=H-T+1;assert w>=2;g=list(range(nv+1,nv+w+1));nv+=w;ops.append((j,k,m,r,p,g));r+=p
 d=Path('out')/f'{name}_{n}_{H}';d.mkdir(exist_ok=True);cnt=0
 with (d/'body').open('w') as f:
  def emit(c):
   nonlocal cnt
   f.write(' '.join(map(str,c))+' 0\n');cnt+=1
  for _,_,_,_,_,g in ops:
   emit(g);bits=list(range(nv+1,nv+1+(len(g)-1).bit_length()));nv+=len(bits)
   for i,x in enumerate(g):
    for k,b in enumerate(bits):emit((-x,b if i>>k&1 else -b))
  for u,(j,k,m,r,p,g) in enumerate(ops):
   for J,l,M,R,P,G in ops[u+1:]:
    if j==J and l==k+1:
     for i,x in enumerate(g):
      for y in G[:i]:emit((-x,-y))
    elif m==M:
     for i,x in enumerate(g):
      for y in G[max(0,r+i-R-P+1):max(0,min(len(G),r+i+p-R))]:emit((-x,-y))
 import shutil
 cnf=d/'source.cnf'
 with cnf.open('wb') as f:
  f.write(f'p cnf {nv} {cnt}\n'.encode())
  with (d/'body').open('rb') as q:shutil.copyfileobj(q,f)
 (d/'body').unlink()
 # Scan endpoints exactly as a mathematical witness; deliberately uses known data for compiler test.
 E=sorted({0,H}|{v for _,_,_,r,p,g in ops for v in (r,r+p,r+len(g)-1,r+len(g)-1+p)})
 for a,b in [(0,H)]+[(a,b) for a in E for b in E if b>a]:
  for m in range(5):
   G=[(r,p,g) for _,_,M,r,p,g in ops if M==m]
   def e(r,p,g):return min(max(0,min(b,t+p)-max(a,t)) for t in (r,r+len(g)-1))
   G=[(r,p,g) for r,p,g in G if e(r,p,g)]
   if sum(e(*z) for z in G)>b-a:
    cert=d/'energy.cert';cert.write_text(f'ENERGY20 {a} {b} {len(G)}\n'+''.join(f'{r} {p} {len(g)} '+' '.join(map(str,g))+'\n' for r,p,g in G));return d,cnf,cert,rows,cnt
 raise RuntimeError('no witness')
def run(args,cap):
 t=time.perf_counter()
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=cap);return {'s':time.perf_counter()-t,'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except subprocess.TimeoutExpired:return {'s':time.perf_counter()-t,'rc':'TIMEOUT'}
def cp(rows,H):
 t=time.perf_counter();m=cp_model.CpModel();ms=[[] for _ in range(5)]
 for j,row in enumerate(rows):
  prev=None
  for k,(M,p) in enumerate(zip(row[::2],row[1::2])):
   s=m.NewIntVar(0,H-p,f's{j}_{k}');e=m.NewIntVar(p,H,f'e{j}_{k}');it=m.NewIntervalVar(s,p,e,f'i{j}_{k}');ms[M].append(it)
   if prev is not None:m.Add(s>=prev)
   prev=e
 for g in ms:m.AddNoOverlap(g)
 solver=cp_model.CpSolver();solver.parameters.num_search_workers=1;solver.parameters.max_time_in_seconds=15
 st=solver.Solve(m);return {'status':solver.StatusName(st),'s':time.perf_counter()-t}
for name,n,H in [('la01',6,403),('la01',10,600),('la02',10,654),('la03',10,587)]:
 d,f,c,rows,cnt=generate(name,n,H)
 pb=d/'proof.pbp';a=run(['/tmp/emit21',str(f),str(c),str(pb)],60)
 v=run([sys.argv[1],'--cnf',str(f),str(pb)],120) if a['rc']==0 else {}
 r={'case':str(d),'clauses':cnt,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest(),'emit':a,'veripb':v,'proof_bytes':pb.stat().st_size if pb.exists() else 0,'cp_sat_structured':cp(rows,H)}
 # Isolate CaDiCaL parsing and solve under a common 15 s outer cap.
 r['cadical195']=run([sys.executable,'-c','from pysat.formula import CNF; from pysat.solvers import Cadical195; import sys; f=CNF(from_file=sys.argv[1]); s=Cadical195(bootstrap_with=f.clauses); print(s.solve())',str(f)],15)
 (d/'result.json').write_text(json.dumps(r,indent=2));print('SCALE21',json.dumps(r),flush=True)
 f.unlink()
 if v.get('rc')!=0 or 'VERIFIED UNSATISFIABLE' not in v.get('stdout','')+v.get('stderr',''):raise SystemExit('official checker did not accept')
