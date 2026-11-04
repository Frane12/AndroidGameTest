#!/usr/bin/env python3
import csv,hashlib,json,pathlib,random,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r111_sensitive_safe_gate as gate
CAP=3.
def solve(binary,cnf,limit):
 t=time.perf_counter()
 try:
  p=subprocess.run([binary,str(cnf)],capture_output=True,text=True,timeout=max(.01,limit))
  return ('SAT' if p.returncode==10 else 'UNSAT' if p.returncode==20 else 'ERROR',time.perf_counter()-t)
 except subprocess.TimeoutExpired:return ('TIMEOUT',limit)
def main():
 out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
 native,solver=sys.argv[2:];rows=[];manifest=[]
 for family in ('xor_unsat','random3','planted_sat'):
  for i in range(8):
   rng=random.Random(20261104+i*101+len(family));n=45;clauses=[]
   if family=='xor_unsat':
    a,b=1+i,20+i
    clauses=[[a,b],[-a,-b],[a,-b],[-a,b]]
   else:
    witness={v:rng.choice((True,False)) for v in range(1,n+1)}
    for _ in range(180):
     vs=rng.sample(range(1,n+1),3)
     lits=[v if rng.randrange(2) else -v for v in vs]
     if family=='planted_sat' and not any((x>0)==witness[abs(x)] for x in lits):lits[0]=-lits[0]
     clauses.append(lits)
   p=out/(family+str(i)+'.cnf')
   p.write_text('p cnf %d %d\n'%(n,len(clauses))+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
   sha=hashlib.sha256(p.read_bytes()).hexdigest();manifest.append(dict(formula=p.name,family=family,sha256=sha))
   for rep in range(2):
    base,bt=solve(solver,p,CAP)
    t=time.perf_counter();d=gate.decide(p,native,threshold=.15,budget_s=.5);overhead=time.perf_counter()-t
    if d['decision']=='certified_unsat':status,total='UNSAT',overhead
    else:
     status,st=solve(solver,p,CAP-overhead);total=overhead+st
    if base in ('SAT','UNSAT') and status in ('SAT','UNSAT') and base!=status:raise RuntimeError('SOUNDNESS '+p.name)
    for mode,s,sec in [('minisat',base,bt),('r111_gate_minisat',status,total)]:
     rows.append(dict(formula=p.name,family=family,sha256=sha,rep=rep,mode=mode,status=s,
      time_s=round(sec,6),par2_s=round(sec if s in ('SAT','UNSAT') else 2*CAP,6),
      gate=d['decision'] if mode!='minisat' else ''))
 assert len(rows)==96
 with (out/'paired.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 summary=[]
 for family in ('xor_unsat','random3','planted_sat'):
  for mode in ('minisat','r111_gate_minisat'):
   subset=[r for r in rows if r['family']==family and r['mode']==mode]
   summary.append(dict(family=family,mode=mode,solved=sum(r['status'] in ('SAT','UNSAT') for r in subset),
    attempts=len(subset),par2_sum=round(sum(r['par2_s'] for r in subset),6)))
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 (out/'summary.json').write_text(json.dumps(summary,indent=2))
 print('R112_AUDIT',json.dumps(summary),flush=True)
if __name__=='__main__':main()
