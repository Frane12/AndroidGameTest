#!/usr/bin/env python3
"""R115 fixed-source 250-variable SATComp26 same-host repeat; never call a timeout exact speed."""
import csv,hashlib,json,pathlib,subprocess,time,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'experiments/drnas_v16'))
import r32p_real_satcomp26_benchmark as r32p
ID='75429ff7acb5acb597abe01aa745c2a6'
out=pathlib.Path('r115');out.mkdir(exist_ok=True)
raw,_=r32p.request_url('https://benchmark-database.de/file/'+ID,28*1024*1024,seconds=60)
plain,_=r32p.decode(raw)
n,c=r32p.parse_dimacs_metadata(plain)
assert (n,c)==(250,1000),(n,c)
p=out/(ID+'.cnf');p.write_bytes(plain)
print('R115_SOURCE',json.dumps(dict(id=ID,sha256=hashlib.sha256(plain).hexdigest(),variables=n,clauses=c,bytes=len(plain))),flush=True)
bins={'r28':'./r115/r28','kissat':'./built/bin/kissat_4_0_4','cadical':'./built/bin/cadical_3_0_1'}
rows=[]
for rep in range(5):
 for name in (('r28','kissat','cadical') if rep%2==0 else ('cadical','kissat','r28')):
  start=time.perf_counter()
  try:
   cmd=[bins[name],str(p)]
   if name=='r28':cmd.append(bins['kissat'])
   proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
   elapsed=time.perf_counter()-start
   status='SAT' if proc.returncode==10 else 'UNSAT' if proc.returncode==20 else 'ERROR'
   if status=='SAT' and name=='r28':
    assert b'certified_pure_xor_sat' in proc.stdout,proc.stdout[-1000:]
   if status=='UNSAT' and name=='r28':
    assert b'certified_xor_contradiction' in proc.stdout
  except subprocess.TimeoutExpired:
   elapsed=60.;status='TIMEOUT'
  rows.append(dict(repeat=rep,solver=name,status=status,seconds=round(elapsed,6),par2=round(elapsed if status in ('SAT','UNSAT') else 120.,6)))
  print('R115_RESULT',json.dumps(rows[-1]),flush=True)
with (out/'paired.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(out/'summary.json').write_text(json.dumps(rows,indent=2))
