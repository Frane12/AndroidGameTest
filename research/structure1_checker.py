#!/usr/bin/env python3
"""Independent source-bound STRUCTURE-1 verifier (not DRAT/LRAT/VeriPB).

Re-parses ORIGINAL DIMACS and checks actual implication clauses and all
Hall/odd-parity witnesses. The producer's UNSAT flag alone is never trusted.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path


def original_clauses(raw):
    nv = nc = None
    result, clause = [], []
    for line in raw.decode('ascii').splitlines():
        tokens = line.strip().split()
        if not tokens or tokens[0] == 'c':
            continue
        if tokens[0] == 'p':
            if nv is not None or tokens[1:2] != ['cnf'] or len(tokens) != 4:
                raise ValueError('invalid header')
            nv, nc = int(tokens[2]), int(tokens[3])
            if not (0 <= nv <= 4096 and 0 <= nc <= 1000000):
                raise ValueError('input out of scope')
            continue
        if nv is None:
            raise ValueError('header required')
        for t in tokens:
            v = int(t)
            if abs(v) > nv:
                raise ValueError('bad literal')
            if v == 0:
                result.append(frozenset(clause))
                clause.clear()
            else:
                clause.append(v)
    if nv is None or len(result) != nc or clause:
        raise ValueError('bad clause count')
    return nv, set(result)


def check_match(cnf, cert):
    groups = cert.get('groups')
    witness = cert.get('hall_jobs')
    ns = cert.get('hall_neighbors')
    if not isinstance(groups, list) or not (2 <= len(groups) <= 64):
        raise ValueError('invalid groups')
    if not isinstance(witness, list) or not witness or any(type(i) != int or i < 0 or i >= len(groups) for i in witness):
        raise ValueError('invalid Hall subset')
    if len(set(witness)) != len(witness):
        raise ValueError('duplicate jobs')
    if not isinstance(ns, list) or len(set(ns)) != len(ns) or any(type(s) != int for s in ns):
        raise ValueError('invalid neighbor list')
    width = len(groups[0])
    if not (2 <= width <= 16) or any(not isinstance(g, list) or len(g) != width for g in groups):
        raise ValueError('invalid group width')
    used = set()
    for g in groups:
        if any(type(v) != int or v <= 0 or v > cnf[0] for v in g):
            raise ValueError('bad selector')
        if len(set(g)) != width or not used.isdisjoint(g):
            raise ValueError('overlapping assignment selectors')
        used.update(g)
        if frozenset(g) not in cnf[1]:
            raise ValueError('missing source ALO')
    S = sorted(witness)
    if any(frozenset((-groups[i][s], -groups[j][s])) not in cnf[1]
           for i,j in itertools.combinations(S, 2)
           for s in range(width)):
        raise ValueError('source lacks cross-job slot mutex')
    # Only source negative units may forbid resources.
    actual = sorted({slot for job in S for slot, v in enumerate(groups[job])
                     if frozenset((-v,)) not in cnf[1]})
    if actual != sorted(ns) or len(actual) >= len(S):
        raise ValueError('no Hall deficiency in source clauses')
    if cert.get('deficiency') != len(S)-len(actual):
        raise ValueError('deficiency tampering')
    return {'status':'MATCH1_SOURCE_UNSAT_VERIFIED',
            'hall_jobs':len(S),'hall_neighbors':len(actual)}


def check_parity(cnf, cert):
    group = cert.get('onehot')
    if not isinstance(group, list) or not 2 <= len(group) <= 7:
        raise ValueError('missing one-hot variables')
    if any(type(v) != int or v <= 0 or v > cnf[0] for v in group) or len(set(group)) != len(group):
        raise ValueError('invalid selectors')
    if frozenset(group) not in cnf[1]:
        raise ValueError('missing original ALO')
    for u,v in itertools.combinations(group, 2):
        if frozenset((-u,-v)) not in cnf[1]:
            raise ValueError('missing original AMO')
    count = 0
    for size in range(1,len(group)+1,2):
        for selected in itertools.combinations(group,size):
            bits = set(selected)
            forbidden = frozenset(-v if v in bits else v for v in group)
            if forbidden not in cnf[1]:
                raise ValueError('incomplete odd-parity blocking clauses')
            count += 1
    if cert.get('blocked_odd_patterns') != count:
        raise ValueError('incorrect parity coverage')
    return {'status':'PARITY1_SOURCE_UNSAT_VERIFIED',
            'selectors':len(group),'blocked_odd_patterns':count}


def check(raw, cert):
    if cert.get('format') != 'DRNAS-STRUCTURE1-SOURCE-V1':
        raise ValueError('unsupported certificate format')
    if cert.get('source_sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('mismatched original DIMACS bytes')
    if cert.get('status') != 'UNSAT_UNCHECKED':
        raise ValueError('nothing to prove')
    cnf = original_clauses(raw)
    if cert.get('method') == 'MATCH-1':
        return check_match(cnf,cert)
    if cert.get('method') == 'INTEGER-PARITY-1':
        return check_parity(cnf,cert)
    raise ValueError('unknown proof method')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('cnf', type=Path)
    p.add_argument('certificate', type=Path)
    a = p.parse_args()
    try:
        outcome = check(a.cnf.read_bytes(),json.loads(a.certificate.read_text()))
        print('STRUCTURE1_CERTIFIED ' + json.dumps(outcome,sort_keys=True))
    except (ValueError, TypeError, KeyError, IndexError, OSError, UnicodeError) as e:
        print('STRUCTURE1_REJECTED ' + str(e))
        raise SystemExit(1)
