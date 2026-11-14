#!/usr/bin/env python3
"""DELTAX-GUARD MIX1: previously unseen mixed synthetic CNFs + retrospective SAT2024.

24 fresh mixed synthetic sources: planted/random 3SAT, Tseitin UNSAT parity,
pigeonhole UNSAT, 3-coloring SAT/UNSAT. All are CONNECTED to guarded equality
motifs from the earlier DELTAX nonlinearity study, with new seeds and some
variable permutations. Plus eight original SAT2024 REAL36 sources, selected
deterministically by family and size, without examining solver results.

This is a research mixed *development/evaluation* cohort. REAL36 was used
before: it is NOT a fresh blind competition holdout. No generator metadata
is supplied to native solver execution.
"""
import hashlib
import itertools
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/drnas_deltax"))
sys.path.insert(0,str(ROOT/"research"))
import hard_formulas as H
import drnas_x55_cpu_real36 as REAL

SEED=1406112651
SYN_COUNT=24
REAL_COUNT=8

def sha(raw):return hashlib.sha256(raw).hexdigest()

def graph3(n,seed,force_k4):
    rng=random.Random(seed)
    colors=[rng.randrange(3) for _ in range(n)]
    def var(v,c):return 3*v+c+1
    cnf=[]
    for v in range(n):
        cnf.append([var(v,c) for c in range(3)])
        for c,d in itertools.combinations(range(3),2):
            cnf.append([-var(v,c),-var(v,d)])
    edges=set()
    for u in range(n):
        for v in range(u+1,n):
            if colors[u]!=colors[v] and rng.random()<0.20:
                edges.add((u,v))
    if force_k4:
        for u,v in itertools.combinations(range(4),2):
            edges.add((u,v))
    for u,v in sorted(edges):
        for c in range(3):
            cnf.append([-var(u,c),-var(v,c)])
    witness=[colors[v]==c for v in range(n) for c in range(3)]
    return 3*n,cnf,(None if force_k4 else witness)

def synth_generator():
    rows=[]
    def put(name,kind,core_n,core,seed,motifs,plant=None):
        n,cs=H.guarded_join(core_n,core,seed,count=motifs,plant=plant)
        rng=random.Random(seed ^ 0xD37A)
        # More than half of synthetic examples are genuinely permuted:
        # the solver cannot rely on source variable indices or order.
        if seed%3:
            perm=list(range(1,n+1));rng.shuffle(perm)
            change={i+1:perm[i] for i in range(n)}
            cs=H.remap(cs,change)
        if seed%2:
            rng.shuffle(cs)
        rows.append({"name":name,"family":kind,"source_kind":"synthetic",
                     "seed":seed,"nvars":n,"clauses":cs,"motifs":motifs,
                     "expected_core":"UNSPECIFIED" if plant is None else "PLANTED_SAT"})
    for i,n in enumerate((56,74,94,122,142,166)):
        seed=SEED+101*n+937*i
        core,plant=H.rng3(n,4.08+(i%3)*0.13,seed,planted=True)
        put(f"mix_planted3_n{n}_s{i}","mix_planted3",n,core,seed,2+(i%2),plant)
    for i,n in enumerate((52,76,96,118,144)):
        seed=SEED+197*n+877*i
        core,_=H.rng3(n,4.25+(i%3)*0.11,seed,planted=False)
        put(f"mix_random3_n{n}_s{i}","mix_random3",n,core,seed,2+(i%2))
    for i,n in enumerate((24,34,46,62)):
        seed=SEED+307*n+83*i
        core_n,core=H.tseitin(n)
        put(f"mix_tseitin_v{n}","mix_xor_tseitin",core_n,core,seed,2)
    for i,p in enumerate((6,7,8,9)):
        seed=SEED+431*p+79*i
        core_n,core=H.php(p)
        put(f"mix_php_{p}_{p-1}","mix_php_unsat",core_n,core,seed,2)
    for i,(n,bad) in enumerate(((16,False),(19,True),(23,False),(27,True),(31,False))):
        seed=SEED+551*n+37*i
        core_n,core,witness=graph3(n,seed,bad)
        put(f"mix_graph3_v{n}_{'unsat' if bad else 'planted'}",
            "mix_graph3",core_n,core,seed,2+(i%2),witness)
    assert len(rows)==SYN_COUNT,len(rows)
    return rows

def selected_real():
    original,_=REAL.official_manifest()
    by_family={}
    for s in original:
        by_family.setdefault(s["family"],[]).append(s)
    chosen=[]
    for family in sorted(by_family):
        items=sorted(by_family[family],key=lambda r:(r.get("bytes",10**30),r["sha256"]))
        chosen.append(items[0])
    remaining=sorted([x for x in original if x["sha256"] not in
                      {r["sha256"] for r in chosen}],
                     key=lambda r:(r.get("bytes",10**30),r["sha256"]))
    chosen=(chosen+remaining)[:REAL_COUNT]
    assert len(chosen)==REAL_COUNT and len({r["sha256"] for r in chosen})==REAL_COUNT
    return [{
        "name":"official_%02d_%s"%(s["id"],s["family"][:20].replace("/","_")),
        "family":"official/"+s["family"],
        "source_kind":"sat2024_retrospective",
        "original_real36_id":s["id"],
        "nvars":s["nvars"],"nclauses":s["nclauses"],
        "path":s["path"],"sha256":s["sha256"],
        "motifs":0,
    } for s in chosen]

def write(directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    old=json.loads(Path("deltax_hard_inputs/manifest.json").read_text())
    oldsha={x["sha256"] for x in old}
    synth=[]
    for row in synth_generator():
        clauses=row.pop("clauses")
        dest=directory/(row["name"]+".cnf")
        text="p cnf %d %d\n"%(row["nvars"],len(clauses))
        text+="".join(" ".join(map(str,c))+" 0\n" for c in clauses)
        dest.write_text(text)
        row["path"]=str(dest)
        row["nclauses"]=len(clauses)
        row["sha256"]=sha(dest.read_bytes())
        assert row["sha256"] not in oldsha,("PREVIOUSLY_SEEN_SYNTH_SOURCE",row["name"])
        synth.append(row)
    real=selected_real()
    result=synth+real
    assert len(result)==SYN_COUNT+REAL_COUNT and len({x["sha256"] for x in result})==len(result)
    assert len({x["family"] for x in result if x["source_kind"]=="synthetic"})==5
    # Each original source and manifest is SHA-pinned before benchmarking.
    for row in result:
        assert sha(Path(row["path"]).read_bytes())==row["sha256"]
    (directory/"manifest.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DELTAX_MIX1_SOURCES",json.dumps({
        "total":len(result),"new_synthetic":len(synth),"original_sat2024":len(real),
        "families":{key:sum(x["family"]==key for x in result)
                    for key in sorted({x["family"] for x in result})},
        "source_manifest_sha256":sha((directory/"manifest.json").read_bytes()),
        "novel_to_hard28_source_sha":True,"blind_holdout":False
    },sort_keys=True),flush=True)
    return result

if __name__=="__main__":write("deltax_mix1_inputs")
