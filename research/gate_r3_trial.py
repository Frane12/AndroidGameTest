#!/usr/bin/env python3
"""GATE-R3 wake-only ablation. Frozen six-arm 30-category prospective test.
Reuses the pinned R2 measurement/verification code, not its benchmark outcomes.
Primary: R3 vs R2. Promotion reference: X46_GATE. NO_SHOCK is diagnostic only.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import random
import subprocess
from pathlib import Path
import gate_r2_trial as R

C, B = R.C, R.B
C.NAMESPACE = 'gate-r3-wake-only30-prospective-20261113-v1'
CAP, REPEATS, EACH, SHARDS = 2.0, 3, 20, 12
ARMS = {
    'CORE': ('build/drnas-x41', 'core'),
    'ADAPTIVE': ('build/drnas-x3', 'x3'),
    'X46_GATE': ('build/drnas-x46', 'x46_gate'),
    'GATE_R2': ('build/drnas-gate-r2', 'gate_r2'),
    'GATE_R3': ('build/drnas-gate-r3', 'gate_r3'),
    'R3_NO_SHOCK': ('build/drnas-gate-r3', 'gate_r3_no_shock'),
}
# The inherited functions look up these experiment-local mappings at call time.
R.ARMS = B.ARMS = ARMS
CODE = tuple(dict.fromkeys(R.CODE + (
    'research/build_gate_r3.py', 'research/gate_r3_trial.py',
    'tests/test_gate_r3.cpp', 'tests/test_gate_r3_report.py', 'README_GATE_R3.md',
    '.github/workflows/drnas-gate-r3-wake-only30.yml',
)))
emit, dump, summarize = R.emit, R.dump, R.summarize


def run_one(src, arm, parsed, cap=CAP):
    record = R.run_one(src, arm, parsed, cap)
    gate = record['gate']
    if arm in ('GATE_R3', 'R3_NO_SHOCK') and gate:
        if (gate.get('wake_decision_gap'), gate.get('wake_conflict_gap')) != (1024, 512):
            raise RuntimeError('Wrong R3 wake configuration')
        if gate.get('conflict_wake_disabled') != (arm == 'R3_NO_SHOCK'):
            raise RuntimeError('Wrong NO_SHOCK mode')
    return record


def comparison(rows, baseline, challenger='GATE_R3', iterations=2000):
    grouped = collections.defaultdict(list)
    metadata = {}
    for row in rows:
        sha = row['sha256']
        grouped[sha].append(row['arms'][challenger]['PAR2_s'] - row['arms'][baseline]['PAR2_s'])
        metadata[sha] = (row['category'], row['domain'])
    categories = collections.defaultdict(list)
    domains = collections.defaultdict(float)
    for sha, values in grouped.items():
        category, domain = metadata[sha]
        delta = sum(values)
        categories[category].append(delta)
        domains[domain] += delta
    rng = random.Random(463031)
    formula_boot, category_boot, domain_boot = [], [], []
    category_values = [sum(values) for _, values in sorted(categories.items())]
    domain_values = [value for _, value in sorted(domains.items())]
    for _ in range(iterations):
        formula_boot.append(sum(sum(rng.choice(v) for _ in v) for v in categories.values()))
        category_boot.append(sum(rng.choice(category_values) for _ in category_values))
        domain_boot.append(sum(rng.choice(domain_values) for _ in domain_values))
    def interval(values):
        values.sort()
        return [round(values[int(.025*iterations)], 7), round(values[int(.975*iterations)], 7)]
    return {
        'challenger': challenger, 'baseline': baseline,
        'delta_PAR2_s': round(sum(category_values), 7),
        'formula_clustered_stratified_95': interval(formula_boot),
        'category_clustered_95': interval(category_boot),
        'domain_clustered_95': interval(domain_boot),
        'formula_units': len(grouped), 'category_units': len(categories),
        'domain_units': len(domains), 'repeats_not_independent': True,
    }


def freeze(prior_dir):
    sources, text, sha = C.make_manifest('gate_r3_generated', EACH)
    history, files = set(), []
    if prior_dir:
        root = Path(prior_dir)
        files = sorted(set(root.rglob('manifest.json')) | set(root.rglob('frozen_manifest.json')))
        if not files:
            raise RuntimeError('Historical manifests missing')
        for file in files:
            data = json.loads(file.read_text())
            if not isinstance(data, list):
                raise RuntimeError('Invalid historical manifest')
            history.update(row['sha256'] for row in data)
        if history & {s['sha256'] for s in sources}:
            raise RuntimeError('Historical source overlap')
    dest = Path('gate_r3_frozen')
    dest.mkdir(exist_ok=True)
    (dest/'manifest.json').write_text(text)
    protocol = {
        'manifest_sha256': sha, 'namespace': C.NAMESPACE,
        'base_commit': '9a3f7f4c0f76510dc3022e1aa25044f7d29e642a',
        'sources': 600, 'categories': 30, 'each': EACH, 'repeats': REPEATS,
        'cap_s': CAP, 'shards': SHARDS, 'arms': list(ARMS),
        'expected_solver_runs': 600*REPEATS*len(ARMS),
        'historical_sha_checked': len(history), 'history_manifests': len(files),
        'generated_sat_only': True, 'primary': 'GATE_R3 vs GATE_R2',
        'promotion_reference': 'X46_GATE',
        'primary_success_rule': 'At least 5% lower PAR2; no fewer solved attempts or stable 3/3 sources; formula-clustered 95% upper endpoint below zero',
        'promotion_success_rule': 'Primary passes AND the same rule passes against X46_GATE; replication still required before production promotion',
        'single_change': 'Scale ONLY R2 conflict-wake thresholds by 4: decision gap/refractory 256->1024; new conflicts 128->512',
        'ablation': 'R3_NO_SHOCK disables only conflict wakes; periodic adaptive checks remain',
        'unchanged': ['online branch scorer', 'probe code', 'hysteresis', 'cost reservation',
                      'CHECK/ACTIVE/SLEEP strides', 'periodic checks', 'forgetting', 'logical inference'],
        'constants': {'wake_scale': 4, 'wake_decision_gap': 1024, 'wake_conflict_gap': 512,
                      'enable_proxy_ewma': .65, 'disable_proxy_ewma': .35,
                      'budget_base_s': .0005, 'budget_fraction_nonprobe': .02,
                      'cost_reserve_factor': 1.25},
        'no_outcome_based_filtering': True, 'no_cross_formula_memory': True,
        'limits': 'Generated SAT profiles, not 30 independent industrial domains. Local usefulness is not causal time saved. Speculative probes restore assignments, NOT full watch order. Three repeats are clustered per formula.',
        'code_sha256': {path: hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in CODE},
    }
    dump(dest/'protocol.json', protocol)
    emit('GATER3_FROZEN', protocol)


def manifest():
    raw = Path('gate_r3_frozen/manifest.json').read_bytes()
    p = json.loads(Path('gate_r3_frozen/protocol.json').read_text())
    if hashlib.sha256(raw).hexdigest() != p['manifest_sha256']:
        raise RuntimeError('Frozen manifest changed')
    if (p['arms'], p['namespace'], p['repeats'], p['cap_s']) != (list(ARMS), C.NAMESPACE, REPEATS, CAP):
        raise RuntimeError('Protocol drift')
    for path, digest in p['code_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Code drift: ' + path)
    return json.loads(raw), p


def shard(number):
    frozen, p = manifest()
    dest = Path('gate_r3_stage')
    dest.mkdir(exist_ok=True)
    selected = [row for row in frozen if row['id'] % SHARDS == number]
    rows, counts = [], collections.Counter()
    with (dest/'trials.jsonl').open('w') as out:
        for index, meta in enumerate(selected):
            src = C.generate(meta['category'], meta['replicate_id'], 'gate_r3_generated')
            if src['sha256'] != meta['sha256']:
                raise RuntimeError('Source changed')
            parsed = B.problem(src['path'])
            for rep in range(REPEATS):
                order = list(ARMS)
                shift = (index*REPEATS + rep) % len(order)
                order = order[shift:] + order[:shift]
                arms = {arm: run_one(src, arm, parsed) for arm in order}
                row = {k: meta[k] for k in ('id', 'sha256', 'category', 'domain')}
                row.update(repeat=rep, shard=number, order=order, arms=arms)
                out.write(json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n')
                out.flush()
                rows.append(row)
                for arm, result in arms.items():
                    counts[arm+'_solved'] += result['status'] == 'SAT_VERIFIED'
                    counts[arm+'_PAR2_s'] += result['PAR2_s']
            if (index+1) % 10 == 0:
                emit('GATER3_PROGRESS', {'shard': number, 'sources_done': index+1, 'total': len(selected), **counts})
    report = {'shard': number, 'sources': len(selected), 'paired_rows': len(rows),
              'manifest_sha256': p['manifest_sha256'], 'arms': summarize(rows)}
    dump(dest/'report.json', report)
    emit('GATER3_SHARD_FINAL', report)


def finish():
    frozen, p = manifest()
    rows = []
    for number in range(SHARDS):
        folder = Path('gate_r3_downloads')/f'gate-r3-wake30-{number}'
        report = json.loads((folder/'report.json').read_text())
        if report['manifest_sha256'] != p['manifest_sha256'] or report['shard'] != number:
            raise RuntimeError('Wrong shard manifest')
        part = [json.loads(line) for line in (folder/'trials.jsonl').read_text().splitlines()]
        if any(row['shard'] != number for row in part):
            raise RuntimeError('Misfiled trial')
        rows.extend(part)
    B.validate(rows, frozen)
    rows.sort(key=lambda r: (r['id'], r['repeat']))
    for row in rows:
        for arm in ('GATE_R2', 'GATE_R3', 'R3_NO_SHOCK'):
            value = row['arms'][arm]
            gate = value['gate']
            if not gate:
                continue  # Killed process remains penalized UNKNOWN, never inferred SAT.
            if gate['proxy_good'] + gate['proxy_bad'] != gate['observations']:
                raise RuntimeError('Feedback accounting failed')
            if gate['observations'] != value['updates'] or gate['observations'] > gate['rounds'] or gate['rounds'] > gate['permits']:
                raise RuntimeError('Probe accounting failed')
            if arm != 'GATE_R2':
                if (gate['wake_decision_gap'], gate['wake_conflict_gap']) != (1024, 512):
                    raise RuntimeError('R3 threshold drift')
                if gate['conflict_wake_disabled'] != (arm == 'R3_NO_SHOCK'):
                    raise RuntimeError('Wrong conflict-wake ablation')
                if arm == 'R3_NO_SHOCK' and gate['shock_wakes'] != 0:
                    raise RuntimeError('Disabled conflict wake occurred')
    overall = summarize(rows)
    categories = {c: summarize([row for row in rows if row['category'] == c]) for c, _ in C.SPECS}
    if len(categories) != 30 or any(v['CORE']['sources'] != 20 for v in categories.values()):
        raise RuntimeError('Category coverage incomplete')
    comparisons = {arm: comparison(rows, arm) for arm in ARMS if arm != 'GATE_R3'}
    def passes(baseline):
        new, old = overall['GATE_R3'], overall[baseline]
        return (new['PAR2_s'] <= .95*old['PAR2_s'] and new['SAT_verified'] >= old['SAT_verified']
                and new['stable_solved_sources'] >= old['stable_solved_sources']
                and comparisons[baseline]['formula_clustered_stratified_95'][1] < 0)
    primary, promotion = passes('GATE_R2'), passes('GATE_R2') and passes('X46_GATE')
    if overall['GATE_R3']['gate_totals']['observations'] <= 0:
        raise RuntimeError('R3 never exercised')
    report = {
        'status': 'COMPLETE', 'protocol': p, 'overall': overall, 'categories': categories,
        'domains': {d: summarize([r for r in rows if r['domain'] == d]) for d in sorted({d for _, d in C.SPECS})},
        'shards': {str(i): summarize([r for r in rows if r['shard'] == i]) for i in range(SHARDS)},
        'comparisons': comparisons,
        'no_shock_vs_r2': comparison(rows, 'GATE_R2', 'R3_NO_SHOCK'),
        'primary_success_rule_pass': primary, 'promotion_rule_pass': promotion,
        'limits': p['limits'],
    }
    dest = Path('gate_r3_final')
    dest.mkdir(exist_ok=True)
    dump(dest/'report.json', report)
    (dest/'paired_trials.jsonl').write_text(''.join(json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n' for row in rows))
    lines = ['## GATE-R3 wake-only30 — 600 generated SAT CNFs, three repeats, six arms', '',
             '| Arm | SAT /1800 | Stable /600 | PAR2 s | E2E s | Probe s | Conflict wakes | Periodic wakes |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for arm, value in overall.items():
        g = value['gate_totals']
        lines.append(f"| {arm} | {value['SAT_verified']} | {value['stable_solved_sources']} | {value['PAR2_s']:.4f} | {value['e2e_s']:.4f} | {value['probe_seconds']:.4f} | {g['shock_wakes']} | {g['periodic_wakes']} |")
    lines += ['', '| Category | CORE | ADAPTIVE | X46 GATE | R2 | R3 | NO SHOCK |', '|---|---:|---:|---:|---:|---:|---:|']
    for category, _ in C.SPECS:
        lines.append('| '+category+' | '+' | '.join(f"{categories[category][arm]['PAR2_s']:.3f}" for arm in ARMS)+' |')
    lines += ['', f'Primary success vs R2: **{primary}**. Promotion criterion vs X46: **{promotion}**. Negative deltas favor R3.']
    for arm, comp in comparisons.items():
        lines.append(f"- R3 vs {arm}: delta {comp['delta_PAR2_s']:.4f}s; formula 95% {comp['formula_clustered_stratified_95']}; category 95% {comp['category_clustered_95']}; domain 95% {comp['domain_clustered_95']}.")
    lines += ['', p['limits']]
    text = '\n'.join(lines)+'\n'
    (dest/'summary.md').write_text(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(text)
    emit('GATER3_FINAL', {'status': 'COMPLETE', 'sources': 600, 'categories': 30,
                         'solver_runs': 10800, 'overall': overall, 'comparisons': comparisons,
                         'primary_success_rule_pass': primary, 'promotion_rule_pass': promotion})


def selftest():
    subprocess.run(['build/test-gate-r3'], check=True)
    R.selftest()  # Inherited exact-oracle test uses experiment-local ARMS above.
    emit('GATER3_SELFTEST_PASS', {'exact_oracle_runs': 600, 'categories': 30,
                                 'threshold_boundary_tests': True, 'no_shock_equivalence_events': 10000})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('selftest', 'freeze', 'shard', 'finish'))
    parser.add_argument('--shard', type=int, default=0)
    parser.add_argument('--prior-dir')
    args = parser.parse_args()
    if args.command == 'selftest': selftest()
    elif args.command == 'freeze': freeze(args.prior_dir)
    elif args.command == 'finish': finish()
    else:
        if args.shard not in range(SHARDS): parser.error('Invalid shard')
        shard(args.shard)
