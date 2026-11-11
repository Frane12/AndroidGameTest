#!/usr/bin/env python3
"""ATLAS-X deterministic SAT controls; each SAT model checked on ORIGINAL CNF."""
import json
import pathlib
import subprocess

out=pathlib.Path("mre_atlasx")
out.mkdir(exist_ok=True)
exe=(out/"bin/drnas_atlasx").resolve()
cases={
  "extended_redundancy": (
    ["1 2 3 0","1 2 -3 0","1 2 4 5 0","1 2 -4 5 0","6 7 0"],
    "L2_MASK_SUBSUMPTION"),
  "extended_expansion": (
    ["1 2 3 0","1 2 -3 0","-1 -2 4 5 0","-1 -2 -4 5 0","6 7 0"],
    "L2_LAZY_EXPAND"),
  "unrelated": (
    ["1 2 3 0","4 5 6 0","7 8 9 0"],
    None),
}
for name,(lines,expected) in cases.items():
    cnf=out/(name+".cnf")
    cnf.write_text("p cnf 16 "+str(len(lines))+"\n"+"\n".join(lines)+"\n")
    clauses=[[int(x) for x in line.split()[:-1]] for line in lines]
    for mode in ("A","ATLAS1","ATLASX"):
        p=subprocess.run([str(exe),str(cnf.resolve()),"--mode",mode,"--time","10"],
                         text=True,capture_output=True)
        assert p.returncode==10,(name,mode,p.returncode,p.stderr,p.stdout)
        d=dict(kv.split("=",1) for kv in
           next(x for x in p.stdout.splitlines() if x.startswith("ATLASX_TRIAL ")).split()[1:]
           if "=" in kv)
        assignment={}
        for ln in p.stdout.splitlines():
            if ln.startswith("v "):
                for l in map(int,ln.split()[1:]):
                    if l:assignment[abs(l)]=l>0
        assert len(assignment)==16,(name,mode,assignment)
        assert all(any(assignment[abs(l)]==(l>0) for l in clause) for clause in clauses)
        assert d["SAT_original_verified"]=="1"
        assert int(d["final_clauses"])==len(lines)-int(d["removed"])+int(d["added"])
        if mode=="ATLASX":
            if expected:
                assert d["decision"]=="commit" and d["kind"]==expected,(name,d)
                assert int(d["saved_literals"])>0,d
            else:
                assert d["decision"]=="sleep",(name,d)
            print("ATLASX_CONTROL "+json.dumps({"case":name,"route":d},sort_keys=True),flush=True)
print("ATLASX_CONTROLS_PASS",flush=True)
