#!/usr/bin/env python3
"""X2 differential testing against an independent exhaustive oracle.

All three X2 modes are checked; no external SAT solvers used.
"""
import argparse
import itertools
import json
import random
import subprocess
import tempfile
import time
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / 'build' / 'drnas-x2'
MODES = ('core', 'backdoor', 'x2')


def brute(n, cnf):
    for bits in itertools.product((False, True), repeat=n):
        if all(any(bits[abs(lit)-1] == (lit>0) for lit in c) for c in cnf):
            return True
    return False


def verify_witness(output, n, cnf):
    literals = []
    for line in output.splitlines():
        if line.startswith('v '):
            literals.extend(int(t) for t in line.split()[1:] if t!='0')
    if len(literals)!=n or {abs(x) for x in literals}!=set(range(1,n+1)):
        return False
    values={abs(x):x>0 for x in literals}
    return all(any(values[abs(l)]==(l>0) for l in c) for c in cnf)


def run(path, mode, n, clauses, expected):
    p=subprocess.run([str(BIN),str(path),'--mode',mode,'--time','1','--stats'],
                     text=True,capture_output=True,timeout=3)
    stats={}
    for line in p.stderr.splitlines():
        if line.startswith('X2_STATS '): stats=json.loads(line[9:])
    if p.returncode not in (10,20) or (p.returncode==10)!=expected or (
        p.returncode==10 and not verify_witness(p.stdout,n,clauses)):
        raise AssertionError({'mode':mode,'case':str(path),'expected':expected,
                              'clauses':clauses,'stdout':p.stdout,'stderr':p.stderr,
                              'return':p.returncode})
    return stats


def hidden(n=7, unsat=False, guard=1):
    # The original 2-CNF becomes 3-CNF by both guards s and !s.
    a,b=guard+1,guard+2
    core = [[a,b],[-a,b],[a,-b],[-a,-b]] if unsat else [[a,b],[-a,b]]
    clauses=[]
    for c in core:
        clauses.append(c+[guard]); clauses.append(c+[-guard])
    return n,clauses


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cases',type=int,default=2500)
    args=ap.parse_args()
    rng=random.Random(620261112)
    started=time.monotonic()
    counts={'random':0,'pure_2sat':0,'hidden':0,'modes':len(MODES),
            'trials':0,'backdoor_sat_seen':0,'backdoor_unsat_seen':0,
            'backdoor_nogoods_seen':0}
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'case.cnf'
        def one(n,clauses,category):
            # Header, multiline clauses and comments: parity with original-CNF parser.
            with path.open('w') as fh:
                fh.write(f'c category {category}\np cnf {n} {len(clauses)}\n')
                for k,c in enumerate(clauses):
                    if k%5==0: fh.write('c spaced comments\n')
                    if len(c)>=2 and k%3==0:
                        fh.write(f'{c[0]}\n'+' '.join(map(str,c[1:]))+' 0\n')
                    else:
                        fh.write(' '.join(map(str,c))+' 0\n')
            expected=brute(n,clauses)
            counts[category]+=1
            for mode in MODES:
                stats=run(path,mode,n,clauses,expected)
                counts['trials']+=1
                if mode!='core':
                    for stat,metric in [('backdoor_sat_seen','backdoor_sat'),
                                        ('backdoor_unsat_seen','backdoor_unsat'),
                                        ('backdoor_nogoods_seen','backdoor_nogoods')]:
                        counts[stat]+=int(stats.get(metric,0)>0)
        # Targeted structural tests first; make sure the new path runs.
        for unsat in (False,True):
            for n in range(3,11):
                one(*hidden(n,unsat),'hidden')
        for i in range(320):
            n=rng.randint(2,12)
            cs=[]
            for j in range(rng.randint(0,55)):
                c=[rng.choice((-1,1))*rng.randint(1,n) for _ in range(rng.randint(1,2))]
                cs.append(c)
            one(n,cs,'pure_2sat')
        for i in range(args.cases):
            n=rng.randint(0,10)
            cs=[]
            for j in range(rng.randint(0,45)):
                width=rng.randrange(0,min(n+4,8)) if n else 0
                cs.append([rng.choice((-1,1))*rng.randint(1,n) for _ in range(width)])
            if i%29==0 and n:
                cs += [[v] for v in range(1,n+1)] + [[-v for v in range(1,n+1)]]
            one(n,cs,'random')
    assert counts['backdoor_sat_seen']>0,counts
    assert counts['backdoor_unsat_seen']>0,counts
    assert counts['backdoor_nogoods_seen']>0,counts
    counts['elapsed_s']=round(time.monotonic()-started,3)
    print('X2_DIFFERENTIAL_PASS '+json.dumps(counts,sort_keys=True),flush=True)

if __name__=='__main__':main()