#!/usr/bin/env python3
"""Source-only k-color / (k+1)-clique -> standard VeriPB cutting planes.

Every accepted output is a formal contradiction of the EXACT original
DIMACS source after external VeriPB verification. Graph, selector groups,
color matchings and clique are all reconstructed from source clauses only.
Unsupported / budget exhaustion returns UNKNOWN. This is not a polynomial
general graph coloring or P=NP algorithm.
"""
import argparse,hashlib,json,pathlib,random,sys,time
from collections import Counter

MAX_BYTES=12_000_000
MAX_NODES=2000
MAX_SEARCH_NODES=400_000
MAX_WIDTH=64

class Unsupported(Exception): pass

def need(ok,why):
    if not ok: raise Unsupported(why)

def parse(raw):
    need(len(raw)<=MAX_BYTES,"source-size gate")
    nv=nc=None;pending=[];clauses=[]
    for line in raw.decode("ascii").splitlines():
        tok=line.split()
        if not tok or tok[0]=="c":continue
        if tok[0]=="p":
            need(nv is None and len(tok)==4 and tok[1]=="cnf","invalid header")
            nv,nc=int(tok[2]),int(tok[3])
            need(0<nv<=100000 and 0<=nc<=2_000_000,"header bounds")
            continue
        need(nv is not None,"header missing")
        for field in tok:
            lit=int(field)
            need(abs(lit)<=nv,"literal not in source")
            if lit:pending.append(lit)
            else:
                need(len(pending)<=512,"max clause width")
                clauses.append(tuple(pending));pending=[]
    need(nv is not None and not pending and len(clauses)==nc,"source clause count mismatch")
    return nv,clauses

def collect(clauses):
    groups=[];source_index={}
    for index,row in enumerate(clauses,1):
        source_index.setdefault(frozenset(row),index)
        if 2<=len(row)<=MAX_WIDTH and all(v>0 for v in row) and len(set(row))==len(row):
            groups.append(tuple(row))
    need(2<=len(groups)<=MAX_NODES,"positive source group count outside gate")
    widths=Counter(map(len,groups))
    need(len(widths)==1,"heterogeneous positive groups unsupported")
    k=next(iter(widths))
    need(2<=k<=MAX_WIDTH,"unsupported color count")
    seen=set()
    for group in groups:
        for lit in group:
            need(lit not in seen,"source positive groups overlap")
            seen.add(lit)
    need(len(groups)>k,"not enough vertices for k+1 clique")
    return groups,k,source_index

def graph(groups,k,clauses):
    """Edges require a source-backed perfect matching of all k selectors.

    A single complete matching is NOT enough to prove a consistent graph
    coloring instance: clique_alignment separately verifies consistency
    of the k color mappings across the entire chosen clique.
    """
    n=len(groups)
    owner={v:(i,c) for i,g in enumerate(groups) for c,v in enumerate(g)}
    maps={}
    for row in clauses:
        if len(row)!=2 or row[0]>=0 or row[1]>=0:continue
        a=owner.get(-row[0]);b=owner.get(-row[1])
        if a is None or b is None or a[0]==b[0]:continue
        if a[0]>b[0]:a,b=b,a
        code=a[0]*n+b[0]
        prior=maps.setdefault(code,{})
        if prior is None:continue
        existing=prior.get(a[1])
        if existing is not None and existing!=b[1]:
            maps[code]=None
        else:prior[a[1]]=b[1]
    adj=[0]*n;complete={}
    for code,match in maps.items():
        if match is None or len(match)!=k or len(set(match.values()))!=k:continue
        if set(match)!=set(range(k)):continue
        u,v=divmod(code,n)
        adj[u]|=1<<v
        adj[v]|=1<<u
        complete[code]=tuple(match[c] for c in range(k))
    return adj,complete

def clique_alignment(clique,groups,index,maps):
    if not clique:return None
    n=len(groups);k=len(groups[0]);anchor=clique[0]
    aligned={anchor:tuple(groups[anchor])}
    for v in clique[1:]:
        match=maps.get(anchor*n+v)
        if match is None:return None
        aligned[v]=tuple(groups[v][match[c]] for c in range(k))
    for i,u in enumerate(clique):
        for v in clique[i+1:]:
            if not all(frozenset((-aligned[u][c],-aligned[v][c])) in index
                       for c in range(k)):
                return None
    return aligned

def clique_search(adj,target,check,max_trials=MAX_SEARCH_NODES):
    nodes=0;n=len(adj)
    # Bounded deterministic diversification avoids poor highest-degree hubs.
    for trial in range(64):
        rng=random.Random((target<<32) ^ (n<<12) ^ trial)
        chosen=[];candidates=(1<<n)-1
        while candidates and len(chosen)<target:
            options=[v for v in range(n) if candidates & (1<<v)]
            options.sort(key=lambda v:(adj[v]&candidates).bit_count(),reverse=True)
            v=options[rng.randrange(min(5,len(options)))]
            chosen.append(v)
            candidates &= adj[v]
        if len(chosen)>=target:
            candidate=tuple(sorted(chosen))
            aligned=check(candidate)
            if aligned is not None:return candidate,aligned,nodes+trial+1
    def descend(chosen,candidates):
        nonlocal nodes
        nodes+=1
        if nodes>max_trials:raise Unsupported("clique search operation budget")
        if len(chosen)==target:
            candidate=tuple(sorted(chosen));aligned=check(candidate)
            return (candidate,aligned) if aligned is not None else None
        if len(chosen)+candidates.bit_count()<target:return None
        while candidates:
            options=[v for v in range(n) if candidates & (1<<v)]
            u=max(options,key=lambda v:(adj[v]&candidates).bit_count())
            candidates &= ~(1<<u)
            found=descend(chosen+(u,),candidates&adj[u])
            if found is not None:return found
            if len(chosen)+candidates.bit_count()<target:break
        return None
    found=descend((),(1<<n)-1)
    return (None,None,nodes) if found is None else (found[0],found[1],nodes)

def compile_source(raw,max_trials=MAX_SEARCH_NODES):
    t=time.perf_counter()
    nv,clauses=parse(raw)
    groups,k,index=collect(clauses)
    adj,maps=graph(groups,k,clauses)
    clique,aligned,nodes=clique_search(
        adj,k+1,lambda q:clique_alignment(q,groups,index,maps),
        max_trials=max_trials)
    need(clique is not None,"no source-backed k+1 clique under budget")
    proof=["pseudo-Boolean proof version 3.0",f"f {len(clauses)} ;"]
    last=len(clauses);uppers=[]
    for color in range(k):
        vec=[aligned[u][color] for u in clique]
        previous=index[frozenset((-vec[0],-vec[1]))]
        for r in range(3,len(vec)+1):
            new=vec[r-1];ops=[str(previous)]
            if r-2!=1:ops.extend([str(r-2),"*"])
            for x in vec[:r-1]:
                ops.extend([str(index[frozenset((-x,-new))]),"+"])
            ops.extend([str(r-1),"d"])
            proof.append("pol "+" ".join(ops)+" ;")
            last+=1;previous=last
        uppers.append(previous)
    alo_ids=[index[frozenset(groups[u])] for u in clique]
    ops=[str(alo_ids[0])]
    for constraint in alo_ids[1:]+uppers:
        ops.extend([str(constraint),"+"])
    proof.append("pol "+" ".join(ops)+" ;")
    proof.extend(["output NONE ;","conclusion UNSAT ;",
                  "end pseudo-Boolean proof ;"])
    pb="\n".join(proof)+"\n"
    need(len(pb)<=4_000_000,"proof-size gate")
    return pb,{
        "status":"EMITTED_EXTERNAL_VERIPB_REQUIRED",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "source_vars":nv,"source_clauses":len(clauses),
        "color_count":k,"alo_vertices":len(groups),
        "source_graph_edges":sum(a.bit_count() for a in adj)//2,
        "clique_vertices_one_based":[u+1 for u in clique],
        "clique_vertices_zero_based":list(clique),
        "clique_size":len(clique),
        "source_alo_clauses":len(clique),
        "source_edge_color_clauses":len(clique)*(len(clique)-1)//2*k,
        "cp_derived_steps":last-len(clauses)+1,
        "search_nodes":nodes,
        "emitter_wall_s":round(time.perf_counter()-t,6),
        "pbp_bytes":len(pb.encode()),
        "permutation_aligned_source_edges":True,
        "do_not_claim_polynomial_clique_search":True,
        "math":"k+1 source-backed color clique impossible with k colors"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--pbp",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    p.add_argument("--max-search-nodes",type=int,default=MAX_SEARCH_NODES)
    a=p.parse_args()
    try:
        source=a.cnf.read_bytes()
        proof,meta=compile_source(source,a.max_search_nodes)
        a.pbp.parent.mkdir(parents=True,exist_ok=True)
        a.pbp.write_text(proof)
        a.meta.write_text(json.dumps(meta,sort_keys=True,indent=2)+"\n")
        print("GRAPH_CLIQUE_VERIPB_EMITTED "+json.dumps(meta,sort_keys=True),flush=True)
        return 0
    except (Unsupported,ValueError,TypeError,OverflowError,IndexError,KeyError,
            UnicodeError) as exc:
        a.pbp.unlink(missing_ok=True)
        print("GRAPH_CLIQUE_UNKNOWN "+str(exc),flush=True)
        return 2

if __name__=="__main__":raise SystemExit(main())
