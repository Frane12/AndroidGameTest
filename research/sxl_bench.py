#!/usr/bin/env python3
"""DRNAS SXL: source-proved ANF lemmas selected by bounded binary lookahead.

Reference-only screening, reused official EQUIV7 originals, one CPU, full E2E.
The tree is an offline selector, never an independent SAT/UNSAT solver.
"""
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import resource
import tempfile
import time

import dmd1_bench as d1

ROOT = pathlib.Path('mre_sxl')
GEN = ROOT / 'bin/dmd3x_native'
TREE = ROOT / 'bin/sxl_tree_gate'
KISSAT = pathlib.Path('built/bin/kissat_4_0_4')
PINNED_KISSAT = 'c96ebe32a7e333a02acad462679a0bbfbeeec54a7f9210421c4c0c8d53bbf95f'
PROTO = 'DRNAS-SXL-ANF-BINARY-TREE-ONECPU-E2E-v1'
ARMS = ('kissat_original', 'sxl_all', 'sxl_root', 'sxl_tree1', 'sxl_tree3', 'sxl_tree3_shadow')
REPS = 3
SHARDS = 4
CAP = 6.0
SCREEN_CAP = 4.0
TREE_BUDGET_MS = 80


def need(ok, message):
    if not ok:
        raise RuntimeError('SXL_REFUSED ' + message)


def core():
    return min(os.sched_getaffinity(0))


def pin():
    os.sched_setaffinity(0, {core()})


def cpu_time():
    return sum(u.ru_utime + u.ru_stime for u in
               (resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)))


def write_cnf(path, n, clauses):
    pathlib.Path(path).write_text('p cnf %d %d\n' % (n, len(clauses)) +
                                ''.join(' '.join(map(str, c)) + ' 0\n' for c in clauses))


def checked_sources():
    manifest = json.loads(pathlib.Path('mre_equiv7/manifest.json').read_text())
    need(len(manifest['cases']) == 48, 'frozen 48-source registry changed')
    need(d1.sha(KISSAT) == PINNED_KISSAT, 'pinned Kissat binary changed')
    result = []
    for c in sorted(manifest['cases'], key=lambda x: x['sha256']):
        p = pathlib.Path('mre_equiv7/cases') / c['filename']
        need(d1.sha(p) == c['sha256'], 'original SHA mismatch')
        result.append(dict(sha256=c['sha256'], filename=c['filename'], path=str(p), year=c.get('year')))
    need(len({c['sha256'] for c in result}) == 48, 'duplicate originals')
    return result


def screen():
    pin()
    ROOT.mkdir(parents=True, exist_ok=True)
    records = []
    for c in checked_sources():
        _, original = d1.read_cnf(c['path'])
        rc, out, err, elapsed, _, timed = d1.run_process([KISSAT, '--seed=1000', c['path']], SCREEN_CAP, core())
        status, witness = ('TIMEOUT', False) if timed else d1.outcome(rc, out, original)
        row = dict(**c, reference_status=status, reference_s=round(elapsed, 6),
                   SAT_original_witness_verified=witness, eligible=not timed)
        records.append(row)
        print('SXL_REFERENCE_SCREEN', json.dumps(row, sort_keys=True), flush=True)
    # Freeze before any SXL run. All reference-completed sources are retained,
    # capped at 16 by source SHA, with no SXL result or tree feature involved.
    selected = [r for r in records if r['eligible']][:16]
    need(len(selected) >= 4, 'fewer than four reference-completed sources; no silent hard-source fill')
    freeze = dict(protocol=PROTO, reference_screen_cap_s=SCREEN_CAP, selection='reference-only completion then source SHA first16',
                  cases=selected, screen=records, globally_unseen=False, reused_EQUIV7=True,
                  arms=ARMS, reps=REPS, cap_s=CAP, binary_sha256=PINNED_KISSAT,
                  expected_trials=len(selected) * len(ARMS) * REPS)
    (ROOT / 'freeze.json').write_text(json.dumps(freeze, indent=2, sort_keys=True) + '\n')
    print('SXL_FREEZE_PASS', json.dumps({k: v for k, v in freeze.items() if k not in ('cases', 'screen')}, sort_keys=True), flush=True)


def frozen():
    data = json.loads((ROOT / 'freeze.json').read_text())
    need(data['protocol'] == PROTO and data['binary_sha256'] == d1.sha(KISSAT), 'freeze/binary drift')
    registry = {c['sha256']: c for c in checked_sources()}
    need(4 <= len(data['cases']) <= 16, 'invalid frozen source count')
    for c in data['cases']:
        need(c['sha256'] in registry and c['path'] == registry[c['sha256']]['path'] and c['eligible'], 'frozen source drift')
    return data


def extract(source, work, remaining):
    aug, cert = work / 'all.cnf', work / 'proof.json'
    rc, out, err, _, _, timed = d1.run_process([GEN, source, aug, cert, 20, 64, 'all'], remaining, core())
    if timed:
        return None
    need(rc == 0 and cert.is_file(), 'native ANF extraction failed ' + err[-200:])
    proof = json.loads(cert.read_text())
    need(proof['dmd3x_protocol'] == 'DMD3X-NATIVE-STRUCTURE-ROOT-BCP-v1' and proof['gate_mode'] == 'all', 'generator version changed')
    d1.proof_replay(pathlib.Path(source), aug, proof)
    return aug, proof


def choose(source, aug, proof, work, depth, remaining):
    selected, meta = work / 'selected.cnf', work / 'tree.json'
    rc, out, err, _, _, timed = d1.run_process(
        [TREE, source, aug, selected, meta, depth, TREE_BUDGET_MS, 2], remaining, core())
    if timed:
        return None
    need(rc == 0 and meta.is_file(), 'binary tree selector failed ' + err[-200:])
    data = json.loads(meta.read_text())
    ids = data['selected_indices']
    need(data['protocol'] == 'DRNAS-SXL-BINARY-LOOKAHEAD-v1' and data['depth'] == depth, 'tree protocol drift')
    need(data['candidates'] == len(proof['lemmas']) and len(ids) == data['selected'] <= 2 and len(ids) == len(set(ids)), 'invalid selected count')
    need(all(type(i) is int and 0 <= i < len(proof['lemmas']) for i in ids), 'unproved lemma index')
    need(not data['budget_exhausted'] or not ids, 'partial over-budget selection used')
    need(selected.exists() == bool(ids), 'selector output presence mismatch')
    if ids:
        n, original = d1.read_cnf(source)
        nn, actual = d1.read_cnf(selected)
        extra = [tuple(proof['lemmas'][i]['clause']) for i in ids]
        need(n == nn and actual == original + extra, 'branch assumptions or unproved clauses injected')
    return selected, data


def trial(case, arm, rep):
    start, before_cpu = time.monotonic(), cpu_time()
    source = pathlib.Path(case['path'])
    need(d1.sha(source) == case['sha256'], 'original changed before trial')
    _, original = d1.read_cnf(source)
    status, witness, target = 'TIMEOUT', False, source
    candidates, injected, proof_replayed = 0, 0, arm == 'kissat_original'
    gate = {}
    with tempfile.TemporaryDirectory(prefix='sxl-') as td:
        work = pathlib.Path(td)
        ready = True
        if arm != 'kissat_original':
            result = extract(source, work, max(0.001, CAP - (time.monotonic() - start)))
            ready = result is not None
            if ready:
                aug, proof = result
                candidates = len(proof['lemmas'])
                proof_replayed = True
                if candidates:
                    if arm == 'sxl_all':
                        target, injected = aug, candidates
                    else:
                        depth = 0 if arm == 'sxl_root' else 1 if arm == 'sxl_tree1' else 3
                        result = choose(source, aug, proof, work, depth, max(0.001, CAP - (time.monotonic() - start)))
                        ready = result is not None
                        if ready:
                            selected, gate = result
                            if gate['selected'] and arm != 'sxl_tree3_shadow':
                                target, injected = selected, gate['selected']
        prep = time.monotonic() - start
        remaining = CAP - prep
        if ready and remaining > 0:
            rc, out, err, _, _, timed = d1.run_process([KISSAT, '--seed=%d' % (1001 + rep), target], remaining, core())
            if not timed:
                status, witness = d1.outcome(rc, out, original)
    elapsed = time.monotonic() - start
    return dict(protocol=PROTO, source_sha256=case['sha256'], filename=case['filename'], arm=arm, rep=rep,
                seed=1001 + rep, status=status, SAT_original_witness_verified=witness,
                UNSAT_independent_LRAT=False, E2E_s=round(elapsed, 6),
                PAR2_s=round(elapsed if status != 'TIMEOUT' else 2 * CAP, 6), cap_s=CAP,
                full_CPU_s=round(cpu_time() - before_cpu, 6), prep_s=round(prep, 6),
                candidates=candidates, injected=injected, source_local_proofs_replayed=proof_replayed,
                gate=gate, cpu_affinity=sorted(os.sched_getaffinity(0)),
                binary_sha256=d1.sha(KISSAT), generator_sha256=d1.sha(GEN), tree_sha256=d1.sha(TREE),
                original_SHA_verified=True, globally_unseen=False)


def bench(shard):
    pin()
    need(0 <= shard < SHARDS, 'bad shard')
    freeze = frozen()
    rows = []
    for i, case in enumerate(freeze['cases']):
        if i % SHARDS != shard:
            continue
        for rep in range(REPS):
            arms = list(ARMS)
            random.Random(int(case['sha256'][:12], 16) + rep).shuffle(arms)
            for arm in arms:
                row = trial(case, arm, rep)
                row['shard'] = shard
                rows.append(row)
                print('SXL_TRIAL', json.dumps(row, sort_keys=True), flush=True)
    (ROOT / ('shard-%d.json' % shard)).write_text(json.dumps(rows, indent=2, sort_keys=True) + '\n')
    print('SXL_SHARD_PASS', shard, len(rows), flush=True)


def score(rows):
    return dict(trials=len(rows), solved=sum(r['status'] != 'TIMEOUT' for r in rows),
                SAT_verified=sum(r['SAT_original_witness_verified'] for r in rows),
                UNSAT_backend_no_LRAT=sum(r['status'] == 'UNSAT' for r in rows),
                PAR2_s=round(sum(r['PAR2_s'] for r in rows), 6),
                full_CPU_s=round(sum(r['full_CPU_s'] for r in rows), 6),
                prep_s=round(sum(r['prep_s'] for r in rows), 6),
                injected=sum(r['injected'] for r in rows),
                tree_nodes=sum(r['gate'].get('nodes', 0) for r in rows),
                tree_budget_abstentions=sum(bool(r['gate'].get('budget_exhausted')) for r in rows))


def audit():
    freeze = frozen()
    rows = sum((json.loads((ROOT / ('shard-%d.json' % i)).read_text()) for i in range(SHARDS)), [])
    expected = {(c['sha256'], arm, rep) for c in freeze['cases'] for arm in ARMS for rep in range(REPS)}
    observed = {(r['source_sha256'], r['arm'], r['rep']) for r in rows}
    need(len(rows) == len(expected) == len(observed) and expected == observed, 'missing/duplicate trials')
    need(all(r['protocol'] == PROTO and len(r['cpu_affinity']) == 1 and r['cap_s'] == CAP and
             r['original_SHA_verified'] and r['binary_sha256'] == PINNED_KISSAT for r in rows), 'source/CPU/protocol mismatch')
    need(len({r['generator_sha256'] for r in rows}) == len({r['tree_sha256'] for r in rows}) == 1, 'native binaries differ across shards')
    need(all(r['status'] != 'SAT' or r['SAT_original_witness_verified'] for r in rows), 'SAT witness missing')
    need(all(not r['injected'] or r['source_local_proofs_replayed'] for r in rows), 'unproved clauses injected')
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r['source_sha256']].append(r)
    for rs in groups.values():
        need(len({r['status'] for r in rs if r['status'] != 'TIMEOUT'}) <= 1, 'SAT/UNSAT disagreement')
    scores = {a: score([r for r in rows if r['arm'] == a]) for a in ARMS}
    reference = scores['kissat_original']['PAR2_s']
    for v in scores.values():
        v['PAR2_speedup_vs_kissat'] = round(reference / v['PAR2_s'], 6)
    paired = {}
    for arm in ARMS[1:]:
        differences = []
        for sha, rs in groups.items():
            for rep in range(REPS):
                ours = next(r for r in rs if r['arm'] == arm and r['rep'] == rep)
                base = next(r for r in rs if r['arm'] == 'kissat_original' and r['rep'] == rep)
                differences.append(dict(sha256=sha, rep=rep, delta_PAR2_s=round(ours['PAR2_s'] - base['PAR2_s'], 6),
                                        ours_status=ours['status'], reference_status=base['status']))
        paired[arm] = dict(best=sorted(differences, key=lambda r: r['delta_PAR2_s'])[:3],
                           regressions=sorted(differences, key=lambda r: -r['delta_PAR2_s'])[:3])
    report = dict(protocol=PROTO, audit='PASS', total_trials=len(rows), original_sources=len(groups), reps=REPS,
                  one_logical_CPU_per_trial=True, globally_unseen=False, reference_selected=True,
                  bounded_tree_is_only_diagnostic=True, E2E_includes_all_preprocessing=True,
                  SAT_original_witness_verified=True, UNSAT_independent_LRAT=False, no_auto_promotion=True,
                  scores=scores, per_shard={str(i): {a: score([r for r in rows if r['shard'] == i and r['arm'] == a])
                                                   for a in ARMS} for i in range(SHARDS)}, paired=paired)
    (ROOT / 'audit.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print('SXL_FINAL', json.dumps(report, sort_keys=True), flush=True)


def selftest():
    pin()
    rc, out, err, _, _, timed = d1.run_process([TREE, 'selftest'], 5, core())
    need(not timed and rc == 0 and 'SXL_NATIVE_SELFTEST_PASS ' in out, 'native closure selftest failed ' + err)
    print(out.strip(), flush=True)
    checks = 0
    rng = random.Random(7719)
    with tempfile.TemporaryDirectory(prefix='sxl-selftest-') as td:
        work = pathlib.Path(td)
        for i in range(48):
            n = rng.randint(2, 7)
            clauses = [tuple((1 if rng.randrange(2) else -1) * v for v in rng.sample(range(1, n + 1), rng.randint(1, min(3, n))))
                       for _ in range(rng.randint(3, 14))]
            source = work / ('random-%d.cnf' % i)
            write_cnf(source, n, clauses)
            result = extract(source, work, 3)
            need(result is not None, 'random extraction timeout')
            aug, proof = result
            lemmas = [tuple(l['clause']) for l in proof['lemmas']]
            for bits in itertools.product((False, True), repeat=n):
                vals = dict(zip(range(1, n + 1), bits))
                need(d1.holds(clauses, vals) == d1.holds(clauses + lemmas, vals), 'full model set changed')
            if lemmas:
                for depth in (0, 1, 3):
                    # Fresh paths: absence of a selected output is significant.
                    with tempfile.TemporaryDirectory(dir=work) as gd:
                        selection = choose(source, aug, proof, pathlib.Path(gd), depth, 3)
                        need(selection is not None, 'random gate timeout')
                        checks += 1
            checks += 1
            if aug.exists():
                aug.unlink()
        # Exact branch-only novelty example and output-subset validation.
        source = work / 'branch.cnf'
        write_cnf(source, 3, [(1, 2, 3), (1, 2, -3)])
        aug = work / 'branch-all.cnf'
        write_cnf(aug, 3, [(1, 2, 3), (1, 2, -3), (1, 2)])
        proof = {'lemmas': [{'clause': [1, 2]}]}
        for depth in (0, 1, 3):
            with tempfile.TemporaryDirectory(dir=work) as gd:
                _, data = choose(source, aug, proof, pathlib.Path(gd), depth, 3)
                need(data['selected'] == (0 if depth == 0 else 1), 'branch-only selection regression')
                checks += 1
    print('SXL_SELFTEST_PASS', json.dumps(dict(checks=checks, exhaustive_model_sets=48,
                                             source_proof_replay=True, conditional_units_never_injected=True)), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('selftest', 'screen', 'bench', 'audit'))
    parser.add_argument('--shard', type=int, default=0)
    args = parser.parse_args()
    if args.mode == 'bench':
        bench(args.shard)
    else:
        globals()[args.mode]()
