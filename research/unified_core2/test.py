import sys,itertools,random,tempfile,subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parents[2];B=R/'build/drnas-unified-core2'
sys.path.insert(0,str(R/'research/xor_math5_unified1'))
from test import eo,xor,verified_sat,make_cnf
rng=random.Random(1771);count=0;kinds={}
with tempfile.TemporaryDirectory() as td:
 t=Path(td)
 fixtures=[(6,eo([[1,2,3,4],[1,2,5,6],[3,4,5,6]])),(3,xor(3,0)+xor(3,1)),(3,xor(3,1)),(1,[[1],[-1]])]
 # pigeonhole: three requirements, two mutually exclusive resources.
 groups=[[1,2],[3,4],[5,6]]
 fixtures.append((6,groups+[[-a,-b] for g in [[1,3,5],[2,4,6]] for a,b in itertools.combinations(g,2)]))
 for _ in range(100):
  n=rng.randrange(2,9);cs=[]
  for j in range(rng.randrange(1,28)):
   cs.append([v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),rng.randrange(1,min(4,n)+1))])
  fixtures.append((n,cs))
 for i,(n,cs) in enumerate(fixtures):
  sat=any(all(any(bool(bits[abs(l)-1])==(l>0) for l in c) for c in cs) for bits in itertools.product([0,1],repeat=n))
  for mode in ['off','strict','full']:
   cnf=t/f'{i}-{mode}.cnf';cert=t/f'{i}-{mode}.json';proof=t/f'{i}-{mode}.drat';make_cnf(cnf,cs,n)
   cmd=[str(B),str(cnf),'--time','3','--proof',str(proof)]
   if mode=='off':cmd+=['--unified-off']
   if mode=='full':cmd+=['--certificate',str(cert)]
   p=subprocess.run(cmd,capture_output=True,text=True,timeout=6)
   assert p.returncode==(10 if sat else 20),(i,mode,p.returncode,p.stderr)
   if sat:assert verified_sat(cs,n,p.stdout)
   elif cert.exists():
    assert proof.stat().st_size==0
    q=subprocess.run([sys.executable,str(R/'research/unified_core1/check.py'),str(cnf),str(cert)],capture_output=True,text=True)
    assert q.returncode==0,(i,q.stdout,q.stderr)
    fmt=json.loads(cert.read_text())['format'];kinds[fmt]=kinds.get(fmt,0)+1
    bad=json.loads(cert.read_text());bad['source_sha256']='0'*64;cert.write_text(json.dumps(bad))
    assert subprocess.run([sys.executable,str(R/'research/unified_core1/check.py'),str(cnf),str(cert)],capture_output=True).returncode!=0
   else:
    assert proof.stat().st_size>0
    if (R/'build/drat-trim').exists():
     q=subprocess.run([str(R/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,text=True)
     assert q.returncode==0 and 'VERIFIED' in q.stdout,(i,mode,q.stdout)
   count+=1
 assert any('math5' in k for k in kinds),kinds
 assert any('hall' in k for k in kinds),kinds
 print('UNIFIED_PREFLIGHT_PASS',json.dumps({'executions':count,'structural_formats':kinds,'drat_checked':(R/'build/drat-trim').exists()}))
# Exercise BDD capacity and ARG3 in isolation, without another constructor winning first.
sys.path.insert(0,str(R/'research/pcmax_capacity/tests'))
from make_fixtures import build_scheduling
sys.path.insert(0,str(R/'research/cdcl299'))
from test_arg3 import generate
with tempfile.TemporaryDirectory() as td:
 t=Path(td)
 n,cs,_,_=build_scheduling([2,2,2],2,2)
 cnf=t/'bdd.cnf';cert=t/'bdd.json';make_cnf(cnf,cs,n)
 p=subprocess.run([str(B),str(cnf),'--time','3','--unified-mask','4','--unified-ms','500','--certificate',str(cert)],capture_output=True,text=True,timeout=5)
 assert p.returncode==20 and cert.exists(),(p.returncode,p.stderr)
 q=subprocess.run([sys.executable,str(R/'research/unified_core1/check.py'),str(cnf),str(cert)],capture_output=True,text=True)
 assert q.returncode==0,(q.stdout,q.stderr)
 for seed in range(4):
  n,cs=generate(0x10292025+seed)
  cnf=t/f'arg{seed}.cnf';make_cnf(cnf,cs,n)
  p=subprocess.run([str(B),str(cnf),'--time','3','--unified-mask','8','--stats'],capture_output=True,text=True,timeout=5)
  assert p.returncode==10 and verified_sat(cs,n,p.stdout),(seed,p.returncode,p.stderr)
  meta=next(json.loads(l.split(' ',1)[1]) for l in p.stderr.splitlines() if l.startswith('SAT_ARG3_STATS '))
  assert meta['recognized'] and meta['found'],meta
 print('UNIFIED_BDD_ARG3_PASS')
