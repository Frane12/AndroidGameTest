#!/usr/bin/env python3
"""R122 circuit-miter engineering benchmark: 96 seen + 96 NEW deterministic mixed gates.
All source CNFs SHA-pinned BEFORE any timing; independent exhaustive UNSAT check.
R122 C++ is allowed to conclude only if full CNF has verified gate/miter encoding.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,pathlib,random,subprocess,sys,time
from collections import Counter
from pathlib import Path
import r119_logic_equiv as old
from r118_xor_paired_real import parse_cnf,check_sat_model,check_unsat_cert

PROTO="DRNAS-R122-MIXED-AND-OR-ANF-20261105-V1"
FAMILIES=("mixed_equiv","mixed_inequiv")
NEW_SEED="DRNAS-R122-MIXED-AND-OR-NEW-EXTERNAL-TO-R119-20261105"
CAP=3.0
REPS=2
SHARDS=8
SOLVERS=("r118","r122","kissat","cryptominisat")

def full_gate_proof(cnf,expected):
 """Independent Python source-clause exactness plus exhaustive primary-input equivalence."""
 n,clauses=parse_cnf(cnf)
 original={tuple(sorted(cl)) for cl in clauses}
 assert len(original)==len(clauses)
 def gcl(op,a,b,z):
  if op=="X":raw=[(a,b,-z),(a,-b,z),(-a,b,z),(-a,-b,-z)]
  elif op=="A":raw=[(-a,-b,z),(a,-z),(b,-z)]
  else:raw=[(-a,z),(-b,z),(a,b,-z)]
  return {tuple(sorted(c)) for c in raw}
 candidates=set()
 for cl in clauses:
  if len(cl)==3 and len({abs(x) for x in cl})==3:
   a,b,z=sorted(abs(x) for x in cl)
   candidates.add((z,a,b))
 gates={}
 for z,a,b in candidates:
  for op in ("X","A","O"):
   terms=gcl(op,a,b,z)
   if terms<=original:
    assert z not in gates,("AMBIGUOUS_GATE",z)
    gates[z]=(op,a,b)
 covered=set()
 for z,(op,a,b) in gates.items():
  assert z>max(a,b)
  parts=gcl(op,a,b,z)
  assert not parts&covered
  covered|=parts
 miters=[]
 for cl in clauses:
  if len(cl)==2 and min(cl)>0 and all(x in gates for x in cl):
   a,b=cl
   if tuple(sorted((-a,-b))) in original:miters.append((a,b))
 assert len(miters)==1,("MISSING_MITER",len(miters))
 a,b=miters[0]
 covered|={tuple(sorted((a,b))),tuple(sorted((-a,-b)))}
 assert covered==original,("UNRECOGNIZED_CLAUSES",len(covered),len(original))
 inputs=[i for i in range(1,n+1) if i not in gates]
 assert len(inputs)<=12
 for bits in range(1<<len(inputs)):
  v={i:bool(bits & (1<<k)) for k,i in enumerate(inputs)}
  for z in sorted(gates):
   op,x,y=gates[z]
   v[z]=(v[x]!=v[y] if op=="X" else v[x] and v[y] if op=="A" else v[x] or v[y])
  if v[a]!=v[b]:
   assert expected=="SAT",("WRONG_FROZEN_UNSAT_EXPECTATION",a,b)
   return {"inputs":len(inputs),"gates":len(gates),"equivalent":False}
 assert expected=="UNSAT",("WRONG_FROZEN_SAT_EXPECTATION",a,b)
 return {"inputs":len(inputs),"gates":len(gates),"equivalent":True}

def freeze(root):
 root.mkdir(parents=True,exist_ok=True);(root/"cnf").mkdir(exist_ok=True)
 original=old.SEED
 manifest_previous=root.parent/"r119-original"/"manifest.json"
 assert manifest_previous.exists(),"R119 original frozen source manifest missing"
 previous=json.loads(manifest_previous.read_text())
 by_old={c["id"]:c for c in previous["cases"]}
 cases=[]
 try:
  for exposure in ("seen","new"):
   old.SEED=original if exposure=="seen" else NEW_SEED
   for family in FAMILIES:
    for i in range(48):
     raw,item=old.make(i,family)
     digest=hashlib.sha256(raw).hexdigest()
     if exposure=="seen":
      assert by_old[item["id"]]["sha256"]==digest,("HISTORICAL_SHA_MISMATCH",item["id"])
     item=dict(item,exposure=exposure,id=f"{exposure}-{item['id']}",
               sha256=digest,bytes=len(raw),source="generated R119 family; NOT industrial hardware")
     # New holdout frozen before any solver execution. Old source independently SHA-matches R119.
     assert full_gate_proof(raw,item["expected"])["equivalent"]==(item["expected"]=="UNSAT")
     (root/"cnf"/(item["id"]+".cnf")).write_bytes(raw)
     cases.append(item)
 finally:old.SEED=original
 assert len(cases)==192 and len({c["sha256"] for c in cases})==192
 manifest=dict(protocol=PROTO,cases=cases,shards=SHARDS,repetitions=REPS,
  cap_seconds=CAP,selection="new mixed circuits use fixed precommitted seed, never selected by solver runtime",
  exclusion="96 seen R119 circuits explicitly tagged; 96 new circuits generated with disjoint fixed seed",
  source_type="reproducible engineering-like synthetic netlists, NOT independent industrial circuit inputs")
 (root/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
 (root/"source.sha256").write_text("".join(f'{c["sha256"]}  cnf/{c["id"]}.cnf\n' for c in cases))
 print("R122_FREEZE",json.dumps(dict(formulas=192,previous_seen=96,new_generated=96,sha_unique=192)),flush=True)

def run_mode(mode,source,binaries):
 cmd=([str(binaries[mode]),str(source),str(binaries["kissat"])] if mode in ("r118","r122")
      else [str(binaries[mode]),str(source)])
 t=time.perf_counter()
 try:
  p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  sec=time.perf_counter()-t
  if p.returncode==10:status="SAT"
  elif p.returncode==20:status="UNSAT"
  elif p.returncode==0 and b"s UNSATISFIABLE" in p.stdout:status="UNSAT"
  elif p.returncode==0 and b"s SATISFIABLE" in p.stdout:status="SAT"
  else:raise RuntimeError("solver error "+mode+":"+str(p.returncode)+" stderr:"+p.stderr[-350:].decode(errors="replace"))
  route=next((m for m in ("certified_gate_anf_equivalent","certified_gate_anf_counterexample",
     "certified_pure_xor_sat","certified_xor_contradiction","fallback") if m.encode() in p.stdout),"baseline")
  return status,sec,route,p.stdout
 except subprocess.TimeoutExpired:return "TIMEOUT",CAP,"timeout",b""

def run_shard(root,index):
 m=json.loads((root/"manifest.json").read_text())
 assert m["protocol"]==PROTO and len(m["cases"])==192
 cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==index]
 assert len(cs)==24
 bins={k:Path(v).resolve() for k,v in (
   ("r118","r122/r118"),("r122","r122/r122_solver"),("kissat","built/bin/kissat_4_0_4"),
   ("cryptominisat",os.environ.get("CRYPTOMINISAT_BIN","/usr/bin/cryptominisat5")))}
 assert all(path.exists() for path in bins.values())
 cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpus[0]})
 out=root/f"shard-{index:02d}";out.mkdir(exist_ok=True)
 rows=[]
 for c in cs:
  src=root/"cnf"/(c["id"]+".cnf")
  data=src.read_bytes()
  assert hashlib.sha256(data).hexdigest()==c["sha256"]
  n,clauses=parse_cnf(data)
  verify=full_gate_proof(data,c["expected"])
  assert verify["inputs"]==10
  for rep in range(REPS):
   order=list(SOLVERS)
   random.Random(PROTO+"/"+c["id"]+"/"+str(rep)).shuffle(order)
   for mode in order:
    status,sec,route,stdout=run_mode(mode,src,bins)
    if status in ("SAT","UNSAT"):assert status==c["expected"],("WRONG_ANSWER",c["id"],mode,status)
    if mode=="r122":
     assert route in ("certified_gate_anf_equivalent","certified_gate_anf_counterexample"),("NO_GATE_DECISION",c["id"],route)
     if route=="certified_gate_anf_equivalent":assert status=="UNSAT" and verify["equivalent"]
     else:assert status=="SAT" and not verify["equivalent"]
    if mode=="r118" and route=="certified_xor_contradiction":
     check_unsat_cert(stdout,clauses,"R118")
    if status=="SAT" and any(s.startswith(b"v ") for s in stdout.splitlines()):
     check_sat_model(stdout,n,clauses)
    if mode=="r122" and status=="SAT":
     assert any(s.startswith(b"v ") for s in stdout.splitlines())
    row=dict(id=c["id"],family=c["family"],exposure=c["exposure"],
      sha256=c["sha256"],seed=c["seed"],rep=rep,mode=mode,status=status,
      route=route,seconds=round(sec,6),par2=round(sec if status in ("SAT","UNSAT") else 2*CAP,6))
    rows.append(row)
    print("R122_MEASURE",json.dumps(row,sort_keys=True),flush=True)
 with (out/"paired.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 (out/"summary.json").write_text(json.dumps(dict(shard=index,cases=len(cs),attempts=len(rows),
   routes=dict(Counter(r["route"] for r in rows))),indent=2))
 print("R122_SHARD_PASS",json.dumps(dict(shard=index,cases=len(cs),attempts=len(rows))),flush=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument("action",choices=("freeze","run"))
 ap.add_argument("--shard",type=int,default=0)
 ap.add_argument("--root",default="r122")
 a=ap.parse_args()
 if a.action=="freeze":freeze(Path(a.root))
 else:run_shard(Path(a.root),a.shard)
if __name__=="__main__":main()
