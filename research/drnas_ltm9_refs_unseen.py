#!/usr/bin/env python3
"""Five-arm, single-CPU E2E evaluation with source-disjoint frozen training memory."""
import hashlib, json, os, pathlib, resource, shutil, subprocess, sys, time
import drnas_atlas13_generator as G

ROOT=pathlib.Path('ltm9_refs')
CAP=5.0
ARMS=('LTM9_FAST','LTM8_FAST','Kissat','CryptoMiniSat','CaDiCaL')
SEEDS=(17,29,43)

def canonical(n,clauses):
    return (f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode()

def witness_ok(n,clauses,out):
    values={}
    try:
        for line in out.splitlines():
            if not line.startswith('v '):continue
            for token in line[2:].split():
                lit=int(token)
                if not lit:continue
                if abs(lit)>n or (abs(lit) in values and values[abs(lit)]!=(lit>0)):return False
                values[abs(lit)]=lit>0
    except ValueError:return False
    return all(any(values.get(abs(lit))==(lit>0) for lit in c) for c in clauses)

def command(arm,path,cap,seed):
    if arm in ('LTM9_FAST','LTM8_FAST'):
        exe='mre_atlas23/bin/drnas_ltm9' if arm=='LTM9_FAST' else 'mre_atlas23/bin/drnas_ltm8_base'
        return [exe,str(path),'--mode','LTM8_FAST','--time',str(cap),'--seed',str(seed),'--policy','1.0,0.85']
    return {'Kissat':['kissat','-q','--seed='+str(seed),str(path)],
            'CryptoMiniSat':['cryptominisat5','--threads=1','--verb=0',str(path)],
            'CaDiCaL':['cadical','-q','--seed='+str(seed),str(path)]}[arm]

def run(arm,case,cap,seed,memory):
    env=dict(os.environ,DRNAS_LTM8_MEMORY=str(memory)+'.'+arm,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    started=time.monotonic();out='';err=''
    try:
        p=subprocess.run(command(arm,case['path'],cap,seed),capture_output=True,text=True,timeout=cap,env=env,
            preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3)))
        rc=p.returncode;out=p.stdout;err=p.stderr
    except subprocess.TimeoutExpired:
        rc=124
    elapsed=time.monotonic()-started
    if rc==10:
        status='SAT_VERIFIED' if witness_ok(case['n'],case['clauses'],out) else 'INVALID_SAT'
    elif rc==20:status='UNSAT_UNVERIFIED'
    elif rc in (0,124):status='UNKNOWN'
    else:status='ERROR'
    return dict(arm=arm,family=case['family'],index=case['index'],sha256=case['sha256'],seed=seed,
                status=status,returncode=rc,e2e_s=round(elapsed,6),
                PAR2_reported_s=round(elapsed if status in ('SAT_VERIFIED','UNSAT_UNVERIFIED') else 2*cap,6),
                PAR2_verified_s=round(elapsed if status=='SAT_VERIFIED' else 2*cap,6),
                diagnostics=(err+out)[-2500:] if status in ('ERROR','INVALID_SAT') else '',
                learning=[line for line in out.splitlines() if line.startswith('LTM8_LEARNING')])

def cases(indices):
    result=[]
    for family in G.CATEGORIES:
        for index in indices:
            n,clauses,_=G.build(family,index);raw=canonical(n,clauses);sha=hashlib.sha256(raw).hexdigest()
            path=ROOT/'cases'/f'{sha}.cnf';path.write_bytes(raw)
            result.append(dict(family=family,index=index,n=n,clauses=clauses,path=path,sha256=sha))
    return result

def summary(rows):
    result={}
    for arm in ARMS:
        a=[r for r in rows if r['arm']==arm]
        result[arm]=dict(trials=len(a),solved_reported=sum(r['status'] in ('SAT_VERIFIED','UNSAT_UNVERIFIED') for r in a),
            SAT_verified=sum(r['status']=='SAT_VERIFIED' for r in a),
            UNSAT_unverified=sum(r['status']=='UNSAT_UNVERIFIED' for r in a),
            errors=sum(r['status'] in ('ERROR','INVALID_SAT') for r in a),
            total_e2e_s=round(sum(r['e2e_s'] for r in a),6),
            PAR2_reported_s=round(sum(r['PAR2_reported_s'] for r in a),6),
            PAR2_verified_s=round(sum(r['PAR2_verified_s'] for r in a),6))
    return result

def main():
    if '--selftest' in sys.argv:
        assert witness_ok(2,[[1],[-2]],'v 1 -2 0\n')
        assert not witness_ok(2,[[1]],'v 1 -1 0\n')
        assert not witness_ok(2,[[1]],'v 3 0\n')
        assert not witness_ok(2,[[1]],'s SATISFIABLE\n')
        assert not witness_ok(2,[[]],'v 1 2 0\n')
        assert not witness_ok(2,[[1]],'v abc 0\n')
        print('LTM9_REFS_HARNESS_SELFTEST_PASS');return
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    for exe in ('kissat','cadical','cryptominisat5'):
        if not shutil.which(exe):raise RuntimeError('Missing reference executable: '+exe)
    if ROOT.exists():raise RuntimeError('Use a clean output directory to avoid stale training memory')
    (ROOT/'cases').mkdir(parents=True);(ROOT/'train').mkdir();(ROOT/'trial').mkdir()
    train=cases((102,103));holdout=cases((211,212));previous=cases((93,94))
    train_sha={c['sha256'] for c in train};test_sha={c['sha256'] for c in holdout}
    assert len(train_sha)==20 and len(test_sha)==20 and not train_sha&test_sha
    assert not test_sha & {c['sha256'] for c in previous}, 'overlap with prior LTM8 holdout'
    manifest=dict(cap_s=CAP,reps=len(SEEDS),arms=ARMS,logical_cpus=1,cpu=cpu,
                  source='synthetic ATLAS13 ten-family generator; not official competition CNFs',
                  note='reused exposed LTM8 indices 211/212 for regression, NOT a new blind holdout',
                  train=[{k:c[k] for k in ('family','index','sha256')} for c in train],
                  holdout=[{k:c[k] for k in ('family','index','sha256')} for c in holdout],
                  CMS_seed='solver default; repeated for timing',UNSAT_independent_proof=False)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    failed=False
    with (ROOT/'training.jsonl').open('w') as f:
        for case in train:
            for arm in ARMS[:2]:
                row=run(arm,case,1.0,11,ROOT/'train'/'memory')
                f.write(json.dumps(row)+'\n');f.flush()
                if row['status'] in ('ERROR','INVALID_SAT'):failed=True
    if failed:raise RuntimeError('Training returned an invalid result; see training.jsonl')
    snapshots={p.name:p.read_bytes() for p in (ROOT/'train').glob('memory.*') if '.lock' not in p.name and '.tmp.' not in p.name}
    print('LTM9_REFS_TRAIN '+json.dumps(dict(cases=20,trial_count=40,memory_snapshots=len(snapshots),holdout_disjoint=True,previous_holdout_disjoint=True)),flush=True)
    rows=[];claims={}
    with (ROOT/'results.jsonl').open('w') as f:
        for ci,case in enumerate(holdout):
            for rep,seed in enumerate(SEEDS):
                # Rotate execution order to avoid always giving the first slot to FAST.
                offset=(ci+rep)%len(ARMS)
                for arm in ARMS[offset:]+ARMS[:offset]:
                    for p in (ROOT/'trial').iterdir():p.unlink()
                    for name,data in snapshots.items():(ROOT/'trial'/name).write_bytes(data)
                    row=run(arm,case,CAP,seed,ROOT/'trial'/'memory');row['rep']=rep
                    row['shard']=0;rows.append(row)
                    if row['status'] in ('ERROR','INVALID_SAT'):failed=True
                    if row['status'] in ('SAT_VERIFIED','UNSAT_UNVERIFIED'):
                        claim=10 if row['status']=='SAT_VERIFIED' else 20
                        old=claims.setdefault(case['sha256'],claim)
                        if old!=claim:failed=True;row['disagreement']=True
                    f.write(json.dumps(row)+'\n');f.flush();print('LTM9_REFS_TRIAL '+json.dumps(row),flush=True)
    totals=summary(rows)
    ratios={ours:{ref:round(totals[ref]['PAR2_reported_s']/max(1e-9,totals[ours]['PAR2_reported_s']),4) for ref in ARMS[2:]} for ours in ARMS[:2]}
    report=dict(total=totals,shards={'0':totals},family={f:summary([r for r in rows if r['family']==f]) for f in G.CATEGORIES},
                reference_PAR2_over_DRNAS=ratios,failed=failed,UNSAT_independent_proof=False)
    (ROOT/'summary.json').write_text(json.dumps(report,indent=2))
    print('LTM9_REFS_FINAL '+json.dumps(report),flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('20 synthetic CNFs × 3 repeats × 5 solvers; 5 s cap; one logical CPU. Training memory frozen before holdout.\n\n')
            f.write('| Solver | Solved (reported) | SAT verified | UNSAT unverified | PAR2 reported s | PAR2 verified s |\n|---|---:|---:|---:|---:|---:|\n')
            for arm,s in totals.items():f.write(f"| {arm} | {s['solved_reported']}/{s['trials']} | {s['SAT_verified']} | {s['UNSAT_unverified']} | {s['PAR2_reported_s']:.3f} | {s['PAR2_verified_s']:.3f} |\n")
            f.write('\nUNSAT is not independently proof-verified. Ratios use reported PAR2; see summary.json for family breakdown and single shard totals.\n')
    if failed:raise RuntimeError('Invalid result, solver error or cross-solver contradiction; inspect compact artifacts')

if __name__=='__main__':main()
