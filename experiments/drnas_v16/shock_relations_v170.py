#!/usr/bin/env python3
"""DRNAS SAT V17.0 — frozen relational k-core shock test.

Development evidence: completed V16.8 seeds 168000..168029 only.  The rule is
frozen in this source before any 170xxx CNF is generated or solved:

    on in-distribution random 3-SAT, use upstream Kissat --sat iff the mean
    core number of the unsigned variable 2-section graph is <= 16.50.

The experiment also runs target-only and restart-only controls to identify
which half of --sat produces any gain.  This is exploratory evidence for one
random-3SAT generator family, not a general SAT claim.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import hashlib
import heapq
import json
import math
from pathlib import Path
import random
import re
import statistics
import subprocess
import time


PINNED = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CAP = 6.0
REPEATS = 2
CORE_THRESHOLD = 16.50
HOLDOUT = tuple(range(170000, 170030))
CONTROLS = tuple(range(170030, 170036))
MODES = ("baseline", "target-only", "restart-only", "sat-fixed", "core-gate")
FLAGS = {
    "baseline": (),
    "target-only": ("--target=2",),
    "restart-only": ("--restartint=50",),
    "sat-fixed": ("--sat",),
}


def generate(path: Path, nvars: int, density: float, seed: int) -> str:
    rng = random.Random(seed)
    nclauses = round(nvars * density)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as out:
        out.write(
            f"c DRNAS-v170 seed={seed} n={nvars} density={density} "
            "frozen_core_threshold=16.50\n"
        )
        out.write(f"p cnf {nvars} {nclauses}\n")
        for _ in range(nclauses):
            variables = rng.sample(range(1, nvars + 1), 3)
            signs = [1 if rng.getrandbits(1) else -1 for _ in range(3)]
            out.write(" ".join(str(v * s) for v, s in zip(variables, signs)) + " 0\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_dimacs(path: Path):
    nvars = declared = None
    clauses = []
    pending = []
    with path.open(encoding="ascii") as source:
        for raw in source:
            line = raw.strip()
            if not line or line.startswith(("c", "%")):
                continue
            if line.startswith("p "):
                fields = line.split()
                if len(fields) != 4 or fields[1] != "cnf" or nvars is not None:
                    raise ValueError("invalid DIMACS header")
                nvars, declared = int(fields[2]), int(fields[3])
                continue
            if nvars is None:
                raise ValueError("clause before DIMACS header")
            for token in line.split():
                literal = int(token)
                if literal:
                    if abs(literal) > nvars:
                        raise ValueError("literal outside declared variable range")
                    pending.append(literal)
                else:
                    if not pending:
                        raise ValueError("empty clause is outside this experiment")
                    clauses.append(tuple(pending))
                    pending = []
    if nvars is None or pending or len(clauses) != declared:
        raise ValueError("invalid DIMACS clause count")
    return nvars, clauses


def relational_features(path: Path):
    nvars, clauses = parse_dimacs(path)
    adjacency = [set() for _ in range(nvars + 1)]
    occurrence = [0] * (nvars + 1)
    positive = negative = 0
    ternary = 0
    for clause in clauses:
        ternary += len(clause) == 3
        variables = sorted({abs(lit) for lit in clause})
        if len(variables) != len(clause):
            raise ValueError("repeated variable inside clause")
        for literal in clause:
            occurrence[abs(literal)] += 1
            positive += literal > 0
            negative += literal < 0
        for i, a in enumerate(variables):
            for b in variables[i + 1:]:
                adjacency[a].add(b)
                adjacency[b].add(a)

    # Exact degeneracy peeling.  The assigned removal degree is the standard
    # core number; mean_core is a compact measure of global constraint coupling.
    degree = [len(adjacency[v]) for v in range(nvars + 1)]
    heap = [(degree[v], v) for v in range(1, nvars + 1)]
    heapq.heapify(heap)
    removed = [False] * (nvars + 1)
    core = [0] * (nvars + 1)
    while heap:
        d, vertex = heapq.heappop(heap)
        if removed[vertex] or d != degree[vertex]:
            continue
        removed[vertex] = True
        core[vertex] = d
        for neighbor in adjacency[vertex]:
            if not removed[neighbor] and degree[neighbor] > d:
                degree[neighbor] -= 1
                heapq.heappush(heap, (degree[neighbor], neighbor))

    graph_degree = [len(adjacency[v]) for v in range(1, nvars + 1)]
    mean_degree = statistics.mean(graph_degree)
    mean_occurrence = statistics.mean(occurrence[1:])
    return {
        "nvars": nvars,
        "nclauses": len(clauses),
        "density": len(clauses) / nvars,
        "three_fraction": ternary / max(1, len(clauses)),
        "mean_core": statistics.mean(core[1:]),
        "max_core": max(core[1:]),
        "graph_degree_cv": statistics.pstdev(graph_degree) / mean_degree,
        "occurrence_cv": statistics.pstdev(occurrence[1:]) / mean_occurrence,
        "polarity_balance": 1.0 - abs(positive - negative) / max(1, positive + negative),
    }


def in_distribution(feature):
    return (
        feature["nvars"] >= 260
        and 4.10 <= feature["density"] <= 4.42
        and feature["three_fraction"] >= 0.995
    )


def gate(feature):
    return "sat-fixed" if in_distribution(feature) and feature["mean_core"] <= CORE_THRESHOLD else "baseline"


def parse_stats(output: str):
    result = {}
    for key in ("conflicts", "decisions", "propagations", "restarts", "search_ticks"):
        match = re.search(r"(?mi)^c\s+" + key + r"\s*:?\s+([0-9][0-9,]*)\b", output)
        result[key] = int(match.group(1).replace(",", "")) if match else ""
    return result


def valid_model(path: Path, output: str) -> bool:
    assignment = {}
    for line in output.splitlines():
        if not line.startswith("v "):
            continue
        for token in line.split()[1:]:
            literal = int(token)
            if not literal:
                continue
            variable, value = abs(literal), literal > 0
            if variable in assignment and assignment[variable] != value:
                return False
            assignment[variable] = value
    nvars, clauses = parse_dimacs(path)
    if len(assignment) != nvars:
        return False
    return all(any(assignment[abs(lit)] == (lit > 0) for lit in clause) for clause in clauses)


def solve(solver: str, path: Path, flags, timeout: float):
    command = [solver, *flags, "-s", str(path)]
    started = time.perf_counter()
    try:
        process = subprocess.run(
            command, capture_output=True, text=True, errors="replace",
            check=False, timeout=max(0.001, timeout),
        )
        status = {0: "UNKNOWN", 10: "SAT", 20: "UNSAT"}.get(process.returncode, "ERROR")
        output = process.stdout + "\n" + process.stderr
        returncode = process.returncode
    except subprocess.TimeoutExpired as error:
        status = "TIMEOUT"
        returncode = -1
        stdout = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode("utf-8", "replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        output = stdout + "\n" + stderr
    elapsed = time.perf_counter() - started
    if status == "SAT" and not valid_model(path, output):
        raise RuntimeError(f"invalid SAT assignment for {path}")
    if status in ("ERROR", "UNKNOWN"):
        raise RuntimeError(f"unexpected Kissat result {status} rc={returncode} for {path}")
    return status, elapsed, returncode, parse_stats(output)


def run_mode(solver: str, path: Path, mode: str, timeout: float):
    started = time.perf_counter()
    feature_seconds = 0.0
    selected = mode
    feature = None
    if mode == "core-gate":
        feature_started = time.perf_counter()
        feature = relational_features(path)
        selected = gate(feature)
        feature_seconds = time.perf_counter() - feature_started
    remaining = timeout - (time.perf_counter() - started)
    if remaining <= 0.002:
        return {
            "status": "TIMEOUT", "total_seconds": time.perf_counter() - started,
            "solve_seconds": 0.0, "feature_seconds": feature_seconds,
            "selected": selected, "returncode": -1, "stats": {}, "feature": feature,
        }
    status, solve_seconds, returncode, stats = solve(solver, path, FLAGS[selected], remaining)
    return {
        "status": status, "total_seconds": time.perf_counter() - started,
        "solve_seconds": solve_seconds, "feature_seconds": feature_seconds,
        "selected": selected, "returncode": returncode, "stats": stats, "feature": feature,
    }


def write_csv(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_cases(root: Path):
    cases = []
    for index, seed in enumerate(HOLDOUT + CONTROLS):
        nvars = (260, 340, 420)[index % 3]
        if seed in HOLDOUT:
            density, group = 4.26, "holdout"
        else:
            density = 3.80 if seed < 170033 else 4.70
            group = "control"
        path = root / "cnf" / group / f"random3_n{nvars}_density{density}_seed{seed}.cnf"
        digest = generate(path, nvars, density, seed)
        static = relational_features(path)
        cases.append({
            "group": group, "seed": seed, "nvars": nvars, "density": density,
            "path": str(path), "sha256": digest, **static,
            "frozen_selection": gate(static),
        })
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True)
    parser.add_argument("--root", type=Path, default=Path("drnas-v170-results"))
    parser.add_argument("--timeout", type=float, default=CAP)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    arguments = parser.parse_args()
    if arguments.timeout != CAP or arguments.repeats != REPEATS:
        parser.error("V17.0 protocol fixes timeout=6 and repeats=2")
    arguments.root.mkdir(parents=True, exist_ok=True)
    cases = build_cases(arguments.root)
    manifest = {
        "protocol": "DRNAS SAT V17.0 frozen relational k-core shock test",
        "kissat_commit": PINNED,
        "development_only": "V16.8 seeds 168000..168029",
        "unseen_holdout": "170000..170029",
        "density_controls": "170030..170035",
        "frozen_mean_core_threshold": CORE_THRESHOLD,
        "modes": list(MODES),
        "cases": cases,
    }
    (arguments.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("V170_PROTOCOL_FROZEN_BEFORE_SOLVES", len(cases), "CNFs", flush=True)

    rows = []
    for case in cases:
        path = Path(case["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != case["sha256"]:
            raise RuntimeError("CNF identity changed after manifest")
        for repeat in range(REPEATS):
            order = MODES[repeat:] + MODES[:repeat]
            for mode in order:
                result = run_mode(arguments.solver, path, mode, CAP)
                stats = result["stats"]
                row = {
                    "group": case["group"], "seed": case["seed"], "nvars": case["nvars"],
                    "density": case["density"], "repeat": repeat, "mode": mode,
                    "selected": result["selected"], "status": result["status"],
                    "total_seconds": round(result["total_seconds"], 6),
                    "feature_seconds": round(result["feature_seconds"], 6),
                    "solve_seconds": round(result["solve_seconds"], 6),
                    "mean_core": round(case["mean_core"], 9),
                    "max_core": case["max_core"],
                    "graph_degree_cv": round(case["graph_degree_cv"], 9),
                    "conflicts": stats.get("conflicts", ""),
                    "decisions": stats.get("decisions", ""),
                    "propagations": stats.get("propagations", ""),
                    "restarts": stats.get("restarts", ""),
                    "search_ticks": stats.get("search_ticks", ""),
                }
                rows.append(row)
                print(
                    "V170_MEASURE", case["group"], case["seed"], repeat, mode,
                    "selected", row["selected"], row["status"],
                    f"{row['total_seconds']:.5f}s", "mean_core", row["mean_core"],
                    flush=True,
                )

    write_csv(arguments.root / "measurements.csv", rows)
    identities = [{k: v for k, v in case.items() if k != "path"} for case in cases]
    write_csv(arguments.root / "identities.csv", identities)

    paired = defaultdict(dict)
    for row in rows:
        paired[(row["seed"], row["repeat"])][row["mode"]] = row
    if len(paired) != len(cases) * REPEATS:
        raise RuntimeError("wrong paired instance count")
    for key, modes in paired.items():
        if set(modes) != set(MODES):
            raise RuntimeError(f"incomplete pair {key}")
        answers = {r["status"] for r in modes.values() if r["status"] in ("SAT", "UNSAT")}
        if len(answers) > 1:
            raise RuntimeError(f"SAT/UNSAT disagreement {key}: {answers}")
        for row in modes.values():
            if float(row["total_seconds"]) > CAP + 0.25:
                raise RuntimeError(f"wall budget exceeded {row}")

    summary = {
        "protocol": manifest["protocol"], "pin": PINNED,
        "timeout": CAP, "repeats": REPEATS, "core_threshold": CORE_THRESHOLD,
        "groups": {}, "limitations": [
            "One random-3SAT generator family; no general SAT claim",
            "The 16.50 threshold was discovered on V16.8 development results",
            "SAT assignments checked on original CNF; UNSAT has no independent proof checker",
            "PAR-2 counts each timeout as 12 seconds",
        ],
    }
    for group in ("holdout", "control"):
        summary["groups"][group] = {}
        for mode in MODES:
            subset = [r for r in rows if r["group"] == group and r["mode"] == mode]
            par2 = statistics.mean(
                float(r["total_seconds"]) if r["status"] in ("SAT", "UNSAT") else 2 * CAP
                for r in subset
            )
            summary["groups"][group][mode] = {
                "attempts": len(subset),
                "solved": sum(r["status"] in ("SAT", "UNSAT") for r in subset),
                "PAR2_seconds": round(par2, 6),
                "median_seconds": round(statistics.median(float(r["total_seconds"]) for r in subset), 6),
                "sat_selected": sum(r["selected"] == "sat-fixed" for r in subset),
            }
    holdout_pairs = [modes for (seed, _), modes in paired.items() if seed in HOLDOUT]
    summary["holdout_baseline_sat_oracle"] = {
        "solved_attempts": sum(
            any(modes[mode]["status"] in ("SAT", "UNSAT") for mode in ("baseline", "sat-fixed"))
            for modes in holdout_pairs
        ),
        "PAR2_seconds": round(statistics.mean(
            min(
                float(modes[mode]["total_seconds"])
                if modes[mode]["status"] in ("SAT", "UNSAT") else 2 * CAP
                for mode in ("baseline", "sat-fixed")
            ) for modes in holdout_pairs
        ), 6),
    }
    (arguments.root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("V170_SUMMARY", json.dumps(summary, sort_keys=True), flush=True)
    print("V170_AUDIT_PASS", len(rows), "measurements", len(cases), "CNFs", flush=True)


if __name__ == "__main__":
    main()
