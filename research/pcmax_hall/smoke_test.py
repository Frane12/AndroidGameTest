#!/usr/bin/env python3
"""Synthetic source-bound native Hall tests; NOT external blind benchmarking."""
import hashlib
import json
import random
import subprocess
import tempfile
from pathlib import Path
from verify_hall import verify


def generate(bins, kind, seed):
    rng = random.Random(seed)
    unsat = kind != 'SAT'
    special = bins + (1 if unsat else 0)
    outside = 4
    choices = [list(range(bins)) for _ in range(special)]
    for k in range(outside):
        choices.append([rng.randrange(bins), bins + k, bins + outside + k % 2])
    mapping = {}
    per_bin = {}
    clauses = []
    for job, slots in enumerate(choices):
        literals = []
        for slot in slots:
            v = len(mapping) + 1
            mapping[(job, slot)] = v
            literals.append(v)
            per_bin.setdefault(slot, []).append(v)
        clauses.append(literals)
        for idx, a in enumerate(literals):
            for b in literals[idx+1:]:
                clauses.append([-a, -b])
    for literals in per_bin.values():
        for idx, a in enumerate(literals):
            for b in literals[idx+1:]:
                clauses.append([-a, -b])
    if kind == 'DECOY':
        clauses.append([-mapping[(0, 0)], -mapping[(1, 1)]])
    # Source-variable permutation and clause shuffle prevent index memorization.
    labels = list(range(1, len(mapping) + 1))
    rng.shuffle(labels)
    for clause in clauses:
        for k, lit in enumerate(clause):
            clause[k] = labels[abs(lit)-1] * (1 if lit > 0 else -1)
        rng.shuffle(clause)
    rng.shuffle(clauses)
    return (f'p cnf {len(mapping)} {len(clauses)}\n' +
            ''.join(' '.join(map(str, c)) + ' 0\n' for c in clauses)).encode()


def main(binary):
    counts = {'UNSAT': 0, 'SAT': 0, 'DECOY': 0}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for k in range(24):
            kind = ['UNSAT', 'SAT', 'DECOY'][k % 3]
            raw = generate(7 + k % 9, kind, 510002 + k * 43)
            cnf, cert = tmp / 'case.cnf', tmp / 'proof.json'
            cnf.write_bytes(raw)
            cert.unlink(missing_ok=True)
            cmd = [str(binary), str(cnf), '--mode', 'core', '--time', '3',
                   '--pcmax-hall-only', '--pcmax-hall-budget-ms', '1500',
                   '--pcmax-certificate', str(cert)]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
            if kind == 'UNSAT':
                assert p.returncode == 20 and cert.is_file(), (kind, p.stdout)
                proof = json.loads(cert.read_text())
                assert verify(raw, proof)['status'] == 'SOURCE_HALL_UNSAT_VERIFIED'
                assert proof['source_sha256'] == hashlib.sha256(raw).hexdigest()
                altered = dict(proof)
                altered['source_sha256'] = '0' * 64
                try:
                    verify(raw, altered)
                except ValueError:
                    pass
                else:
                    raise AssertionError('forged SHA accepted')
            else:
                assert p.returncode == 0 and not cert.exists(), (kind, p.stdout)
            counts[kind] += 1
    print('PCMAX_HALL_NATIVE_PASS', json.dumps(counts, sort_keys=True))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, default=Path('build/drnas-pcmax'))
    a = parser.parse_args()
    main(a.binary.resolve())
