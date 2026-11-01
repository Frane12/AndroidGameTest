#!/usr/bin/env python3
"""V16.5 independent exhaustively verified binary relations.
Each original formula includes two distinct full XOR3 blocks with a hidden
XOR2 consequence. Random permutation and distracting satisfiable clauses.
Never infer SAT/UNSAT from merely detecting a relation: verify original CNF.
"""
import collections,itertools,json,random,subprocess,statistics,hashlib
from pathlib import Path
from v153_proof_checker import verify_certificate
ROOT=Path("v165-binary-relation-property");ROOT.mkdir(exist_ok=True)
S=Path("bin/v165_binary_bridge").resolve()
K=Path("bin/kissat_solver").resolve()
C=Path("bin/kissat_api_control").resolve()
B=Path("bin/v159_relational_dispatch").resolve()
def blocks(triple,rhs):
 return [[-v if mask>>i&1 else v for i,v in enumerate(triple)]
         for mask in range(8) if (mask.bit_count()&1)!=rhs]
def formula(i):
 rng=random.Random(16420261101+i*7919)
 n=8;truth={v:rng.randrange(2) for v in range(1,n+1)}
 cls=blocks([1,2,3],truth[1]^truth[2]^truth[3])
 cls+=blocks([2,3,4],truth[2]^truth[3]^truth[4])
 # Every distracting clause has a known satisfying planted assignment.
 for j in range(4+i%5):
  ids=rng.sample(range(1,9),3)
  clause=[v if rng.getrandbits(1) else -v for v in ids]
  if not any(truth[abs(v)]==(v>0) for v in clause):
   clause[0]=abs(clause[0]) if truth[abs(clause[0])] else -abs(clause[0])
  cls.append(clause)
 # 25% UNSAT by a direct contradiction of the derived 2-variable equality.
 # The other 75% SAT have no units and require a genuine new binary clause.
 unsat=i%4==0
 if unsat:
  cls.append([1 if truth[1] else -1])
  cls.append([4 if not truth[4] else -4])
 perm=list(range(1,n+1));rng.shuffle(perm)
 cls=[[perm[abs(lit)-1]*(1 if lit>0 else -1) for lit in cl] for cl in cls]
 for row in cls:rng.shuffle(row)
 rng.shuffle(cls)
 return n,cls,"UNSAT" if unsat else "SAT",(perm[0],perm[3])
def cfile(n,clauses,path):
 path.write_text("p cnf "+str(n)+" "+str(len(clauses))+"\n"+
    "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
def allmodels(n,clauses):
 return [bits for bits in itertools.product((False,True),repeat=n)
         if all(any(bits[abs(lit)-1]==(lit>0) for lit in cl) for cl in clauses)]
def answer_and_check(text,expect,n,clauses):
 tagged=[z.split("\t",1)[1] for z in text.splitlines()
         if z.startswith("DRNAS_HYBRID_RESULT\t")]
 if tagged:
  payload=json.loads(tagged[-1])
  if payload.get("status")!=expect:return False
  if expect=="SAT":
   vals={abs(l):l>0 for l in payload.get("model",[])}
   return bool(vals) and all(any(vals.get(abs(l))==(l>0) for l in cl) for cl in clauses)
  return bool(verify_certificate(payload,clauses))
 expected=("s SATISFIABLE" if expect=="SAT" else "s UNSATISFIABLE")
 return expected in text and (expect!="SAT" or witness(text,n,clauses))
def checkrun(bin_,p,extra=()):
 cmd=[str(bin_),str(p.resolve())] if bin_==C else [str(bin_),str(p.resolve()),str(K),"1",*extra]
 return subprocess.run(cmd,capture_output=True,text=True,timeout=6)
def witness(text,n,clauses):
 model=[int(t) for line in text.splitlines() if line.startswith("v ")
        for t in line.split()[1:] if t!="0"]
 vals={abs(l):l>0 for l in model}
 return bool(vals) and all(any(vals.get(abs(l))==(l>0) for l in cl) for cl in clauses)
records=[];valid=0;binary_cases=0;forced_cases=0
for i in range(144):
 n,clauses,status,pair=formula(i)
 path=ROOT/f"new-{i:03}.cnf";cfile(n,clauses,path)
 models=allmodels(n,clauses)
 assert bool(models)==(status=="SAT"),(i,status)
 diagnostic=checkrun(S,path,["--derive-only"])
 assert diagnostic.returncode==0,(i,diagnostic.stderr)
 outputs=[z for z in diagnostic.stdout.splitlines() if z.startswith("DRNAS_V162_DERIVE\t")]
 assert len(outputs)==1,(i,diagnostic.stdout)
 d=json.loads(outputs[0].split("\t",1)[1])
 for lit in d["units"]:
  assert all(m[abs(lit)-1]==(lit>0) for m in models),(i,"invalid unit",lit)
 for clause in d["binary"]:
  assert len(clause)==2
  assert all(any(m[abs(l)-1]==(l>0) for l in clause) for m in models),(i,"invalid binary",clause)
 if d["contradiction"]:assert not models,(i,"false conflict")
 # Both new binary clauses should be derived when there are no units.
 if status=="SAT":
  assert any(set(map(abs,c))==set(pair) for c in d["binary"]),(i,"missing pair",d)
  binary_cases+=1
 result=checkrun(S,path,["--bridge-first"])
 expected=("s SATISFIABLE" if status=="SAT" else "s UNSATISFIABLE")
 assert result.returncode==0 and answer_and_check(result.stdout,status,n,clauses),(i,status,result.stdout[-200:],result.stderr[-200:])
 if status=="SAT":
  assert "v165_selective_scc_xor_binary_api" in result.stdout,(i,"no binary bridge API",result.stdout)
  assert witness(result.stdout,n,clauses),(i,"wrong SAT witness")
  forced_cases+=1
 for method in (C,B,S):
  rr=checkrun(method,path)
  assert rr.returncode==0 and answer_and_check(rr.stdout,status,n,clauses),(i,method,status,rr.stdout[-200:])
  valid+=1
 records.append({"id":i,"status":status,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                 "derived_units":len(d["units"]),"derived_binary":len(d["binary"]),
                 "bridge_route":("v165_selective_scc_xor_binary_api" in result.stdout)})
# Guard against useless GF2 work on formulas without full XOR supports.
# The selector must keep safe Kissat fallback on unrelated normal 3SAT.
for i in range(24):
 rng=random.Random(1651234+i)
 cl=[]
 for j in range(40):
  v=rng.sample(range(1,17),3)
  lit=[x if rng.getrandbits(1) else -x for x in v]
  cl.append(lit)
 path=ROOT/f"negative-{i:03}.cnf";cfile(16,cl,path)
 rr=checkrun(S,path,["--bridge-first"])
 assert rr.returncode==0,(i,rr.stderr[-300:])
 assert "v165_kissat_fast_skip" in rr.stdout,(i,rr.stdout[-300:])
print("V165_FAST_SKIP_PASS",24,"unrelated 3SAT controls",flush=True)
print("V165_EXHAUSTIVE_PASS",len(records),"cases",valid,"default solver checks",flush=True)
print("V165_BRIDGE_PASS",forced_cases,"SAT cases reached embedded Kissat with sound new binaries",flush=True)
print("V165_BINARY_RELATIONS",binary_cases,"SAT cases with verified hidden pair implication",flush=True)
(ROOT/"report.json").write_text(json.dumps(records,indent=2))
