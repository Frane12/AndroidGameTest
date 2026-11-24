"""SCALE26 retrospective raw DIMACS band recovery; CP-SAT backend, not native DRNAS.
Fail closed on unsupported clause shapes. No scheduling metadata reaches recover().
"""
import sys,time,json,os,hashlib
from pathlib import Path
from collections import defaultdict
from ortools.sat.python import cp_model
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scale25'))
from bench25 import DATA,rows,generate,run,write_model
def clauses(path):
 with open(path) as f:
  for line in f:
   if not line.strip() or line[0] in 'cp':continue
   a=list(map(int,line.split()))
   if not a or a[-1]!=0:raise ValueError('DIMACS line')
   yield a[:-1]
def recover(path):
 with open(path) as f:
  header=next(f).split()
  if header[:2]!=['p','cnf']:raise ValueError('header')
  nv,nc=map(int,header[2:])
 groups=[];loc={}
 for c in clauses(path):
  if len(c)>=2 and all(x>0 for x in c):
   g=sorted(c)
   if len(set(g))!=len(g) or any(x in loc for x in g):raise ValueError('overlapping ALO')
   k=len(groups);groups.append(g)
   for i,x in enumerate(g):loc[x]=(k,i)
 if not groups:raise ValueError('no ALO')
 aux={};pairs={};seen=0
 for c in clauses(path):
  seen+=1
  if len(c)>=2 and all(x>0 for x in c):continue
  if len(c)!=2:raise ValueError('unsupported clause')
  x,y=c
  if x<0 and y<0 and -x in loc and -y in loc:
   a,i=loc[-x];b,j=loc[-y]
   if a==b:raise ValueError('same group mutex')
   if a>b:a,b,i,j=b,a,j,i
   d=pairs.setdefault((a,b),{})
   d[i]=d.get(i,0)|(1<<j)
   continue
  if not (x<0 and -x in loc):x,y=y,x
  if not (x<0 and -x in loc and abs(y) not in loc):raise ValueError('unexpected binary')
  a,i=loc[-x];v=abs(y)
  if v not in aux:aux[v]=[a,0,0]
  rec=aux[v]
  if rec[0]!=a:raise ValueError('shared auxiliary')
  rec[1 if y>0 else 2]|=1<<i
 if seen!=nc or set(loc)|set(aux)!=set(range(1,nv+1)):raise ValueError('uncovered variables or clauses')
 groupaux=defaultdict(list)
 for v,(a,pos,neg) in aux.items():
  if pos&neg or pos|neg!=(1<<len(groups[a]))-1:raise ValueError('incomplete bit channel')
  groupaux[a].append((v,pos))
 for a,g in enumerate(groups):
  # Distinct complete bit signatures prove at-most-one in every ALO.
  codes=[tuple((mask>>i)&1 for _,mask in groupaux[a]) for i in range(len(g))]
  if len(set(codes))!=len(g):raise ValueError('not exactly one')
 bands=[]
 for (a,b),d in pairs.items():
  L=min((m&-m).bit_length()-1-i for i,m in d.items())
  U=max(m.bit_length()-1-i for i,m in d.items())
  for i in range(len(groups[a])):
   lo=max(0,i+L);hi=min(len(groups[b])-1,i+U)
   mask=((1<<(hi-lo+1))-1)<<lo if hi>=lo else 0
   if mask!=d.get(i,0):raise ValueError('non-band conflict')
  bands.append((a,b,L,U))
 return nv,groups,groupaux,bands
def worker(path,model):
 t=time.monotonic()
 try:nv,g,aux,bands=recover(path)
 except ValueError as e:print('UNSUPPORTED',e,flush=True);return
 print('RECOVER',json.dumps(dict(groups=len(g),bands=len(bands),seconds=time.monotonic()-t)),flush=True)
 m=cp_model.CpModel();x=[m.new_int_var(0,len(a)-1,'') for a in g]
 for a,b,L,U in bands:
  d=x[b]-x[a];left=L>-len(g[a])+1;right=U<len(g[b])-1
  if left and right:
   q=m.new_bool_var('');m.add(d<=L-1).only_enforce_if(q);m.add(d>=U+1).only_enforce_if(q.Not())
  elif left:m.add(d<=L-1)
  elif right:m.add(d>=U+1)
  else:m.add_bool_or([])
 s=cp_model.CpSolver();s.parameters.num_search_workers=1;s.parameters.random_seed=42;s.parameters.max_time_in_seconds=max(0.01,300-(time.monotonic()-t))
 st=s.solve(m);print('CP_STATUS',s.status_name(st),flush=True)
 if st in (cp_model.OPTIMAL,cp_model.FEASIBLE):
  val=[-i for i in range(1,nv+1)]
  for a,group in enumerate(g):
   i=s.value(x[a]);v=group[i];val[v-1]=v
   for v,mask in aux[a]:
    if mask>>i&1:val[v-1]=v
  write_model(model,val)
def verify(path,model):
 a=list(map(int,Path(model).read_text().split()[1:-1]))
 return all(any(a[abs(v)-1]==v for v in c) for c in clauses(path))
def main(name,delta):
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 H=DATA[name]+delta;src=Path('jsplib/instances')/name;cnf=Path('input.cnf');generate(rows(src),H,cnf)
 d=Path('out26');d.mkdir(exist_ok=True);model=d/'model.txt';log=d/'solve.log'
 result=run([sys.executable,__file__,'raw',cnf,model],log)
 out=log.read_text(errors='replace');print(out,flush=True)
 status='TIMEOUT' if result['rc']=='TIMEOUT' else 'UNKNOWN'
 if 'CP_STATUS OPTIMAL' in out or 'CP_STATUS FEASIBLE' in out:status='SAT'
 if 'CP_STATUS INFEASIBLE' in out:status='UNSAT'
 t=time.monotonic();verified=status=='SAT' and model.exists() and verify(cnf,model);check=time.monotonic()-t
 rec=dict(case=name+'/'+str(H),expected='SAT' if delta==0 else 'UNSAT',status=status,model_verified=verified,decision_s=result['seconds'],check_s=check,e2e_s=result['seconds']+check,cnf_sha256=hashlib.file_digest(cnf.open('rb'),'sha256').hexdigest(),rc=result['rc'])
 print('SCALE26_ROW',json.dumps(rec),flush=True);(d/'result.json').write_text(json.dumps(rec,indent=2))
if __name__=='__main__':
 if sys.argv[1]=='raw':worker(sys.argv[2],sys.argv[3])
 else:main(sys.argv[1],int(sys.argv[2]))
