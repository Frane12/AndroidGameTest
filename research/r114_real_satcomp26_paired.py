#!/usr/bin/env python3
"""R114 real SATComp2026 fixed manifest, paired Kissat vs R113. No official ranking."""
import argparse,csv,hashlib,json,pathlib,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r113_cheap_selector as selector
CAP=20.
def run(binary,cnf,cap):
 t=time.perf_counter()
 try:
  p=subprocess.run([str(binary),str(cnf)],capture_output=True,timeout=max(.02,cap))
  return ('SAT' if p.returncode==10 else 'UNSAT' if p.returncode==20 else 'ERROR',time.perf_counter()-t)
 except subprocess.TimeoutExpired:return 'TIMEOUT',cap
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--sources',required=True);ap.add_argument('--kissat',required=True);ap.add_argument('--native',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
 src=pathlib.Path(a.sources);out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((src/'manifest.json').read_text());rows=[]
 for c in manifest['cases']:
  p=src/c['filename']
  assert hashlib.sha256(p.read_bytes()).hexdigest()==c['sha256']
  for rep in range(2):
   baseline,bt=run(a.kissat,p,CAP)
   t=time.perf_counter();d=selector.decide(p,a.native,budget_s=.5);overhead=time.perf_counter()-t
   if d['decision']=='certified_unsat':status,total='UNSAT',overhead
   else:
    status,st=run(a.kissat,p,CAP-overhead);total=overhead+st
   expected=c['expected']
   for mode,s,sec in [('kissat',baseline,bt),('r113_kissat',status,total)]:
    if s in ('SAT','UNSAT') and s!=expected:raise RuntimeError('INCORRECT '+p.name+' '+mode)
    rows.append(dict(formula=p.name,sha256=c['sha256'],expected=expected,rep=rep,mode=mode,status=s,
      seconds=round(sec,6),par2=round(sec if s in ('SAT','UNSAT') else 2*CAP,6),
      gate=d['decision'] if mode=='r113_kissat' else ''))
 with (out/'paired.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 summary=[]
 for mode in ('kissat','r113_kissat'):
  r=[x for x in rows if x['mode']==mode]
  summary.append(dict(mode=mode,cases=len(manifest['cases']),trials=len(r),solved=sum(x['status'] in ('SAT','UNSAT') for x in r),
    par2_sum=round(sum(x['par2'] for x in r),6),wall_sum=round(sum(x['seconds'] for x in r),6)))
 (out/'summary.json').write_text(json.dumps(summary,indent=2))
 print('R114_REAL_RESULTS',json.dumps(summary),flush=True)
if __name__=='__main__':main()
