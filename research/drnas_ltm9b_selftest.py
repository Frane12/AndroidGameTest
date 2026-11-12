#!/usr/bin/env python3
"""Metamorphic checks on original CNFs, explicit PHP proof and negative cases."""
import os,random,tempfile,subprocess,pathlib
import drnas_atlas13_generator as G
from drnas_ltm9b_verify import verify
BIN='mre_atlas23/bin/drnas_ltm9b'
def run(path,n,clauses):
    path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
    p=subprocess.run([BIN,str(path),'--mode','LTM8_FAST','--time','3','--seed','11','--policy','1.0,0.85'],
                     text=True,capture_output=True,timeout=4,env=dict(os.environ,DRNAS_LTM8_MEMORY=''))
    assert p.returncode in (10,20),(p.returncode,p.stdout,p.stderr)
    return p.returncode,verify(clauses,p.stdout)
with tempfile.TemporaryDirectory() as d:
    path=pathlib.Path(d)/'test.cnf'
    count=0
    for fam in ('pigeonhole_unsat','graph3color_unsat'):
        for index in (301,302):
            n,cs,_=G.build(fam,index)
            rc,cert=run(path,n,cs)
            assert rc==20 and cert,(fam,index,rc,cert)
            count+=1
            perm=list(range(1,n+1))
            random.Random(index+19).shuffle(perm)
            mapped=[[perm[abs(l)-1]*(1 if l>0 else -1) for l in c] for c in cs]
            random.Random(index+31).shuffle(mapped)
            for c in mapped:random.Random(len(c)*17+index).shuffle(c)
            rc,cert=run(path,n,mapped)
            assert rc==20 and cert,('metamorphic',fam,index)
            count+=1
    n,cs,_=G.build('pigeonhole_sat',301)
    rc,cert=run(path,n,cs)
    assert rc==10 and not cert
    count+=1
print('LTM9B_SELFTEST_PASS structural_and_permuted=',count)
