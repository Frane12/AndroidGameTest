#!/usr/bin/env python3
"""IPG6B automatic bounded source-CG closure of machine mutex triangles.

Start from binary source capacity nogoods forming a 3-job triangle
on each of 3 machines. Derive rank1 triangle capacity bounds, then
derive new pair exclusions from 3 original one-hot ALOs + 3 original
ternary covering constraints + two other-machine triangle bounds,
integer divide by 3. Repeat on newly formed, source-provable triangles.

NO DPLL, CDCL, learned SAT clauses or LP solver is used in DERIVING
the rank1/rank2/rank3/rank4 source-PB cuts. Each PB combination is
independently checked for exact integer arithmetical correctness.

The FINAL complete UNSAT transcript has the old 100 POL steps
APPENDED and adjusted for new source-CG line IDs; those previous
POL steps were discovered by STRUCTURAL DPLL. Do not conflate the
new source-CG proof of graph mutexes with a full search-free refutation.

No complete general polynomial PCMAX method is claimed. Source SHA
and original clause semantics must be verified independently.
"""
import argparse,hashlib,itertools,json,pathlib
from ipg4_rup_drat_to_veripb import dimacs
from ipg6_rank2_source_cg import row,divide,shift_old,SHA

def derive(source):
    raw,nv,clauses=dimacs(source)
    if hashlib.sha256(raw).hexdigest()!=SHA or nv!=45 or len(clauses)!=300:
        raise ValueError("not source-frozen weighted Petersen")
    val=lambda j,m:3*j+m+1
    index={}
    for i,c in enumerate(clauses,1):index.setdefault(frozenset(c),i)
    original=[row(c) for c in clauses]
    known={i+1:p for i,p in enumerate(original)}
    proof_lines=[]
    source_id=300
    pair={}
    capacities={}
    for a,b in itertools.combinations(range(15),2):
        ids=[index.get(frozenset((-val(a,m),-val(b,m)))) for m in range(3)]
        if all(ids):
            for m,cid in enumerate(ids):pair[(a,b,m)]=cid
    discovered_pairs=[]
    caps_log=[]
    rounds=[]
    triangles_used=set()
    def add(antecedents,divisor,expected,name):
        nonlocal source_id
        tested=divide([known[cid] for cid in antecedents],divisor)
        if tested!=expected:
            raise ValueError(f"original-source integer CP mismatch: {name}")
        tokens=[str(antecedents[0])]
        for cid in antecedents[1:]:tokens.extend([str(cid),"+"])
        tokens.extend([str(divisor),"d"])
        proof_lines.append("pol "+" ".join(tokens)+" ;")
        source_id+=1
        known[source_id]=tested
        return source_id
    # Iterate to mathematical closure or resource limit.
    for iteration in range(8):
        novel_tris=[]
        for T in itertools.combinations(range(15),3):
            if T in triangles_used:continue
            if all((a,b,m) in pair for a,b in itertools.combinations(T,2)
                   for m in range(3)):
                novel_tris.append(T)
        for T in novel_tris:
            triangle_ids=[]
            for m in range(3):
                ids=[pair[(a,b,m)] for a,b in itertools.combinations(T,2)]
                expected=[0]*45
                for j in T:expected[val(j,m)-1]=-1
                pid=add(ids,2,(tuple(expected),-1),f"triangle {T} m{m}")
                triangle_ids.append(pid)
            capacities[T]=triangle_ids
            triangles_used.add(T)
            caps_log.append({"jobs":list(T),"veripb_ids":triangle_ids})
        novel_pair_sets=[]
        for a,b in itertools.combinations(range(15),2):
            if any((a,b,m) in pair for m in range(3)):continue
            for T in sorted(capacities):
                if a in T or b in T:continue
                if all(index.get(frozenset((-val(a,m),-val(b,m),-val(j,m))))
                       for m in range(3) for j in T):
                    novel_pair_sets.append((a,b,T))
                    break
        for a,b,T in novel_pair_sets:
            for m in range(3):
                u,v=val(a,m),val(b,m)
                alo=[index.get(frozenset((val(j,0),val(j,1),val(j,2)))) for j in T]
                ternary=[index.get(frozenset((-u,-v,-val(j,m)))) for j in T]
                if any(cid is None for cid in alo+ternary):
                    raise ValueError("missing original packing or assignment clause")
                parents=alo+ternary+[capacities[T][k] for k in range(3) if k!=m]
                expected=[0]*45;expected[u-1]=expected[v-1]=-1
                cid=add(parents,3,(tuple(expected),-1),
                        f"new graph mutex jobs({a},{b}) machine {m}")
                pair[(a,b,m)]=cid
                discovered_pairs.append({
                    "jobs_0based":[a,b],"machine":m,
                    "source_premises":alo+ternary,
                    "other_machine_triangles":parents[6:],
                    "derived_mutex":[-u,-v],
                    "derived_PB_id":cid,
                    "level":iteration+1,
                })
        rounds.append({"round":iteration+1,"new_triangles":len(novel_tris),
                       "new_symmetric_pairs":len(novel_pair_sets),
                       "cumulative_new_mutexes":len(discovered_pairs)})
        if not novel_tris and not novel_pair_sets:break
    if (len(proof_lines)!=21 or len(discovered_pairs)!=15 or
        len(capacities)!=2):
        raise ValueError("source CG closure differs from expected original 21/15/2")
    return proof_lines,discovered_pairs,caps_log,rounds

def generate(source,old_pol,dest,meta):
    lines,new_pairs,triangle_caps,iterations=derive(source)
    old=old_pol.read_text().splitlines()
    if old[:2]!=["pseudo-Boolean proof version 3.0","f 300 ;"] or old[-3:]!=[
       "output NONE ;","conclusion UNSAT ;",
       "end pseudo-Boolean proof ;"]:
        raise ValueError("bad original POL suffix")
    previous=old[2:-3]
    if len(previous)!=100:
        raise ValueError("historic source DPLL-POL suffix not 100 lines")
    new=shift_old(previous,300,len(lines))
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text("\n".join(old[:2]+lines+new+old[-3:])+"\n")
    report={
        "status":"SOURCE_ITERATIVE_CG_CLOSURE_NEEDS_EXTERNAL_VERIPB",
        "source_sha256":SHA,"original_clauses":300,
        "initial_source_binary_mutex_job_pairs":3,
        "automatically_discovered_triangle_capacity_groups":triangle_caps,
        "automatically_derived_non_source_graph_mutexes":new_pairs,
        "new_source_mutexes":len(new_pairs),
        "new_source_only_pol_lines":len(lines),
        "source_CG_closure_rounds":iterations,
        "rank1_source_only_triangle_steps":3,
        "rank2_new_mutex_steps":9,
        "rank3_derived_triangle_steps":3,
        "rank4_new_mutex_steps":6,
        "full_POL_lines":len(lines)+len(new),
        "full_RUP_lines":0,
        "DPLL_discovered_historical_suffix_lines":100,
        "pure_cut_only_proves_full_UNSAT":False,
        "source_algebra_verified_without_DPLL":True,
        "proof_bytes":dest.stat().st_size,
    }
    meta.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cnf",required=True,type=pathlib.Path)
    p.add_argument("--old-pol",required=True,type=pathlib.Path)
    p.add_argument("--proof",required=True,type=pathlib.Path)
    p.add_argument("--meta",required=True,type=pathlib.Path)
    a=p.parse_args()
    try:
        report=generate(a.cnf,a.old_pol,a.proof,a.meta)
        print("IPG6B_ITERATIVE_CG "+json.dumps({
            k:v for k,v in report.items() if k not in (
               "automatically_derived_non_source_graph_mutexes",
               "automatically_discovered_triangle_capacity_groups")
        },sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError) as err:
        a.proof.unlink(missing_ok=True)
        print("IPG6B_REJECT "+str(err),flush=True)
        return 1

if __name__=="__main__":raise SystemExit(main())
