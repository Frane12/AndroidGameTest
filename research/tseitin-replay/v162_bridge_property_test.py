#!/usr/bin/env python3
"""V16.2 mathematical soundness test: executable-derived units must be
entailed by ORIGINAL CNF, checked by exhaustive enumeration (<=10 variables).
Also compare final SAT/UNSAT with pinned Kissat; UNSAT path never self-certified
by bridge, all SAT witnesses checked on original clauses.
"""
import collections,itertools,json,random,subprocess,statistics,time
from pathlib import Path
ROOT=Path("v162-property-audit");ROOT.mkdir(exist_ok=True)
SOLVER=Path("bin/v162_bridge_solver").resolve()
KISSAT=Path("bin/kissat_solver").resolve()
V159=Path("bin/v159_relational_dispatch").resolve()
def xorclauses(vars_,rhs):
 n=len(vars_)
 return [[-v if (mask>>i)&1 else v for i,v in enumerate(vars_)]
         for mask in range(1<<n) if (mask.bit_count()%2)!=rhs]
def formula(i):
 rng=random.Random(0x16262026+i)
 n=8;cls=[]
 invert=rng.randrange(2);answer=rng.randrange(2)
 # b = a XOR invert. Exactly two CNF binary clauses imply SCC literal eq.
 if not invert:cls.extend([[-1,2],[1,-2]])
 else:cls.extend([[1,2],[-1,-2]])
 # a XOR b XOR c = invert XOR answer => c=answer.
 cls+=xorclauses([1,2,3],invert^answer)
 expected=[False]*9
 expected[1]=bool(rng.randrange(2))
 expected[2]=bool(expected[1]^bool(invert))
 expected[3]=bool(answer)
 for j in range(4,9):expected[j]=bool(rng.randrange(2))
 # Optional other XOR4 with its own true planted assignment, not a label.
 if i%3==0:
  rhs=int(expected[4])^int(expected[5])^int(expected[6])^int(expected[7])
  cls+=xorclauses([4,5,6,7],rhs)
 # Random ordinary clauses always satisfied by planted assignment;
 # they may introduce no UNSAT or change their own solution set.
 for j in range(6+i%5):
  vars_=rng.sample(range(1,9),3)
  c=[v*rng.choice((-1,1)) for v in vars_]
  if not any(expected[abs(l)]==(l>0) for l in c):
   c[0]=abs(c[0]) if expected[abs(c[0])] else -abs(c[0])
  cls.append(c)
 # Other SCC-equivalence via implication chain.
 if i%4==1:
  # 5 and 8 have the same planted bit if we add equality.
  if expected[5]==expected[8]:cls.extend([[-5,8],[5,-8]])
  else:cls.extend([[5,8],[-5,-8]])
 if i%6==2:
  # Make UNSAT with a direct negation of a mathematically implied unit.
  cls.append([-3 if answer else 3])
  expect="UNSAT"
 else:expect="SAT"
 for c in cls:rng.shuffle(c)
 rng.shuffle(cls)
 # Fixed random renaming avoids learning variable IDs.
 perm=list(range(1,9));rng.shuffle(perm)
 cls=[[ (1 if lit>0 else -1)*perm[abs(lit)-1] for lit in c] for c in cls]
 expected_lit=(perm[2] if answer else -perm[2])
 return n,cls,expect,expected_lit
def write(path,n,cls):
 path.write_text("p cnf "+str(n)+" "+str(len(cls))+"\n"+
  "".join(" ".join(map(str,c))+" 0\n" for c in cls))
def exhaustive_models(n,cls):
 for bits in itertools.product((False,True),repeat=n):
  if all(any(bits[abs(lit)-1]==(lit>0) for lit in c) for c in cls):
   yield bits
def run(program,path,extra=()):
 cmd=[str(program),str(path.resolve()),str(KISSAT),"1"]+list(extra)
 return subprocess.run(cmd,text=True,capture_output=True,timeout=4)
rows=[]
for i in range(120):
 n,cls,expect,target=formula(i)
 path=ROOT/f"rel-{i:03}.cnf";write(path,n,cls)
 models=list(exhaustive_models(n,cls))
 assert (bool(models)==(expect=="SAT")),(i,expect,len(models))
 res=run(SOLVER,path,["--derive-only"])
 assert res.returncode==0,(i,res.stderr,res.stdout)
 found=[l for l in res.stdout.splitlines() if l.startswith("DRNAS_V162_DERIVE\t")]
 assert len(found)==1,(i,res.stdout)
 data=json.loads(found[0].split("\t",1)[1])
 # With source XOR+binary SCC, the root variable c is always implied.
 if models:
  assert target in data["units"],(i,target,data)
 else:
  assert data["contradiction"] or (target in data["units"]),(i,target,data)
 for lit in data["units"]:
  assert all(bits[abs(lit)-1]==(lit>0) for bits in models),(i,lit,data)
 if data["contradiction"]:
  assert not models,(i,"UNSOUND_CONTRADICTION")
 for name,solver in [("v159",V159),("v162",SOLVER)]:
  p=run(solver,path)
  expected_tag=('"status":"'+expect+'"')
  status=(expect=="SAT" and ('s SATISFIABLE' in p.stdout or expected_tag in p.stdout)) or (expect=="UNSAT" and ('s UNSATISFIABLE' in p.stdout or expected_tag in p.stdout))
  assert status,(i,name,expect,p.returncode,p.stdout[-400:],p.stderr[-400:])
  # Dedicated output SAT witness replay on original CNF is also run by bench.
 # Exercise the FULL native route: original CNF -> implied unit additions ->
 # embedded Kissat. Merely finding units in --derive-only is insufficient.
 forced=run(SOLVER,path,["--bridge-first"])
 assert forced.returncode==0,(i,forced.stderr[-300:],forced.stdout[-300:])
 got=('"status":"'+expect+'") in forced.stdout or (
     ('s SATISFIABLE' if expect=="SAT" else 's UNSATISFIABLE') in forced.stdout)
 assert got,(i,expect,forced.stdout[-300:])
 if models:
  assert "v162_scc_xor_unit_api" in forced.stdout,(i,forced.stdout[-300:])
  model=[int(w) for line in forced.stdout.splitlines() if line.startswith("v ")
         for w in line.split()[1:] if w!="0"]
  assert model,(i,"no native Kissat SAT witness")
  assignment={abs(lit):lit>0 for lit in model}
  assert all(any(assignment.get(abs(lit))==(lit>0) for lit in c) for c in cls),(i,"invalid witness")
 rows.append({"case":i,"sat":expect=="SAT","xor_equations":data["xor"],
              "aliases":data["scc_aliases"],
              "units":len(data["units"]),"contradiction":data["contradiction"]})
print("V162_PROPERTY_PASS",len(rows),"exhaustive original-CNF implication and native Kissat augmentation tests",flush=True)
print("V162_PROPERTY_STATS",json.dumps({"cases":len(rows),
  "derived_unit_cases":sum(bool(x["units"]) for x in rows),
  "unsat_cases":sum(not x["sat"] for x in rows),
  "scc_alias_cases":sum(x["aliases"]>0 for x in rows)}),flush=True)
(ROOT/"audit.json").write_text(json.dumps(rows,indent=2))
