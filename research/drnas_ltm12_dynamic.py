#!/usr/bin/env python3
"""Generate a replayable grouped SAT curriculum and measure verified routing."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import statistics
import tempfile
import time
from unittest.mock import patch

import drnas_ltm12_progressive as L
from drnas_ltm9_independent_cert import parse_dimacs

B, F = L.B, L.F
CAP = 1.5
ARMS = L.SCREEN_ARMS + ("MATH14", "REDUCE_KISSAT")
ROUTERS = ("LTM12_NATIVE", "LTM12_HYBRID")
REFERENCES = ("Kissat", "CaDiCaL", "CryptoMiniSat")
VARIANTS = {
    "implications": ("path", "tree", "layered"),
    "parity": ("pairs", "hub", "ladder"),
    "exactly_one": ("blocks3", "blocks4", "blocks5"),
    "planted_sat": ("3sat", "3and4sat", "3and5sat"),
}
SPLITS = ("train", "validation", "holdout")
COUNTS = (12, 5, 8)


def formula(group, variant, tier, seed):
    rng = random.Random(seed)
    n = rng.randrange(*((45, 76), (115, 166), (190, 251))[tier])
    variables = list(range(1, n + 1))
    planted = {v: bool(rng.getrandbits(1)) for v in variables}
    clauses = []
    if group == "implications":
        planted = {v: v > n // 2 for v in variables}
        for v in variables[1:]:
            if variant == "path":
                parent = v - 1
            elif variant == "tree":
                parent = v // 2
            else:
                parent = rng.randint(max(1, v - 12), v - 1)
            clauses.append((-parent, v))
        clauses.extend([(-1,), (n,)])
    elif group == "parity":
        for index in range(min(120, n // 2)):
            if variant == "pairs":
                a, b, c, d = rng.sample(variables, 4)
            elif variant == "hub":
                a, b = 1, 2
                c, d = rng.sample(variables[2:], 2)
            else:
                a, b, c, d = [variables[(2 * index + offset) % n] for offset in range(4)]
            for triple in ((a, b, c), (a, b, d)):
                rhs = sum(planted[v] for v in triple) % 2
                for bits in itertools.product((0, 1), repeat=3):
                    if sum(bits) % 2 != rhs:
                        clauses.append(tuple(-v if bit else v for v, bit in zip(triple, bits)))
    elif group == "exactly_one":
        width = int(variant[-1])
        winners = []
        blocks = []
        for start in range(0, n, width):
            block = variables[start:start + width]
            winner = rng.choice(block)
            blocks.append(block)
            winners.append(winner)
            planted.update({v: v == winner for v in block})
            clauses.append(tuple(block))
            clauses.extend((-a, -b) for a, b in itertools.combinations(block, 2))
        for left, right, winner in zip(blocks, blocks[1:], winners):
            for v in left:
                candidates = [w for w in right if v != winner or not planted[w]]
                if candidates:
                    clauses.append((-v, -rng.choice(candidates)))
    else:
        extra_width = {"3sat": 3, "3and4sat": 4, "3and5sat": 5}[variant]
        density = (2.8, 4.2, 4.7)[tier]
        for _ in range(round(n * density)):
            width = rng.choice((3, 3, 3, extra_width))
            literals = [v * rng.choice((-1, 1)) for v in rng.sample(variables, width)]
            if not any(planted[abs(lit)] == (lit > 0) for lit in literals):
                i = rng.randrange(width)
                literals[i] = -literals[i]
            clauses.append(tuple(literals))
    permutation = rng.sample(variables, n)
    signed = {v: label * rng.choice((-1, 1)) for v, label in zip(variables, permutation)}
    encoded = sorted({tuple(sorted(signed[abs(lit)] * (1 if lit > 0 else -1)
                                   for lit in clause)) for clause in clauses})
    rng.shuffle(encoded)
    raw = f"p cnf {n} {len(encoded)}\n" + "".join(
        " ".join(map(str, clause)) + " 0\n" for clause in encoded)
    witness = "v " + " ".join(str(signed[v] if planted[v] else -signed[v])
                              for v in variables) + " 0\n"
    return raw, witness


def collect(root, run_seed):
    cases = root / "cases"
    cases.mkdir(parents=True)
    rng = random.Random(run_seed)
    sources = []
    for split, count, variant_index in zip(SPLITS, COUNTS, range(len(SPLITS))):
        for group, variants in VARIANTS.items():
            variant = variants[variant_index]
            for i in range(count):
                tier = i % 3
                seed = rng.getrandbits(64)
                raw, witness = formula(group, variant, tier, seed)
                sha = hashlib.sha256(raw.encode()).hexdigest()
                path = cases / f"{sha}.cnf"
                if path.exists():
                    raise RuntimeError(f"duplicate CNF: {sha}")
                path.write_text(raw)
                if not B.sat_witness_valid(path, B.nvars(path), witness):
                    raise RuntimeError(f"invalid planted witness: {sha}")
                sources.append(dict(id=len(sources), path=str(path), sha256=sha, split=split,
                                    group=group, variant=variant, tier=tier, generator_seed=seed))
    (root / "manifest.json").write_text(json.dumps(
        dict(run_seed=run_seed, corpus="synthetic planted SAT", variants=VARIANTS,
             sources=sources), indent=2))
    return sources


def implication_model(n, clauses):
    graph = [[] for _ in range(2 * n)]
    reverse = [[] for _ in graph]
    for clause in clauses:
        indices = [2 * (abs(lit) - 1) + (lit < 0) for lit in clause]
        a, b = indices[0], indices[-1]
        for start, end in ((a ^ 1, b), (b ^ 1, a)):
            graph[start].append(end)
            reverse[end].append(start)
    seen = set()
    order = []
    for v in range(len(graph)):
        if v in seen:
            continue
        stack = [(v, iter(graph[v]))]
        seen.add(v)
        while stack:
            node, edges = stack[-1]
            child = next(edges, None)
            if child is None:
                order.append(node)
                stack.pop()
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(graph[child])))
    component = [-1] * len(graph)
    for i, v in enumerate(reversed(order)):
        if component[v] != -1:
            continue
        component[v] = i
        stack = [v]
        while stack:
            for child in reverse[stack.pop()]:
                if component[child] == -1:
                    component[child] = i
                    stack.append(child)
    if any(component[2 * i] == component[2 * i + 1] for i in range(n)):
        return None
    return [component[2 * i] > component[2 * i + 1] for i in range(n)]


def parity_model(n, clauses):
    groups = {}
    for clause in clauses:
        literals = sorted(clause, key=abs)
        variables = tuple(map(abs, literals))
        if len(set(variables)) != 3:
            return None
        signs = sum(1 << i for i, lit in enumerate(literals) if lit < 0)
        groups[variables] = groups.get(variables, 0) | (1 << signs)
    # A parity row is sound only with every forbidden assignment represented.
    if any(mask not in (0x69, 0x96) for mask in groups.values()):
        return None
    basis = {}
    for variables, mask in groups.items():
        row = sum(1 << (v - 1) for v in variables)
        rhs = int(mask == 0x69)
        while row:
            pivot = row.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = row, rhs
                break
            previous, bit = basis[pivot]
            row ^= previous
            rhs ^= bit
        if not row and rhs:
            return None
    solution = 0
    for pivot, (row, rhs) in sorted(basis.items()):
        if ((row & solution).bit_count() & 1) != rhs:
            solution |= 1 << pivot
    return [bool(solution & (1 << i)) for i in range(n)]


def shortcut(path):
    if path.stat().st_size > 64 * 1024:
        return None
    data = parse_dimacs(path)
    n, clauses = data["n"], data["clauses"]
    if not 1 <= n <= 512 or not clauses or len(clauses) > 2500:
        return None
    widths = {len(clause) for clause in clauses}
    if widths <= {1, 2}:
        operator, model = "2sat_scc", implication_model(n, clauses)
    elif widths == {3}:
        operator, model = "gf2_elimination", parity_model(n, clauses)
    else:
        return None
    if model is None:
        return None
    witness = "v " + " ".join(str(i if value else -i)
                               for i, value in enumerate(model, 1)) + " 0\n"
    if not B.sat_witness_valid(path, n, witness):
        raise RuntimeError(f"invalid {operator} witness for {path}")
    return operator


def trial(arm, source, seed, model=None):
    started = time.monotonic()
    features = F.extract(source["path"]) if model and model["enabled"] else {}
    selected = L.pick(model, features) if model else arm
    routing_s = time.monotonic() - started if model else 0.0
    operator = None
    if selected == "REDUCE_KISSAT":
        path = Path(source["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise RuntimeError("original CNF SHA changed")
        operator = shortcut(path)
    remaining = CAP - (time.monotonic() - started) - .12
    if operator:
        row = dict(id=source["id"], seed=seed, split=source["split"], status="SAT_VERIFIED",
                   verified=True, php_math_certified=False, decisions=0, conflicts=0)
    elif remaining <= 0:
        row = dict(id=source["id"], seed=seed, split=source["split"], status="UNKNOWN",
                   verified=False, php_math_certified=False)
    elif selected == "MATH14":
        command = B.command
        def math14_command(alias, path, solver_seed, cap):
            cmd = command(alias, path, solver_seed, cap)
            cmd[0] = "mre_atlas23/bin/drnas_math14"
            return cmd
        with patch.object(B, "command", math14_command):
            row = B.run_solver("LTM9_FAST", source, seed, remaining)
    else:
        row = B.run_solver("Kissat" if selected == "REDUCE_KISSAT" else selected,
                           source, seed, remaining)
    if row["status"].startswith("UNSAT"):
        raise RuntimeError(f"{selected} returned UNSAT for a witness-checked SAT case")
    elapsed = time.monotonic() - started
    if elapsed > CAP:
        row.update(status="UNKNOWN", verified=False, php_math_certified=False)
    row.update(arm=arm, group=source["group"], variant=source["variant"],
               tier=source["tier"], chosen_solver=selected, route_s=routing_s,
               operator=operator, e2e_s=round(elapsed, 6), cap_s=CAP)
    return B.with_metrics(row, CAP)


def benchmark(root, run_seed):
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    sources = collect(root, run_seed)
    pairs = {"train": [], "validation": []}
    extraction = {group: [] for group in VARIANTS}
    with (root / "screen.jsonl").open("w") as log:
        for source in sources:
            if source["split"] == "holdout":
                continue
            started = time.monotonic()
            features = F.extract(source["path"])
            features["feature_extract_s"] = time.monotonic() - started
            extraction[source["group"]].append(features["feature_extract_s"])
            arms = ARMS[source["id"] % len(ARMS):] + ARMS[:source["id"] % len(ARMS)]
            rows = {arm: trial(arm, source, 17) for arm in arms}
            for row in rows.values():
                print(json.dumps(row), file=log, flush=True)
            pairs[source["split"]].append((features, rows))
    policies = {mode: L.fit(pairs["train"], pairs["validation"], mode,
                           extra_arms=("MATH14", "REDUCE_KISSAT") if mode == "HYBRID" else ("MATH14",))
                for mode in ("NATIVE", "HYBRID")}
    (root / "policy.json").write_text(json.dumps(policies, indent=2))
    L.emit("LTM12_DYNAMIC_POLICY", policies)
    rows = []
    test = ROUTERS + ARMS
    with (root / "holdout.jsonl").open("w") as log:
        for source in sources:
            if source["split"] != "holdout":
                continue
            for rep, seed in enumerate((17, 29)):
                shift = (source["id"] + rep) % len(test)
                for arm in test[shift:] + test[:shift]:
                    row = trial(arm, source, seed, policies.get(arm.removeprefix("LTM12_")))
                    rows.append(row)
                    print(json.dumps(row), file=log, flush=True)
    totals = B.metrics(rows, CAP, test)
    best = min(REFERENCES, key=lambda arm: totals[arm]["PAR2_verified_s"])
    report = dict(run_seed=run_seed, corpus="synthetic planted SAT", totals=totals, best_reference=best,
                  policies=policies, cap_s=CAP,
                  reference_over_candidate={arm: totals[best]["PAR2_verified_s"] /
                                            totals[arm]["PAR2_verified_s"]
                                            for arm in (*ROUTERS, "REDUCE_KISSAT", "MATH14")},
                  verified_without_search={arm: sum(r["arm"] == arm and r["operator"] is not None
                                                    and r["verified"] for r in rows)
                                           for arm in (*ROUTERS, "REDUCE_KISSAT")},
                  by_group={group: B.metrics([r for r in rows if r["group"] == group], CAP, test)
                            for group in VARIANTS},
                  median_feature_ms={group: round(1000 * statistics.median(times), 3)
                                     for group, times in extraction.items()})
    (root / "report.json").write_text(json.dumps(report, indent=2))
    L.emit("LTM12_DYNAMIC_FINAL", report)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            print(f"Replay seed: `{run_seed}`. 48 train, 20 validation, 32 holdout ×2. Synthetic SAT.",
                  file=summary)
            print("\n| Arm | Verified | PAR2 (s) |\n|---|---:|---:|", file=summary)
            for arm, metrics in totals.items():
                print(f'| {arm} | {metrics["SAT_verified"]}/{metrics["trials"]} | '
                      f'{metrics["PAR2_verified_s"]:.6f} |', file=summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("ltm12_dynamic"))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.SystemRandom().getrandbits(64)
    if args.selftest:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = collect(root / "first", seed)
            replay = collect(root / "replay", seed)
            fresh = collect(root / "fresh", seed + 1)
            assert [s["sha256"] for s in first] == [s["sha256"] for s in replay]
            assert not ({s["sha256"] for s in first} & {s["sha256"] for s in fresh})
            for group in VARIANTS:
                variants = [{s["variant"] for s in first if s["group"] == group and s["split"] == split}
                            for split in SPLITS]
                assert len(set.union(*variants)) == len(SPLITS)
            for source in first:
                expected = {"implications": "2sat_scc", "parity": "gf2_elimination"}.get(source["group"])
                assert shortcut(Path(source["path"])) == expected, source
            incomplete = root / "incomplete.cnf"
            incomplete.write_text("p cnf 3 1\n1 2 3 0\n")
            assert shortcut(incomplete) is None
            contradiction = root / "contradiction.cnf"
            contradiction.write_text("p cnf 1 2\n1 0\n-1 0\n")
            assert shortcut(contradiction) is None
            print(f"LTM12_DYNAMIC_SELFTEST_PASS {len(first)} verified SAT examples")
    else:
        benchmark(args.root, seed)
