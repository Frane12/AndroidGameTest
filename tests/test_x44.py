#!/usr/bin/env python3
"""X4.4: exhaustive tiny-CNF oracle and identical-prefix intervention audit."""
import hashlib,importlib.util,itertools,json,pathlib,random,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,'research')
import drnas_x44_counterfactual as X

def run(exe,p,cap,idx,sign):
    r=subprocess.run([str(exe),str(p),'--time',str(cap),'--mode','core','--stats',
       '--checkpoint',str(idx),'--force-polarity',str(sign)],capture_output=True,text=True,timeout=6)
    if r.returncode not in (0,10,20):raise AssertionError((r.returncode,r.stderr[-400:]))
    events={}
    for line in r.stderr.splitlines():
        if line.startswith('X44_CHECKPOINT '):events['checkpoint']=json.loads(line[len('X44_CHECKPOINT '):])
        if line.startswith('X44_STATS '):events['stats']=json.loads(line[len('X44_STATS '):])
    assert 'stats' in events
    return r,events

def oracle(n,clauses):
    for bits in itertools.product((False,True),repeat=n):
        if all(any(bits[abs(x)-1]==(x>0) for x in clause) for clause in clauses):return True
    return False

def main():
    exe=Path('build/drnas-x44')
    if not exe.is_file():raise RuntimeError('build/drnas-x44 missing')
    rng=random.Random(20261113)
    cnt=0; paired=0
    with tempfile.TemporaryDirectory() as td:
        for i in range(140):
            n=rng.randrange(3,10)
            clauses=[]
            for j in range(rng.randrange(2,29)):
                clause=[rng.choice((-1,1))*rng.randrange(1,n+1) for _ in range(rng.randrange(1,5))]
                clauses.append(clause)
            # Explicit tautologies are essential for the original-count fix.
            if i%7==0:clauses += [[1,-1],[2,-2]]
            path=Path(td)/f'tiny{i}.cnf'
            path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,x))+' 0\n' for x in clauses))
            expected=10 if oracle(n,clauses) else 20
            base,meta=run(exe,path,2.0,-1,0)
            assert base.returncode==expected,(i,expected,base.returncode)
            if expected==10:assert X.check_witness(path,base.stdout,n)
            if meta['stats']['decisions']>0:
                a,ra=run(exe,path,2.0,0,1)
                b,rb=run(exe,path,2.0,0,-1)
                for output in (a,b):
                    assert output.returncode==expected,(i,expected,output.returncode)
                    if expected==10:assert X.check_witness(path,output.stdout,n)
                aa,bb=ra['checkpoint'],rb['checkpoint']
                assert aa['prestate_fingerprint']==bb['prestate_fingerprint']
                assert aa['selected_var']==bb['selected_var']
                assert aa['default_sign']==bb['default_sign']
                paired+=1
            cnt+=1
        # Late checkpoint never reached must be explicitly reported as missing.
        path=Path(td)/'last.cnf';path.write_text('p cnf 1 1\n1 0\n')
        r,meta=run(exe,path,2.0,999,1)
        assert r.returncode==10 and not meta['stats']['checkpoint_hit']
        # Manifest: source families have nonoverlapping train/val/holdout.
        X.ROOT=Path(td)/'frozen'
        sources,sha=X.manifest()
        assert len(sources)==300 and len({s['sha256'] for s in sources})==300
        for split,fs in X.G.SPLITS.items():
            assert sum(s['split']==split for s in sources)==len(fs)*30
            assert {s['family'].removeprefix('GENERATED:') for s in sources if s['split']==split}==set(fs)
        assert hashlib.sha256((X.ROOT/'manifest.json').read_bytes()).hexdigest()==sha
    print('X44_ORACLE_PASS '+json.dumps({'small_CNF_sources':cnt,'paired_identical_prestates':paired,
       'manifest_sources':len(sources),'family_split_no_leakage':True},sort_keys=True))

if __name__=='__main__':main()