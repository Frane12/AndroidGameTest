#!/usr/bin/env python3
"""DELTAX graph ablation: EXACTLY matching graph edges, controlled guarded links.

Twelve NEW graph cores (3 per planted SAT, K4 UNSAT, odd wheel UNSAT,
even wheel SAT). For each identical graph use:
  core   = graph alone (dimension/reference control);
  off    = same 3 guarded motifs, all linked to private dummy bits;
  low1   = first motif linked to one low-degree graph color bit;
  high1  = first motif linked to one high-degree graph color bit;
  low3   = three motifs linked to low-degree color bits;
  high3  = three motifs linked to high-degree color bits.

For the FIVE motif variants, variables, clause count, graph core,
clause order permutation, gadget logic and original guards are identical.
Only the target literal in TWO binary link clauses per rewired motif changes.
No solver is told formula labels, graph facts, color witnesses or degrees.

This ablates coupling and location rather than using unrelated graphs as
controls. Still synthetic: NOT a representative blind SAT holdout.
"""
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"research/drnas_deltax_guard"),
             str(ROOT/"research/drnas_deltax")]
from graphlab_sources import color_cnf,random_colored_graph,wheel_graph,check_graph_certificate
from hard_formulas import motif

SEED=20261114231
N_MOTIFS=3
VARIANTS=("core","off","low1","high1","low3","high3")
MATCHED=("off","low1","high1","low3","high3")

def sha(b):return hashlib.sha256(b).hexdigest()
def canon(cs):return [tuple(sorted(c)) for c in cs]

def graphs():
    result=[]
    for j,n in enumerate((19,26,34)):
        seed=SEED+j*1771
        edges,colors=random_colored_graph(n,seed,0.18+0.035*j,False)
        result.append((f"planted_n{n}_s{j}","planted",n,edges,colors,seed))
    for j,n in enumerate((20,27,35)):
        seed=SEED+100000+j*2053
        edges,colors=random_colored_graph(n,seed,0.13+0.038*j,True)
        result.append((f"k4_n{n}_s{j}","k4",n,edges,colors,seed))
    for j,rim in enumerate((9,13,17)):
        n,edges,colors=wheel_graph(rim)
        result.append((f"oddwheel_r{rim}","odd_wheel",n,edges,colors,SEED+200000+j*2589))
    for j,rim in enumerate((10,14,18)):
        n,edges,colors=wheel_graph(rim)
        result.append((f"evenwheel_r{rim}","even_wheel",n,edges,colors,SEED+300000+j*2339))
    assert len(result)==12
    return result

def graph_degree(n,edges):
    degree=[0]*n
    for a,b in edges:degree[a]+=1;degree[b]+=1
    return degree

def policies(n,edges,seed):
    deg=graph_degree(n,edges)
    rng=random.Random(seed^0xAB1A710)
    priority=list(range(n));rng.shuffle(priority)
    rank={v:i for i,v in enumerate(priority)}
    low=sorted(range(n),key=lambda v:(deg[v],rank[v]))[:3]
    high=sorted((v for v in range(n) if v not in low),
                key=lambda v:(-deg[v],rank[v]))[:3]
    assert len(set(low+high))==6
    # Each slot i gets a fixed color across all graph variants.
    colors=[random.Random(seed+17*i+140).randrange(3) for i in range(3)]
    return deg,low,high,colors

def make_cnf(graph_id,kind,n,edges,colors,seed,variant):
    check_graph_certificate(n,edges,colors,kind)
    degrees,low,high,choice_colors=policies(n,edges,seed)
    core=color_cnf(n,edges)
    color_witness=None if colors is None else [colors[v]==c for v in range(n) for c in range(3)]
    graph_digest=sha(json.dumps([n,sorted(edges)],separators=(",",":")).encode())
    if variant=="core":
        nvars=3*n
        clauses=[list(c) for c in core]
        if color_witness is not None:
            assert all(any((color_witness[abs(l)-1])==(l>0) for l in c) for c in clauses)
        return nvars,clauses,[],{"graph_sha256":graph_digest,"graph_degree":degrees,
                                  "low_vertices":low,"high_vertices":high,
                                  "color_choices":choice_colors,
                                  "matched_nvars":False}
    offset=5*N_MOTIFS
    gbase=offset+3*n
    # Three dedicated dummy target variables plus three paired dummy
    # partners; these appear in FIXED clauses on ALL five motif arms.
    dummy=[gbase+i+1 for i in range(3)]
    pair=[gbase+i+4 for i in range(3)]
    nvars=gbase+6
    clauses=[[(abs(l)+offset)*(1 if l>0 else -1) for l in c] for c in core]
    for i in range(N_MOTIFS):
        clauses+=motif(5*i)
        clauses+=[[-(5*i+3)],[-(5*i+4)]]
    for d,p in zip(dummy,pair):
        clauses += [[d,p],[-d,-p]] # always: p = not d
    link_role=[]
    for i in range(N_MOTIFS):
        y=5*i+5
        if variant in ("low1","high1","low3","high3") and (
            variant.endswith("3") or i==0):
            loc=low[i] if variant.startswith("low") else high[i]
            col=choice_colors[i]
            target=offset+3*loc+col+1
            link_role.append({"slot":i,"y_variable":y,"attached":True,"vertex":loc,
                              "degree":degrees[loc],"color_index":col,
                              "target_variable":target})
        else:
            target=dummy[i]
            link_role.append({"slot":i,"y_variable":y,"attached":False,"vertex":None,
                              "degree":None,"color_index":None,
                              "target_variable":target})
        clauses += [[-y,target],[y,-target]]
    assert len(clauses)==len(core)+3*(9+2)+6+6
    # Explicit known satisfying *whole formula* witness when graph is 3-colorable.
    if color_witness is not None:
        model={offset+j+1:bool(x) for j,x in enumerate(color_witness)}
        for d,p in zip(dummy,pair):model[d]=False;model[p]=True
        for r in link_role:
            i=r["slot"];y=5*i+5;target=r["target_variable"]
            v=model[target]
            model.update({5*i+1:v,5*i+2:v,5*i+3:False,5*i+4:False,y:v})
        assert len(model)==nvars,("INCOMPLETE_MODEL",graph_id,variant,len(model),nvars)
        assert all(any(model[abs(l)]==(l>0) for l in c) for c in clauses),(
            "GRAPH_ABLATION_PLANTED_MODEL_INVALID",graph_id,variant)
    return nvars,clauses,link_role,{"graph_sha256":graph_digest,
                                    "graph_degree":degrees,
                                    "low_vertices":low,"high_vertices":high,
                                    "color_choices":choice_colors,
                                    "matched_nvars":True}

def write(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for graph_id,kind,n,edges,colors,seed in graphs():
        prepared={}
        for variant in VARIANTS:
            nv,clauses,links,common=make_cnf(graph_id,kind,n,edges,colors,seed,variant)
            # Apply SAME full-variable permutation and clause-index ordering
            # to all five matched variants. The no-gadget reference is
            # intentionally separate; its total variable count is smaller.
            if variant!="core":
                shuffled=list(range(1,nv+1))
                random.Random(seed^0xC010A).shuffle(shuffled)
                perm={i+1:shuffled[i] for i in range(nv)}
                clauses=[[(1 if lit>0 else -1)*perm[abs(lit)] for lit in c]
                         for c in clauses]
                for link in links:
                    link["target_variable"]=perm[link["target_variable"]]
                    link["y_variable"]=perm[link["y_variable"]]
                order=list(range(len(clauses)))
                random.Random(seed^0x57AB1E).shuffle(order)
                clauses=[clauses[i] for i in order]
            else:
                order=list(range(len(clauses)))
                random.Random(seed^0x57AB1E).shuffle(order)
                clauses=[clauses[i] for i in order]
            text=f"p cnf {nv} {len(clauses)}\n"+"".join(
                " ".join(map(str,c))+" 0\n" for c in clauses)
            path=folder/(graph_id+"__"+variant+".cnf")
            path.write_text(text)
            entry={"name":graph_id+"__"+variant,
                   "family":"graphablation/"+kind,"graph_id":graph_id,
                   "graph_kind":kind,"graph_vertices":n,"graph_edges":len(edges),
                   "graph_edges_explicit":edges,"graph_sha256":common["graph_sha256"],
                   "graph_degree":common["graph_degree"],
                   "low_vertices":common["low_vertices"],
                   "high_vertices":common["high_vertices"],
                   "color_choices":common["color_choices"],
                   "variant":variant,"attached_links":sum(r["attached"] for r in links),
                   "link_role":links,
                   "source_kind":"new_synthetic_graph_ablation",
                   "nvars":nv,"nclauses":len(clauses),"path":str(path),
                   "sha256":sha(path.read_bytes()),
                   "expected_by_graph":"SAT" if colors is not None else "UNSAT",
                   "certified_graph_structure":kind,"seed":seed}
            manifest.append(entry)
            prepared[variant]=entry
        base=prepared["off"]
        assert all(prepared[x]["nvars"]==base["nvars"] and
                   prepared[x]["nclauses"]==base["nclauses"] and
                   prepared[x]["graph_sha256"]==base["graph_sha256"]
                   for x in MATCHED),(graph_id,"MISMATCHED_ABLATION")
        assert all(prepared[x]["attached_links"]==(0 if x=="off" else 1 if x.endswith("1") else 3)
                   for x in MATCHED)
    assert len(manifest)==12*len(VARIANTS)
    assert len({x["sha256"] for x in manifest})==len(manifest)
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print("DELTAX_ABLATION_SOURCES",json.dumps({
        "graphs":12,"variants":list(VARIANTS),"sources":len(manifest),
        "SAT_graphs":sum(x["expected_by_graph"]=="SAT" and x["variant"]=="core" for x in manifest),
        "UNSAT_graphs":sum(x["expected_by_graph"]=="UNSAT" and x["variant"]=="core" for x in manifest),
        "all_matched_same_nvars_and_nclauses":True,
        "manifest_sha256":sha((folder/"manifest.json").read_bytes()),
        "unseen_graph_seeds":True,
        "blind_holdout":False,
    },sort_keys=True),flush=True)
    return manifest

if __name__=="__main__":write("deltax_graph_ablation1_inputs")
