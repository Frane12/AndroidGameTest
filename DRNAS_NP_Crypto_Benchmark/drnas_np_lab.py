#!/usr/bin/env python3
"""DRNAS NP Lab 0.2 - blind, exact SAT representation experiment.

No third-party dependencies. Python 3.9+.
Input is ONLY a CNF: the solver does not receive how it was generated.
This is an educational research prototype, NOT a new complexity result.

Usage:
  python drnas_np_lab.py test
  python drnas_np_lab.py demo
  python drnas_np_lab.py benchmark --budget 0.30
  python drnas_np_lab.py solve example.cnf
"""
import argparse
import csv
import json
import random
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from itertools import combinations, product
from pathlib import Path


@dataclass
class Result:
    status: str                 # SAT, UNSAT, LIMIT
    method: str
    seconds: float
    nodes: int
    rank: int = 0
    free: int = 0
    xor_found: int = 0
    assignment: list = None
    interface: int = 0
    resolved_pairs: int = 0


def normalize(n, clauses):
    """Canonicalize and remove tautologies. Keep an empty clause (UNSAT)."""
    out, seen = [], set()
    for clause in clauses:
        literals = set(int(x) for x in clause)
        if 0 in literals or any(abs(x) > n for x in literals):
            raise ValueError('Illegal variable or zero inside a clause')
        if any(-x in literals for x in literals):
            continue
        row = tuple(sorted(literals, key=lambda x: (abs(x), x < 0)))
        if row not in seen:
            out.append(row)
            seen.add(row)
    return out


def check(clauses, values):
    return all(any((values[abs(lit) - 1] == (lit > 0)) for lit in c)
               for c in clauses)


def read_dimacs(path):
    n = None
    terms, clauses = [], []
    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if line.startswith('%'):
            break  # SATLIB DIMACS EOF; trailing standalone 0 must NOT create empty clause
        if not line or line.startswith('c'):
            continue
        if line.startswith('p'):
            parts = line.split()
            if len(parts) < 4 or parts[1] != 'cnf':
                raise ValueError('Expected p cnf N M')
            n = int(parts[2])
            continue
        for word in line.split():
            val = int(word)
            if val == 0:
                clauses.append(tuple(terms))
                terms = []
            else:
                terms.append(val)
    if n is None or terms:
        raise ValueError('Missing DIMACS header or clause terminator')
    return n, normalize(n, clauses)


def write_dimacs(path, n, clauses):
    with open(path, 'w', encoding='utf-8') as file:
        file.write(f'c DRNAS NP Lab generated test\np cnf {n} {len(clauses)}\n')
        for clause in clauses:
            file.write(' '.join(map(str, clause)) + ' 0\n')


def xor_to_cnf(vars3, rhs):
    """The four length-three clauses forbidding the wrong parity."""
    out = []
    for bits in product((0, 1), repeat=3):
        if (sum(bits) & 1) != rhs:
            out.append(tuple(-v if bit else v for v, bit in zip(vars3, bits)))
    return out


def detect_xor3(clauses):
    """Recognize exact XOR triple quartets using ONLY the CNF clauses.

    Every clause forbids exactly one assignment to its variable triple.
    The four assignments of one parity must all be forbidden to imply the
    opposite XOR parity. Any remaining clauses are preserved verbatim.
    """
    by_vars = defaultdict(dict)
    for idx, clause in enumerate(clauses):
        if len(clause) != 3 or len(set(map(abs, clause))) != 3:
            continue
        vars3 = tuple(sorted(abs(l) for l in clause))
        forbidden = sum(1 << i for i, v in enumerate(vars3) if -v in clause)
        by_vars[vars3][forbidden] = idx
    equations, consumed = [], set()
    for vars3, masks in sorted(by_vars.items()):
        for forbidden_parity in (0, 1):
            group = [mask for mask in range(8)
                     if (mask.bit_count() & 1) == forbidden_parity]
            if all(mask in masks for mask in group):
                equations.append((sum(1 << (v - 1) for v in vars3), 1 - forbidden_parity))
                consumed.update(masks[mask] for mask in group)
    remaining = [c for i, c in enumerate(clauses) if i not in consumed]
    return equations, remaining


def gaussian(equations, n):
    """Sparse GF(2) elimination with Python integer bitsets.
    Each pivot is the LEAST-significant 1-bit of its row. The row may contain
    higher bits, so back substitution proceeds from HIGH to LOW pivots.
    """
    pivots = {}
    for mask, rhs in equations:
        mask, rhs = int(mask), int(rhs)
        while mask:
            pivot = mask & -mask
            if pivot in pivots:
                other_mask, other_rhs = pivots[pivot]
                mask ^= other_mask
                rhs ^= other_rhs
            else:
                pivots[pivot] = (mask, rhs)
                break
        if not mask and rhs:
            return None, n - len(pivots)
    return pivots, n - len(pivots)


def affine_assignment(n, pivots, free_columns, free_state):
    assignment_mask = sum((1 << col) for bit, col in enumerate(free_columns)
                          if (free_state >> bit) & 1)
    for pivot in sorted(pivots, reverse=True):
        row, rhs = pivots[pivot]
        upper_bits = row ^ pivot
        value = rhs ^ ((assignment_mask & upper_bits).bit_count() & 1)
        if value:
            assignment_mask |= pivot
    return [(assignment_mask >> i) & 1 == 1 for i in range(n)]


def solve_affine_enumeration(n, equations, remaining, limit_free=16, deadline=None):
    pivots, free_count = gaussian(equations, n)
    rank = n - free_count
    if pivots is None:
        return 'UNSAT', None, rank, free_count, 0
    if free_count > limit_free:
        return None, None, rank, free_count, 0
    free_columns = [i for i in range(n) if (1 << i) not in pivots]
    checked = 0
    for free_state in range(1 << free_count):
        if deadline is not None and (checked & 255) == 0 and time.perf_counter() > deadline:
            return 'LIMIT', None, rank, free_count, checked
        values = affine_assignment(n, pivots, free_columns, free_state)
        checked += 1
        if check(remaining, values):
            return 'SAT', values, rank, free_count, checked
    return 'UNSAT', None, rank, free_count, checked




def cancel_complementary_pairs(n, clauses, max_rounds=3):
    """Equivalence-preserving local CNF rewriting.

    (C OR z) AND (C OR NOT z) == C, including empty C.
    This detects a pattern obscured by auxiliary Boolean variables.
    The transformation is SOUND even if z occurs in other clauses,
    because the pair of clauses itself is logically identical to C.
    At most max_rounds linear-index passes; intentionally incomplete.
    """
    clauses = list(clauses)
    total = 0
    for _ in range(max_rounds):
        lookup = {}
        for idx, clause in enumerate(clauses):
            for lit in clause:
                key = (tuple(x for x in clause if x != lit), abs(lit))
                cell = lookup.setdefault(key, [None, None])
                cell[0 if lit > 0 else 1] = idx
        eliminated, replacements = set(), []
        for (rest, _), (a, b) in lookup.items():
            if a is not None and b is not None and a not in eliminated and b not in eliminated:
                eliminated.add(a); eliminated.add(b)
                replacements.append(rest)
        if not eliminated:
            break
        total += len(replacements)
        clauses = normalize(n, [c for i,c in enumerate(clauses) if i not in eliminated]
                             + replacements)
    return clauses, total

def solve_interface_enumeration(n, equations, remaining, limit_interface=16, deadline=None):
    """Exact XOR + residual CNF via enumeration of interface assignments.

    Let I be *only* variables appearing in non-XOR clauses. Any CNF model
    restricts to one assignment to I. Conversely, each residual-satisfying
    assignment on I extends to a full model iff the GF(2) equations with
    those fixed bits are consistent. We test each such assignment, so
    UNSAT is sound only after exhaustive enumeration of the interface.

    Complexity O(2^|I| * (|CNF| + GF2_elim)) -- a structural, not a generic
    polynomial-time guarantee. This is a standard backdoor-style method.
    """
    variables = sorted({abs(lit) for clause in remaining for lit in clause})
    if len(variables) > limit_interface:
        return None, None, 0, len(variables)
    checked = 0
    for state in range(1 << len(variables)):
        if deadline is not None and time.perf_counter() > deadline:
            return 'LIMIT', None, checked, len(variables)
        interface_bits = {v: bool((state >> idx) & 1)
                          for idx, v in enumerate(variables)}
        if not all(any(interface_bits[abs(lit)] == (lit > 0) for lit in clause)
                   for clause in remaining):
            continue
        checked += 1
        fixed_rows = [(1 << (v - 1), int(interface_bits[v])) for v in variables]
        pivots, _ = gaussian(equations + fixed_rows, n)
        if pivots is not None:
            free_columns = [i for i in range(n) if (1 << i) not in pivots]
            values = affine_assignment(n, pivots, free_columns, 0)
            assert check(remaining, values), 'Internal error: interface model not preserved'
            return 'SAT', values, checked, len(variables)
    return 'UNSAT', None, checked, len(variables)

def solve_horn(n, clauses):
    """Linear-time forward chaining for clauses with <= one positive literal."""
    watchers = [[] for _ in range(n)]
    left, heads, agenda = [], [], deque()
    values = [False] * n
    for idx, clause in enumerate(clauses):
        positive = [l - 1 for l in clause if l > 0]
        if len(positive) > 1:
            raise ValueError('Not a Horn formula')
        body = [-l - 1 for l in clause if l < 0]
        heads.append(positive[0] if positive else None)
        left.append(len(body))
        for v in body:
            watchers[v].append(idx)
        if not body:
            if heads[idx] is None:
                return 'UNSAT', None
            agenda.append(heads[idx])
    while agenda:
        v = agenda.popleft()
        if values[v]:
            continue
        values[v] = True
        for idx in watchers[v]:
            left[idx] -= 1
            if left[idx] == 0:
                if heads[idx] is None:
                    return 'UNSAT', None
                agenda.append(heads[idx])
    return 'SAT', values


def solve_2sat(n, clauses):
    """Implication graph + Kosaraju SCC, works for unit and empty clauses."""
    if any(len(c) == 0 for c in clauses):
        return 'UNSAT', None
    size = 2 * n
    graph, reverse = [[] for _ in range(size)], [[] for _ in range(size)]
    def node(lit):
        return 2 * (abs(lit) - 1) + (0 if lit > 0 else 1)
    def edge(a, b):
        graph[a].append(b)
        reverse[b].append(a)
    for clause in clauses:
        if len(clause) > 2:
            raise ValueError('Not a 2-SAT formula')
        a = node(clause[0])
        b = node(clause[-1])
        edge(a ^ 1, b)
        edge(b ^ 1, a)
    # Iterative Kosaraju, no recursion-depth dependence.
    visited, order = [False] * size, []
    for start in range(size):
        if visited[start]:
            continue
        visited[start] = True
        stack = [(start, 0)]
        while stack:
            v, idx = stack[-1]
            if idx < len(graph[v]):
                w = graph[v][idx]
                stack[-1] = (v, idx + 1)
                if not visited[w]:
                    visited[w] = True
                    stack.append((w, 0))
            else:
                order.append(v)
                stack.pop()
    component = [-1] * size
    count = 0
    for start in reversed(order):
        if component[start] != -1:
            continue
        component[start] = count
        stack = [start]
        while stack:
            for w in reverse[stack.pop()]:
                if component[w] == -1:
                    component[w] = count
                    stack.append(w)
        count += 1
    values = []
    for i in range(n):
        if component[2 * i] == component[2 * i + 1]:
            return 'UNSAT', None
        values.append(component[2 * i] > component[2 * i + 1])
    return 'SAT', values


class BudgetExceeded(Exception):
    pass


def solve_dpll(n, clauses, deadline=None):
    """Small transparent reference solver; NOT CDCL/industrial-strength SAT."""
    nodes = 0
    def recurse(assign):
        nonlocal nodes
        nodes += 1
        if deadline is not None and time.perf_counter() > deadline:
            raise BudgetExceeded()
        while True:
            updated = False
            unresolved = []
            for clause in clauses:
                unknown = []
                satisfied = False
                for lit in clause:
                    value = assign[abs(lit) - 1]
                    if value is None:
                        unknown.append(lit)
                    elif value == (lit > 0):
                        satisfied = True
                        break
                if satisfied:
                    continue
                if not unknown:
                    return None
                if len(unknown) == 1:
                    unit = unknown[0]
                    idx, value = abs(unit) - 1, unit > 0
                    if assign[idx] is not None and assign[idx] != value:
                        return None
                    if assign[idx] is None:
                        assign[idx] = value
                        updated = True
                else:
                    unresolved.append(unknown)
            if not updated:
                break
        if not unresolved:
            return [False if x is None else x for x in assign]
        scores = defaultdict(int)
        for clause in unresolved:
            for lit in clause:
                if assign[abs(lit) - 1] is None:
                    scores[abs(lit) - 1] += 1
        variable = max(scores, key=scores.get)
        for value in (True, False):
            next_assign = assign.copy()
            next_assign[variable] = value
            out = recurse(next_assign)
            if out is not None:
                return out
        return None
    try:
        result = recurse([None] * n)
        return ('SAT' if result is not None else 'UNSAT'), result, nodes
    except BudgetExceeded:
        return 'LIMIT', None, nodes


def solve(n, input_clauses, mode='auto', budget=0.4, free_limit=18, preprocess_resolve=True):
    """All reported timings cover preparation + mode selection + solve."""
    start = time.perf_counter()
    deadline = start + budget if budget else None
    clauses = normalize(n, input_clauses)
    interface, resolved_pairs = 0, 0
    if mode == 'dpll':
        status, values, nodes = solve_dpll(n, clauses, deadline)
        method, rank, free, found = 'DPLL', 0, n, 0
    elif mode == 'auto':
        found, rank, free, nodes, values = 0, 0, n, 0, None
        if all(len(clause) <= 2 for clause in clauses):
            method = '2-SAT SCC'
            status, values = solve_2sat(n, clauses)
        elif all(sum(lit > 0 for lit in clause) <= 1 for clause in clauses):
            method = 'Horn'
            status, values = solve_horn(n, clauses)
        else:
            # Cheap representation-selection gate: 4+-CNF is a possible
            # sign of clause splitting. On native 3-CNF skip resolution
            # overhead; this is a heuristic, not an equivalence claim.
            consider_resolution = preprocess_resolve and any(len(c) > 3 for c in clauses)
            work, resolved_pairs = (cancel_complementary_pairs(n, clauses)
                                    if consider_resolution else (clauses, 0))
            equations, remaining = detect_xor3(work)
            found = len(equations)
            status = None
            if found:
                pivots, free = gaussian(equations, n)
                rank = n - free
                interface = len({abs(l) for c in remaining for l in c})
                if pivots is None:
                    status, values = 'UNSAT', None
                    method = 'GF(2) contradiction'
                elif not remaining:
                    cols = [i for i in range(n) if (1 << i) not in pivots]
                    status, values = 'SAT', affine_assignment(n, pivots, cols, 0)
                    method = 'GF(2) direct'
                elif interface <= free and interface <= free_limit:
                    status, values, nodes, interface = solve_interface_enumeration(
                        n, equations, remaining, free_limit, deadline)
                    method = 'GF(2) + interface enumeration'
                elif free <= free_limit:
                    status, values, rank, free, nodes = solve_affine_enumeration(
                        n, equations, remaining, free_limit, deadline)
                    method = 'GF(2) + affine enumeration'
            if status is None:
                method = 'DPLL fallback'
                status, values, nodes = solve_dpll(n, clauses, deadline)
            if resolved_pairs:
                method += f' + {resolved_pairs} resolution pairs'
    else:
        raise ValueError('mode must be auto or dpll')
    if status == 'SAT' and not check(clauses, values):
        raise AssertionError('Solver returned an INVALID satisfying assignment')
    return Result(status, method, time.perf_counter() - start,
                  nodes, rank, free, found, values, interface, resolved_pairs)


def random_3sat(n, m, rng, planted=None):
    clauses = []
    for _ in range(m):
        vars3 = rng.sample(range(1, n + 1), 3)
        clause = tuple(v if rng.randrange(2) else -v for v in vars3)
        if planted is not None and not check([clause], planted):
            lit_index = rng.randrange(3)
            clause = tuple(-lit if j == lit_index else lit
                           for j, lit in enumerate(clause))
        clauses.append(clause)
    rng.shuffle(clauses)
    return normalize(n, clauses)


def xor_instance(n, m, rng, sat, extra=0):
    plant = [bool(rng.randrange(2)) for _ in range(n)]
    while True:
        groups = [tuple(sorted(rng.sample(range(1, n + 1), 3)))
                  for _ in range(m)]
        if len(set(groups)) < m:
            continue
        equations = []
        for group in groups:
            rhs = (sum(plant[x - 1] for x in group) & 1) if sat else rng.randrange(2)
            equations.append((sum(1 << (x - 1) for x in group), rhs))
        pivots, free = gaussian(equations, n)
        if sat or pivots is None:
            break
    clauses = [c for vars3, rhs in zip(groups, (rhs for _, rhs in equations))
               for c in xor_to_cnf(vars3, rhs)]
    if sat and extra:
        clauses += random_3sat(n, extra, rng, planted=plant)
    rng.shuffle(clauses)
    return normalize(n, clauses)


def little_original():
    eq = [((1,2,3),1), ((3,4,5),0), ((2,5,6),1),
          ((4,6,7),0), ((1,7,8),1)]
    extra = [(1,2,4), (-3,5,6), (-7,2,-5), (4,-6,5)]
    cnf = [clause for group, rhs in eq for clause in xor_to_cnf(group, rhs)] + extra
    random.Random(20261031).shuffle(cnf)  # Unlabeled input for the analyzer.
    return 8, cnf


def test_suite():
    rng = random.Random(20261031)
    # Exhaustively compare with ground-truth brute force for varied small instances.
    cases = 0
    for n in range(3, 10):
        for _ in range(55):
            shape = rng.randrange(5)
            if shape == 0:
                clauses = random_3sat(n, rng.randrange(1, 22), rng)
            elif shape == 1:
                clauses = xor_instance(n, min(n, len(list(combinations(range(n), 3)))), rng,
                                       sat=True)
            elif shape == 2:
                clauses = [tuple(rng.sample(range(1, n + 1), 2)) for _ in range(15)]
                clauses = [tuple(l if rng.randrange(2) else -l for l in c) for c in clauses]
            elif shape == 3:
                clauses = [tuple([-v for v in rng.sample(range(1, n+1), rng.randrange(0, 3))]
                                 + [rng.randrange(1, n+1)]) for _ in range(10)]
            else:
                clauses = [tuple((v if rng.randrange(2) else -v)
                                 for v in rng.sample(range(1,n+1), rng.randrange(0,4)))
                           for _ in range(18)]
            clauses = normalize(n, clauses)
            expected = any(check(clauses, bits) for bits in product((False, True), repeat=n))
            actual = solve(n, clauses, budget=None, free_limit=20)
            baseline = solve(n, clauses, mode='dpll', budget=None)
            assert actual.status == ('SAT' if expected else 'UNSAT'), (n, clauses, actual)
            assert baseline.status == actual.status
            cases += 1
    # Explicit malformed / contradictory parity checks.
    cnf = xor_to_cnf((1,2,3), 0) + xor_to_cnf((1,2,3), 1)
    assert solve(3, cnf).status == 'UNSAT'
    n, clauses = little_original()
    auto = solve(n, clauses)
    assert auto.status == 'SAT' and auto.xor_found == 5 and auto.rank == 5
    count = sum(check(clauses, x) for x in product((False, True), repeat=n))
    assert count == 4
    print(f'PASS: {cases} random small CNFs + contradictory XOR + 24-clause regression.')


def benchmarks(budget, outfile=None):
    rng = random.Random(20261031)
    specs = [
        ('mixed_xor_sat', 24, 20, True, 8),
        ('mixed_xor_sat', 32, 29, True, 8),
        ('mixed_xor_sat', 80, 76, True, 8),
        ('xor_unsat', 24, 32, False, 0),
        ('xor_unsat', 40, 49, False, 0),
        ('xor_unsat', 80, 82, False, 0),
        ('xor_unsat', 120, 122, False, 0),
        ('random_3sat', 18, 74, None, 0),
        ('random_3sat', 24, 98, None, 0),
        ('random_2sat', 70, 200, None, 0),
        ('random_horn', 70, 200, None, 0),
    ]
    records = []
    for family, n, m, sat, extra in specs:
        for case in range(3):
            if family in ('mixed_xor_sat', 'xor_unsat'):
                clauses = xor_instance(n, m, rng, sat, extra)
            elif family == 'random_3sat':
                clauses = random_3sat(n, m, rng)
            elif family == 'random_2sat':
                clauses = [tuple((v if rng.randrange(2) else -v)
                          for v in rng.sample(range(1, n+1), 2)) for _ in range(m)]
            else:
                clauses = []
                for _ in range(m):
                    vars3 = rng.sample(range(1, n+1), rng.randrange(1,4))
                    positive = rng.choice([None] + vars3)
                    clauses.append(tuple(v if v == positive else -v for v in vars3))
            clauses = normalize(n, clauses)
            a = solve(n, clauses, budget=budget)
            b = solve(n, clauses, mode='dpll', budget=budget)
            if a.status != 'LIMIT' and b.status != 'LIMIT':
                assert a.status == b.status
            for label, result in (('auto', a), ('baseline', b)):
                records.append({'family': family, 'case': case, 'n': n, 'clauses': len(clauses),
                                'solver': label, 'status': result.status, 'method': result.method,
                                'milliseconds': round(result.seconds * 1000, 4),
                                'nodes_or_affine_candidates': result.nodes,
                                'xor_found': result.xor_found, 'rank': result.rank,
                                'free': result.free})
            print(f'{family:15s} n={n:2} #{case} | '
                  f'auto={a.status:5} {a.seconds*1000:9.2f}ms {a.method:29s} | '
                  f'dpll={b.status:5} {b.seconds*1000:9.2f}ms')
    if outfile:
        prefix = Path(outfile)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        (prefix.with_suffix('.json')).write_text(json.dumps({
            'seed': 20261031, 'time_budget_per_run_seconds': budget,
            'hardware_notice': 'Timing is local to this execution, Python reference DPLL only',
            'cases': records}, ensure_ascii=False, indent=2), encoding='utf-8')
        with prefix.with_suffix('.csv').open('w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    return records



def spectral_profile(n, clauses, max_n=12):
    """Exact Walsh spectrum of f(x)=1 iff the CNF holds; EXPONENTIAL diagnostic.

    It deliberately never influences the solver-selection decision: computing
    all coefficients is not a polynomial-time representation search.
    """
    if n > max_n:
        return {'computed': False, 'reason': f'n={n} > diagnostic limit {max_n}'}
    values = []
    for state in range(1 << n):
        assignment = [bool((state >> i) & 1) for i in range(n)]
        values.append(int(check(clauses, assignment)))
    sat_assignments = sum(values)
    step = 1
    while step < len(values):
        for offset in range(0, len(values), step * 2):
            for i in range(offset, offset + step):
                u, v = values[i], values[i + step]
                values[i], values[i + step] = u + v, u - v
        step <<= 1
    return {
        'computed': True, 'satisfying_assignments': sat_assignments,
        'nonzero_walsh_coefficients': sum(v != 0 for v in values),
        'total_walsh_coefficients': 1 << n,
        'largest_coefficient_abs': max(map(abs, values)),
        'note': 'unnormalized spectrum; exact computation requires 2^n truth values',
    }


def graph_profile(n, clauses):
    """Primal variable graph, component count, and min-fill width UPPER bound.

    This is only a heuristic upper bound on treewidth, NOT the optimum.
    """
    adj = [set() for _ in range(n)]
    for clause in clauses:
        variables = sorted({abs(lit) - 1 for lit in clause})
        for a, b in combinations(variables, 2):
            adj[a].add(b)
            adj[b].add(a)
    unseen = set(range(n))
    components = []
    while unseen:
        start = unseen.pop()
        found = {start}
        stack = [start]
        while stack:
            for w in adj[stack.pop()]:
                if w in unseen:
                    unseen.remove(w)
                    found.add(w)
                    stack.append(w)
        components.append(len(found))
    degrees = [len(a) for a in adj]
    remaining = set(range(n))
    work = [set(a) for a in adj]
    width = 0
    while remaining:
        def fill_cost(v):
            neighbors = sorted(work[v] & remaining)
            edges_missing = sum(1 for a, b in combinations(neighbors, 2)
                                if b not in work[a])
            return edges_missing, len(neighbors), v
        vertex = min(remaining, key=fill_cost)
        neighbors = sorted(work[vertex] & remaining)
        width = max(width, len(neighbors))
        for a, b in combinations(neighbors, 2):
            work[a].add(b)
            work[b].add(a)
        remaining.remove(vertex)
        for a in neighbors:
            work[a].discard(vertex)
    return {
        'components': len(components), 'component_sizes': sorted(components, reverse=True),
        'avg_variable_degree': round(sum(degrees) / n, 3) if n else 0,
        'max_variable_degree': max(degrees, default=0),
        'min_fill_treewidth_upper_bound': width,
    }


def analyze(n, clauses, spectral_limit=12):
    clauses = normalize(n, clauses)
    equations, residual = detect_xor3(clauses)
    pivots, free = gaussian(equations, n)
    lengths = {str(k): sum(len(c) == k for c in clauses)
               for k in sorted({len(c) for c in clauses})}
    return {
        'variables': n, 'clauses': len(clauses), 'clause_lengths': lengths,
        'is_2sat': all(len(c) <= 2 for c in clauses),
        'is_horn': all(sum(lit > 0 for lit in c) <= 1 for c in clauses),
        'recovered_xor_triples': len(equations),
        'xor_equations_consistent': pivots is not None,
        'xor_rank_if_consistent': (n - free) if pivots is not None else None,
        'free_variables_if_consistent': free if pivots is not None else None,
        'remaining_clauses_after_exact_xor_extraction': len(residual),
        'interface_variables_in_remaining_clauses': len({abs(l) for c in residual for l in c}),
        'recommended_representation': ('GF(2) direct' if pivots is not None and not residual else
            'GF(2) + interface' if pivots is not None and equations and
                len({abs(l) for c in residual for l in c}) < free else
            'GF(2) + affine' if pivots is not None and equations else 'DPLL or other'),
        'graph': graph_profile(n, clauses),
        'spectrum': spectral_profile(n, clauses, max_n=spectral_limit),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('command', choices=['test','demo','benchmark','solve','analyze'])
    parser.add_argument('cnf', nargs='?')
    parser.add_argument('--budget', type=float, default=0.3)
    parser.add_argument('--output', default=None, help='Benchmark results filename stem')
    args = parser.parse_args()
    if args.command == 'test':
        test_suite()
    elif args.command == 'demo':
        n, clauses = little_original()
        print(f'Blind, shuffled CNF: variables={n}, clauses={len(clauses)}')
        for mode in ('auto','dpll'):
            print(mode, asdict(solve(n, clauses, mode=mode, budget=args.budget)))
        print('Total satisfying states:', sum(check(clauses, bits)
              for bits in product((False,True),repeat=n)))
    elif args.command == 'benchmark':
        benchmarks(args.budget, args.output)
    elif args.command == 'analyze':
        if args.cnf:
            n, clauses = read_dimacs(args.cnf)
        else:
            n, clauses = little_original()
        print(json.dumps(analyze(n, clauses), indent=2, ensure_ascii=False))
    elif args.command == 'solve':
        if not args.cnf:
            parser.error('solve requires a DIMACS .cnf file')
        n, clauses = read_dimacs(args.cnf)
        for mode in ('auto','dpll'):
            print(mode, json.dumps(asdict(solve(n, clauses, mode, args.budget)), indent=2))


if __name__ == '__main__':
    main()