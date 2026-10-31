"""Locked V10 holdout: test frozen V9.9 Auto against two 2026-era solvers.

Six 2026 formulas excluded from the V9.9 final test and diagnostic set.
These may still have appeared in EARLIER project experiments.
"""
import csv
import importlib.util
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
MODES = ('drnas-v99', 'cadical3', 'kissat-lr-ds')
CAP, REPEATS, N = 10, (1, 2), 6


def load_v99():
    module = ROOT / 'research/drnas-sat-v9-9/competition.py'
    spec = importlib.util.spec_from_file_location('drnas_v99_competition', module)
    comp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(comp)
    return comp


def freeze():
    pool = {}
    for filename in ('old/official_v94_manifest.json', 'new/official_v96_manifest.json'):
        for case in json.loads(Path(filename).read_text())['cases']:
            pool[case['id']] = case
    assert len(pool) == 24, 'changed source manifest'
    baseline = json.loads(Path('baseline/plan.json').read_text())
    excluded = {case['id'] for case in baseline} | set(load_v99().KNOWN7)
    available = [case for case in pool.values() if case['id'] not in excluded]
    selected = []
    for label in ('SAT', 'UNSAT'):
        ordered = sorted((c for c in available if c['official_label'] == label),
                         key=lambda c: (c['sha256'], c['id']))
        selected.extend(ordered[:3])
    already = {c['id'] for c in selected}
    if len(selected) < N:
        rest = sorted((c for c in available if c['id'] not in already),
                      key=lambda c: (c['sha256'], c['id']))
        selected.extend(rest[:N - len(selected)])
    assert len(selected) == N and {c['official_label'] for c in selected} == {'SAT', 'UNSAT'}
    plan = [dict(id=c['id'], sha256=c['sha256'],
                 label=c['official_label'], group='not-in-v99-final') for c in selected]
    assert len({c['id'] for c in plan}) == N
    Path('plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    print('Frozen by input SHA only, no DRNAS score was used for selection')
    print(Path('plan.json').read_text())


def trial(index):
    assert index in range(N)
    comp = load_v99()
    comp.CAP = CAP
    comp.MODES = MODES
    # Reuse v9.9 CPU pinning, SHA checks, randomized order and label/model validation.
    comp.trial(index)


def aggregate(rows, plan):
    expected = {(case['id'], mode, repeat) for case in plan
                for mode in MODES for repeat in REPEATS}
    keys = [(r['case'], r['mode'], int(r['repeat'])) for r in rows]
    assert len(keys) == len(expected) == N * len(MODES) * len(REPEATS)
    assert set(keys) == expected, 'duplicate or missing runs'
    assert all(r['status'] in ('solved', 'timeout', 'execution-failure') for r in rows)
    for r in rows:
        if r['status'] == 'solved':
            assert r['validation'] in ('SAT-model-verified', 'official-label', 'official-label-only')
            assert 0 <= float(r['wall_s']) <= CAP + 0.3
    def cost(r):
        return float(r['wall_s']) if r['status'] == 'solved' else 2 * CAP
    lines = [
        '# DRNAS V10 — unchanged V9.9 Auto on additional 2026 formulas', '',
        'Six CNFs outside V9.9 final and diagnostic selection. These were NOT '
        'guaranteed unseen to earlier DRNAS experiments.',
        '2 runs/formula/solver, same CPU core, 10 s cap; PAR-2 is 20 s on timeout/error.',
        '',
        '| Solver | Solved/12 | Failed execution | Mean PAR-2 s |',
        '|---|---:|---:|---:|']
    for mode in sorted(MODES, key=lambda m: statistics.mean(cost(r) for r in rows if r['mode'] == m)):
        sample = [r for r in rows if r['mode'] == mode]
        lines.append(f"| {mode} | {sum(r['status'] == 'solved' for r in sample)} | "
                     f"{sum(r['status'] == 'execution-failure' for r in sample)} | "
                     f"{statistics.mean(cost(r) for r in sample):.4f} |")
    lines += ['', '| CNF | ' + ' | '.join(MODES) + ' |',
              '|---|' + '---:|' * len(MODES)]
    for case in plan:
        values = []
        for mode in MODES:
            sample = [r for r in rows if r['case'] == case['id'] and r['mode'] == mode]
            solved = [float(r['wall_s']) for r in sample if r['status'] == 'solved']
            values.append(f"{statistics.mean(solved):.3f} ({len(solved)}/2)"
                          if solved else 'timeout/error')
        lines.append('| ' + case['id'][:12] + ' ' + case['label'] + ' | ' +
                     ' | '.join(values) + ' |')
    lines += ['', 'Failed/timeout trials counted in denominator.',
              'SAT witness checked only when emitted; UNSAT follows official labels, '
              'not independent local UNSAT certificates.',
              'No general/record claim from this six-formula sample.']
    return '\n'.join(lines) + '\n'


def audit():
    plan = json.loads(Path('plan.json').read_text())
    files = sorted(Path('trials').glob('trial-*.json'))
    assert len(files) == N, 'missing shards'
    rows = [r for f in files for r in json.loads(f.read_text())]
    report = aggregate(rows, plan)
    with Path('v100-results.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    Path('v100-summary.md').write_text(report)
    print(report)


def selftest():
    plan = [dict(id=f'case{i}', label='SAT') for i in range(N)]
    rows = [dict(case=p['id'], mode=m, repeat=n, status='solved',
                 wall_s=0.1, validation='SAT-model-verified')
            for p in plan for m in MODES for n in REPEATS]
    assert '12 | 0 | 0.1000' in aggregate(rows, plan)
    for invalid in (rows[:-1], [dict(rows[0], status='error')] + rows[1:],
                    [dict(rows[0], validation='unverified')] + rows[1:]):
        try:
            aggregate(invalid, plan)
        except AssertionError:
            pass
        else:
            raise AssertionError('audit failed to reject invalid rows')
    print('V10 preflight OK')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'trial':
        trial(int(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] in ('freeze', 'audit', 'selftest'):
        globals()[sys.argv[1]]()
    else:
        raise SystemExit('usage: holdout.py freeze|trial INDEX|audit|selftest')
