#!/usr/bin/env python3
"""DRNAS STRUCTURE-1: sufficient source-CNF UNSAT recognition.

MATCH-1: source clauses imply bipartite assignment with Hall-deficient subset.
INTEGER-PARITY-1: source clauses imply exactly-one and even XOR on same group.
UNKNOWN otherwise. Not C++ integrated, no standard DRAT/VeriPB proof yet.
"""
import argparse
import hashlib
import json
from collections import deque
from pathlib import Path

FMT = 'DRNAS-STRUCTURE1-SOURCE-V1'


def parse(raw):
    nvars = declared = None
    clauses, pending = [], []
    for line in raw.decode('ascii').splitlines():
        parts = line.split()
        if not parts or parts[0] == 'c':
            continue
        if parts[0] == 'p':
            if nvars is not None or len(parts) != 4 or parts[1] != 'cnf':
                raise ValueError('invalid DIMACS header')
            nvars, declared = int(parts[2]), int(parts[3])
            if not (0 <= nvars <= 4096 and 0 <= declared <= 1000000):
                raise ValueError('outside bounded scope')
            continue
        if nvars is None:
            raise ValueError('header missing')
        for token in parts:
            literal = int(token)
            if abs(literal) > nvars:
                raise ValueError('literal out of bounds')
            if literal == 0:
                clauses.append(tuple(pending))
                pending = []
            else:
                pending.append(literal)
    if nvars is None or pending or len(clauses) != declared:
        raise ValueError('incomplete DIMACS')
    return nvars, clauses


def hall_witness(groups, allowed):
    """Maximum matching, alternating reachability and Hall witness."""
    n = len(groups)
    partner = [-1] * len(groups[0])

    def augment(job, seen):
        for s in sorted(allowed[job]):
            if s in seen:
                continue
            seen.add(s)
            if partner[s] < 0 or augment(partner[s], seen):
                partner[s] = job
                return True
        return False

    for job in range(n):
        augment(job, set())
    matched_jobs = set(partner) - {-1}
    if len(matched_jobs) == n:
        return None
    reached_jobs = set(range(n)) - matched_jobs
    reached_slots = set()
    q = deque(sorted(reached_jobs))
    while q:
        j = q.popleft()
        for s in allowed[j]:
            if s not in reached_slots:
                reached_slots.add(s)
                if partner[s] >= 0 and partner[s] not in reached_jobs:
                    reached_jobs.add(partner[s]); q.append(partner[s])
    neighbors = set().union(*(allowed[j] for j in reached_jobs))
    if len(neighbors) >= len(reached_jobs):
        raise AssertionError('alternating witness not deficient')
    return sorted(reached_jobs), sorted(neighbors)


def match1(nvars, clauses):
    keys = {frozenset(c) for c in clauses}
    positives = [tuple(c) for c in clauses if 2 <= len(c) <= 16
                 and len(set(c)) == len(c) and all(x > 0 for x in c)]
    if not positives:
        return None
    widths = {len(c) for c in positives}
    if len(widths) != 1:
        return None
    groups = positives
    r, n = len(groups[0]), len(groups)
    if not (2 <= n <= 64) or nvars != n * r:
        return None
    if len({x for g in groups for x in g}) != nvars:
        return None
    # Treat position s as a resource only when all actual mutex clauses exist.
    for s in range(r):
        for j in range(n):
            for i in range(j + 1, n):
                if frozenset((-groups[j][s], -groups[i][s])) not in keys:
                    return None
    allowed = [set(s for s, var in enumerate(g) if frozenset((-var,)) not in keys)
               for g in groups]
    result = hall_witness(groups, allowed)
    if result is None:
        return None
    subset, neighbors = result
    return {'method': 'MATCH-1', 'status': 'UNSAT_UNCHECKED',
            'groups': [list(g) for g in groups], 'hall_jobs': subset,
            'hall_neighbors': neighbors, 'deficiency': len(subset) - len(neighbors)}


def parity1(clauses):
    keys = {frozenset(c) for c in clauses}
    for group in clauses:
        if not (2 <= len(group) <= 7 and all(v > 0 for v in group)
                and len(set(group)) == len(group)):
            continue
        if any(frozenset((-a, -b)) not in keys
               for i, a in enumerate(group) for b in group[i + 1:]):
            continue
        clauses_required = []
        for bits in range(1 << len(group)):
            if bits.bit_count() % 2 == 0:
                continue
            blocker = tuple(-v if bits & (1 << i) else v
                            for i, v in enumerate(group))
            if frozenset(blocker) not in keys:
                break
            clauses_required.append(list(blocker))
        else:
            return {'method': 'INTEGER-PARITY-1', 'status': 'UNSAT_UNCHECKED',
                    'onehot': list(group), 'blocked_odd_patterns': len(clauses_required)}
    return None


def prove(raw):
    digest = hashlib.sha256(raw).hexdigest()
    data = {'format': FMT, 'source_sha256': digest,
            'status': 'UNKNOWN', 'method': 'NONE'}
    try:
        nvars, clauses = parse(raw)
        for detector in (match1, parity1):
            result = detector(nvars, clauses) if detector is match1 else detector(clauses)
            if result is not None:
                data.update(result)
                break
    except (ValueError, UnicodeError, OverflowError, RecursionError) as err:
        data['reason'] = type(err).__name__
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cnf', type=Path)
    parser.add_argument('--certificate', type=Path, required=True)
    args = parser.parse_args()
    result = prove(args.cnf.read_bytes())
    args.certificate.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print('STRUCTURE1_PRODUCER ' + json.dumps({k:v for k,v in result.items() if k!='groups'}, sort_keys=True))
