#!/usr/bin/env python3
"""MRE12: proof-replayed signed-equivalence CNF quotient, with safe abstention.

Only substitute v = signed_representative(v) when BOTH implication paths
are replayed as original binary-clause consequences. Every SAT witness
is expanded to original variables and independently checked on source CNF.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import subprocess
import tempfile
import time

PROTO = 'DRNAS-MRE12-EXACT-SCC-QUOTIENT-12SHA-4ARM-2REP-8S-v1'
ARMS = ('baseline', 'shadow', 'quotient', 'selective_no_vivify')
CAP, REPS, SHARDS = 8.0, 2, 4
OUT = pathlib.Path('mre12_out')
MAX_VARIABLES, MAX_CLAUSES = 6000, 70000
MAX_EQUIVALENCES, MAX_PATH_EDGES = 48, 12
MAX_PREPASS_S = 0.6

def need(condition, why):
    if not condition:
        raise RuntimeError('MRE12_FAIL_CLOSED: ' + str(why))

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for data in iter(lambda: stream.read(1 << 20), b''):
            h.update(data)
    return h.hexdigest()

def parse_dimacs(path):
    header = None
    clauses, current = [], []
    with open(path, encoding='utf-8') as stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith(('c', '%')):
                continue
            if line.startswith('p '):
                fields = line.split()
                need(header is None and not current and len(fields) == 4 and fields[1] == 'cnf',
                     'DIMACS header invalid')
                header = (int(fields[2]), int(fields[3]))
                need(header[0] >= 0 and header[1] >= 0, 'negative DIMACS dimensions')
                continue
            need(header is not None, 'clause before header')
            for token in line.split():
                literal = int(token)
                if literal == 0:
                    clauses.append(tuple(current))
                    current = []
                else:
                    need(0 < abs(literal) <= header[0], 'literal out of range')
                    current.append(literal)
    need(header is not None and not current and len(clauses) == header[1],
         'DIMACS clause count or terminator mismatch')
    return header[0], clauses

def edge_graph(clauses):
    graph = collections.defaultdict(set)
    reverse = collections.defaultdict(set)
    original_binary = set()
    for clause in clauses:
        if len(clause) != 2:
            continue
        a, b = clause
        if a == b or a == -b:
            continue
        original_binary.add(frozenset((a, b)))
        for x, y in ((-a, b), (-b, a)):
            graph[x].add(y)
            reverse[y].add(x)
    return graph, reverse, original_binary

def components(graph, reverse):
    nodes = sorted(set(graph) | set(reverse), key=lambda x: (abs(x), x))
    visited, finish = set(), []
    for root in nodes:
        if root in visited:
            continue
        visited.add(root)
        stack = [(root, iter(sorted(graph.get(root, ()))))]
        while stack:
            here, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                finish.append(here)
                stack.pop()
            elif nxt not in visited:
                visited.add(nxt)
                stack.append((nxt, iter(sorted(graph.get(nxt, ())))))
    comp, groups = {}, []
    for root in reversed(finish):
        if root in comp:
            continue
        cid = len(groups)
        comp[root] = cid
        group, stack = [], [root]
        while stack:
            here = stack.pop()
            group.append(here)
            for nxt in reverse.get(here, ()):
                if nxt not in comp:
                    comp[nxt] = cid
                    stack.append(nxt)
        groups.append(group)
    return comp, groups

def path_in_component(graph, comp, start, finish):
    if start == finish:
        return [start]
    q = collections.deque([(start, 0)])
    parent = {start: None}
    while q:
        here, depth = q.popleft()
        if depth >= MAX_PATH_EDGES:
            continue
        for nxt in sorted(graph.get(here, ())):
            if comp.get(nxt) != comp.get(start) or nxt in parent:
                continue
            parent[nxt] = here
            if nxt == finish:
                path = [nxt]
                while parent[path[-1]] is not None:
                    path.append(parent[path[-1]])
                return list(reversed(path))
            q.append((nxt, depth + 1))
    return None

def discover(nvars, clauses, budget=MAX_PREPASS_S):
    begun = time.perf_counter()
    if nvars > MAX_VARIABLES or len(clauses) > MAX_CLAUSES:
        return [], 'size_guard'
    graph, reverse, _ = edge_graph(clauses)
    if not graph:
        return [], 'no_binary_implications'
    comp, groups = components(graph, reverse)
    if any(comp.get(v) == comp.get(-v) for v in range(1, nvars + 1)
           if v in comp and -v in comp):
        return [], 'contradictory_scc_fallback'
    certs = []
    for v in range(1, nvars + 1):
        if time.perf_counter() - begun > budget:
            return [], 'budget_fallback'
        if v not in comp:
            continue
        group = groups[comp[v]]
        opposite = groups[comp[-v]] if -v in comp else []
        representative = min((abs(u) for u in group + opposite), default=v)
        if representative >= v:
            continue
        signed = representative if comp.get(v) == comp.get(representative) else -representative
        if comp.get(v) != comp.get(signed) or comp.get(-v) != comp.get(-signed):
            continue
        there = path_in_component(graph, comp, v, signed)
        back = path_in_component(graph, comp, signed, v)
        if there is None or back is None:
            continue
        certs.append(dict(variable=v, target=signed, forward=there, backward=back))
        if len(certs) == MAX_EQUIVALENCES:
            break
    return certs, 'certificates' if certs else 'no_short_equivalences'

def replay(clauses, certs):
    """Independent replay against ORIGINAL binary clauses, not SCC labels."""
    original = {frozenset(c) for c in clauses if len(c) == 2}
    mapping = {}
    for c in certs:
        v, target = c['variable'], c['target']
        need(v > 0 and 0 < abs(target) < v and v not in mapping,
             'noncanonical or duplicate signed representative')
        for key, begin, end in (('forward', v, target), ('backward', target, v)):
            path = c[key]
            need(isinstance(path, list) and 2 <= len(path) <= MAX_PATH_EDGES + 1
                 and path[0] == begin and path[-1] == end, 'bad proof path')
            for src, dst in zip(path, path[1:]):
                need(src != dst and src != -dst and frozenset((-src, dst)) in original,
                     'non-original implication in path')
        mapping[v] = target
    need(all(abs(t) not in mapping for t in mapping.values()), 'nonterminating mapping')
    return mapping

def reduce_clauses(nvars, clauses, mapping):
    reduced, seen = [], set()
    for clause in clauses:
        values = set()
        tautology = False
        for lit in clause:
            rep = mapping.get(abs(lit), abs(lit))
            x = rep if lit > 0 else -rep
            if -x in values:
                tautology = True
                break
            values.add(x)
        if tautology:
            continue
        mapped = tuple(sorted(values, key=lambda x: (abs(x), x)))
        if mapped not in seen:
            seen.add(mapped)
            reduced.append(mapped)
    need(all(0 < abs(lit) <= nvars for c in reduced for lit in c),
         'reduction out of original variable range')
    return reduced

def reconstruct(nvars, model, mapping):
    # Original variable IDs are retained. Unused/free variables are arbitrary.
    full = {v: bool(model.get(v, False)) for v in range(1, nvars + 1)}
    for v, signed in mapping.items():
        full[v] = full[abs(signed)] if signed > 0 else not full[abs(signed)]
    return full

def model_satisfies(clauses, model):
    return all(any(model.get(abs(x), False) == (x > 0) for x in c) for c in clauses)

def encode(nvars, clauses):
    lines = [f'p cnf {nvars} {len(clauses)}']
    lines += [(' '.join(map(str, c)) + ' 0').strip() for c in clauses]
    return '\n'.join(lines) + '\n'

def exhaustive_test():
    rng = random.Random(120926)
    examples = [
        (2, [(1, -2), (-1, 2)]),
        (2, [(1, 2), (-1, -2)]),
        (3, [(1, -2), (-1, 2), (2, -3), (-2, 3)]),
        (2, [(1, 2), (1, -2), (-1, 2), (-1, -2)]),
        (3, [(1,), (-1,), (1, 2)]),
        (2, [(), (1, 2)]),
    ]
    for n in range(1, 6):
        pool = [tuple(c) for width in (1, 2, 3)
                for vs in itertools.combinations(range(1, n + 1), width)
                for signs in itertools.product((-1, 1), repeat=width)
                for c in [tuple(a * b for a, b in zip(vs, signs))]]
        for _ in range(100):
            examples.append((n, rng.choices(pool, k=rng.randrange(0, 15))))
    checked = 0
    for n, clauses in examples:
        certs, reason = discover(n, clauses, budget=5)
        mapping = replay(clauses, certs)
        transformed = reduce_clauses(n, clauses, mapping) if mapping else clauses
        for bits in range(1 << n):
            model = {v: bool(bits & (1 << (v - 1))) for v in range(1, n + 1)}
            projected = reconstruct(n, model, mapping)
            if model_satisfies(transformed, model):
                need(model_satisfies(clauses, projected), 'reconstructed model invalid')
            if model_satisfies(clauses, model):
                need(model_satisfies(transformed, model), 'original model lost')
                need(all(model[v] == projected[v] for v in range(1, n + 1)),
                     'original model reconstruction changed truth values')
            checked += 1
        if certs:
            bad = [dict(c) for c in certs]
            bad[0] = dict(bad[0], forward=list(bad[0]['forward']))
            bad[0]['forward'][0] = -bad[0]['forward'][0]
            try:
                replay(clauses, bad)
            except RuntimeError:
                pass
            else:
                need(False, 'tampered implication proof not rejected')
    need(replay([(1, -2), (-1, 2)], discover(2, [(1, -2), (-1, 2)])[0]),
         'positive equality missing')
    need(replay([(1, 2), (-1, -2)], discover(2, [(1, 2), (-1, -2)])[0]),
         'negative equality missing')
    print('MRE12_EXHAUSTIVE_PASS ' + json.dumps(dict(tests=len(examples), assignments=checked,
          negative_proof_test=True, exact_source_models_only=True), sort_keys=True), flush=True)

def source_cases():
    import c15d_benchmark as c15d
    cases = c15d.cases()
    need(len(cases) == 12, 'C15D source manifest not frozen')
    return cases

def prepass(original_path, budget=MAX_PREPASS_S):
    n, clauses = parse_dimacs(original_path)
    certs, reason = discover(n, clauses, budget=budget)
    mapping = replay(clauses, certs)
    reduced = reduce_clauses(n, clauses, mapping) if mapping else clauses
    return n, clauses, reduced, mapping, reason, certs

def trial(case, rep, arm, position, order_seed):
    import c15d_benchmark as c15d
    path = c15d.SRC / case['filename']
    need(digest(path) == case['sha256'], 'source SHA changed before trial')
    original_binary = pathlib.Path('c8c/bin/instrumented')
    need(original_binary.is_file(), 'pinned CaDiCaL missing')
    started = time.perf_counter()
    n, source, reduced, mapping, reason, certs = 0, [], [], {}, 'baseline', []
    if arm != 'baseline':
        n, source, reduced, mapping, reason, certs = prepass(path)
    prep_s = time.perf_counter() - started
    using_quotient = arm == 'quotient' and bool(mapping)
    # Research-only conditional no-vivify gate, not a validated predictor.
    # It uses only replay-proven structure, never labels or previous timings.
    disable_vivify = arm == 'selective_no_vivify' and len(mapping) >= 2
    temp = tempfile.TemporaryDirectory(prefix='drnas-mre12-')
    try:
        effective = path
        if using_quotient:
            effective = pathlib.Path(temp.name) / 'quotient.cnf'
            effective.write_text(encode(n, reduced), encoding='utf-8')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('DRNAS_C8', 'DRNAS_C14', 'DRNAS_C15'))}
        cmd = [str(original_binary.resolve())]
        if disable_vivify:
            cmd.append('--no-vivify')
        cmd.append(str(effective.resolve()))
        status, verified = 'TIMEOUT', False
        remaining = CAP - (time.perf_counter() - started)
        if remaining > 0.05:
            try:
                p = subprocess.run(cmd, capture_output=True, text=True,
                                   errors='replace', timeout=remaining, env=env)
                need(p.returncode in (10, 20), 'unexpected solver exit: ' + str(p.returncode))
                status, model = c15d.h.ref.external_parse(p)
                need(status == case['status'], 'reference contradiction')
                if status == 'SAT':
                    if using_quotient:
                        transformed_model = {v: bool(model.get(v, False)) for v in range(1, n + 1)}
                        need(model_satisfies(reduced, transformed_model), 'quotient witness invalid')
                        model = reconstruct(n, model, mapping)
                    c15d.h.cms.verify_model(path, model)
                    verified = True
                if time.perf_counter() - started >= CAP:
                    status, verified = 'TIMEOUT', False
            except subprocess.TimeoutExpired:
                status = 'TIMEOUT'
        elapsed = time.perf_counter() - started
        return dict(protocol=PROTO, arm=arm, cohort=case['cohort'], gbd=case['gbd'],
                    source_sha256=case['sha256'], rep=rep, position=position,
                    order_seed=order_seed, status=status, reference=case['status'],
                    model_on_original_verified=verified, independent_UNSAT_LRAT=False,
                    same_binary_sha256=digest(original_binary),
                    cap_s=CAP, PAR2_s=round(elapsed if status != 'TIMEOUT' else 2*CAP, 6),
                    elapsed_s=round(elapsed, 6), prep_s=round(prep_s, 6),
                    eligible_aliases=len(mapping), quotient_applied=using_quotient,
                    selective_novivify_applied=disable_vivify,
                    certificate_replayed=True, abstain_reason=reason,
                    source_clauses=len(source), transformed_clauses=len(reduced),
                    original_CNF_unchanged=True, solver_seed_independent=False)
    finally:
        temp.cleanup()

def shard(index):
    need(0 <= index < SHARDS, 'bad shard')
    cases = source_cases()
    rows = []
    OUT.mkdir(parents=True, exist_ok=True)
    for x in cases[index::SHARDS]:
        for rep in range(REPS):
            seed = int(hashlib.sha256((PROTO + x['sha256'] + str(rep)).encode()).hexdigest()[:8], 16)
            arms = list(ARMS)
            random.Random(seed).shuffle(arms)
            for position, arm in enumerate(arms):
                row = trial(x, rep, arm, position, seed)
                rows.append(row)
                (OUT / f'shard-{index}.json').write_text(json.dumps(rows, sort_keys=True) + '\n')
                print('MRE12_TRIAL ' + json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == 3 * REPS * len(ARMS), 'shard incomplete')
    print(f'MRE12_SHARD_PASS {index} {len(rows)}', flush=True)

def audit():
    cc = source_cases()
    rows = []
    for i in range(SHARDS):
        rows += json.loads((OUT / f'shard-{i}.json').read_text())
    expected = {(x['sha256'], a, rep) for x in cc for rep in range(REPS) for a in ARMS}
    got = {(r['source_sha256'], r['arm'], r['rep']) for r in rows}
    need(len(rows) == len(expected) == len(got) and got == expected, 'source/arm pairs incomplete')
    bysha = {x['sha256']: x for x in cc}
    binaries = set()
    for r in rows:
        c = bysha[r['source_sha256']]
        need(r['reference'] == c['status'] and r['cohort'] == c['cohort'] and
             r['protocol'] == PROTO and r['cap_s'] == CAP and r['certificate_replayed'],
             'audit row metadata mismatched')
        binaries.add(r['same_binary_sha256'])
        need(r['status'] in ('SAT', 'UNSAT', 'TIMEOUT'), 'unclassified solver status')
        if r['status'] == 'TIMEOUT':
            need(r['PAR2_s'] == 2 * CAP, 'timeout PAR2 incorrect')
        else:
            need(r['status'] == c['status'] and
                 (r['status'] != 'SAT' or r['model_on_original_verified']),
                 'witness or reference mismatch')
        if r['arm'] == 'quotient':
            need(r['quotient_applied'] == (r['eligible_aliases'] > 0), 'false quotient claim')
        if r['arm'] == 'selective_no_vivify':
            need(r['selective_novivify_applied'] == (r['eligible_aliases'] >= 2),
                 'selective gate provenance mismatch')
    need(len(binaries) == 1, 'different binaries across arms')
    def summarize(values):
        return {a: dict(attempts=len(group := [r for r in values if r['arm'] == a]),
                       solved=sum(r['status'] != 'TIMEOUT' for r in group),
                       PAR2_s=round(sum(r['PAR2_s'] for r in group), 6),
                       actual_quotient=sum(r['quotient_applied'] for r in group),
                       actual_no_vivify=sum(r['selective_novivify_applied'] for r in group),
                       proved_aliases=sum(r['eligible_aliases'] for r in group))
                for a in ARMS}
    report = dict(protocol=PROTO, total_trials=len(rows), original_sources=len(cc),
                  independent_solver_seeds=False, independent_UNSAT_LRAT=False,
                  global_blind=False, selective_gate_unvalidated=True,
                  scores=summarize(rows),
                  by_cohort={key: summarize([r for r in rows if r['cohort'] == key])
                             for key in sorted({r['cohort'] for r in rows})},
                  by_source={x['gbd']: summarize([r for r in rows if r['gbd'] == x['gbd']])
                             for x in cc})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print('MRE12_FINAL ' + json.dumps(report, sort_keys=True), flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=('selftest', 'verify', 'shard', 'audit'))
    p.add_argument('--shard', type=int, default=0)
    a = p.parse_args()
    if a.action == 'selftest':
        exhaustive_test()
    elif a.action == 'verify':
        need(len(source_cases()) == 12, 'source verification failed')
        print('MRE12_SOURCE_SHA_VERIFIED 12', flush=True)
    elif a.action == 'shard':
        shard(a.shard)
    else:
        audit()

if __name__ == '__main__':
    main()
