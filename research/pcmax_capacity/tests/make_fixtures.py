"""Small independent native-guard fixtures with exact CNF witnesses/oracles."""
from functools import lru_cache
from itertools import combinations, product
from pathlib import Path
import hashlib
import json
import random

ROOT = Path(__file__).resolve().parent


def build_scheduling(durations, machines, capacity):
    groups = [[j * machines + m + 1 for m in range(machines)]
              for j in range(len(durations))]
    clauses = []
    for group in groups:
        clauses.append(tuple(group))
        clauses.extend((-a, -b) for a, b in combinations(group, 2))
    next_variable = len(durations) * machines
    graphs = []
    for m in range(machines):
        bound = capacity[m] if isinstance(capacity, list) else capacity
        next_variable += 1
        true = next_variable
        next_variable += 1
        false = next_variable
        unique, transitions = {}, []

        @lru_cache(None)
        def node(j, load):
            nonlocal next_variable
            if load > bound:
                return false
            if j == len(durations):
                return true
            low = node(j + 1, load)
            high = node(j + 1, load + durations[j])
            if low == high:
                return low
            selector = groups[j][m]
            key = selector, low, high
            if key not in unique:
                next_variable += 1
                parent = next_variable
                unique[key] = parent
                clauses.extend(((selector, -parent, low),
                                (-selector, -parent, high)))
                transitions.append((parent, selector, low, high))
            return unique[key]

        root = node(0, 0)
        clauses.extend(((root,), (true,), (-false,)))
        graphs.append(dict(root=root, true=true, false=false,
                           transitions=transitions))
    return next_variable, clauses, groups, graphs


def extend_horn(nvars, clauses, selectors):
    """Least Horn model after fixing all assignment variables; no BDD reads."""
    residual = []
    for clause in clauses:
        if any(abs(l) in selectors and selectors[abs(l)] == (l > 0)
               for l in clause):
            continue
        rem = [l for l in clause if abs(l) not in selectors]
        positive = [l for l in rem if l > 0]
        assert len(positive) <= 1
        residual.append(({abs(l) for l in rem if l < 0},
                         positive[0] if positive else None))
    true = set()
    changed = True
    while changed:
        changed = False
        for body, head in residual:
            if not body <= true:
                continue
            if head is None:
                return None
            if head not in true:
                true.add(head)
                changed = True
    true.update(v for v, value in selectors.items() if value)
    assert all(any((abs(l) in true) == (l > 0) for l in c) for c in clauses)
    return [v if v in true else -v for v in range(1, nvars + 1)]


def oracle(nvars, clauses, groups):
    examined = 0
    for choices in product(*(range(len(group)) for group in groups)):
        examined += 1
        selected = {v: k == choices[j]
                    for j, group in enumerate(groups) for k, v in enumerate(group)}
        model = extend_horn(nvars, clauses, selected)
        if model is not None:
            return dict(status="SAT", assignments_checked=examined, model=model)
    return dict(status="UNSAT", assignments_checked=examined)


def write_case(name, nvars, clauses, groups, metadata):
    raw = (f"p cnf {nvars} {len(clauses)}\n" +
           "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)).encode()
    dest = ROOT / "fixtures" / (name + ".cnf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    truth = oracle(nvars, clauses, groups)
    return dict(file=str(dest), source_sha256=hashlib.sha256(raw).hexdigest(),
                groups=groups, variables=nvars, clauses=len(clauses),
                oracle=truth, **metadata)


def main():
    rows = []
    cases = [([6, 6, 6], 2, 10), ([6, 4, 6, 4], 2, 10),
             ([3, 3, 3, 3, 3], 2, 8), ([6, 6, 6, 1], 2, 10),
             ([4, 3, 3, 4, 3, 3], 2, 10), ([2, 4, 4, 3, 7], 3, 8),
             ([6, 6, 6, 1], 2, [10, 12]),
             ([6, 6, 6, 6, 6, 1], 3, [10, 10, 12])]
    rng = random.Random(22062026)
    while len(cases) < 24:
        n, machines = rng.randrange(3, 7), rng.randrange(2, 4)
        durations = [rng.randrange(1, 10) for _ in range(n)]
        capacity = rng.randrange(max(durations), sum(durations))
        cases.append((durations, machines, capacity))
    for index, (durations, machines, capacity) in enumerate(cases):
        nvars, clauses, groups, _ = build_scheduling(durations, machines, capacity)
        rows.append(write_case(f"schedule-{index:02d}", nvars, clauses, groups,
                               dict(durations=durations, machine_count=machines,
                                    capacity=capacity, kind="scheduling")))
    for index in (0, 1):
        durations, machines, capacity = cases[index]
        nvars, clauses, groups, _ = build_scheduling(durations, machines, capacity)
        renamed = list(range(1, nvars + 1))
        rng.shuffle(renamed)
        renamed = [0] + renamed
        clauses = [tuple(renamed[abs(l)] if l > 0 else -renamed[abs(l)] for l in c)
                   for c in clauses]
        rng.shuffle(clauses)
        groups = [[renamed[v] for v in group] for group in groups]
        rows.append(write_case(f"renamed-shuffled-{index}", nvars, clauses, groups,
                               dict(durations=durations, machine_count=machines,
                                    capacity=capacity, kind="scheduling",
                                    variable_and_clause_permutation=True)))
    nvars, clauses, groups, graphs = build_scheduling([6, 6, 6], 2, 10)
    root = graphs[0]["root"]
    root_node = next(t for t in graphs[0]["transitions"] if t[0] == root)
    removals = {
        "missing-root-unit": (root,),
        "missing-false-terminal-unit": (-graphs[0]["false"],),
        "missing-root-low-branch": (root_node[1], -root, root_node[2]),
    }
    for name, remove in removals.items():
        mutant = list(clauses)
        mutant.remove(remove)
        row = write_case(name, nvars, mutant, groups,
                         dict(kind="missing-prerequisite", removed_clause=remove))
        assert row["oracle"]["status"] == "SAT", name
        rows.append(row)
    manifest = dict(cases=rows, count=len(rows),
                    total_selector_assignments_checked=sum(r["oracle"]["assignments_checked"] for r in rows))
    (ROOT / "fixtures.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(dict(cases=len(rows),
                          sat=sum(r["oracle"]["status"] == "SAT" for r in rows),
                          unsat=sum(r["oracle"]["status"] == "UNSAT" for r in rows),
                          assignments_checked=manifest["total_selector_assignments_checked"])))


if __name__ == "__main__":
    main()
