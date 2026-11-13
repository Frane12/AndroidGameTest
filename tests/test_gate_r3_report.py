#!/usr/bin/env python3
"""Mock complete aggregation and adversarial audit checks. NOT performance data."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'research'))
import gate_r3_trial as T


def main():
    frozen, protocol = T.manifest()
    allrows = []
    for meta in frozen:
        for rep in range(T.REPEATS):
            arms = {}
            for arm in T.ARMS:
                gate = {key: 0 for key in T.R.GATE_FIELDS}
                gate.update(calls=100, permits=1, rounds=1, proxy_good=1,
                            observations=1, wake_decision_gap=1024, wake_conflict_gap=512,
                            conflict_wake_disabled=(arm == 'R3_NO_SHOCK'))
                arms[arm] = {'status': 'SAT_VERIFIED', 'e2e_s': .01, 'PAR2_s': .01,
                             'process_s': .009, 'verify_and_parse_s': .001,
                             'late_verified': False, 'decisions': 100, 'conflicts': 10,
                             'probe_seconds': .00001, 'counterfactuals': 6,
                             'updates': 1, 'interventions': 1, 'gate': gate}
            row = {k: meta[k] for k in ('id', 'sha256', 'category', 'domain')}
            row.update(repeat=rep, shard=meta['id'] % T.SHARDS, order=list(T.ARMS), arms=arms)
            allrows.append(row)
    assert T.B.validate(allrows, frozen)
    try: T.B.validate(allrows[:-1] + [allrows[0]], frozen)
    except RuntimeError: pass
    else: raise AssertionError('Duplicate not rejected')
    assert T.comparison(allrows, 'GATE_R2', iterations=50)['formula_clustered_stratified_95'] == [0., 0.]
    assert T.comparison(allrows, 'GATE_R2', 'R3_NO_SHOCK', 50)['delta_PAR2_s'] == 0.
    before = Path.cwd()
    summary = os.environ.pop('GITHUB_STEP_SUMMARY', None)
    actual_manifest = T.manifest
    try:
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            T.manifest = lambda: (frozen, protocol)
            for i in range(T.SHARDS):
                folder = Path('gate_r3_downloads')/f'gate-r3-wake30-{i}'
                folder.mkdir(parents=True)
                (folder/'report.json').write_text(json.dumps({'shard': i, 'manifest_sha256': protocol['manifest_sha256']}))
                (folder/'trials.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in allrows if r['shard'] == i))
            with contextlib.redirect_stdout(io.StringIO()): T.finish()
            report = json.loads(Path('gate_r3_final/report.json').read_text())
            assert report['status'] == 'COMPLETE'
            assert len(report['categories']) == 30 and len(report['shards']) == 12
            assert report['overall']['GATE_R3']['SAT_verified'] == 1800
            assert report['overall']['GATE_R3']['stable_solved_sources'] == 600
            assert not report['primary_success_rule_pass'] and not report['promotion_rule_pass']
            # A disabled shock wake must be caught even if all CNF hashes match.
            p = Path('gate_r3_downloads/gate-r3-wake30-0/trials.jsonl')
            part = [json.loads(line) for line in p.read_text().splitlines()]
            part[0]['arms']['R3_NO_SHOCK']['gate']['shock_wakes'] = 1
            p.write_text(''.join(json.dumps(r)+'\n' for r in part))
            try: T.finish()
            except RuntimeError as exc: assert 'Disabled conflict wake' in str(exc)
            else: raise AssertionError('NO_SHOCK contamination not rejected')
    finally:
        T.manifest = actual_manifest
        os.chdir(before)
        if summary is not None: os.environ['GITHUB_STEP_SUMMARY'] = summary
    print('GATER3_MOCK_REPORT_PASS synthetic_rows=1800 duplicate_and_ablation_audits=True NOT_PERFORMANCE_DATA')


if __name__ == '__main__': main()
