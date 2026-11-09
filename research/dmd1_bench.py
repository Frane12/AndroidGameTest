#!/usr/bin/env python3
"""DRNAS DMD1: one-core, proof-checked ANF preprocessor E2E vs shadow vs Kissat.

Reused EQUIV7 SHA-frozen originals are DEVELOPMENT, not unseen blind holdout.
Independent local truth-table replay proves every appended CNF clause.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import resource
import subprocess
import tempfile
import time

PROTO = 'DRNAS-DMD1-ANF-LOCAL-EXHAUSTIVE-24OFFICIAL-4TOY-4ARMS-2REP-v1'
ARMS = ('kissat_original', 'dmd3_active', 'dmd15_shadow', 'dmd15_active')
CAP = 6.0
REPS = 2
SHARDS = 4
SOURCE = pathlib.Path('mre_equiv7')
ROOT = pathlib.Path('mre_dmd1')
BIN = pathlib.Path('mre_dmd1/bin/dmd1_anf')
KISSAT = pathlib.Path('built/bin/kissat_4_0_4')


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def read_cnf(path):
    vars_n = None
    clauses = []
    current = []
    expected = None
    for line in pathlib.Path(path).read_text().splitlines():
        tokens = line.split()
        if not tokens or tokens[0] in ('c', '%'):
            continue
        if tokens[0] == 'p':
            need(vars_n is None and len(tokens) == 4 and tokens[1] == 'cnf', 'DIMACS header')
            vars_n, expected = int(tokens[2]), int(tokens[3])
            continue
        need(vars_n is not None, 'header missing')
        for token in tokens:
            lit = int(token)
            if lit == 0:
                clauses.append(tuple(current))
                current = []
            else:
                need(0 < abs(lit) <= vars_n, 'bad literal')
                current.append(lit)
    need(vars_n is not None and not current and len(clauses) == expected, 'bad clause count')
    return vars_n, clauses


def holds(clauses, assignment):
    return all(any(assignment.get(abs(l), False) == (l > 0) for l in c) for c in clauses)


def proof_replay(original, augmented, proof):
    n, clauses = read_cnf(original)
    lemmas = proof['lemmas']
    need(proof['protocol'] == 'DMD1-ANF-LOCAL-EXHAUSTIVE-v1', 'bad proof protocol')
    need(len(lemmas) <= 24, 'too many lemmas')
    for lemma in lemmas:
        ids, clause = lemma['source_ids'], lemma['clause']
        need(ids and all(isinstance(i, int) and 0 <= i < len(clauses) for i in ids), 'bad source IDs')
        source = [clauses[i] for i in ids]
        variables = sorted({abs(l) for c in source for l in c})
        need(len(variables) <= 8, 'source too large for independent exhaustive proof')
        need(all(isinstance(x, int) and 0 < abs(x) <= n and abs(x) in variables for x in clause), 'invalid lemma')
        for mask in range(1 << len(variables)):
            state = {v: bool(mask & (1 << j)) for j, v in enumerate(variables)}
            if holds(source, state):
                need(holds([clause], state), 'LOCAL PROOF FAILURE: lemma not implied by original CNF')
    need((augmented.exists() == bool(lemmas)), 'augmented CNF mismatch')
    if lemmas:
        nn, output = read_cnf(augmented)
        need(nn == n and output[:len(clauses)] == clauses, 'original CNF modified')
        need(output[len(clauses):] == [tuple(x['clause']) for x in lemmas], 'appended lemmas mismatch')
    return n, clauses


def toy_cases(toydir):
    toydir.mkdir(parents=True, exist_ok=True)
    cases = []
    for idx in range(4):
        a, b, c = (1, 2, 3) if idx == 0 else (idx * 3 + 1, idx * 3 + 2, idx * 3 + 3)
        clauses = [[a, -b, c], [a, b, -c], [b, c], [-b, -c]]
        if idx % 2:
            clauses = list(reversed(clauses))
        if idx == 2:
            clauses += [[-a, b, c], [a, -b, -c]]  # still satisfiable
        filename = f'toy{idx}.cnf'
        n = max(a, b, c)
        text = f'p cnf {n} {len(clauses)}\n' + ''.join(' '.join(map(str, c)) + ' 0\n' for c in clauses)
        path = toydir / filename
        path.write_text(text)
        cases.append(dict(cohort='synthetic_toy', filename=filename, sha256=sha(path), path=str(path)))
    return cases


def cases():
    m = json.loads((SOURCE / 'manifest.json').read_text())
    need(len(m['cases']) == 48 and m['source_only_preselection'], 'unexpected EQUIV7 source')
    selected = sorted(m['cases'], key=lambda x: x['sha256'])[:24]
    out = []
    for c in selected:
        path = SOURCE / 'cases' / c['filename']
        need(path.is_file() and sha(path) == c['sha256'], 'SHA mismatch: ' + c['filename'])
        out.append(dict(cohort='reused_equiv7_original', filename=c['filename'], sha256=c['sha256'], path=str(path)))
    out += toy_cases(ROOT / 'toy')
    need(len(out) == 28 and len({x['sha256'] for x in out}) == 28, 'selection mismatch')
    return out


def run_process(cmd, timeout, cpu):
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.monotonic()
    try:
        p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True,
                           timeout=timeout, preexec_fn=lambda: os.sched_setaffinity(0, {cpu}))
        return p.returncode, p.stdout, p.stderr, time.monotonic()-start, (
            resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime + resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime
            - before.ru_utime - before.ru_stime), False
    except subprocess.TimeoutExpired:
        return None, '', '', time.monotonic()-start, (
            resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime + resource.getrusage(resource.RUSAGE_CHILDREN).ru_stime
            - before.ru_utime - before.ru_stime), True


def outcome(rc, stdout, clauses):
    if rc == 20:
        need('s UNSATISFIABLE' in stdout.splitlines(), 'invalid UNSAT verdict line')
        return 'UNSAT', False
    need(rc == 10 and 's SATISFIABLE' in stdout.splitlines(), 'unexpected solver exit code/output')
    assignment = {}
    for line in stdout.splitlines():
        if not line.startswith('v '):
            continue
        for token in line.split()[1:]:
            v = int(token)
            if v == 0:
                continue
            need(abs(v) not in assignment or assignment[abs(v)] == (v > 0), 'contradictory SAT witness')
            assignment[abs(v)] = v > 0
    need(assignment and holds(clauses, assignment), 'SAT witness fails original CNF')
    return 'SAT', True


def trial(case, arm, rep):
    cpu = sorted(os.sched_getaffinity(0))[0]
    with tempfile.TemporaryDirectory(prefix='dmd1-') as td:
        tmp = pathlib.Path(td)
        orig = pathlib.Path(case['path'])
        start = time.monotonic()
        elapsed = 0.0
        proof = dict(groups=0, nonlinear_relations=0, lemmas=[], tested_assignments=0, abstain=False, timed_out=False)
        target = orig
        if arm != 'kissat_original':
            active = arm.endswith('_active')
            budget_ms = 3 if arm == 'dmd3_active' else 15
            augmented, proof_path = tmp/'augmented.cnf', tmp/'local_proof.json'
            rc, out, err, dt, pcpu, timed = run_process([BIN, orig, augmented, proof_path, budget_ms, 48], CAP, cpu)
            need(not timed and rc == 0 and proof_path.is_file(), 'DMD1 preprocessing failed closed: '+err[-500:])
            proof = json.loads(proof_path.read_text())
            _, clauses = proof_replay(orig, augmented, proof)
            if active and proof['lemmas']:
                target = augmented
        else:
            _, clauses = read_cnf(orig)
        elapsed = time.monotonic() - start
        remaining = max(0.001, CAP - elapsed)
        if elapsed >= CAP:
            status, verified, solver_cpu = 'TIMEOUT', False, 0.0
        else:
            rc, out, err, dt, solver_cpu, timed = run_process([KISSAT, target], remaining, cpu)
            if timed:
                status, verified = 'TIMEOUT', False
            else:
                status, verified = outcome(rc, out, clauses)
        total = time.monotonic() - start
        if total >= CAP and status == 'TIMEOUT':
            total = CAP
        return dict(protocol=PROTO, cohort=case['cohort'], source_sha256=case['sha256'],
                    original_file=case['filename'], rep=rep, arm=arm, cpu=[cpu],
                    e2e_s=round(total, 6), PAR2_s=round(total if status != 'TIMEOUT' else 2*CAP, 6),
                    status=status, SAT_original_witness_verified=verified,
                    UNSAT_independent_LRAT=False, solver_CPU_s=round(solver_cpu, 6),
                    lemmas=len(proof['lemmas']), groups=proof['groups'], nonlinear_relations=proof['nonlinear_relations'],
                    tested_assignments=proof['tested_assignments'], proof_replayed=(arm != 'kissat_original'),
                    abstain=proof['abstain'], timed_out_discovery=proof['timed_out'])


def selftest():
    with tempfile.TemporaryDirectory(prefix='dmd1-test-') as td:
        root = pathlib.Path(td)
        rnd = random.Random(1789)
        ntests = 0
        for idx in range(42):
            if idx == 0:
                clauses = [(1,-2,3),(1,2,-3),(2,3),(-2,-3)]
                n=3
            else:
                n = rnd.randint(2, 6)
                clauses = []
                for _ in range(rnd.randint(3, 17)):
                    k = rnd.randint(1, min(4, n))
                    vs = rnd.sample(range(1,n+1), k)
                    clauses.append(tuple(x if rnd.randrange(2) else -x for x in vs))
            orig, aug, cert = root/'test.cnf', root/'aug.cnf', root/'proof.json'
            orig.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str, c))+' 0\n' for c in clauses))
            aug.unlink(missing_ok=True)
            rc,out,err,elapsed,cpu,timed = run_process([BIN,orig,aug,cert,100,64],3.0, sorted(os.sched_getaffinity(0))[0])
            need(rc == 0 and not timed, 'C++ selftest failed: '+err)
            p = json.loads(cert.read_text())
            nn, original = proof_replay(orig, aug, p)
            if idx == 0:
                need(any(x['clause'] == [1] for x in p['lemmas']), 'missing discovered a=1 in toy')
            test = read_cnf(aug)[1] if p['lemmas'] else original
            for bits in range(1<<n):
                model = {i+1:bool(bits & (1<<i)) for i in range(n)}
                need(holds(original,model) == holds(test,model), 'semantic equivalence failed')
            ntests += 1
        print('DMD1_SELFTEST_PASS', json.dumps(dict(cases=ntests, exhaustive_models=True, toy_unit=True)), flush=True)


def bench(shard):
    cs = cases()
    need(0 <= shard < SHARDS, 'bad shard')
    ROOT.mkdir(exist_ok=True)
    rows = []
    for i, case in enumerate(cs):
        if i % SHARDS != shard:
            continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(int(case['sha256'][:7],16)+rep).shuffle(arms)
            for arm in arms:
                r = trial(case, arm, rep)
                rows.append(r)
                print('DMD1_TRIAL', json.dumps(r, sort_keys=True), flush=True)
    expected = len([c for i,c in enumerate(cs) if i%SHARDS == shard])*REPS*len(ARMS)
    need(len(rows) == expected, 'missing trials')
    (ROOT/f'shard-{shard}.json').write_text(json.dumps(rows, sort_keys=True))
    print('DMD1_SHARD_PASS', shard, expected, flush=True)


def audit():
    cs=cases()
    rows=[]
    for shard in range(SHARDS):
        path=ROOT/f'shard-{shard}.json'
        need(path.is_file(), 'missing shard: '+str(path))
        data=json.loads(path.read_text())
        need(len(data)==len([c for i,c in enumerate(cs) if i%SHARDS == shard])*REPS*len(ARMS), 'shard count')
        rows.extend(data)
    expected={(c['sha256'],rep,arm) for c in cs for rep in range(REPS) for arm in ARMS}
    got={(r['source_sha256'],r['rep'],r['arm']) for r in rows}
    need(len(rows)==len(expected)==224 and got==expected, 'not exactly 224 SHA-paired trials')
    need(all(r['protocol']==PROTO and len(r['cpu'])==1 for r in rows), 'protocol or core drift')
    need(all(r['status']!='SAT' or r['SAT_original_witness_verified'] for r in rows), 'unverified SAT')
    scores={}
    for arm in ARMS:
        a=[r for r in rows if r['arm']==arm]
        scores[arm]=dict(trials=len(a),solved=sum(r['status']!='TIMEOUT' for r in a),
                         SAT_verified=sum(r['status']=='SAT' for r in a),
                         UNSAT_no_independent_LRAT=sum(r['status']=='UNSAT' for r in a),
                         PAR2_s=round(sum(r['PAR2_s'] for r in a),4),
                         E2E_s=round(sum(r['e2e_s'] for r in a),4),
                         lemmas=sum(r['lemmas'] for r in a),
                         discoveries=sum(r['nonlinear_relations'] for r in a),
                         abstained=sum(r['abstain'] for r in a))
    base=scores['kissat_original']['PAR2_s']
    ratios={k:round(base/v['PAR2_s'],5) for k,v in scores.items()}
    result=dict(protocol=PROTO, total_trials=len(rows), original_sources=24,
                synthetic_toy_sources=4, source_selection='REUSED_EQUIV7_FIRST24_SORTED_SHA_NO_OUTCOME_FILTER',
                not_blind=True, cpu_policy='ONE_PINNED_LOGICAL_CORE_PER_CHILD',
                cap_s=CAP, independent_UNSAT_LRAT=False,
                independent_exhaustive_local_clause_replay=True, scores=scores,
                PAR2_speedup_vs_kissat=ratios,
                no_auto_promotion=True)
    (ROOT/'audit.json').write_text(json.dumps(result,sort_keys=True,indent=2))
    print('DMD1_FINAL',json.dumps(result,sort_keys=True),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('selftest','bench','audit'))
    p.add_argument('--shard',type=int,default=0)
    a=p.parse_args()
    if a.action=='selftest':selftest()
    elif a.action=='bench':bench(a.shard)
    else:audit()