"""Frozen paired test: all raw arms see identical DIMACS, no tuning after launch."""
import sys,os,time,json,hashlib,subprocess,random,resource,shutil
from pathlib import Path
CAP=300
DATA={'la04':590,'la05':593,'la08':863,'la09':951,'la10':958,'la16':945,'la17':784,'la18':848,'la19':842,'la20':902}
def rows(path):
 return [list(map(int,l.split())) for l in Path(path).read_text().splitlines() if l.strip() and not l.startswith('#')][1:]
def ops_for(R,H):
 ops=[];nv=0
 for j,row in enumerate(R):
  r=0;w=H-sum(row[1::2])+1
  assert w>=2
  for k,(m,p) in enumerate(zip(row[::2],row[1::2])):
   g=list(range(nv+1,nv+w+1));nv+=w;ops.append((j,k,m,r,p,g));r+=p
 return ops,nv
def generate(R,H,path):
 ops,nv=ops_for(R,H);cnt=0
 body=path.with_suffix('.body')
 with body.open('w',buffering=1024*1024) as f:
  def emit(c):
   nonlocal cnt
   f.write(' '.join(map(str,c))+' 0\n');cnt+=1
  for _,_,_,_,_,g in ops:
   emit(g);bits=list(range(nv+1,nv+1+(len(g)-1).bit_length()));nv+=len(bits)
   for i,x in enumerate(g):
    for k,b in enumerate(bits):emit((-x,b if i>>k&1 else -b))
  for u,(j,k,m,r,p,g) in enumerate(ops):
   for J,l,M,R0,P,G in ops[u+1:]:
    if j==J and l==k+1:
     for i,x in enumerate(g):
      for y in G[:i]:emit((-x,-y))
    elif m==M:
     for i,x in enumerate(g):
      for y in G[max(0,r+i-R0-P+1):max(0,min(len(G),r+i+p-R0))]:emit((-x,-y))
 with path.open('wb') as f:
  f.write(f'p cnf {nv} {cnt}\n'.encode())
  with body.open('rb') as b:shutil.copyfileobj(b,f)
 body.unlink()
 return nv,cnt
def write_model(path,vals):
 Path(path).write_text('v '+' '.join(map(str,vals))+' 0\n')
def cp_worker(mode,cnf,source,H,model):
 from ortools.sat.python import cp_model
 m=cp_model.CpModel()
 if mode=='raw':
  with open(cnf) as f:
   _,_,nv,nc=next(f).split();nv=int(nv);x=[m.new_bool_var('') for _ in range(nv)]
   for l in f:
    c=list(map(int,l.split()));assert c[-1]==0
    m.add_bool_or([x[v-1] if v>0 else x[-v-1].Not() for v in c[:-1]])
 else:
  R=rows(source);ops,nv=ops_for(R,H);ss=[];ends=[];ms={}
  for j,k,M,r,p,g in ops:
   a=m.new_int_var(r,r+len(g)-1,'');b=m.new_int_var(r+p,r+p+len(g)-1,'')
   it=m.new_interval_var(a,p,b,'');ss.append(a);ends.append(b);ms.setdefault(M,[]).append(it)
   if k:m.add(a>=ends[-2])
  for g in ms.values():m.add_no_overlap(g)
 sol=cp_model.CpSolver();sol.parameters.num_search_workers=1;sol.parameters.max_time_in_seconds=CAP;sol.parameters.random_seed=42
 st=sol.solve(m);print('CP_STATUS',sol.status_name(st),flush=True)
 if st in (cp_model.OPTIMAL,cp_model.FEASIBLE):
  if mode=='raw':vals=[i+1 if sol.value(v) else -(i+1) for i,v in enumerate(x)]
  else:
   vals=[-i for i in range(1,nv+1)];aux=nv
   for (_,_,_,r,p,g),a in zip(ops,ss):
    i=sol.value(a)-r;vals[g[i]-1]=g[i]
    for k in range((len(g)-1).bit_length()):
     aux+=1;vals.append(aux if i>>k&1 else -aux)
  write_model(model,vals)
def child_limit():
 # same address-space limit for all timed processes, avoid OOM killing runner
 resource.setrlimit(resource.RLIMIT_AS,(5*1024**3,5*1024**3))
def run(cmd,log,cap=CAP):
 t=time.monotonic()
 with open(log,'w') as f:
  try:
   p=subprocess.run(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT,timeout=cap,preexec_fn=child_limit)
   rc=p.returncode
  except subprocess.TimeoutExpired:rc='TIMEOUT'
  except OSError as e:rc='LAUNCH_ERROR';f.write(str(e))
 return dict(seconds=time.monotonic()-t,rc=rc,log=str(log))
def model_from_log(log,model,nv):
 vals={}
 for l in Path(log).open():
  if not l.startswith('v '):continue
  for x in map(int,l.split()[1:]):
   if x:
    if abs(x)>nv or (abs(x) in vals and vals[abs(x)]!=x):return False
    vals[abs(x)]=x
 if not vals:return False
 write_model(model,[vals.get(i,-i) for i in range(1,nv+1)])
 return True
def main(name,delta):
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 root=Path.cwd();bin=root/'bin25';d=root/'out';d.mkdir(exist_ok=True);H=DATA[name]+delta
 src=root/'jsplib'/'instances'/name;cnf=root/'input.cnf';nv,nc=generate(rows(src),H,cnf)
 meta=dict(case=f'{name}/{H}',expected='SAT' if delta==0 else 'UNSAT',source_sha256=hashlib.file_digest(src.open('rb'),'sha256').hexdigest(),cnf_sha256=hashlib.file_digest(cnf.open('rb'),'sha256').hexdigest(),vars=nv,clauses=nc,cap=CAP,source_commit='eea2b60dd7e2f5c907ff7302662c61812eb7efdf',results=[])
 print('SCALE25_MANIFEST',json.dumps(meta),flush=True)
 # fixed rotation; no adaptive solver/parameter selection
 order=['drnas','kissat','cadical','cms','cp_raw','cp_struct'];random.Random(name+str(delta)).shuffle(order)
 for arm in order:
  prefix=d/arm;model=prefix.with_suffix('.model');log=prefix.with_suffix('.log');proof=prefix.with_suffix('.drat')
  if arm=='drnas':cmd=[bin/'drnas',cnf,model,CAP,42]
  elif arm in ('kissat','cadical'):cmd=[bin/arm,cnf]
  elif arm=='cms':cmd=['cryptominisat5','--threads=1','--verb=0',cnf]
  else:cmd=[sys.executable,__file__,'cp','raw' if arm=='cp_raw' else 'structured',cnf,src,H,model]
  a=run(cmd,log);out=log.read_text(errors='replace');r=dict(arm=arm,decision=a,status='UNKNOWN',validation='NONE')
  if a['rc']=='TIMEOUT':r['status']='TIMEOUT'
  elif arm=='drnas':
   if a['rc']==0 and 'MODEL_CANDIDATE' in out:r['status']='SAT'
   elif a['rc']==0 and 'UNSAT_CANDIDATE_UNCERTIFIED' in out:r['status']='UNSAT'
   elif a['rc']!=0:r['status']='LIMIT_OR_ERROR'
  elif arm.startswith('cp'):
   if a['rc']==0 and ('CP_STATUS OPTIMAL' in out or 'CP_STATUS FEASIBLE' in out):r['status']='SAT'
   elif a['rc']==0 and 'CP_STATUS INFEASIBLE' in out:r['status']='UNSAT'
   elif a['rc']!=0:r['status']='LIMIT_OR_ERROR'
  elif a['rc']==10 and 's SATISFIABLE' in out:r['status']='SAT';model_from_log(log,model,nv)
  elif a['rc']==20 and 's UNSATISFIABLE' in out:r['status']='UNSAT'
  elif a['rc'] not in (0,10,20):r['status']='LIMIT_OR_ERROR'
  if r['status']=='SAT':
   if model.exists():
    v=run([bin/'verify_model',cnf,model],prefix.with_suffix('.check.log'));r['check']=v
    r['validation']='SAT_VERIFIED' if v['rc']==0 and 'VERIFIED SAT' in Path(v['log']).read_text() else 'SAT_NOT_VERIFIED'
   else:r['validation']='SAT_NOT_VERIFIED'
  elif r['status']=='UNSAT':
   if arm=='drnas':
    cert=Path(str(model)+'.cert')
    if cert.exists():
     v=run([bin/'verify_trace',cnf,cert],prefix.with_suffix('.check.log'));r['check']=v
     r['validation']='CUSTOM_UNSAT' if v['rc']==0 else 'UNSAT_NOT_VERIFIED'
     e=run([bin/'emit23',cnf,cert,proof],prefix.with_suffix('.emit.log'));r['standard_emit']=e
     if e['rc']==0:
      q=run([bin/'veripb','--cnf',cnf,proof],prefix.with_suffix('.standard.log'));r['standard_check']=q
      if q['rc']==0 and 's VERIFIED UNSATISFIABLE' in Path(q['log']).read_text():r['validation']='STANDARD_UNSAT'
   elif arm in ('kissat','cadical'):
    e=run([bin/arm,cnf,proof],prefix.with_suffix('.emit.log'));r['standard_emit']=e
    if e['rc']==20 and proof.exists():
     v=run([bin/'drat-trim',cnf,proof],prefix.with_suffix('.standard.log'));r['standard_check']=v
     if v['rc']==0 and 's VERIFIED' in Path(v['log']).read_text():r['validation']='STANDARD_UNSAT'
   # CMS and CP-SAT UNSAT: raw decision only, no supported checker in this harness.
   if r['validation']=='NONE':r['validation']='UNSAT_NOT_VERIFIED'
  r['matches_expected']=r['status']==meta['expected']
  r['contradicts_expected']=r['status'] in ('SAT','UNSAT') and not r['matches_expected']
  r['strict_custom_e2e_s']=a['seconds']+r.get('check',{}).get('seconds',0)
  r['standard_e2e_s']=a['seconds']+r.get('standard_emit',{}).get('seconds',0)+r.get('standard_check',{}).get('seconds',0)
  if arm=='drnas':r['standard_e2e_s']+=r.get('check',{}).get('seconds',0)
  if proof.exists():
   r['proof_bytes']=proof.stat().st_size;r['proof_sha256']=hashlib.file_digest(proof.open('rb'),'sha256').hexdigest();proof.unlink()
  meta['results'].append(r);(d/'result.json').write_text(json.dumps(meta,indent=2));print('SCALE25_ROW',json.dumps(r),flush=True)
 cnf.unlink()
if __name__=='__main__':
 if sys.argv[1]=='cp':cp_worker(sys.argv[2],sys.argv[3],sys.argv[4],int(sys.argv[5]),sys.argv[6])
 else:main(sys.argv[1],int(sys.argv[2]))
