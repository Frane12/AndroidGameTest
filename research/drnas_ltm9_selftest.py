#!/usr/bin/env python3
"""Check the LTM9 short-circuit against small exhaustive problems and SHA-renamed examples."""
import os,random,pathlib,subprocess,tempfile
import drnas_atlas13_generator as G
rng=random.Random(912730)
bin='mre_atlas23/bin/drnas_ltm9'
def run(path,n,clauses,expect_unsat=None,expect_struct=None):
    path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
    p=subprocess.run([bin,str(path),'--mode','LTM8_FAST','--time','3','--seed','13','--policy','1.0,0.85'],
        text=True,capture_output=True,timeout=4,env=dict(os.environ,DRNAS_LTM8_MEMORY=''))
    assert p.returncode in (10,20),(p.returncode,p.stdout,p.stderr)
    marker='LTM9_PHP_CERT' in p.stdout
    if expect_struct is not None: assert marker==expect_struct,(n,clauses,p.stdout)
    if expect_unsat is not None: assert (p.returncode==20)==expect_unsat,(n,clauses,p.stdout)
    if marker: assert p.returncode==20
with tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d)/'small.cnf'
    for i in range(100):
        n=rng.randrange(1,9)
        clauses=[[rng.choice((-1,1))*v for v in rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))]
                 for _ in range(rng.randrange(0,n*5+1))]
        sat=any(all(any(bool((bits>>(abs(l)-1))&1)==(l>0) for l in c) for c in clauses) for bits in range(1<<n))
        run(p,n,clauses,expect_unsat=not sat)
    for family,positive in [('pigeonhole_unsat',True),('graph3color_unsat',True),
                            ('pigeonhole_sat',False),('graph3color_sat',False)]:
        for i in (0,1):
            n,clauses,_=G.build(family,i)
            run(p,n,clauses,expect_struct=positive,expect_unsat=positive if positive else None)
    # The constructive 2-column/3-row case must be detected, but a 2x2
    # satisfiable case must not be shortcut.
    def php(h,r):
        def v(a,b):return a*h+b+1
        cs=[[v(a,b) for b in range(h)] for a in range(r)]
        cs += [[-v(a,b),-v(c,b)] for b in range(h) for a in range(r) for c in range(a+1,r)]
        return h*r,cs
    for h,r,expected in [(2,3,True),(3,4,True),(2,2,False),(3,3,False)]:
        n,cs=php(h,r);run(p,n,cs,expect_struct=expected,expect_unsat=expected)
    n,cs=php(2,3)
    cs.remove([-1,-3])
    run(p,n,cs,expect_struct=False,expect_unsat=False)
print('LTM9_SELFTEST_PASS brute_force=100 structural=8 cardinality=5')
