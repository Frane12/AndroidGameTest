#!/usr/bin/env python3
"""Source-bound polynomial-size cutting-planes proof for PCMAX clique certificates.
Producer reports EMITTED_UNCHECKED; only independent VeriPB 3.0.2 acceptance
of the unchanged original CNF establishes standard VERIFIED_UNSAT.
"""
from __future__ import annotations
import argparse
import json
import hashlib
from pathlib import Path
from verify_clique import parse, verify


def derive(source: bytes, certificate: dict, max_proof_lines: int = 100000):
    summary = verify(source, certificate)
    _, clauses = parse(source)
    edge = {}
    for ci, clause in enumerate(clauses, 1):
        if len(clause) == 2 and clause[0] < 0 and clause[1] < 0 and clause[0] != clause[1]:
            edge.setdefault(tuple(sorted((-clause[0], -clause[1]))), ci)
    lines = ['pseudo-Boolean proof version 3.0', f'f {len(clauses)} ;']
    next_id = len(clauses)
    clique_constraint_ids = []
    for group in certificate['mutex_cliques']:
        v = sorted(group)
        if len(v) == 1:
            continue
        prev = edge[(v[0], v[1])]
        for i in range(2, len(v)):
            k = i + 1
            # (k-2)*AMO(k-1)+sum_{u in previous} mutex(u,new), divide k-1
            # => sum_{u in clique} ~x_u >= k-1.
            terms = [str(prev), str(k - 2), '*']
            for u in v[:i]:
                terms.extend([str(edge[tuple(sorted((u, v[i])))]), '+'])
            terms.extend([str(k - 1), 'd', ';'])
            if len(lines) >= max_proof_lines:
                raise ValueError('proof line budget exhausted')
            lines.append('pol ' + ' '.join(terms))
            next_id += 1
            prev = next_id
        clique_constraint_ids.append(prev)
    # Adding every at-least-one source clause to each derived AMO source
    # inequality creates a contradiction if J > C. Singleton cliques impose
    # only Boolean upper bounds and need no explicit inequality.
    ids = [i + 1 for i in certificate['job_clause_indices']] + clique_constraint_ids
    if not ids:
        raise ValueError('empty proof')
    terms = [str(ids[0])]
    for cid in ids[1:]:
        terms.extend([str(cid), '+'])
    terms.append(';')
    lines += ['pol ' + ' '.join(terms), 'output NONE ;',
              'conclusion UNSAT ;', 'end pseudo-Boolean proof ;']
    return '\n'.join(lines) + '\n', {
        'source_sha256': hashlib.sha256(source).hexdigest(),
        'original_clauses': len(clauses),
        'cutting_planes_steps': next_id - len(clauses) + 1,
        'selected_demand_clauses': certificate['demand'],
        'clique_count': certificate['capacity'],
        'selected_selector_count': summary['selectors'],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cnf', type=Path, required=True)
    p.add_argument('--certificate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit('refusing to overwrite existing proof')
    proof, meta = derive(args.cnf.read_bytes(), json.loads(args.certificate.read_text()))
    args.output.write_text(proof)
    meta['proof_bytes'] = args.output.stat().st_size
    print('EMITTED_UNCHECKED ' + json.dumps(meta, sort_keys=True))


if __name__ == '__main__':
    main()
