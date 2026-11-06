#!/usr/bin/env python3
"""DRNAS Medical R2: real E. coli metabolism, exact gene/reaction KO pairing.

Research only. Uses the published e_coli_core model via COBRApy "textbook".
This is not human cancer, and it does not include real regulatory feedback data.
Two solvers explore the SAME single-gene-reaction interventions; FBA independently
validates every growth-loss claim. gMISpy calculateMCS is run separately, if licensed.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import time


def model_and_pairs(out, limit=18):
    from cobra.io import load_model, write_sbml_model
    model = load_model("textbook")  # bundled COBRApy e_coli_core
    model.solver = "glpk"
    baseline = model.slim_optimize(error_value=float("nan"))
    if not math.isfinite(baseline) or baseline <= 0.01:
        raise RuntimeError("Invalid wild-type growth / missing experimental model")
    if len(model.reactions) != 95 or len(model.metabolites) != 72 or len(model.genes) != 137:
        raise RuntimeError("Unexpected e_coli_core model; fail closed")
    out.mkdir(parents=True, exist_ok=True)
    sbml = out / "e_coli_core_cobrapy_textbook.xml"
    write_sbml_model(model, str(sbml))
    source_sha = hashlib.sha256(sbml.read_bytes()).hexdigest()
    flux = model.optimize()
    pairs = []
    for gene in model.genes:
        if len(gene.reactions) != 1:
            continue
        reaction = next(iter(gene.reactions))
        if len(reaction.genes) != 1 or reaction.gene_reaction_rule.strip() != gene.id:
            continue
        pairs.append({"gene": gene.id, "reaction": reaction.id,
                      "wildtype_flux": float(flux.fluxes[reaction.id])})
    pairs.sort(key=lambda p: (abs(p["wildtype_flux"]) < 1e-8,
                              -abs(p["wildtype_flux"]), p["gene"]))
    pairs = pairs[:limit]
    if len(pairs) < 8:
        raise RuntimeError("Too few 1:1 gene-to-reaction pairs for exact intervention equivalence")
    if len({p["reaction"] for p in pairs}) != len(pairs):
        raise RuntimeError("1:1 matching failed")
    return model, baseline, source_sha, pairs


def growth(model, pairs, knocked_out, mode):
    with model:
        for ix in knocked_out:
            pair = pairs[ix]
            if mode == "genes":
                model.genes.get_by_id(pair["gene"]).knock_out()
            elif mode == "reactions":
                model.reactions.get_by_id(pair["reaction"]).knock_out()
            else:
                raise ValueError(mode)
        raw = model.slim_optimize(error_value=float("nan"))
    # Non-feasible model has no positive growth, but preserve diagnostic status.
    return float(raw) if math.isfinite(raw) else 0.0


def record_json(out, name, data):
    (out / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def benchmark(out, max_genes, ratio):
    from pysat.card import CardEnc, EncType
    from pysat.solvers import Solver
    model, wild, source_sha, pairs = model_and_pairs(out, max_genes)
    threshold = wild * ratio
    n = len(pairs)
    rows = []
    reference_lethal = set()
    started = time.perf_counter()
    for k in (1, 2):
        for combo in itertools.combinations(range(n), k):
            t0 = time.perf_counter()
            gene_growth = growth(model, pairs, combo, "genes")
            rxn_growth = growth(model, pairs, combo, "reactions")
            if abs(gene_growth - rxn_growth) > 1e-7:
                raise RuntimeError("Gene KO vs reaction KO non-equivalent: " + str(combo))
            lethal = gene_growth < threshold
            if lethal and (k == 1 or not any((idx,) in reference_lethal for idx in combo)):
                reference_lethal.add(combo)
            rows.append({"method": "exhaustive_FBA", "k": k,
                         "genes": "|".join(pairs[i]["gene"] for i in combo),
                         "growth": round(gene_growth, 10),
                         "lethal": lethal, "elapsed_s": round(time.perf_counter()-t0, 7),
                         "fba_calls": 2})
    reference_wall_s = time.perf_counter()-started

    found = set()
    trials = []
    total_fba_calls = 0
    master_sat_calls = 0
    sat_solver_s = 0.0
    started = time.perf_counter()
    for k in (1, 2):
        formula = CardEnc.equals(lits=list(range(1, n+1)), bound=k,
                                 encoding=EncType.seqcounter, top_id=n)
        with Solver(name="cadical195", bootstrap_with=formula.clauses) as solver:
            for earlier in found:
                solver.add_clause([-(i + 1) for i in earlier])
            while True:
                t_sat = time.perf_counter()
                status = solver.solve()
                sat_solver_s += time.perf_counter() - t_sat
                master_sat_calls += 1
                if not status:
                    break
                values = solver.get_model()
                positive = {v for v in values if 1 <= v <= n}
                combo = tuple(sorted(v-1 for v in positive))
                if len(combo) != k:
                    raise RuntimeError("SAT cardinality certificate invalid: " + str(combo))
                if any(set(prev).issubset(combo) for prev in found):
                    raise RuntimeError("Failed monotone exclusion")
                t0 = time.perf_counter()
                obj = growth(model, pairs, combo, "genes")
                total_fba_calls += 1
                lethal = obj < threshold
                if lethal:
                    found.add(combo)
                    solver.add_clause([-(i + 1) for i in combo])  # proven monotone dominance
                else:
                    solver.add_clause([-(i + 1) if i in combo else i + 1
                                       for i in range(n)])  # no repeat, exact assignment
                trials.append({"method": "DRNAS_SAT_LP_monotone",
                               "k": k, "genes": "|".join(pairs[i]["gene"] for i in combo),
                               "growth": round(obj, 10), "lethal": lethal,
                               "elapsed_s": round(time.perf_counter()-t0, 7),
                               "fba_calls": 1})
    drnas_wall_s = time.perf_counter()-started
    if found != reference_lethal:
        raise RuntimeError("Mismatch between exhaustive FBA and DRNAS SAT/LP minimal cuts")
    if len(rows) != n + n*(n-1)//2:
        raise RuntimeError("Incorrect reference instance count")
    reference_status = sorted([[pairs[i]["gene"] for i in c] for c in reference_lethal])
    with (out / "paired_queries.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows + trials)
    results = {
        "protocol": "DRNAS-MEDICAL-R2-REAL-E_COLI_CORE-MONOTONE-SAT-LP",
        "source": "COBRApy textbook / BiGG e_coli_core",
        "source_model_sha256": source_sha,
        "model_reactions": len(model.reactions),
        "model_genes": len(model.genes),
        "model_metabolites": len(model.metabolites),
        "biomass_objective": str(model.objective.expression),
        "wildtype_biomass_flux": float(wild),
        "lethal_threshold_fraction_of_wildtype": ratio,
        "lethal_threshold_absolute": threshold,
        "selected_one_to_one_gene_reaction_pairs": pairs,
        "reference": {"method": "exhaustive_FBA_gene_KO_vs_reaction_KO",
                      "cases": len(rows), "lp_calls": 2*len(rows),
                      "wall_s": reference_wall_s},
        "drnas": {"method": "PySAT_CaDiCaL_CardEnc_plus_FBA_monotone_learned_nogoods",
                  "candidate_cases": len(trials), "lp_calls": total_fba_calls,
                  "sat_calls": master_sat_calls,
                  "sat_solver_s": sat_solver_s,
                  "wall_s": drnas_wall_s},
        "minimal_growth_blocking_KO_sets": reference_status,
        "minimal_cut_sets_match": True,
        "medical_claims": False, "model_is_human": False,
        "regulatory_feedback_included": False,
        "full_gmispy_equivalence": False,
        "timing_note": "One process timing run per method; not a repeated blind benchmark. "
                       "Reference doubles LP calls to audit gene/reaction KO equivalence. "
                       "DRNAS arm is a SAT-master + GLPK LP oracle, not a native DRNAS solver speed test.",
    }
    record_json(out, "summary.json", results)
    print("DRNAS_GMISPY_R2_REAL_FBA", json.dumps({
        "genes": n, "reference_cases": len(rows), "drnas_cases": len(trials),
        "reference_lp_calls": 2*len(rows), "drnas_lp_calls": total_fba_calls,
        "reference_wall_s": round(reference_wall_s, 5),
        "drnas_wall_s": round(drnas_wall_s, 5),
        "minimal_sets": len(reference_lethal), "matching": True,
        "model_sha256": source_sha,
        "note": "real E. coli metabolism, no cancer data, no full gMISpy speed comparison",
    }), flush=True)


def upstream_mcs(out, max_genes, ratio):
    """True upstream gMISpy MILP MCS function on exactly the same 1:1 reaction subset."""
    from cyclic_gmispy.calculateMCS import calculateMCS
    model, wild, sha, pairs = model_and_pairs(out, max_genes)
    choices = [p["reaction"] for p in pairs]
    t0 = time.perf_counter()
    try:
        answer = calculateMCS(model, MAX_MCS=100, MAX_LENGTH_MCS=2,
                              rxnSubset=choices, timelimit=100, targetB=wild*ratio,
                              forceLength=True, solver="gurobi", numWorkers=1,
                              verbose=0)
        elapsed = time.perf_counter() - t0
        if not isinstance(answer, dict):
            raise RuntimeError("Unexpected gMISpy result type: " + str(type(answer)))
        results = []
        for value in answer.values():
            if not isinstance(value, dict) or "solution" not in value:
                raise RuntimeError("Unexpected gMISpy solution structure: " + str(value)[:300])
            sol = value["solution"]
            if not set(sol).issubset(choices):
                raise RuntimeError("Original solver proposed interventions outside frozen subset")
            ids = [choices.index(rid) for rid in sol]
            g = growth(model, pairs, ids, "genes")
            if g >= wild*ratio:
                raise RuntimeError("gMISpy proposed invalid growth blocking KO " + str(sol))
            results.append({"reactions": sorted(sol), "genes": sorted(pairs[i]["gene"] for i in ids),
                            "verified_growth": g})
        summary = {"status":"PASS","function":"cyclic_gmispy.calculateMCS",
                   "original_revision":"76ce96de9d4e18c8200876f5a73d3b2d60e4a012",
                   "model_sha256":sha,"reaction_candidates":choices,
                   "wall_s":elapsed,"solutions":results,
                   "not_full_regulatory_cyclic_gMISpy":True}
        record_json(out, "gmispy_mcs.json", summary)
        print("DRNAS_GMISPY_R2_ORIGINAL_MCS", json.dumps({
            "status":"PASS", "solutions":len(results),
            "wall_s":round(elapsed,5), "model_sha256":sha,
            "scope":"upstream reaction-level MILP MCS, not full cyclic regulation"}), flush=True)
    except BaseException as exc:
        record_json(out, "gmispy_mcs.json", {"status":"FAILED","error":str(exc),
                    "model_sha256":sha, "note":"No timing superiority claim allowed"})
        print("DRNAS_GMISPY_R2_ORIGINAL_MCS_FAILED",repr(exc),flush=True)
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["sat-lp", "upstream-mcs"])
    p.add_argument("--out", default="medical-results/gmispy-r2")
    p.add_argument("--max-genes", type=int, default=18)
    p.add_argument("--growth-ratio", type=float, default=0.01)
    args = p.parse_args()
    if not 0 < args.growth_ratio < 1:
        raise ValueError("Growth ratio must be in (0, 1)")
    if args.mode == "sat-lp":
        benchmark(Path(args.out), args.max_genes, args.growth_ratio)
    else:
        upstream_mcs(Path(args.out), args.max_genes, args.growth_ratio)
