#!/usr/bin/env python3
"""R131 historical forensic audit: 4 SHA-pinned R115/R117 real SAT formulas.
No training, no blind benchmark, no modification of R130. Structural replay
is independent of the solver implementation and checks source CNF identity.
"""
import collections,hashlib,json,pathlib,subprocess,sys
from collections import defaultdict
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent/'experiments/drnas_v16'))
import r32p_real_satcomp26_benchmark as source
ROOT=pathlib.Path("r131");ROOT.mkdir(exist_ok=True)
CASES=[
 ("R115_2026_SAT","75429ff7acb5acb597abe01aa745c2a6","243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83","SAT"),
 ("R117_2025_UNSAT","42f1311ce504db8cc0cb590a568da20a","9e4c57b9739f39a924d03267f05542831dc87fec9e9e2238f5e4ba11886378f4","UNSAT"),
 ("R117_2026_SAT","01d6fa8efd18ebfecd06af408958477b","6be9bfe6b44454a061a2e93350f589643f8a16f5bca6babdaa50a2d3d7069361","SAT"),
 ("R117_2026_UNSAT","0efcbd10294eb001b16b4d126923372f","84729f80119b50efac42d9477438abbc58c8712654ffe1fcdf9f324e44ae165d","UNSAT")]
def need(ok,msg):
 if not ok:raise RuntimeError("R131_FORENSIC_REFUSED "+str(msg))
def clauses_of(data):
 n=m=None;clauses=[];cl=[]
 for line in data.decode('ascii').splitlines():
  t=line.strip()
  if not t or t.startswith(('c','%')):continue
  if t.startswith('p '):
   _,fmt,nn,mm=t.split();need(fmt=='cnf','invalid header');n,m=int(nn),int(mm);continue
  for x in t.split():
   v=int(x)
   if v:cl.append(v)
   else:clauses.append(tuple(cl));cl=[]
 need(n is not None and m==len(clauses) and not cl,"incomplete CNF")
 need(all(abs(l)<=n and l!=0 for c in clauses for l in c),"literal bounds")
 return n,clauses
def equations_of(cs):
 groups=defaultdict(int);look=[];lengths=collections.Counter()
 for i,c in enumerate(cs):
  lengths[len(c)]+=1
  if not 2<=len(c)<=6 or len({abs(v) for v in c})!=len(c):continue
  vs=tuple(sorted(abs(v) for v in c));negative={abs(v) for v in c if v<0}
  mask=sum(1<<j for j,v in enumerate(vs) if v in negative)
  groups[vs]|=1<<mask;look.append((i,vs,mask))
 eqs=[];rec=defaultdict(int)
 for vs,masks in groups.items():
  for parity in (0,1):
   want=sum(1<<j for j in range(1<<len(vs)) if j.bit_count()%2==parity)
   if masks&want==want:
    eqs.append((vs,1-parity));rec[vs]|=want
 cov={i for i,vs,mask in look if rec[vs]&(1<<mask)}
 cov4={i for i,vs,mask in look if len(vs)<=4 and rec[vs]&(1<<mask)}
 details=dict(equations=len(eqs),widths=dict(sorted(collections.Counter(len(v) for v,r in eqs).items())),
   covered=len(cov),coverage_pct=round(100*len(cov)/max(1,len(cs)),3),
   equations_k2_k4=sum(len(v)<=4 for v,r in eqs),covered_k2_k4=len(cov4),
   coverage_k2_k4_pct=round(100*len(cov4)/max(1,len(cs)),3),
   clause_lengths=dict(sorted(lengths.items())))
 return eqs,details
def eliminate(eqs,clauses):
 basis={}
 for idx,(vs,rhs) in enumerate(eqs):
  b=sum(1<<v for v in vs);provenance=1<<idx
  while b:
   pivot=(b&-b).bit_length()-1
   if pivot not in basis:basis[pivot]=(b,rhs,provenance);break
   row,r,orig=basis[pivot];b^=row;rhs^=r;provenance^=orig
  if not b and rhs:
   chosen=[j for j in range(len(eqs)) if provenance>>j&1]
   vmask=0;rhs_xor=0
   for j in chosen:
    vs,r=eqs[j];rhs_xor^=r
    for v in vs:vmask^=1<<v
   need(vmask==0 and rhs_xor==1,"certificate replay failure")
   return dict(unsat=True,rank=len(basis),unsat_core_equations=len(chosen),unsat_core=[dict(vars=eqs[j][0],rhs=eqs[j][1]) for j in chosen],certified=True,sat_model_checked=False)
 truth=0
 for p in sorted(basis,reverse=True):
  row,r,_=basis[p]
  if r ^ ((row&truth).bit_count()&1):truth|=1<<p
 valid=all(any(((truth>>abs(l))&1)==(1 if l>0 else 0) for l in cl) for cl in clauses)
 return dict(unsat=False,rank=len(basis),unsat_core_equations=0,certified=False,sat_model_checked=valid)
def connected(eqs):
 roots={}
 def root(v):
  roots.setdefault(v,v)
  if roots[v]!=v:roots[v]=root(roots[v])
  return roots[v]
 for vs,_ in eqs:
  for v in vs[1:]:
   a,b=root(vs[0]),root(v)
   if a!=b:roots[b]=a
 count=collections.Counter(root(vs[0]) for vs,r in eqs)
 return dict(components=len(count),largest_equations=max(count.values(),default=0))
def classify(p,method):
 if method=="r28":cmd=["r131/r28",str(p),"unused-kissat","--classify-only"]
 elif method=="r118":cmd=["r131/r118",str(p),"unused-kissat","--classify-only"]
 else:cmd=["r131/r130_filter",str(p),"r131/r118","unused-kissat",method,"--probe-only"]
 proc=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
 need(proc.returncode==0,"native classifier crashed "+method+" "+proc.stderr[-200:])
 prefix={"r28":"c R28_ROUTE ","r118":"c R118_ROUTE "}.get(method,"c R130_SELECTOR ")
 found=[line for line in proc.stdout.splitlines() if line.startswith(prefix)]
 need(len(found)==1,"native route not found "+method)
 core=next((x for x in proc.stdout.splitlines() if "UNSAT_CERT ids=" in x),None)
 return dict(route=found[0],native_unsat_certificate=core)
def main():
 results=[]
 for label,id,expected,status in CASES:
  raw,_=source.request_url("https://benchmark-database.de/file/"+id,28*1024*1024,seconds=90)
  data,_=source.decode(raw)
  sha=hashlib.sha256(data).hexdigest();need(sha==expected,"source SHA changed "+label)
  path=ROOT/(id+".cnf");path.write_bytes(data)
  n,cs=clauses_of(data);eqs,st=equations_of(cs);proof=eliminate(eqs,cs)
  need(proof["unsat"]==(status=="UNSAT"),"independent SAT-UNSAT mismatch")
  if status=="SAT":need(st["covered"]==len(cs) and proof["sat_model_checked"],"SAT source model invalid")
  native={k:classify(path,k) for k in ("r28","r118","adaptive","q2_25","q1_0")}
  expected_route="certified_pure_xor_sat" if status=="SAT" else "certified_xor_contradiction"
  need(all(expected_route in native[k]["route"] for k in ("r28","r118")),"R28/R118 classifier mismatch")
  row=dict(label=label,id=id,sha256=sha,status=status,bytes=len(data),variables=n,clauses=len(cs),
           **st,**proof,graph=connected(eqs),classifiers=native)
  print("R131_FORENSIC_CASE",json.dumps(row,sort_keys=True),flush=True)
  results.append(row)
 report=dict(protocol="R131-FOUR-HISTORICAL-XOR-FORENSIC-20261105",cases=results,
             controls_are_PREVIOUSLY_SEEN=True,certificates_independently_replayed=True,
             source_sha_locked=True,no_world_record_claim=True)
 (ROOT/"forensic-report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
 print("R131_FORENSIC_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":main()
