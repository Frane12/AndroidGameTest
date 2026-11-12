#!/usr/bin/env python3
"""REX2 native single-core paired E2E benchmark against LTM8 + three references.

30 previously defined ATLAS13 synthetic CNFs, 10 families, 2 repetitions,
5 arms = 300 matched trials. SAT witnesses checked against ORIGINAL CNF;
UNSAT is only reported, never independently certified by this harness.
No online cross-formula memory: LTM8_FAST and REX2_GRAPH start from the same
policy state; controller can still adapt within an individual solve.
"""
import hashlib
import json
import os
import pathlib
import resource
import shutil
import subprocess
import sys
import time

import drnas_atlas13_generator as G
from drnas_ltm8_refs_benchmark import canonical, witness_ok

ROOT = pathlib.Path('rex2_wide')
ARMS = ('REX2_GRAPH', 'LTM8_FAST', 'Kissat', 'CaDiCaL', 'CryptoMiniSat')
CAP = 4.0
SEEDS = (17, 29)
INDICES = (91, 92, 93)

def command(arm, path, seed):
    if arm in ('REX2_GRAPH', 'LTM8_FAST'):
        executable = ('mre_atlas23/bin/drnas_rex2' if arm == 'REX2_GRAPH'
                      else 'mre_atlas23/bin/drnas_ltm8')
        return [executable, str(path), '--mode', arm, '--time', str(CAP),
                '--seed', str(seed), '--policy', '1.0,0.85']
    if arm == 'Kissat':
        return ['kissat', '-q', '--seed='+str(seed), str(path)]
    if arm == 'CaDiCaL':
        return ['cadical', '-q', '--seed='+str(seed), str(path)]
    if arm == 'CryptoMiniSat':
        return ['cryptominisat5', '--threads=1', '--verb=0', str(path)]
    raise ValueError(arm)

def parse_stats(output):
    result={}
    for line in output.splitlines():
        if line.startswith('REX2_STATS '):
            for token in line.split()[1:]:
                k,v=token.split('=',1)
                result['rex2_'+k]=int(v)
        if line.startswith('ATLAS13_TRIAL '):
            for token in line.split()[1:]:
                if '=' not in token:continue
                k,v=token.split('=',1)
                if k in ('decisions','conflicts','propagations','watch_visits'):
                    result[k]=int(v)
    return result

def run(arm, case, seed):
    # No file/session sharing between paired arms or between holdout formulas.
    env=dict(os.environ,DRNAS_LTM8_MEMORY='',OMP_NUM_THREADS='1',
             OPENBLAS_NUM_THREADS='1')
    start=time.monotonic()
    try:
        p=subprocess.run(command(arm,case['path'],seed),capture_output=True,
                         text=True,timeout=CAP,env=env,
                         preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_AS,
                                                 (3*1024**3,3*1024**3)))
        rc=p.returncode
        out=p.stdout
        err=p.stderr
    except subprocess.TimeoutExpired:
        rc=124;out='';err='timeout'
    elapsed=time.monotonic()-start
    if rc==10:
        status=('SAT_VERIFIED' if witness_ok(case['n'],case['clauses'],out)
                else 'INVALID_SAT')
    elif rc==20:
        status='UNSAT_UNVERIFIED'
    elif rc in (0,124):
        status='TIMEOUT_OR_UNKNOWN'
    else:
        status='ERROR'
    row=dict(arm=arm,family=case['family'],index=case['index'],
             sha256=case['sha256'],shard=case['shard'],seed=seed,
             rc=rc,status=status,e2e_s=round(elapsed,6),
             PAR2_reported_s=round(elapsed if status in
                         ('SAT_VERIFIED','UNSAT_UNVERIFIED') else 2*CAP,6),
             PAR2_verified_s=round(elapsed if status=='SAT_VERIFIED' else 2*CAP,6),
             **parse_stats(out))
    if status in ('ERROR','INVALID_SAT'):
        row['diagnostics']=(out+'\n'+err)[-1200:]
    return row

def summarize(rows):
    result={}
    for arm in ARMS:
        a=[r for r in rows if r['arm']==arm]
        result[arm]=dict(trials=len(a),
                         reported_solved=sum(r['status'] in
                                         ('SAT_VERIFIED','UNSAT_UNVERIFIED') for r in a),
                         SAT_verified=sum(r['status']=='SAT_VERIFIED' for r in a),
                         UNSAT_unverified=sum(r['status']=='UNSAT_UNVERIFIED' for r in a),
                         error=sum(r['status'] in ('ERROR','INVALID_SAT') for r in a),
                         PAR2_reported_s=round(sum(r['PAR2_reported_s'] for r in a),6),
                         PAR2_verified_s=round(sum(r['PAR2_verified_s'] for r in a),6),
                         measured_e2e_s=round(sum(r['e2e_s'] for r in a),6))
        if arm=='REX2_GRAPH':
            result[arm]['rex2_choices']=sum(r.get('rex2_choices',0) for r in a)
            result[arm]['rex2_overrides']=sum(r.get('rex2_overrides',0) for r in a)
    return result

def main():
    if '--selftest' in sys.argv:
        assert witness_ok(2,[[1],[-2]],'v 1 -2 0\n')
        assert not witness_ok(2,[[1]],'v 2 0\n')
        assert parse_stats('REX2_STATS choices=10 overrides=2\n')['rex2_overrides']==2
        print('REX2_WIDE_SELFTEST_PASS',flush=True)
        return
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    for exe in ('kissat','cadical','cryptominisat5'):
        if not shutil.which(exe):
            raise RuntimeError('reference missing: '+exe)
    if ROOT.exists():raise RuntimeError('REX2 output path exists; fresh run required')
    (ROOT/'cases').mkdir(parents=True)
    cases=[]
    for fno,family in enumerate(G.CATEGORIES):
        for idx in INDICES:
            n,clauses,_=G.build(family,idx)
            raw=canonical(n,clauses)
            sha=hashlib.sha256(raw).hexdigest()
            path=ROOT/'cases'/f'{sha}.cnf'
            path.write_bytes(raw)
            cases.append(dict(family=family,index=idx,shard=fno//5,n=n,
                              clauses=clauses,sha256=sha,path=path))
    assert len(cases)==30 and len({c['sha256'] for c in cases})==30
    manifest=dict(source='ATLAS13 synthetic deterministic generator, not official competition',
                  original_cnf_sha256=[{k:c[k] for k in ('family','index','shard','sha256')} for c in cases],
                  cap_s=CAP,seeds=SEEDS,arms=ARMS,one_logical_cpu=True,cpu=cpu,
                  independent_UNSAT_certification=False,
                  persistent_memory_disabled=True,replicates=len(SEEDS))
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('REX2_WIDE_START '+json.dumps(dict(formulas=len(cases),arms=ARMS,
          repetitions=len(SEEDS),trials=len(cases)*len(SEEDS)*len(ARMS),
          cap_s=CAP,one_logical_cpu=True)),flush=True)
    rows=[]
    claims={}
    failed=False
    with (ROOT/'trials.jsonl').open('w') as fd:
        for ci,case in enumerate(cases):
            for rep,seed in enumerate(SEEDS):
                shift=(ci+rep)%len(ARMS)
                for arm in ARMS[shift:]+ARMS[:shift]:
                    row=run(arm,case,seed)
                    if row['status'] in ('ERROR','INVALID_SAT'):
                        failed=True
                    if row['status'] in ('SAT_VERIFIED','UNSAT_UNVERIFIED'):
                        value='SAT' if row['status']=='SAT_VERIFIED' else 'UNSAT'
                        old=claims.setdefault(case['sha256'],value)
                        if old!=value:
                            failed=True
                            row['DISAGREEMENT_WITH']=old
                    rows.append(row)
                    fd.write(json.dumps(row)+'\n');fd.flush()
                    print('REX2_WIDE_TRIAL '+json.dumps(row),flush=True)
                    if failed:
                        raise RuntimeError('Solver invalid output/error/disagreement: see trials.jsonl')
    total=summarize(rows)
    shards={str(shard):summarize([r for r in rows if r['shard']==shard]) for shard in (0,1)}
    family={f:summarize([r for r in rows if r['family']==f]) for f in G.CATEGORIES}
    ratios={arm:{ref:round(total[ref]['PAR2_reported_s']/
                      max(1e-9,total[arm]['PAR2_reported_s']),4)
                    for ref in ARMS if ref!=arm} for arm in ARMS[:2]}
    report=dict(total=total,shards=shards,family=family,
                reference_over_native_reported_PAR2=ratios,failed=failed,
                original_cnf_SAT_witness_verified=True,
                original_cnf_UNSAT_independently_verified=False,
                note='REX2 is graph-branching vs LTM8_FAST; synthetic CNF, 1 logical CPU')
    (ROOT/'summary.json').write_text(json.dumps(report,indent=2))
    print('REX2_WIDE_FINAL '+json.dumps(report),flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('30 synthetic original CNFs × 2 repetitions × 5 arms; 4s cap; single logical CPU. UNSAT unverified.\n\n')
            f.write('| Arm | Reported solved | SAT verified | UNSAT unverified | PAR2 reported (s) | PAR2 strict (s) |\n|---|---:|---:|---:|---:|---:|\n')
            for name,v in total.items():
                f.write(f"| {name} | {v['reported_solved']}/{v['trials']} | {v['SAT_verified']} | {v['UNSAT_unverified']} | {v['PAR2_reported_s']:.3f} | {v['PAR2_verified_s']:.3f} |\n")
            f.write(f"\nREX2 graph decisions: {total['REX2_GRAPH']['rex2_choices']}; overrides: {total['REX2_GRAPH']['rex2_overrides']}.\n")
    print('REX2_WIDE_PASS',flush=True)

if __name__=='__main__':main()
