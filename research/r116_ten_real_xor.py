#!/usr/bin/env python3
"""R116: structure-selected REAL official SATComp26 originals; not blind or leaderboard."""
import csv,hashlib,json,pathlib,subprocess,time,sys,collections,random
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'experiments/drnas_v16'))
import r32p_real_satcomp26_benchmark as r32p
SEED='75429ff7acb5acb597abe01aa745c2a6'
root=pathlib.Path('r116');root.mkdir(exist_ok=True)
uri='https://satcompetition.github.io/2026/downloads/track_main_2026.uri'
urls=r32p.request_url(uri,100000,seconds=45)[0].decode().splitlines()
ids=[u.strip().rsplit('/',1)[-1] for u in urls if u.strip()]
assert len(ids)==400
# Selection fixed BEFORE solving. Structural match: high complete parity clause coverage.
ranked=sorted((i for i in ids if i!=SEED),key=lambda i:hashlib.sha256(('R116-structural-selection-v1/'+i).encode()).hexdigest())
candidates=[SEED]+ranked[:180]
cases=[];attempts=[]
def parity_coverage(blob):
 groups=collections.defaultdict(set);total=0
 for line in blob.decode('ascii').splitlines():
  if not line or line[0] in 'cp%':continue
  try: a=[int(x) for x in line.split()]
  except ValueError:return 0
  if not a or a[-1]!=0:return 0
  v=a[:-1];total+=1
  if not 2<=len(v)<=6 or len({abs(x) for x in v})!=len(v):continue
  key=tuple(sorted(abs(x) for x in v))
  groups[key].add(tuple(sorted(v)))
 covered=0
 for key,patterns in groups.items():
  k=len(key)
  if len(patterns)>=2**(k-1):
   masks=set()
   for clause in patterns:
    masks.add(sum(1<<j for j,x in enumerate(key) if -x in clause))
   for parity in (0,1):
    expected={m for m in range(1<<k) if m.bit_count()%2==parity}
    if expected<=masks:covered+=len(expected)
 return covered/max(total,1)
for idx,id in enumerate(candidates):
 if len(cases)>=10:break
 try:
  raw,_=r32p.request_url('https://benchmark-database.de/file/'+id,2*1024*1024,seconds=12)
  plain,_=r32p.decode(raw)
  if len(plain)>2*1024*1024:raise ValueError('size')
  n,c=r32p.parse_dimacs_metadata(plain)
  coverage=parity_coverage(plain)
  # Structural threshold only; no solver runtime / correctness used to select.
  if coverage<.80 or n>3000 or c>150000:raise ValueError('structure_not_pure_xor')
  p=root/(id+'.cnf');p.write_bytes(plain)
  item=dict(id=id,sha256=hashlib.sha256(plain).hexdigest(),n=n,clauses=c,coverage=round(coverage,4),seed=id==SEED)
  cases.append(item);print('R116_SELECTED',json.dumps(item),flush=True)
 except Exception as e:
  attempts.append(dict(id=id,reason=str(e)[:100]))
print('R116_SELECTION',json.dumps(dict(selected=len(cases),examined=len(cases)+len(attempts))),flush=True)
(root/'selection.json').write_text(json.dumps(dict(cases=cases,attempts=attempts,selection='official 2026 fixed SHA-ranked candidates; parity coverage >=80%; no runtime selection',not_blind=True),indent=2))
if not cases:raise RuntimeError('No official parity-rich CNF downloaded')
bins={'drnas_r28':'./r116/r28','kissat':'./built/bin/kissat_4_0_4','cadical':'./built/bin/cadical_3_0_1'}
rows=[]
for item in cases:
 p=root/(item['id']+'.cnf')
 for rep in range(2):
  order=list(bins);random.Random(item['id']+str(rep)).shuffle(order)
  for name in order:
   t=time.perf_counter()
   cmd=[bins[name],str(p)]+([bins['kissat']] if name=='drnas_r28' else [])
   try:
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    elapsed=time.perf_counter()-t
    status='SAT' if result.returncode==10 else 'UNSAT' if result.returncode==20 else 'ERROR'
    route='pure_xor' if b'certified_pure_xor_sat' in result.stdout else 'xor_unsat' if b'certified_xor_contradiction' in result.stdout else 'fallback'
   except subprocess.TimeoutExpired:elapsed=60;status='TIMEOUT';route='timeout'
   if name=='drnas_r28' and status=='SAT' and route=='pure_xor':
    assert b's SATISFIABLE' in result.stdout
   row=dict(id=item['id'],rep=rep,solver=name,status=status,route=route,seconds=round(elapsed,6),par2=round(elapsed if status in ('SAT','UNSAT') else 120,6))
   rows.append(row);print('R116_RESULT',json.dumps(row),flush=True)
with (root/'paired.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
summary=[dict(solver=name,solved=sum(r['status'] in ('SAT','UNSAT') for r in rows if r['solver']==name),attempts=sum(r['solver']==name for r in rows),par2_sum=round(sum(r['par2'] for r in rows if r['solver']==name),4)) for name in bins]
(root/'summary.json').write_text(json.dumps(summary,indent=2))
print('R116_FINAL',json.dumps(summary),flush=True)
