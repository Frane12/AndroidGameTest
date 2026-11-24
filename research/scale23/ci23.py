import os,sys,time,subprocess,hashlib,json
from pathlib import Path
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
 return d,cnf,ops,cnt

d,f,ops,cnt=generate('la03',10,596)
assert hashlib.file_digest(f.open('rb'),'sha256').hexdigest()=='8ccc5e34359ac21e6cf6062dddda3fcd80d80bc67b514a3128bb82e4531c2e95'
# Reproduce the frozen SCALE22 trace, not a new solver run.
mmap={1:0,2:1,0:2,4:3,3:4}
c=d/'trace.cert'
with c.open('w') as q:
 q.write('SCALE22 50 596\n')
 for _,_,m,r,p,g in ops:q.write(f'{r} {p} {mmap[m]} {len(g)} '+' '.join(map(str,g))+'\n')
 for l in """1 0 21 596 9 324
1 47 37 533 0 398
1 47 37 544 399 409
1 16 50 533 12 312
1 7 53 56 0 5
1 32 53 56 0 2
1 7 53 57 6 6
1 32 53 57 3 3
1 41 53 57 0 0
1 7 53 63 7 12
1 21 53 63 0 5
1 32 53 63 4 9
1 41 53 63 1 6
1 7 53 68 13 17
1 21 53 68 6 10
1 32 53 68 10 14
1 41 53 68 7 11
1 2 53 81 0 12
1 7 53 81 18 30
1 21 53 81 11 23
1 32 53 81 15 27
1 41 53 81 12 24
1 2 53 91 13 22
1 7 53 91 31 40
1 21 53 91 24 33
1 26 53 91 0 9
1 32 53 91 28 37
1 41 53 91 25 34
0 6 0 0 0 1
0 3 2 0 0 22
0 4 3 0 0 22
0 8 7 0 0 40
0 9 8 0 0 40
0 15 16 0 12 312
0 20 15 0 0 36
0 25 15 0 0 36
0 35 15 0 0 36
0 40 15 0 0 36
0 45 15 0 0 36
0 21 20 0 34 36
0 22 21 0 0 36
0 23 22 0 0 36
0 24 23 0 0 36
0 26 25 0 10 36
0 27 26 0 0 36
0 28 27 0 0 36
0 29 28 0 0 36
0 33 32 0 0 37
0 34 33 0 0 37
0 36 35 0 0 36
0 37 36 0 0 36
0 38 37 0 0 36
0 39 38 0 0 36
0 41 40 0 35 36
0 42 41 0 0 36
0 43 42 0 0 36
0 44 43 0 0 36
0 46 45 0 0 36
0 48 47 0 0 409
0 49 48 0 0 409
0 4 49 0 318 324
0 9 49 0 431 437
0 19 49 0 306 312
0 24 48 0 285 292
0 28 48 0 244 247
0 38 48 0 387 393
0 3 4 0 318 324
0 8 9 0 431 437
0 18 19 0 306 312
0 27 28 0 244 247
0 37 38 0 387 393
0 2 3 0 318 324
0 7 8 0 431 437
0 17 18 0 306 312
0 26 27 0 244 247
0 36 37 0 387 393
0 1 2 0 318 324
0 6 7 0 431 437
0 25 26 0 244 247
0 35 36 0 387 393
0 5 6 0 431 437
1 6 52 596 11 430
2 0 596 0 61 61""".splitlines():
  t,u,a,b,lo,hi=map(int,l.split())
  for i in range(lo,hi+1):q.write(f'{t} {u} {i} {a} {b}\n')
pb=d/'proof.pbp'
def run(cmd,cap):
 t=time.perf_counter()
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap)
  return dict(s=time.perf_counter()-t,rc=p.returncode,stdout=p.stdout,stderr=p.stderr)
 except subprocess.TimeoutExpired:return dict(s=time.perf_counter()-t,rc='TIMEOUT')
a=run(['/tmp/emit23',str(f),str(c),str(pb)],120)
v=run([sys.argv[1],'--cnf',str(f),str(pb)],300) if a['rc']==0 else {}
r=dict(case='LA03/596',clauses=cnt,sha256=hashlib.file_digest(f.open('rb'),'sha256').hexdigest(),emit=a,veripb=v,proof_bytes=pb.stat().st_size if pb.exists() else 0)
(d/'result.json').write_text(json.dumps(r,indent=2))
print('SCALE23',json.dumps(r),flush=True)
f.unlink()
assert v.get('rc')==0 and 'VERIFIED UNSATISFIABLE' in v.get('stdout','')+v.get('stderr','')
