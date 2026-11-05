#!/usr/bin/env python3
"""R24 live telemetry pilot: actual paired monitor/forced runs, never train on test.

This is a diagnostic study, not a frozen predictive rule or certified UNSAT.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import threading
import time

CAP = 2.0
REPEATS = 2
OUT = Path('drnas-r24-pilot')
SEED_OFFSET = 0


def make_case(family, fold, index, n=220):
    # Seed namespace differs from the initial four-formula smoke run.
    seed = 2424310300 + SEED_OFFSET + (10000 if family == 'community3' else 0) + (1000 if fold == 'test' else 0) + index
    rng = random.Random(seed)
    clauses = []
    for _ in range(round(4.23 * n)):
        if family == 'community3' and rng.random() < .65:
            begin = rng.randrange(4) * (n // 4) + 1
            v = rng.sample(range(begin, begin + n // 4), 3)
        else:
            v = rng.sample(range(1, n + 1), 3)
        clauses.append([x if rng.getrandbits(1) else -x for x in v])
    text = f'p cnf {n} {len(clauses)}\n' + ''.join(' '.join(map(str, c)) + ' 0\n' for c in clauses)
    name = f'r24_{family}_{fold}_{index:02}.cnf'
    path = OUT / 'cnf' / name
    path.write_text(text)
    return path, clauses, hashlib.sha256(text.encode()).hexdigest(), seed


def run(binary, path, clauses, family, fold, repeat, mode):
    env = os.environ.copy()
    env.update(DRNAS_V177_MODE=('r5_monitor' if mode == 'monitor' else 'r11_2048_50'),
               DRNAS_R13_N='220', DRNAS_R12_DEGREE_CV='0.28',
               DRNAS_R16_GINI='0.16', DRNAS_R16_POLARITY='0.22')
    start = time.monotonic()
    proc = subprocess.Popen([binary, str(path)], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=env, bufsize=1)
    lines = []

    def reader():
        for line in proc.stdout:
            lines.append(line)
            if line.startswith('c R24_TRACE'):
                print(f'LIVE {path.stem} repeat={repeat} mode={mode} {line.strip()}', flush=True)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    # Waiting on the reader gives prompt completion for millisecond solves;
    # Popen.wait(timeout=...) uses polling sleeps that distorted smoke timings.
    thread.join(timeout=CAP)
    timed_out = thread.is_alive()
    if timed_out:
        proc.kill()
    code = proc.wait()
    thread.join()
    elapsed = time.monotonic() - start
    if code not in (10, 20, -9):
        raise RuntimeError(f'Unexpected exit={code}: {"".join(lines)[-1500:]}')
    if code == 10:
        vals = [int(v) for line in lines if line.startswith('v ') for v in line.split()[1:] if v != '0']
        assignment = {abs(v): v > 0 for v in vals}
        if not all(any(abs(l) in assignment and assignment[abs(l)] == (l > 0) for l in c) for c in clauses):
            raise RuntimeError('SAT model failed independent original-CNF check')
    traces = []
    for line in lines:
        if line.startswith('c R24_TRACE '):
            traces.append({k: int(v) for k, v in (t.split('=', 1) for t in line.split()[2:])})
    for t in traces:
        if t['conflict'] < t['mark'] or (t['mark'] < 1024 and t['conflict'] >= 2*t['mark']):
            raise RuntimeError('Invalid checkpoint order')
    result = dict(formula=path.name, family=family, fold=fold, repeat=repeat, mode=mode,
                  status=('TIMEOUT' if timed_out else 'SAT' if code == 10 else 'UNSAT'),
                  seconds=elapsed, par2=2*CAP if timed_out else elapsed, traces=traces,
                  switched=any('DRNAS_V177_SWITCH' in line for line in lines))
    print('R24_RESULT ' + json.dumps({k:v for k,v in result.items() if k != 'traces'}), flush=True)
    return result


def main():
    global OUT, SEED_OFFSET
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', required=True)
    ap.add_argument('--cases-per-family-fold', type=int, default=8)
    ap.add_argument('--seed-offset', type=int, default=0)
    ap.add_argument('--output', type=Path, default=OUT)
    args = ap.parse_args()
    OUT, SEED_OFFSET = args.output, args.seed_offset
    binary = str(Path(args.binary).resolve())
    (OUT / 'cnf').mkdir(parents=True, exist_ok=True)
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    cases = [make_case(family, fold, i) + (family, fold)
             for family in ('random3', 'community3') for fold in ('development', 'test')
             for i in range(args.cases_per_family_fold)]
    rng = random.Random(240301)
    rng.shuffle(cases)
    identities = [x[2] for x in cases]
    if len(set(identities)) != len(identities):
        raise RuntimeError('Duplicate formula SHA')
    (OUT / 'manifest.json').write_text(json.dumps(dict(cap=CAP, repeats=REPEATS, cpu=cpu,
        note='Synthetic exploratory pilot. R23/R22 holdouts not reused by seed; '
             'prior corpus SHA comparison and independent UNSAT proof are not available.',
        formulas=[dict(name=p.name, sha256=sha, seed=seed, family=fam, fold=fold)
                  for p, _, sha, seed, fam, fold in cases]), indent=2))
    rows=[]
    with (OUT / 'measurements.jsonl').open('w', buffering=1) as output:
        for path, clauses, sha, seed, family, fold in cases:
            for repeat in range(REPEATS):
                modes = ['monitor', 'forced']
                rng.shuffle(modes)
                for mode in modes:
                    row=run(binary,path,clauses,family,fold,repeat,mode)
                    row.update(sha256=sha, seed=seed)
                    rows.append(row)
                    output.write(json.dumps(row)+'\n')
            statuses={r['status'] for r in rows if r['formula']==path.name} - {'TIMEOUT'}
            if len(statuses)>1:
                raise RuntimeError('SAT/UNSAT disagreement: '+str(statuses))
    summaries={}
    for fold in ('development','test'):
        for family in ('random3','community3'):
            group=[r for r in rows if r['fold']==fold and r['family']==family]
            pairs=[]
            for name in sorted({r['formula'] for r in group}):
                per={m:statistics.median(r['par2'] for r in group if r['formula']==name and r['mode']==m)
                     for m in ('monitor','forced')}
                pairs.append(per)
            base=sum(x['monitor'] for x in pairs); forced=sum(x['forced'] for x in pairs)
            summaries[f'{family}/{fold}']=dict(formulas=len(pairs), monitor=base, forced=forced,
                 forced_gain_pct=100*(base-forced)/base, forced_gt2x=sum(x['forced']>2*x['monitor'] for x in pairs),
                 timeouts=sum(x['status']=='TIMEOUT' for x in group),
                 switched=sum(x['switched'] for x in group if x['mode']=='forced'))
    (OUT / 'summary.json').write_text(json.dumps(summaries,indent=2))
    print('R24_SUMMARY '+json.dumps(summaries),flush=True)


if __name__ == '__main__':
    main()
