#!/usr/bin/env python3
"""R119: circuit-equivalence SAT miters, deterministic engineering-realistic XOR/Tseitin test.

All circuits are newly generated, NOT extracted from industry designs or SAT Competition.
R28/R118/Kissat/CryptoMiniSat solve unchanged original CNF on identical runner.
Builds disjoint restructured implementations of the same parity function, tests whether
a mismatch is possible, and verifies ground truth from exact Boolean semantics.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,pathlib,random,subprocess,sys,time
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from r118_xor_paired_real import parse_cnf,check_sat_model,check_unsat_cert

SEED="DRNAS-R119-LOGIC-EQUIVALENCE-FIXED-20261104-V1"
REPS=2
CAP=3.0
SHARDS=8
PER_FAMILY=48
FAMILIES=("linear_equiv","linear_inequiv","mixed_equiv","mixed_inequiv")

class Circuit:
 def __init__(self,n):
  self.n=n;self.next=n;self.clauses=[];self.gates=[]
  self.affine={i:1<<(i-1) for i in range(1,n+1)}
 def new(self,kind,a,b):
  self.next+=1;z=self.next
  self.gates.append((kind,a,b,z))
  if kind=="XOR":
   for va in (0,1):
    for vb in (0,1):
     vz=1-(va^vb)
     self.clauses.append(tuple((-x if value else x) for x,value in ((a,va),(b,vb),(z,vz))))
   self.affine[z]=self.affine[a]^self.affine[b]
  elif kind=="AND":
   self.clauses.extend([(-a,-b,z),(a,-z),(b,-z)])
  elif kind=="OR":
   self.clauses.extend([(-a,z),(-b,z),(a,b,-z)])
  else:raise ValueError(kind)
  return z
 def parity(self,vars_,method,rng):
  vs=list(vars_)
  if method=="shuffle":rng.shuffle(vs)
  if method=="reverse":vs.reverse()
  if method=="chain":
   v=vs[0]
   for x in vs[1:]:v=self.new("XOR",v,x)
   return v
  while len(vs)>1:
   next_level=[]
   for i in range(0,len(vs)-1,2):next_level.append(self.new("XOR",vs[i],vs[i+1]))
   if len(vs)%2:next_level.append(vs[-1])
   vs=next_level
  return vs[0]
 def and_or(self,kind,a,b):
  return self.new(kind,a,b)
 def mismatch(self,a,b):
  assert a!=b
  self.clauses.extend([(a,b),(-a,-b)])
 def evaluation(self,inputbits,a,b):
  val={i:bool(inputbits&(1<<(i-1))) for i in range(1,self.n+1)}
  for kind,x,y,z in self.gates:
   if kind=="XOR":val[z]=val[x]!=val[y]
   elif kind=="AND":val[z]=val[x] and val[y]
   elif kind=="OR":val[z]=val[x] or val[y]
  return val[a]!=val[b]
 def dimacs(self,meta):
  header="c R119 deterministic digital circuit SAT miter; NOT official CNF\n"
  header+="c family="+meta["family"]+" seed="+str(meta["seed"])+" expected="+meta["expected"]+"\n"
  header+=f"p cnf {self.next} {len(self.clauses)}\n"
  return (header+"".join(" ".join(map(str,cl))+" 0\n" for cl in self.clauses)).encode()

def make(case_id,family):
 # Stable independent seed for every formula.
 seed=int(hashlib.sha256((SEED+"/"+family+"/"+str(case_id)).encode()).hexdigest()[:15],16)
 rng=random.Random(seed)
 linear=family.startswith("linear")
 inequivalent=family.endswith("inequiv")
 n=([12,40,96,256][case_id%4] if linear else 10)
 c=Circuit(n)
 if linear:
  k=([8,30,72,192][case_id%4])
  pool=list(range(1,n+1))
  chosen=rng.sample(pool,k)
  b_chosen=list(chosen)
  if inequivalent:
   extra=rng.choice([x for x in pool if x not in chosen])
   b_chosen[-1]=extra
  a=c.parity(chosen,"chain" if case_id%2 else "balanced",rng)
  b=c.parity(b_chosen,"shuffle" if case_id%2 else "reverse",rng)
  expected="SAT" if c.affine[a]!=c.affine[b] else "UNSAT"
  assert expected==("SAT" if inequivalent else "UNSAT")
 else:
  allvars=list(range(1,n+1));s1=rng.sample(allvars,5);s2=rng.sample(allvars,6)
  while set(s1)==set(s2):s2=rng.sample(allvars,6)
  p1a=c.parity(s1,"chain",rng);p2a=c.parity(s2,"balanced",rng)
  p1b=c.parity(s1,"shuffle",rng);p2b=c.parity(s2,"reverse",rng)
  a=c.and_or("AND",p1a,p2a)
  b=c.and_or("OR" if inequivalent else "AND",p1b,p2b)
  differences=sum(c.evaluation(bits,a,b) for bits in range(1<<n))
  expected="SAT" if differences else "UNSAT"
  assert expected==("SAT" if inequivalent else "UNSAT")
 c.mismatch(a,b)
 meta=dict(id=f"{family}-{case_id:03d}",family=family,seed=seed,expected=expected,
           variables=c.next,clauses=len(c.clauses),xor_gates=sum(g[0]=="XOR" for g in c.gates),
           nonlinear_gates=sum(g[0]!="XOR" for g in c.gates),
           source="deterministically generated XOR/AND/OR gate-level netlists, NOT official")
 return c.dimacs(meta),meta

def freeze(root):
 root.mkdir(parents=True,exist_ok=True)
 (root/"cnf").mkdir(exist_ok=True)
 cases=[]
 for family in FAMILIES:
  for idx in range(PER_FAMILY):
   data,item=make(idx,family)
   item["sha256"]=hashlib.sha256(data).hexdigest()
   path=root/"cnf"/(item["id"]+".cnf")
   path.write_bytes(data)
   item["bytes"]=len(data)
   cases.append(item)
 assert len(cases)==PER_FAMILY*len(FAMILIES)==192
 assert len({x["sha256"] for x in cases})==len(cases)
 manifest={"protocol":SEED,"family_counts":dict(Counter(x["family"] for x in cases)),
   "cases":cases,"repetitions":REPS,"cap_seconds":CAP,"shards":SHARDS,
   "selection":"fixed generation seeds and families, no runtime-based selection",
   "source_type":"generated circuit-equivalence test, not harvested hardware and not SAT Competition"}
 (root/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
 (root/"source.sha256").write_text("".join(f'{c["sha256"]}  cnf/{c["id"]}.cnf\n' for c in cases))
 print("R119_FREEZE",json.dumps({k:v for k,v in manifest.items() if k!="cases"}),flush=True)

def run_solver(mode,src,binaries):
 if mode in ("r28","r118"):
  cmd=[str(binaries[mode]),str(src),str(binaries["kissat"])]
 elif mode=="cryptominisat":cmd=[str(binaries[mode]),str(src)]
 else:cmd=[str(binaries[mode]),str(src)]
 t=time.perf_counter()
 try:
  p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  sec=time.perf_counter()-t
  stdout=p.stdout
  if p.returncode==10:status="SAT"
  elif p.returncode==20:status="UNSAT"
  elif p.returncode in (0,):
   if b"s UNSATISFIABLE" in stdout:status="UNSAT"
   elif b"s SATISFIABLE" in stdout:status="SAT"
   else:status="ERROR"
  else:status="ERROR"
  route=(next((x for x in ("certified_pure_xor_sat","certified_xor_contradiction","fallback") if x.encode() in stdout),"native") if mode in ("r28","r118") else "baseline")
  if status=="ERROR":raise RuntimeError(f"bad solver status {mode} code={p.returncode} stderr={p.stderr[-400:]!r}")
 except subprocess.TimeoutExpired:
  sec=CAP;status="TIMEOUT";stdout=b"";route="timeout"
 return status,sec,stdout,route

def execute(root,shard):
 manifest=json.loads((root/"manifest.json").read_text())
 assert manifest["protocol"]==SEED and len(manifest["cases"])==192
 cases=[c for i,c in enumerate(manifest["cases"]) if i%SHARDS==shard]
 assert len(cases)==24
 binaries={n:Path(p).resolve() for n,p in (("r28","r119/r28"),("r118","r119/r118"),("kissat","built/bin/kissat_4_0_4"),("cryptominisat",os.environ.get("CRYPTOMINISAT_BIN","/usr/bin/cryptominisat5")))}
 assert all(p.exists() for p in binaries.values()),binaries
 # Force all competing subprocesses onto the same single logical CPU.
 cpus=sorted(os.sched_getaffinity(0))
 os.sched_setaffinity(0,{cpus[0]})
 out=root/f"shard-{shard:02d}";out.mkdir(exist_ok=True)
 results=[]
 for c in cases:
  src=root/"cnf"/(c["id"]+".cnf")
  data=src.read_bytes()
  assert hashlib.sha256(data).hexdigest()==c["sha256"]
  n,clauses=parse_cnf(data)
  assert n==c["variables"] and len(clauses)==c["clauses"]
  for rep in range(REPS):
   order=list(binaries)
   random.Random(SEED+c["id"]+str(rep)).shuffle(order)
   for mode in order:
    status,sec,stdout,route=run_solver(mode,src,binaries)
    if status in ("SAT","UNSAT"):
     assert status==c["expected"],("INCORRECT_ANSWER",c["id"],mode,status,c["expected"])
     if mode in ("r28","r118"):
      if route=="certified_pure_xor_sat":
       assert status=="SAT"
       check_sat_model(stdout,n,clauses)
      elif route=="certified_xor_contradiction":
       assert status=="UNSAT"
       check_unsat_cert(stdout,clauses,"R28" if mode=="r28" else "R118")
      elif route!="fallback":raise AssertionError(("Missing DRNAS route",c["id"],mode))
     if status=="SAT" and any(line.startswith(b"v ") for line in stdout.splitlines()):
      check_sat_model(stdout,n,clauses)
    row=dict(id=c["id"],family=c["family"],sha256=c["sha256"],seed=c["seed"],
             rep=rep,mode=mode,status=status,route=route,
             seconds=round(sec,6),par2=round(sec if status in ("SAT","UNSAT") else 2*CAP,6))
    results.append(row)
    print("R119_RESULT",json.dumps(row,sort_keys=True),flush=True)
 with (out/"paired.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 summary=[]
 for family in FAMILIES:
  for mode in binaries:
   rr=[r for r in results if r["family"]==family and r["mode"]==mode]
   summary.append(dict(shard=shard,family=family,mode=mode,cases=len(rr)//REPS,
                       solved=sum(r["status"] in ("SAT","UNSAT") for r in rr),
                       attempts=len(rr),par2_sum=round(sum(r["par2"] for r in rr),5),
                       direct=sum(r["route"].startswith("certified_") for r in rr)))
 (out/"summary.json").write_text(json.dumps(summary,indent=2))
 print("R119_SHARD_FINAL",json.dumps(dict(shard=shard,attempts=len(results),cases=len(cases),
    direct=sum(x["route"].startswith("certified_") for x in results))),flush=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument("action",choices=["freeze","run"]);ap.add_argument("--root",default="r119");ap.add_argument("--shard",type=int,default=0);a=ap.parse_args()
 if a.action=="freeze":freeze(Path(a.root))
 else:execute(Path(a.root),a.shard)
if __name__=="__main__":main()
