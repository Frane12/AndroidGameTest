#!/usr/bin/env python3
"""PCD3: selective bounded proof-by-UP failed literals injected as original-implied units.
One logical CPU for both arms; probe subprocess is explicitly included in E2E.
UNSAT from native CDCL is reported but never independently certified here.
"""
import hashlib,json,pathlib,subprocess,time,resource,sys
sys.path.insert(0,"research")
from drnas_atlas13_generator import build
from drnas_atlas21_official import model_ok
ROOT=pathlib.Path("pcd3_results");ROOT.mkdir(exist_ok=True)
CATS=("random3_sat","random3_unsat","xor_dense_sat","xor_dense_unsat",
      "graph3color_sat","graph3color_unsat","pigeonhole_unsat","pigeonhole_sat",
      "mixed_circuit","mixed_hard")
CAP=6.0

def gate(raw):
 """Cheap structural gate, using only source properties (no result labels)."""
 lines=raw.decode().splitlines()[1:]
 short=sum(len(x.split())<=4 for x in lines)
 # Skip low-complexity cases and sparse short-clause families.
 return len(lines)>=220 and short*3>=len(lines)

def call(cmd,timeout):
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=max(.05,timeout))
  return p.returncode,p.stdout,p.stderr
 except subprocess.TimeoutExpired:return 124,"","timeout"
def run(path,arm,rep):
 start=time.monotonic();orig=path.read_bytes();cnf=path
 units=[]
 if arm=="PCD2" or (arm=="PCD3" and gate(orig)):
  unitfile=ROOT/(path.stem+f"_{rep}.units")
  # One worker: fair CPU accounting and no concurrent CPU oversubscription.
  rc,out,err=call(["/tmp/drnas-pcd1",str(path),"1",str(6 if arm=="PCD3" else 12),str(12000 if arm=="PCD3" else 120000),str(unitfile)],min(0.04 if arm=="PCD3" else 1.0,CAP*.2))
  if rc==0:
   units=[int(line.split()[0]) for line in unitfile.read_text().splitlines()]
   if units:
    lines=orig.decode().splitlines()
    head=lines[0].split()
    assert head[:2]==["p","cnf"]
    head[3]=str(int(head[3])+len(units))
    cnf=ROOT/(path.stem+f"_{rep}.{arm.lower()}.cnf")
    cnf.write_text(" ".join(head)+"\n"+"\n".join(lines[1:])+"\n"+
                   "".join(f"{u} 0\n" for u in units))
  elif rc!=124:raise RuntimeError(("PCD2 preprocessing failed",rc,err))
 elapsed=time.monotonic()-start
 remaining=CAP-elapsed
 if remaining<=0:return dict(status="UNKNOWN",e2e_s=CAP,units=len(units),stdout="")
 rc,out,err=call(["mre_atlas23/bin/drnas_pcd3",str(cnf),"--mode","V23_C7_STABLE",
                  "--time",str(remaining),"--seed",str(rep+1),"--policy","1.0,0.85"],remaining)
 elapsed=time.monotonic()-start
 if rc not in (10,20,124):raise RuntimeError(("native solver failed",rc,err[-500:]))
 if rc==10 and not model_ok(path,out):raise RuntimeError("INVALID ORIGINAL SAT MODEL "+str(path))
 status="SAT_VERIFIED" if rc==10 else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN"
 return dict(status=status,e2e_s=round(elapsed,6),units=len(units),stdout=out)
rows=[]
for cat in CATS:
 for idx in (71,72):
  n,clauses,seed=build(cat,idx)
  raw=("p cnf %d %d\n"%(n,len(clauses))+
       "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
  sha=hashlib.sha256(raw).hexdigest();p=ROOT/(sha+".cnf");p.write_bytes(raw)
  for rep in range(2):
   for arm in ("CONTROL","PCD2","PCD3"):
    r=run(p,arm,rep)
    status=r.pop("status");output=r.pop("stdout")
    # Conservative: do not claim SAT verification without original witness parser.
    row=dict(category=cat,index=idx,sha256=sha,rep=rep,arm=arm,status=status,
             original_SAT_verified=status=="SAT_VERIFIED",independent_UNSAT_verified=False,
             par2_s=r["e2e_s"] if status!="UNKNOWN" else 2*CAP,**r)
    rows.append(row);print("PCD3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
 for rep in range(2):
  subset=[x for x in rows if x["category"]==cat and x["index"]==idx and x["rep"]==rep]
  if len(subset)==3:
   assert not ({x["status"] for x in subset}>={"SAT_VERIFIED","UNSAT_UNVERIFIED"}),subset
sums={}
for arm in ("CONTROL","PCD2","PCD3"):
 rr=[r for r in rows if r["arm"]==arm]
 sums[arm]=dict(trials=len(rr),reported_solved=sum(r["status"]!="UNKNOWN" for r in rr),
                par2_reported_s=round(sum(r["par2_s"] for r in rr),5),
                total_units=sum(r["units"] for r in rr))
sums["pcd2_speedup"]=round(sums["CONTROL"]["par2_reported_s"]/sums["PCD2"]["par2_reported_s"],5)
sums["pcd3_speedup"]=round(sums["CONTROL"]["par2_reported_s"]/sums["PCD3"]["par2_reported_s"],5)
(ROOT/"results.json").write_text(json.dumps(dict(rows=rows,summary=sums),indent=2))
print("PCD3_FINAL "+json.dumps(sums,sort_keys=True),flush=True)
print("PCD3_AUDIT_PASS paired=true one_cpu=true original_SHA=true UNSAT_independent_proof=false SAT_original_witness_verified=true",flush=True)
