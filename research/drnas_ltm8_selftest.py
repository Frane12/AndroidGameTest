#!/usr/bin/env python3
"""Independent brute-force SAT/UNSAT and original-witness checks."""
import itertools, json, os, pathlib, random, subprocess, tempfile
ROOT=pathlib.Path(__file__).resolve().parent.parent
BIN=ROOT/'mre_atlas23/bin/drnas_ltm8'
rng=random.Random(20261112)
def solve(path,mode,seed=7,env=None):
    if env is None: env=dict(os.environ,DRNAS_LTM8_MEMORY="")
    p=subprocess.run([str(BIN),str(path),'--mode',mode,'--time','2','--seed',str(seed),'--policy','1.0,0.85'],capture_output=True,text=True,timeout=3,env=env)
    assert p.returncode in (0,10,20),(p.returncode,p.stderr)
    return p
with tempfile.TemporaryDirectory() as d:
    root=pathlib.Path(d);cnf=root/'case.cnf';checks=0
    for case in range(320):
        n=rng.randrange(1,10)
        cs=[[rng.choice((-1,1))*v for v in rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))] for _ in range(rng.randrange(0,7*n+1))]
        if case==0:cs=[[]]
        expected=any(all(any(bool((bits>>(abs(l)-1))&1)==(l>0) for l in c) for c in cs) for bits in range(1<<n))
        cnf.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
        for mode in ('LTM8_FAST','LTM8_CHAOS'):
            p=solve(cnf,mode,case+1)
            assert p.returncode==(10 if expected else 20),(case,mode,p.stdout)
            if expected:
                values={abs(int(v)):int(v)>0 for line in p.stdout.splitlines() if line.startswith('v ') for v in line[2:].split() if int(v)}
                assert all(any(values.get(abs(l))==(l>0) for l in c) for c in cs)
            checks+=1
    # A full solve large enough to cross learning windows, deletion and restart paths.
    import drnas_atlas13_generator as G
    n,cs,_=G.build('pigeonhole_unsat',0)
    cnf.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
    for mode in ('LTM8_FAST','LTM8_CHAOS'):
        env=dict(os.environ,DRNAS_LTM8_MEMORY=str(root/'memory'))
        first=solve(cnf,mode,7,env)
        assert first.returncode==20,first.stdout
        import re
        assert int(re.search(r'windows=(\d+)',first.stdout)[1])>0,first.stdout
        second=solve(cnf,mode,7,env)
        assert int(re.search(r'loaded=(\d+)',second.stdout)[1])>0,second.stdout
        assert second.returncode==20
        # Independent fresh sessions with equal seed must take the same decisions.
        a=solve(cnf,mode);b=solve(cnf,mode)
        assert re.search(r'conflicts=(\d+) decisions=(\d+)',a.stdout).groups()==re.search(r'conflicts=(\d+) decisions=(\d+)',b.stdout).groups()
    print(json.dumps(dict(bruteforce_checks=checks,memory_roundtrip=True,reproducible_seed=True)))
