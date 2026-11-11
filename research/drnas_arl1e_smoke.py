#!/usr/bin/env python3
"""Positive exact-gate smoke, synthetic only, not performance evidence."""
import pathlib,subprocess,json
root=pathlib.Path("mre_arl1e")
f=root/"positive.cnf"
f.write_text("p cnf 50 2\n-9 18 46 0\n-9 -18 46 0\n")
results={}
for arm in ("A","ARL1E"):
 p=subprocess.run([str((root/"bin/drnas_e").resolve()),str(f.resolve()),"--mode",arm,"--time","10"],capture_output=True,text=True)
 assert p.returncode==10,(arm,p.returncode,p.stderr)
 line=next(x for x in p.stdout.splitlines() if x.startswith("ARL1E_TRIAL "))
 results[arm]=dict(x.split("=",1) for x in line.split()[1:] if "=" in x)
 assert results[arm]["SAT_original_verified"]=="1"
assert results["ARL1E"]["decision"]=="commit"
assert results["ARL1E"]["accepted"]=="1"
assert results["ARL1E"]["final_clauses"]=="3"
print("ARL1E_POSITIVE_SMOKE "+json.dumps(results,sort_keys=True))
(root/"positive_smoke.json").write_text(json.dumps(results,indent=2))
