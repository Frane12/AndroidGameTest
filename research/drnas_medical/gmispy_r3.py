#!/usr/bin/env python3
"""DRNAS Medical R3 — real AND/OR gene-protein-reaction constraints in E. coli.

All biological constraints originate from COBRApy textbook (BiGG e_coli_core).
The solver is PySAT CaDiCaL (DRNAS-inspired structural algorithm), NOT
a compiled native DRNAS release. No cancer or full cyclic-gMISpy claims.
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

BASE = ("b2926 b1779 b2779 b3919 b1136 b0720 b3236 b0767 b1852 "
        "b2029 b4025 b1761 b3956 b0474 b1479 b1702 b2463 b2587").split()
COMPLEX = ("b2415 b1818 b1817 b2417 b1101 b3738 b3736 "
           "b0978 b0979 b1773 b2097 b0115 b0114 b0116").split()
EXPECTED_SBML_SHA = "13daac1b0ef19a12459371d4c11d16122ffaccf207070c08a6a66f8ba983b91f"


def parse_rule(text, gene_names):
    root = ast.parse(text, mode="eval").body
    def check(node):
        if isinstance(node, ast.Name):
            if node.id not in gene_names:
                raise ValueError("GPR has unknown gene " + node.id)
        elif isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            for child in node.values:
                check(child)
        else:
            raise ValueError("Non-monotone or unsupported GPR: " + text)
    check(root)
    def evaluate(node, knocked):
        if isinstance(node, ast.Name):
            return node.id not in knocked
        if isinstance(node.op, ast.And):
            return all(evaluate(x, knocked) for x in node.values)
        return any(evaluate(x, knocked) for x in node.values)
    return root, lambda knocked: evaluate(root, knocked)


def prepare(out):
    from cobra.io import load_model, write_sbml_model
    model = load_model("textbook")
    model.solver = "glpk"
    if (len(model.reactions), len(model.metabolites), len(model.genes)) != (95, 72, 137):
        raise AssertionError("Unexpected e_coli_core model dimensions")
    wild = float(model.slim_optimize(error_value=float("nan")))
    if not math.isfinite(wild) or wild < 0.1:
        raise AssertionError("Invalid E. coli wild-type biomass")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "e_coli_core.xml"
    write_sbml_model(model, str(path))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != EXPECTED_SBML_SHA:
        raise AssertionError("Input SBML changed since R2: " + sha)
    genes = BASE + COMPLEX
    assert len(genes) == len(set(genes)) == 32
    available = {g.id for g in model.genes}
    assert set(genes) <= available, "Selected gene missing in biological model"
    rules = {}
    and_count = or_count = 0
    for rxn in model.reactions:
        s = rxn.gene_reaction_rule.strip()
        if not s:
            continue
        tree, fn = parse_rule(s, available)
        if not fn(frozenset()):
            raise AssertionError("GPR false for wild-type gene assignment")
        rules[rxn.id] = (s, tree, fn)
        and_count += any(isinstance(z, ast.And) for z in ast.walk(tree))
        or_count += any(isinstance(z, ast.Or) for z in ast.walk(tree))
    complex_examples = {
        k: rules[k][0] for k in ("GLCpts", "ATPS4r", "CYTBD", "FBA", "PDH", "TKT1")
    }
    if and_count < 6 or or_count < 10:
        raise AssertionError("Complex GPR coverage missing")
    return model, genes, rules, wild, sha, and_count, or_count, complex_examples


def disabled_reactions(rules, gene_ids):
    knocked = frozenset(gene_ids)
    return tuple(sorted(rid for rid, (_, _, fn) in rules.items() if not fn(knocked)))


def fba_growth(model, genes, combo, via, disabled=None):
    with model:
        if via == "gene":
            for ix in combo:
                model.genes.get_by_id(genes[ix]).knock_out()
        elif via == "reaction":
            if disabled is None:
                raise ValueError("disabled reaction signature required")
            for rxn_id in disabled:
                model.reactions.get_by_id(rxn_id).knock_out()
        else:
            raise ValueError(via)
        value = float(model.slim_optimize(error_value=float("nan")))
        return value if math.isfinite(value) else 0.0


def all_combinations(n, max_k):
    for k in range(1, max_k + 1):
        yield from itertools.combinations(range(n), k)


def structural_oracle(model, genes, rules, max_k, threshold):
    # Independent exhaustive reference: every KO measured through COBRA gene KO,
    # and independently through a separate reaction KO derived from Boolean GPR.
    start = time.perf_counter()
    truth = {}
    minima = set()
    rows = []
    for combo in all_combinations(len(genes), max_k):
        disabled = disabled_reactions(rules, (genes[i] for i in combo))
        g = fba_growth(model, genes, combo, "gene")
        r = fba_growth(model, genes, combo, "reaction", disabled=disabled)
        if abs(g-r) > 1e-7:
            raise AssertionError("GPR and native COBRA knockouts disagree: " +
                                 str(combo) + " " + str((g,r)))
        lethal = g < threshold
        truth[combo] = lethal
        if lethal and not any(set(p).issubset(combo) for p in minima):
            minima.add(combo)
        rows.append({
            "ko": "|".join(genes[i] for i in combo),
            "k": len(combo), "knocked_reactions": "|".join(disabled),
            "growth_gene": round(g, 10), "growth_from_GPR_reactions": round(r, 10),
            "growth_blocked": lethal
        })
    for combo, lethal in truth.items():
        if lethal and not any(set(m).issubset(combo) for m in minima):
            raise AssertionError("Minimal set coverage mismatch")
    return truth, minima, rows, time.perf_counter() - start


def sat_arm(model, genes, rules, max_k, threshold, truth, minima, method):
    from pysat.card import CardEnc, EncType
    from pysat.solvers import Solver
    assert method in ("plain", "structural", "structural_memo")
    start = time.perf_counter()
    selected = set()
    disabled_cache = {}
    sat_calls = lp_calls = cache_hits = 0
    actual_solve_s = 0.0
    tried = 0
    for k in range(1, max_k + 1):
        formula = CardEnc.equals(lits=list(range(1, len(genes)+1)), bound=k,
                                 encoding=EncType.seqcounter, top_id=len(genes))
        with Solver(name="cadical195", bootstrap_with=formula.clauses) as solver:
            if method != "plain":
                for known in selected:
                    solver.add_clause([-i - 1 for i in known])
            while True:
                t = time.perf_counter()
                possible = solver.solve()
                actual_solve_s += time.perf_counter() - t
                sat_calls += 1
                if not possible:
                    break
                answer = solver.get_model()
                chosen = tuple(i for i in range(len(genes)) if i+1 in answer)
                if len(chosen) != k:
                    raise AssertionError("Invalid SAT cardinality assignment")
                if chosen not in truth:
                    raise AssertionError("SAT returned non-reference candidate")
                tried += 1
                signature = disabled_reactions(rules, (genes[i] for i in chosen))
                if method == "structural_memo" and signature in disabled_cache:
                    g = disabled_cache[signature]
                    cache_hits += 1
                else:
                    g = fba_growth(model, genes, chosen, "gene")
                    lp_calls += 1
                    if method == "structural_memo":
                        disabled_cache[signature] = g
                lethal = g < threshold
                if lethal != truth[chosen]:
                    raise AssertionError("SAT/LP and independent reference disagree: " + str(chosen))
                is_min = lethal and not any(set(p).issubset(chosen) for p in selected)
                if is_min:
                    selected.add(chosen)
                if lethal and method != "plain":
                    # Monotone GPR: any superset KO disables >= same reactions;
                    # optimum biomass flux cannot increase after disabling more reactions.
                    solver.add_clause([-i - 1 for i in chosen])
                else:
                    chosen_set = set(chosen)
                    solver.add_clause([-(i+1) if i in chosen_set else (i+1)
                                       for i in range(len(genes))])
    if selected != minima:
        raise AssertionError("Minimal interventions disagree: " +
                             repr(sorted(selected ^ minima)))
    return {
        "method": method, "wall_s": round(time.perf_counter()-start, 7),
        "sat_solve_s": round(actual_solve_s, 7),
        "sat_calls": sat_calls, "candidates": tried, "lp_calls": lp_calls,
        "gpr_signature_cache_hits": cache_hits, "minimal_sets": len(selected),
        "crosscheck": "PASS"
    }


def benchmark(out, max_k, repeats):
    if max_k not in (2, 3):
        raise ValueError("R3 supports k=2 or k=3 for exact oracle")
    if not 1 <= repeats <= 5:
        raise ValueError("1<=repeats<=5")
    model, genes, rules, wild, sha, a_count, o_count, examples = prepare(out)
    threshold = wild * 0.01
    truth, minima, raw_oracle, reference_s = structural_oracle(
        model, genes, rules, max_k, threshold)
    n = len(genes)
    with (out / "exhaustive_growth_checks.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(raw_oracle[0]))
        w.writeheader()
        w.writerows(raw_oracle)
    repetitions = []
    methods = ("plain", "structural", "structural_memo")
    for rep in range(repeats):
        order = methods[rep % 3:] + methods[:rep % 3]
        for method in order:
            trial = sat_arm(model, genes, rules, max_k, threshold, truth, minima, method)
            trial["repeat"] = rep
            repetitions.append(trial)
            print("DRNAS_GMISPY_R3_TRIAL", json.dumps(trial), flush=True)
    medians = {
        method: statistics.median(x["wall_s"] for x in repetitions if x["method"] == method)
        for method in methods
    }
    result = {
        "protocol": "DRNAS-MEDICAL-R3-E_COLI_CORE-REAL_GPR",
        "model_name": "BiGG e_coli_core / COBRApy textbook",
        "model_source_sbml_sha256": sha,
        "genes": genes, "gene_count": n,
        "reaction_count": len(model.reactions),
        "and_gpr_count": a_count, "or_gpr_count": o_count,
        "original_complex_gpr_examples": examples,
        "wildtype_growth": wild,
        "blocked_if_biomass_less_than": threshold,
        "k_limit": max_k,
        "independent_exhaustive": {
            "candidates": len(truth), "lp_calls": 2*len(truth),
            "gene_vs_reaction_match_all": True, "wall_s": reference_s,
            "minimal_gene_knockout_sets": [
                list(genes[i] for i in x) for x in sorted(minima)
            ],
        },
        "sat_core": "PySAT CaDiCaL 1.9.5, not native DRNAS",
        "methods": methods, "repetitions": repetitions, "median_wall_s": medians,
        "no_clinical_evidence": True, "no_full_gmispy_cyclic_feedback": True,
        "fair_timing_note": "Interleaved 3-arm SAT/GLPK timings including GPR parsing "
                            "and LP oracle cost; exhaustive reference also runs a second LP "
                            "to verify exact GPR semantics. Resource contention and short "
                            "wall times limit generalization.",
    }
    (out / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print("DRNAS_GMISPY_R3_SUMMARY", json.dumps({
        "real_model_sha256": sha, "genes": n, "AND_rules": a_count,
        "OR_rules": o_count, "combinations": len(truth),
        "minimal_interventions": len(minima),
        "reference_lp_calls": 2*len(truth),
        "medians_s": medians,
        "trials": {m: [(t["candidates"], t["lp_calls"], t["gpr_signature_cache_hits"])
                       for t in repetitions if t["method"] == m] for m in methods},
        "independent_oracle": "PASS"
    }), flush=True)


def upstream_gpr(out):
    from cobra.io import load_model, write_sbml_model
    from cyclic_gmispy.calculateGMCSwithCycles import getGPRDict, boolTransformer
    model = load_model("textbook")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "e_coli_core.xml"
    write_sbml_model(model, str(path))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if sha != EXPECTED_SBML_SHA:
        raise AssertionError("Real model SHA differs from SAT job")
    grouped = getGPRDict(model)
    examples = {}
    for rid in ("GLCpts", "ATPS4r", "CYTBD", "FBA", "PDH", "TKT1"):
        matched = [value for value in grouped.values() if rid in value["reactions"]]
        if len(matched) != 1:
            raise AssertionError("gMISpy did not map known complex GPR: " + rid)
        value = matched[0]
        transformed = boolTransformer({
            "sources": [], "targets": [], "interaction": [], "genes": value["genes"]
        }, value)
        if not transformed["gpr"]:
            raise AssertionError("Original gMISpy returned empty GPR")
        examples[rid] = {
            "upstream_gpr": str(value["gpr"]),
            "official_transformed_marker": transformed["gpr"],
            "genes": sorted(value["genes"])
        }
    if " and " not in examples["PDH"]["upstream_gpr"] or " or " not in examples["FBA"]["upstream_gpr"]:
        raise AssertionError("Expected complex AND/OR missing upstream")
    report = {
        "status": "PASS",
        "model_source_sbml_sha256": sha,
        "upstream_gmispy_commit": "76ce96de9d4e18c8200876f5a73d3b2d60e4a012",
        "upstream_api": ["getGPRDict", "boolTransformer"],
        "complex_examples": examples,
        "is_full_gmispy_optimization": False
    }
    (out/"upstream_gpr.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    print("DRNAS_GMISPY_R3_UPSTREAM_GPR", json.dumps({
        "status": "PASS", "complex_rules": len(examples), "same_model_sha256": sha
    }), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["benchmark", "upstream-gpr"])
    p.add_argument("--out", default="medical-results/r3")
    p.add_argument("--max-k", type=int, default=3)
    p.add_argument("--repeats", type=int, default=3)
    x = p.parse_args()
    if x.mode == "benchmark":
        benchmark(Path(x.out), x.max_k, x.repeats)
    else:
        upstream_gpr(Path(x.out))
