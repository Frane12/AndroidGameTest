#!/usr/bin/env python3
"""R117 independently selected 50-case shard; record ALL exclusions, no substitutions."""
import argparse,csv,hashlib,json,pathlib,subprocess,time,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'experiments/drnas_v16'))
import r32p_real_satcomp26_benchmark as src
p=argparse.ArgumentParser();p.add_argument('--shard',type=int,required=True);a=p.parse_args()
assert 0<=a.shard<10
root=pathlib.Path('r117');manifest=json.loads((root/'manifest.json').read_text())
cases=manifest['cases'][a.shard*50:(a.shard+1)*50]
out=root/('shard%02d'%a.shard);out.mkdir(parents=True,exist_ok=True)
rows=[];download=[]
for item in cases:
 id=item['id']
 try:
  raw,_=src.request_url(item['url'],4*1024*1024,seconds=15)
  plain,_=src.decode(raw)
  if len(plain)>4*1024*1024:raise ValueError('decompressed_size_cap')
  n,c=src.parse_dimacs_metadata(plain)
  path=out/(id+'.cnf');path.write_bytes(plain)
  digest=hashlib.sha256(plain).hexdigest()
  download.append(dict(id=id,status='READY',sha256=digest,variables=n,clauses=c))
 except Exception as e:
  download.append(dict(id=id,status='EXCLUDED',reason=str(e)[:180]))
  continue
 for rep in range(2):
  for mode in (('drnas','kissat') if rep%2==0 else ('kissat','drnas')):
   cmd=['./r117/r28',str(path),'./built/bin/kissat_4_0_4'] if mode=='drnas' else ['./built/bin/kissat_4_0_4',str(path)]
   t=time.perf_counter()
   try:
    r=subprocess.run(cmd,capture_output=True,timeout=5)
    sec=time.perf_counter()-t
    status='SAT' if r.returncode==10 else 'UNSAT' if r.returncode==20 else 'ERROR'
    route='pure_xor' if b'certified_pure_xor_sat' in r.stdout else 'xor_unsat' if b'certified_xor_contradiction' in r.stdout else 'fallback'
   except subprocess.TimeoutExpired:sec=5.;status='TIMEOUT';route='timeout'
   rows.append(dict(id=id,year=item['year'],sha256=digest,rep=rep,mode=mode,status=status,route=route,seconds=round(sec,6),par2=round(sec if status in ('SAT','UNSAT') else 10.,6)))
   print('R117_RESULT',json.dumps(rows[-1]),flush=True)
   if mode=='drnas' and status=='SAT' and route=='pure_xor':
    assert b's SATISFIABLE' in r.stdout
with (out/'results.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['id','year','sha256','rep','mode','status','route','seconds','par2']);w.writeheader();w.writerows(rows)
(out/'download_audit.json').write_text(json.dumps(download,indent=2))
print('R117_SHARD_FINAL',json.dumps(dict(shard=a.shard,selected=len(cases),downloaded=sum(x['status']=='READY' for x in download),attempts=len(rows))),flush=True)
