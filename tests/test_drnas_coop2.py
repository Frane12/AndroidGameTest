#!/usr/bin/env python3
import itertools,json,os,pathlib,random,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/drnas_coop1'))
from synthetic import encode,xor,and_xor,oracle,text,model_ok

def check_rup(cs,proof):
 db=[list(set(c)) for c in cs]
 for line in proof.splitlines():
  if not line.strip():continue
  assert not line.startswith('d ')
  c=list(map(int,line.split()));assert c.pop()==0
  values={};conflict=False
  for l in c:
   v=abs(l);b=l<0
   if v in values and values[v]!=b:conflict=True
   values[v]=b
  while not conflict:
   changed=False
   for d in db:
    if any(abs(l) in values and values[abs(l)]==(l>0) for l in d):continue
    free=[l for l in d if abs(l) not in values]
    if not free:conflict=True;break
    if len(free)==1:values[abs(free[0])]=free[0]>0;changed=True
   if not changed:break
  assert conflict,('not RUP',c)
  db.append(c)
 return len(db)-len(cs)

def run():
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 rng=random.Random(613119);cases=[(0,[]),(0,[[]]),(1,[[1],[-1]]),(3,[[1,1],[-1,2],[2,-2],[3]])]
 # Exhaust all 256 Boolean functions of 3 bits, including non-affine relations.
 for mask in range(256):cases.append((3,encode([1,2,3],lambda b:bool(mask&(1<<sum(v<<i for i,v in enumerate(b)))))))
 for _ in range(180):
  n=rng.randrange(2,11);cs=[]
  for _ in range(rng.randrange(n,6*n)):
   cs.append([v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))])
  cases.append((n,cs))
 # Hidden affine cancellation and nonlinear branch restriction.
 cases += [(4,xor([1,2,3],0)+xor([1,2,4],1)),
           (4,xor([1,2,3],0)+xor([1,2,4],1)+xor([3,4],0)),
           (5,and_xor([1,2,3,4],0)+and_xor([1,2,4,5],1)),
           (5,and_xor([1,2,3,4],0)+and_xor([1,2,4,5],1)+xor([3,5],0))]
 counts={'runs':0,'unsat_drat':0,'rup_steps':0,'lemmas':0,'conditioned':0,'applied_hints':0,'affine_windows':0,'nonaffine_windows':0}
 with tempfile.TemporaryDirectory() as td:
  p=pathlib.Path(td);cnf=p/'f.cnf';proof=p/'p.drat'
  for idx,(n,cs) in enumerate(cases):
   expected=oracle(n,cs);cnf.write_text(text(n,cs));off=None
   for mode in ['off','observe','algebra','on']:
    q=subprocess.run([str(ROOT/'build/drnas-coop2'),str(cnf),'--mode','core','--time','2','--stats','--x5-no-minimize','--coop2',mode,'--coop2-eager','--proof',str(proof)],capture_output=True,text=True,timeout=4)
    assert q.returncode==(10 if expected else 20),(idx,mode,q.stderr,cs)
    if expected:assert model_ok(n,cs,q.stdout),(idx,mode,q.stdout)
    counts['rup_steps']+=check_rup(cs,proof.read_text())
    if not expected:
     v=subprocess.run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,text=True,timeout=5)
     assert 's VERIFIED' in v.stdout,(idx,mode,v.stdout,v.stderr)
     counts['unsat_drat']+=1
    st=json.loads(next(l.split(' ',1)[1] for l in q.stderr.splitlines() if l.startswith('X5_STATS ')))
    search=json.loads(next(l.split(' ',1)[1] for l in q.stderr.splitlines() if l.startswith('X41_STATS ')))
    co=json.loads(next(l.split(' ',1)[1] for l in q.stderr.splitlines() if l.startswith('COOP2_STATS ')))
    for k in ['lemmas','conditioned','applied_hints','affine_windows','nonaffine_windows']:counts[k]+=co[k]
    if mode=='off':off=(st,search,q.stdout)
    if mode=='observe':
     assert st==off[0]
     for k in ['conflicts','decisions','propagations','learnt','restarts','reduce_removed']:assert search[k]==off[1][k],(idx,k)
     assert q.stdout==off[2]
    counts['runs']+=1
   if idx%100==0:print('COOP2_TEST_PROGRESS',idx,flush=True)
  for bad in ['p cnf 1 1\n2 0\n','p cnf 1 2\n1 0\n']:
   cnf.write_text(bad)
   q=subprocess.run([str(ROOT/'build/drnas-coop2'),str(cnf),'--coop2','on'],capture_output=True)
   assert q.returncode==1
  try:check_rup([[1,2]],'0\n')
  except AssertionError:pass
  else:raise AssertionError('false proof accepted')
 assert counts['lemmas']>0 and counts['conditioned']>0 and counts['applied_hints']>0,counts
 counts['status']='PASS';print('COOP2_SAFETY',json.dumps(counts),flush=True)
 (ROOT/'build/coop1_safety.json').write_text(json.dumps(counts,indent=2)+'\n')
if __name__=='__main__':run()
