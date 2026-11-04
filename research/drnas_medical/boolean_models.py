#!/usr/bin/env python3
"""Research-only synthetic Boolean regulatory networks to CNF. No clinical data."""
from __future__ import annotations
import argparse, hashlib, itertools, json, random
from pathlib import Path

FAMILIES = ('memory', 'toggle', 'inhibition', 'xor', 'mixed')

def network(n: int, family: str, seed: int):
    if n < 3 or family not in FAMILIES:
        raise ValueError('requires at least 3 nodes and a known family')
    rng = random.Random(seed + n * 1009 + sum(ord(c) for c in family))
    rules = []
    for i in range(n):
        if family == 'memory':
            rules.append(('copy', i, i))
        elif family == 'toggle':
            rules.append(('not' if i == 0 else 'copy', i, i))
        elif family == 'inhibition':
            rules.append(('and_not', (i - 1) % n, (i + 1) % n))
        elif family == 'xor':
            rules.append(('xor', (i - 1) % n, (i + 1) % n))
        else:
            a, b = rng.sample(range(n), 2)
            rules.append((rng.choice(('copy','not','and_not','or','xor')), a, b))
    return rules

def evaluate(rule, state):
    op, a, b = rule
    x, y = state[a], state[b]
    return {'copy': lambda: x, 'not': lambda: not x,
            'and_not': lambda: x and not y,
            'or': lambda: x or y, 'xor': lambda: x != y}[op]()

def next_state(rules, state):
    return tuple(evaluate(rule, state) for rule in rules)

def all_states(n):
    return itertools.product((False, True), repeat=n)

def expected(rules, period):
    """Independent exhaustive state-transition oracle for small networks."""
    n = len(rules)
    for state in all_states(n):
        end = state
        for _ in range(period):
            end = next_state(rules, end)
        if end == state and (period == 1 or next_state(rules, state) != state):
            return 'SAT', state
    return 'UNSAT', None

def relation(out_var, input_vars, fn):
    """Exact truth-table CNF, including self-loops and repeated inputs."""
    vars_used = sorted(set((out_var, *input_vars)))
    clauses = []
    for bits in itertools.product((False, True), repeat=len(vars_used)):
        assignment = dict(zip(vars_used, bits))
        if assignment[out_var] != fn(*(assignment[var] for var in input_vars)):
            clauses.append(tuple(-var if assignment[var] else var for var in vars_used))
    return clauses

def encode(rules, period):
    if period not in (1, 2):
        raise ValueError('period must be 1 or 2')
    n = len(rules)
    clauses = []
    for t in range(period):
        src = t * n
        dst = ((t+1) % period) * n
        for i, (op,a,b) in enumerate(rules):
            def f(x, y, operation=op):
                if operation == 'copy': return x
                if operation == 'not': return not x
                if operation == 'and_not': return x and not y
                if operation == 'or': return x or y
                if operation == 'xor': return x != y
                raise ValueError(operation)
            clauses.extend(relation(dst+i+1, (src+a+1,src+b+1), f))
    if period == 2:
        for i in range(n):
            y = 2*n+i+1
            clauses.extend(relation(y, (i+1,n+i+1), lambda x,z: x != z))
        clauses.append(tuple(2*n+i+1 for i in range(n)))
    return n*period + (n if period == 2 else 0), sorted(set(clauses))

def dimacs(nvars, clauses):
    return f'p cnf {nvars} {len(clauses)}\n' + ''.join(' '.join(map(str,c))+' 0\n' for c in clauses)

def assignment_valid(clauses, state0, state1=None):
    n = len(state0)
    values = {i+1:state0[i] for i in range(n)}
    if state1 is not None:
        values.update({n+i+1:state1[i] for i in range(n)})
        values.update({2*n+i+1:state0[i] != state1[i] for i in range(n)})
    return all(any(values[abs(lit)] == (lit>0) for lit in clause) for clause in clauses)

def selftest():
    counts = 0
    for family in FAMILIES:
        for period in (1,2):
            rules=network(4,family,101)
            _, clauses = encode(rules, period)
            for s0 in all_states(4):
                if period == 1:
                    should = next_state(rules, s0) == s0
                    actual = assignment_valid(clauses,s0)
                    assert actual == should, (family,period,s0)
                    counts+=1
                else:
                    for s1 in all_states(4):
                        should = (next_state(rules,s0)==s1 and next_state(rules,s1)==s0 and s0!=s1)
                        actual = assignment_valid(clauses,s0,s1)
                        assert actual == should, (family,period,s0,s1)
                        counts+=1
            status, candidate = expected(rules,period)
            assert (status=='SAT') == (candidate is not None)
    print('DRNAS_MEDICAL_BOOLEAN_CNF_SELFTEST_PASS exhaustive_assignments=',counts,flush=True)

def generate(out, families, sizes, periods, seed):
    out.mkdir(parents=True,exist_ok=True)
    items=[]
    for family in families:
        for n in sizes:
            for period in periods:
                rules=network(n,family,seed)
                nvars,clauses=encode(rules,period)
                filename=f'{family}_n{n:03d}_p{period}.cnf'
                dest=out/filename
                dest.write_text(dimacs(nvars,clauses))
                status='UNKNOWN'
                if n<=12: status=expected(rules,period)[0]
                items.append(dict(name=filename, family=family, nodes=n, period=period,
                     variables=nvars, clauses=len(clauses), sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                     expected=status, data_origin='synthetic_biology_inspired_not_empirical',
                     model_rules=[list(x) for x in rules]))
    manifest=dict(protocol='DRNAS-MEDICAL-V0.1-BOOLEAN-SYNTHETIC',seed=seed,
         clinical_data=False, empirical_biological_validation=False,
         cases=items)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print('DRNAS_MEDICAL_GENERATED cases=',len(items),'out=',out,flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['selftest','generate'])
    p.add_argument('--out',default='medical-results/cnfs')
    p.add_argument('--families',default='memory,toggle,inhibition,xor,mixed')
    p.add_argument('--sizes',default='6,10,20')
    p.add_argument('--periods',default='1,2')
    p.add_argument('--seed',type=int,default=20261104)
    a=p.parse_args()
    if a.command=='selftest': selftest()
    else: generate(Path(a.out),a.families.split(','),[int(x) for x in a.sizes.split(',')],
                   [int(x) for x in a.periods.split(',')],a.seed)

if __name__=='__main__': main()
