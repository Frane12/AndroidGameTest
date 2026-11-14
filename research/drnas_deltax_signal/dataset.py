#!/usr/bin/env python3
"""DELTAX SIGNAL1 — 60 SEALED graph groups, 3 matched CNF variants each.

30 train / 15 validation / 15 holdout independent graph cores. Stratified
across: planted SAT, explicit K4 UNSAT, odd-wheel UNSAT, even-wheel SAT.
Every graph has same-source-dimension OFF, LOW1, HIGH1 variants, which
change only the motif-to-vertex binary target literals. A graph's variants
NEVER cross train/validation/holdout. No graph metadata enters solver.

Seeds are fresh relative to DELTAX GRAPH-ABLATION1; source SHA disjointness
is checked against regenerated historical graph benchmark sources.
"""
import collections
import hashlib
import json
import random
import sys
from pathlib import Path

R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/"research/drnas_deltax_guard"),
             str(R/"research/drnas_deltax")]
from graphlab_sources import random_colored_graph,wheel_graph
from graph_ablation_sources import make_cnf,write as previous_write

SEED=20261114729
SPLITS={
    "planted":(7,4,4),
    "k4":(7,4,4),
    "odd_wheel":(8,3,4),
    "even_wheel":(8,4,3),
}
VARIANTS=("off","low1","high1")
KINDS=("planted","k4","odd_wheel","even_wheel")

def sha(raw):return hashlib.sha256(raw).hexdigest()

def graphs():
    all_graphs=[]
    for kind in KINDS:
        for index in range(15):
            seed=SEED+100000*KINDS.index(kind)+5077*index
            if kind=="planted":
                n=19+2*index
                edges,colors=random_colored_graph(n,seed,0.15+0.025*(index%4),False)
            elif kind=="k4":
                n=20+2*index
                edges,colors=random_colored_graph(n,seed,0.13+0.024*(index%4),True)
            elif kind=="odd_wheel":
                n,edges,colors=wheel_graph(9+2*index)
            else:
                n,edges,colors=wheel_graph(10+2*index)
            a,b,c=SPLITS[kind]
            split="train" if index<a else "validation" if index<a+b else "holdout"
            all_graphs.append({"graph_id":f"{kind}_new_{index:02}",
                "kind":kind,"split":split,"seed":seed,"n":n,"edges":edges,
                "colors":colors})
    assert len(all_graphs)==60
    assert collections.Counter(g["split"] for g in all_graphs)=={
        "train":30,"validation":15,"holdout":15}
    return all_graphs

def write(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    out=[]
    for graph in graphs():
        kind=graph["kind"];n=graph["n"];edges=graph["edges"];colors=graph["colors"]
        seed=graph["seed"];name=graph["graph_id"]
        variants={}
        for variant in VARIANTS:
            nvars,clauses,roles,details=make_cnf(
                name,kind,n,edges,colors,seed,variant)
            # Reuse identical, deterministic permutation across all variants
            # on one graph. Source labels only appear in offline manifest.
            rng=random.Random(seed ^ 0x5A11C011)
            perm=list(range(1,nvars+1));rng.shuffle(perm)
            varmap={i+1:perm[i] for i in range(nvars)}
            clauses=[[(1 if l>0 else -1)*varmap[abs(l)] for l in c]
                     for c in clauses]
            for role in roles:
                role["y_variable"]=varmap[role["y_variable"]]
                role["target_variable"]=varmap[role["target_variable"]]
            order=list(range(len(clauses)))
            random.Random(seed ^ 0x0A55).shuffle(order)
            clauses=[clauses[i] for i in order]
            payload=f"p cnf {nvars} {len(clauses)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses)
            path=folder/(name+"__"+variant+".cnf")
            path.write_text(payload)
            entry={
                "name":name+"__"+variant,"graph_id":name,"family":kind,
                "split":graph["split"],"variant":variant,
                "source_kind":"new_matched_graph_signal",
                "seed":seed,"graph_kind":kind,"graph_vertices":n,
                "graph_edges":len(edges),
                "graph_sha256":details["graph_sha256"],
                "graph_roles":roles,
                "nvars":nvars,"nclauses":len(clauses),
                "expected":"SAT" if colors is not None else "UNSAT",
                "path":str(path),"sha256":sha(path.read_bytes())
            }
            variants[variant]=entry
            out.append(entry)
        assert len({x["nvars"] for x in variants.values()})==1
        assert len({x["nclauses"] for x in variants.values()})==1
        assert len({x["graph_sha256"] for x in variants.values()})==1
    assert len(out)==180 and len({r["sha256"] for r in out})==180
    # Historical checks use graph-ablation family with different seeds;
    # ensure exact source SHA separation, not just a verbal claim.
    refdir=folder.parent/(folder.name+"-historical-shas")
    old=previous_write(refdir)
    historical={r["sha256"] for r in old}
    assert not historical.intersection(r["sha256"] for r in out),(
        "SOURCE_SHA_OVERLAP_PRIOR_GRAPHLAB")
    for split in ("train","validation","holdout"):
        rows=[r for r in out if r["split"]==split]
        manifest=folder/(split+"_manifest.json")
        manifest.write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
        assert len({r["graph_id"] for r in rows})==(
            30 if split=="train" else 15)
    (folder/"manifest.json").write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    result={
        "status":"FROZEN","distinct_graphs":60,"total_CNF_sources":180,
        "train_graphs":30,"validation_graphs":15,"holdout_graphs":15,
        "family_counts":dict(collections.Counter(x["family"] for x in
                      out if x["variant"]=="off")),
        "split_manifest_shas":{
            split:sha((folder/(split+"_manifest.json")).read_bytes())
            for split in ("train","validation","holdout")
        },
        "all_manifest_sha256":sha((folder/"manifest.json").read_bytes()),
        "source_disjoint_from_prior_ablation":True,
        "only_graph_metadata_outside_solver":True,
        "graph_level_split_no_leakage":True,
        "same_nvars_nclauses_in_graph_variants":True,
        "no_promotion":True
    }
    (folder/"freeze.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("DELTAX_SIGNAL_DATA_FROZEN",json.dumps(result,sort_keys=True),flush=True)
    return result

if __name__=="__main__":write("deltax_signal1_inputs")
