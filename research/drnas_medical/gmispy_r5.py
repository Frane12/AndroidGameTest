#!/usr/bin/env python3
"""DRNAS Medical R5: scale to 48 real gene KO targets; compare GPR-aware Gurobi
MIP master, R4 Gurobi lazy-MIP master and SAT structural/memo master.

All three enumerate inclusion-minimal KO sets with exactly the SAME real
COBRApy/GLPK biomass feasibility oracle. Independent exhaustive gene-KO versus
reaction-KO FBA audit on every candidate; no clinical or native DRNAS claims.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import itertools
import json
import math
import statistics
import time
from pathlib import Path

from gmispy_r3 import (
    prepare as prepare_r3, disabled_reactions, fba_growth,
    structural_oracle, sat_arm
)
from gmispy_r4 import mip_arm as r4_mip_arm, check_gpr_signatures
from gmispy_r3 import parse_rule


def prepare_48(out, extra_count):
    cobra_model, base_genes, rules, wild, sha, n_and, n_or, examples = prepare_r3(out)
    if not 1 <= extra_count <= 24:
        raise ValueError("R5 extra genes must be 1..24")
    remaining = [g for g in cobra_model.genes if g.id not in base_genes and g.reactions]
    def score(g):
        c = sum((" and " in r.gene_reaction_rule or " or " in r.gene_reaction_rule)
                for r in g.reactions)
        return (-c, -len(g.reactions), g.id)
    extra = [g.id for g in sorted(remaining,key=score)[:extra_count]]
    genes = base_genes + extra
    if len(genes) != len(set(genes)) or len(extra) != extra_count:
        raise AssertionError("Insufficient extra source GPR genes")
    return cobra_model, genes, rules, wild, sha, n_and, n_or, examples, extra


def gpr_mip_arm(cobra_model, genes, rules, truth, minimal, threshold,
                max_k=3, cap_s=120, seed=42):
    """Gurobi MILP master with exact AND/OR gene-reaction logic, objective guided
    toward higher disabled-reaction count. GLPK remains an independent oracle.

    The GPR MILP is NOT the full stoichiometric network optimization:
    it is a reaction-aware *master* combined with FBA in lazy callback.
    """
    import gurobipy as gp
    from gurobipy import GRB
    started = time.perf_counter()
    n = len(genes)
    gene_ids=set(genes)
    gene_index={g:i for i,g in enumerate(genes)}
    found=set()
    cache={}
    visited=set()
    counter=dict(candidates=0,lp_calls=0,memo_hits=0,mipsol_events=0)
    per_k=[]
    for k in range(1,max_k+1):
        elapsed=time.perf_counter()-started
        if elapsed>=cap_s:
            return dict(method="gurobi_gpr_aware_mip",complete=False,
                        wall_s=elapsed,**counter,per_k=per_k,
                        reason="global timeout")
        m=gp.Model("DRNAS-Medical-R5-GPR-aware-k%d"%k)
        m.Params.OutputFlag=0
        m.Params.Threads=1
        m.Params.Seed=seed
        m.Params.MIPGap=0
        m.Params.LazyConstraints=1
        m.Params.Presolve=2
        m.Params.TimeLimit=max(0.5,cap_s-elapsed)
        x=m.addVars(n,vtype=GRB.BINARY,name="KO")
        m.addConstr(gp.quicksum(x[i] for i in range(n))==k,name="exact_gene_KO_count")
        for old in sorted(found):
            m.addConstr(gp.quicksum(x[i] for i in old)<=len(old)-1)
        off=[]
        nodes=0
        def activity(node):
            nonlocal nodes
            if isinstance(node,ast.Name):
                return 1-x[gene_index[node.id]] if node.id in gene_index else 1
            if not isinstance(node,ast.BoolOp) or not isinstance(node.op,(ast.And,ast.Or)):
                raise AssertionError("Unexpected published GPR tree node")
            children=[activity(y) for y in node.values]
            z=m.addVar(vtype=GRB.BINARY,name="GPR_%d"%nodes)
            nodes+=1
            if isinstance(node.op,ast.And):
                for child in children:
                    m.addConstr(z<=child)
                m.addConstr(z>=gp.quicksum(children)-(len(children)-1))
            else:
                for child in children:
                    m.addConstr(z>=child)
                m.addConstr(z<=gp.quicksum(children))
            return z
        for rid,(rule,tree,fn) in sorted(rules.items()):
            used={node.id for node in ast.walk(tree) if isinstance(node,ast.Name)}
            if not used.intersection(gene_ids):
                continue
            rr=m.addVar(vtype=GRB.BINARY,name="reaction_disabled_%s"%rid)
            m.addConstr(rr+activity(tree)==1)
            off.append(rr)
        # This guided objective uses actual biological GPR reaction consequences.
        # The objective affects only search ORDER; every legal gene subset is
        # nevertheless rejected by sound lazy cuts until Gurobi proves none left.
        m.setObjective(gp.quicksum(off),GRB.MAXIMIZE)
        m.update()
        callback_errors=[]
        def callback(cb,where):
            if where!=GRB.Callback.MIPSOL or callback_errors:
                return
            try:
                values=cb.cbGetSolution(x)
                combo=tuple(i for i in range(n) if values[i]>.5)
                if len(combo)!=k or combo not in truth:
                    raise AssertionError("GPR-aware MIP candidate outside reference")
                counter["mipsol_events"]+=1
                if combo in visited:
                    rejected=gp.quicksum((1-x[i]) if i in combo else x[i] for i in range(n))
                    cb.cbLazy(rejected>=1)
                    return
                visited.add(combo)
                counter["candidates"]+=1
                signature=disabled_reactions(rules,(genes[i] for i in combo))
                if signature in cache:
                    value=cache[signature]
                    counter["memo_hits"]+=1
                else:
                    value=fba_growth(cobra_model,genes,combo,"gene")
                    counter["lp_calls"]+=1
                    cache[signature]=value
                lethal=value<threshold
                if lethal != truth[combo]:
                    raise AssertionError("GPR MIP/FBA disagrees with exhaustive truth")
                if lethal:
                    if any(set(v).issubset(combo) for v in found):
                        raise AssertionError("MIP failed earlier minimal superset block")
                    found.add(combo)
                    cb.cbLazy(gp.quicksum(x[i] for i in combo)<=len(combo)-1)
                else:
                    cb.cbLazy(gp.quicksum((1-x[i]) if i in combo else x[i]
                                        for i in range(n))>=1)
            except BaseException as exc:
                callback_errors.append(str(exc))
                cb.terminate()
        m.optimize(callback)
        per_k.append(dict(k=k,status=int(m.Status),runtime_s=float(m.Runtime),
                          nodes=float(m.NodeCount),GPR_variables=nodes,
                          reaction_activity_variables=len(off)))
        if callback_errors:
            raise RuntimeError("GPR-aware MILP callback failed: "+repr(callback_errors))
        if m.Status!=GRB.INFEASIBLE:
            return dict(method="gurobi_gpr_aware_mip",complete=False,
                        wall_s=round(time.perf_counter()-started,7),
                        **counter,per_k=per_k,reason="Gurobi did not exhaust alternatives")
    if found!=minimal:
        raise AssertionError("GPR-aware MILP missing minimum growth disruption gene sets")
    return dict(method="gurobi_gpr_aware_mip",complete=True,
                wall_s=round(time.perf_counter()-started,7),
                **counter,per_k=per_k,minimal_sets=len(found),crosscheck="PASS")


def run(out, extra_count=16,max_k=3,repeats=2,mip_cap=120.):
    if max_k not in (2,3) or not 1<=repeats<=3:
        raise ValueError("R5 supports k=2..3, repeats 1..3")
    out.mkdir(parents=True,exist_ok=True)
    model,genes,rules,wild,sha,a_count,o_count,examples,extra=prepare_48(out,extra_count)
    threshold=wild*.01
    t0=time.perf_counter()
    truth,minimal,oracle_rows,oracle_seconds=structural_oracle(
        model,genes,rules,max_k,threshold)
    monotone_checks=check_gpr_signatures(genes,rules,truth,max_tests=40000)
    print("DRNAS_MEDICAL_R5_ORACLE",json.dumps(dict(
        sha256=sha,genes=len(genes),candidates=len(truth),minimum=len(minimal),
        wall_s=round(time.perf_counter()-t0,5),
        gene_reaction_equivalence="PASS",monotone=monotone_checks)),flush=True)
    with (out/"exhaustive_gene_reaction_growth.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(oracle_rows[0]))
        writer.writeheader();writer.writerows(oracle_rows)
    arms=("sat_structural_memo","gurobi_lazy_master","gurobi_gpr_aware_mip")
    trials=[]
    for rep in range(repeats):
        order=arms[rep%len(arms):]+arms[:rep%len(arms)]
        for method in order:
            if method=="sat_structural_memo":
                row=sat_arm(model,genes,rules,max_k,threshold,truth,minimal,"structural_memo")
                row["method"]=method
                row["complete"]=True
            elif method=="gurobi_lazy_master":
                row=r4_mip_arm(model,genes,rules,max_k,threshold,truth,minimal,
                               time_cap=mip_cap,mip_seed=42+rep)
                row["method"]=method
            else:
                row=gpr_mip_arm(model,genes,rules,truth,minimal,threshold,max_k,
                                cap_s=mip_cap,seed=42+rep)
            row["repeat"]=rep
            trials.append(row)
            print("DRNAS_MEDICAL_R5_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    summary={}
    for m in arms:
        rows=[t for t in trials if t["method"]==m]
        complete=len(rows)==repeats and all(t.get("complete") for t in rows)
        summary[m]=dict(
            complete=complete,
            wall_s_median=statistics.median(t["wall_s"] for t in rows)
                          if complete else None,
            lp_calls_median=statistics.median(t["lp_calls"] for t in rows)
                            if complete else None,
            candidates_median=statistics.median(t["candidates"] for t in rows)
                              if complete else None)
    result=dict(
        protocol="DRNAS-MEDICAL-R5-REAL-GPR-48GENES-PSEUDO_BILEVEL",
        source_model="BiGG e_coli_core / COBRApy 0.30.0 textbook",
        sha256=sha,original_reactions=len(model.reactions),
        original_metabolites=len(model.metabolites),
        original_genes=len(model.genes),
        genes=genes, added_genes=extra, selected_gene_count=len(genes),
        GPR_AND_reactions=a_count,GPR_OR_reactions=o_count,
        max_KO=max_k, wildtype_biomass=wild, biomass_threshold=threshold,
        exhaustive=dict(cases=len(truth),lp_calls=2*len(truth),
                        wall_s=oracle_seconds,monotone_checked=monotone_checks,
                        gene_reaction_equivalence=True,
                        minimal_sets=[[genes[i] for i in x] for x in sorted(minimal)]),
        repeats=repeats, trials=trials, methods=summary,
        independent_model_origin=True,
        caveats=[
            "real E coli metabolic model; not cancer or clinical testing",
            "SAT engine is PySAT CaDiCaL not native DRNAS",
            "Gurobi GPR-aware formulation is a gene/reaction-aware MIP master with FBA oracle, not an integrated strong-duality full metabolic MILP",
            "Not a full gMISpy BoNesis/cyclic regulation benchmark",
            "Both MIP and SAT enumerate same gene KO sets and use same GLPK oracle and reaction-signature memoization",
            "Subsecond to minute timing: verify repeatability and out-of-sample transfer"
        ])
    (out/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("DRNAS_MEDICAL_R5_SUMMARY",json.dumps({
        "source_sha256":sha,"genes":len(genes),"combinations":len(truth),
        "minimal_sets":len(minimal),"methods":summary},sort_keys=True),flush=True)
    if not all(row["complete"] for row in summary.values()):
        raise RuntimeError("At least one external MILP master did not fully complete; no speed superiority asserted")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="medical-results/r5")
    p.add_argument("--extra-genes",type=int,default=16)
    p.add_argument("--max-k",type=int,default=3)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--mip-cap",type=float,default=120)
    x=p.parse_args()
    run(Path(x.out),x.extra_genes,x.max_k,x.repeats,x.mip_cap)
