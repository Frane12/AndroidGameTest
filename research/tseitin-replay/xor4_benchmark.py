"""Time the native v14.2 XOR4 entry point; replay its actual output afterwards."""
import hashlib
import itertools
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

from grid_certificates import make, replay, targets
from official_shortlong_select import download_and_features
from proofcheck import dimacs, verify_model

OUT = Path('xor4-results')
BIN = Path('bin').resolve()
NEW = 'v142_xor4'
BASE = 'v142_fastgate'
KISSAT = 'kissat_solver'
CAP = 8

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_cnf(path, n, clauses):
    with path.open('w') as f:
        print('p cnf', n, len(clauses), file=f)
        for clause in clauses:
            print(*clause, 0, file=f)

def invoke(exe, path):
    cmd = [str(BIN / exe), str(path)]
    if exe != KISSAT:
        cmd.extend([str(BIN / KISSAT), '0'])
    start = time.perf_counter()
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=CAP)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT', CAP, {}
    elapsed = time.perf_counter() - start
    if elapsed > CAP:
        return 'TIMEOUT', CAP, {}
    tags = [s.split('\t', 1)[1] for s in run.stdout.splitlines() if s.startswith('DRNAS_HYBRID_RESULT\t')]
    if tags:
        assert len(tags) == 1 and run.returncode == 0
        answer = json.loads(tags[0])
        return answer['status'], elapsed, answer
    verdict = {10: 'SAT', 20: 'UNSAT'}[run.returncode]
    expected = 's SATISFIABLE' if verdict == 'SAT' else 's UNSATISFIABLE'
    assert expected in run.stdout.splitlines()
    model = [int(v) for row in run.stdout.splitlines() if row.startswith('v ') for v in row.split()[1:] if v!='0']
    return verdict, elapsed, {'path': 'kissat', 'model': model}

def validate(path, verdict, answer):
    n, clauses = dimacs(path)
    if verdict == 'SAT':
        verify_model(n, clauses, answer['model'])
    elif answer['path'] in ('affine_exact_xor4','affine_exact'):
        groups = make(clauses)
        ids = answer['proof_rows']
        assert answer['variables'] == n and answer['equations'] == len(groups)
        assert ids and len(ids) == len(set(ids)) and all(type(i) is int and 0<=i<len(groups) for i in ids)
        selected = [groups[i] for i in ids]
        replay(clauses, selected)
        return selected

def controls():
    # Tseitin on K5. Each support has four variables and every edge occurs twice.
    edges = {pair:i for i,pair in enumerate(itertools.combinations(range(5),2),1)}
    blocks = []
    for vertex in range(5):
        vs = [i for pair,i in edges.items() if vertex in pair]
        blocks.append([tuple(-v if bit else v for bit,v in zip(bits,vs))
                       for bits in itertools.product((0,1),repeat=4)
                       if sum(bits)%2 != int(vertex == 0)])
    original = sum(blocks, [])
    def flip_block(clauses):
        return [(-row[0], *row[1:]) for row in clauses]
    tests = [
        ('odd', original, 'UNSAT', 'affine_exact_xor4'),
        ('even', flip_block(blocks[0]) + sum(blocks[1:], []), 'SAT', 'affine_exact_xor4'),
        ('missing', original[1:], 'SAT', 'kissat'),
        ('duplicate', [original[1]] + original[1:], 'SAT', 'kissat'),
        ('wrong_sign', [(-original[0][0], *original[0][1:])] + original[1:], 'SAT', 'kissat'),
        ('repeated_literal', [(*original[0], original[0][0])] + original[1:], 'UNSAT', 'kissat')]
    for name, clauses, expected, route in tests:
        path = OUT/(name+'.cnf')
        write_cnf(path,10,clauses)
        status, _, answer = invoke(NEW,path)
        assert (status,answer.get('path')) == (expected,route), (name,status,answer)
        validate(path,status,answer)
    return len(tests)

def main():
    OUT.mkdir(exist_ok=True)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    count = controls()
    if sys.argv[1:] == ['--controls']:
        print(count,'controls passed')
        return
    info = {'controls':count,'cap_seconds':CAP,'sha256':{s:sha(BIN/s) for s in (NEW,BASE,KISSAT)},
            'cpu':next(s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name'))}
    trials = []
    rng = random.Random(146027)
    for name,(source_id,digest) in targets.items():
        path = OUT/(name+'.cnf')
        download_and_features(source_id,path)
        assert sha(path)==digest
        n, clauses = dimacs(path)
        # Flip one variable in one equation only. The grid stays connected
        # and the charges now have even parity. Check the actual returned model.
        group = make(clauses)[0]
        indices = set(group['clause_indices'])
        changed = [[-x if i in indices and abs(x)==group['variables'][0] else x for x in c]
                   for i,c in enumerate(clauses)]
        control = OUT/(name+'-even.cnf')
        write_cnf(control,n,changed)
        status, _, model = invoke(NEW,control)
        assert status=='SAT' and model['path']=='affine_exact_xor4'
        validate(control,status,model)
        info[name] = {'original_sha256':digest,'sat_control_sha256':sha(control),'sat_model_verified':True}
        for rep in range(3):
            order = [NEW,BASE,KISSAT]
            rng.shuffle(order)
            for exe in order:
                status, seconds, answer = invoke(exe,path)
                verify_seconds = None
                if status != 'TIMEOUT':
                    assert status=='UNSAT'
                    start = time.perf_counter()
                    proof = validate(path,status,answer)
                    verify_seconds = time.perf_counter()-start
                    if exe==NEW:
                        assert answer['path']=='affine_exact_xor4' and proof
                        if rep==0:
                            (OUT/(name+'-certificate.json')).write_text(json.dumps({
                                'cnf_sha256':digest,'solver_answer':answer,'source_equations':proof}))
                trials.append(dict(case=name,rep=rep,solver=exe,status=status,seconds=seconds,
                                   route=answer.get('path'),replay_seconds=verify_seconds))
                print(trials[-1],flush=True)
        times = [t['seconds'] for t in trials if t['case']==name and t['solver']==NEW and t['status']=='UNSAT']
        info[name]['solved'] = len(times)
        info[name]['median_seconds'] = statistics.median(times) if times else None
    (OUT/'results.json').write_text(json.dumps(dict(protocol=info,trials=trials),indent=2))
if __name__=='__main__':
    main()
