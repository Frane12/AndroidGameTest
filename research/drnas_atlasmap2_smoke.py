#!/usr/bin/env python3
"""ATLAS-MAP2: original-CNF witnesses and online-vs-shadow smoke controls."""
import json
import pathlib
import subprocess

OUT=pathlib.Path("mre_atlasmap2")
OUT.mkdir(exist_ok=True)
EXE=(OUT/"bin/drnas_atlasmap2").resolve()
MODES=("A","ATLASX","MAP1","MAP2_LIVE","MAP2_SHADOW","MAP2_COMBO")

def encoded_pair(x,y,rhs):
    if rhs==0:return [[-x,y],[x,-y]]
    return [[x,y],[-x,-y]]

def run(name,clauses,mode,expect="SAT"):
    n=16
    path=OUT/(name+".cnf")
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    p=subprocess.run([str(EXE),str(path.resolve()),"--mode",mode,"--time","6"],
                     capture_output=True,text=True,timeout=12)
    assert p.returncode==(10 if expect=="SAT" else 20),(
       name,mode,p.returncode,p.stdout[-500:],p.stderr[-500:])
    ln=next(x for x in p.stdout.splitlines()
            if x.startswith("ATLASMAP2_TRIAL "))
    d=dict(pair.split("=",1) for pair in ln.split()[1:] if "=" in pair)
    assert d["status"]==expect,d
    if expect=="SAT":
        model={}
        for ln in p.stdout.splitlines():
            if ln.startswith("v "):
                for lit in map(int,ln.split()[1:]):
                    if lit:model[abs(lit)]=lit>0
        assert len(model)==n,(name,mode,len(model))
        assert all(any(model[abs(l)]==(l>0) for l in c) for c in clauses),(
            name,mode,model)
        assert d["SAT_original_verified"]=="1",d
    return d

cases={
 "live_chain_positive": encoded_pair(1,2,1)+encoded_pair(2,3,0)+[[1],[4,5,6]],
 "mixed_chain": encoded_pair(1,2,0)+encoded_pair(2,3,1)+
      [[1],[3,4,5],[-3,5,6],[7,-8,9],[10,11,12]],
 "non_xor_control": [[1,2,3],[4,5,6],[7,8,9],[10,11,12]],
 "incomplete_pair": [[1,2],[-2,3],[1],[4,5,6]],
}
for name,clauses in cases.items():
    for mode in MODES:
        d=run(name,clauses,mode)
        if name in ("live_chain_positive","mixed_chain"):
            if mode=="MAP2_LIVE":
                assert int(d["map2_groups"])>=1 and int(d["map2_implications"])>=2,d
                assert int(d["map2_reasons"])>=2,d
            if mode=="MAP2_SHADOW":
                assert int(d["map2_shadow_opportunities"])>=2,d
                assert int(d["map2_implications"])==0,d
        if name in ("non_xor_control","incomplete_pair"):
            assert int(d["map2_groups"])==0,d
        print("ATLASMAP2_CONTROL "+json.dumps({
            "case":name,"mode":mode,"status":d["status"],
            "groups":int(d["map2_groups"]),
            "live_implications":int(d["map2_implications"]),
            "shadow_opportunities":int(d["map2_shadow_opportunities"]),
            "E2E_s":float(d["E2E_s"])
        },sort_keys=True),flush=True)
print("ATLASMAP2_SMOKE_PASS",flush=True)
