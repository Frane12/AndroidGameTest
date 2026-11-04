#!/usr/bin/env python3
"""R110 frozen selector regression: same proofs, no lost base rows, deliberate skips."""
import hashlib,json,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r108_hidden_xor_benchmark as examples

def execute(exe,src,out,ev):
    p=subprocess.run([exe,str(src),str(out),str(ev)],capture_output=True,text=True,timeout=30)
    if p.returncode:
        raise RuntimeError('R110 selftest native failed '+p.stderr[-1200:])
    return json.loads(ev.read_text())

def main():
    if len(sys.argv)!=4:
        raise SystemExit('usage: r110_selector_selftest.py R107C R109 R110')
    base,prior,current=sys.argv[1:]
    with tempfile.TemporaryDirectory() as d:
        root=pathlib.Path(d)
        cases=examples.synthetic(root)
        proofs=0
        for c in cases:
            src=pathlib.Path(c['path'])
            values={}
            for label,executable in [('r107c',base),('r109',prior),('r110',current)]:
                dest=root/(label+'.cnf');ev=root/(label+'.json')
                values[label]=execute(executable,src,dest,ev)
                if not values[label]['gf2_unsat'] and src.read_bytes()!=dest.read_bytes():
                    raise AssertionError('R110 changed CNF without GF2 proof')
            c107=values['r107c'];c109=values['r109'];c110=values['r110']
            if c110['baseline_xors']!=c107['source_xors']:
                raise AssertionError('R110 baseline XOR coverage changed')
            if c110['source_xors']<c107['source_xors']:
                raise AssertionError('R110 dropped baseline XOR')
            if c110['gf2_unsat']!=c109['gf2_unsat']:
                raise AssertionError('R110 hidden GF2 contradiction disagrees with R109')
            if c['expected']=='SAT' and c110['gf2_unsat']:
                raise AssertionError('R110 unsound SAT-to-UNSAT transition')
            proofs+=bool(c110['gf2_unsat'] and not c107['gf2_unsat'])
            if c110['source_xors']<c109['source_xors']:
                raise AssertionError('R110 lost an R109 hidden row on small probes')
            print('R110_SELFTEST_CASE',c['name'],'source_xors',c107['source_xors'],
                  'r109',c109['source_xors'],'r110',c110['source_xors'],
                  'gate',c110['gate'],'gf2_proof',c110['gf2_unsat'],flush=True)
        assert proofs==3
        # Larger, completely non-overlapping positive triplets guarantee no
        # opposite-polarity twin core, no XOR and a selector rejection.
        src=root/'selector-negative-large.cnf'
        n=2100
        clauses=[(3*i+1,3*i+2,3*i+3) for i in range(n)]
        src.write_text(f'p cnf {n*3} {n}\n'+
                       ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        result=execute(current,src,root/'r110.cnf',root/'r110.json')
        assert not result['selector_enabled'],result
        assert result['source_xors']==0 and result['new_xors']==0
        assert result['gate']=='structural_twin_probe_reject',result
        assert src.read_bytes()==(root/'r110.cnf').read_bytes()
        print('R110_SELECTOR_NEGATIVE_PASS',result['gate'],
              'probe_twins',result['probe_twins'],flush=True)
    print('R110_FROZEN_SELECTOR_SELFTEST_PASS',flush=True)
if __name__=='__main__':main()
