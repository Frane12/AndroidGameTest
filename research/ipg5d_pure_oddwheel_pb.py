#!/usr/bin/env python3
"""IPG5D: pure ORIGINAL-SOURCE cutting-planes UNSAT proof for odd wheels.

A source-clause-recognized odd wheel W_(2k+1) in a graph 3-coloring CNF
has rim vertices 0..2k and a hub adjacent to all. Original source clauses:
  - ALO exactly-one triples on each vertex,
  - binary inter-vertex conflicts of all three corresponding colors.

Pure cutting-plane derivation, no RUP, SAT/CDCL/DPLL or model oracle:

For each color c, sum the (2k+1) source rim edge mutex inequalities:
       2 sum_rim ~x_(v,c) >= 2k+1,
then divide by 2:
       sum_rim ~x_(v,c) >= k+1,
equivalently at most k rim vertices use color c.

Sum rim vertex ALOs: sum_{rim,c} x_(v,c) >= 2k+1.
Add the odd-cycle caps for the OTHER two colors:
       sum_rim x_(v,c) >= 1.

Sum all source hub-to-rim edge mutex clauses for color c:
       (2k+1) ~x_(hub,c) + sum_rim ~x_(v,c) >= 2k+1.
Add the just-derived color-presence lemma and divide by 2k+1:
       ~x_(hub,c) >= 1.
Repeat for all c; sum all three with original hub ALO
       sum_c x_(hub,c) >= 1
to obtain 0 >= 1. STANDARD VeriPB3 pure 'pol' proof.

ALL premises are exact original CNF clauses and IDs. Any ambiguity,
missing edge or non-odd-wheel structure -> UNKNOWN and no proof.
Generator output is UNCHECKED until pinned EXTERNAL VeriPB accepts it.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys

from ipg4_rup_drat_to_veripb import dimacs

def keypair(a,b):
    return frozenset((a,b))

def source_wheel(raw_path):
    raw,nvars,clauses=dimacs(raw_path)
    if nvars<18 or nvars>45:
        raise ValueError("wheel variable count outside 6..15 source groups")
    index={}
    for i,c in enumerate(clauses,1):
        index.setdefault(frozenset(c),i)
    groups=[]
    owner={}
    for c in clauses:
        if len(c)!=3 or any(x<=0 for x in c):continue
        group=tuple(sorted(c))
        if len(set(group))!=3:continue
        if not all(keypair(-a,-b) in index for a,b in itertools.combinations(group,2)):
            continue
        if any(v in owner for v in group):
            raise ValueError("overlapping original source exactly-one groups")
        for v in group:owner[v]=len(groups)
        groups.append(group)
    if len(groups)<6 or len(groups)>15 or set(owner)!=set(range(1,nvars+1)):
        raise ValueError("source does not contain complete disjoint 3-way onehot")
    # A genuine graph edge exists if source supports a one-to-one matching
    # of all three selector literals across two different original groups.
    edges={}
    for u,v in itertools.combinations(range(len(groups)),2):
        matching=[]
        for a in groups[u]:
            for b in groups[v]:
                cid=index.get(frozenset((-a,-b)))
                if cid is not None:
                    matching.append((a,b,cid))
        if (len(matching)==3 and
                {a for a,b,cid in matching}==set(groups[u]) and
                {b for a,b,cid in matching}==set(groups[v])):
            edges[(u,v)]=matching
    def neighbors(u):
        return {v if u==a else a for a,v in edges if a==u or v==u}
    # Hub joined to all other groups; rim induced graph is one odd cycle.
    for hub in range(len(groups)):
        if len(neighbors(hub))!=len(groups)-1:continue
        rim=set(range(len(groups)))-{hub}
        if len(rim)<5 or len(rim)%2==0:continue
        if any(len(neighbors(v)&rim)!=2 for v in rim):continue
        first=min(rim)
        previous=-1
        current=first
        ordered=[]
        while current not in ordered and len(ordered)<=len(rim):
            ordered.append(current)
            options=sorted((neighbors(current)&rim)-{previous})
            if len(options)!=1 and previous!=-1:
                raise ValueError("rim has ambiguous traversal")
            if not options:break
            following=options[0]
            previous,current=current,following
        if current!=first or set(ordered)!=rim:
            continue
        # Global colors are grounded by the source's 3 hub selectors,
        # with each spoke's source mutexes inducing a bijection.
        colors={hub:tuple(sorted(groups[hub]))}
        valid=True
        for v in rim:
            edge=edges[tuple(sorted((hub,v)))]
            byhub={}
            for a,b,cid in edge:
                hv,rv=(a,b) if hub<v else (b,a)
                byhub[hv]=rv
            if set(byhub)!=set(colors[hub]):
                valid=False;break
            colors[v]=tuple(byhub[x] for x in colors[hub])
        if not valid:continue
        # Every consecutive rim edge MUST contain the grounded
        # equal-color mutex clauses, no guessed color identification.
        if any(frozenset((-colors[a][c],-colors[b][c])) not in index
               for a,b in zip(ordered,ordered[1:]+ordered[:1])
               for c in range(3)):
            continue
        return {
            "raw":raw,"nv":nvars,"clauses":clauses,"index":index,
            "hub":hub,"rim":ordered,"colors":colors,"groups":groups,
        }
    raise ValueError("source has no complete odd-wheel graph substructure")

def generate(original,output,meta,expected_sha):
    raw=original.read_bytes()
    digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected_sha:
        raise ValueError("original source sha mismatch")
    S=source_wheel(original)
    C=S["colors"];rim=S["rim"];hub=S["hub"];ids=S["index"]
    n=len(rim);clauses=S["clauses"]
    steps=[]
    counter=len(clauses)
    def poly(ids_1,divisor=1):
        nonlocal counter
        if not ids_1:raise ValueError("empty proof combination")
        tokens=[str(ids_1[0])]
        for x in ids_1[1:]:tokens.extend([str(x),"+"])
        if divisor>1:tokens.extend([str(divisor),"d"])
        steps.append("pol "+" ".join(tokens)+" ;")
        counter+=1
        return counter
    # Exactly one color per rim vertex, all clauses are INPUT source IDs.
    rim_alo=[ids[frozenset(C[v])] for v in rim]
    rim_total=poly(rim_alo)
    odd_cycle_caps=[]
    rim_succ=rim[1:]+rim[:1]
    for color in range(3):
        edges=[ids[frozenset((-C[a][color],-C[b][color]))]
               for a,b in zip(rim,rim_succ)]
        odd_cycle_caps.append(poly(edges,2))
    final_hub_exclusions=[]
    for color in range(3):
        others=[odd_cycle_caps[c] for c in range(3) if c!=color]
        # Add lower bound on total rim-color assignments with two
        # OTHER color caps -> >=1 selected rim vertex of this color.
        at_least_one=poly([rim_total]+others)
        spokes=[ids[frozenset((-C[hub][color],-C[v][color]))]
                 for v in rim]
        forbid_hub=poly(spokes)
        final_hub_exclusions.append(poly([forbid_hub,at_least_one],n))
    hub_alo=ids[frozenset(C[hub])]
    poly([hub_alo]+final_hub_exclusions)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(
        "pseudo-Boolean proof version 3.0\n"+
        f"f {len(clauses)} ;\n"+
        "\n".join(steps)+"\n"+
        "output NONE ;\nconclusion UNSAT ;\nend pseudo-Boolean proof ;\n"
    )
    report={
        "status":"IPG5D_PURE_PB_EMITTED_NEEDS_EXTERNAL_VERIPB",
        "source_sha256":digest,
        "source_vars":S["nv"],"source_clauses":len(clauses),
        "source_onehot_groups":len(S["groups"]),
        "odd_wheel_rim_length":n,
        "odd_wheel_hub_source_group_index":hub,
        "rim_source_group_indices":rim,
        "cutting_planes_only":True,
        "rup_steps":0,
        "cdcl_or_dpll_calls":0,
        "pure_pol_steps":len(steps),
        "source_original_clause_ids_only":True,
        "proof_bytes":output.stat().st_size,
        "expected_external_checker":"VeriPB3.0.2",
        "scope":"Recognized complete odd-wheel graph 3-coloring SOURCE substructure; no arbitrary PCMAX parity proof claimed.",
    }
    meta.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--proof",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    p.add_argument("--expected-sha256",required=True)
    a=p.parse_args()
    try:
        r=generate(a.cnf,a.proof,a.meta,a.expected_sha256)
        print("IPG5D_PURE_PB "+json.dumps(r,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,UnicodeError) as e:
        a.proof.unlink(missing_ok=True)
        a.meta.parent.mkdir(parents=True,exist_ok=True)
        a.meta.write_text(json.dumps({"status":"UNKNOWN","reason":str(e)})+"\n")
        print("IPG5D_UNKNOWN "+str(e),flush=True)
        return 1
if __name__=="__main__":sys.exit(main())
