#!/usr/bin/env python3
"""Independent original-CNF checker for exact-one / XOR / root-UP refutations.

No imports from the producer, no search, no trust in catalog labels. Experimental
certificate format, NOT DRAT/LRAT and NOT a formally verified implementation.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path

class InvalidProof(ValueError):
    pass

def need(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidProof(message)

def parse(raw: bytes) -> tuple[int, set[frozenset[int]]]:
    n = declared = None
    clauses: list[frozenset[int]] = []
    pending: list[int] = []
    for line in raw.decode('ascii').splitlines():
        xs = line.split()
        if not xs or xs[0] == 'c':
            continue
        if xs[0] == 'p':
            need(n is None and len(xs) == 4 and xs[1] == 'cnf', 'bad header')
            n, declared = int(xs[2]), int(xs[3])
            need(0 < n <= 6000 and 0 <= declared <= 100000, 'source size gate')
            continue
        need(n is not None, 'missing header')
        for x in map(int, xs):
            need(abs(x) <= n, 'literal out of range')
            if x:
                pending.append(x)
            else:
                clauses.append(frozenset(pending)); pending = []
    need(n is not None and not pending and len(clauses) == declared, 'clause count mismatch')
    return n, set(clauses)

def unit_closure(clauses: set[frozenset[int]], n: int) -> dict[int, bool]:
    forced: dict[int, bool] = {}
    for _ in range(n + 1):
        changed = False
        for c in clauses:
            if any(abs(l) in forced and forced[abs(l)] == (l > 0) for l in c):
                continue
            missing = [l for l in c if abs(l) not in forced]
            need(bool(missing), 'direct UP conflict requires a separate proof format')
            if len(missing) == 1:
                l = missing[0]; forced[abs(l)] = l > 0; changed = True
        if not changed:
            return forced
    raise InvalidProof('UP closure did not converge')

def verify(raw: bytes, proof: dict) -> dict:
    need(type(proof) is dict and proof.get('format') == 'drnas-math5-eo-xor-unit-v1', 'bad proof format')
    need(proof.get('source_sha256') == hashlib.sha256(raw).hexdigest(), 'source SHA mismatch')
    n, original = parse(raw)
    xors, eos, units = (proof.get(k) for k in ('xor_rows', 'exact_one_groups', 'root_units'))
    need(all(type(v) is list for v in (xors, eos, units)), 'bad proof collections')
    need(1 <= len(xors) + len(eos) <= 4096 and len(units) <= 4096, 'proof size gate')
    variables: set[int] = set()
    rhs = 0
    for row in xors:
        need(type(row) is dict, 'bad XOR row')
        vs, parity = row.get('vars'), row.get('forbidden_parity')
        need(type(vs) is list and 2 <= len(vs) <= 6, 'bad XOR support')
        need(all(type(v) is int and 0 < v <= n for v in vs) and len(set(vs)) == len(vs), 'bad XOR variables')
        need(type(parity) is int and parity in (0, 1), 'bad parity')
        for bits in itertools.product((0, 1), repeat=len(vs)):
            if sum(bits) % 2 == parity:
                c = frozenset(-v if b else v for v, b in zip(vs, bits))
                need(c in original, 'missing original XOR clause')
        variables.symmetric_difference_update(vs)
        rhs ^= 1 - parity
    for group in eos:
        need(type(group) is list and 3 <= len(group) <= 128, 'bad exact-one group')
        need(all(type(l) is int and 0 < abs(l) <= n for l in group), 'bad exact-one literal')
        need(len({abs(l) for l in group}) == len(group), 'duplicate/tautological exact-one variables')
        need(frozenset(group) in original, 'missing original ALO clause')
        for a, b in itertools.combinations(group, 2):
            need(frozenset((-a, -b)) in original, 'missing original mutex clause')
        variables.symmetric_difference_update(abs(l) for l in group)
        rhs ^= 1 ^ (sum(l < 0 for l in group) & 1)
    forced = unit_closure(original, n) if units else {}
    seen = set()
    for l in units:
        need(type(l) is int and 0 < abs(l) <= n and abs(l) not in seen, 'bad/duplicate unit')
        need(forced.get(abs(l)) == (l > 0), 'unit not derivable from original CNF')
        seen.add(abs(l)); variables.symmetric_difference_update((abs(l),)); rhs ^= int(l > 0)
    need(not variables and rhs == 1, 'sum does not derive 0=1')
    return dict(status='UNSAT_MATH5_CERTIFICATE_VERIFIED', source_sha256=proof['source_sha256'],
                xor_rows=len(xors), exact_one_rows=len(eos), root_units=len(units),
                mixed_bridge_used=bool(eos and xors), unique_source_clauses=len(original))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('cnf', type=Path); p.add_argument('proof', type=Path)
    a = p.parse_args()
    try:
        print(json.dumps(verify(a.cnf.read_bytes(), json.loads(a.proof.read_text())), sort_keys=True))
    except (ValueError, KeyError, TypeError) as e:
        print(json.dumps({'status':'INVALID_CERTIFICATE', 'reason':str(e)})); raise SystemExit(1)
