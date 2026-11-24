#!/usr/bin/env python3
"""Independent source-bound Hall UNSAT certificate checker, no solver import.
The JSON certificate is not a VeriPB, DRAT or LRAT proof.
"""
import argparse
import hashlib
import json
from pathlib import Path


def check_cnf(raw):
    nvars = total = None
    clauses = []
    current = []
    for line in raw.decode('ascii').splitlines():
        words = line.split()
        if not words or words[0] == 'c':
            continue
        if words[0] == 'p':
            if nvars is not None or current or len(words) != 4 or words[1] != 'cnf':
                raise ValueError('invalid or duplicate DIMACS header')
            nvars, total = int(words[2]), int(words[3])
            if nvars < 0 or total < 0:
                raise ValueError('negative DIMACS dimensions')
            continue
        if nvars is None:
            raise ValueError('missing DIMACS header')
        for token in words:
            lit = int(token)
            if lit:
                if abs(lit) > nvars:
                    raise ValueError('literal out of range')
                current.append(lit)
            else:
                clauses.append(tuple(current))
                current = []
    if nvars is None or current or len(clauses) != total:
        raise ValueError('DIMACS clause mismatch')
    return nvars, clauses


def verify(source, proof):
    if proof.get('format') != 'pcmax-scale3-hall-source-v1':
        raise ValueError('unrecognized certificate')
    sha = hashlib.sha256(source).hexdigest()
    if proof.get('source_sha256') != sha:
        raise ValueError('source SHA mismatch')
    nvars, clauses = check_cnf(source)
    binary = set()
    for c in clauses:
        if len(c) == 2 and c[0] < 0 and c[1] < 0:
            binary.add(tuple(sorted((-c[0], -c[1]))))
    chosen = proof.get('job_clause_indices')
    slots = proof.get('mutex_slot_groups')
    if not isinstance(chosen, list) or not chosen or not isinstance(slots, list) or not slots:
        raise ValueError('empty witness')
    if any(type(j) is not int for j in chosen) or len(set(chosen)) != len(chosen):
        raise ValueError('invalid demand indices')
    demanded = set()
    for idx in chosen:
        if idx < 0 or idx >= len(clauses):
            raise ValueError('demand index out of range')
        c = clauses[idx]
        if len(c) < 2 or any(x <= 0 for x in c) or len(c) != len(set(c)):
            raise ValueError('invalid source demand clause')
        if demanded.intersection(c):
            raise ValueError('overlapping demands')
        demanded.update(c)
    covered = set()
    for slot in slots:
        if not isinstance(slot, list) or not slot or any(type(x) is not int or x <= 0 or x > nvars for x in slot):
            raise ValueError('invalid slot')
        if len(set(slot)) != len(slot) or covered.intersection(slot):
            raise ValueError('overlapping slot membership')
        for i, a in enumerate(slot):
            for b in slot[i+1:]:
                if tuple(sorted((a, b))) not in binary:
                    raise ValueError('not a source mutex clique')
        covered.update(slot)
    if not demanded.issubset(covered):
        raise ValueError('uncovered demand selectors')
    if any(not demanded.intersection(slot) for slot in slots):
        raise ValueError('extraneous slots')
    if type(proof.get('demand')) is not int or type(proof.get('capacity')) is not int:
        raise ValueError('invalid integer capacity')
    if proof['demand'] != len(chosen) or proof['capacity'] != len(slots) or proof['demand'] <= proof['capacity']:
        raise ValueError('missing Hall contradiction')
    return {'status': 'SOURCE_HALL_UNSAT_VERIFIED', 'sha256': sha,
            'demand': len(chosen), 'capacity': len(slots)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cnf', type=Path)
    parser.add_argument('certificate', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.cnf.read_bytes(), json.loads(args.certificate.read_text()))))
    except (ValueError, UnicodeError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'REJECTED: {exc}\n')
