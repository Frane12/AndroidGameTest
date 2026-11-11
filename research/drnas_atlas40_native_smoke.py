#!/usr/bin/env python3
"""ATLAS40 native-only smoke. No apt, pip, Kissat, CMS or external inputs.
Checks native modes, valid original-CNF SAT witnesses, and mode telemetry.
UNSAT result is NOT independently certified.
"""
import pathlib,subprocess,tempfile
BIN="mre_atlas23/bin/drnas_atlas40"
ARMS=("A36_75","A39_PROTECT","A40_YOUNG","A40_MATURE")
def verify(clauses,stdout,n):
 values={}
 for line in stdout.splitlines():
  if line.startswith("v "):
   for token in line.split()[1:]:
    lit=int(token)
    if lit:
     if abs(lit) in values and values[abs(lit)]!=(lit>0):return False
     values[abs(lit)]=lit>0
 return bool(values) and all(any(values.get(abs(l))==(l>0) for l in c) for c in clauses)
with tempfile.TemporaryDirectory() as d:
 path=pathlib.Path(d)/"smoke.cnf"
 # A small SAT source, every result must be a valid original witness.
 n=4
 clauses=[[1,2],[-1,3],[-3,4],[-4,2]]
 path.write_text(f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses))
 for arm in ARMS:
  cmd=[BIN,str(path),"--mode",arm,"--time","3","--seed","1","--policy","1.0,0.85"]
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=8)
  assert p.returncode==10,(arm,p.returncode,p.stdout[-900:],p.stderr[-900:])
  assert verify(clauses,p.stdout,n),("invalid SAT model",arm,p.stdout[-1000:])
  rows=[line for line in p.stdout.splitlines() if line.startswith("ATLAS13_TRIAL ")]
  assert rows,("missing native diagnostics",arm)
  info=dict(t.split("=",1) for t in rows[-1].split()[1:] if "=" in t)
  assert info.get("atlas39_mode")==str({"A36_75":0,"A39_PROTECT":2,"A40_YOUNG":3,"A40_MATURE":4}[arm]),(arm,info)
  assert info.get("atlas36_quota_pct")=="75",(arm,info.get("atlas36_quota_pct"))
  print("ATLAS40_NATIVE_SMOKE_TRIAL",arm,"SAT_VERIFIED",flush=True)
 print("ATLAS40_NATIVE_SMOKE_PASS modes=4 original_SAT_verified=true UNSAT_certified=false external_deps=false",flush=True)
