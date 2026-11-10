#!/usr/bin/env python3
"""Synthetic positive commit control, NOT a performance benchmark."""
import json,pathlib,subprocess
out=pathlib.Path("mre_arl1b")
p=out/"synthetic_trigger.cnf"
# Deliberately place matching clauses beyond first 128 ternaries:
# indexed selector searches all 1024, first-prefix ARL1A cannot see both.
clauses=[]
for i in range(150):
 a=1+i%7;b=12+i%8;c=27+i%11
 clauses.append(f"{a} {b} {c} 0")
clauses+=["-9 18 46 0","-9 -18 46 0"]
p.write_text("p cnf 50 "+str(len(clauses))+"\n"+"\n".join(clauses)+"\n")
rows={}
for mode,binary in (("A","drnas_b"),("ARL1A","drnas_a"),("ARL1B","drnas_b")):
 r=subprocess.run([str((out/"bin"/binary).resolve()),str(p.resolve()),"--mode",mode,"--time","10"],capture_output=True,text=True)
 assert r.returncode==10,(mode,r.returncode,r.stderr)
 x=next(x for x in r.stdout.splitlines() if x.startswith(("ARL1A_TRIAL ","ARL1B_TRIAL ")))
 d=dict(v.split("=",1) for v in x.split()[1:] if "=" in v)
 model={}
 for line in r.stdout.splitlines():
  if line.startswith("v "):
   for tok in line.split()[1:]:
    lit=int(tok)
    if lit:model[abs(lit)]=lit>0
 assert len(model)==50
 for clause in clauses:
  lits=[int(lit) for lit in clause.split() if lit!="0"]
  assert any(model[abs(lit)]==(lit>0) for lit in lits)
 rows[mode]=d
assert rows["ARL1B"]["decision"]=="commit" and int(rows["ARL1B"]["accepted"])>=1,rows
assert int(rows["ARL1B"]["final_clauses"])==len(clauses)+int(rows["ARL1B"]["accepted"])
(out/"synthetic_smoke.json").write_text(json.dumps(rows,indent=2,sort_keys=True))
print("ARL1B_POSITIVE_SMOKE "+json.dumps({k:{t:v for t,v in d.items() if t in ("decision","accepted","conflicts","decisions","probe_s","pairs")} for k,d in rows.items()},sort_keys=True))
