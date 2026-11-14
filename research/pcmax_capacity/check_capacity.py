#!/usr/bin/env python3
"""Check a PCMAX capacity contradiction using original CNF clauses and integers.

The checker does not import a SAT solver, LP optimizer, or structure extractor.
For each claimed graph it checks the two conditional implication clauses for
all nodes, and explicitly counts selected variables skipped along each edge.
Every satisfying assignment would induce an accepting path in every graph.
The resulting maximum counts upper-bound the selected true literals.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time


class InvalidCertificate(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidCertificate(message)


def parse_cnf(data):
    clauses, pending = [], []
    variables = declared = None
    for line in data.decode('ascii').splitlines():
        fields = line.split()
        if not fields or fields[0] == 'c':
            continue
        if fields[0] == 'p':
            require(variables is None and len(fields) == 4 and fields[1] == 'cnf', 'invalid header')
            variables, declared = map(int, fields[2:])
            require(variables >= 0 and declared >= 0, 'negative dimensions')
            continue
        require(variables is not None, 'missing header')
        for value in map(int, fields):
            require(abs(value) <= variables, 'literal outside header range')
            if value:
                pending.append(value)
            else:
                clauses.append(frozenset(pending))
                pending = []
    require(variables is not None and not pending and len(clauses) == declared, 'clause count mismatch')
    return variables, set(clauses)


def check(data, certificate):
    started = time.perf_counter()
    digest = hashlib.sha256(data).hexdigest()
    require(certificate['source_sha256'] == digest, 'source hash mismatch')
    variables, clauses = parse_cnf(data)
    selected = set()
    selected_weight = {}
    groups = certificate['selected_groups']
    require(bool(groups), 'empty group list')
    weights = certificate.get('group_weights', [1] * len(groups))
    require(len(weights) == len(groups), 'weight count mismatch')
    require(all(type(w) is int and w > 0 for w in weights), 'invalid group weight')
    for group, weight in zip(groups, weights):
        require(bool(group) and all(type(v) is int and 0 < v <= variables for v in group), 'invalid group')
        require(len(group) == len(set(group)), 'repeated group literal')
        require(not selected.intersection(group), 'overlapping groups')
        require(frozenset(group) in clauses, 'missing at-least-one input clause')
        selected.update(group)
        selected_weight.update((v, weight) for v in group)

    all_selectors, all_states = set(), set()
    capacities, roots = [], []
    for machine in certificate['machines']:
        order = machine['variable_order']
        require(bool(order) and all(type(v) is int and 0 < v <= variables for v in order), 'invalid selector order')
        require(len(order) == len(set(order)), 'repeated selector')
        require(not all_selectors.intersection(order), 'overlapping machine selectors')
        all_selectors.update(order)
        ranks = {v: i for i, v in enumerate(order)}
        prefix = [0]
        for variable in order:
            prefix.append(prefix[-1] + selected_weight.get(variable, 0))
        nodes = {}
        for row in machine['transitions']:
            require(len(row) == 4 and all(type(v) is int and 0 < v <= variables for v in row), 'invalid transition')
            parent, selector, left, right = row
            require(parent not in nodes, 'repeated parent')
            require(selector in ranks, 'unknown selector')
            require(len({parent, selector, left}) == 3 and len({parent, selector, right}) == 3, 'aliased transition')
            require(frozenset((-parent, selector, left)) in clauses, 'missing false-branch input clause')
            require(frozenset((-parent, -selector, right)) in clauses, 'missing true-branch input clause')
            nodes[parent] = selector, left, right
        root, true, false = machine['root'], machine['true_terminal'], machine['false_terminal']
        require(root in nodes and true != false and true not in nodes and false not in nodes, 'invalid root/terminals')
        require(frozenset((root,)) in clauses and frozenset((true,)) in clauses and frozenset((-false,)) in clauses, 'missing root/terminal units')
        states = set(nodes) | {true, false}
        require(not all_states.intersection(states), 'overlapping machine states')
        all_states.update(states)
        node_rank = {p: ranks[row[0]] for p, row in nodes.items()}
        node_rank[true] = node_rank[false] = len(order)
        for parent, (selector, left, right) in nodes.items():
            require(left in states and right in states, 'unlisted child')
            require(node_rank[left] > ranks[selector] and node_rank[right] > ranks[selector], 'unordered or cyclic graph')

        # None denotes an impossible path. Skipped selector levels can all be
        # selected for an upper bound, even if other input constraints forbid it.
        best = {true: 0, false: None}
        for parent in sorted(nodes, key=node_rank.__getitem__, reverse=True):
            selector, left, right = nodes[parent]
            current = ranks[selector]
            options = []
            for child, chosen in ((left, 0), (right, selected_weight.get(selector, 0))):
                if best[child] is not None:
                    skipped = prefix[node_rank[child]] - prefix[current + 1]
                    options.append(best[child] + skipped + chosen)
            best[parent] = max(options) if options else None
        require(best[root] is not None, 'no accepting graph path')
        capacity = prefix[node_rank[root]] + best[root]
        require(type(machine['capacity']) is int and machine['capacity'] == capacity, 'claimed capacity mismatch')
        capacities.append(capacity)
        roots.append(root)

    require(not all_states.intersection(all_selectors), 'state used as selector')
    require(selected <= all_selectors, 'selected literal lacks a machine')
    require(certificate['required'] == sum(weights), 'required weight mismatch')
    require(certificate['capacity_sum'] == sum(capacities), 'capacity sum mismatch')
    require(sum(capacities) < sum(weights), 'capacity bound does not contradict demand')
    return {'status': 'UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED', 'source_sha256': digest,
            'required': sum(weights), 'selected_groups': len(groups), 'group_weights': weights,
            'capacity_sum': sum(capacities),
            'machine_roots': roots, 'machine_capacities': capacities,
            'selected_literals': len(selected), 'check_s': time.perf_counter() - started}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cnf', type=Path)
    parser.add_argument('certificate', type=Path)
    args = parser.parse_args()
    try:
        result = check(args.cnf.read_bytes(), json.loads(args.certificate.read_text()))
    except (InvalidCertificate, KeyError, TypeError, ValueError) as error:
        print(json.dumps({'status': 'INVALID_CERTIFICATE', 'reason': str(error)}, sort_keys=True))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
