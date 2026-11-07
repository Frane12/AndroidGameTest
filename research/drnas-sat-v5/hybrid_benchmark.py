#!/usr/bin/env python3
"""DRNAS SAT v5: exact separator-conditioned CaDiCaL vs plain CaDiCaL.
Uses the v4 benchmark's original CNF generator and quick_cut without changes.
All preprocessing, file writing and CaDiCaL process launch time is included.
"""
import argparse
import csv
import hashlib
import itertools
import json
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'drnas-sat-v4'))
from benchmark_sat import cases, condition, normalize, quick_cut, write_dimacs

def binary_status(binary, cnf_file, timeout):
    started = time.perf_counter_ns()
    try:
        proc = subprocess.run([str(binary), str(cnf_file)], capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'CaDiCaL timeout for {cnf_file}') from exc
    elapsed_ms = (time.perf_counter_ns() - started) / 1e6
    if proc.returncode not in (10, 20):
        raise RuntimeError(f'CaDiCaL failed exit={proc.returncode} stderr={proc.stderr[:350]!r}')
    return proc.returncode == 10, elapsed_ms

def run_hybrid(binary, original, original_file, timeout=30, max_calls=16):
    started = time.perf_counter_ns()
    cnf = normalize(original)
    selected, meta = quick_cut(cnf)
    if selected is None:
        result, solver_ms = binary_status(binary, original_file, timeout)
        return result, dict(selected=False, reason=meta['reason'], calls=1,
                            solver_ms=solver_ms, cut_size=0, components=1)
    cut, groups = selected
    # Rule fixed before the new benchmark; no use of answer or timing feedback.
    if (2 ** len(cut)) * len(groups) > max_calls:
        result, solver_ms = binary_status(binary, original_file, timeout)
        return result, dict(selected=False, reason='cost_gate', calls=1,
                            solver_ms=solver_ms, cut_size=len(cut), components=len(groups))
    owners = {v: i for i, group in enumerate(groups) for v in group}
    calls = 0
    solver_ms = 0.0
    with tempfile.TemporaryDirectory(prefix='drnas_sat_cut_') as td:
        for signs in itertools.product((-1, 1), repeat=len(cut)):
            reduced = condition(cnf, {v * s for v, s in zip(cut, signs)})
            if frozenset() in reduced:
                continue
            parts = [set() for _ in groups]
            for clause in reduced:
                belongs = {owners[abs(l)] for l in clause}
                if len(belongs) != 1:
                    raise AssertionError('Invalid separator: residual crosses components')
                parts[belongs.pop()].add(clause)
            fully_sat = True
            for index, part in enumerate(parts):
                if not part:
                    continue
                file = Path(td) / f'piece_{index}.cnf'
                write_dimacs(file, part)
                result, t = binary_status(binary, file, timeout)
                calls += 1
                solver_ms += t
                if not result:
                    fully_sat = False
                    break
            if fully_sat:
                return True, dict(selected=True, reason='selected', calls=calls,
                                  solver_ms=solver_ms, cut_size=len(cut), components=len(groups))
    return False, dict(selected=True, reason='selected', calls=calls,
                       solver_ms=solver_ms, cut_size=len(cut), components=len(groups))

def benchmark(binary, outdir, seed=20261113, count=40, reps=3, timeout=30):
    outdir = Path(outdir)
    cnfdir = outdir / 'dimacs'
    cnfdir.mkdir(parents=True, exist_ok=True)
    data = cases(seed=seed, count=count)
    rows = []
    for idx, (id_, family, cnf) in enumerate(data):
        file = cnfdir / f'{id_}_{family}.cnf'
        write_dimacs(file, cnf)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        methods = ['cadical_plain', 'drnas_hybrid'] * reps
        random.Random(seed + idx).shuffle(methods)
        expected = None
        for method in methods:
            t0 = time.perf_counter_ns()
            if method == 'cadical_plain':
                answer, solver_ms = binary_status(binary, file, timeout)
                meta = dict(selected=False, reason='plain', calls=1, solver_ms=solver_ms,
                            cut_size=0, components=1)
            else:
                answer, meta = run_hybrid(binary, cnf, file, timeout=timeout)
            elapsed = (time.perf_counter_ns() - t0)/1e6
            if expected is None:
                expected = answer
            if answer != expected:
                raise AssertionError(f'INVALID SAT RESULT case={id_} family={family} method={method}')
            rows.append(dict(case=id_, family=family, sha256=digest,
                             method=method, result='SAT' if answer else 'UNSAT', ms=round(elapsed,6),
                             selected=int(meta['selected']), reason=meta['reason'],
                             calls=meta['calls'], solver_ms=round(meta['solver_ms'],6),
                             overhead_ms=round(elapsed-meta['solver_ms'],6),
                             cut_size=meta['cut_size'], components=meta['components']))
        print(f'Verified {idx + 1}/{count} {family} {"SAT" if expected else "UNSAT"}', flush=True)
    with (outdir / 'measurements.csv').open('w', newline='') as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    sample={}
    for method in ('cadical_plain','drnas_hybrid'):
        subset=[r for r in rows if r['method']==method]
        median_by_case={k:statistics.median(r['ms'] for r in subset if r['case']==k) for k,_,_ in data}
        sample[method]=dict(sum_case_medians_ms=round(sum(median_by_case.values()),4),
                            median_case_ms=round(statistics.median(median_by_case.values()),4),
                            medians_ms={k:round(v,5) for k,v in median_by_case.items()})
    plain=sample['cadical_plain']['medians_ms']; hybrid=sample['drnas_hybrid']['medians_ms']
    used={r['case'] for r in rows if r['method']=='drnas_hybrid' and r['selected']}
    by_family={}
    for fam in sorted({x[1] for x in data}):
        ids=[case for case,f,_ in data if f==fam]
        by_family[fam]=dict(n=len(ids),selected=sum(i in used for i in ids),
                            plain_ms=round(sum(plain[i] for i in ids),4),
                            hybrid_ms=round(sum(hybrid[i] for i in ids),4),
                            faster_cases=sum(hybrid[i]<plain[i] for i in ids))
    report=dict(seed=seed, cases=count, repetitions=reps, platform=platform.platform(),
                python=platform.python_version(), bin=str(binary),
                summary=sample, hybrid_faster_cases=sum(hybrid[i]<plain[i] for i in plain),
                selected_cases=len(used),
                selection_reasons=dict(Counter(r['reason'] for r in rows if r['method']=='drnas_hybrid')),
                by_family=by_family, verified=len(data),
                caveats=['Synthetic benchmark; not SAT Competition',
                         'Subprocess launch and file I/O included for both methods',
                         'CaDiCaL is invoked independently for each hybrid component',
                         'No claim of improvement unless hybrid beats baseline including overhead'])
    (outdir/'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='summary'}, indent=2), flush=True)
    return report

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--cadical', required=True)
    p.add_argument('--outdir', default='bench_hybrid_v5')
    p.add_argument('--seed', type=int, default=20261113)
    p.add_argument('--count', type=int, default=40)
    p.add_argument('--reps', type=int, default=3)
    p.add_argument('--timeout', type=int, default=30)
    a=p.parse_args()
    benchmark(a.cadical, a.outdir, a.seed, a.count, a.reps, a.timeout)
