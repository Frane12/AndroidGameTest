#!/usr/bin/env python3
"""ATLAS-MAP1 independent original-CNF SAT and learned-gate controls."""
import json
import pathlib
import subprocess

ROOT=pathlib.Path("mre_atlasmap1")
ROOT.mkdir(exist_ok=True)
EXE=(ROOT/"bin/drnas_atlasmap1").resolve()

def trial(name,clauses,arm,memory=None):
    path=ROOT/(name+".cnf")
    n=16
    path.write_text(f"p cnf {n} {len(clauses)}\n" +
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    command=[str(EXE),str(path.resolve()),"--mode",arm,"--time","10"]
    if memory is not None:command.extend(["--memory",str(memory)])
    p=subprocess.run(command,text=True,capture_output=True)
    assert p.returncode==10,(name,arm,p.returncode,p.stderr,p.stdout)
    line=next(x for x in p.stdout.splitlines()
              if x.startswith("ATLASMAP1_TRIAL "))
    d=dict(field.split("=",1) for field in line.split()[1:] if "=" in field)
    model={}
    for text in p.stdout.splitlines():
        if text.startswith("v "):
            for l in map(int,text.split()[1:]):
                if l:model[abs(l)]=l>0
    assert len(model)==n,(name,arm,len(model),p.stdout)
    assert all(any(model[abs(l)]==(l>0) for l in c) for c in clauses), (name,arm)
    assert d["SAT_original_verified"]=="1"
    assert int(d["final_clauses"])<=len(clauses) if d["kind"]=="PARITY_DSU_SHORTCUT" else True
    return d

positive=[
    [-1,2],[1,-2],[2],
    [1,3,4],[-2,5,6],[7,8,9]
]
negated=[
    [1,2],[-1,-2],[1],
    [2,3,4],[-1,5,6],[7,8,9]
]
mixed=[
    [-1,2],[1,-2],[3,4,5],[3,4,-5],
    [3,4,6,7],[3,4,-6,7],[8,9,10]
]
unrelated=[[1,2,3],[4,5,6],[7,8,9]]
for name,clauses,expected in (
        ("alias_positive",positive,"PARITY_DSU_SHORTCUT"),
        ("alias_negated",negated,"PARITY_DSU_SHORTCUT"),
        ("mixed_alias_priority",mixed,"PARITY_DSU_SHORTCUT"),
        ("no_alias_fallback",unrelated,"none"),
    ):
    for arm in ("A","ATLASX","MAP1","MAP_LEARN"):
        d=trial(name,clauses,arm)
        if arm.startswith("MAP"):
            if expected=="PARITY_DSU_SHORTCUT":
                assert d["kind"]==expected and d["atlas_checked"]=="0",d
                assert int(d["saved_literals"])>0,d
            else:
                assert d["alias_edges"]=="0" and d["atlas_checked"]=="1",d
        print("ATLASMAP1_CONTROL "+json.dumps({"name":name,"arm":arm,"kind":d["kind"],"decision":d["decision"],"saved_literals":d["saved_literals"]},sort_keys=True),flush=True)

# Persistent memory is strictly a statistical gate, never a cache of assumed
# logical consequences. After 4 probes without a win, bypass expensive L2.
memory=ROOT/"learned_gate.tsv"
memory.unlink(missing_ok=True)
checks=[]
for i in range(9):
    d=trial("cold_unrelated",unrelated,"MAP_LEARN",memory.resolve())
    checks.append((d["atlas_checked"],d["memory_skip"]))
assert checks[:4]==[("1","0")]*4,checks
assert checks[4:7]==[("0","1")]*3,checks
assert checks[7]==("1","0"),checks
assert checks[8]==("0","1"),checks
assert memory.read_text().strip(), "learning table not written"
print("ATLASMAP1_MEMORY_PASS "+json.dumps(checks),flush=True)
print("ATLASMAP1_SMOKE_PASS",flush=True)
