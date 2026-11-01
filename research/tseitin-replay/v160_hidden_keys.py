#!/usr/bin/env python3
"""V16.0 novel-relations challenge, 7 previously unused transformations.
All cases created BEFORE any timings; no feature or label fed to solvers.
SAT witness on original CNF checked, native UNSAT proofs independently checked.
The UNSAT generators carry construction certificates (not solver DRAT).
"""
import collections,hashlib,json,random,statistics,subprocess,time,sys
from pathlib import Path
sys.path.insert(0,"research/tseitin-replay")
from v153_proof_checker import verify_certificate
SEED="V160-HIDDEN-KEYS-2026-11-01-FROZEN"
FAMILIES=("xor_bridge","xor_chain","binary_equivalence","sequential_counter",
          "graph_k4","hall_masked","guarded_parity")
SOLVERS={"kissat_api":"kissat_api_control","kissat_cli":"kissat_solver",
         "v1531":"v1531_nohang","v159":"v159_relational_dispatch"}
REPS=5;TIMEOUT=3
OUT=Path("v160-hidden-keys")
def xor(vs,rhs,rng):
 out=[]
 for mask in range(1<<len(vs)):
  if mask.bit_count()%2==rhs:continue
  c=[-v if mask>>i&1 else v for i,v in enumerate(vs)]
  rng.shuffle(c);out.append(c)
 return out
def gen(family,i):
 rng=random.Random(int(hashlib.sha256(f"{SEED}:{family}:{i}".encode()).hexdigest()[:16],16))
 unsat=bool(i%2);cl=[];n=64;planted={}
 if family=="xor_bridge":
  # a XOR b = 0 inferred by separate full XOR3 blocks.
  a,b,x,y=1,2,3,4
  cl+=xor([a,x,y],0,rng)+xor([b,x,y],0,rng)
  cl+=[[a],[-b]] if unsat else [[a],[b]]
 elif family=="xor_chain":
  # Chain of Tseitin XOR3 equalities, with consistent or opposite last bit.
  bits=[rng.randrange(2) for _ in range(10)]
  prev=1;cl.append([prev if bits[0] else -prev])
  for j in range(1,10):
   x=j+1;z=11+j
   cl+=xor([prev,x,z],0,rng)
   cl.append([x if bits[j] else -x])
   prev=z
  parity=0
  for bit in bits:parity^=bit
  cl.append([prev if parity^int(unsat) else -prev])
 elif family=="binary_equivalence":
  # a↔b via long binary implication cycle; cannot shortcut by name.
  for j in range(1,22):
   cl.extend([[-j,j+1],[j,-(j+1)]])
  cl.append([1]);cl.append([-22] if unsat else [22])
 elif family=="sequential_counter":
  # At least one pigeon per row, at most one per column, 5 vs 4
  # UNSAT deficiency is exact; SAT has 4 vs 4.
  H=4;B=5 if unsat else 4
  n=64
  def v(b,h):return b*H+h+1
  for b in range(B):cl.append([v(b,h) for h in range(H)])
  for h in range(H):
   for b in range(B):
    for j in range(b+1,B):cl.append([-v(b,h),-v(j,h)])
  # Redundant weakened clauses preserve satisfiability and obscure shape.
  for _ in range(12):
   c=rng.choice(cl)
   w=rng.randrange(30,65)
   cl.append(c+[rng.choice((-1,1))*w])
 elif family=="graph_k4":
  # 3-color graph with a hidden K4 for UNSAT.
  V=10;C=3
  def v(i,c):return i*C+c+1
  colors=[rng.randrange(C) for _ in range(V)]
  edges=set()
  for x in range(V):
   for y in range(x+1,V):
    if colors[x]!=colors[y] and rng.random()<.18:edges.add((x,y))
  if unsat:
   for x in range(4):
    for y in range(x+1,4):edges.add((x,y))
  for x in range(V):
   cl.append([v(x,c) for c in range(C)])
   for c in range(C):
    for d in range(c+1,C):cl.append([-v(x,c),-v(x,d)])
  for x,y in edges:
   for c in range(C):cl.append([-v(x,c),-v(y,c)])
 elif family=="hall_masked":
  # 4 mandatory rows restricted to 3 holes = Hall unsat; a SAT case
  # has four holes for four rows. Redundant clauses mask exact PHP.
  H=3 if unsat else 4;B=4
  def v(b,h):return b*4+h+1
  for b in range(B):cl.append([v(b,h) for h in range(H)])
  for h in range(H):
   for x in range(B):
    for y in range(x+1,B):cl.append([-v(x,h),-v(y,h)])
  for _ in range(16):
   c=rng.choice(cl);w=rng.randrange(25,65)
   cl.append(c+[w if rng.randrange(2) else -w])
 elif family=="guarded_parity":
  # Unit guard activates one of two contradictory parity equations.
  a,b,c,g=1,2,3,4
  cl+=xor([a,b,c],0,rng)
  for row in xor([a,b,c],1,rng):cl.append(row+([g] if unsat else [-g]))
  cl.append([-g] if unsat else [g])
 else:raise ValueError(family)
 # Add only redundant weakened clauses from exact original base.
 original=[c[:] for c in cl]
 for _ in range(20):
  c=rng.choice(original);w=rng.randrange(35,65)
  cl.append(c+[w if rng.randrange(2) else -w])
 perm=list(range(1,n+1));rng.shuffle(perm)
 cl=[[(1 if x>0 else -1)*perm[abs(x)-1] for x in row] for row in cl]
 for row in cl:rng.shuffle(row)
 rng.shuffle(cl)
 raw=("p cnf "+str(n)+" "+str(len(cl))+"\n"+"".join(" ".join(map(str,row))+" 0\n" for row in cl)).encode()
 return raw,n,cl,("UNSAT" if unsat else "SAT")
def check_sat(n,cls,model):
 vals={}
 for l in model:
  if abs(l)>n or not l:return False
  if abs(l) in vals and vals[abs(l)]!=(l>0):return False
  vals[abs(l)]=l>0
 return bool(vals) and all(any(vals.get(abs(l))==(l>0) for l in cl) for cl in cls)
def run(name,path,n,cls,expect):
 exe=str(Path("bin",SOLVERS[name]).resolve());cnf=str(path.resolve())
 cmd=([exe,cnf] if name in ("kissat_cli","kissat_api") else
      [exe,cnf,str(Path("bin/kissat_solver").resolve()),"1"])
 start=time.perf_counter()
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
 except subprocess.TimeoutExpired:return {"status":"TIMEOUT","seconds":TIMEOUT,"route":"timeout","correct":False}
 dt=time.perf_counter()-start
 tagged=[l.split("\t",1)[1] for l in p.stdout.splitlines() if l.startswith("DRNAS_HYBRID_RESULT\t")]
 if tagged:
  payload=json.loads(tagged[-1]);status=payload.get("status")
  route=payload.get("path");model=payload.get("model",[])
 else:
  payload=None
  if "s UNSATISFIABLE" in p.stdout:status="UNSAT"
  elif "s SATISFIABLE" in p.stdout:status="SAT"
  else:status="ERROR"
  model=[int(w) for l in p.stdout.splitlines() if l.startswith("v ") for w in l.split()[1:] if w!="0"]
  route="kissat_api" if name=="kissat_api" else ("kissat_cli" if name=="kissat_cli" else "fallback")
 valid=status==expect and (status!="SAT" or check_sat(n,cls,model))
 if status=="UNSAT" and payload:valid=valid and verify_certificate(payload,cls)
 return {"status":status,"seconds":round(dt,7),"route":route,"correct":valid}
def main():
 OUT.mkdir(exist_ok=True)
 records=[]
 for family in FAMILIES:
  for i in range(12):
   raw,n,cl,expected=gen(family,i)
   digest=hashlib.sha256(raw).hexdigest()
   p=OUT/(digest[:20]+".cnf");p.write_bytes(raw)
   records.append({"family":family,"index":i,"file":p.name,"sha256":digest,
                   "n":n,"expected":expected,"clauses":len(cl)})
 (OUT/"frozen-manifest.json").write_text(json.dumps(records,indent=2))
 assert len({x["sha256"] for x in records})==84
 print("V160_FROZEN",len(records),"families",len(FAMILIES),flush=True)
 rng=random.Random(160_2026_11_01)
 rows=[]
 for x in records:
  path=OUT/x["file"]
  assert hashlib.sha256(path.read_bytes()).hexdigest()==x["sha256"]
  raw,n,cl,label=gen(x["family"],x["index"])
  results=collections.defaultdict(list)
  for rep in range(REPS):
   order=list(SOLVERS);rng.shuffle(order)
   for name in order:
    v=run(name,path,n,cl,label);v["rep"]=rep
    results[name].append(v)
  for name,arr in results.items():
   assert all(r["correct"] for r in arr),(x["family"],x["index"],name,arr)
   rows.append({"family":x["family"],"index":x["index"],"solver":name,
                "median_seconds":statistics.median(r["seconds"] for r in arr),
                "routes":dict(collections.Counter(r["route"] for r in arr))})
 print("V160_VALID_ALL",len(records)*REPS*len(SOLVERS),flush=True)
 sums=collections.defaultdict(dict)
 for family in ["ALL"]+list(FAMILIES):
  for name in SOLVERS:
   sub=[z for z in rows if z["solver"]==name and (family=="ALL" or z["family"]==family)]
   sums[family][name]=round(sum(z["median_seconds"] for z in sub),7)
  print("V160_RESULT",family,json.dumps(sums[family],sort_keys=True),flush=True)
 (OUT/"results.json").write_text(json.dumps({"results":rows,"sums":sums,"cases":records,
    "repeats":REPS,"warning":"Synthetic generated hidden relations; not an external SAT benchmark or official ranking"},indent=2))
 print("V160_AUDIT_PASS",flush=True)
if __name__=="__main__":main()
