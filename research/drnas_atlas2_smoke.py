#!/usr/bin/env python3
"""ATLAS2 proof-equivalence smoke and multi-block control."""
import json,pathlib,subprocess
root=pathlib.Path("mre_atlas2");root.mkdir(exist_ok=True)
exe=(root/"bin/drnas_atlas2").resolve()
cases={
 "two_disjoint_binary_resolvents":(40,[
  [1,2],[1,-2],[5,6],[5,-6],[7,8,9],
 ],2),
 "gate_circuit_redundancy":(40,[
  [-1,-2,3],[1,-3],[2,-3],[-3,1,2],
  [-4,-5,6],[4,-6],[5,-6],[-6,4,5],
  [7,8,9],
 ],2),
 "unrelated_clauses":(40,[
  [1,2,3],[4,5,6],[7,8,9]
 ],0),
}
for name,(n,clauses,minimum_modules) in cases.items():
    path=root/(name+".cnf")
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    telemetry={}
    for mode in ("A","ATLAS2"):
        p=subprocess.run([str(exe),str(path.resolve()),"--mode",mode,"--time","10"],
            text=True,capture_output=True)
        assert p.returncode==10,(name,mode,p.returncode,p.stdout,p.stderr)
        assignment={}
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                for x in map(int,line.split()[1:]):
                    if x:assignment[abs(x)]=(x>0)
        assert len(assignment)==n
        assert all(any(assignment[abs(l)]==(l>0) for l in c) for c in clauses)
        t=next(x for x in p.stdout.splitlines() if x.startswith("ATLAS2_TRIAL "))
        telemetry[mode]=dict(part.split("=",1) for part in t.split()[1:] if "=" in part)
    d=telemetry["ATLAS2"]
    assert int(d["modules"])>=minimum_modules,(name,d)
    if minimum_modules:
        assert d["decision"]=="commit" and int(d["saved_literals"])>0,(name,d)
    else:
        assert d["decision"]=="sleep",(name,d)
    assert int(d["final_clauses"])==len(clauses)-int(d["removed"])+int(d["added"])
    print("ATLAS2_CONTROL "+json.dumps(dict(case=name,telemetry=d),sort_keys=True),flush=True)
print("ATLAS2_CONTROLS_PASS")
