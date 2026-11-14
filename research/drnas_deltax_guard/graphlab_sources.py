#!/usr/bin/env python3
"""GraphLab1: novel graph 3-coloring formulas with exact witnesses/obstructions.

Tests why proof-carrying DELTAX-GUARD equalities help some graph-coloring
CNFs. Source-disjoint from MIX1. No graph labels or oracle values passed
to native solver. Exact original-model SAT and original-DRAT UNSAT checks
are performed by the separate paired test harness.

Build graph-coloring cores of:
  - planted 3-colorable connected-style random graphs,
  - K4-containing 4-chromatic graphs (UNSAT),
  - odd wheels (UNSAT) and even wheels (SAT),
  - two no-gadget controls (one SAT and one UNSAT).
Connect 2 or 3 nonlinear guarded equivalence motifs to graph vertex-color
variables. Randomize all variable IDs and clause order on alternating cases.
"""
import hashlib
import itertools
import json
import random
import sys
from pathlib import Path

R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/"research/drnas_deltax"))
import hard_formulas as H
SEED=611141227

def color_cnf(n,edges):
    def v(i,c):return 3*i+c+1
    clauses=[]
    for i in range(n):
        clauses.append([v(i,c) for c in range(3)])
        for a,b in itertools.combinations(range(3),2):
            clauses.append([-v(i,a),-v(i,b)])
    for i,j in sorted(set(edges)):
        assert 0<=i<j<n
        for c in range(3):
            clauses.append([-v(i,c),-v(j,c)])
    return clauses

def random_colored_graph(n,seed,density,k4=False):
    rng=random.Random(seed)
    planted=[(i+rng.randrange(3))%3 for i in range(n)]
    rng.shuffle(planted)
    # Connect all vertices while preserving planted 3-coloring.
    edges=set()
    for i in range(1,n):
        possible=[j for j in range(i) if planted[j]!=planted[i]]
        if possible:edges.add(tuple(sorted((i,rng.choice(possible)))))
    for i,j in itertools.combinations(range(n),2):
        if planted[i]!=planted[j] and rng.random()<density:
            edges.add((i,j))
    if k4:
        for i,j in itertools.combinations(range(4),2):
            edges.add((i,j))
    return sorted(edges), (None if k4 else planted)

def wheel_graph(rim):
    # A wheel is 3-colorable iff the rim cycle is even.
    assert rim>=5
    n=rim+1
    edges=set()
    for i in range(rim):
        edges.add(tuple(sorted((i,(i+1)%rim))))
        edges.add((i,rim))
    planted=None
    if rim%2==0:
        planted=[1 if i%2==0 else 2 for i in range(rim)]+[0]
    return n,sorted(edges),planted

def check_graph_certificate(n,edges,assignment,kind):
    if kind=="planted":
        assert assignment is not None and len(assignment)==n
        assert all(assignment[i]!=assignment[j] for i,j in edges)
    elif kind=="k4":
        assert all((i,j) in set(edges) for i,j in itertools.combinations(range(4),2))
    elif kind=="odd_wheel":
        assert n>=6 and (n-1)%2==1
        edges=set(edges)
        assert all(tuple(sorted((i,(i+1)%(n-1)))) in edges for i in range(n-1))
        assert all((i,n-1) in edges for i in range(n-1))
    elif kind=="even_wheel":
        assert (n-1)%2==0
        assert assignment is not None
        assert all(assignment[i]!=assignment[j] for i,j in edges)
    else:
        raise ValueError(kind)

def check_full_planted_extension(clauses,core_assignment,core_n,motifs):
    # The graph planted assignment extends to motif vars, because each
    # motif y is linked to exactly one shifted graph-core color literal.
    model={}
    offset=5*motifs
    for i,bit in enumerate(core_assignment,start=1):
        model[offset+i]=bool(bit)
    for i in range(motifs):
        a=5*i+1;z=5*i+2;g1=5*i+3;g2=5*i+4;y=5*i+5
        links=[c for c in clauses if len(c)==2 and -y in c and any(
            lit>offset for lit in c)]
        assert len(links)==1,(y,links)
        target=next(lit for lit in links[0] if lit!=-y)
        assert target>offset
        bit=model[target]
        model.update({a:bit,z:bit,g1:False,g2:False,y:bit})
    assert all(any(model[abs(l)]==(l>0) for l in c) for c in clauses),(
        "PLANTED_FULL_CNF_WITNESS_INVALID",motifs)
    return True

def generate():
    rows=[]
    # 6 colored random SAT graphs; 4 graphs with an explicit K4 obstruction.
    for i,n in enumerate((17,20,24,28,33,37)):
        seed=SEED+1049*i
        edges,colors=random_colored_graph(n,seed,0.14+(i%3)*0.045,False)
        rows.append((f"planted_v{n}_s{i}","planted",n,edges,colors,2+i%2,seed,True))
    for i,n in enumerate((18,22,26,32)):
        seed=SEED+3011*i+200
        edges,colors=random_colored_graph(n,seed,0.12+(i%2)*0.07,True)
        rows.append((f"k4_unsat_v{n}_s{i}","k4",n,edges,colors,2+i%2,seed,True))
    for i,rim in enumerate((5,7,9,11)):
        n,edges,colors=wheel_graph(rim)
        rows.append((f"oddwheel_unsat_r{rim}","odd_wheel",n,edges,colors,2,SEED+5701*i,True))
    for i,rim in enumerate((6,8,10,12)):
        n,edges,colors=wheel_graph(rim)
        rows.append((f"evenwheel_sat_r{rim}","even_wheel",n,edges,colors,2,SEED+7409*i,True))
    # Same-colored-graph cores with NO guarded gadget at all: negative
    # controls for false nonlinear witnesses. They are distinct formulas,
    # not substitutes for JOIN vs GUARD same-formula A/B controls.
    for n,kind,seed in ((23,"planted",SEED+98001),(27,"k4",SEED+98002)):
        edges,colors=random_colored_graph(n,seed,0.19,kind=="k4")
        rows.append((f"core_only_{kind}_v{n}",kind,n,edges,colors,0,seed,False))
    assert len(rows)==20
    return rows

def write(folder):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    data=[]
    for name,kind,n,edges,colors,motifs,seed,with_gadget in generate():
        check_graph_certificate(n,edges,colors,kind)
        core=color_cnf(n,edges)
        known=None if colors is None else [colors[v]==c for v in range(n) for c in range(3)]
        links=[]
        if motifs:
            total,cnf=H.guarded_join(3*n,core,seed,count=motifs,plant=known)
            if known is not None:
                check_full_planted_extension(cnf,known,3*n,motifs)
            for i in range(motifs):
                y=5*i+5
                candidates=[c for c in cnf if len(c)==2 and -y in c
                            and any(lit>5*motifs for lit in c)]
                assert len(candidates)==1
                target=next(lit for lit in candidates[0] if lit!=-y)
                core_var=target-5*motifs-1
                vertex,color=divmod(core_var,3)
                links.append({"gadget_id":i,"y":y,"core_variable":target,
                              "graph_vertex":vertex,"color":color,
                              "vertex_degree":sum(vertex in edge for edge in edges)})
        else:
            total=3*n;cnf=core
        # Important: deterministic complete permutation + clause shuffle
        # means the first five variables are not always gadget variables.
        shuffled=seed%2==1
        if shuffled:
            rng=random.Random(seed+17)
            vs=list(range(1,total+1));rng.shuffle(vs)
            perm={i+1:vs[i] for i in range(total)}
            cnf=[[(1 if lit>0 else -1)*perm[abs(lit)] for lit in c] for c in cnf]
            rng.shuffle(cnf)
        for link in links:
            if shuffled:
                link["y"]=perm[link["y"]]
                link["core_variable"]=perm[link["core_variable"]]
        text=f"p cnf {total} {len(cnf)}\n"
        text+="".join(" ".join(map(str,c))+" 0\n" for c in cnf)
        path=folder/(name+".cnf")
        path.write_text(text)
        data.append({
            "name":name,"family":"graphlab/"+kind,"source_kind":"synthetic_graph",
            "graph_kind":kind,"graph_vertices":n,"graph_edges":len(edges),
            "graph_edges_explicit":edges,
            "motifs":motifs,"seed":seed,"permuted":shuffled,
            "gadget_to_graph_links":links,
            "nvars":total,"nclauses":len(cnf),"path":str(path),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "expected_by_graph":"SAT" if colors is not None else "UNSAT",
            "original_graph_certificate_checked":True
        })
    assert len(data)==20 and len({s["sha256"] for s in data})==20
    (folder/"manifest.json").write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print("DELTAX_GRAPHLAB_SOURCES",json.dumps({
        "cases":len(data),"graph_types":{k:sum(x["graph_kind"]==k for x in data)
                                        for k in sorted({x["graph_kind"] for x in data})},
        "sha256_manifest":hashlib.sha256((folder/"manifest.json").read_bytes()).hexdigest(),
        "blinded_solver_input":True,"promotion":False
    },sort_keys=True),flush=True)
    return data

if __name__=="__main__":write("deltax_graphlab1_inputs")
