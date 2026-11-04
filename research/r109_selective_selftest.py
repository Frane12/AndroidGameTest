#!/usr/bin/env python3
"""R109 differential and negative-proof selftests against frozen R107C."""
import hashlib,itertools,json,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as check
import r108_hidden_xor_benchmark as examples

def run(binary,src,dest,ev):
    p=subprocess.run([binary,str(src),str(dest),str(ev)],capture_output=True,text=True,timeout=30)
    if p.returncode:
        raise RuntimeError('R109_FAIL_CLOSED native execution '+p.stderr[-1200:])
    return json.loads(ev.read_text())

def main():
    if len(sys.argv)!=3:
        raise SystemExit('usage: r109_selftest.py NATIVE_R109 NATIVE_R107C')
    fast,base=sys.argv[1:]
    with tempfile.TemporaryDirectory() as d:
        root=pathlib.Path(d)
        scenarios=examples.synthetic(root)
        for case in scenarios:
            src=pathlib.Path(case['path'])
            old=run(base,src,root/'baseline.cnf',root/'baseline.json')
            new=run(fast,src,root/'native.cnf',root/'native.json')
            assert new['baseline_xors']==old['source_xors'],case['name']
            assert new['source_xors']>=old['source_xors'],case['name']
            assert not(old['gf2_unsat'] and not new['gf2_unsat']),case['name']
            if case['expected']=='SAT':
                assert not new['gf2_unsat'],case['name']
            if new['gf2_unsat']:
                assert check.cnf_clauses(root/'native.cnf')[-1]==(),case['name']
                assert new['proof_length']>0
            else:
                assert (root/'native.cnf').read_bytes()==src.read_bytes()
            if hashlib.sha256(src.read_bytes()).hexdigest()!=case['sha256']:
                raise RuntimeError('R109 source mutation')
            print('R109_SELFTEST_CASE',case['name'],'old',old['source_xors'],
                  'new',new['source_xors'],'new_proof',new['gf2_unsat'],
                  'ms',round(new['prep_s']*1000,4),flush=True)
        assert sum(run(fast,pathlib.Path(c['path']),root/'native.cnf',root/'native.json')['gf2_unsat']
                   for c in scenarios if c['name'] in (
                       'r108_hidden1_unsat.cnf','r108_hidden2_unsat.cnf',
                       'r108_hidden2_xor5_unsat.cnf'))==3
        # Refuse malformed DIMACS and spurious row evidence.
        malformed=root/'invalid.cnf'
        malformed.write_text('p cnf 4 2\n1 2 3 0\n')
        p=subprocess.run([fast,str(malformed),str(root/'native.cnf'),str(root/'native.json')],
                         capture_output=True,text=True)
        assert p.returncode!=0
    print('R109_NATIVE_SELECTIVE_SELFTEST_PASS',flush=True)
if __name__=='__main__':main()
