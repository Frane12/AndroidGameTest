#!/usr/bin/env python3
"""DRNAS SAT V17.1 — frozen target/restart cascade filtration.

The V17.0 partial development evidence (first 33 complete paired trials) showed
that target-only is a frequent fast path while restart-only rescues hard cases.
The old one-threshold/one-mode k-core gate lost that complementarity.  V17.1
therefore freezes three auditable filters before any 171xxx CNF is generated:

* cascade-trb: target 0.80 s -> restart 1.20 s -> baseline with the remainder;
* cascade-rtb: restart 1.20 s -> target 0.80 s -> baseline with the remainder;
* relation-filter: use TRB for in-distribution mean_core <= 16.45, otherwise
  RTB; out-of-distribution density controls fall back directly to baseline.

Every cascade has one shared six-second wall budget.  Timed-out stages are
restarted deliberately; their cost is included.  This is a prospective test on
new seeds, not a claim about general SAT performance.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import hashlib
import heapq
import json
from pathlib import Path
import random
import re
import statistics
import subprocess
import time


PINNED = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CAP = 6.0
REPEATS = 2
TARGET_BUDGET = 0.80
RESTART_BUDGET = 1.20
RELATION_THRESHOLD = 16.45
HOLDOUT = tuple(range(171000, 171030))
CONTROLS = tuple(range(171030, 171036))
MODES = (
    "baseline",
    "target-only",
    "restart-only",
    "cascade-trb",
    "cascade-rtb",
    "relation-filter",
)
FLAGS = {
    "baseline": (),
    "target-only": ("--target=2",),
    "restart-only": ("--restartint=50",),
}
ORDERS = {
    "trb": ("target-only", "restart-only", "baseline"),
    "rtb": ("restart-only", "target-only", "baseline"),
    "baseline-only": ("baseline",),
}


def generate(path: Path, nvars: int, density: float, seed: int) -> str:
    rng = random.Random(seed)
    nclauses = round(nvars * density)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii") as output:
        output.write(
            f"c DRNAS-v171 seed={seed} n={nvars} density={density} "
            "target_budget=0.80 restart_budget=1.20 relation_threshold=16.45\n"
        )
        output.write(f"p cnf {nvars} {nclauses}\n")
        for _ in range(nclauses):
            variables = rng.sample(range(1, nvars + 1), 3)
            signs = [1 if rng.getrandbits(1) else -1 for _ in range(3)]
            output.write(" ".join(str(v * s) for v, s in zip(variables, signs)) + " 0\n")
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
    positive = negative = ternary = 0
    for clause in clauses:
        ternary += len(clause) == 3
        variables = sorted({abs(literal) for literal in clause})
        if len(variables) != len(clause):
            raise ValueError("repeated variable inside clause")
        for literal in clause:
            occurrence[abs(literal)] += 1
            positive += literal > 0
            negative += literal < 0
        for index, left in enumerate(variables):
            for right in variables[index + 1:]:
                adjacency[left].add(right)
                adjacency[right].add(left)

    degree = [len(adjacency[v]) for v in range(nvars + 1)]
    heap = [(degree[v], v) for v in range(1, nvars + 1)]
    heapq.heapify(heap)
    removed = [False] * (nvars + 1)
    core = [0] * (nvars + 1)
    while heap:
        current, vertex = heapq.heappop(heap)
        if removed[vertex] or current != degree[vertex]:
            continue
        removed[vertex] = True
        core[vertex] = current
        for neighbor in adjacency[vertex]:
            if not removed[neighbor] and degree[neighbor] > current:
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


def in_distribution(feature) -> bool:
    return (
        feature["nvars"] >= 260
        and 4.10 <= feature["density"] <= 4.42
        and feature["three_fraction"] >= 0.995
    )


def frozen_route(feature) -> str:
    if not in_distribution(feature):
        return "baseline-only"
    return "trb" if feature["mean_core"] <= RELATION_THRESHOLD else "rtb"


def parse_stats(output: str):
    parsed = {}
    for key in ("conflicts", "decisions", "propagations", "restarts", "search_ticks"):
        match = re.search(r"(?mi)^c\s+" + key + r"\s*:?\s+([0-9][0-9,]*)\b", output)
        parsed[key] = int(match.group(1).replace(",", "")) if match else ""
    return parsed


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
            command,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=max(0.001, timeout),
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


def stage_budget(stage: str, remaining: float) -> float:
    if stage == "target-only":
        return min(TARGET_BUDGET, remaining)
    if stage == "restart-only":
        return min(RESTART_BUDGET, remaining)
    return remaining


def run_cascade(solver: str, path: Path, order, started: float, feature_seconds: float, route: str):
    trace = []
    last_stats = {}
    last_returncode = -1
    for stage in order:
        remaining = CAP - (time.perf_counter() - started)
        if remaining <= 0.002:
            break
        budget = stage_budget(stage, remaining)
        status, seconds, returncode, stats = solve(solver, path, FLAGS[stage], budget)
        trace.append({
            "stage": stage,
            "budget": round(budget, 6),
            "status": status,
            "seconds": round(seconds, 6),
        })
        last_stats, last_returncode = stats, returncode
        if status in ("SAT", "UNSAT"):
            return {
                "status": status,
                "total_seconds": time.perf_counter() - started,
                "feature_seconds": feature_seconds,
                "selected": stage,
                "route": route,
                "order": ">".join(order),
                "returncode": returncode,
                "stats": stats,
                "trace": trace,
            }
    return {
        "status": "TIMEOUT",
        "total_seconds": time.perf_counter() - started,
        "feature_seconds": feature_seconds,
        "selected": trace[-1]["stage"] if trace else "none",
        "route": route,
        "order": ">".join(order),
        "returncode": last_returncode,
        "stats": last_stats,
        "trace": trace,
    }


def run_mode(solver: str, path: Path, mode: str):
    started = time.perf_counter()
    feature_seconds = 0.0
    if mode in FLAGS:
        return run_cascade(solver, path, (mode,), started, feature_seconds, mode)
    if mode == "cascade-trb":
        return run_cascade(solver, path, ORDERS["trb"], started, feature_seconds, "trb")
    if mode == "cascade-rtb":
        return run_cascade(solver, path, ORDERS["rtb"], started, feature_seconds, "rtb")
    if mode != "relation-filter":
        raise ValueError(f"unknown mode {mode}")
    feature_started = time.perf_counter()
    feature = relational_features(path)
    feature_seconds = time.perf_counter() - feature_started
    route = frozen_route(feature)
    return run_cascade(solver, path, ORDERS[route], started, feature_seconds, route)


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
            density = 3.80 if seed < 171033 else 4.70
            group = "control"
        path = root / "cnf" / group / f"random3_n{nvars}_density{density}_seed{seed}.cnf"
        digest = generate(path, nvars, density, seed)
        static = relational_features(path)
        cases.append({
            "group": group,
            "seed": seed,
            "nvars": nvars,
            "density": density,
            "path": str(path),
            "sha256": digest,
            **static,
            "frozen_route": frozen_route(static),
        })
    return cases


def par2(row) -> float:
    return float(row["total_seconds"]) if row["status"] in ("SAT", "UNSAT") else 2 * CAP


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", required=True)
    parser.add_argument("--root", type=Path, default=Path("drnas-v171-results"))
    parser.add_argument("--timeout", type=float, default=CAP)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    arguments = parser.parse_args()
    if arguments.timeout != CAP or arguments.repeats != REPEATS:
        parser.error("V17.1 protocol fixes timeout=6 and repeats=2")

    arguments.root.mkdir(parents=True, exist_ok=True)
    cases = build_cases(arguments.root)
    manifest = {
        "protocol": "DRNAS SAT V17.1 frozen target/restart cascade filtration",
        "kissat_commit": PINNED,
        "development_evidence": "V17.0 first 33 complete paired trials; 171xxx unseen",
        "unseen_holdout": "171000..171029",
        "density_controls": "171030..171035",
        "shared_wall_cap_seconds": CAP,
        "target_probe_seconds": TARGET_BUDGET,
        "restart_probe_seconds": RESTART_BUDGET,
        "frozen_relation_threshold": RELATION_THRESHOLD,
        "modes": list(MODES),
        "cases": cases,
    }
    (arguments.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("V171_PROTOCOL_FROZEN_BEFORE_SOLVES", len(cases), "CNFs", flush=True)

    rows = []
    for case in cases:
        path = Path(case["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != case["sha256"]:
            raise RuntimeError("CNF identity changed after manifest")
        for repeat in range(REPEATS):
            order = MODES[repeat:] + MODES[:repeat]
            for mode in order:
                result = run_mode(arguments.solver, path, mode)
                stats = result["stats"]
                row = {
                    "group": case["group"],
                    "seed": case["seed"],
                    "nvars": case["nvars"],
                    "density": case["density"],
                    "repeat": repeat,
                    "mode": mode,
                    "route": result["route"],
                    "order": result["order"],
                    "selected": result["selected"],
                    "status": result["status"],
                    "total_seconds": round(result["total_seconds"], 6),
                    "feature_seconds": round(result["feature_seconds"], 6),
                    "mean_core": round(case["mean_core"], 9),
                    "max_core": case["max_core"],
                    "graph_degree_cv": round(case["graph_degree_cv"], 9),
                    "occurrence_cv": round(case["occurrence_cv"], 9),
                    "polarity_balance": round(case["polarity_balance"], 9),
                    "conflicts": stats.get("conflicts", ""),
                    "decisions": stats.get("decisions", ""),
                    "propagations": stats.get("propagations", ""),
                    "restarts": stats.get("restarts", ""),
                    "search_ticks": stats.get("search_ticks", ""),
                    "stage_trace": json.dumps(result["trace"], separators=(",", ":")),
                }
                rows.append(row)
                print(
                    "V171_MEASURE",
                    case["group"],
                    case["seed"],
                    repeat,
                    mode,
                    "route",
                    row["route"],
                    "selected",
                    row["selected"],
                    row["status"],
                    f"{row['total_seconds']:.5f}s",
                    "mean_core",
                    row["mean_core"],
                    flush=True,
                )

    write_csv(arguments.root / "measurements.csv", rows)
    identities = [{key: value for key, value in case.items() if key != "path"} for case in cases]
    write_csv(arguments.root / "identities.csv", identities)

    paired = defaultdict(dict)
    for row in rows:
        paired[(row["seed"], row["repeat"])][row["mode"]] = row
    if len(paired) != len(cases) * REPEATS:
        raise RuntimeError("wrong paired instance count")
    for key, mode_rows in paired.items():
        if set(mode_rows) != set(MODES):
            raise RuntimeError(f"incomplete pair {key}")
        answers = {row["status"] for row in mode_rows.values() if row["status"] in ("SAT", "UNSAT")}
        if len(answers) > 1:
            raise RuntimeError(f"SAT/UNSAT disagreement {key}: {answers}")
        if any(float(row["total_seconds"]) > CAP + 0.25 for row in mode_rows.values()):
            raise RuntimeError(f"wall budget exceeded {key}")

    summary = {
        "protocol": manifest["protocol"],
        "pin": PINNED,
        "timeout": CAP,
        "repeats": REPEATS,
        "groups": {},
        "limitations": [
            "One random-3SAT generator family; no general SAT claim",
            "Cascade budgets and 16.45 route threshold came from partial V17.0 development evidence",
            "All stage restarts and feature extraction are charged to one six-second wall budget",
            "SAT assignments checked on original CNF; UNSAT has no independent proof checker",
            "PAR-2 counts each timeout as 12 seconds",
        ],
    }
    for group in ("holdout", "control"):
        summary["groups"][group] = {}
        for mode in MODES:
            subset = [row for row in rows if row["group"] == group and row["mode"] == mode]
            summary["groups"][group][mode] = {
                "attempts": len(subset),
                "solved": sum(row["status"] in ("SAT", "UNSAT") for row in subset),
                "PAR2_seconds": round(statistics.mean(par2(row) for row in subset), 6),
                "median_seconds": round(statistics.median(float(row["total_seconds"]) for row in subset), 6),
                "selected_counts": {
                    selected: sum(row["selected"] == selected for row in subset)
                    for selected in FLAGS
                },
            }

    holdout_pairs = [mode_rows for (seed, _), mode_rows in paired.items() if seed in HOLDOUT]
    oracle_modes = ("baseline", "target-only", "restart-only")
    summary["holdout_baseline_target_restart_oracle"] = {
        "solved_attempts": sum(
            any(mode_rows[mode]["status"] in ("SAT", "UNSAT") for mode in oracle_modes)
            for mode_rows in holdout_pairs
        ),
        "PAR2_seconds": round(statistics.mean(
            min(par2(mode_rows[mode]) for mode in oracle_modes)
            for mode_rows in holdout_pairs
        ), 6),
    }
    (arguments.root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("V171_SUMMARY", json.dumps(summary, sort_keys=True), flush=True)
    print("V171_AUDIT_PASS", len(rows), "measurements", len(cases), "CNFs", flush=True)


if __name__ == "__main__":
    main()
