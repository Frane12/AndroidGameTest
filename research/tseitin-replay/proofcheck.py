"""Replay certificates directly against DIMACS without importing solver code."""
from collections import defaultdict
from itertools import product
from pathlib import Path

def dimacs(path):
    clauses, clause = [], []
    n = count = None
    for line in Path(path).read_text().splitlines():
        row = line.split()
        if not row or row[0] == 'c':
            continue
        if row[0] == 'p':
            assert n is None and row[1] == 'cnf'
            n, count = map(int, row[2:])
            continue
        for lit in map(int, row):
            if lit:
                assert 0 < abs(lit) <= n
                clause.append(lit)
            else:
                clauses.append(tuple(clause))
                clause = []
    assert not clause and len(clauses) == count
    return n, clauses

def rhs_of(support, clauses):
    assert 1 <= len(support) <= 3 and len(set(support)) == len(support)
    assert all(set(map(abs, c)) <= set(support) for c in clauses)
    allowed = set()
    for values in product((0, 1), repeat=len(support)):
        env = dict(zip(support, values))
        if all(any(bool(env[abs(x)]) == (x > 0) for x in c) for c in clauses):
            allowed.add(values)
    for rhs in (0, 1):
        if allowed == {v for v in product((0, 1), repeat=len(support)) if sum(v) % 2 == rhs}:
            return rhs
    raise ValueError("Clauses do not encode the asserted parity")

def check_hidden(clauses, equations):
    residual, parity = set(), 0
    assert equations
    for row in equations:
        support, indices = row['variables'], row['clause_indices']
        assert all(0 <= i < len(clauses) for i in indices)
        rhs = rhs_of(support, [clauses[i] for i in indices])
        assert rhs == row['rhs']
        residual.symmetric_difference_update(support)
        parity ^= rhs
    assert not residual and parity == 1

def check_whole(n, clauses, answer):
    if answer['status'] == 'SAT':
        verify_model(n, clauses, answer['model'])
        return
    groups = defaultdict(list)
    for clause in clauses:
        groups[tuple(sorted(map(abs, clause)))].append(clause)
    supports = sorted(groups)
    assert len(set(answer['proof_rows'])) == len(answer['proof_rows'])
    residual, parity = set(), 0
    for i in answer['proof_rows']:
        assert 0 <= i < len(supports)
        support = supports[i]
        parity ^= rhs_of(support, groups[support])
        residual.symmetric_difference_update(support)
    assert not residual and parity == 1

def verify_model(n, clauses, model):
    values = {abs(v):v > 0 for v in model if v}
    assert set(values) == set(range(1,n+1))
    assert all(any(values[abs(x)] == (x > 0) for x in c) for c in clauses)
