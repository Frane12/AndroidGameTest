#!/usr/bin/env python3
"""Summarize C1 reason concentration and incomplete native telemetry.

Input: C1 all-trials.json from the original audit artifact. Counts on runs
without terminal native output are lower bounds, not proof of inactivity.
"""
import argparse
import collections
import json
import pathlib


def analyze(rows, mode):
    selected = [r for r in rows if r.get('mode') == mode]
    if not selected:
        raise ValueError(f'no rows for mode {mode!r}')
    keys = [(r['sha256'], r['rep']) for r in selected]
    if len(keys) != len(set(keys)):
        raise ValueError('duplicate source/repetition in selected mode')
    per_source = collections.defaultdict(lambda: {'repetitions': 0, 'proposals': 0, 'completed_reasons': 0, 'timeouts': 0, 'missing_terminal': 0})
    for r in selected:
        g = per_source[r['sha256']]
        g['id'] = r['id']
        g['repetitions'] += 1
        g['proposals'] += int(r.get('native_proposals', 0))
        g['completed_reasons'] += int(r.get('native_reasons', 0))
        g['timeouts'] += r['status'] == 'TIMEOUT'
        g['missing_terminal'] += r['status'] == 'TIMEOUT' and r.get('native_started') == mode and r.get('native_mode') is None
    sources = [{'sha256': sha, **data} for sha, data in per_source.items()]
    sources.sort(key=lambda x: (-x['completed_reasons'], x['sha256']))
    return {'mode': mode, 'attempts': len(selected), 'sources': len(sources),
            'sources_with_recorded_reasons': sum(x['completed_reasons'] > 0 for x in sources),
            'recorded_proposals': sum(x['proposals'] for x in sources),
            'recorded_completed_reasons': sum(x['completed_reasons'] for x in sources),
            'timeouts_without_terminal_telemetry': sum(x['missing_terminal'] for x in sources),
            'interpretation': 'Recorded counts can be incomplete on timeout; association is not causation.',
            'by_source': sources}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trials', type=pathlib.Path)
    parser.add_argument('--mode', default='c1_lazy_cooldown')
    args = parser.parse_args()
    rows = json.loads(args.trials.read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise ValueError('expected a JSON array of trial records')
    print(json.dumps(analyze(rows, args.mode), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
