#!/usr/bin/env python3
"""ATLAS3 strict/normal opportunity gate positive, negative and tradeoff cases."""
import pathlib,subprocess,json
root=pathlib.Path("mre_atlas3");root.mkdir(exist_ok=True)
exe=(root/"bin/drnas_atlas3").resolve()
cases={
 "high_repeated_support":(
   [clause for i in range(14)
    for clause in ([3*i+1,3*i+2],[3*i+1,-(3*i+2)])],
   {"ATLAS2":"commit","ATLAS3":"commit","ATLAS3_STRICT":"commit"}),
 "low_single_opportunity":(
   [[1,2],[1,-2],[3,4,5],[6,7,8]],
   {"ATLAS2":"commit","ATLAS3":"sleep","ATLAS3_STRICT":"sleep"}),
 "no_overlap":(
   [[3*i+1,3*i+2,3*i+3] for i in range(35)],
   {"ATLAS2":"sleep","ATLAS3":"sleep","ATLAS3_STRICT":"sleep"})
}
for name,(clauses,expected) in cases.items():
 n=160
 f=root/(name+".cnf")
 f.write_text(f"p cnf {n} {len(clauses)}\n"+"".join(" ".join(map(str,c))+" 0\n" for c in clauses))
 for mode in ("A","ATLAS2","ATLAS3","ATLAS3_STRICT"):
  p=subprocess.run([str(exe),str(f.resolve()),"--mode",mode,"--time","10"],capture_output=True,text=True)
  assert p.returncode==10,(name,mode,p.returncode,p.stderr,p.stdout)
  line=next(x for x in p.stdout.splitlines() if x.startswith("ATLAS3_TRIAL "))
  tel=dict(x.split("=",1) for x in line.split()[1:] if "=" in x)
  assert tel["SAT_original_verified"]=="1"
  if mode in expected:assert tel["decision"]==expected[mode],(name,mode,tel)
  if mode in ("ATLAS3","ATLAS3_STRICT"):
   assert float(tel["gate_s"])>=0
   if tel["decision"]=="commit":
    assert int(tel["saved_literals"])>0 and int(tel["modules"])>0
  print("ATLAS3_CONTROL "+json.dumps(dict(case=name,mode=mode,decision=tel["decision"],gate_score=int(tel["gate_score"]),modules=int(tel["modules"])),sort_keys=True),flush=True)
print("ATLAS3_CONTROLS_PASS")
