#!/usr/bin/env python3
"""Standalone differential tests for the DRNAS mixed-CNF 2SAT UNSAT guard.
No solver oracle: exhaustive assignments and independent RUP replay.
"""
import itertools
import pathlib
import random
import subprocess
import sys
import tempfile

exe = pathlib.Path(sys.argv[1]).resolve()
rng = random.Random(15112026)

def sat(n, clauses):
    for bits in itertools.product((False, True), repeat=n):
        if all(any(bits[abs(l)-1] == (l>0) for l in c) for c in clauses):
            return True
    return False

def rup_check(clauses, drat):
    work = [tuple(c) for c in clauses]
    assert drat.strip()
    for line in drat.splitlines():
        row = [int(i) for i in line.split()]
        assert row[-1] == 0
        proposed = tuple(row[:-1])
        assign = {abs(x): x < 0 for x in proposed}
        conflict = False
        while True:
            changed = False
            for c in work:
                pending = []
                satisfied = False
                for l in c:
                    state = assign.get(abs(l))
                    if state is None:
                        pending.append(l)
                    elif state == (l > 0):
                        satisfied = True
                        break
                if satisfied:
                    continue
                if not pending:
                    conflict = True
                    break
                if len(pending) == 1:
                    l = pending[0]
                    if abs(l) in assign and assign[abs(l)] != (l>0):
                        conflict = True
                        break
                    if abs(l) not in assign:
                        assign[abs(l)] = l>0
                        changed = True
            if conflict or not changed:
                break
        assert conflict, ('RUP_failed', proposed)
        work.append(proposed)
    assert work[-1] == ()

def check(n, clauses, pure, number, tmp):
    source = tmp / f'case-{number}.cnf'
    proof = tmp / f'case-{number}.drat'
    source.write_text(
        f'p cnf {n} {len(clauses)}\n'
        + ''.join(' '.join(map(str,c))+' 0\n' for c in clauses)
    )
    result = subprocess.run(
        [str(exe), str(source), '--proof', str(proof), '--time', '10'],
        capture_output=True, text=True,
    )
    assert result.returncode in (0,20), (number, result.stdout, result.stderr)
    truth = sat(n, clauses)
    if result.returncode == 20:
        assert not truth, ('unsound',number)
        assert proof.exists()
        rup_check(clauses, proof.read_text())
    else:
        assert not proof.exists()
        if pure:
            assert truth, ('missed_pure_2sat_UNSAT',number)
    return result.returncode == 20

def permute(clauses, mapping, negated):
    out = []
    for c in clauses:
        out.append([(-1 if (l<0)^negated[abs(l)-1] else 1)*mapping[abs(l)-1] for l in c])
    return out

def main():
    count = 0
    found = 0
    with tempfile.TemporaryDirectory() as folder:
        tmp = pathlib.Path(folder)
        examples = [
            (2,[[1,2],[-1,2],[1,-2],[-1,-2]], True),
            (3,[[1,2],[-1,2],[1,-2],[-1,-2],[1,2,3]], False),
            (3,[[1,2,3],[-1,2,3],[-1,-2,3]],False),
            (1,[[]], True),
            (1,[[1]], True),
            (2,[[1],[-1],[1,2]], False),
        ]
        for n,c,pure in examples:
            found += check(n,c,pure,count,tmp)
            count += 1
        for n in range(1,9):
            for _ in range(75):
                pure = bool(rng.getrandbits(1))
                c = [[rng.choice((-1,1))*rng.randint(1,n)
                      for _ in range(rng.choice([1,2] if pure else [1,2,3,4]))]
                     for __ in range(rng.randrange(0,35))]
                found += check(n,c,pure,count,tmp)
                count += 1
        base = [[1,2],[-1,2],[1,-2],[-1,-2],[1,2,3]]
        for _ in range(75):
            mapping=list(range(1,5));rng.shuffle(mapping)
            negated=[bool(rng.getrandbits(1)) for __ in range(4)]
            c=permute(base,mapping,negated)
            found += check(4,c,False,count,tmp)
            count+=1
        print(f'DRNAS_2SAT_GUARD_TEST PASS total={count} certified_unsat={found} false_unsat=0')
if __name__ == '__main__':
    main()
