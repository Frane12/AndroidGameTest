#!/usr/bin/env python3
"""Native GF2 smoke and negative tests, independent CNF checker cross-validation."""
import pathlib,subprocess,tempfile,sys
from drnas_ltm9c_gf2_verify import verify
BIN='mre_atlas23/bin/drnas_ltm9d'
def xor(v,parity):
    return [[(-x if (mask>>j)&1 else x) for j,x in enumerate(v)]
            for mask in range(1<<len(v)) if mask.bit_count()%2 != parity]
def run(c):
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/'case.cnf'
        p.write_text('p cnf 8 '+str(len(c))+'\n'+''.join(' '.join(map(str,row))+' 0\n' for row in c))
        x=subprocess.run([BIN,str(p),'--mode','LTM8_FAST','--time','2','--seed','17','--policy','1.0,0.85'],
                         capture_output=True,text=True,timeout=4)
        return x.returncode,x.stdout
cases=[
    ('direct_unsat',xor([1,2,3],0)+xor([1,2,3],1),True),
    ('gauss_unsat',xor([1,2],0)+xor([2,3],0)+xor([1,3],1),True),
    ('single_sat',xor([1,2,3],0),False),
    ('gauss_sat',xor([1,2],0)+xor([2,3],0)+xor([1,3],0),False),
    ('incomplete',xor([1,2,3],0)+xor([1,2,3],1)[:-1],False),
]
for name,c,expect in cases:
    independent=verify(c)
    assert independent==expect,(name,independent)
    rc,out=run(c)
    native='LTM9D_GF2_CERT' in out
    assert native==expect,(name,rc,out)
    assert (rc==20)==expect,(name,rc,out)
    print('LTM9D_GF2_SELFTEST',name,'native=',native,'independent=',independent)
print('LTM9D_GF2_SELFTEST_PASS')
