#!/usr/bin/env python3
"""Preflight on known controls only; never reads the blind input directory."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import benchmark as b
from freeze import dimensions

def main():
    b.pin()
    with tempfile.TemporaryDirectory(prefix='math5-blind-selftest-',dir=b.ROOT) as tmp:
        d=Path(tmp);sat=d/'sat.cnf';unsat=d/'unsat.cnf'
        sat.write_text('p cnf 2 2\n1 2 0\n-1 2 0\n')
        unsat.write_text('p cnf 2 4\n1 2 0\n-1 2 0\n1 -2 0\n-1 -2 0\n')
        model=d/'model.txt';model.write_text('s SATISFIABLE\nv 1 2 0\n');assert b.model_check(sat,model)
        model.write_text('s SATISFIABLE\nv 1 -2 0\n');assert not b.model_check(sat,model)
        model.write_text('s SATISFIABLE\nv 1 -1 2 0\n');assert not b.model_check(sat,model)
        model.write_text('s SATISFIABLE\nv 1 2 0\n');assert not b.model_check(unsat,model)
        assert dimensions(sat.read_bytes())==(2,2)
        try:dimensions(b'p cnf 2 2\n1 0\n')
        except ValueError:pass
        else:raise AssertionError('malformed CNF accepted')
        for i,(cnf,wanted) in enumerate([(sat,'SAT_VERIFIED'),(unsat,'UNSAT_VERIFIED')]):
            s=dict(id=i,family='CONTROL',path=str(cnf.relative_to(b.ROOT)),sha256=b.sha(cnf))
            for arm in b.P['arms']:
                row=b.trial(s,arm,0,d/f'{i}-{arm}',cap=5)
                assert row['status']==wanted and row['accepted'] and not row['critical'],row
                assert row['strict_accepted']==(row['certificate_kind'] in ('MODEL','DRAT')),row
        expired=b.run([sys.executable,'-c','import time;time.sleep(1)'],d/'timeout',.02)
        assert expired['expired'] and expired['rc']!=0
        count=list((b.ROOT/'hall3_inputs/cnf').glob('21-*.cnf'))
        if not count:count=[b.ROOT.parent/'math5-frozen/MATH5/inputs/count21.original.cnf']
        assert len(count)==1 and b.sha(count[0])=='23702be6f54e7c6722880ea44f26ce4c7ca01791631cdfc8bce47c18615477c6'
        s=dict(id=21,family='KNOWN_COUNT_CONTROL',path=str(count[0]),sha256=b.sha(count[0]))
        row=b.trial(s,'MATH5',0,d/'known-count',cap=5)
        assert row['accepted'] and not row['strict_accepted'] and row['certificate_kind'].startswith('STRUCTURAL_'),row
        cert=d/'known-count/structural.json';proof=json.loads(cert.read_text());proof['source_sha256']='0'*64;cert.write_text(json.dumps(proof))
        rejected=b.run([sys.executable,str(b.ROOT/'research/math5/check_math5.py'),str(count[0]),str(cert)],d/'corrupt-check',5)
        assert rejected['rc']!=0 and not rejected['expired']
        print('BLIND_PREFLIGHT_PASS',flush=True)
if __name__=='__main__':main()
