#!/usr/bin/env python3
"""ATLAS1 source-equivalence positive and abstention controls."""
import json,pathlib,subprocess
root=pathlib.Path("mre_atlas1")
exe=(root/"bin/drnas_atlas").resolve()
cases={
 "binary_unit":(30,["1 2 0","1 -2 0","7 8 9 0"],True),
 "four_literal_resolution":(30,["1 2 3 4 0","1 2 3 -4 0","7 8 9 0"],True),
 "absorption":(30,["1 0","1 2 0","7 8 9 0"],True),
 "nonoverlapping":(30,["1 2 3 0","4 5 6 0","7 8 9 0"],False),
}
for name,(n,clauses,expect_commit) in cases.items():
 cnf=root/(name+".cnf")
 cnf.write_text("p cnf "+str(n)+" "+str(len(clauses))+"\n"+"\n".join(clauses)+"\n")
 all_c=[[int(y) for y in x.split()[:-1]] for x in clauses]
 def check_model(stdout):
  assignment={}
  for line in stdout.splitlines():
   if line.startswith("v "):
    for lit in map(int,line.split()[1:]):
     if lit:assignment[abs(lit)]=lit>0
  assert len(assignment)==n
  assert all(any(assignment[abs(l)]==(l>0) for l in clause) for clause in all_c)
 for mode in ("A","ATLAS1"):
  p=subprocess.run([str(exe),str(cnf.resolve()),"--mode",mode,"--time","10"],capture_output=True,text=True)
  assert p.returncode==10,(name,mode,p.returncode,p.stderr,p.stdout)
  check_model(p.stdout)
  line=next(x for x in p.stdout.splitlines() if x.startswith("ATLAS1_TRIAL "))
  telemetry=dict(part.split("=",1) for part in line.split()[1:] if "=" in part)
  assert telemetry["SAT_original_verified"]=="1"
  if mode=="ATLAS1":
   assert (telemetry["decision"]=="commit")==expect_commit,(name,telemetry)
   if expect_commit:
    assert int(telemetry["saved_literals"])>0
    assert int(telemetry["final_clauses"])==len(clauses)-int(telemetry["removed"])+int(telemetry["added"])
   print("ATLAS1_CONTROL "+json.dumps(dict(case=name,telemetry=telemetry),sort_keys=True),flush=True)
print("ATLAS1_CONTROLS_PASS")
