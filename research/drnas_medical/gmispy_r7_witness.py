#!/usr/bin/env python3
"""R7: GPR-exact SAT + feasible metabolic flux witnesses vs true gMCSpy.

Every *surviving* LP solution yields a primal flux vector. Any successful
gene KO must disable at least one reaction with nonzero flux in that vector.
Thus a single SAT witness clause excludes many biologically viable KO choices.
Not a dual-MILP implementation, native DRNAS engine, or cancer experiment.
"""
from __future__ import annotations
import argparse
import ast
import json
import math
from pathlib import Path
import statistics
import time

from gmispy_r3 import sat_arm, structural_oracle
from gmispy_r4 import check_gpr_signatures
from gmispy_r6_specialist import freeze_model, upstream_once, ORIGINAL_GMCSPY_COMMIT

EXPECTED_SHA = "13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f"

class GPRCNF:
    """Reify original gene activity formulas, keeping non-target genes active."""
    def __init__(self, genes, rules):
        self.indices={g:i+1 for i,g in enumerate(genes)}
        self.top=len(genes)
        self.clauses=[]
        self.disabled={}
        for rid,(_rule,tree,_fn) in sorted(rules.items()):
            active=self.expr(tree)
            if active is False:
                raise AssertionError("Wild-type GPR inactive: "+rid)
            if active is not True:
                self.disabled[rid]=-active

    def expr(self,node):
        if isinstance(node,ast.Expression):
            return self.expr(node.body)
        if isinstance(node,ast.Name):
            return -self.indices[node.id] if node.id in self.indices else True
        if not isinstance(node,ast.BoolOp) or not isinstance(node.op,(ast.And,ast.Or)):
            raise ValueError("Unsupported GPR expression: "+ast.dump(node))
        conjunction=isinstance(node.op,ast.And)
        vals=[self.expr(n) for n in node.values]
        if conjunction and any(v is False for v in vals):
            return False
        if not conjunction and any(v is True for v in vals):
            return True
        vals=list(dict.fromkeys(v for v in vals
             if v is not (True if conjunction else False)))
        if not vals:
            return True if conjunction else False
        if len(vals)==1:
            return vals[0]
        self.top+=1
        v=self.top
        if conjunction:
            self.clauses.extend([[-v,x] for x in vals])
            self.clauses.append([v]+[-x for x in vals])
        else:
            self.clauses.extend([[-x,v] for x in vals])
            self.clauses.append([-v]+vals)
        return v

    def witness_clause(self,flux):
        # Never drop tiny nonzero fluxes: magnitude pruning could be unsound.
        return tuple(sorted({d for rid,d in self.disabled.items()
                             if float(flux.get(rid,0.0))!=0.0},
                            key=lambda x:(abs(x),x)))

def lp_flux(model,genes,ko):
    with model:
        for idx in ko:
            model.genes.get_by_id(genes[idx]).knock_out()
        sol=model.optimize()
        if sol.status=="infeasible":
            return 0.0,{}
        if sol.status!="optimal" or not math.isfinite(float(sol.objective_value)):
            raise RuntimeError("Unexpected FBA status "+str(sol.status))
        return float(sol.objective_value),sol.fluxes

def witness_sat(model,genes,rules,threshold):
    from pysat.card import CardEnc,EncType
    from pysat.solvers import Solver
    t0=time.perf_counter()
    logic=GPRCNF(genes,rules)
    minima=set()
    learned=[]
    seen=set()
    stats=dict(sat_calls=0,lp_calls=0,viable_lp=0,lethal_lp=0,
               flux_cuts=0,empty_flux_cuts=0)
    def add_witness(flux,sat=None):
        clause=logic.witness_clause(flux)
        if clause in seen:
            raise AssertionError("Learned flux witness was already present")
        seen.add(clause)
        learned.append(list(clause))
        stats["flux_cuts"]+=1
        if not clause:
            stats["empty_flux_cuts"]+=1
        if sat is not None:
            sat.add_clause(list(clause))
    growth,flux=lp_flux(model,genes,())
    stats["lp_calls"]+=1
    stats["viable_lp"]+=1
    if growth<threshold:
        raise AssertionError("Wild-type below viability threshold")
    add_witness(flux)
    per_k=[]
    for k in (1,2,3):
        card=CardEnc.equals(lits=list(range(1,len(genes)+1)),bound=k,
                            encoding=EncType.seqcounter,top_id=logic.top)
        with Solver(name="cadical195",
                    bootstrap_with=logic.clauses+card.clauses+learned) as sat:
            for old in minima:
                sat.add_clause([-(i+1) for i in old])
            count=0
            while True:
                stats["sat_calls"]+=1
                if not sat.solve():
                    break
                assignment=set(sat.get_model())
                ko=tuple(i for i in range(len(genes)) if i+1 in assignment)
                if len(ko)!=k:
                    raise AssertionError("Cardinality error")
                count+=1
                growth,flux=lp_flux(model,genes,ko)
                stats["lp_calls"]+=1
                if growth<threshold:
                    stats["lethal_lp"]+=1
                    if any(set(old).issubset(ko) for old in minima):
                        raise AssertionError("Nonminimal cut")
                    minima.add(ko)
                    sat.add_clause([-(i+1) for i in ko])
                else:
                    stats["viable_lp"]+=1
                    add_witness(flux,sat)
        per_k.append(dict(k=k,candidates_with_LP=count,
                          minimal_found=sum(len(x)==k for x in minima),
                          flux_cuts_total=stats["flux_cuts"]))
    solutions=sorted((sorted(genes[i] for i in ko) for ko in minima),
                     key=lambda x:(len(x),x))
    return dict(method="r7_flux_witness_sat",wall_s=round(time.perf_counter()-t0,7),
                complete=True,solutions=solutions,minimal_sets=len(minima),
                reified_reactions=len(logic.disabled),
                GPR_clauses=len(logic.clauses),
                per_k=per_k,**stats)

def run(out,cohort,repeats=3,cap=120):
    if cohort not in (48,64) or repeats!=3:
        raise ValueError("Frozen protocol: 48 or 64 genes, 3 repetitions")
    out.mkdir(parents=True,exist_ok=True)
    model,genes,rules,wild,sha=freeze_model(out,cohort)
    if sha!=EXPECTED_SHA:
        raise AssertionError("Biological input has changed")
    threshold=wild*0.01
    truth,minima,_rows,oracle_seconds=structural_oracle(model,genes,rules,3,threshold)
    mono=check_gpr_signatures(genes,rules,truth,max_tests=50000)
    if mono!=len(truth):
        raise AssertionError("Incomplete independent GPR check")
    expected={frozenset(genes[i] for i in ko) for ko in minima}
    reference=dict(candidates=len(truth),gene_and_reaction_FBA=2*len(truth),
                   monotonicity_checks=mono,wall_s=oracle_seconds,
                   minimal_solutions=[sorted(s) for s in
                     sorted(expected,key=lambda s:(len(s),sorted(s)))])
    report=dict(protocol="DRNAS-MEDICAL-R7-PRIMAL-FLUX-CEGAR",
                source_sha256=sha,genes=genes,cohort=cohort,
                max_k=3,biomass_threshold=threshold,
                original_gMCSpy_commit=ORIGINAL_GMCSPY_COMMIT,
                native_drnas=False,human_cancer_data=False,
                independent_reference=reference,trials=[],
                median_wall_s={},certified=False)
    arms=("r7","r6","gmcspy")
    for rep in range(repeats):
        for arm in arms[rep:]+arms[:rep]:
            if arm=="r7":
                row=witness_sat(model,genes,rules,threshold)
                row["all_solutions_verified"]=(
                    {frozenset(s) for s in row["solutions"]}==expected)
            elif arm=="r6":
                row=sat_arm(model,genes,rules,3,threshold,truth,minima,
                            "structural_memo")
                row["method"]="r6_sat_candidate_glpk"
                row["all_solutions_verified"]=(
                    row["crosscheck"]=="PASS" and row["minimal_sets"]==len(expected))
            else:
                row=upstream_once(dict(genes=genes,max_k=3,cap_s=cap,
                                       repeat=rep),out,cap)
                row["method"]="published_gMCSpy_staged_lazy"
                solutions=[frozenset(x) for x in row.get("solutions",[])]
                row["all_solutions_verified"]=(
                    row.get("status")=="returned" and
                    len(solutions)==len(set(solutions)) and
                    set(solutions)==expected and
                    not any("time limit" in x.lower() or "lower bound" in x.lower()
                            for x in row.get("warnings",[])))
            row["repeat"]=rep
            if not row["all_solutions_verified"]:
                report["trials"].append(row)
                (out/"summary.json").write_text(json.dumps(report,indent=2))
                raise AssertionError("Incomplete/mismatched "+row["method"]+
                                     " repeat="+str(rep))
            report["trials"].append(row)
            (out/"summary.json").write_text(json.dumps(report,indent=2))
            print("DRNAS_MEDICAL_R7_TRIAL",json.dumps(dict(
                cohort=cohort,repeat=rep,method=row["method"],
                wall_s=row["wall_s"],verified=True,lp_calls=row.get("lp_calls"),
                flux_cuts=row.get("flux_cuts")),sort_keys=True),flush=True)
    for name in ("r7_flux_witness_sat","r6_sat_candidate_glpk",
                 "published_gMCSpy_staged_lazy"):
        report["median_wall_s"][name]=statistics.median(
            row["wall_s"] for row in report["trials"] if row["method"]==name)
    report["certified"]=True
    report["speedup_vs_r6"]=(
        report["median_wall_s"]["r6_sat_candidate_glpk"]/
        report["median_wall_s"]["r7_flux_witness_sat"])
    report["speedup_vs_original_gMCSpy"]=(
        report["median_wall_s"]["published_gMCSpy_staged_lazy"]/
        report["median_wall_s"]["r7_flux_witness_sat"])
    (out/"summary.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DRNAS_MEDICAL_R7_SUMMARY",json.dumps(dict(
        cohort=cohort,minimal=len(expected),median_s=report["median_wall_s"],
        speedup_vs_r6=report["speedup_vs_r6"],
        speedup_vs_original=report["speedup_vs_original_gMCSpy"]),sort_keys=True),
        flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",type=int,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--repeats",type=int,default=3)
    p.add_argument("--cap",type=float,default=120)
    a=p.parse_args()
    run(a.out,a.cohort,a.repeats,a.cap)
