#!/usr/bin/env python3
"""Honest apples-to-apples DRNAS v0.2 vs real CryptoMiniSat CLI.

Measures wall-clock time including independent process startup for BOTH.
No claim of a CryptoMiniSat result is made when the official binary is absent.

Outputs results.csv and summary.csv; validates SAT models against original DIMACS.
"""
import argparse
import csv
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from drnas_np_lab import read_dimacs, check

ROOT=Path(__file__).resolve().parent

def verify_model(n, clauses, stdout):
    found=[]
    in_model=False
    for line in stdout.splitlines():
        if not line.startswith('v '):
            continue
        in_model=True
        for token in line[2:].split():
            try:
                v=int(token)
            except ValueError:
                return 'MODEL_INVALID'
            if v: found.append(v)
    if not in_model:
        return 'MODEL_NOT_EMITTED'
    assignment=[None]*n
    for lit in found:
        if abs(lit)>n:
            return 'MODEL_INVALID'
        idx=abs(lit)-1
        if assignment[idx] is not None and assignment[idx]!=(lit>0):
            return 'MODEL_INVALID'
        assignment[idx]=(lit>0)
    if any(x is None for x in assignment):
        return 'MODEL_PARTIAL'
    return 'OK' if check(clauses,assignment) else 'MODEL_INVALID'

def parse(stdout,stderr,returncode,n,clauses):
    statuses=[]
    for raw in stdout.splitlines():
        line=raw.strip()
        if line=='s SATISFIABLE': statuses.append('SAT')
        if line=='s UNSATISFIABLE': statuses.append('UNSAT')
        if line in ('s UNKNOWN','s INDETERMINATE'): statuses.append('LIMIT')
    if len(set(statuses))>1: return 'ERROR','CONFLICTING_STATUS'
    status=statuses[0] if statuses else 'ERROR'
    if status=='SAT':
        validation=verify_model(n,clauses,stdout)
        if validation=='MODEL_INVALID': return 'ERROR',validation
    else:
        validation='NO_MODEL' if status=='UNSAT' else 'NO_RESULT'
    if status=='SAT' and returncode not in (0,10): return 'ERROR',f'UNEXPECTED_EXIT_{returncode}'
    if status=='UNSAT' and returncode not in (0,20): return 'ERROR',f'UNEXPECTED_EXIT_{returncode}'
    return status,validation

def run(argv,timeout,n,clauses):
    start=time.perf_counter()
    try:
        c=subprocess.run(argv,capture_output=True,text=True,timeout=timeout,check=False,
                         env={**os.environ,'PYTHONHASHSEED':'0'})
        elapsed=(time.perf_counter()-start)*1000
        status,valid=parse(c.stdout,c.stderr,c.returncode,n,clauses)
        err=c.stderr[-800:] if status=='ERROR' else ''
        return status,valid,elapsed,err
    except subprocess.TimeoutExpired:
        return 'TIMEOUT','NO_RESULT',(time.perf_counter()-start)*1000,''
    except OSError as e:
        return 'ERROR','SPAWN_ERROR',(time.perf_counter()-start)*1000,str(e)

def benchmark(args):
    root=Path(args.cases_dir).resolve()
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    with (root/'manifest.csv').open() as f: manifest=list(csv.DictReader(f))
    crypto=shutil.which(args.crypto) if not Path(args.crypto).is_file() else str(Path(args.crypto).resolve())
    if not crypto:
        if args.require_crypto:
            raise SystemExit('ERROR: CryptoMiniSat is required but no real binary was found')
        print('WARNING: real CryptoMiniSat binary not found. No CryptoMiniSat benchmark will be fabricated.',flush=True)
    else:
        try:
            c=subprocess.run([crypto,'--version'],capture_output=True,text=True,timeout=4)
            ver=(c.stdout+' '+c.stderr).strip()[:180]
        except Exception as e:
            ver=f'unknown: {e}'
        print('CryptoMiniSat:',crypto,ver,flush=True)
    meta={'python':sys.version.split()[0], 'platform':platform.platform(),
          'machine':platform.machine(), 'crypto_binary':crypto,
          'crypto_version':ver if crypto else None,
          'repeats':args.repeats,'timeout_seconds':args.timeout,
          'measurement':'wall clock per isolated process, includes startup, not solver-only CPU',
          'cases':len(manifest),'fairness_notes':'same DIMACS bytes, one thread for CMS where possible, no DRNAS preprocessed input passed to CMS'}
    (out/'environment.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
    rows=[]
    for case in manifest:
        path=root/(case['case_id']+'.cnf')
        n,clauses=read_dimacs(path)
        if n!=int(case['n']) or len(clauses)!=int(case['m']): raise AssertionError('bad fixture')
        for solver in ('DRNAS v0.2','CryptoMiniSat'):
            for rep in range(args.repeats):
                if solver=='DRNAS v0.2':
                    cmd=[sys.executable,str(ROOT/'drnas_cli.py'),str(path),'--budget',str(args.timeout)]
                    status,valid,ms,err=run(cmd,args.timeout+0.15,n,clauses)
                elif crypto:
                    # Official CLI accepts --verb 0, and emits DIMACS SAT model by default.
                    cmd=[crypto,'--verb','0',str(path)]
                    status,valid,ms,err=run(cmd,args.timeout,n,clauses)
                else:
                    status,valid,ms,err='UNAVAILABLE','NO_BINARY',None,''
                if case['expected']!='UNKNOWN' and status in ('SAT','UNSAT') and status!=case['expected']:
                    raise AssertionError(f'WRONG ANSWER: {case["case_id"]} expected {case["expected"]}: {solver} -> {status}')
                if valid=='MODEL_INVALID': raise AssertionError(f'INVALID MODEL: {case["case_id"]} {solver}')
                rows.append({'case_id':case['case_id'],'family':case['family'],'n':n,'m':len(clauses),
                             'seed':case['seed'],'expected':case['expected'],'solver':solver,
                             'repetition':rep,'status':status,'model_verification':valid,
                             'wall_ms':round(ms,3) if ms is not None else '',
                             'error':err.replace('\n',' ')})
        current=[r for r in rows if r['case_id']==case['case_id']]
        s=' '.join(f'{slv}={next((r["status"] for r in current if r["solver"]==slv),"?")}' for slv in ('DRNAS v0.2','CryptoMiniSat'))
        print(f'{case["case_id"]} {case["family"]:17} n={n:3} | {s}',flush=True)
    with (out/'results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    # Comparison on equal completed instances only, no naive averaging of timeouts.
    summaries=[]
    for family in list(dict.fromkeys(r['family'] for r in rows)):
        group=[r for r in rows if r['family']==family]
        for solver in ('DRNAS v0.2','CryptoMiniSat'):
            rec=[r for r in group if r['solver']==solver]
            vals=[r['wall_ms'] for r in rec if r['status'] in ('SAT','UNSAT')]
            summaries.append({'family':family,'solver':solver,'total_runs':len(rec),
                'solved':len(vals),'timeouts':sum(r['status'] in ('TIMEOUT','LIMIT') for r in rec),
                'unavailable':sum(r['status']=='UNAVAILABLE' for r in rec),
                'errors':sum(r['status']=='ERROR' for r in rec),
                'median_solved_wall_ms':round(statistics.median(vals),3) if vals else ''})
    with (out/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    # Strict status disagreement check, excluding unknown/limits.
    for case in manifest:
        status={}
        for solver in ('DRNAS v0.2','CryptoMiniSat'):
            solved={r['status'] for r in rows if r['case_id']==case['case_id'] and r['solver']==solver and r['status'] in ('SAT','UNSAT')}
            if len(solved)>1: raise AssertionError(f'inconsistent repeated solve: {case} {solved}')
            status[solver]=next(iter(solved),None)
        if all(status.values()) and len(set(status.values()))>1:
            raise AssertionError(f'cross-solver mismatch: {case} {status}')
    print(f'CSV: {out/"results.csv"}; Summary: {out/"summary.csv"}',flush=True)
    if not crypto: print('NOT A CRYPTOMINISAT COMPARISON: missing real binary',flush=True)
    if any(r['status']=='ERROR' for r in rows): sys.exit(2)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--crypto',default='cryptominisat5')
    p.add_argument('--cases-dir',default=str(ROOT/'cases'))
    p.add_argument('--out',default=str(ROOT/'results'))
    p.add_argument('--timeout',type=float,default=2.0)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--require-crypto',action='store_true',help='fail instead of logging UNAVAILABLE when CryptoMiniSat is absent')
    args=p.parse_args()
    if args.repeats < 1 or args.timeout <=0: p.error('invalid benchmark settings')
    benchmark(args)