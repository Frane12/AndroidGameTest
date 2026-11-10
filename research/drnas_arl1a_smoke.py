#!/usr/bin/env python3
"""ARL1A positive activation smoke; synthetic construction, not a speed claim."""
import json,pathlib,subprocess
out=pathlib.Path("mre_arl1a")
p=out/"synthetic_trigger.cnf"
# Two exact ternary parents imply (-9 OR 46); 50 variable DIMACS.
p.write_text("p cnf 50 2\n-9 18 46 0\n-9 -18 46 0\n")
bin=(out/"bin"/"drnas").resolve()
rows=[]
for mode in ("A","ARL1A"):
 r=subprocess.run([str(bin),str(p.resolve()),"--mode",mode,"--time","10"],
                  capture_output=True,text=True)
 assert r.returncode==10,(mode,r.returncode,r.stderr)
 result=next(x for x in r.stdout.splitlines() if x.startswith("ARL1A_TRIAL "))
 stats=dict(x.split("=",1) for x in result.split()[1:] if "=" in x)
 model={}
 for line in r.stdout.splitlines():
  if line.startswith("v "):
   for tok in line.split()[1:]:
    n=int(tok)
    if n:model[abs(n)]=n>0
 assert len(model)==50
 assert ((not model[9]) or model[18] or model[46])
 assert ((not model[9]) or (not model[18]) or model[46])
 assert stats["SAT_original_verified"]=="1"
 rows.append(stats)
assert rows[0]["decision"]=="baseline"
assert rows[1]["decision"]=="commit" and int(rows[1]["accepted"])>=1,rows[1]
assert int(rows[1]["final_clauses"])==3
(out/"synthetic_smoke.json").write_text(json.dumps(rows,indent=2,sort_keys=True))
print("ARL1A_POSITIVE_SMOKE "+json.dumps(dict(
  baseline_decisions=rows[0]["decisions"],active_decisions=rows[1]["decisions"],
  accepted=rows[1]["accepted"],decision=rows[1]["decision"],status="PASS",
  case="synthetic_50var_two_exact_ternary_parents_not_benchmark"),sort_keys=True))
