#!/usr/bin/env python3
"""R118 proof-on-demand XOR specialization. Pinned REAL sources, not a blind holdout.
Independent source-clause SAT model and XOR UNSAT-certificate checks.
"""
import argparse,csv,hashlib,json,os,pathlib,random,re,subprocess,sys,time,collections
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'experiments/drnas_v16'))
import r32p_real_satcomp26_benchmark as source

PINNED=[
 dict(id='75429ff7acb5acb597abe01aa745c2a6',year=2026,expected='SAT',sha256='243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83',study='R115 historical'),
 dict(id='42f1311ce504db8cc0cb590a568da20a',year=2025,expected='UNSAT',sha256='9e4c57b9739f39a924d03267f05542831dc87fec9e9e2238f5e4ba11886378f4',study='R117 discovery'),
 dict(id='01d6fa8efd18ebfecd06af408958477b',year=2026,expected='SAT',sha256='6be9bfe6b44454a061a2e93350f589643f8a16f5bca6babdaa50a2d3d7069361',study='R117 discovery'),
 dict(id='0efcbd10294eb001b16b4d126923372f',year=2026,expected='UNSAT',sha256='84729f80119b50efac42d9477438abbc58c8712654ffe1fcdf9f324e44ae165d',study='R117 discovery'),
]
CAP=15.0;REPS=3

def parse_cnf(data):
 n=nc=None;clauses=[];current=[]
 for line in data.decode('ascii').splitlines():
  s=line.strip()
  if not s or s.startswith('c') or s.startswith('%'):continue
  if s.startswith('p '):
   parts=s.split();assert len(parts)==4 and parts[1]=='cnf'
   n,nc=int(parts[2]),int(parts[3]);continue
  for token in s.split():
   x=int(token)
   if x:current.append(x)
   else:clauses.append(tuple(current));current=[]
 assert n is not None and not current and len(clauses)==nc
 assert all(1<=abs(x)<=n for cl in clauses for x in cl)
 return n,clauses

def check_sat_model(stdout,n,clauses):
 model={}
 for line in stdout.decode('ascii',errors='replace').splitlines():
  if not line.startswith('v '):continue
  for token in line[2:].split():
   lit=int(token)
   if lit:model[abs(lit)]=(lit>0)
 assert len(model)==n,('incomplete model',len(model),n)
 assert all(any(model[abs(v)]==(v>0) for v in clause) for clause in clauses),'SAT model does not satisfy original source clauses'

def check_unsat_cert(stdout,clauses,prefix):
 text=stdout.decode('ascii',errors='replace')
 eqs={}
 for line in text.splitlines():
  if line.startswith('c '+prefix+'_EQ '):
   m=re.fullmatch(r'c '+prefix+r'_EQ id=(\d+) rhs=([01]) vars=([\d,]+)',line)
   assert m,('bad equation format',line)
   i,rhs=int(m.group(1)),int(m.group(2))
   variables=tuple(int(x) for x in m.group(3).split(','))
   assert variables==tuple(sorted(set(variables))) and 2<=len(variables)<=6
   eqs[i]=(rhs,variables)
 line=next((s for s in text.splitlines() if s.startswith('c '+prefix+'_UNSAT_CERT ids=')),None)
 assert line and eqs,'missing proof trace'
 selected=[int(x) for x in line.split('ids=',1)[1].split(',') if x]
 assert len(selected)==len(set(selected)) and selected
 full={}
 for cl in clauses:
  vars=tuple(sorted(abs(v) for v in cl))
  if len(cl)!=len(vars):continue
  mask=sum(1<<i for i,v in enumerate(vars) if -v in cl)
  full.setdefault(vars,set()).add(mask)
 lhs=set();rhs=0
 for i in selected:
  assert i in eqs,('missing equation ID',i)
  parity,variables=eqs[i]
  k=len(variables)
  required={mask for mask in range(1<<k) if (mask.bit_count()%2)==(1-parity)}
  assert required<=full.get(variables,set()),('not a complete source XOR block',i)
  rhs^=parity
  for v in variables:
   if v in lhs:lhs.remove(v)
   else:lhs.add(v)
 assert not lhs and rhs==1,'certificate XOR does not equal 0=1'
 return len(selected)

def run(binary,src,kissat,cap):
 cmd=[str(binary),str(src),str(kissat)] if binary.name.startswith('r1') else [str(binary),str(src)]
 t=time.perf_counter()
 try:
  p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap)
  sec=time.perf_counter()-t
  status='SAT' if p.returncode==10 else 'UNSAT' if p.returncode==20 else 'ERROR'
  out=p.stdout
 except subprocess.TimeoutExpired:status='TIMEOUT';sec=cap;out=b''
 return status,sec,out

def run_pair(src,expected,sha,n,clauses,rep,binaries,out_rows,key):
 order=list(binaries)
 random.Random(key+'-'+str(rep)).shuffle(order)
 for mode in order:
  t=time.perf_counter()
  command=([str(binaries[mode]),str(src),str(binaries['kissat'])] if mode in ('r28','r118') else [str(binaries['kissat']),str(src)])
  try:
   p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
   elapsed=time.perf_counter()-t
   status='SAT' if p.returncode==10 else 'UNSAT' if p.returncode==20 else 'ERROR'
   lines=p.stdout
   route=next((x for x in ['certified_pure_xor_sat','certified_xor_contradiction','fallback'] if x.encode() in lines),'native_kissat')
   if status in ('SAT','UNSAT'):
    assert status==expected,('WRONG ANSWER',key,mode,expected,status)
   if mode in ('r28','r118'):
    if route=='certified_pure_xor_sat':
     assert status=='SAT'
     check_sat_model(lines,n,clauses)
    if route=='certified_xor_contradiction':
     assert status=='UNSAT'
     cert_count=check_unsat_cert(lines,clauses,'R28' if mode=='r28' else 'R118')
    else:cert_count=0
   else:cert_count=0
   if status=='ERROR':raise RuntimeError('Solver exited ERROR '+mode+' '+str(p.returncode)+' '+p.stderr[-350:].decode(errors='replace'))
  except subprocess.TimeoutExpired:
   elapsed=CAP;status='TIMEOUT';route='timeout';cert_count=0
  row=dict(id=key,rep=rep,mode=mode,status=status,route=route,seconds=round(elapsed,6),par2=round(elapsed if status in ('SAT','UNSAT') else CAP*2,6),cert_equations=cert_count,sha256=sha)
  out_rows.append(row)
  print('R118_REAL_RESULT',json.dumps(row,sort_keys=True),flush=True)

def main():
 root=pathlib.Path('r118');root.mkdir(exist_ok=True)
 bins={name:pathlib.Path(path).resolve() for name,path in [('r28','r118/r28'),('r118','r118/r118'),('kissat','built/bin/kissat_4_0_4')]}
 assert all(b.exists() for b in bins.values())
 cases=[];results=[]
 for pinned in PINNED:
  raw,_=source.request_url('https://benchmark-database.de/file/'+pinned['id'],8*1024*1024,seconds=60)
  plain,_=source.decode(raw)
  sha=hashlib.sha256(plain).hexdigest()
  assert sha==pinned['sha256'],('PINNED SOURCE SHA MISMATCH',pinned['id'],sha)
  n,clauses=parse_cnf(plain)
  path=root/(pinned['id']+'.cnf');path.write_bytes(plain)
  cases.append(dict(**pinned,bytes=len(plain),n=n,clauses=len(clauses)))
  print('R118_SOURCE',json.dumps(cases[-1],sort_keys=True),flush=True)
  for rep in range(REPS):
   run_pair(path,pinned['expected'],sha,n,clauses,rep,bins,results,pinned['id'])
 (root/'source_manifest.json').write_text(json.dumps(cases,indent=2)+'\n')
 with (root/'paired.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 summary=[]
 for mode in ('r28','r118','kissat'):
  a=[v for v in results if v['mode']==mode]
  summary.append(dict(mode=mode,attempts=len(a),solved=sum(v['status'] in ('SAT','UNSAT') for v in a),
       par2_sum=round(sum(v['par2'] for v in a),6),wall_sum=round(sum(v['seconds'] for v in a),6),
       certified=sum(v['route'].startswith('certified_') for v in a)))
 (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print('R118_FINAL',json.dumps(summary),flush=True)

if __name__=='__main__':main()
