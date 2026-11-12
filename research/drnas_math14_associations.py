#!/usr/bin/env python3
"""Compare adding XOR consequences, substitution, and implication equivalences."""
import argparse
import collections
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time

from drnas_ltm12_dynamic import B, implication_components
from drnas_ltm9_independent_cert import parse_dimacs

CAP = 2.0
REFERENCES = ("Kissat", "CaDiCaL", "CryptoMiniSat")
METHODS = ("MATH14_ADD", "MATH14_SUBST", "MATH14_SUBST_SCC", "MATH14_CASCADE")
ARMS = REFERENCES + METHODS
GROUPS = ("shared_3sat", "shared_exactly_one", "implication_cycles", "second_pass",
          "disjoint", "incomplete")


def xor_links(clauses):
    masks = collections.defaultdict(int)
    for clause in clauses:
        if len(clause) != 3 or len(set(map(abs, clause))) != 3:
            continue
        ordered = sorted(clause, key=abs)
        signs = sum(1 << i for i, literal in enumerate(ordered) if literal < 0)
        masks[tuple(map(abs, ordered))] |= 1 << signs
    rows = [(triple, rhs) for triple, mask in sorted(masks.items())
            for forbidden, rhs in ((0x69, 1), (0x96, 0)) if mask & forbidden == forbidden]
    if len(rows) > 256:
        return len(rows), []
    anchors = {}
    links = set()
    for (a, b, c), rhs in rows:
        for shared, other in (((a, b), c), ((a, c), b), ((b, c), a)):
            v, bit = anchors.setdefault(shared, (other, rhs))
            if v != other:
                links.add((*sorted((v, other)), bit ^ rhs))
    return len(rows), sorted(links)[:64]


def binary_clauses(links):
    for a, b, rhs in links:
        yield (a, b if rhs else -b)
        yield (-a, -b if rhs else b)


class Equivalences:
    def __init__(self, n):
        self.parents = list(range(n + 1))
        self.parity = [0] * (n + 1)
        self.size = [1] * (n + 1)

    def find(self, v):
        if self.parents[v] != v:
            root, bit = self.find(self.parents[v])
            self.parents[v] = root
            self.parity[v] ^= bit
        return self.parents[v], self.parity[v]

    def join(self, a, b, rhs):
        root_a, bit_a = self.find(a)
        root_b, bit_b = self.find(b)
        between = rhs ^ bit_a ^ bit_b
        if root_a == root_b:
            if between:
                raise RuntimeError("inconsistent implied equivalences")
            return False
        if self.size[root_a] < self.size[root_b]:
            root_a, root_b = root_b, root_a
        self.parents[root_b] = root_a
        self.parity[root_b] = between
        self.size[root_a] += self.size[root_b]
        return True


def bridge_signal(clauses, links):
    edges = collections.defaultdict(set)
    for clause in clauses:
        if len(clause) == 2:
            a, b = clause
            edges[-a].add(b)
            edges[-b].add(a)
    for a, b, rhs in links:
        signed_b = -b if rhs else b
        for start, end in ((a, signed_b), (signed_b, a)):
            if any(abs(mid) not in (a, b) and end in edges.get(mid, ())
                   for mid in edges.get(start, ())):
                return True
    return False


def single_pass(n, clauses, method):
    started = time.monotonic()
    row_count, links = xor_links(clauses)
    graph_worth_trying = (bool(links) and method in ("MATH14_SUBST_SCC", "MATH14_CASCADE")
                         and bridge_signal(clauses, links))
    stats = dict(xor_rows=row_count, xor_links=len(links), added_binaries=0,
                 scc_merges=0, new_units=0, removed_variables=0, removed_clauses=0,
                 recognition_s=time.monotonic() - started, scc_triggered=int(graph_worth_trying))
    if not links:
        return n, clauses, None, stats
    if method == "MATH14_ADD" or graph_worth_trying:
        enriched = set(clauses)
        additions = {tuple(sorted(clause)) for clause in binary_clauses(links)} - enriched
        stats["added_binaries"] = len(additions)
        if method == "MATH14_ADD":
            return n, sorted(enriched | additions), None, stats
    eq = Equivalences(n)
    for link in links:
        eq.join(*link)
    if graph_worth_trying:
        binary = [clause for clause in enriched | additions if 1 <= len(clause) <= 2]
        components = implication_components(n, binary)
        reps = {}
        for node, component in enumerate(components):
            representative = reps.setdefault(component, node)
            stats["scc_merges"] += eq.join(node // 2 + 1, representative // 2 + 1,
                                          (node ^ representative) & 1)
    compact = {}
    mapping = {}
    for v in range(1, n + 1):
        root, bit = eq.find(v)
        index = compact.setdefault(root, len(compact) + 1)
        mapping[v] = -index if bit else index
    reduced = set()
    for clause in clauses:
        mapped = {mapping[abs(lit)] * (1 if lit > 0 else -1) for lit in clause}
        if any(-lit in mapped for lit in mapped):
            continue
        reduced.add(tuple(sorted(mapped)))
    stats.update(removed_variables=n - len(compact), removed_clauses=len(clauses) - len(reduced),
                 new_units=sum(len(c) == 1 for c in reduced) - sum(len(c) == 1 for c in clauses))
    return len(compact), sorted(reduced), mapping, stats


def transform(n, clauses, method):
    new_n, reduced, mapping, stats = single_pass(n, clauses, method)
    stats["second_pass_merges"] = 0
    if method != "MATH14_CASCADE" or mapping is None or new_n == n:
        return new_n, reduced, mapping, stats
    final_n, final, second, followup = single_pass(new_n, reduced, method)
    stats["recognition_s"] += followup["recognition_s"]
    if second is None or final_n == new_n:
        return new_n, reduced, mapping, stats
    combined = {v: second[abs(lit)] * (1 if lit > 0 else -1) for v, lit in mapping.items()}
    stats.update(second_pass_merges=new_n - final_n, removed_variables=n - final_n,
                 removed_clauses=len(clauses) - len(final),
                 new_units=sum(len(c) == 1 for c in final) - sum(len(c) == 1 for c in clauses),
                 scc_merges=stats["scc_merges"] + followup["scc_merges"])
    return final_n, final, combined, stats


def dimacs(n, clauses):
    return f"p cnf {n} {len(clauses)}\n" + "".join(
        " ".join(map(str, clause)) + " 0\n" for clause in clauses)


def witness(values):
    return "v " + " ".join(str(v if value else -v) for v, value in values.items()) + " 0\n"


def generate(group, seed):
    rng = random.Random(seed)
    count = rng.randrange(64, 113)
    core = list(range(1, count + 1))
    model = {v: bool(rng.getrandbits(1)) for v in core}
    clauses = []

    def new_var(value):
        v = len(model) + 1
        model[v] = value
        return v

    def append_xor(triple):
        rhs = sum(model[v] for v in triple) % 2
        forbidden = [bits for bits in itertools.product((0, 1), repeat=3)
                     if sum(bits) % 2 != rhs]
        if group == "incomplete":
            forbidden.pop(rng.randrange(len(forbidden)))
        clauses.extend(tuple(-v if bit else v for v, bit in zip(triple, bits))
                       for bits in forbidden)

    blocks = [core[i:i+4] for i in range(0, count, 4)]
    if group == "shared_exactly_one":
        for block in blocks:
            choice = rng.choice(block)
            model.update({v: v == choice for v in block})
    aliases = {}
    domain = core if group != "disjoint" else [new_var(bool(rng.getrandbits(1))) for _ in core]
    for target in rng.sample(domain, count // 2):
        a, b = (new_var(bool(rng.getrandbits(1))) for _ in range(2))
        alias = new_var(bool(rng.getrandbits(1)))
        signed_alias = alias if model[target] == model[alias] else -alias
        aliases[target] = signed_alias
        append_xor((a, b, target))
        append_xor((a, b, alias))
        if group == "implication_cycles":
            bridge = new_var(model[target])
            clauses.extend(((-signed_alias, bridge), (-bridge, target)))
        if group == "second_pass":
            shared, left, right = (new_var(bool(rng.getrandbits(1))) for _ in range(3))
            append_xor((target, shared, left))
            append_xor((alias, shared, right))

    def use_alias(lit):
        if abs(lit) in aliases and rng.getrandbits(1):
            return aliases[abs(lit)] * (1 if lit > 0 else -1)
        return lit

    if group == "shared_exactly_one":
        for block in blocks:
            clauses.append(tuple(use_alias(v) for v in block))
            clauses.extend((use_alias(-a), use_alias(-b)) for a, b in itertools.combinations(block, 2))
    else:
        for _ in range(round(count * 4.2)):
            clause = [v * rng.choice((-1, 1)) for v in rng.sample(core, 3)]
            if not any(model[abs(lit)] == (lit > 0) for lit in clause):
                i = rng.randrange(3)
                clause[i] = -clause[i]
            clauses.append(tuple(map(use_alias, clause)))
    perm = rng.sample(range(1, len(model) + 1), len(model))
    labels = {v: p * rng.choice((-1, 1)) for v, p in zip(model, perm)}
    shuffled = sorted({tuple(sorted(labels[abs(lit)] * (1 if lit > 0 else -1) for lit in clause))
                       for clause in clauses})
    rng.shuffle(shuffled)
    values = {abs(labels[v]): value ^ (labels[v] < 0) for v, value in model.items()}
    return len(model), shuffled, witness(values)


def solve(source, arm, seed, scratch):
    started = time.monotonic()
    original = Path(source["path"])
    if hashlib.sha256(original.read_bytes()).hexdigest() != source["sha256"]:
        raise RuntimeError("source SHA changed")
    original_n = source["variables"]
    target = original
    mapping = None
    stats = {}
    if arm in METHODS:
        reduction_started = time.monotonic()
        data = parse_dimacs(original)
        parse_s = time.monotonic() - reduction_started
        n, clauses, mapping, stats = transform(data["n"], data["clauses"], arm)
        if stats["xor_links"]:
            target = scratch / "reduced.cnf"
            target.write_text(dimacs(n, clauses))
        stats["recognition_s"] += parse_s
        stats["rewrite_s"] = max(0.0, time.monotonic() - reduction_started - stats["recognition_s"])
    remaining = CAP - (time.monotonic() - started) - .10
    backend = "CaDiCaL" if arm in METHODS else arm
    status = "UNKNOWN"
    if remaining > 0:
        try:
            proc = subprocess.run(B.command(backend, target, seed, remaining), capture_output=True,
                                  text=True, timeout=remaining)
        except subprocess.TimeoutExpired:
            proc = None
        if proc is not None and proc.returncode == 10:
            answer = proc.stdout
            if mapping:
                values = {}
                for line in answer.splitlines():
                    if line.startswith(("v ", "v\t")):
                        for lit in map(int, line[1:].split()):
                            if not lit:
                                continue
                            if abs(lit) in values and values[abs(lit)] != (lit > 0):
                                raise RuntimeError("contradictory solver witness")
                            values[abs(lit)] = lit > 0
                answer = witness({v: values.get(abs(lit), False) ^ (lit < 0)
                                  for v, lit in mapping.items()})
            if not B.sat_witness_valid(original, original_n, answer):
                raise RuntimeError(f"invalid original-CNF witness for {arm}, case {source['id']}")
            status = "SAT_VERIFIED"
        elif proc is not None and proc.returncode != 0:
            raise RuntimeError(f"{backend} returned {proc.returncode} for known SAT case {source['id']}")
    elapsed = time.monotonic() - started
    if elapsed > CAP:
        status = "UNKNOWN"
    return B.with_metrics(dict(id=source["id"], group=source["group"], arm=arm, seed=seed,
                               status=status, e2e_s=round(elapsed, 6),
                               **stats), CAP)


def run(root, run_seed):
    root.mkdir()
    cases = root / "cases"
    cases.mkdir()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    rng = random.Random(run_seed)
    sources = []
    seen = set()
    for group in GROUPS:
        for _ in range(8):
            seed = rng.getrandbits(64)
            n, clauses, model = generate(group, seed)
            raw = dimacs(n, clauses)
            sha = hashlib.sha256(raw.encode()).hexdigest()
            if sha in seen:
                raise RuntimeError("duplicate source")
            seen.add(sha)
            path = cases / f"{sha}.cnf"
            path.write_text(raw)
            if not B.sat_witness_valid(path, n, model):
                raise RuntimeError("invalid generator witness")
            sources.append(dict(id=len(sources), group=group, seed=seed, path=str(path),
                                sha256=sha, variables=n, clauses=len(clauses)))
    (root / "manifest.json").write_text(json.dumps(dict(seed=run_seed, sources=sources), indent=2))
    rows = []
    with tempfile.TemporaryDirectory() as tmp, (root / "trials.jsonl").open("w") as output:
        for source in sources:
            for rep, seed in enumerate((17, 29, 43)):
                shift = (source["id"] + rep) % len(ARMS)
                for arm in ARMS[shift:] + ARMS[:shift]:
                    row = solve(source, arm, seed, Path(tmp))
                    rows.append(row)
                    print(json.dumps(row), file=output, flush=True)
    totals = B.metrics(rows, CAP, ARMS)
    best = min(REFERENCES, key=lambda arm: totals[arm]["PAR2_verified_s"])
    groups = {}
    for group in GROUPS:
        matched = [r for r in rows if r["group"] == group]
        effects = {}
        for arm in METHODS:
            arm_rows = [r for r in matched if r["arm"] == arm]
            effects[arm] = {key: sum(r[key] for r in arm_rows) / len(arm_rows)
                            for key in ("xor_rows", "xor_links", "added_binaries", "removed_variables",
                                        "removed_clauses", "scc_merges", "scc_triggered",
                                        "second_pass_merges", "recognition_s", "rewrite_s")}
        groups[group] = dict(metrics=B.metrics(matched, CAP, ARMS), mean_effects=effects)
    report = dict(seed=run_seed, sources=len(sources), repetitions=3, cap_s=CAP,
                  corpus="synthetic planted SAT", best_reference=best, totals=totals, groups=groups)
    (root / "report.json").write_text(json.dumps(report, indent=2))
    print("MATH14_ASSOCIATIONS_FINAL", json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--root", type=Path, default=Path("math14_associations"))
    args = parser.parse_args()
    run(args.root, args.seed if args.seed is not None else random.SystemRandom().getrandbits(64))
