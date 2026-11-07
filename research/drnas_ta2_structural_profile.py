#!/usr/bin/env python3
"""DRNAS TA2 — bounded source-only SAT structural telemetry, beyond XOR.

Purpose: characterize 40 SHA-pinned original SAT2025 formulas for future
adaptive selectors, not to claim a win or train on a sealed evaluation set.
Reads only original DIMACS clauses; never uses SAT status, solver runtime,
or labels to derive features. Costs are charged in any future live router.
This exploratory first pass is NOT a blind validation of a new selector.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
import statistics
import time

PROTOCOL = "DRNAS-TA2-SOURCE-ONLY-SAT-STRUCTURE-v1"
ROOT = pathlib.Path("r199")
SRC = ROOT / "sources"
SAMPLE_CLAUSES = 16000
SAMPLE_LITERALS = 160000


def need(cond, msg):
    if not cond:
        raise RuntimeError("DRNAS_TA2_FAIL_CLOSED " + msg)


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def ratio(x, y):
    return round(x / y, 6) if y else 0.0


def feature(path):
    """Bounded streaming fingerprint; no proof, no answer prediction."""
    started = time.perf_counter()
    total_vars = total_clauses = 0
    clauses_scanned = literal_count = 0
    sizes = collections.Counter()
    pos = collections.Counter()
    neg = collections.Counter()
    abs_occ = collections.Counter()
    edges = set()
    xor_masks = collections.defaultdict(set)
    units = horn = dual_horn = binary = pure_pos = pure_neg = long = 0
    cap_hit = False

    def consume(lits):
        nonlocal clauses_scanned, literal_count, units, horn, dual_horn
        nonlocal binary, pure_pos, pure_neg, long
        clauses_scanned += 1
        literal_count += len(lits)
        k = len(lits)
        sizes[str(min(k, 8)) if k <= 8 else "9+"] += 1
        if k == 1:
            units += 1
        if k == 2:
            binary += 1
            a, b = lits
            edges.add((-a, b))
            edges.add((-b, a))
        if k >= 5:
            long += 1
        plus = sum(v > 0 for v in lits)
        minus = k - plus
        horn += plus <= 1
        dual_horn += minus <= 1
        pure_pos += minus == 0
        pure_neg += plus == 0
        for lit in lits:
            v = abs(lit)
            abs_occ[v] += 1
            if lit > 0:
                pos[v] += 1
            else:
                neg[v] += 1
        # Evidence only: complete four-clause XOR3 templates in sampled source.
        if k == 3 and len({abs(v) for v in lits}) == 3:
            ordered = sorted(lits, key=abs)
            key = tuple(abs(v) for v in ordered)
            mask = sum(1 << j for j, v in enumerate(ordered) if v < 0)
            xor_masks[key].add(mask)

    header = False
    current = []
    with pathlib.Path(path).open("rb") as fd:
        for lineno, raw in enumerate(fd, start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith((b"c", b"%")):
                continue
            if not header:
                tokens = stripped.split()
                need(len(tokens) == 4 and tokens[0:2] == [b"p", b"cnf"],
                     "malformed DIMACS header: " + str(path))
                total_vars, total_clauses = int(tokens[2]), int(tokens[3])
                need(total_vars >= 0 and total_clauses > 0, "bad DIMACS dimensions")
                header = True
                continue
            for token in stripped.split():
                lit = int(token)
                if lit == 0:
                    consume(current)
                    current = []
                    if clauses_scanned >= SAMPLE_CLAUSES or literal_count >= SAMPLE_LITERALS:
                        cap_hit = True
                        break
                else:
                    need(abs(lit) <= total_vars, "literal outside DIMACS variable range")
                    current.append(lit)
                    need(len(current) <= 100000, "oversized single clause")
            if cap_hit:
                break
    need(header and clauses_scanned > 0, "missing DIMACS content")
    if not cap_hit:
        need(not current, "incomplete DIMACS final clause")
        need(clauses_scanned == total_clauses, "DIMACS clause count mismatch")
    observed_vars = len(abs_occ)
    degrees = sorted(abs_occ.values())
    median_occ = statistics.median(degrees) if degrees else 0
    p90_occ = degrees[min(len(degrees) - 1, int(0.9 * len(degrees)))] if degrees else 0
    active_pure = sum(not(pos[v] and neg[v]) for v in abs_occ)
    xor3_templates = sum(
        any(all(((mask in masks) for mask in range(8)
                 if mask.bit_count() % 2 == parity))
            for parity in (0, 1))
        for masks in xor_masks.values()
    )
    reciprocal_implications = sum((b, a) in edges for a, b in edges)
    # Conservative source-only structure classes. These are hypotheses, not
    # correctness-preserving solver transformations or learned predictions.
    bfrac = ratio(binary, clauses_scanned)
    hfrac = ratio(horn, clauses_scanned)
    dfrac = ratio(dual_horn, clauses_scanned)
    lfrac = ratio(long, clauses_scanned)
    degree_skew = round(p90_occ / max(1, median_occ), 4)
    if hfrac >= 0.95:
        tag = "horn_dominant"
    elif dfrac >= 0.95:
        tag = "dual_horn_dominant"
    elif bfrac >= 0.65:
        tag = "binary_implication_dominant"
    elif xor3_templates >= 2:
        tag = "complete_xor3_sample"
    elif degree_skew >= 8:
        tag = "variable_hub_dominated"
    elif lfrac >= 0.5:
        tag = "long_clause_dominant"
    else:
        tag = "mixed_generic"
    return {
        "protocol": PROTOCOL,
        "declared_variables": total_vars,
        "declared_clauses": total_clauses,
        "sampled_clauses": clauses_scanned,
        "sampled_literals": literal_count,
        "sample_fraction_clauses": ratio(clauses_scanned, total_clauses),
        "sample_cap_hit": cap_hit,
        "observed_variables": observed_vars,
        "clauses_by_length": dict(sizes),
        "unit_fraction": ratio(units, clauses_scanned),
        "binary_fraction": bfrac,
        "ternary_fraction": ratio(int(sizes.get("3", 0)), clauses_scanned),
        "long_clause_fraction": lfrac,
        "horn_clause_fraction": hfrac,
        "dual_horn_clause_fraction": dfrac,
        "positive_only_clause_fraction": ratio(pure_pos, clauses_scanned),
        "negative_only_clause_fraction": ratio(pure_neg, clauses_scanned),
        "active_pure_variable_fraction": ratio(active_pure, observed_vars),
        "variable_occurrence_p90_over_median": degree_skew,
        "binary_implication_edges": len(edges),
        "binary_reciprocal_edge_fraction": ratio(reciprocal_implications, len(edges)),
        "complete_xor3_templates_sample": xor3_templates,
        "structural_tag_hypothesis": tag,
        "scan_wall_ms": round((time.perf_counter() - started) * 1000, 3),
    }


def analyze():
    import json as _json
    src = _json.loads((ROOT / "candidates.json").read_text())
    cases = src["cases"]
    need(len(cases) == 40 and len({x["sha256"] for x in cases}) == 40,
         "40 distinct original source SHAs required")
    output = []
    for c in cases:
        p = SRC / (c["id"] + ".cnf")
        need(sha(p) == c["sha256"], "source digest mismatch: " + c["id"])
        data = feature(p)
        # Do NOT read or write the known SAT/UNSAT answer from metadata.
        row = {
            "id": c["id"], "sha256": c["sha256"],
            "family": c["family"], "origin_group": c["group"],
            **data,
        }
        output.append(row)
        print("TA2_SOURCE_FEATURE", json.dumps(row, sort_keys=True), flush=True)
    output.sort(key=lambda x: x["sha256"])
    need(len(output) == 40, "incomplete structural telemetry")
    summary = {
        "protocol": PROTOCOL,
        "status": "TA2_SOURCE_ONLY_AUDIT_PASS",
        "cases": 40,
        "mean_scan_ms": round(statistics.mean(x["scan_wall_ms"] for x in output), 3),
        "max_scan_ms": max(x["scan_wall_ms"] for x in output),
        "source_only_no_solver_outcomes_used": True,
        "not_blind_validation_of_selector": True,
        "tags": dict(collections.Counter(x["structural_tag_hypothesis"] for x in output)),
        "groups": {
            g: [x["id"] for x in output if x["origin_group"] == g]
            for g in sorted({x["origin_group"] for x in output})
        },
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "ta2-structural-fingerprints.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n")
    (ROOT / "ta2-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    lines = [
        "# DRNAS TA2 — structural SAT fingerprints without solver outcomes",
        "",
        "40 SHA-pinned SAT2025 original CNFs; up to 16k clauses / 160k literals per case.",
        "The labels are **heuristic hypotheses only**. No new selector is validated.",
        "",
        "| Formula | Source cohort | Structure hypothesis | Binary % | Horn % | Long % | XOR3 | Scan ms |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for x in output:
        lines.append(
            "| %s | %s | %s | %.1f | %.1f | %.1f | %d | %.2f |" % (
                x["id"], x["origin_group"], x["structural_tag_hypothesis"],
                100 * x["binary_fraction"], 100 * x["horn_clause_fraction"],
                100 * x["long_clause_fraction"],
                x["complete_xor3_templates_sample"], x["scan_wall_ms"]))
    lines += ["", "Follow-up: join paired R199 trial records by SHA only for",
              "exploratory causal hypotheses. Validate any adapted gate on a NEW",
              "source-disjoint holdout; do not retroactively claim R199 blind gains."]
    (ROOT / "ta2-summary.md").write_text("\n".join(lines) + "\n")
    print("TA2_AUDIT_PASS", json.dumps(summary, sort_keys=True), flush=True)


def smoke():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "toy.cnf"
        p.write_text(
            "c tiny mixed test\n"
            "p cnf 4 6\n"
            "1 0\n"
            "-1 2 0\n"
            "1 2 3 0\n"
            "-1 -2 3 0\n"
            "-1 2 -3 0\n"
            "1 -2 -3 0\n")
        r = feature(p)
        need(r["declared_clauses"] == 6 and r["sampled_clauses"] == 6,
             "clause count")
        need(r["complete_xor3_templates_sample"] == 1, "source XOR3 pattern")
        need(r["binary_implication_edges"] == 2, "binary implication edges")
        need(r["unit_fraction"] > 0 and r["ternary_fraction"] > 0, "mixed profile")
    print("TA2_SMOKE_PASS", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("smoke", "analyze"))
    args = p.parse_args()
    if args.action == "smoke":
        smoke()
    else:
        analyze()
