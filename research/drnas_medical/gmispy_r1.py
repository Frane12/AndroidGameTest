#!/usr/bin/env python3
"""DRNAS Medical gMISpy R1: gMISpy regulatory-layer smoke and audited SAT feasibility.

IMPORTANT: These are synthetic networks. We test Boolean fixed-point viability,
not gMISpy's full metabolic MILP or clinical phenotype predictions.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import itertools
import json
import pathlib
import subprocess
import sys
import time

from benchmark import parse, solve, check, verify_model
from boolean_models import dimacs, relation

MODELS = {
    "feedback": {
        "A": "A", "B": "A", "C": "B | !D", "D": "C",
        "E": "!D", "F": "E | C", "gpr": "C & F",
    },
    "inhibitory": {
        "A": "A", "B": "!A | C", "C": "B & A", "D": "C | !E",
        "E": "D", "F": "D & B", "gpr": "D & F",
    },
    "mixed": {
        "A": "A", "B": "A | !C", "C": "B & D", "D": "C | E",
        "E": "!F", "F": "B | E", "gpr": "B & (D | F)",
    },
}


def parse_expr(expr, genes):
    """Safe Boolean grammar only: names, !, &, |, parentheses."""
    root = ast.parse(expr.replace("!", "~"), mode="eval").body
    def validate(node):
        if isinstance(node, ast.Name):
            if node.id not in genes:
                raise ValueError("Unknown regulator: " + node.id)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            validate(node.operand)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitOr, ast.BitAnd)):
            validate(node.left)
            validate(node.right)
        else:
            raise ValueError("Unsupported Boolean expression: " + expr)
    validate(root)
    deps = sorted({n.id for n in ast.walk(root) if isinstance(n, ast.Name)})
    def evaluate(node, values):
        if isinstance(node, ast.Name):
            return bool(values[node.id])
        if isinstance(node, ast.UnaryOp):
            return not evaluate(node.operand, values)
        a, b = evaluate(node.left, values), evaluate(node.right, values)
        return a and b if isinstance(node.op, ast.BitAnd) else a or b
    return deps, lambda values: evaluate(root, values)


def compiled(model):
    genes = sorted(k for k in model if k != "gpr")
    if len(genes) != 6:
        raise ValueError("R1 small-model oracle assumes six genes")
    rules = {g: parse_expr(model[g], genes) for g in genes}
    gpr = parse_expr(model["gpr"], genes)
    return genes, rules, gpr


def oracle(model, ko):
    genes, rules, gpr = compiled(model)
    total_fixed = 0
    viable_fixed = 0
    for state in itertools.product((False, True), repeat=len(genes)):
        values = dict(zip(genes, state))
        if all(values[g] == (False if g in ko else rules[g][1](values)) for g in genes):
            total_fixed += 1
            viable_fixed += int(gpr[1](values))
    return total_fixed, viable_fixed


def cnf(model, ko):
    genes, rules, gpr = compiled(model)
    indices = {g: i + 1 for i, g in enumerate(genes)}
    clauses = []
    for target in genes:
        deps, fn = rules[target]
        vars_used = [indices[g] for g in deps]
        def transition(*bits, deps=deps, fn=fn, knocked=(target in ko)):
            return False if knocked else fn(dict(zip(deps, bits)))
        clauses += relation(indices[target], vars_used, transition)
    deps, fn = gpr
    clauses += relation(len(genes) + 1, [indices[g] for g in deps],
                        lambda *bits: fn(dict(zip(deps, bits))))
    clauses.append((len(genes) + 1,))
    return len(genes) + 1, sorted(set(clauses))


def upstream_smoke(output):
    """Call real upstream gMISpy implementation; it is NOT the DRNAS timing baseline."""
    from cyclic_gmispy.calculateGMCSwithCycles import boolTransformer, bonesisCalculateCutSets
    edges = dict(sources=["A", "B"], targets=["B", "C"], interaction=[1, 1],
                 genes=["A", "B", "C"])
    bnet = boolTransformer(edges, {"gpr": "C"})
    assert bnet["B"] == "A" and bnet["C"] == "B" and bnet["gpr"] == "C", bnet
    t0 = time.perf_counter()
    interventions = bonesisCalculateCutSets(bnet, maxKOLength=2)
    elapsed = time.perf_counter() - t0
    report = {
        "upstream": "PlanesLab/cyclic-gMISpy",
        "upstream_revision": "76ce96de9d4e18c8200876f5a73d3b2d60e4a012",
        "api": ["boolTransformer", "bonesisCalculateCutSets"],
        "upstream_boolean_network": bnet,
        "interventions": [dict(item) for item in interventions],
        "elapsed_s": elapsed,
        "scope": "upstream_BoNesis_regulatory_layer_smoke_not_full_gMISpy_FBA",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "upstream_smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print("DRNAS_GMISPY_UPSTREAM_SMOKE", json.dumps(report), flush=True)


def benchmark(out, cap, max_r108):
    out.mkdir(parents=True, exist_ok=True)
    records = []
    cases = []
    r108_used = 0
    for name, model in MODELS.items():
        genes, _, _ = compiled(model)
        for length in range(3):
            for combo in itertools.combinations(genes, length):
                ko = frozenset(combo)
                fixed, viable = oracle(model, ko)
                vars_count, clauses = cnf(model, ko)
                path = out / (name + "_KO_" + ("-".join(combo) or "none") + ".cnf")
                path.write_text(dimacs(vars_count, clauses))
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                expected = "SAT" if viable else "UNSAT"
                cases.append(dict(model=name, ko=list(combo), fixed=fixed,
                                  viable=viable, expected=expected, cnf=path.name, sha256=sha))
                observed = {}
                for method in ("cadical195", "kissat404"):
                    _, original = parse(path)
                    res = solve(method, original, cap)
                    check(res, expected)
                    observed[method] = res["status"]
                    records.append(dict(model=name, ko=",".join(combo), method=method,
                                        expected=expected, observed=res["status"],
                                        wall_s=res["wall_s"], preprocessing_s=0.,
                                        total_s=res["wall_s"], sha256=sha))
                if (r108_used < max_r108 and fixed > 0 and
                        (length == 0 or (length == 1 and combo[0] in ("A", "C")))):
                    r108_used += 1
                    evidence = out / (path.stem + ".r108.json")
                    augmented = out / (path.stem + ".r108.cnf")
                    started = time.perf_counter()
                    p = subprocess.run([sys.executable, "research/r108_hidden_xor.py", "export",
                                        "--cnf", str(path), "--out", str(evidence),
                                        "--augmented", str(augmented), "--rounds", "1"],
                                       capture_output=True, text=True, timeout=20)
                    preprocessing_s = time.perf_counter() - started
                    if p.returncode:
                        raise RuntimeError("R108 prepass failed: " + p.stderr[-1500:])
                    meta = json.loads(evidence.read_text())
                    assert meta["sha256"] == sha, "source SHA mismatch"
                    if meta.get("gf2_unsat"):
                        assert expected == "UNSAT", "Unsound certified UNSAT"
                    else:
                        assert path.read_bytes() == augmented.read_bytes(), "Unexpected changed CNF"
                    _, new_clauses = parse(augmented)
                    remaining = cap - preprocessing_s
                    if remaining <= 0:
                        result = dict(status="TIMEOUT", wall_s=0)
                    else:
                        result = solve("cadical195", new_clauses, remaining)
                        check(result, expected)
                    records.append(dict(model=name, ko=",".join(combo),
                                        method="DRNAS-R108+cadical195", expected=expected,
                                        observed=result["status"],
                                        wall_s=result["wall_s"],
                                        preprocessing_s=round(preprocessing_s, 6),
                                        total_s=round(preprocessing_s + result["wall_s"], 6),
                                        sha256=sha))
                print("DRNAS_GMISPY_TRIAL", json.dumps({
                    "model": name, "knockout": list(combo), "fixed_points": fixed,
                    "viable_points": viable, "expected": expected,
                    "cadical": observed["cadical195"], "kissat": observed["kissat404"],
                }), flush=True)
    for model_name in MODELS:
        valid = [c for c in cases if c["model"] == model_name and c["fixed"] > 0
                 and c["viable"] == 0]
        minimum = min((len(c["ko"]) for c in valid), default=None)
        print("DRNAS_GMISPY_MIN_KO", json.dumps({
            "model": model_name, "minimum": minimum,
            "solutions": [c["ko"] for c in valid if len(c["ko"]) == minimum]
                         if minimum is not None else [],
        }), flush=True)
    with (out / "paired.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    manifest = {
        "protocol": "DRNAS-MEDICAL-GMISPY-R1-SYNTHETIC-FIXEDPOINT",
        "cases": cases, "model_rules": MODELS, "cap_s": cap,
        "upstream_is_separate_smoke": True,
        "no_metabolic_flux_model": True,
        "no_real_cancer_data": True,
        "no_gmispy_speedup_claim": True,
        "drnas_r108_pairs": r108_used,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("DRNAS_GMISPY_SUMMARY", json.dumps({
        "cases": len(cases), "timings": len(records),
        "r108_pairs": r108_used, "all_oracle_checks": "PASS",
        "note": "Synthetic Boolean layer only. No paired full-gMISpy runtime result.",
    }), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["upstream-smoke", "sat-benchmark"])
    ap.add_argument("--out", default="medical-results/gmispy-r1")
    ap.add_argument("--cap", type=float, default=5.0)
    ap.add_argument("--r108", type=int, default=6)
    a = ap.parse_args()
    if a.mode == "upstream-smoke":
        upstream_smoke(pathlib.Path(a.out))
    else:
        benchmark(pathlib.Path(a.out), a.cap, a.r108)
