#!/usr/bin/env python3
"""DRNAS Medical R4 — identical E. coli gene-KO problem, Gurobi MIP vs SAT.

Both methods enumerate inclusion-minimal biomass-disrupting gene KOs (size <= 3)
using exactly the same real COBRApy/GLPK FBA oracle, monotone superset cuts and
disabled-reaction-signature memoization. MILP enumerates through Gurobi MIPSOL
lazy constraints; SAT uses the R3 CaDiCaL master. Independently exhaustively
verified. This is NOT a native DRNAS solver or a full gMISpy BoNesis benchmark.
"""
from __future__ import annotations
import argparse
import csv
import json
import statistics
import time
from pathlib import Path

from gmispy_r3 import prepare, disabled_reactions, fba_growth, structural_oracle, sat_arm

METHODS = ("drnas_sat_structural_memo", "gurobi_mip_lazy_memo")

def mip_arm(cobra_model, genes, rules, max_k, threshold, truth, minima,
            time_cap=90.0, mip_seed=42):
    import gurobipy as gp
    from gurobipy import GRB

    started = time.perf_counter()
    n = len(genes)
    selected = set()
    cache = {}
    visited = set()
    per_k = []
    counters = dict(candidates=0, lp_calls=0, memo_hits=0, mip_solutions=0)
    callback_errors = []

    for k in range(1, max_k + 1):
        m = gp.Model("gMISpy-R4-Gurobi-MIP-gene-k%d" % k)
        m.Params.OutputFlag = 0
        m.Params.Threads = 1
        m.Params.Seed = mip_seed
        m.Params.LazyConstraints = 1
        m.Params.Presolve = 2
        m.Params.MIPGap = 0
        m.Params.TimeLimit = max(1.0, time_cap - (time.perf_counter()-started))
        x = m.addVars(n, vtype=GRB.BINARY, name="geneKO")
        m.addConstr(gp.quicksum(x[i] for i in range(n)) == k)
        for previous in sorted(selected):
            m.addConstr(gp.quicksum(x[i] for i in previous) <= len(previous)-1)
        m.setObjective(gp.LinExpr(), GRB.MINIMIZE)
        m.update()

        def callback(cb_model, where):
            if where != GRB.Callback.MIPSOL or callback_errors:
                return
            try:
                assignments = cb_model.cbGetSolution(x)
                combo = tuple(i for i in range(n) if assignments[i] > 0.5)
                if len(combo) != k or combo not in truth:
                    raise AssertionError("Invalid Gurobi MIPSOL candidate")
                counters["mip_solutions"] += 1
                if combo in visited:
                    # Gurobi may revisit a lazy-cut assignment; the same exclusion remains sound.
                    reject = gp.quicksum((1-x[i]) if i in combo else x[i] for i in range(n))
                    cb_model.cbLazy(reject >= 1)
                    return
                visited.add(combo)
                counters["candidates"] += 1
                signature = disabled_reactions(rules, (genes[i] for i in combo))
                if signature in cache:
                    growth = cache[signature]
                    counters["memo_hits"] += 1
                else:
                    growth = fba_growth(cobra_model, genes, combo, "gene")
                    counters["lp_calls"] += 1
                    cache[signature] = growth
                lethal = growth < threshold
                if lethal != truth[combo]:
                    raise AssertionError("Gurobi candidate FBA differs from independent oracle")
                if lethal:
                    if any(set(p).issubset(combo) for p in selected):
                        raise AssertionError("Gurobi failed earlier subset exclusion")
                    selected.add(combo)
                    cb_model.cbLazy(gp.quicksum(x[i] for i in combo) <= len(combo)-1)
                else:
                    cb_model.cbLazy(
                        gp.quicksum((1-x[i]) if i in combo else x[i] for i in range(n)) >= 1
                    )
            except BaseException as exc:
                callback_errors.append("%s: %s" % (type(exc).__name__, exc))
                cb_model.terminate()

        m.optimize(callback)
        status = int(m.Status)
        per_k.append(dict(k=k, status=status, runtime_s=float(m.Runtime),
                          node_count=float(m.NodeCount)))
        if callback_errors:
            raise RuntimeError("Gurobi callback failure: " + repr(callback_errors))
        if status != GRB.INFEASIBLE:
            # Expected INFEASIBLE after every candidate has been rejected by
            # genuine lazy constraints (enumeration has no remaining candidates).
            return dict(method="gurobi_mip_lazy_memo", complete=False,
                        status_code=status, wall_s=round(time.perf_counter()-started,7),
                        **counters, per_k=per_k)
    if selected != minima:
        raise AssertionError("Gurobi MIP did not recover same minimal KO sets")
    return dict(method="gurobi_mip_lazy_memo", complete=True,
                status_code=int(GRB.INFEASIBLE),
                wall_s=round(time.perf_counter()-started,7),
                **counters, per_k=per_k, minimal_sets=len(selected), crosscheck="PASS")


def check_gpr_signatures(genes, rules, truth, max_tests=5488):
    """Independent monotonic GPR rule check for all in-scope KO subsets."""
    if len(truth) > max_tests:
        raise AssertionError("Unexpected test set size")
    signatures = {}
    for combo in truth:
        signatures[combo] = frozenset(disabled_reactions(
            rules, (genes[i] for i in combo)
        ))
    for combo, signature in signatures.items():
        if len(combo) < 2:
            continue
        for index in combo:
            smaller = tuple(x for x in combo if x != index)
            if smaller and not signatures[smaller].issubset(signature):
                raise AssertionError("Nonmonotone real GPR: " + repr(combo))
    return len(signatures)


def benchmark(out, repeats, time_cap, max_k):
    if repeats not in (1, 2, 3, 4, 5):
        raise ValueError("repeats must be in 1..5")
    if max_k not in (2, 3):
        raise ValueError("max-k must be 2 or 3")
    import gurobipy as gp
    out.mkdir(parents=True, exist_ok=True)
    cobra_model, genes, rules, wild, sha, and_rules, or_rules, examples = prepare(out)
    if len(genes) != 32:
        raise AssertionError("R4 must use same 32 frozen genes as R3")
    threshold = wild * .01
    truth, minimal, oracle_rows, oracle_wall_s = structural_oracle(
        cobra_model, genes, rules, max_k, threshold
    )
    checked = check_gpr_signatures(genes, rules, truth)
    trial_rows = []
    for rep in range(repeats):
        order = METHODS if rep%2 == 0 else tuple(reversed(METHODS))
        for method in order:
            if method == "drnas_sat_structural_memo":
                row = sat_arm(cobra_model, genes, rules, max_k, threshold,
                              truth, minimal, "structural_memo")
                row["method"] = method
                row["complete"] = True
            else:
                row = mip_arm(cobra_model, genes, rules, max_k, threshold,
                              truth, minimal, time_cap=time_cap, mip_seed=42+rep)
            row["repeat"] = rep
            trial_rows.append(row)
            print("DRNAS_GMISPY_R4_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    summaries = {}
    for method in METHODS:
        collected = [r for r in trial_rows if r["method"] == method]
        complete = [r for r in collected if r.get("complete")]
        summaries[method] = {
            "runs": len(collected), "complete": len(complete),
            "median_wall_s": statistics.median(r["wall_s"] for r in complete)
                             if len(complete)==len(collected) else None,
            "median_lp_calls": statistics.median(r["lp_calls"] for r in complete)
                               if len(complete)==len(collected) else None
        }
    with (out/"oracle_ko_queries.csv").open("w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(oracle_rows[0]))
        wr.writeheader(); wr.writerows(oracle_rows)
    report = dict(
        protocol="DRNAS-MEDICAL-R4-GUROBI-LAZY-MIP-VS-SAT-IDENTICAL-FBA",
        model="BiGG e_coli_core COBRApy textbook",
        model_sha256=sha,
        genes=genes, max_knockouts=max_k,
        independent_oracle=dict(combinations=len(truth), minimal=len(minimal),
                                gene_reaction_match=True, wall_s=oracle_wall_s,
                                gpr_monotone_checks=checked,
                                minimal_ko_sets=[[genes[i] for i in s]
                                                 for s in sorted(minimal)]),
        upstream_gmispy_full_regulatory_run=False,
        using_native_drnas_solver=False,
        experiment_compares_gene_interventions_using_identical_cobrapy_fba=True,
        mip_solver="Gurobi "+str(gp.gurobi.version())+"; callback MIPSOL lazy cuts",
        sat_solver="PySAT CaDiCaL 1.9.5",
        timing_limit_s_per_mip_rep=time_cap,
        repeats=repeats, trials=trial_rows, summaries=summaries,
        timing_note=("Only both-complete runs warrant numerical speed comparison. "
                     "Identical 32 gene candidates, same GLPK growth oracle, "
                     "same monotone cuts and disabled-reaction memoization. "
                     "Gurobi optimizer and SAT enumerator may explore different "
                     "candidate orders; FBA calls need not be identical. "
                     "R3 exhaustive reference validates gene-level equivalence. "
                     "No disease or therapy claims.")
    )
    (out/"summary.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DRNAS_GMISPY_R4_SUMMARY",json.dumps({
        "model_sha256":sha, "independently_checked":len(truth),
        "minimal_sets":len(minimal),"gpr_checked":checked,
        "methods":summaries,
        "all_complete":all(r.get("complete") for r in trial_rows)
    },sort_keys=True),flush=True)
    if not all(r.get("complete") for r in trial_rows):
        # Strict fail close: still persist results on Actions using always artifact step.
        raise RuntimeError("One or more Gurobi MIP enumerations timed out; no winner claimed")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",default="medical-results/gmispy-r4")
    parser.add_argument("--max-k",type=int,default=3)
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--mip-cap",type=float,default=120.0)
    args=parser.parse_args()
    benchmark(Path(args.out),args.repeats,args.mip_cap,args.max_k)
