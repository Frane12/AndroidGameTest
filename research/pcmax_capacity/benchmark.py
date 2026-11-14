#!/usr/bin/env python3
"""Serial single-CPU discovery plus independent verification, with full timings.

Only the harness reads expected labels. The solver sees the original CNF bytes.
Each certificate is checked in a separate fresh process. Caches are not flushed.
"""
import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request


def timed_process(command, stdout, stderr, hard_limit):
    before = time.perf_counter()
    with stdout.open('w') as out, stderr.open('w') as err:
        process = subprocess.Popen(command, stdout=out, stderr=err)
        def alarm(signum, frame):
            raise TimeoutError('process hard limit')
        previous = signal.signal(signal.SIGALRM, alarm)
        signal.setitimer(signal.ITIMER_REAL, hard_limit)
        timeout = False
        try:
            _, status, usage = os.wait4(process.pid, 0)
        except TimeoutError:
            timeout = True
            process.kill()
            _, status, usage = os.wait4(process.pid, 0)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        process.returncode = os.waitstatus_to_exitcode(status)
    return dict(returncode=process.returncode, timeout=timeout,
                wall_s=time.perf_counter()-before,
                cpu_s=usage.ru_utime+usage.ru_stime, maxrss_kib=usage.ru_maxrss)


def materialize(entry, directory, download):
    path = directory / entry['name']
    if not path.exists():
        if not download:
            raise FileNotFoundError(path)
        request = urllib.request.Request(entry['url'], headers={'User-Agent': 'DRNAS-PCMAX-capacity-audit/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response:
            blob = response.read(30_000_001)
        if len(blob)>30_000_000:
            raise ValueError('source exceeds compressed size limit')
        raw = lzma.decompress(blob) if blob.startswith(b'\xfd7zXZ\x00') else blob
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:
            raise ValueError('download source hash mismatch: '+entry['name'])
        path.write_bytes(raw)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
        raise ValueError('cached source hash mismatch: '+entry['name'])
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('sources20.json'))
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget-ms', type=float, default=2000)
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--cpu', type=int)
    parser.add_argument('--download', action='store_true')
    args=parser.parse_args()
    assert args.budget_ms>0 and args.repetitions>0
    cpu = min(os.sched_getaffinity(0)) if args.cpu is None else args.cpu
    os.sched_setaffinity(0,{cpu})
    args.inputs.mkdir(parents=True,exist_ok=True)
    args.output.mkdir(parents=True,exist_ok=True)
    entries=json.loads(args.manifest.read_text())['entries']
    inputs={e['sha256']:materialize(e,args.inputs,args.download) for e in entries}
    checker=Path(__file__).with_name('check_capacity.py')
    summary=dict(single_logical_cpu=cpu, budget_ms=args.budget_ms,
                 repetitions=args.repetitions, native_binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                 checker_sha256=hashlib.sha256(checker.read_bytes()).hexdigest(),
                 timing_scope='Fresh native process plus separate checker, including startup/read/write/teardown; caches not flushed.',
                 proof_format='pcmax-capacity-v1 (not DRAT/LRAT)', rows=[])
    with (args.output/'trials.jsonl').open('w') as log:
        for rep in range(args.repetitions):
            ordered=entries if rep%2==0 else list(reversed(entries))
            for index,entry in enumerate(ordered):
                case=args.output/f'rep-{rep:02d}-{entry["sha256"][:12]}'
                case.mkdir(exist_ok=False)
                certificate=case/'capacity.json'
                native=timed_process([str(args.binary.resolve()),str(inputs[entry['sha256']]),
                                      '--mode','core','--time',str(args.budget_ms/1000+3),
                                      '--pcmax-only','--pcmax-budget-ms',str(args.budget_ms),
                                      '--pcmax-certificate',str(certificate.resolve())],
                                     case/'native.stdout',case/'native.stderr',args.budget_ms/1000+8)
                stdout=(case/'native.stdout').read_text()
                records=[json.loads(line.split(' ',2)[2]) for line in stdout.splitlines()
                         if line.startswith('c PCMAX_CAPACITY ')]
                row=dict(name=entry['name'],sha256=entry['sha256'],expected_status=entry['expected_status'],
                         catalog_status=entry.get('catalog_status'),old_or_new=entry.get('old_or_new'),
                         rep=rep,native=native,telemetry=records[-1] if records else None,
                         status='UNKNOWN',verified=False,total_wall_s=native['wall_s'])
                if native['returncode']==20 and 's UNSATISFIABLE' in stdout:
                    assert certificate.is_file(), 'UNSAT lacks certificate'
                    verification=timed_process([sys.executable,str(checker),str(inputs[entry['sha256']]),str(certificate)],
                                               case/'checker.stdout',case/'checker.stderr',30)
                    row['checker']=verification
                    row['total_wall_s']+=verification['wall_s']
                    assert verification['returncode']==0,'independent checker rejected certificate'
                    checked=json.loads((case/'checker.stdout').read_text())
                    assert checked['status']=='UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED'
                    assert entry['expected_status']!='SAT','certificate contradicts SAT control label'
                    row.update(status='UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED',verified=True,
                               required=checked['required'],capacity_sum=checked['capacity_sum'])
                else:
                    assert native['returncode']==0 and 's UNKNOWN' in stdout, 'unexpected native execution result'
                    assert not certificate.exists(), 'UNKNOWN left a certificate'
                summary['rows'].append(row)
                log.write(json.dumps(row,sort_keys=True)+'\n');log.flush()
                print(json.dumps({k:row[k] for k in ('name','rep','status','total_wall_s')},sort_keys=True),flush=True)
    summary['verified_unsat_trials']=sum(r['verified'] for r in summary['rows'])
    summary['source_count']=len(entries)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')


if __name__=='__main__':
    main()
